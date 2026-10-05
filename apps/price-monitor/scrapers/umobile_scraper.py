# -*- coding: utf-8 -*-
"""
umobile_scraper.py - U+유모바일 직영몰 요금제 + 사은품 수집

[수정 이력]
- v0.3 (2026-07-08) body 텍스트 파싱 방식으로 전면 재작성
    * CSS 셀렉터 0건 확인 → inner_text('body') 파싱 방식으로 전환
    * 133개 요금제 body에 존재 확인 (2026-07-08 실측)
    * '사은품 혜택' 버튼 전체 클릭 후 재수집으로 추가 사은품 확보
    * 카드 구분: 가격 패턴(월 X원) 2회 연속 등장 = 카드 경계
- v0.2 (2026-07-07) _parse_card 재작성 (가격 누적, 이벤트코드 병합)
- v0.1 (2026-07-07) 최초 작성

[페이지 구조 - 2026-07-08 실측]
body 텍스트 카드 예시:
    LTE (7GB+/통화기본)
    7GB+1Mbps
    통화 기본제공, 문자 기본제공
    🎁매월 이마트24 5천원 혜택 (24개월)
    월 39,800원
    월 15,900원
    사은품 혜택          ← 클릭 시 추가 사은품 노출
"""

import re
from datetime import datetime, timezone

LIST_URL = 'https://www.uplusumobile.com/product/pric/usim/pricList'
PROVIDER = 'U+유모바일'
SITE     = 'umobile_direct'

_RE_PRICE    = re.compile(r'^월\s*([\d,]+)\s*원$')
_RE_DATA     = re.compile(r'\d+GB|\d+MB|무제한')
_RE_VOICE    = re.compile(r'통화')
_RE_SKIP     = re.compile(
    r'^(홈|요금제|유심|eSIM|전체|LTE|5G|필터|추천순|원하는|닫기|검색|로그인|'
    r'MY|이벤트|결합|고객지원|인기|추천|검색어|오늘|🚌|휴대폰|부가|소액|번호|로밍|보험|친구|유심보호).*')
_RE_GIFT_MARKER = re.compile(r'^🎁')


def _parse_price(line: str) -> int:
    m = _RE_PRICE.match(line.strip())
    return int(m.group(1).replace(',', '')) if m else 0


def _split_cards(lines: list) -> list:
    """
    body 텍스트 라인 배열 → 카드별 라인 묶음 리스트.
    '월 X원 / 월 Y원' 패턴(가격 2줄)을 카드 경계로 사용.
    """
    cards, buf = [], []
    price_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _RE_SKIP.match(line):
            continue

        buf.append(line)
        if _RE_PRICE.match(line):
            price_count += 1
            if price_count >= 2:
                cards.append(buf[:])
                buf, price_count = [], 0
        else:
            if price_count == 1 and not _RE_PRICE.match(line) and line != '사은품 혜택':
                # 가격 1줄만 있고 다음이 가격 아닌 경우 → 할인 없는 요금제
                cards.append(buf[:])
                buf, price_count = [], 0

    if buf and price_count:
        cards.append(buf)

    return cards


def _parse_card(lines: list) -> dict | None:
    name, data_raw, voice_sms = '', '', ''
    builtin_gifts, extra_gifts = [], []
    prices = []
    in_gift = False

    for line in lines:
        if _RE_PRICE.match(line):
            prices.append(_parse_price(line))
            in_gift = False
        elif line == '사은품 혜택':
            in_gift = True
        elif _RE_GIFT_MARKER.match(line):
            builtin_gifts.append(line.lstrip('🎁').strip())
        elif in_gift:
            extra_gifts.append(line)
        elif not name:
            name = line
        elif not data_raw and _RE_DATA.search(line):
            data_raw = line
        elif not voice_sms and _RE_VOICE.search(line):
            voice_sms = line

    if not name or not prices:
        return None

    base_price  = prices[0] if len(prices) >= 2 else prices[0]
    final_price = prices[-1]

    return {
        'site':         SITE,
        'provider':     PROVIDER,
        'network':      'LGU+',
        'name':         name,
        'data':         data_raw,
        'voice_sms':    voice_sms,
        'base_price':   base_price,
        'final_price':  final_price,
        'builtin_gift': builtin_gifts,
        'gift_texts':   list(dict.fromkeys(builtin_gifts + extra_gifts)),  # 중복 제거
        'scraped_at':   datetime.now(timezone.utc).isoformat(),
    }


async def scrape_umobile(page) -> list:
    """
    Playwright page 객체를 받아 유모바일 직영 요금제 전체 수집.
    gift_job.py 의 browser/context 재사용 전제.
    """
    await page.goto(LIST_URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(3000)

    # '사은품 혜택' 버튼 전체 클릭 → 추가 사은품 노출
    clicked = await page.evaluate("""
        () => {
            const els = Array.from(document.querySelectorAll('*'))
                .filter(el => el.childElementCount === 0 &&
                              el.innerText && el.innerText.trim() === '사은품 혜택');
            els.forEach(el => el.click());
            return els.length;
        }
    """)
    if clicked:
        await page.wait_for_timeout(800)
    print(f'  사은품 버튼 {clicked}개 클릭')

    body  = await page.inner_text('body')
    lines = body.split('\n')
    raw_cards = _split_cards(lines)
    print(f'  body 파싱: 카드 후보 {len(raw_cards)}개')

    plans = []
    for raw in raw_cards:
        plan = _parse_card(raw)
        if plan:
            plans.append(plan)

    print(f'  유효 요금제 {len(plans)}건 (사은품 {sum(1 for p in plans if p["gift_texts"])}건)')
    return plans