# -*- coding: utf-8 -*-
"""
gift_parser.py - 사은품 텍스트 → 금액 환산 파서

[수정 이력]
- v0.3 (2026-07-07) 모요 API 사은품 문구 대응
    * '5,000P' 콤마 포인트 패턴 추가
    * '매월 X 제공' 개월수 미표기 → confidence='partial' (최소 1회분만 계상,
      수동확인 대상으로 리포트)
    * 구독 이용권 단가표 확장 (밀리의서재 월 9,900원, N개월=수량으로 처리)
- v0.2 (2026-07-07) 비금전 단가 보정
    * 유모바일 직영몰 공식 필터 표기 총액 기준 역산 캘리브레이션
      (빽다방 17만/100잔=1700원, 윌야쿠르트 38만/240개=1583.33원)
    * goods 총액 float 계산 후 round 처리
- v0.1 (2026-07-07) 최초 작성
    * 만원/천원/원/만P 금액 패턴 파싱
    * 매월 반복 혜택 x 개월수 → 총액 계산
    * '기본료의 N%' 퍼센트형 혜택 지원 (base_price 필요)
    * 비금전 사은품(데이터GB, 커피 잔수 등) GIFT_UNIT_PRICES 로 추정
"""

import re

# ─────────────────────────────────────────────
# 비금전 사은품 단가표 (필요시 여기만 수정)
# key: 텍스트에 포함되면 매칭
# value: (단위 정규식, 개당 단가[, 'qty_is_months'])
#   'qty_is_months': 수량 패턴이 개월수 자체인 경우 (이용권류, 중복계산 방지)
# ※ 단가는 유모바일 공식 표기 총액 기준 역산 (2026-07-07)
# ─────────────────────────────────────────────
GIFT_UNIT_PRICES = {
    '빽다방':   (r'커피\s*(\d+)\s*잔', 1500),          # [수정 20261010] 잔수만 있을 때 1,500원 (실제로는 위 1-b에서 먼저 처리)
    '야쿠르트': (r'(\d+)\s*개',       380000 / 240),   # 공식 38만원/240개
    '밀리':     (r'(\d+)\s*개월',     9900, 'qty_is_months'),  # 월 구독가
}

# 데이터 GB 환산 단가 (원/GB) - 규제 비교 목적이라 보수적으로 0 처리 가능
DATA_GB_UNIT_PRICE = 0  # 0이면 금액 미산정(unknown 처리)

_RE_MONTHS   = re.compile(r'[(\sXx×](\d+)\s*개월')
# [수정 20260925, 버그] "1만5천원"처럼 만+천이 섞인 표기를 _RE_MAN_WON("N만원")도
# _RE_CHEON("N천원")도 온전히 못 잡고, _RE_CHEON이 뒷부분 "5천원"만 매칭해
# 15,000원짜리 혜택을 5,000원으로 3분의 1 토막내던 문제 발견(네이버페이 매달
# 1만5천원 페이백 등 다수 건 영향). "N만M천원" 조합 패턴을 최우선으로 매칭.
_RE_MAN_CHEON = re.compile(r'(\d+)\s*만\s*(\d+)\s*천\s*원')
_RE_MAN_WON  = re.compile(r'(\d+(?:\.\d+)?)\s*만\s*원')
_RE_CHEON    = re.compile(r'(\d+(?:\.\d+)?)\s*천\s*원')
_RE_WON      = re.compile(r'(\d[\d,]{2,})\s*원')          # 3자리 이상 (5천원 오매칭 방지)
_RE_MAN_P    = re.compile(r'(\d+(?:\.\d+)?)\s*만\s*[Pp]')  # 라이프케어몰 20만P
_RE_NUM_P    = re.compile(r'(\d[\d,]{2,})\s*[Pp](?![a-zA-Z])')  # 5,000P (모요 API)
_RE_PERCENT  = re.compile(r'기본료의\s*(\d+(?:\.\d+)?)\s*%')
_RE_MONTHLY  = re.compile(r'매월|매달')
# [수정 20260925, 버그] "매월/매달"이 금액이 아니라 다른 수량(잔/개/회 등)을 수식하는
# 경우(예: "빽다방 100잔 (25개월간 매월 4잔) (15만원 혜택)", "윌 240개 (24개월간
# 매월 10개) (38만원 혜택)")에도 is_monthly=True로 잘못 판정돼, 이미 총액으로
# 명시된 "15만원"을 개월수(25)만큼 또 곱해서 375만원으로 25배 부풀려지는 문제
# 발견(사장님 지적: "빽다방 아메리카노 몇잔 같은거 제대로 못했던듯"). 처음엔
# "매월/매달 바로 뒤에 금액단위 필수"인 화이트리스트로 고쳤으나, 그러면 "매달
# 프레딧 할인쿠폰 3만원(24개월간 지급)"처럼 매월/매달과 금액 사이에 설명 문구가
# 낀 정상 월반복 케이스까지 놓치는 역효과 발생 - 대신 "매월/매달 바로 뒤에 숫자+
# 비금전 수량단위(잔/개/회 등)"가 오는 경우만 블랙리스트로 제외하는 방식으로 재수정.
_RE_MONTHLY_NONCASH_QTY = re.compile(
    r'(?:매월|매달)\s*\d+\s*(?:잔|개|회|캔|장|병|팩|알)'
)
_RE_DATA_GB  = re.compile(r'데이터\s*(\d+(?:\.\d+)?)\s*GB', re.I)
_RE_UNIT_X_M = re.compile(r'(\d+(?:\.\d+)?)\s*만?\s*원\s*[Xx×]\s*(\d+)\s*개월')
_RE_PAREN_TOTAL = re.compile(r'\((\d+(?:\.\d+)?)\s*만\)')  # '1만원(6만)' 의 총액 병기


def _extract_amount(text: str):
    """텍스트에서 1회분 금액(원) 추출. (amount, kind) 반환"""
    m = _RE_MAN_CHEON.search(text)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2)) * 1000, 'cash'
    m = _RE_MAN_WON.search(text)
    if m:
        return int(float(m.group(1)) * 10000), 'cash'
    m = _RE_MAN_P.search(text)
    if m:
        return int(float(m.group(1)) * 10000), 'point'
    m = _RE_NUM_P.search(text)
    if m:
        return int(m.group(1).replace(',', '')), 'point'
    m = _RE_CHEON.search(text)
    if m:
        return int(float(m.group(1)) * 1000), 'cash'
    m = _RE_WON.search(text)
    if m:
        return int(m.group(1).replace(',', '')), 'cash'
    return None, None


def _extract_months(text: str) -> int:
    m = _RE_MONTHS.search(text)
    return int(m.group(1)) if m else 1


def parse_gift(text: str, base_price: int = 0) -> dict:
    """
    사은품 텍스트 1건 → 구조화 dict

    Returns:
        {
            'raw':        원문,
            'kind':       'cash'|'point'|'percent'|'goods'|'data'|'unknown',
            'unit_value': 1회분 금액(원),
            'months':     반복 개월수,
            'total_value': 총 환산액(원),
            'confidence': 'exact'|'estimated'|'unknown',
        }
    """
    text = ' '.join(text.split())
    months = _extract_months(text)
    result = {'raw': text, 'months': months}

    # 1) 퍼센트형 (기본료의 10% 적립)
    m = _RE_PERCENT.search(text)
    if m:
        pct = float(m.group(1)) / 100
        unit = int(base_price * pct) if base_price else 0
        result.update(kind='percent', unit_value=unit,
                      total_value=unit * months,
                      confidence='exact' if base_price else 'unknown')
        return result

    # 1-b) 빽다방 커피 - 금액이 적혀 있으면 그 금액(아래 일반 파싱), 잔수만 있으면 잔수 × 1,500원
    #      [수정 20261010] 사용자 결정 - 직영과 같은 규칙 (core.gift_rules.BBAEK_CUP_WON)
    from core.gift_rules import bbaek_value
    bv = bbaek_value(text, months)
    if bv is not None:
        result.update(kind='goods', unit_value=bv, months=1, total_value=bv, confidence='estimated')
        return result

    # 2-a) '1만원X15개월' 패턴 → 단가×개월 직접 계산 (최우선)
    m = _RE_UNIT_X_M.search(text)
    if m:
        unit = int(float(m.group(1)) * (10000 if '만' in m.group(0) else 1))
        mo = int(m.group(2))
        result.update(kind='cash', unit_value=unit, months=mo,
                      total_value=unit * mo, confidence='exact')
        return result

    # 2-b) 금액 직접 표기 (만원/천원/원/만P)
    amount, kind = _extract_amount(text)
    if amount:
        # '매달 1만원(6만)' 처럼 괄호 총액 병기 시 → 총액 우선
        pt = _RE_PAREN_TOTAL.search(text)
        if pt:
            total = int(float(pt.group(1)) * 10000)
            result.update(kind=kind, unit_value=amount,
                          months=max(1, round(total / amount)) if amount else months,
                          total_value=total, confidence='exact')
            return result

        # '매달/매월'이 금액보다 앞에 있을 때만 월반복
        # ex) '매달 1만원(12만)' → 월반복 O
        #     '12만원 혜택(매월 5천원) (24개월)' → 12만원이 총액, 월반복 X
        #     '매달 프레딧 할인쿠폰 3만원(24개월간 지급)' → 사이에 설명 있어도 월반복 O
        # [수정 20260925] '매월'이 금액이 아닌 다른 수량(예: '매월 4잔', '매월 10개')을
        # 수식하는 경우까지 월반복으로 오판하던 버그 - _RE_MONTHLY_NONCASH_QTY에
        # 해당하면(매월/매달 바로 뒤에 비금전 수량단위) 월반복 판정에서 제외.
        monthly_m = _RE_MONTHLY.search(text)
        amount_m  = _RE_MAN_CHEON.search(text) or _RE_MAN_WON.search(text) or _RE_NUM_P.search(text) or _RE_CHEON.search(text) or _RE_WON.search(text)
        is_monthly = (bool(monthly_m)
                      and (not amount_m or monthly_m.start() < amount_m.start())
                      and not _RE_MONTHLY_NONCASH_QTY.search(text))
        has_months = bool(_RE_MONTHS.search(text))
        if is_monthly and not has_months:
            # '매월 5,000P 제공' 개월수 미표기 → 최소 1회분만 계상, 수동확인 대상
            result.update(kind=kind, unit_value=amount,
                          total_value=amount, confidence='partial')
            return result
        if is_monthly:
            # 매달/매월이 금액 앞 → 월반복
            total = amount * months
            conf = 'exact'
        else:
            # 금액이 앞 = 이미 총액 (12만원 혜택(매월 5천원) 같은 케이스)
            total, conf = amount, 'exact'
        result.update(kind=kind, unit_value=amount,
                      total_value=total, confidence=conf)
        return result

    # 3) 비금전 - 단가표 매칭 (빽다방 커피 4잔, 밀리 3개월 이용권 등)
    for keyword, entry in GIFT_UNIT_PRICES.items():
        if keyword in text:
            pattern, unit_price = entry[0], entry[1]
            qty_is_months = len(entry) > 2 and entry[2] == 'qty_is_months'
            m = re.search(pattern, text)
            qty = int(m.group(1)) if m else 1
            unit = qty * unit_price
            eff_months = 1 if qty_is_months else months
            result.update(kind='goods', unit_value=round(unit),
                          total_value=round(unit * eff_months),
                          months=qty if qty_is_months else months,
                          confidence='estimated')
            return result

    # 4) 데이터 증정
    m = _RE_DATA_GB.search(text)
    if m:
        gb = float(m.group(1))
        unit = int(gb * DATA_GB_UNIT_PRICE)
        result.update(kind='data', unit_value=unit, total_value=unit * months,
                      confidence='estimated' if DATA_GB_UNIT_PRICE else 'unknown')
        return result

    # 5) 파싱 불가
    result.update(kind='unknown', unit_value=0, total_value=0,
                  confidence='unknown')
    return result


def parse_gifts(texts: list, base_price: int = 0) -> dict:
    """
    사은품 텍스트 목록 → 총액 요약

    Returns:
        {
            'gifts': [parse_gift 결과들],
            'total_value': 금액 환산 총합(원),
            'exact_value': confidence=exact 만의 총합,
            'unknown_count': 환산 실패 건수,
        }
    """
    flat = []
    for t in texts:
        if isinstance(t, list): flat.extend(t)
        elif t: flat.append(t)
    gifts = [parse_gift(t, base_price) for t in flat if t and str(t).strip()]
    return {
        'gifts': gifts,
        'total_value': sum(g['total_value'] for g in gifts),
        'exact_value': sum(g['total_value'] for g in gifts
                           if g['confidence'] == 'exact'),
        'unknown_count': sum(1 for g in gifts
                             if g['confidence'] in ('unknown', 'partial')),
    }