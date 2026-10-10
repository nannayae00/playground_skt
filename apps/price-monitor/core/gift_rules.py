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
