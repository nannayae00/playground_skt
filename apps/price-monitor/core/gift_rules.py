# -*- coding: utf-8 -*-
"""
gift_rules.py - 모요 vs 직영 사은품 비교에서 금액에 넣지 않는 혜택 규칙 (공통)

[추가 2026-10-10] 모요 파서와 직영 스크래퍼(유모바일·KT엠·스카이·헬로)가 혜택을 각자 다른
기준으로 거르고 있어(구독 이용권·할인쿠폰·추천인 혜택 포함 여부가 제각각) 비교 편차가
기준 차이만큼 부풀던 문제. 사용자 결정으로 아래 항목은 양쪽 모두 비교 금액에서 제외:
  - 단말 조건: 자급제 등록, 휴대폰/교체 지원금 쿠폰
  - 친구추천·추천인 입력 혜택
  - 구독·제휴 서비스 이용권: 밀리의서재, 웨이브, 교보 sam, 매거진 구독 등
  - 할인쿠폰·할인 혜택: 프레딧 할인쿠폰, CU 연간 할인 등
현금성 혜택(페이·캐시·상품권·포인트·편의점/커피 교환권), 요금제 자체 혜택, 프로모션 코드,
직영 개통경로 혜택(바로유심 등)은 그대로 포함.
"""
import re

_EXCLUDE_PATTERNS = {
    '단말조건': re.compile(r'자급제|(?:휴대폰|교체|단말|기기)\s*지원금'),
    '추천':     re.compile(r'친구\s*추천|추천인|친구\s*초대'),
    '구독':     re.compile(r'(?<!패)밀리|웨이브|wavve|sam\s*무제한|교보문고\s*sam|이용권|구독|매거진', re.I),
    '할인':     re.compile(r'할인|(?:프레딧|fredit)\s*쿠폰', re.I),   # hy프레딧 쿠폰 = 할인쿠폰 (프레딧 '상품권'은 포함)
}


def compare_exclusion(text: str) -> str:
    """비교 금액에서 빼야 하는 혜택이면 사유('단말조건'/'추천'/'구독'/'할인'), 아니면 ''"""
    t = text or ''
    for reason, pat in _EXCLUDE_PATTERNS.items():
        if pat.search(t):
            # "이벤트코드, 추천인 입력 혜택"처럼 코드 입력으로도 받을 수 있으면 누구나 받는 혜택이라 포함
            if reason == '추천' and '코드' in t:
                continue
            return reason
    return ''


def is_compare_excluded(text: str) -> bool:
    return bool(compare_exclusion(text))


# ── 빽다방 커피 단가 (사용자 결정 2026-10-10) ──
# 사업자가 금액을 적어 둔 경우(예: "100잔 17만원")는 그 금액을 그대로 쓰고,
# 잔수만 있을 때만 1잔 1,500원으로 환산 (모요·직영 공통)
BBAEK_CUP_WON = 1500
_RE_CUPS = re.compile(r'(매월|매달)?\s*(\d+)\s*잔')


def bbaek_value(text: str, months: int = 1):
    """모요 문구 → 빽다방 환산액(잔수×1,500원). 빽다방 문구가 아니거나 잔수가 없거나,
    금액(만원/천원/원)이 적혀 있으면 None (적힌 금액을 쓰도록 일반 파싱에 맡김).
    "100잔 (25개월간 매월 4잔)"처럼 총 잔수가 먼저 나오면 그 값, "매월 4잔"만 있으면 ×개월수."""
    if '빽다방' not in (text or ''):
        return None
    if re.search(r'\d\s*(?:만|천)?\s*원', text):
        return None
    m = _RE_CUPS.search(text)
    if not m:
        return None
    cups = int(m.group(2)) * (months if m.group(1) else 1)
    return cups * BBAEK_CUP_WON


def normalize_bbaek_benefit(b: dict) -> dict:
    """직영 Vision 결과의 빽다방 혜택 재환산.
    유모바일 프롬프트는 잔수만 있을 때 1잔 2,000원(4잔=8,000원)으로 계산하므로 그 경우만 1,500원으로 바꾼다.
    이미지에 총액이 적혀 있던 경우(예: 17만/100잔 → 월 6,800원)는 적힌 금액이라 그대로 둔다."""
    if '빽다방' not in (b.get('name') or ''):
        return b
    amount = int(b.get('amount_won') or 0)
    if amount <= 0:
        return b
    if amount % 2000:
        return b                       # 2,000원 단가로 계산된 값이 아님 = 이미지에 적힌 금액
    cups = amount // 2000
    months = max(int(b.get('months') or 1), 1)
    nb = dict(b)
    nb['amount_won'] = cups * BBAEK_CUP_WON
    nb['total_won'] = nb['amount_won'] * months
    return nb
