"""
moyo_scraper.py  v5.4
─────────────────────────────────────────────────────────────────────────────
v5.4 변경:
  - 파싱 실패 시 로그 출력 추가 (parts<7, final_price==0)
  - _collect_cards 카드 파싱 실패 시 plan_id/alt 로그 출력
  - Cloud Run 로그에서 누락 요금제 원인 추적 가능
─────────────────────────────────────────────────────────────────────────────
v5.3 변경:
  - 스크롤 추가 (lazy loading 트리거) - PAGE_WAIT는 그대로 500ms 유지
  - 재시도 로직 seen_ids 버그 수정
  - RETRY_WAIT 2000ms로 증가
─────────────────────────────────────────────────────────────────────────────
카드 텍스트 구조 (| 분리):
  [offset+0] 요금제명
  [offset+1] 데이터
  [offset+2] 통화
  [offset+3] 문자
  [offset+4] 사용망
  [offset+5] 네트워크세대
  [offset+6] 할인후금액    ex) '월 17,000원'
  [offset+7] 할인개월+전금액 ex) '7개월 이후 47,300원'
  [offset+8] 가입자수      ex) '9,275명이 선택'  (없을 수 있음)
─────────────────────────────────────────────────────────────────────────────
"""

from playwright.async_api import async_playwright
# from core.rs2_classifier import classify_rs2  # RS2 제거
from datetime import datetime
import re
import asyncio

BASE_URL   = "https://www.moyoplan.com/plans"
MAX_PAGES  = 300
EMPTY_STOP  = 3
PAGE_WAIT   = 500   # ms - 정상 페이지 대기 (변경 없음)
RETRY_MAX   = 3     # 10개 미만 시 최대 재시도 횟수
RETRY_WAIT  = 2000  # ms - 재시도 대기 (1000 → 2000으로 증가)

# ── RS 요금제 데이터 패턴 (RPA 룰베이스 동일 적용) ───────────────────────────
RS_DATA_SET = {
    '월 7GB + 1Mbps', '월 10GB + 1Mbps', '월 11GB + 매일 2GB + 3Mbps',
    '월 15GB + 3Mbps', '매일 5GB + 5Mbps', '월 1.4GB + 1Mbps',
    '월 100GB + 515024Mbps', '월 100GB + 5Mbps', '월 10GB + 3Mbps',
    '월 10GB + 매일 2GB + 3Mbps', '월 110GB + 1Mbps', '월 110GB + 5Mbps',
    '월 11GB + 1Mbps', '월 11GB + 3Mbps', '월 125GB + 5Mbps',
    '월 12GB + 1Mbps', '월 135GB + 3Mbps', '월 13GB + 1Mbps',
    '월 150GB + 5Mbps', '월 15GB + 1Mbps', '월 15GB + 35024Mbps',
    '월 160GB + 5Mbps', '월 17GB + 3Mbps', '월 180GB + 10Mbps',
    '월 1GB + 1Mbps', '월 2.25GB + 1Mbps', '월 2.2GB + 1Mbps',
    '월 2.5GB + 1Mbps', '월 200GB + 10Mbps', '월 200GB + 5Mbps',
    '월 210GB + 5Mbps', '월 24GB + 1Mbps', '월 250GB + 5Mbps',
    '월 250MB + 1Mbps', '월 2GB + 1Mbps', '월 3.5GB + 1Mbps',
    '월 300GB + 5Mbps', '월 300MB + 1Mbps', '월 30GB + 1Mbps',
    '월 30GB + 매일 2GB + 5Mbps', '월 31GB + 1Mbps', '월 36GB + 1Mbps',
    '월 3GB + 1Mbps', '월 3GB +월 4GB + 1Mbps', '월 4.5GB + 1Mbps',
    '월 40GB + 3Mbps', '월 41GB + 1Mbps', '월 4GB + 1Mbps',
    '월 50GB + 1Mbps', '월 54GB + 1Mbps', '월 5GB + 1Mbps',
    '월 5GB + 5Mbps', '월 6GB + 1Mbps', '월 70GB + 1Mbps',
    '월 74GB + 1Mbps', '월 750MB + 1Mbps', '월 80GB + 1Mbps',
    '월 8GB + 1Mbps', '월 90GB + 1Mbps', '월 95GB + 3Mbps',
    '월 99GB + 1Mbps', '월 9GB + 1Mbps',
}


# ── 파싱 유틸 ─────────────────────────────────────────────────────────────────

def _network(raw):
    r = raw.replace('망', '').replace(' ', '')
    if 'SKT' in r:                  return 'SKT'
    if 'KT' in r and 'U' not in r:  return 'KT'
    return 'LGU+'

def _data_gb(raw):
    if '무제한' in raw: return 9999
    m = re.search(r'([\d.]+)\s*GB', raw)
    return float(m.group(1)) if m else 0

def _price(raw):
    m = re.search(r'([\d,]+)원', raw)
    return int(m.group(1).replace(',', '')) if m else 0

def _after(raw):
    """'7개월 이후 47,300원' → (7, 47300)"""
    months_m = re.search(r'(\d+)개월', raw)
    price_m  = re.search(r'([\d,]+)원', raw)
    months   = int(months_m.group(1)) if months_m else 0
    price    = int(price_m.group(1).replace(',', '')) if price_m else 0
    return months, price

def _subscribers(raw):
    """'9,275명이 선택' → 9275"""
    m = re.search(r'([\d,]+)명', raw)
    return int(m.group(1).replace(',', '')) if m else 0

def _parse_card(card_el):
    """JS evaluate 결과 dict → plan dict"""
    text_raw = card_el.get('_text', '')
    parts    = [p for p in text_raw.split('|') if p.strip()]
    provider = card_el.get('_alt', '기타/확인불가')
    plan_id  = card_el.get('_id', '')

    if len(parts) < 7:
        print(f"⚠️ 파싱 실패 (parts={len(parts)}) id={plan_id} text={text_raw[:120]}")
        return None

    offset = 1 if re.match(r'^[\d.]+$', parts[0]) else 0

    name      = parts[offset]     if len(parts) > offset     else f'요금제 {plan_id}'
    data_raw  = parts[offset + 1] if len(parts) > offset + 1 else ''
    voice     = parts[offset + 2] if len(parts) > offset + 2 else '제공안함'
    sms       = parts[offset + 3] if len(parts) > offset + 3 else '제공안함'
    net_raw   = parts[offset + 4] if len(parts) > offset + 4 else ''
    gen_raw   = parts[offset + 5] if len(parts) > offset + 5 else 'LTE'
    price_raw = parts[offset + 6] if len(parts) > offset + 6 else ''
    after_raw = parts[offset + 7] if len(parts) > offset + 7 else ''
    subs_raw  = parts[offset + 8] if len(parts) > offset + 8 else ''

    final_price              = _price(price_raw)
    discount_months, base_price = _after(after_raw)
    if base_price == 0: base_price = final_price
    if final_price == 0:
        print(f"⚠️ 파싱 실패 (price=0) id={plan_id} price_raw={price_raw!r}")
        return None

    voice = re.sub(r'^통화\s*', '', voice)
    sms   = re.sub(r'^문자\s*', '', sms)

    data_gb    = _data_gb(data_raw)
    data_label = '무제한' if data_gb == 9999 else data_raw
    is_rs      = data_label.strip() in RS_DATA_SET
    subscribers = _subscribers(subs_raw)

    is_rs2 = False  # RS2 제거

    return {
        'plan_id':            plan_id,
        'provider':           provider,
        'name':               name,
        'data':               data_label,
        'data_gb':            data_gb,
        'voice':              voice,
        'sms':                sms,
        'network':            _network(net_raw),
        'network_generation': '5G' if '5G' in gen_raw else 'LTE',
        'final_price':        final_price,
        'base_price':         base_price,
        'discount_months':    discount_months,
        'is_rs':              is_rs,
        'is_rs2':             is_rs2,
        'subscribers':        subscribers,
        'scraped_at':         datetime.utcnow().isoformat(),
    }


async def _collect_cards(page, seen_ids):
    """현재 페이지에서 카드 수집. seen_ids에 없는 신규 plan만 반환."""
    card_data = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('a[href^="/plans/"]');
            return Array.from(cards).map(card => {
                const href = card.getAttribute('href') || '';
                const id   = href.replace('/plans/', '');
                const img  = card.querySelector('img');
                const alt  = img ? (img.alt || '') : '';
                const text = card.innerText
                    .split('\\n')
                    .map(s => s.trim())
                    .filter(s => s.length > 0)
                    .join('|');
                const allText = card.innerText || '';
                const isRsBadge = allText.includes('도매제공') ||
                                  allText.includes('의무제공') ||
                                  card.querySelector('[class*="rs"]') !== null ||
                                  card.querySelector('[class*="RS"]') !== null;
                const ariaLabel = card.getAttribute('aria-label') || '';
                const dataRs = card.getAttribute('data-rs') || '';
                return { id, alt, text, isRsBadge, ariaLabel, dataRs };
            });
        }
    """)

    page_plans = []
    for item in card_data:
        plan_id = item.get('id', '')
        if not plan_id or plan_id in seen_ids:
            continue
        plan = _parse_card({
            '_id':   plan_id,
            '_alt':  item.get('alt', '기타/확인불가') or '기타/확인불가',
            '_text': item.get('text', ''),
        })
        if plan is None:
            print(f"⚠️ 카드 파싱 실패 plan_id={plan_id} alt={item.get('alt','?')}")
            continue
        if plan:
            badge_rs = item.get('isRsBadge', False)
            if badge_rs:
                plan['is_rs'] = True
                plan['rs_source'] = 'badge'
            else:
                plan['rs_source'] = 'dataset'
            page_plans.append(plan)

    return page_plans


# ── 메인 스크래퍼 ─────────────────────────────────────────────────────────────

class MoyoScraper:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback

    def scrape(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._scrape_async())
        finally:
            loop.close()

    async def _scrape_async(self):
        print("🔍 모요 스크래핑 시작 (v5.3 - 스크롤 추가 + 재시도 버그 수정)")
        all_plans    = []
        seen_ids     = set()
        consec_empty = 0

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox',
                      '--disable-dev-shm-usage', '--disable-gpu']
            )
            context = await browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            )
            page = await context.new_page()

            for page_num in range(1, MAX_PAGES + 1):
                url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
                try:
                    await page.goto(url, timeout=60_000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(PAGE_WAIT)

                    # ── lazy loading 트리거 (스크롤 다운 → 업) ────────────
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(400)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(200)

                    html_content = await page.content()
                    found_ids    = list(dict.fromkeys(
                        re.findall(r'/plans/(\d+)', html_content)
                    ))
                    unique_ids   = [pid for pid in found_ids if pid not in seen_ids]

                    if not unique_ids:
                        consec_empty += 1
                        if consec_empty >= EMPTY_STOP:
                            print(f"🛑 {consec_empty}회 연속 빈 페이지 → 종료")
                            break
                        continue

                    consec_empty = 0

                    # ── 10개 미만이면 최대 RETRY_MAX회 재시도 ──────────────
                    # v5.3 버그 수정: 재시도 시 seen_ids 관리를 루프 밖에서 처리
                    page_plans = await _collect_cards(page, seen_ids)

                    for retry in range(1, RETRY_MAX + 1):
                        is_last = (page_num == MAX_PAGES)
                        if len(page_plans) >= 10 or is_last:
                            break

                        retry_msg = (f"⚠️ {page_num}p {len(page_plans)}개 수집 "
                                     f"→ 재시도 {retry}/{RETRY_MAX}")
                        print(retry_msg)
                        if self.progress_callback:
                            self.progress_callback(retry_msg)

                        # 이번 시도에서 수집한 ID를 seen_ids에서 제거 후 재수집
                        for p in page_plans:
                            seen_ids.discard(str(p.get('plan_id', '')))

                        await page.reload(timeout=60_000, wait_until='domcontentloaded')
                        await page.wait_for_timeout(RETRY_WAIT)

                        # 재시도 시에도 스크롤 적용
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(400)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(200)

                        page_plans = await _collect_cards(page, seen_ids)

                    # 최종 확정된 plan_id를 seen_ids에 추가
                    for p in page_plans:
                        seen_ids.add(str(p.get('plan_id', '')))

                    all_plans.extend(page_plans)

                    rs_count = sum(1 for p in page_plans if p.get('is_rs'))
                    msg = (f"✅ {page_num}p 완료 | "
                           f"이번 {len(page_plans)}개 | 누적 {len(all_plans)}개 | "
                           f"RS {rs_count}/{len(page_plans)}")
                    print(msg)
                    if self.progress_callback:
                        self.progress_callback(msg)

                except Exception as e:
                    print(f"⚠️ {page_num}페이지 에러: {e}")
                    continue

            await browser.close()

        total    = len(all_plans)
        rs_tot   = sum(1 for p in all_plans if p.get('is_rs'))
        rs_badge = sum(1 for p in all_plans if p.get('rs_source') == 'badge')
        unknown  = sum(1 for p in all_plans if p['provider'] == '기타/확인불가')
        print(f"\n🎉 최종 수집: {total}개 (RS: {rs_tot}개 / RM: {total-rs_tot}개)")
        print(f"   RS 뱃지 감지: {rs_badge}개 / 데이터셋 기준: {rs_tot-rs_badge}개")
        print(f"   사업자 미파싱: {unknown}개")

        return all_plans, "/tmp/moyo_last.png"