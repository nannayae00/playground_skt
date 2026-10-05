"""
aldot_scraper.py  v0.11
─────────────────────────────────────────────────────────────────────────────
알닷 (https://www.uplusmvno.com/plan/plan-list) 요금제 스크래퍼

변경 이력:
  v0.1  최초 작성 - .plan_item 선택자, 10페이지 페이지네이션
  v0.2  JS SyntaxError 수정 (f-string → evaluate(js, arg) 방식)
        가격 파싱 .month/.period 분리 (최종가/기본가/할인개월)
        _collect JS 내 따옴표 충돌 제거
  v0.3  페이지네이션 전략 변경 - 총 87페이지 지원
        .last 버튼으로 총 페이지 수 파악
        현재 묶음에 없는 번호면 .next 버튼으로 묶음 이동
        provider 파싱 개선 (siwol_logo_n2 → siwol)
  v0.4  PROVIDER_MAP 추가 - 알닷 영문 파일명 → 모요 한글 사업자명 매핑
        (asiamobile 등 모요 미등록 사업자는 raw값 유지)
  v0.5  asiamobile → 아시아모바일 매핑 추가
        통화(120분)/문자(100건) 수집 확인 - 기존 로직 정상 처리 확인
  v0.6  _parse_data() 수정 - 매일 시작 데이터에 월 붙이지 않음
        월 중복(월 월 ...) 제거 로직 추가 → RS 판정 정확도 향상
  v0.7  plan_tit_sub 텍스트노드 순회 파싱 → 월 10GB + 월 10GB 중복 방지
  v0.8  JS_COLLECT 중복 중괄호 제거 → SyntaxError 수정
  v0.9  JS_COLLECT 내 \'\\n\' → \'\\\\n\' 수정 (트리플쿼트 내 줄바꿈 이스케이프)
        JS 주석(//) 제거
  v0.10 _parse_data() 단기혜택 패턴 제거
        월 XGB + 월 YGB + ZMbps → 월 XGB + ZMbps (중간 월YGB는 단기혜택)
  v0.11 PROVIDER_MAP 대폭 확장
        amo→에이모바일, egm→이지모바일, freet→프리티, kgm→KG모바일 등
        알닷 raw 사업자명 → 모요 기준 한글 사업자명 통일

사이트 특성:
  - LGU+ 운영 알뜰폰 비교 플랫폼 (다수 사업자)
  - SPA(Vue.js) + 페이지네이션 (87페이지 × 10개 = 최대 870개)
  - 페이지 묶음 10개씩 표시, .next/.last 버튼으로 묶음 이동
  - 가입자수 없음

DOM 구조 (실측):
  카드        : .plan_item
  사업자      : .partner img src → 파일명 파싱
  요금제명    : .plan_tit (앞 [혜택명] 제거)
  데이터      : .plan_tit_sub
  통화/문자/망: .phone / .message / .cellular
  최종가      : .card_price .month
  기본가      : .card_price .period  예) '24개월 이후 56,800원'
  페이지 버튼 : .pagination ul li button
  이동 버튼   : .pagination .next / .last
─────────────────────────────────────────────────────────────────────────────
"""

import re
from playwright.async_api import async_playwright
from scrapers.base_scraper import (
    BaseScraper, make_plan,
    COMMON_UA, BROWSER_ARGS
)

BASE_URL  = 'https://www.uplusmvno.com/plan/plan-list'
SOURCE    = 'aldot'
PAGE_WAIT = 2500


# ── 파싱 유틸 ────────────────────────────────────────────────────────────────

# 알닷 이미지 파일명 → 모요 사업자명 매핑 테이블
PROVIDER_MAP = {
    # 이미지 파일명 → 모요 기준 한글 사업자명
    'asiamobile':    '아시아모바일',
    'siwol':         '시월모바일',
    'mona':          '모나',
    'kg':            'KG모바일',
    'kgm':           'KG모바일',
    'kgmobile':      'KG모바일',
    'ktm':           'KT엠모바일',
    'ktmobile':      'KT엠모바일',
    'ktskylife':     'KT스카이라이프',
    'hellovision':   'LG헬로모바일',
    'lghellovision': 'LG헬로모바일',
    'umobile':       'U+유모바일',
    'umo':           'U+유모바일',
    'sk7':           'SK7모바일',
    'sk7mobile':     'SK7모바일',
    'airbysk':       'air by SK telecom',
    'gogo':          '고고모바일',
    'gogomobile':    '고고모바일',
    'daewon':        '더원모바일',
    'theone':        '더원모바일',
    'liiv':          '리브모바일',
    'liivmobile':    '리브모바일',
    'mvp':           '마블링',
    'marbling':      '마블링',
    'mobing':        '모빙',
    'shake':         '쉐이크모바일',
    'shakemobile':   '쉐이크모바일',
    'sugar':         '슈가모바일',
    'sugarmobile':   '슈가모바일',
    'snowman':       '스노우맨',
    'smartel':       '스마텔',
    '011_smartel':   '스마텔',
    '018_well':      '스마텔',
    'eyes':          '아이즈모바일',
    'eyesmobile':    '아이즈모바일',
    'erl':           '에르엘',
    'amo':           '에이모바일',
    'amobile':       '에이모바일',
    'winners':       '위너스텔',
    'winnerstel':    '위너스텔',
    'iyagi':         '이야기모바일',
    'iyagi_new':     '이야기모바일',
    'egm':           '이지모바일',
    'easy':          '이지모바일',
    'easymobile':    '이지모바일',
    'ins':           '인스모바일',
    'insmobile':     '인스모바일',
    'chance':        '찬스모바일',
    'chancemobile':  '찬스모바일',
    'toss':          '토스모바일',
    'tossmobile':    '토스모바일',
    'tplus':         '티플러스',
    'freet':         '프리티',
    'pretty':        '프리티',
    'findirect':     '핀다이렉트',
    'pin':           '핀다이렉트',
    'hello':         '헬로모바일',
    'logo_gme':      'GME',
    'logo_lguplus_0519': '너겟',
    '%ec%84%b8%eb%a1%9c_1000x500': '한패스모바일',
}


def _extract_provider(img_src):
    if not img_src:
        return '알닷'
    # filename=2025/3/27/asiamobile_logo.png 형태에서 추출
    m = re.search(r'filename=[\d/]+/(.+?)\.png', img_src, re.IGNORECASE)
    if not m:
        return '알닷'
    fname = m.group(1).lower()  # 예) asiamobile_logo, siwol_logo_n2
    # _logo, _n, _n2 등 suffix 제거
    fname = re.sub(r'_logo.*$', '', fname)
    fname = re.sub(r'_n\d*$', '', fname)
    fname = fname.strip()
    # 매핑 테이블 적용
    return PROVIDER_MAP.get(fname, fname)


def _extract_plan_name(raw):
    # 앞의 [혜택명] 제거: '[Npay 최대 2만] 아시아 5G...' → '아시아 5G...'
    cleaned = re.sub(r'^\[.*?\]\s*', '', raw.strip())
    return cleaned.strip() or raw.strip()


def _parse_data(raw):
    raw = raw.strip()
    if not raw:
        return ''
    if '무제한' in raw:
        return raw
    # '+' 주변 공백 정규화
    raw = re.sub(r'\s*\+\s*', ' + ', raw)
    # '월 월 ...' 중복 제거
    raw = re.sub(r'^(월\s+)+', '월 ', raw)
    # '매일'로 시작하면 '월 ' 붙이지 않음 (RS_DATA_SET 형식: '매일 5GB + 5Mbps')
    if raw.startswith('매일'):
        # '매일 XGB + 월 YGB + ZMbps' → '매일 XGB + ZMbps' (중간 월YGB 단기혜택 제거)
        raw = re.sub(r' \+ 월 [\d.]+GB(?= \+ [\d]+Mbps)', '', raw)
        return raw
    # '월 '로 시작하지 않으면 붙이기
    if not raw.startswith('월 '):
        raw = '월 ' + raw
    # '월 XGB + 월 YGB + ZMbps' → '월 XGB + ZMbps' (중간 월YGB 단기혜택 제거)
    raw = re.sub(r' \+ 월 [\d.]+GB(?= \+ [\d]+Mbps)', '', raw)
    # '월 XGB + 월 YGB + ZMbps' 에서 ZMbps 없는 경우도 처리
    # '월 XGB + 월 YGB' → '월 XGB' (마지막 월YGB가 단기혜택)
    raw = re.sub(r' \+ 월 [\d.]+GB$', '', raw)
    return raw


def _parse_price(month_txt, period_txt):
    """
    month_txt  = '월 49,100원'
    period_txt = '24개월 이후 56,800원'  (없으면 '')
    → (final_price, base_price, discount_months)
    """
    m0 = re.search(r'([\d,]+)\s*원', month_txt)
    final_price = int(m0.group(1).replace(',', '')) if m0 else 0
    if not final_price:
        return 0, 0, 0

    base_price  = final_price
    disc_months = 0
    if period_txt:
        m1 = re.search(r'([\d,]+)\s*원', period_txt)
        if m1:
            base_price = int(m1.group(1).replace(',', ''))
        m2 = re.search(r'(\d+)개월', period_txt)
        if m2:
            disc_months = int(m2.group(1))

    return final_price, base_price, disc_months


def _make_plan_id(provider, plan_name, data_raw):
    raw   = provider + '_' + plan_name + '_' + data_raw
    clean = re.sub(r'[^\w가-힣+]', '_', raw)
    return clean[:80]


# ── JS 스니펫 (문자열 상수로 분리) ──────────────────────────────────────────

JS_GET_TOTAL_PAGES = """
() => {
    var lastBtn = document.querySelector('.pagination .last');
    if (lastBtn) { lastBtn.click(); return -1; }
    var onBtn = document.querySelector('.pagination .on button');
    return onBtn ? parseInt(onBtn.innerText.trim()) : 0;
}
"""

JS_GET_CURRENT_MAX = """
() => {
    var btns = document.querySelectorAll('.pagination ul li button');
    var nums = Array.from(btns).map(function(b) { return parseInt(b.innerText.trim()); });
    return Math.max.apply(null, nums);
}
"""

JS_GET_TOTAL_AFTER_LAST = """
() => {
    var onBtn = document.querySelector('.pagination .on button');
    return onBtn ? parseInt(onBtn.innerText.trim()) : 0;
}
"""

JS_CLICK_NEXT = """
() => {
    var btn = document.querySelector('.pagination .next');
    if (btn) { btn.click(); return true; }
    return false;
}
"""

JS_COLLECT = """
() => {
    var cards = document.querySelectorAll('.plan_item');
    return Array.from(cards).map(function(card) {
        var imgEl  = card.querySelector('.partner img');
        var imgSrc = imgEl ? imgEl.src : '';

        var planTitEl = card.querySelector('.plan_tit');
        var planTit = '';
        if (planTitEl) {
            var node = planTitEl.childNodes[0];
            planTit = (node ? node.textContent : planTitEl.innerText || '').trim();
        }

        var subEl = card.querySelector('.plan_tit_sub');
        var dataTxt = '';
        if (subEl) {
            var found = '';
            for (var ni = 0; ni < subEl.childNodes.length; ni++) {
                var nd = subEl.childNodes[ni];
                if (nd.nodeType === 3 && nd.textContent.trim()) {
                    found = nd.textContent.trim(); break;
                }
            }
            dataTxt = found || (subEl.innerText || '').trim();
        }

        var phoneEl    = card.querySelector('.phone');
        var messageEl  = card.querySelector('.message');
        var cellularEl = card.querySelector('.cellular');
        var monthEl    = card.querySelector('.card_price .month');
        var periodEl   = card.querySelector('.card_price .period');

        return {
            imgSrc:    imgSrc,
            planTit:   planTit,
            dataTxt:   dataTxt,
            phone:     phoneEl    ? phoneEl.innerText.replace('통화량','').trim()    : '기본제공',
            message:   messageEl  ? messageEl.innerText.replace('문자량','').trim()  : '기본제공',
            cellular:  cellularEl ? cellularEl.innerText.replace('통신기술','').trim(): 'LTE',
            monthTxt:  monthEl    ? monthEl.innerText.trim()  : '',
            periodTxt: periodEl   ? periodEl.innerText.trim() : ''
        };
    });
}
"""


# ── 스크래퍼 ─────────────────────────────────────────────────────────────────

class AldotScraper(BaseScraper):
    SOURCE = 'aldot'

    async def _scrape_async(self):
        self.progress('🔍 알닷 스크래핑 시작')
        all_plans = []
        seen_ids  = set()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = await browser.new_context(user_agent=COMMON_UA)
            page    = await context.new_page()

            try:
                await page.goto(BASE_URL, timeout=60_000, wait_until='networkidle')
                await page.wait_for_timeout(PAGE_WAIT)

                # 1) last 버튼 클릭 → 마지막 페이지로 이동해 총 페이지 수 파악
                await page.evaluate(JS_GET_TOTAL_PAGES)
                await page.wait_for_timeout(PAGE_WAIT)
                total_pages = await page.evaluate(JS_GET_TOTAL_AFTER_LAST)
                self.progress(f'📄 총 {total_pages}페이지 감지')
                if total_pages == 0:
                    total_pages = 87  # fallback

                # 2) 1페이지로 복귀
                await page.evaluate(
                    "() => { var b = document.querySelector('.pagination .first'); if(b) b.click(); }"
                )
                await page.wait_for_timeout(PAGE_WAIT)

                # 3) 1~total_pages 순회
                for page_num in range(1, total_pages + 1):
                    # 현재 묶음에 page_num 버튼이 없으면 next 클릭
                    for _ in range(20):
                        current_max = await page.evaluate(JS_GET_CURRENT_MAX)
                        current_min = await page.evaluate(
                            "() => { var btns = document.querySelectorAll('.pagination ul li button'); return Math.min.apply(null, Array.from(btns).map(function(b){return parseInt(b.innerText.trim());})); }"
                        )
                        if current_min <= page_num <= current_max:
                            break
                        # 묶음 밖이면 next 클릭
                        moved = await page.evaluate(JS_CLICK_NEXT)
                        if not moved:
                            break
                        await page.wait_for_timeout(1000)

                    # 해당 번호 버튼 클릭
                    clicked = await page.evaluate(
                        """(num) => {
                            var btns = Array.from(document.querySelectorAll('.pagination ul li button'));
                            var target = btns.find(function(b) { return b.innerText.trim() === String(num); });
                            if (target) { target.click(); return true; }
                            return false;
                        }""",
                        page_num
                    )
                    if not clicked:
                        self.progress(f'⚠️ {page_num}p 버튼 클릭 실패 → 스킵')
                        continue
                    await page.wait_for_timeout(PAGE_WAIT)

                    # 카드 수집
                    plans = await self._collect(page, seen_ids)
                    new_count = 0
                    for p in plans:
                        if p['plan_id'] not in seen_ids:
                            all_plans.append(p)
                            seen_ids.add(p['plan_id'])
                            new_count += 1

                    if page_num % 10 == 0 or new_count > 0:
                        self.progress(f'✅ 알닷 {page_num}p | 신규 {new_count}개 | 누적 {len(all_plans)}개')

            except Exception as e:
                self.progress(f'⚠️ 알닷 에러: {e}')
            finally:
                await browser.close()

        self.progress(f'🎉 알닷 완료: {len(all_plans)}개')
        return all_plans, '/tmp/aldot_last.png'

    async def _collect(self, page, seen_ids):
        items = await page.evaluate(JS_COLLECT)
        plans = []
        for item in items:
            p = self._parse_item(item)
            if p and p['plan_id'] not in seen_ids:
                plans.append(p)
        return plans

    def _parse_item(self, item):
        try:
            provider  = _extract_provider(item.get('imgSrc', ''))
            plan_name = _extract_plan_name(item.get('planTit', ''))
            data_raw  = item.get('dataTxt', '').strip()

            if not data_raw or not plan_name:
                return None

            data_label = _parse_data(data_raw)

            # 통화
            phone_txt = item.get('phone', '')
            if '기본제공' in phone_txt or '무제한' in phone_txt:
                voice = '무제한'
            else:
                m = re.search(r'(\d[\d,]*)\s*분', phone_txt)
                voice = m.group(1).replace(',', '') + '분' if m else phone_txt.strip()

            # 문자
            msg_txt = item.get('message', '')
            if '기본제공' in msg_txt or '무제한' in msg_txt:
                sms = '무제한'
            else:
                m = re.search(r'(\d[\d,]*)\s*건', msg_txt)
                sms = m.group(1).replace(',', '') + '건' if m else msg_txt.strip()

            # 망
            cellular = item.get('cellular', 'LTE').strip()
            net_gen  = '5G' if '5G' in cellular.upper() else 'LTE'

            # 가격
            final_price, base_price, disc_months = _parse_price(
                item.get('monthTxt', ''), item.get('periodTxt', '')
            )
            if final_price == 0:
                return None

            plan_id = _make_plan_id(provider, plan_name, data_raw)

            return make_plan(
                source=SOURCE, plan_id=plan_id,
                provider=provider, name=plan_name,
                data=data_label, voice=voice, sms=sms,
                network='LGU+', network_generation=net_gen,
                final_price=final_price, base_price=base_price,
                discount_months=disc_months, subscribers=0,
            )

        except Exception as e:
            print(f'⚠️ 알닷 파싱 실패: {e} | {item}')
            return None