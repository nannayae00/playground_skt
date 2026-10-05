"""
moyo_scraper.py  v6.4
─────────────────────────────────────────────────────────────────────────────
v6.4 변경 (2026-07-03):
  - RS 판단 로직 근본 수정: data_gb 기반 fallback 추가
    · 기존: RS_RULES 딕셔너리 exact match만 → 125GB, 160GB 등 누락
    · 추가: RS_RULES 미매칭 시 fallback 룰 적용
            data_gb >= 100 AND 통화 무제한 AND 문자 무제한 → RS (100G+)
    · 5G/LTE 구분 없이 동일 적용
    · 매일 2GB 포함 케이스는 기존 RS_RULES 유지
─────────────────────────────────────────────────────────────────────────────
v6.3 변경 (2026-07-03):
  - 페이백 배지 끼어들기 파싱 버그 수정
    · 증상: '페이백 포함' 배지가 parts 중간(offset+7 위치)에 삽입되어
            price_raw가 '페이백 포함'으로 파싱 → _price()=0 → 카드 누락
    · 원인: parts 구조가 정상 10개 → 배지 포함 11개로 늘어나면서 offset 밀림
    · 수정: _parse_card()에서 parts 파싱 전 배지 텍스트 사전 제거
            BADGE_TEXTS = {'페이백 포함', ...} 패턴으로 필터링
    · 영향: 페이백 배지 포함 카드 정상 수집 (예: 26613, 30954 등)
─────────────────────────────────────────────────────────────────────────────
v6.2 변경 (2026-06-30):
  - RS 오분류 버그 수정: isRsBadge 클래스 셀렉터 제거
    · 증상: classify_rs()가 정확히 RM으로 판단해도, 카드 내 클래스명에
            "rs"/"RS" 글자만 포함되면 강제로 RS로 덮어써지는 문제
            (Tailwind 'cursor-pointer' 등 흔한 클래스도 "rs" 부분문자열 포함)
            → 특정 수집 시점에 거의 전체가 RS로 오분류 (예: RS 2449/RM 0)
    · 원인: card.querySelector('[class*="rs"]') / '[class*="RS"]' 가
            RS 표시 의도와 무관한 요소까지 광범위하게 매칭
    · 수정: isRsBadge 판정에서 클래스 셀렉터 제거, 텍스트 키워드
            ('도매제공', '의무제공') 매칭만 유지
    · 영향: RS_RULES 룰 매칭(classify_rs) 결과가 그대로 최종 is_rs로 반영됨
            (룰 누락분 보완용 안전망이었던 클래스 감지만 제거, 텍스트 감지는 유지)
─────────────────────────────────────────────────────────────────────────────
v6.1 변경 (2025-04-23):
  - 이지모바일 Mbps 소수점 표기 오분류 버그 수정
    · 증상: 1.024Mbps / 5.12Mbps 표기로 RS_RULES 매칭 실패 → RM 오판
    · 원인: _normalize_data()가 Mbps 소수점 정규화를 하지 않음
    · 수정: _normalize_data()에 범용 Mbps 정규화 추가 (방법 C)
            소수점 Mbps → round() 정수 변환 (1.024→1, 5.12→5)
    · 영향: 이지모바일 46개 행 RS 정상 판단, 타사 소수점 케이스도 대응
─────────────────────────────────────────────────────────────────────────────
v6.0 변경:
  - RS 판단 로직 전면 재설계
    · 기존: RS_DATA_SET (데이터 문자열만 매칭)
    · 변경: RS_RULES (데이터 + 통화 조합으로 판단) + segment 동시 맵핑
  - 월 15GB + 3Mbps → 통화 100분/300분에 따라 15G+100 / 15G+300 구간 분리
  - 통화 무제한 + 문자 무제한 케이스(데이터 없음) 처리
  - 매일 5GB / 월 5GB + 매일 5GB 등 일일 단위 데이터 → 100G+ 구간
  - segment 맵핑을 scraper에서 직접 수행 (comparator 의존 제거)
─────────────────────────────────────────────────────────────────────────────
v5.4 변경:
  - 파싱 실패 시 로그 출력 추가 (parts<7, final_price==0)
  - _collect_cards 카드 파싱 실패 시 plan_id/alt 로그 출력
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
from core.rs2_classifier import classify_rs2
from datetime import datetime
import re
import asyncio

BASE_URL    = "https://www.moyoplan.com/plans"
MAX_PAGES   = 300
EMPTY_STOP  = 3
PAGE_WAIT   = 500   # ms
RETRY_MAX   = 3
RETRY_WAIT  = 2000  # ms


# ── RS 판단 규칙 테이블 ────────────────────────────────────────────────────────
# 키: (데이터 정규화 문자열, 통화 키워드)
#   - 통화 키워드: '무제한' | '100분' | '300분' | '*' (통화 무관)
# 값: (is_rs, segment)
#
# 통화 정규화: '통화 무제한' → '무제한', '통화 100분' → '100분' 등
# ※ 매칭 우선순위: 정확한 (데이터, 통화) 쌍 → (데이터, '*') 순

RS_RULES = {
    # 데이터                              통화       구간
    ('매일 5GB + 5Mbps',                '무제한'):  '100G+',
    ('월 100GB + 5Mbps',                '무제한'):  '100G+',
    ('월 10GB + 1Mbps',                 '무제한'):  '10G+',
    ('월 10GB + 3Mbps',                 '무제한'):  '11G+',
    ('월 10GB + 매일 2GB + 3Mbps',      '무제한'):  '11G+',
    ('월 110GB + 5Mbps',                '무제한'):  '100G+',
    ('월 11GB + 매일 2GB + 3Mbps',      '무제한'):  '11G+',
    ('월 150GB + 5Mbps',                '무제한'):  '100G+',
    ('월 15GB + 3Mbps',                 '100분'):   '15G+100',
    ('월 15GB + 3Mbps',                 '300분'):   '15G+300',
    ('월 180GB + 10Mbps',               '무제한'):  '100G+',
    ('월 200GB + 10Mbps',               '무제한'):  '100G+',
    ('월 200GB + 5Mbps',                '무제한'):  '100G+',
    ('월 210GB + 5Mbps',                '무제한'):  '100G+',
    ('월 250GB + 5Mbps',                '무제한'):  '100G+',
    ('월 300GB + 5Mbps',                '무제한'):  '100G+',
    ('월 6GB + 1Mbps',                  '무제한'):  '7G+',
    ('월 7GB + 1Mbps',                  '무제한'):  '7G+',
    ('월 8GB + 1Mbps',                  '무제한'):  '7G+',
    ('월 9GB + 1Mbps',                  '무제한'):  '7G+',
    ('월 71GB + 매일 2GB + 3Mbps',      '무제한'):  '11G+',
    ('월 11GB + 3Mbps',                 '무제한'):  '11G+',
    ('월 100GB + 3Mbps',                '무제한'):  '100G+',
    ('월 5GB + 매일 5GB + 5Mbps',       '무제한'):  '100G+',
    ('월 11GB + 매일 2GB',              '무제한'):  '11G+',
    ('월 11GB + 400Kbps',               '무제한'):  '11G+',
    # 데이터 없음 케이스: 통화 무제한 + 문자 무제한
    ('통화 무제한',                      '문자무제한'): '11G+',
}

# 통화 정규화 함수
def _normalize_voice(raw: str) -> str:
    """'통화 무제한' → '무제한', '통화 100분' → '100분', '문자 무제한' → '문자무제한'"""
    r = raw.strip()
    if '문자' in r and '무제한' in r:
        return '문자무제한'
    if '무제한' in r:
        return '무제한'
    m = re.search(r'(\d+)분', r)
    if m:
        return f"{m.group(1)}분"
    return r

def _normalize_data(raw: str) -> str:
    """
    데이터 문자열 정규화:
      1) 공백 정규화
      2) 소수점 Mbps → 반올림 정수 Mbps 변환 (방법 C, 범용)
         예) 1.024Mbps → 1Mbps, 5.12Mbps → 5Mbps
         이유: 이지모바일이 1Mbps → 1.024Mbps, 5Mbps → 5.12Mbps로 표기 변경
               RS_RULES 키는 정수 Mbps 기준이므로 정규화 필요
    """
    normalized = re.sub(r'\s+', ' ', raw.strip())
    # 소수점 Mbps를 반올림 정수로 변환 (정수 표기는 그대로 통과)
    normalized = re.sub(
        r'([\d.]+)\s*Mbps',
        lambda m: f"{round(float(m.group(1)))}Mbps",
        normalized
    )
    return normalized

def classify_rs(data_raw: str, voice_raw: str, sms_raw: str = ''):
    """
    Returns (is_rs: bool, segment: str | None)
    segment는 RS_RULES에 정의된 구간, RS가 아니면 None

    판단 순서:
    1) RS_RULES exact match
    2) fallback: data_gb >= 100 + 통화 무제한 + 문자 무제한 → RS 100G+
    """
    data  = _normalize_data(data_raw)
    voice = _normalize_voice(voice_raw)

    # 1) 정확한 (데이터, 통화) 매칭
    seg = RS_RULES.get((data, voice))
    if seg is not None:
        return True, seg

    # 2) fallback: data_gb >= 100 + 통화 무제한 + 문자 무제한 → RS 100G+
    data_gb = _data_gb(data_raw)
    sms_normalized = sms_raw.strip().replace('문자', '').strip()
    if (data_gb >= 100
            and voice == '무제한'
            and '무제한' in sms_raw):
        return True, '100G+'

    return False, None


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
    m = re.search(r'([\d,]+)명', raw)
    return int(m.group(1).replace(',', '')) if m else 0

# 카드 텍스트에 끼어들 수 있는 배지 텍스트 목록 (offset 밀림 방지용)
BADGE_TEXTS = {'페이백 포함', '모요개통', '모요ONLY', '모요only'}


def _parse_card(card_el):
    """JS evaluate 결과 dict → plan dict"""
    text_raw = card_el.get('_text', '')
    # 배지 텍스트 사전 제거 (페이백 포함 등이 끼어들면 offset이 밀려 파싱 실패)
    parts    = [p for p in text_raw.split('|') if p.strip() and p.strip() not in BADGE_TEXTS]
    provider = card_el.get('_alt', '기타/확인불가')
    plan_id  = card_el.get('_id', '')

    if len(parts) < 7:
        print(f"⚠️ 파싱 실패 (parts={len(parts)}) id={plan_id} text={text_raw[:120]}")
        return None

    offset = 1 if re.match(r'^[\d.]+$', parts[0]) else 0

    name      = parts[offset]     if len(parts) > offset     else f'요금제 {plan_id}'
    data_raw  = parts[offset + 1] if len(parts) > offset + 1 else ''
    voice_raw = parts[offset + 2] if len(parts) > offset + 2 else '제공안함'
    sms       = parts[offset + 3] if len(parts) > offset + 3 else '제공안함'
    net_raw   = parts[offset + 4] if len(parts) > offset + 4 else ''
    gen_raw   = parts[offset + 5] if len(parts) > offset + 5 else 'LTE'
    price_raw = parts[offset + 6] if len(parts) > offset + 6 else ''
    after_raw = parts[offset + 7] if len(parts) > offset + 7 else ''
    subs_raw  = parts[offset + 8] if len(parts) > offset + 8 else ''

    final_price                  = _price(price_raw)
    discount_months, base_price  = _after(after_raw)
    if base_price == 0: base_price = final_price
    if final_price == 0:
        print(f"⚠️ 파싱 실패 (price=0) id={plan_id} price_raw={price_raw!r}")
        return None

    voice = re.sub(r'^통화\s*', '', voice_raw)
    sms   = re.sub(r'^문자\s*', '', sms)

    # ── RS 판단 (데이터 + 통화 조합) ──────────────────────────────────────
    is_rs, rs_segment = classify_rs(data_raw, voice_raw, sms)

    data_gb    = _data_gb(data_raw)
    data_label = '무제한' if data_gb == 9999 else _normalize_data(data_raw)  # v6.1: Mbps 정규화 포함

    is_rs2 = classify_rs2(provider, name)
    subscribers = _subscribers(subs_raw)

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
        'rs_segment':         rs_segment,   # RS인 경우 확정 구간, 아니면 None
        'is_rs2':             is_rs2,
        'subscribers':        subscribers,
        'scraped_at':         datetime.utcnow().isoformat(),
    }


async def _collect_cards(page, seen_ids):
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
                                  allText.includes('의무제공');
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
            if badge_rs and not plan['is_rs']:
                # 뱃지가 있는데 룰 매칭 안 된 경우 → RS로 표시하되 segment 없음
                plan['is_rs']     = True
                plan['rs_source'] = 'badge'
            elif plan['is_rs']:
                plan['rs_source'] = 'rules'
            else:
                plan['rs_source'] = 'none'
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
        print("🔍 모요 스크래핑 시작 (v6.2 - RS 뱃지 클래스 오탐 제거)")
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

                        for p in page_plans:
                            seen_ids.discard(str(p.get('plan_id', '')))

                        await page.reload(timeout=60_000, wait_until='domcontentloaded')
                        await page.wait_for_timeout(RETRY_WAIT)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(400)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(200)

                        page_plans = await _collect_cards(page, seen_ids)

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

        total     = len(all_plans)
        rs_tot    = sum(1 for p in all_plans if p.get('is_rs'))
        rs_rules  = sum(1 for p in all_plans if p.get('rs_source') == 'rules')
        rs_badge  = sum(1 for p in all_plans if p.get('rs_source') == 'badge')
        unknown   = sum(1 for p in all_plans if p['provider'] == '기타/확인불가')
        print(f"\n🎉 최종 수집: {total}개 (RS: {rs_tot}개 / RM: {total-rs_tot}개)")
        print(f"   RS 룰 매칭: {rs_rules}개 / 뱃지 감지: {rs_badge}개")
        print(f"   사업자 미파싱: {unknown}개")

        return all_plans, "/tmp/moyo_last.png"