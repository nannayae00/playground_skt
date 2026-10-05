"""
mvnohub_scraper.py  v0.7
─────────────────────────────────────────────────────────────────────────────
알뜰폰허브 (https://www.mvnohub.kr/product/products.do) 요금제 스크래퍼

[수정 이력]
  v0.1  2026-04-11  최초 작성
  v0.7  2026-04-11  봇 차단 우회 강화
        - 고정 PAGE_WAIT → 랜덤 2500~4500ms (_rand_wait())
        - 페이지 클릭 후 plan_card 렌더링 감지 (wait_for_selector)
        - 스크롤 시뮬레이션 (scrollTo 중간→상단) 추가
  v0.6  2026-04-11  data_gb=0 후처리 추가
        - 0GB+XMbps → 요금제명에서 NGB 추출 → '매일 NGB + XMbps' 변환
        - GB 추출 불가(WELL 공유 240분 등 음성전용) → 수집 제외
  v0.5  2026-04-11  데이터 파싱 개선
        - getLiText: 줄바꿈/다중공백 → 단일공백 정규화
        - _parse_data_label: '데이터 ' 접두어 잔류 제거
        - '일XGB' → '매일 XGB' 변환 추가
  v0.4  2026-04-11  swiper-wrapper 내 카드 제외 (추천 슬라이더 중복 수집 방지)
        - JS_COLLECT: closest('.swiper-wrapper') 체크로 슬라이더 카드 스킵
        - 실제 요금제 목록 카드만 수집 (페이지당 ~12개 정상화)
  v0.3  2026-04-11  페이지네이션 button+data-page 방식으로 전면 교체
        - ul.pagination button[data-page] (0-indexed)
        - JS_GET_TOTAL_PAGES: data-page 최대값+1
        - JS_CLICK_DATA_PAGE: data-page 속성으로 직접 클릭
        - JS_GET_VISIBLE_DATA_PAGES: 현재 보이는 data-page 목록
        - 카드: div.plan_card (data-product-id 속성으로 plan_id)
        - 요금제명: p.tit
        - 망/사업자: div.posi ul li[0]/li[1]
        - 세대: div.tips span (LTE=purple, 5G=blue 등)
        - 현재가: div.price p.now span
        - 이후가: p.time_after span + 개월수
        - 데이터: li.wifi, 통화: li.call, 문자: li.mes
        - 페이지네이션: ul.pagination 기반 (swiper는 카드 컨테이너용)

사이트 특성:
  - KAIT(한국정보통신진흥협회) 운영 공식 알뜰폰 비교 플랫폼
  - SSR(서버사이드렌더링) + 페이지네이션
  - TRACER 봇차단: User-Agent + 딜레이 필수
  - 가입자수 없음

DOM 구조 (실측 확인):
  카드        : div.plan_card (data-product-id 속성)
  plan_id     : data-product-id
  요금제명    : p.tit (title 속성 우선)
  망/사업자   : div.posi ul li[0]=망, li[1]=사업자
  세대        : div.tips span (LTE/5G 텍스트)
  현재가      : div.price p.now span
  이후가      : p.time_after (전체 텍스트)
  데이터      : li.wifi
  통화        : li.call
  문자        : li.mes
  페이지네이션: ul.pagination li a
─────────────────────────────────────────────────────────────────────────────
"""

import re
import asyncio
from playwright.async_api import async_playwright
from scrapers.base_scraper import (
    BaseScraper, make_plan,
    COMMON_UA, BROWSER_ARGS,
)

BASE_URL  = 'https://www.mvnohub.kr/product/products.do'
SOURCE    = 'mvnohub'
import random

PAGE_WAIT_MIN = 2500   # 최소 대기 (ms)
PAGE_WAIT_MAX = 4500   # 최대 대기 (ms)
NAV_WAIT  = 2500


def _rand_wait():
    """2500~4500ms 랜덤 딜레이"""
    return random.randint(PAGE_WAIT_MIN, PAGE_WAIT_MAX)


# ── 파싱 유틸 ────────────────────────────────────────────────────────────────

def _parse_network(raw: str) -> str:
    """'SKT' / 'KT' / 'LGU+' 반환"""
    r = raw.replace(' ', '').upper()
    if 'SKT' in r:                     return 'SKT'
    if 'LGU' in r or 'LGUPLUS' in r:  return 'LGU+'
    if 'KT' in r:                      return 'KT'
    return 'SKT'  # fallback


def _parse_data_label(raw: str) -> str:
    """
    '6GB'              → '월 6GB'
    '11GB+3Mbps'       → '월 11GB + 3Mbps'
    '매일 5GB+5Mbps'   → '매일 5GB + 5Mbps'
    '매일5GB+5Mbps'    → '매일 5GB + 5Mbps'
    '일5GB+5Mbps'      → '매일 5GB + 5Mbps'
    '데이터 6GB'        → '월 6GB'
    '무제한'            → '무제한'
    이미 '월 ...' 형식이면 그대로
    """
    raw = raw.strip()
    if not raw:
        return ''

    # '데이터 ' 접두어 잔류 방지
    raw = re.sub(r'^데이터\s*', '', raw).strip()

    # '+' 공백 정규화
    raw = re.sub(r'\s*\+\s*', ' + ', raw)

    if raw.startswith('월 '):
        return raw
    if '무제한' in raw:
        return raw

    # '매일5GB' → '매일 5GB' (공백 없는 경우)
    raw = re.sub(r'^매일(\d)', r'매일 \1', raw)
    if raw.startswith('매일 '):
        return raw

    # '일5GB+5Mbps' → '매일 5GB + 5Mbps'
    raw = re.sub(r'^일(\d)', r'매일 \1', raw)
    if raw.startswith('매일'):
        return raw

    return '월 ' + raw


def _parse_voice(raw: str) -> str:
    raw = raw.strip()
    if not raw or '무제한' in raw:
        return '무제한'
    m = re.search(r'(\d[\d,]*)\s*분', raw)
    if m:
        return m.group(1).replace(',', '') + '분'
    return raw


def _parse_sms(raw: str) -> str:
    raw = raw.strip()
    if not raw or '무제한' in raw:
        return '무제한'
    m = re.search(r'(\d[\d,]*)\s*건', raw)
    if m:
        return m.group(1).replace(',', '') + '건'
    return raw


def _parse_price_texts(current_txt: str, after_txt: str):
    """
    current_txt  : '20,000' or '월 20,000원' or '20,000원'
    after_txt    : '7개월 이후 42,900원/월' or ''
    → (final_price, base_price, discount_months)
    """
    m0 = re.search(r'([\d,]+)', current_txt.replace(' ', ''))
    final_price = int(m0.group(1).replace(',', '')) if m0 else 0
    if not final_price:
        return 0, 0, 0

    base_price  = final_price
    disc_months = 0
    if after_txt:
        m1 = re.search(r'(\d+)개월', after_txt)
        m2 = re.search(r'([\d,]+)원', after_txt)
        if m1:
            disc_months = int(m1.group(1))
        if m2:
            base_price = int(m2.group(1).replace(',', ''))

    return final_price, base_price, disc_months


# ── JS 스니펫 ────────────────────────────────────────────────────────────────

JS_COLLECT = """
() => {
    var results = [];
    var seen    = new Set();

    // swiper-wrapper 안 카드는 추천 슬라이더 → 제외
    // 실제 요금제 목록: swiper-wrapper 밖의 div.plan_card
    var cards = document.querySelectorAll('div.plan_card');
    cards.forEach(function(card) {
        // swiper-slide 안에 있으면 스킵
        if (card.closest('.swiper-wrapper') || card.closest('.swiper-slide')) return;

        var pid = card.getAttribute('data-product-id') || '';
        if (!pid || seen.has(pid)) return;
        seen.add(pid);

        // 요금제명
        var titEl = card.querySelector('p.tit');
        var name  = titEl ? titEl.getAttribute('title') || titEl.innerText.trim() : '';
        name = name.replace(/^\\[.*?\\]\\s*/, '').trim();

        // 망 / 사업자
        var posiLis = card.querySelectorAll('div.posi ul li');
        var network  = posiLis[0] ? posiLis[0].innerText.trim() : '';
        var provider = posiLis[1] ? posiLis[1].innerText.trim() : '';

        // 세대
        var netGen = 'LTE';
        card.querySelectorAll('div.tips span').forEach(function(sp) {
            if (sp.innerText.trim().toUpperCase() === '5G') netGen = '5G';
        });

        // 현재가
        var nowEl      = card.querySelector('div.price p.now span');
        var currentTxt = nowEl ? nowEl.innerText.trim() : '';

        // 이후가
        var afterEl  = card.querySelector('p.time_after');
        var afterTxt = afterEl ? afterEl.innerText.trim() : '';

        // 데이터/통화/문자
        function getLiText(sel) {
            var el = card.querySelector(sel);
            if (!el) return '';
            var t = el.innerText.trim();
            // 줄바꿈/다중공백 → 단일 공백
            t = t.replace(/\\s+/g, ' ').trim();
            // 앞의 레이블(데이터/통화/문자) 제거
            t = t.replace(/^(데이터|통화|문자)\\s*/, '').trim();
            return t;
        }
        var data  = getLiText('li.wifi');
        var voice = getLiText('li.call');
        var sms   = getLiText('li.mes');

        results.push({
            pid: pid, name: name, network: network, provider: provider,
            netGen: netGen, data: data, voice: voice, sms: sms,
            currentTxt: currentTxt, afterTxt: afterTxt,
        });
    });

    return results;
}
"""

JS_GET_TOTAL_PAGES = """
() => {
    // data-page 속성 최대값 + 1 = 총 페이지 수 (0-indexed)
    var maxDataPage = 0;
    document.querySelectorAll('ul.pagination button[data-page]').forEach(function(btn) {
        var dp = parseInt(btn.getAttribute('data-page'));
        if (!isNaN(dp) && dp > maxDataPage) maxDataPage = dp;
    });
    return maxDataPage + 1;
}
"""

JS_CLICK_DATA_PAGE = """
(dataPage) => {
    // data-page 속성으로 직접 클릭 (0-indexed)
    var btns = document.querySelectorAll('ul.pagination button[data-page]');
    for (var i = 0; i < btns.length; i++) {
        var dp = parseInt(btns[i].getAttribute('data-page'));
        var cls = btns[i].className || '';
        if (dp === dataPage && !cls.includes('arrow') && !cls.includes('ellipsis')) {
            btns[i].click();
            return true;
        }
    }
    // 버튼이 보이지 않으면 다음 화살표 클릭
    var nextBtn = document.querySelector('ul.pagination button.arrow.right:not(.disabled)');
    if (nextBtn) { nextBtn.click(); return 'next'; }
    return false;
}
"""

JS_GET_VISIBLE_DATA_PAGES = """
() => {
    var nums = [];
    document.querySelectorAll('ul.pagination button[data-page]').forEach(function(btn) {
        var cls = btn.className || '';
        if (cls.includes('arrow') || cls.includes('ellipsis')) return;
        var dp = parseInt(btn.getAttribute('data-page'));
        if (!isNaN(dp)) nums.push(dp);
    });
    return nums;
}
"""


# ── 스크래퍼 ─────────────────────────────────────────────────────────────────

class MvnohubScraper(BaseScraper):
    SOURCE = SOURCE

    async def _scrape_async(self):
        self.progress('🔍 알뜰폰허브 스크래핑 시작')
        all_plans = []
        seen_ids  = set()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = await browser.new_context(
                user_agent=COMMON_UA,
                extra_http_headers={
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
            )
            page = await context.new_page()

            try:
                await page.goto(BASE_URL, timeout=60_000, wait_until='networkidle')
                await page.wait_for_timeout(_rand_wait())

                # 1) 총 페이지 수: data-page 최대값+1 (0-indexed)
                total_pages = await page.evaluate(JS_GET_TOTAL_PAGES)
                self.progress(f'📄 알뜰폰허브 총 {total_pages}페이지 감지')

                # 2) 0~(total_pages-1) 순회 (data-page 기준)
                data_page = 0
                while data_page < total_pages:
                    visible = await page.evaluate(JS_GET_VISIBLE_DATA_PAGES)

                    if data_page not in visible:
                        result = await page.evaluate(JS_CLICK_DATA_PAGE, data_page)
                        if result is False:
                            self.progress(f'⚠️ {data_page+1}p 이동 실패 → 종료')
                            break
                        await page.wait_for_timeout(NAV_WAIT)
                        continue

                    # 해당 data-page 버튼 클릭
                    clicked = await page.evaluate(JS_CLICK_DATA_PAGE, data_page)
                    if not clicked:
                        self.progress(f'⚠️ {data_page+1}p 클릭 실패 → 스킵')
                        data_page += 1
                        continue

                    # 카드 렌더링 대기: plan_card 등장 감지 + 랜덤 딜레이
                    try:
                        await page.wait_for_selector(
                            'div.plan_card:not(.swiper-slide *)',
                            timeout=8000
                        )
                    except Exception:
                        pass
                    # 스크롤 시뮬레이션 (봇 탐지 우회)
                    await page.evaluate(
                        "() => window.scrollTo(0, document.body.scrollHeight / 2)"
                    )
                    await page.wait_for_timeout(_rand_wait())
                    await page.evaluate("() => window.scrollTo(0, 0)")
                    await page.wait_for_timeout(300)

                    plans = await self._collect_page(page, seen_ids)
                    all_plans.extend(plans)
                    self.progress(f'✅ {data_page+1}p | 신규 {len(plans)}개 | 누적 {len(all_plans)}개')
                    data_page += 1

            except Exception as e:
                self.progress(f'⚠️ 알뜰폰허브 에러: {e}')
                import traceback
                self.progress(traceback.format_exc())
            finally:
                await browser.close()

        self.progress(f'🎉 알뜰폰허브 완료: {len(all_plans)}개')
        return all_plans, '/tmp/mvnohub_last.png'

    async def _collect_page(self, page, seen_ids: set) -> list:
        items = await page.evaluate(JS_COLLECT)
        plans = []
        for item in items:
            p = self._parse_item(item)
            if p and p['plan_id'] not in seen_ids:
                plans.append(p)
                seen_ids.add(p['plan_id'])
        return plans

    def _parse_item(self, item: dict):
        try:
            pid      = item.get('pid', '').strip()
            name     = item.get('name', '').strip()
            network  = _parse_network(item.get('network', ''))
            provider = item.get('provider', '알뜰폰허브').strip() or '알뜰폰허브'
            net_gen  = item.get('netGen', 'LTE').strip()

            data_raw = item.get('data', '').strip()
            voice_raw= item.get('voice', '').strip()
            sms_raw  = item.get('sms', '').strip()

            if not pid or not name:
                return None

            data_label = _parse_data_label(data_raw)
            voice      = _parse_voice(voice_raw)
            sms        = _parse_sms(sms_raw)

            final_price, base_price, disc_months = _parse_price_texts(
                item.get('currentTxt', ''), item.get('afterTxt', '')
            )
            if final_price == 0:
                return None

            # data_gb=0 후처리:
            # 0GB+XMbps → 요금제명에서 매일 NGB 추출 시도
            from scrapers.base_scraper import parse_data_gb
            data_gb_check = parse_data_gb(data_label)
            if data_gb_check == 0:
                # 요금제명에서 숫자GB 추출
                m = re.search(r'(\d+)\s*GB', name)
                if m:
                    gb = m.group(1)
                    # Mbps 부분 유지
                    mbps_m = re.search(r'(\d+)\s*Mbps', data_label, re.IGNORECASE)
                    mbps = mbps_m.group(0) if mbps_m else '5Mbps'
                    data_label = f'매일 {gb}GB + {mbps}'
                else:
                    # GB 추출 불가 → 제외
                    return None

            plan_id = f'mvnohub_{pid}'

            return make_plan(
                source=SOURCE,
                plan_id=plan_id,
                provider=provider,
                name=name,
                data=data_label,
                voice=voice,
                sms=sms,
                network=network,
                network_generation=net_gen,
                final_price=final_price,
                base_price=base_price,
                discount_months=disc_months,
                subscribers=0,
            )

        except Exception as e:
            print(f'⚠️ 알뜰폰허브 파싱 실패: {e} | {item}')
            return None