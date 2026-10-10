# -*- coding: utf-8 -*-
"""
gift_comparator.py - 사이트간 동일 데이터 스펙 요금제 사은품 총액 비교

[수정 이력]
- v0.22 (2026-08-28) _gift_breakdown_lines를 core.gift_parser.parse_gift 기반으로 교체
    * 그동안 항목별 금액을 정규식으로 추측(첫/마지막 'N만원' 매칭)하던 걸 실제
      core.gift_parser.parse_gift()의 total_value로 교체 - build_group_index()가
      총액 계산에 쓰는 것과 동일한 로직이라 '◎ 총 X' 줄과 항목별 합이 항상 일치함.
      (기존 정규식 방식은 '매달 1만원 페이백 (6개월)'처럼 총액이 텍스트에 명시적으로
      없는 케이스를 못 잡았는데, parse_gift는 '매달/매월 여부 + 개월수'를 보고
      단가×개월로 정확히 계산함)
    * 4개 넘는 프로모션 항목은 화면엔 4개까지만 보여주되, 5번째부터는
      ' + 외 N건 (X만원)' 요약 줄로 나머지 합계를 표시 - 이전엔 그냥 안 보여서
      표시된 항목 합이 총액보다 작아 보이는 문제가 있었음
    * 더 이상 안 쓰는 _RE_WON_ANY/_RE_WON_TRAILING_PAREN 정규식 상수 제거
- v0.21 (2026-08-28) 헤더 요약 줄 순서/포맷 재조정
    * '⚠️ 요금제 Gap' 경고를 편차/단계 줄보다 위(사업자·금액 요약 줄 바로 다음)로 이동
    * 문구를 '실제 데이터량 차이 큼: ...(참고용)' → '요금제 Gap : 모요 XGB vs 직영 YGB'로 축약
    * '🔴 편차...위반'과 '(참고: 최대 벌점...)'을 두 줄 → 한 줄로 병합
- v0.20 (2026-08-28) 같은 tier 내 실제 GB 차이 경고 추가
    * 채널 dict에 'gb' 필드 추가 (_moyo_group_to_channel: data_key에서 파싱,
      _direct_plan_to_channel: compare_kcup에서 계산한 _direct_plan_gb 결과를 plan['_gb']로
      전달받음) - tier 버킷(예: '50~99GB')이 넓어서 그 안에서 모요/직영이 각자 사은품
      최고가 요금제를 뽑다 보면 실제 데이터량이 크게 다른 요금제끼리 비교되는 문제 대응
    * GB_DIFF_WARN_THRESHOLD(5GB) 이상 차이나면 '⚠️ 실제 데이터량 차이 큼' 경고 문구 추가.
      전 절대값(5GB)으로 했다가 100GB↔110GB(10%)는 잡히고 1GB↔3GB(200%)는 안 잡히는
      역효과가 있어서 비율(30%, GB_DIFF_WARN_RATIO=1.3)로 최종 확정
    * 비교 자체는 그대로 유지, 경고만 추가하는 쪽으로 결정(tier 재분류나 제외는 안 함)
- v0.19 (2026-08-28) 위반 요약을 상단으로 이동 + 신호등 색 + 불필요 문구 삭제
    * '→ 편차...위반' + '(참고: 벌점...)' 줄을 메시지 맨 아래 → 헤더 바로 아래(상세 내용
      보기 전에 결론부터)로 이동. 'ㅇ 사업자 (구간)' 줄과 금액비교 줄도 한 줄로 합침.
    * 단계별 신호등 이모지 추가: 1단계🟢 2단계🟡 3단계🟠 4단계🔴 (_STAGE_EMOJI)
    * '— 확정 벌점은 소명 결과에 따라 달라짐' 문구 삭제 - 모든 단계에 공통으로 붙는
      일반 안내라 매번 반복할 필요 없다는 피드백 반영
- v0.18 (2026-08-28) 특이사항 메시지 포맷 재조정
    * '[모요] 요금제명 : 가격' 한 줄 → '[모요] 스펙' + '◎  요금제명 : 총 X' 두 줄로 분리
    * 프로모션 항목에 번호 매기기(' 1) + 금액 : 텍스트') 추가, '프로모션 총' 헤더 줄은
      제거(◎ 줄에 총액이 이미 있어 중복이라 삭제)
    * 이벤트 링크를 채널별(모요/직영)에서 각각 표시하던 것 → 전체에서 1번만(직영 우선,
      없으면 모요) 두 채널 블록이 끝난 뒤 한 번만 표시
- v0.17 (2026-08-28) 특이사항 메시지 추가 수정
    * 헤더 순번을 "(N)" → "(N/{TOTAL})"로 변경. 전체 건수는 이 함수 하나만으로는 알 수
      없어(다른 사업자 배치와 합쳐진 후 정해짐) '{TOTAL}' 플레이스홀더를 남겨두고,
      호출부(gift_job.py)에서 두 사업자 결과를 다 합친 뒤 문자열 치환으로 채워 넣음.
    * [모요]/[직영] 각 채널에 요금제 스펙 요약 줄 추가(_spec_line) - plan_name 텍스트에서
      GB/통화 정보를 정규식으로 추출. 통화 정보가 텍스트에 없으면 지어내지 않고 생략.
    * 프로모션 한 줄 합산 표시를 항목별 줄바꿈+금액 표시로 변경(_gift_breakdown_lines) -
      '프로모션: A + B + C' → '프로모션 총 X만원 :' 아래 항목별로 '금액 : 텍스트' 한 줄씩.
      각 항목 금액은 텍스트 안 마지막 'N만원' 매칭 사용(완벽히 정확하진 않을 수 있음).
- v0.16 (2026-08-28) 특이사항 메시지 포맷 조정 (실사용 피드백 반영)
    * 헤더에 실행 시각 + 배치 내 순번 추가: "8/28 특이사항" → "8/28 11시 특이사항 (1)"
      (run_time/index 파라미터, compare_kcup의 run_time/start_index로 연결)
    * "ㅇ 사업자 (구간)" 바로 아래 금액 요약 한 줄 추가: "-26만원(모요) vs 6만원(직영)"
    * [모요]/[직영] 채널별 태그를 provider별 라벨("KT엠모바일 직영" 등) 대신 고정 문구
      "모요"/"직영"으로 단순화 - 어차피 바로 위 "ㅇ 사업자" 줄에 사업자명이 이미 있어서 중복이었음
- v0.15 (2026-08-28) format_moyo_vs_direct()에 direct_label 파라미터 추가
    * 제목이 "유모바일직영"으로 고정돼 있던 걸 파라미터화 - KT엠모바일 등 다른 provider로
      호출해도 제목이 맞게 나오도록 함. gift_job.py에서 모요 vs 유모바일 vs 엠모바일
      3자 통합 메시지(format_moyo_vs_direct_multi) 대신, 이 함수를 사업자별로 두 번
      호출해 메시지를 분리하기 위한 선행 작업.
- v0.14 (2026-08-27) compare_kcup() 기본값을 상세 포맷(compact=False)으로 되돌림
    * 건별로 따로 발송하는 것을 전제로 하면 상세 포맷(요금제명/프로모션/링크 포함)이
      한 메시지가 너무 길어질 걱정이 없어 이 방식으로 최종 확정. compact=True 옵션은
      필요 시(예: 요약 다이제스트) 그대로 사용 가능.
- v0.13 (2026-08-27) format_kcup_violation()에 compact 모드 추가
    * compact=True: 텔레그램 발송용 축약판(3~4줄) - 단계/편차/금액/링크만, 프로모션
      세부내용은 생략. 기존 상세 포맷(compact=False)은 로그/검증용으로 유지.
    * compare_kcup()도 compact 파라미터 전달 가능 (기본값 True로 변경 - 실제 발송을
      염두에 둔 기본 동작이 축약판이 되도록)
- v0.12 (2026-08-27) 직영 plan tier 분류 기준 변경 (base_gb/total_gb → 요금제명 우선)
    * 실데이터 검증 중 U+유모바일 '이즈' 시리즈에서 base_gb(11)/total_gb(91)/요금제명(71GB+)
      세 값이 서로 어긋나 tier가 잘못 잡히는 사례 발견(기본+랜덤 데이터 혼합 상품).
    * _direct_plan_gb() 추가: 모요 쪽(_data_key)과 동일하게 요금제명에서 GB 숫자를
      정규식(_RE_DATA_GB)으로 우선 추출, 없을 때만 base_gb→total_gb로 폴백.
      양쪽 다 "광고 문구 기준 GB"로 통일해 tier 불일치 가능성을 줄임.
- v0.11 (2026-08-27) 실데이터 테스트에서 발견된 버그 2건 수정
    * compare_kcup(): 직영 plan의 total_won에 PLAN_VAL_CAP(60만원) 미적용 → ktm/umobile
      스크래퍼 자체 캡(format_telegram_message)과 다르게 원본(캡 전) 값을 그대로 비교/표시
      하고 있었음. min(total_won, PLAN_VAL_CAP)으로 통일.
    * _direct_plan_to_channel / _moyo_group_to_channel: plan_name/price 등 필드가 dict에
      키는 있지만 값이 None으로 저장된 경우 .get(key, default)가 default를 안 주고 None을
      그대로 반환해 메시지에 "None" 문자열이 찍히던 버그 → 전부 `or` 가드로 교체.
- v0.10 (2026-08-27) compare_kcup() 오케스트레이션 함수 추가
    * moyo_plans + direct_posts(scrape_with_cache 결과) → tier별 자동 매칭 → 편차 판정
      → min_stage(기본 2단계) 이상만 format_kcup_violation 메시지로 반환
    * _moyo_group_to_channel(): _moyo_plan_to_channel을 대체 - build_group_index()가 만든
      그룹 dict(plan_name/total_value 이미 계산됨)를 바로 받도록 정리. 모요는 이벤트 링크가
      불필요하므로 event_* 필드는 항상 빈 값으로 고정.
- v0.9 (2026-08-27) format_kcup_violation 입력 어댑터 추가
    * _direct_plan_to_channel(): KT엠모바일/U+유모바일 스크래퍼의 plan dict
      (plan_name/total_won/benefits/_event_url/_event_title/_date_start/_date_end)를
      format_kcup_violation 채널 dict로 정규화. benefits(list[dict]) → 사람이 읽는
      프로모션 텍스트 리스트로 변환(_benefits_to_gift_texts).
    * _moyo_plan_to_channel(): 모요 plan dict(name/gift_texts) → 채널 dict로 정규화.
      모요는 이벤트 게시글 개념이 없어 event_url/title/period는 항상 빈 값
      (format_kcup_violation의 _event_link_line이 자동으로 "링크 없음"으로 표시).
      gift_val은 build_group_index()로 산출한 total_value를 그대로 넘겨야 함
      (원시 plan dict엔 금액 필드가 없고 gift_texts만 있음).
    * _short_date(): 'YYYY-MM-DD' → 'M/D' (ktm/umobile 스크래퍼의 동명 함수와 동일 규칙)
- v0.8 (2026-08-27) format_kcup_violation() 추가
    * K CUP 경품 편차 기준(5/10/20만원) 위반 단계 판정 + 요금제명/프로모션 세부내용/
      이벤트 링크(제목+기간, Telegram <a href> 링크)를 포함한 채널 2자 비교 메시지
    * KCUP_TIERS: (임계값, 단계라벨, 해당 단계 최대 참고 벌점) 튜플 리스트
    * _kcup_tier(diff): 편차 금액 → (단계, 최대참고벌점) 판정
    * 입력 채널 dict는 plan_name/price/gift_texts 외 event_title/event_url/event_period
      필드 필요 - 현재 스크래퍼 산출물에 이 필드가 없다면 먼저 채워야 함(하단 주석 참고)
- v0.7 (2026-08-25) format_moyo_vs_direct_multi() 추가
    * 모요 vs 유모바일직영 vs KT엠모바일직영 3자 비교 메시지 (구간별 모요/유모/엠모 3열 + GAP)
    * 기존 format_moyo_vs_direct()(2자 비교)는 그대로 유지 - 다른 provider 조합 재사용 대비
    * v0.7.1: 텔레그램 모바일에서 <code> 표가 줄바꿈으로 깨지는 문제 → "구간+값" 줄과
      "GAP" 줄을 분리하는 포맷으로 변경. GAP 표시 기준을 10만원 이상 차이로 상향
      (gap_threshold 파라미터, 기본 100000)
    * v0.7.2: <code> 블록 + 정렬(ljust)로 표 형태 재구성 (price-monitor "현재 최저가" 표와 동일 스타일).
      행마다 GAP 텍스트 반복 대신, 모요 대비 10만원 이상 차이나는 값에 바로 '*' 붙이고
      맨 아래 범례 한 줄만 표시 (예: "* 다른 값과 10만원 이상 차이")
- v0.6 (2026-07-27) 비교 메시지 <code> 테이블 포맷으로 변경
- v0.5 (2026-07-15) 전일 대비 + 볼드 + 직영 비교 추가
    * format_summary_report: 전일 대비 ▲▼━ 표기, 구간명/금액 볼드
    * compute_tier_max(): 플랜 리스트 → 구간별 최대값 dict
    * format_moyo_vs_direct(): 모요 vs 유모바일직영 구간별 비교 메시지
- v0.4 (2026-07-08) 상세 출력 + 만원 표기 + 이상값 방어
- v0.3 (2026-07-08) 데이터스펙 그룹 비교 + min/max 범위
- v0.2 (2026-07-08) builtin_gift 리스트 타입 대응
- v0.1 (2026-07-07) 최초 작성
"""

import re
import unicodedata
from core.gift_parser import parse_gifts

DIFF_THRESHOLD  = 10000
GIFT_VAL_CAP    = 500000

# K CUP 경품 편차 기준표 (하한 미만, 단계라벨, 해당 단계 최대 참고 벌점)
# ※ 실제 벌점은 소명 불인용 시에만 확정 - 여기서는 "위반 시 최대 가능 벌점"만 참고 표시
KCUP_TIERS = [
    (50000,  '1단계', 0),
    (100000, '2단계', 2),   # 소명불인용1점 + 자율조치미이행1점
    (200000, '3단계', 3),
    (None,   '4단계', 3),   # 최초 발생 기준 3점, 2개월 내 2회 위반 시 4점(별도 로직 필요)
]

_RE_DATA_GB = re.compile(r'(\d+(?:\.\d+)?)\s*GB', re.I)

TIER_ORDER = ['5GB 이하', '5~9GB', '10~15GB', '16~49GB', '50~99GB', '100GB 이상']


# ── 포맷 유틸 ─────────────────────────────────────────────────────────────────

def _man(v: int) -> str:
    if v == 0: return '0원'
    m = v / 10000
    return f'{m:.0f}만원' if m == int(m) else f'{m:.1f}만원'


_RE_SPEC_GB    = re.compile(r'(\d+(?:\.\d+)?)\s*GB', re.IGNORECASE)
_RE_SPEC_VOICE = re.compile(r'(통화[^,/()]*|음성[^,/()]*)')


def _spec_line(plan_name: str) -> str:
    """
    요금제명에서 데이터/통화 스펙만 뽑아 'N GB/통화OOO 요금제' 형태로 정리.
    plan_name 텍스트에 실제로 있는 내용만 사용 - 통화 정보가 텍스트에 없으면 지어내지 않고
    GB만 표시하거나(통화 정보 없음) 아예 빈 문자열 반환(GB도 없을 때).
    """
    name = plan_name or ''
    gb_m    = _RE_SPEC_GB.search(name)
    voice_m = _RE_SPEC_VOICE.search(name)
    parts = []
    if gb_m:
        parts.append(f'{gb_m.group(1)}GB')
    if voice_m:
        parts.append(voice_m.group(1).strip())
    if not parts:
        return ''
    return '/'.join(parts) + ' 요금제'


def _gift_breakdown_lines(gift_texts: list) -> list:
    """
    프로모션 항목을 번호 매겨 한 줄씩 분해 ' N) + 금액 : 항목텍스트'.
    core.gift_parser.parse_gift()로 각 항목의 정확한 total_value를 그대로 사용
    (build_group_index()가 총액 합산에 쓰는 것과 동일한 로직이라, 항목별 합과
    '◎ 요금제명 : 총 X' 줄의 총액이 서로 어긋나지 않음 - 이전엔 정규식 추측이라
    '매달 1만원 페이백 (6개월)'처럼 단가만 있고 총액이 텍스트에 없는 경우 틀렸었음).
    4개 넘는 항목은 화면에 다 못 띄우는 대신 '+ 외 N건 (X만원)' 요약 줄로 합계를 살림
    (이전엔 5번째부터 그냥 안 보여서 표시된 항목 합 ≠ 총액인 것처럼 보이는 문제가 있었음).
    """
    from core.gift_parser import parse_gift

    texts = [t for t in (gift_texts or []) if isinstance(t, str)]
    if not texts:
        return []
    shown, rest = texts[:4], texts[4:]
    lines = []
    for i, t in enumerate(shown, start=1):
        amt = _man(parse_gift(t)['total_value'])
        lines.append(f' {i}) + {amt} : {t}')
    if rest:
        rest_total = sum(parse_gift(t)['total_value'] for t in rest)
        lines.append(f' + 외 {len(rest)}건 ({_man(rest_total)})')
    return lines


def format_range(min_val: int, max_val: int) -> str:
    if min_val == max_val:
        return _man(max_val)
    return f'최대 {_man(max_val)} ({_man(min_val)}~{_man(max_val)})'


def _diff_arrow(curr: int, prev: int) -> str:
    if prev == 0 or curr == prev: return '━'
    diff = curr - prev
    sign = '▲' if diff > 0 else '▼'
    return f'{sign}{_man(abs(diff))}'


# ── 키 추출 ──────────────────────────────────────────────────────────────────

def _data_key(plan: dict) -> str:
    api_gb = float(plan.get('data_gb') or 0)
    name_m = _RE_DATA_GB.search(plan.get('name', ''))
    if name_m:
        name_gb = float(name_m.group(1))
        v = name_gb if api_gb and name_gb < api_gb else (api_gb or name_gb)
    elif api_gb:
        v = api_gb
    else:
        m = _RE_DATA_GB.search(plan.get('data', ''))
        v = float(m.group(1)) if m else 0
    if not v: return 'unknown'
    return f'{int(v) if v == int(v) else v}gb'


def _voice_key(plan: dict) -> str:
    name = plan.get('name', '') + plan.get('voice_sms', '') + plan.get('voice', '')
    if '무제한' in name: return '무제한'
    if '기본' in name:   return '기본'
    if '300분' in name:  return '300분'
    if '200분' in name:  return '200분'
    if '100분' in name:  return '100분'
    m = re.search(r'(\d+)분', name)
    if m:
        mins = int(m.group(1))
        return f'{mins}분' if mins <= 600 else '기타'
    return '기타'


def _gift_summary(plan: dict) -> dict:
    texts = []
    for t in plan.get('gift_texts') or []:
        if isinstance(t, list): texts.extend(t)
        elif t: texts.append(t)
    builtin = plan.get('builtin_gift')
    if builtin:
        if isinstance(builtin, list): texts.extend(builtin)
        elif isinstance(builtin, str): texts.append(builtin)
    texts = list(dict.fromkeys(texts))
    return parse_gifts(texts, base_price=plan.get('base_price', 0))


def _data_tier(data_key: str) -> tuple:
    try:
        gb = float(data_key.replace('gb', ''))
    except ValueError:
        return (99, '기타')
    if gb <= 5:   return (0, '5GB 이하')
    if gb <= 9:   return (1, '5~9GB')
    if gb <= 15:  return (2, '10~15GB')
    if gb <= 49:  return (3, '16~49GB')
    if gb <= 99:  return (4, '50~99GB')
    return (5, '100GB 이상')


# ── 그룹 인덱스 ───────────────────────────────────────────────────────────────

def build_group_index(plans: list) -> dict:
    groups = {}
    for p in plans:
        key     = (p['provider'], _data_key(p), _voice_key(p))
        summary = _gift_summary(p)
        val     = summary['total_value']
        if val > GIFT_VAL_CAP: val = 0
        gift_texts = [t for t in (p.get('gift_texts') or []) if isinstance(t, str)]
        if key not in groups:
            groups[key] = {
                'provider':      p['provider'],
                'data_key':      _data_key(p),
                'voice_key':     _voice_key(p),
                'plan_name':     p['name'],
                'final_price':   p.get('final_price', 0),
                'gift_texts':    gift_texts,
                'total_value':   val,
                'min_value':     val,
                'max_value':     val,
                'plan_count':    1,
                'unknown_count': summary['unknown_count'],
            }
        else:
            g = groups[key]
            g['plan_count']    += 1
            g['min_value']      = min(g['min_value'], val)
            g['max_value']      = max(g['max_value'], val)
            g['unknown_count'] += summary['unknown_count']
            if val > g['total_value']:
                g['total_value'] = val
                g['plan_name']   = p['name']
                g['final_price'] = p.get('final_price', 0)
                g['gift_texts']  = gift_texts
    return groups


def compute_tier_max(plans: list, provider: str = None) -> dict:
    """
    플랜 리스트 → {tier_label: max_val} dict
    Firestore 저장 및 비교에 사용
    """
    tier_max = {}
    for p in plans:
        if provider and p.get('provider') != provider:
            continue
        summary = _gift_summary(p)
        val = summary['total_value']
        if val > GIFT_VAL_CAP: val = 0
        _, tier_label = _data_tier(_data_key(p))
        if tier_label == '기타': continue
        if val > tier_max.get(tier_label, 0):
            tier_max[tier_label] = val
    return tier_max


def _data_key_gb(data_key: str) -> float:
    """'5gb' → 5.0, 정렬/표시용. 'unknown'이면 큰 값을 반환해 맨 뒤로 보냄."""
    try:
        return float(data_key.replace('gb', ''))
    except ValueError:
        return float('inf')


def _data_key_label(data_key: str) -> str:
    """'5gb' → '5GB', 'unknown' → '기타'."""
    if data_key == 'unknown':
        return '기타'
    gb = _data_key_gb(data_key)
    gb_str = str(int(gb)) if gb == int(gb) else str(gb)
    return f'{gb_str}GB'


def compute_datakey_max(plans: list, provider: str = None) -> dict:
    """
    [추가 20260925] format_summary_report()를 구간(TIER_ORDER) 대신 데이터제공량별로
    바꿔달라는 요청 반영 - 플랜 리스트 → {data_key: max_val} dict (구간 없이 정확한
    GB 단위). compute_tier_max와 동일한 용도(Firestore 저장/전일 대비)이나 구간으로
    묶지 않고 실제 데이터량(5gb/7gb/11gb 등) 그대로 키로 사용.
    """
    dk_max = {}
    for p in plans:
        if provider and p.get('provider') != provider:
            continue
        summary = _gift_summary(p)
        val = summary['total_value']
        if val > GIFT_VAL_CAP: val = 0
        dk = _data_key(p)
        if dk == 'unknown': continue
        if val > dk_max.get(dk, 0):
            dk_max[dk] = val
    return dk_max


# ── 비교 ─────────────────────────────────────────────────────────────────────

def compare_sites(site_a: list, site_b: list,
                  label_a: str = 'moyo',
                  label_b: str = 'umobile_direct') -> dict:
    idx_a  = build_group_index(site_a)
    idx_b  = build_group_index(site_b)
    common = set(idx_a) & set(idx_b)
    issues = []
    for key in sorted(common):
        a, b    = idx_a[key], idx_b[key]
        val_a   = a['total_value']
        val_b   = b['total_value']
        diff    = abs(val_a - val_b)
        unknown = a['unknown_count'] + b['unknown_count']
        if diff >= DIFF_THRESHOLD or unknown:
            issues.append({
                'provider':           key[0],
                'data_key':           key[1],
                'voice_key':          key[2],
                f'{label_a}_plan':    a['plan_name'],
                f'{label_b}_plan':    b['plan_name'],
                f'{label_a}_price':   a['final_price'],
                f'{label_b}_price':   b['final_price'],
                f'{label_a}_total':   val_a,
                f'{label_a}_range':   format_range(a['min_value'], a['max_value']),
                f'{label_a}_count':   a['plan_count'],
                f'{label_a}_gifts':   a['gift_texts'],
                f'{label_b}_total':   val_b,
                f'{label_b}_range':   format_range(b['min_value'], b['max_value']),
                f'{label_b}_count':   b['plan_count'],
                f'{label_b}_gifts':   b['gift_texts'],
                'diff':               diff,
                'unknown_count':      unknown,
                'over_threshold':     diff >= DIFF_THRESHOLD,
            })
    return {
        'matched': len(common),
        'issues':  sorted(issues, key=lambda x: -x['diff']),
        'only_a':  sorted(set(idx_a) - common),
        'only_b':  sorted(set(idx_b) - common),
    }


def format_telegram(result: dict,
                    label_a: str = '모요',
                    label_b: str = '유모바일') -> str:
    la, lb = 'moyo', 'umobile_direct'
    lines = [f'🎁 <b>사은품 센싱 리포트</b>',
             f'매칭 그룹: {result["matched"]}건 / 이슈: {len(result["issues"])}건', '']
    hot = [i for i in result['issues'] if i['over_threshold']]
    for i in hot[:10]:
        a_range = i.get(f'{la}_range', '0원')
        b_range = i.get(f'{lb}_range', '0원')
        a_gifts = i.get(f'{la}_gifts', [])
        b_gifts = i.get(f'{lb}_gifts', [])
        a_gift_lines = '\n'.join(f'    · {g}' for g in a_gifts) if a_gifts else '    · 없음'
        b_gift_lines = '\n'.join(f'    · {g}' for g in b_gifts) if b_gifts else '    · 없음'
        lines.append(f'⚠️{i["data_key"].upper()} / {i["voice_key"]} : GAP {_man(i["diff"])}')
        lines.append(f'  [{label_a}] {i.get(f"{la}_count",1)}개 {a_range}')
        lines.append(f'  · {i.get(f"{la}_plan","")} | 월 {i.get(f"{la}_price",0):,}원')
        lines.append(f'  프로모션:'); lines.append(a_gift_lines)
        lines.append(f'  [{label_b}] {i.get(f"{lb}_count",1)}개 {b_range}')
        lines.append(f'  · {i.get(f"{lb}_plan","")} | 월 {i.get(f"{lb}_price",0):,}원')
        lines.append(f'  프로모션:'); lines.append(b_gift_lines)
        lines.append('')
    unknown_only = [i for i in result['issues'] if not i['over_threshold']]
    if unknown_only:
        lines.append(f'❓ 환산 불가 포함: {len(unknown_only)}건 (수동 확인 필요)')
    if not result['issues']:
        lines.append('✅ 임계값 초과 차이 없음')
    return '\n'.join(lines)


# ── 모요 단독 리포트 ─────────────────────────────────────────────────────────

def _abbrev_gift(text: str, base_price: int = 0) -> str:
    from core.gift_parser import parse_gift
    g = parse_gift(text, base_price)
    BRANDS = ['이마트24', 'hy', '네이버페이', 'N페이', 'GS25', '올리브영',
              '다이소', '빽다방', '교보문고', '라이프케어몰', '밀리',
              '쿠팡이츠', '야쿠르트', '윌', '티머니', '교통비', '다솜케어',
              '신세계', '프레딧', '모바일티머니', 'S-머니']
    brand = next((b for b in BRANDS if b in text), None)
    if not brand:
        brand = re.split(r'[(（7/]', text.lstrip('매달매월').strip())[0].strip()[:12]
    unit, months, total = g['unit_value'], g['months'], g['total_value']
    def _fmt(v):
        if v == 0: return '0원'
        if v % 10000 == 0: return f'{v//10000}만원'
        if v % 1000 == 0:  return f'{v//1000}천원'
        return _man(v)
    if months > 1 and unit > 0 and unit != total:
        return f'{brand} {_fmt(unit)}×{months}개월({_man(total)})'
    elif total > 0:
        return f'{brand} {_man(total)}'
    return f'{brand}(금액미상)'


def format_moyo_report(plans: list,
                       provider: str = 'U+유모바일',
                       gap_threshold: int = 50000) -> str:
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today    = datetime.now(KST).strftime('%Y-%m-%d')
    time_str = datetime.now(KST).strftime('%H:%M')

    groups = {}
    for p in plans:
        if p['provider'] != provider: continue
        dk, vk = _data_key(p), _voice_key(p)
        key = (dk, vk)
        summary = _gift_summary(p)
        val = summary['total_value']
        if val > GIFT_VAL_CAP: val = 0
        gift_texts = [t for t in (p.get('gift_texts') or []) if isinstance(t, str)]
        if key not in groups:
            groups[key] = {'data_key': dk, 'voice_key': vk, 'count': 1,
                           'min_val': val, 'max_val': val, 'best_val': val,
                           'best_name': p['name'], 'best_price': p.get('final_price', 0),
                           'best_gifts': gift_texts}
        else:
            g = groups[key]
            g['count'] += 1
            g['min_val'] = min(g['min_val'], val)
            g['max_val'] = max(g['max_val'], val)
            if val > g['best_val']:
                g['best_val']   = val
                g['best_name']  = p['name']
                g['best_price'] = p.get('final_price', 0)
                g['best_gifts'] = gift_texts

    if not groups:
        return f'📊 {provider} 수집 데이터 없음'

    tiers = {}
    for key, g in groups.items():
        tier_idx, tier_label = _data_tier(g['data_key'])
        if tier_label not in tiers:
            tiers[tier_label] = {'idx': tier_idx, 'groups': []}
        tiers[tier_label]['groups'].append(g)

    lines = [f'📊 모요 <b>{provider}</b> 사은품 현황', f'📅 {today}  {time_str}', '']

    for tier_label in TIER_ORDER + ['기타']:
        if tier_label not in tiers: continue
        tier_groups = sorted(tiers[tier_label]['groups'], key=lambda g: (-g['max_val'], g['data_key']))
        best = tier_groups[0]
        tier_max = best['max_val']
        if tier_max == 0: continue

        lines.append(f'📌 <b>{tier_label}  최대 {_man(tier_max)}</b>')
        lines.append(f'  ㅇ 요금제명: {best["best_name"]}  월 {best["best_price"]:,}원')
        if best['best_gifts']:
            abbrevs = [a for t in best['best_gifts'] if isinstance(t, str)
                       for a in [_abbrev_gift(t, best['best_price'])]
                       if '금액미상' not in a][:4]
            if abbrevs:
                lines.append('  ㅇ 지원세부: ' + ' + '.join(abbrevs))
        lines.append('')

    return '\n'.join(lines)


# ── 요약 리포트 (전일 대비 포함) ─────────────────────────────────────────────

_DATA_KEY_GB_CAP = 300  # 이보다 큰 값은 API 파싱 오류(무제한 요금제 등)로 간주해 제외


def _man_short(v: int) -> str:
    """표 셀용 짧은 포맷 - '25.5만원' 대신 '25.5만' (원 생략해 폭 절약)."""
    if v == 0: return '-'
    m = v / 10000
    return f'{m:.0f}만' if m == int(m) else f'{m:.1f}만'


def _disp_width(s: str) -> int:
    """[버그수정, Claude] 모노스페이스 폰트 기준 표시 폭 계산 - 한글/전각문자는
    2칸, 나머지(영문/숫자)는 1칸으로 셈. Python len()은 글자 수만 세서(한글도
    1개=1) '유모'(2글자, 실제 4칸)처럼 한글이 섞인 셀은 실제 렌더링보다 좁게
    계산돼 <code> 표 컬럼이 안 맞던 문제(사장님 지적: "칸도 너무 안맞고")."""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1 for ch in s)


def _pad_disp(s: str, width: int) -> str:
    """_disp_width() 기준으로 오른쪽에 공백을 채워 폭을 맞춤(왼쪽 정렬)."""
    return s + ' ' * max(0, width - _disp_width(s))


SUMMARY_MIN_VAL = 200000  # 요약 표에 실을 최소 사은품 금액(20만원) - 3차 수정 참고


def format_summary_report(plans: list, prev_snapshot: dict = None) -> str:
    """
    1번 메시지: 데이터제공량별 LG/KT 자회사 최대 혜택 요약(표 형태) + 전일 대비
    [수정 20260925 1차] 기존엔 TIER_ORDER(5GB 이하/5~9GB/... 6개 구간)로 묶어서
    보여줬는데, 구간으로 묶지 말고 실제 데이터제공량(5GB/7GB/11GB 등) 단위로 그대로
    보여달라는 요청 반영.
    [수정 20260925 2차] 1차 결과 실제 데이터제공량이 40종류나 돼서(1GB~200GB+ 세분화),
    기존처럼 구간당 4줄(제목+LG+KT+공백)씩 쓰면 161줄까지 늘어나는 문제 발견
    (사장님 피드백: "너무 메시지 양이 늘어나려나?"). 구간당 4줄 블록 대신 표(<code>
    monospace) 형태로 압축 - GB당 1줄로 줄임. 파싱 오류로 나오는 비정상 GB값
    (_DATA_KEY_GB_CAP 초과, 예: "무제한" 요금제가 309969gb로 파싱되는 경우)과
    사은품 0원인 항목은 표에서 제외.
    [수정 20260925 3차] 2차 압축 후에도 33개 데이터구간이 다 나와 여전히 길다는
    피드백("모요 너무길다"). "사업자별로 데이터기준 몇개있고, 금액 큰것만
    보여주기(20만 이상)" 요청 반영 - 헤더에 사업자별 전체 데이터구간 개수를
    요약해서 보여주고, 표 본문은 SUMMARY_MIN_VAL(20만원) 이상인 구간만 표시.
    (전체 구간 수는 남겨서 "20만원 미만인 나머지 N개는 생략됨"을 알 수 있게 함)
    [수정 20260925 4차] LG/KT 2개로 묶던 걸 "유모 헬로 엠모 스카이 4개 사업자별로
    나눠줘" 요청 반영 - 헤더 요약을 "ㅇ 사업자별 요금제수"(모요에 등록된 전체
    요금제 개수 + 그중 최고 사은품 금액)로 바꾸고, 표도 LG/KT 2열 → 유모/헬로/엠모/
    스카이 4열로 확장.
    prev_snapshot: Firestore gift_daily_datakey 어제 데이터 {'U+유모바일': {'5gb': 240000}, ...}
    """
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today    = datetime.now(KST).strftime('%Y-%m-%d')
    time_str = datetime.now(KST).strftime('%H:%M')

    PROVIDER_SHORT = [
        ('U+유모바일',    '유모'),
        ('LG헬로모바일',  '헬로'),
        ('KT엠모바일',    '엠모'),
        ('KT스카이라이프', 'sky'),  # '스카이'(3글자)보다 짧아 표 폭 절약
    ]
    SHORT_OF = dict(PROVIDER_SHORT)

    # ㅇ 사업자별 요금제수 (모요에 등록된 전체 요금제 개수 + 그중 최고 사은품 금액)
    plan_stat_lines = []
    for prov_name, short in PROVIDER_SHORT:
        prov_plans = [p for p in plans if p.get('provider') == prov_name]
        max_val = 0
        for p in prov_plans:
            val = _gift_summary(p)['total_value']
            if val > GIFT_VAL_CAP: val = 0
            if val > max_val: max_val = val
        suffix = f' (최대 {_man_short(max_val)})' if max_val else ''
        plan_stat_lines.append(f' - {short} {len(prov_plans)}개{suffix}')

    all_groups = {}
    for p in plans:
        dk = _data_key(p)
        if dk == 'unknown' or _data_key_gb(dk) > _DATA_KEY_GB_CAP:
            continue
        key = (p['provider'], dk)
        summary = _gift_summary(p)
        val = summary['total_value']
        if val > GIFT_VAL_CAP: val = 0
        if key not in all_groups or val > all_groups[key]['val']:
            all_groups[key] = {
                'provider': p['provider'], 'data_key': dk, 'val': val,
                'plan_name': p['name'], 'final_price': p.get('final_price', 0),
            }

    datakey_data = {}
    all_data_keys = set()
    for key, g in all_groups.items():
        if g['val'] <= 0:
            continue  # 사은품 없는(0원) 항목은 표에서 제외
        short = SHORT_OF.get(g['provider'])
        if not short:
            continue
        dk = g['data_key']
        all_data_keys.add(dk)
        dk_key = (dk, short)
        if dk_key not in datakey_data or g['val'] > datakey_data[dk_key]['val']:
            datakey_data[dk_key] = g

    header_lines = [
        f'📊 <b>자회사 사은품 현황 요약 (모요 기준)</b>  📅 {today}  {time_str}',
        '',
        'ㅇ 사업자별 요금제수',
        *plan_stat_lines,
    ]

    if not all_data_keys:
        return '\n'.join(header_lines) + '\n\n사은품 데이터 없음'

    shorts = [s for _, s in PROVIDER_SHORT]
    rows = []
    for dk in sorted(all_data_keys, key=_data_key_gb):
        dk_label = _data_key_label(dk)
        cells = [dk_label]
        raw_vals = []
        for short in shorts:
            dk_key = (dk, short)
            if dk_key not in datakey_data:
                cells.append('-')
                raw_vals.append(0)
                continue
            g    = datakey_data[dk_key]
            curr = g['val']
            prov = g['provider']
            raw_vals.append(curr)
            cell = _man_short(curr)
            if prev_snapshot:
                prev_val = prev_snapshot.get(prov, {}).get(dk, 0)
                if prev_val and prev_val != curr:
                    diff = curr - prev_val
                    sign = '▲' if diff > 0 else '▼'
                    cell += f'{sign}{_man_short(abs(diff))}'
            cells.append(cell)
        if max(raw_vals) < SUMMARY_MIN_VAL:
            continue  # 20만원 미만인 구간은 표에서 생략
        rows.append(cells)

    lines = header_lines

    if not rows:
        lines.append(f'ㅇ {_man_short(SUMMARY_MIN_VAL)} 이상 구간 없음')
        return '\n'.join(lines)

    lines.append(f'ㅇ {_man_short(SUMMARY_MIN_VAL)} 이상만 표시 ({len(rows)}개)')
    lines.append('')

    col_labels = ['GB'] + shorts
    col_w = [max(_disp_width(r[i]) for r in rows + [col_labels]) for i in range(len(col_labels))]
    header = '  '.join(_pad_disp(col_labels[i], col_w[i]) for i in range(len(col_labels)))
    table_lines = [header, '─' * _disp_width(header)]
    for cells in rows:
        table_lines.append('  '.join(_pad_disp(cells[i], col_w[i]) for i in range(len(cells))))

    # [수정 20260927] <code>(인라인) 대신 <pre>(블록) 사용 - 사업자 실적 봇이 쓰는
    # 카드형 박스+복사버튼 스타일과 동일한 효과(사장님 요청: "이런형태가 더
    # 나으려나?"). 그 봇은 Markdown ``` 코드펜스를 쓰지만 Telegram에서 <pre>와
    # ```는 같은 entity(pre)로 렌더링되므로 parse_mode=HTML 그대로 유지하면서
    # <pre>로만 바꾸면 동일한 카드+복사버튼 모양이 나옴.
    lines.append('<pre>' + '\n'.join(table_lines) + '</pre>')
    return '\n'.join(lines)


# ── 모요 vs 유모바일직영 비교 ─────────────────────────────────────────────────

def format_moyo_vs_direct(moyo_plans: list, direct_dk_max: dict,
                          provider: str = 'U+유모바일',
                          direct_label: str = None) -> str:
    """
    모요 vs 직영 이벤트 데이터제공량(GB)별 비교 메시지 (<code> 테이블)
    [수정 20260925] 기존엔 6개 구간(TIER_ORDER)으로 묶어서 "구간 내 각자 최고금액"을
    비교했는데, 모요/직영이 서로 다른 사이트에서 큐레이션된 요금제라 같은 구간 안에서도
    실제 GB가 다른 요금제끼리 비교되는 문제가 있었음. "서로 비교값 있는 것만 출력해도
    될듯" 피드백 반영 - 정확히 같은 GB에 양쪽 다 데이터 있는 경우만 비교.
    direct_dk_max: {'7gb': 480000, ...} (format_telegram_message의 4번째 반환값 dk_max)
    direct_label: 제목에 쓸 직영 쪽 이름 (예: '유모바일직영', '엠모바일직영').
                  생략하면 provider에서 자동 유도(예: 'U+유모바일' → '유모바일직영').
    """
    from datetime import datetime, timezone, timedelta
    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime('%Y-%m-%d')

    if direct_label is None:
        direct_label = provider.replace('U+', '').replace('KT', '') + '직영'

    moyo_dk = compute_datakey_max(moyo_plans, provider=provider)

    row_cells = []
    for dk in sorted(set(moyo_dk) & set(direct_dk_max), key=_data_key_gb):
        moyo_val   = moyo_dk.get(dk, 0)
        direct_val = direct_dk_max.get(dk, 0)
        if moyo_val == 0 or direct_val == 0:
            continue
        diff = direct_val - moyo_val
        if diff > 0:   gap = f'직영+{_man(abs(diff))}▲'
        elif diff < 0: gap = f'모요+{_man(abs(diff))}▲'
        else:          gap = '동일━'
        row_cells.append([_data_key_label(dk), _man(moyo_val), _man(direct_val), gap])

    if not row_cells:
        return f'⚖️ <b>모요 vs {direct_label} 비교</b>  📅 {today}\n\nℹ️ 비교 데이터 없음'

    # [수정 20260927] len() 기반 :<N 고정폭 대신 _disp_width()/_pad_disp() 사용 -
    # "모요"/"직영"처럼 한글 셀이 섞이면 len()은 실제 표시폭(한글=2칸)보다 좁게
    # 세서 표가 안 맞던 문제. <code> 대신 <pre>로 바꿔 카드형 박스+복사버튼
    # 스타일도 함께 적용(사장님 요청: "이런형태가 더 나으려나?").
    col_labels = ['GB', '모요', '직영']
    col_w = [max(_disp_width(r[i]) for r in row_cells + [col_labels]) for i in range(3)]
    header = ' '.join(_pad_disp(col_labels[i], col_w[i]) for i in range(3)) + ' GAP'
    rows = [' '.join(_pad_disp(r[i], col_w[i]) for i in range(3)) + ' ' + r[3] for r in row_cells]
    table = header + '\n' + '-' * _disp_width(header) + '\n' + '\n'.join(rows)

    return (
        f'⚖️ <b>모요 vs {direct_label} 비교</b>  📅 {today}\n\n'
        f'<pre>{table}</pre>'
    )


# ── K CUP 입력 어댑터 (직영 스크래퍼 / 모요 raw plan → format_kcup_violation 채널 dict) ─

def _short_date(d: str) -> str:
    """'YYYY-MM-DD' → 'M/D' (ktm/umobile 스크래퍼 _short_date와 동일 규칙)"""
    m = re.match(r'\d{4}-(\d{2})-(\d{2})', d or '')
    return f'{int(m.group(1))}/{int(m.group(2))}' if m else (d or '')


def _benefits_to_gift_texts(benefits: list) -> list:
    """KT엠모바일/U+유모바일 Vision 파싱 결과의 benefits(list[dict]) → 사람이 읽는 텍스트 리스트"""
    texts = []
    for b in benefits or []:
        name   = b.get('name', '') or '혜택'
        amount = b.get('amount_won', 0)
        months = b.get('months', 1) or 1
        total  = b.get('total_won', 0) or amount
        if months > 1 and amount:
            texts.append(f'{name} {_man(amount)}×{months}개월({_man(total)})')
        else:
            texts.append(f'{name} {_man(total)}')
    return texts


def _direct_plan_to_channel(plan: dict) -> dict:
    """
    KT엠모바일/U+유모바일 직영 스크래퍼의 plan dict
    (format_telegram_message에서 _event_url/_event_title/_date_start/_date_end가
     이미 주입된 상태) → format_kcup_violation()이 기대하는 채널 dict로 정규화.
    """
    ds = plan.get('_date_start', '')
    de = plan.get('_date_end', '')
    period = f'{_short_date(ds)}~{_short_date(de)}' if ds and de else ''
    return {
        'plan_name':    plan.get('plan_name') or '',
        'price':        plan.get('total_won') or 0,
        'gift_texts':   _benefits_to_gift_texts(plan.get('benefits')),
        'event_title':  plan.get('_event_title') or '',
        'event_url':    plan.get('_event_url') or '',
        'event_period': period,
        'gb':           plan.get('_gb', 0) or 0,
    }


def _moyo_group_to_channel(group: dict) -> dict:
    """
    build_group_index()가 만든 모요 그룹 dict(plan_name/total_value/gift_texts)를
    채널 dict로 정규화. 모요는 이벤트 링크가 불필요하므로 event_* 필드는 항상 빈 값.
    """
    try:
        gb = float(str(group.get('data_key', '')).replace('gb', ''))
    except ValueError:
        gb = 0
    return {
        'plan_name':    group.get('plan_name') or '',
        'price':        group.get('total_value') or 0,
        'gift_texts':   [t for t in (group.get('gift_texts') or []) if isinstance(t, str)],
        'event_title':  '',
        'event_url':    '',
        'event_period': '',
        'gb':           gb,
    }


PLAN_VAL_CAP = 600000  # ktm/umobile 스크래퍼의 format_telegram_message()와 동일한 과대계산 방지 상한
STAGE_RANK = {'1단계': 1, '2단계': 2, '3단계': 3, '4단계': 4}


def _direct_plan_gb(plan: dict) -> float:
    """
    직영 plan의 tier 분류용 GB 추출.
    base_gb/total_gb가 서로 어긋나는 경우(예: U+유모바일 '이즈' 시리즈처럼 기본+랜덤
    데이터가 섞인 상품)가 있어, 모요 쪽(_data_key)과 동일하게 요금제명에 적힌 숫자를
    최우선으로 사용 - 광고 문구 기준으로 양쪽을 통일해야 tier가 어긋나지 않음.
    요금제명에 GB가 없을 때만 base_gb → total_gb 순으로 폴백.
    """
    name = plan.get('plan_name') or ''
    m = _RE_DATA_GB.search(name)
    if m:
        return float(m.group(1))
    return float(plan.get('base_gb') or plan.get('total_gb') or 0)


def compare_kcup(moyo_plans: list, direct_posts: list,
                 moyo_provider: str, direct_label: str,
                 min_stage: str = '2단계',
                 compact: bool = False,
                 run_time: str = None, start_index: int = 1) -> list:
    """
    모요 plan 리스트 + 직영 스크래퍼 post 리스트(scrape_with_cache 결과) → K CUP 특이사항 메시지 리스트

    moyo_plans:    gift_moyo_scraper.scrape_moyo_gifts() 결과 (전체, provider 필터는 내부에서 처리)
    direct_posts:  gift_ktm_event_scraper / gift_umobile_event_scraper의
                   scrape_with_cache() 결과 - [{url, title, date_start, date_end, plans:[...]}]
    moyo_provider: 모요 데이터 필터링용 provider명 (예: 'KT엠모바일', 'U+유모바일')
    direct_label:  메시지 표시용 라벨 (예: 'KT엠모바일 직영')
    min_stage:     이 단계 미만은 메시지로 만들지 않음 (기본 2단계 - 1단계는 조치 없음이라 제외)
    compact:       False(기본)면 요금제명/프로모션 세부내용/링크까지 포함한 상세 메시지
                   (건별로 따로 발송하는 걸 전제 - 길지만 건당 1건씩 보내면 문제없음).
                   True면 텔레그램 요약용 축약판(3~4줄, 세부 프로모션 생략).
    run_time:      메시지 헤더에 쓸 실행 시각 문자열 (예: '8/28 11시'). 여러 사업자를 이어서
                   호출할 때 같은 값을 넘겨야 모든 메시지 헤더 시각이 일치함.
    start_index:   이 배치의 첫 메시지 순번 (기본 1). 사업자별로 나눠 호출할 때 두 번째
                   호출에는 len(첫번째_결과)+1을 넘기면 전체 배치에서 순번이 이어짐.

    [수정 20260925] 기존엔 tier(TIER_ORDER 구간) 단위로 모요/직영 각각 최고 금액
    요금제를 뽑아 비교했는데, 같은 구간이어도 실제 GB가 다른 요금제끼리 비교되는
    문제가 있어 _gb_diff_warning()으로 경고만 붙이던 상태였음. "서로 비교값 있는
    것만 출력해도 될듯" 피드백 반영 - 정확히 같은 GB에 양쪽 다 데이터가 있는
    경우만 비교 대상으로 삼음 (매칭되는 건수는 줄 수 있으나 비교 자체는 항상
    동일 GB끼리라 gb_diff_warning이 필요 없어짐 - 자연히 빈 문자열 반환됨).
    """
    min_rank = STAGE_RANK.get(min_stage, 2)

    # 1) 모요: provider 필터 → 그룹핑 → data_key(GB)별 최고금액 그룹
    moyo_filtered = [p for p in moyo_plans if p.get('provider') == moyo_provider]
    moyo_groups = build_group_index(moyo_filtered)
    moyo_by_dk = {}
    for g in moyo_groups.values():
        dk = g['data_key']
        if dk == 'unknown':
            continue
        if g['total_value'] > moyo_by_dk.get(dk, {}).get('total_value', -1):
            moyo_by_dk[dk] = g

    # 2) 직영: post → plan에 이벤트 메타 주입 → data_key(GB)별 최고금액 plan
    direct_by_dk = {}
    for post in direct_posts:
        for raw_plan in post.get('plans', []):
            won = min(raw_plan.get('total_won', 0) or 0, PLAN_VAL_CAP)
            if won <= 0:
                continue
            plan = dict(raw_plan)  # 원본 훼손 방지
            plan['total_won']    = won  # 캡 적용된 값으로 덮어씀 (비교/표시 모두 이 값 사용)
            plan['_event_url']   = post.get('url', '')
            plan['_event_title'] = post.get('title', '')
            plan['_date_start']  = post.get('date_start', '')
            plan['_date_end']    = post.get('date_end', '')
            gb = _direct_plan_gb(plan)
            plan['_gb'] = gb
            if not gb:
                continue
            dk = f'{int(gb) if gb == int(gb) else gb}gb'
            if won > direct_by_dk.get(dk, {}).get('total_won', -1):
                direct_by_dk[dk] = plan

    # 3) 정확히 같은 GB에 양쪽 다 있는 경우만 비교 → min_stage 이상인 것만 메시지 생성
    messages = []
    idx = start_index
    for dk in sorted(set(moyo_by_dk) & set(direct_by_dk), key=_data_key_gb):
        a = _moyo_group_to_channel(moyo_by_dk[dk])
        b = _direct_plan_to_channel(direct_by_dk[dk])
        diff = abs(a['price'] - b['price'])
        stage, _ = _kcup_tier(diff)
        if STAGE_RANK.get(stage, 0) < min_rank:
            continue
        gb_label = _data_key_label(dk)
        messages.append(format_kcup_violation(
            gb_label, '', '', a, b,
            provider=moyo_provider, label_a='모요', label_b=direct_label,
            compact=compact, run_time=run_time, index=idx))
        idx += 1
    return messages


def build_kcup_records(moyo_plans: list, direct_posts: list,
                       moyo_provider: str, direct_label: str,
                       min_stage: str = '2단계') -> list:
    """
    compare_kcup()과 동일한 매칭 로직(정확히 같은 GB에 양쪽 다 데이터가 있는 것만)으로
    위반 건을 뽑되, 텔레그램 메시지 문자열이 아니라 구조화된 레코드로 반환.

    [추가 20260925] 기존엔 위반 건마다(요금제명+프로모션 세부내역+링크 포함) 전체
    메시지를 건별로 따로 발송했는데, 사장님 요청으로 "요약(단계별 건수 + GB:금액
    한 줄씩) + 상세는 버튼으로" 구조로 바꾸면서 요약 조립용(format_kcup_summary)과
    버튼 클릭 시 보여줄 상세(format_kcup_violation, compact=False)용으로 같은
    매칭 결과를 두 군데서 재사용해야 해서, compare_kcup()의 매칭 로직만 분리.

    Returns: [{
        'gb_label': str, 'gb': float, 'stage': str, 'penalty': int, 'diff': int,
        'moyo_price': int, 'direct_price': int,
        'channel_a': dict,  # 모요 - format_kcup_violation()의 channel_a와 동일 스키마
        'channel_b': dict,  # 직영 - format_kcup_violation()의 channel_b와 동일 스키마
        'provider': str, 'direct_label': str,
    }, ...]  (GB 오름차순)
    """
    min_rank = STAGE_RANK.get(min_stage, 2)

    moyo_filtered = [p for p in moyo_plans if p.get('provider') == moyo_provider]
    moyo_groups = build_group_index(moyo_filtered)
    moyo_by_dk = {}
    for g in moyo_groups.values():
        dk = g['data_key']
        if dk == 'unknown':
            continue
        if g['total_value'] > moyo_by_dk.get(dk, {}).get('total_value', -1):
            moyo_by_dk[dk] = g

    direct_by_dk = {}
    for post in direct_posts:
        for raw_plan in post.get('plans', []):
            won = min(raw_plan.get('total_won', 0) or 0, PLAN_VAL_CAP)
            if won <= 0:
                continue
            plan = dict(raw_plan)
            plan['total_won']    = won
            plan['_event_url']   = post.get('url', '')
            plan['_event_title'] = post.get('title', '')
            plan['_date_start']  = post.get('date_start', '')
            plan['_date_end']    = post.get('date_end', '')
            gb = _direct_plan_gb(plan)
            plan['_gb'] = gb
            if not gb:
                continue
            dk = f'{int(gb) if gb == int(gb) else gb}gb'
            if won > direct_by_dk.get(dk, {}).get('total_won', -1):
                direct_by_dk[dk] = plan

    records = []
    for dk in sorted(set(moyo_by_dk) & set(direct_by_dk), key=_data_key_gb):
        a = _moyo_group_to_channel(moyo_by_dk[dk])
        b = _direct_plan_to_channel(direct_by_dk[dk])
        diff = abs(a['price'] - b['price'])
        stage, penalty = _kcup_tier(diff)
        if STAGE_RANK.get(stage, 0) < min_rank:
            continue
        records.append({
            'gb_label': _data_key_label(dk), 'gb': _data_key_gb(dk),
            'stage': stage, 'penalty': penalty, 'diff': diff,
            'moyo_price': a['price'], 'direct_price': b['price'],
            'channel_a': a, 'channel_b': b,
            'provider': moyo_provider, 'direct_label': direct_label,
        })
    return records


_STAGE_ORDER_DESC = ['4단계', '3단계', '2단계', '1단계']


def format_kcup_summary(records_by_provider: dict, run_time: str = None) -> str:
    """
    K CUP 특이사항 요약 메시지 (건별 상세 발송 대신 1건으로 통합).

    [추가 20260925] "상세메시지는 링크나 버튼으로 구현" 요청 반영 - 요금제명/
    프로모션 세부내역/이벤트 링크가 포함된 전체 상세(format_kcup_violation,
    compact=False)는 더 이상 텔레그램에 그대로 뿌리지 않고, 이 요약 메시지 +
    build_kcup_buttons()가 만드는 인라인 버튼(건별 "상세보기")으로 대체.

    records_by_provider: {provider_label: [record, ...]}  # build_kcup_records() 결과.
                          위반 없는 사업자도 키만 있으면 "해당 없음"으로 표시됨.
    """
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    title_time = run_time or datetime.now(KST).strftime('%-m/%-d %H시')

    lines = [f'{title_time} 특이사항 요약', '']

    lines.append('ㅇ 특이사항 요약')
    total_count = 0
    for provider, records in records_by_provider.items():
        total_count += len(records)
        if not records:
            lines.append(f'{provider} 해당 없음')
            continue
        counts = {}
        for r in records:
            counts[r['stage']] = counts.get(r['stage'], 0) + 1
        parts = [f'{s} {counts[s]}건' for s in _STAGE_ORDER_DESC if s in counts]
        lines.append(f'{provider} ' + ', '.join(parts))

    if total_count == 0:
        return '\n'.join(lines)

    for provider, records in records_by_provider.items():
        if not records:
            continue
        lines.append('')
        lines.append(f'ㅇ {provider} (모요 VS 직영)')
        by_stage = {}
        for r in records:
            by_stage.setdefault(r['stage'], []).append(r)
        for stage in _STAGE_ORDER_DESC:
            rows = by_stage.get(stage)
            if not rows:
                continue
            lines.append(f'{_STAGE_EMOJI.get(stage, "")} {stage}')
            for r in rows:
                lines.append(f' - {r["gb_label"]} : {_man_short(r["moyo_price"])} VS {_man_short(r["direct_price"])}')

    return '\n'.join(lines)


_KCUP_SHORT_PROVIDER = {'KT엠모바일': 'KT', 'U+유모바일': 'U+', 'KT스카이라이프': '스카', 'LG헬로모바일': '헬로'}


def build_kcup_buttons(records_by_provider: dict, date_str: str,
                       per_row: int = 2) -> list:
    """
    요약 메시지에 붙일 건별 "상세보기" 인라인 버튼 생성.
    callback_data 형식: 'gift_kcup_{date_str}_{seq}' - gift_callback_handler.py가
    seq로 Firestore gift_reports/{date_str}/kcup_details/{seq} 문서를 조회해 상세를 보여줌
    (seq→상세 매핑은 호출부에서 build_kcup_records() 순서 그대로 저장해야 함).

    Returns: 텔레그램 inline_keyboard 형식 [[{text, callback_data}, ...], ...]
    """
    buttons = []
    seq = 0
    for provider, records in records_by_provider.items():
        short = _KCUP_SHORT_PROVIDER.get(provider, provider[:2])
        for r in records:
            emoji = _STAGE_EMOJI.get(r['stage'], '')
            buttons.append({
                'text': f'{emoji}{short} {r["gb_label"]}',
                'callback_data': f'gift_kcup_{date_str}_{seq}',
            })
            seq += 1
    rows = [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]
    return rows


# ── K CUP 위반 단계 판정 ──────────────────────────────────────────────────────

_STAGE_EMOJI = {
    '1단계': '🟢',
    '2단계': '🟡',
    '3단계': '🟠',
    '4단계': '🔴',
}


def _kcup_tier(diff: int) -> tuple:
    """편차 금액 → (단계라벨, 해당 단계 최대 참고 벌점)"""
    for upper, label, penalty in KCUP_TIERS:
        if upper is None or diff < upper:
            return label, penalty
    return KCUP_TIERS[-1][1], KCUP_TIERS[-1][2]


def _event_link_line(ch: dict) -> str:
    """이벤트 제목+기간을 Telegram <a href> 링크로 (URL 없으면 링크 없이 텍스트만)"""
    title  = ch.get('event_title', '')
    period = ch.get('event_period', '')
    url    = ch.get('event_url', '')
    if not title:
        return ''
    label = f'{title} ({period})' if period else title
    if url:
        return f'  └ 🔗 <a href="{url}">{label}</a>'
    return f'  └ 🔗 {label} (링크 없음)'


GB_DIFF_WARN_RATIO = 1.3  # 큰 쪽이 작은 쪽의 130%(=30% 이상 차이)면 "실제 데이터량 차이 큼" 경고
                          # 절대값(5GB)으로 했다가 100GB↔110GB(10%)는 잡히고 1GB↔3GB(200%)는
                          # 안 잡히는 역효과가 있어 비율 기준으로 변경 (2026-08-28)


def _gb_diff_warning(gb_a: float, gb_b: float) -> str:
    """같은 tier 안에서도 모요/직영이 뽑힌 요금제의 실제 GB가 크게 다를 때 경고 문구 생성"""
    if not gb_a or not gb_b:
        return ''
    lo, hi = min(gb_a, gb_b), max(gb_a, gb_b)
    if hi / lo < GB_DIFF_WARN_RATIO:
        return ''
    return f'⚠️ 요금제 Gap : 모요 {gb_a:g}GB vs 직영 {gb_b:g}GB'


def format_kcup_violation(tier_label: str, data_key: str, voice_key: str,
                          channel_a: dict, channel_b: dict,
                          provider: str = '',
                          label_a: str = '모요', label_b: str = '알뜰폰허브',
                          compact: bool = False,
                          run_time: str = None, index: int = None) -> str:
    """
    K CUP 편차 위반 특이사항 메시지.

    compact=False(기본): 요금제명 + 프로모션 세부내용 + 이벤트 링크 전부 포함 (로그/검증용, 길다)
    compact=True: 텔레그램 알림용 축약판 - 3~4줄, 세부 프로모션 텍스트는 생략하고
                  금액/편차/단계/링크만 표시.

    run_time: 헤더에 쓸 실행 시각 문자열 (예: '8/28 11시'). 생략하면 호출 시점 날짜만 표시.
    index:    같은 배치에서 이 메시지의 순번 (예: 1). 생략하면 표시 안 함.

    channel_a / channel_b: {
        'plan_name':    str,   # 예: '11GB / 통화·문자 무제한'
        'price':        int,   # 사은품 총액(원)
        'gift_texts':   list[str],   # 프로모션 세부내용 (build_group_index의 gift_texts 재사용)
        'event_title':  str,   # 예: 'M모바일 BEST! 매월 밀리의...'
        'event_url':    str,   # 이벤트 상세페이지 URL
        'event_period': str,   # 예: '8/14~8/31'
    }
    ※ event_title/event_url/event_period는 현재 스크래퍼 산출물에 없다면 먼저 채워 넣어야 함
       (KT엠모바일/U+유모바일 스크래퍼가 이미 인라인 키보드 버튼용으로 제목+URL을 들고 있다면
        그 값을 그대로 넘기면 됨)
    """
    from datetime import datetime, timezone, timedelta
    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime('%-m/%-d')

    diff = abs(channel_a.get('price', 0) - channel_b.get('price', 0))
    tier, penalty = _kcup_tier(diff)

    if compact:
        link_line = _event_link_line(channel_b) or _event_link_line(channel_a)
        header = f'⚠️ {provider} ({tier_label})' if provider else f'⚠️ ({tier_label})'
        lines = [
            f'{header}  {tier} 위반 (편차 {_man(diff)})',
            f'{label_a} {_man(channel_a.get("price", 0))} vs {label_b} {_man(channel_b.get("price", 0))}',
        ]
        if link_line:
            lines.append(link_line.replace('  └ 🔗 ', '🔗 '))
        return '\n'.join(lines)

    title_time = run_time or today
    title = f'{title_time} 특이사항' + (f' ({index}/{{TOTAL}})' if index else '')
    lines = [title]
    header = f'ㅇ {provider} ({tier_label})' if provider else f'ㅇ ({tier_label})'
    lines.append(f'{header}  -{_man(channel_a.get("price", 0))}(모요) vs {_man(channel_b.get("price", 0))}(직영)')

    gb_warn = _gb_diff_warning(channel_a.get('gb', 0), channel_b.get('gb', 0))
    if gb_warn:
        lines.append(gb_warn)

    emoji = _STAGE_EMOJI.get(tier, '')
    penalty_note = f'참고: {tier} 최대 벌점 {penalty}점' if penalty else f'참고: {tier} (벌점 대상 아님)'
    lines.append(f'{emoji} 편차 {_man(diff)} → {tier} 위반 ({penalty_note})')
    lines.append('')

    for bracket_label, ch in [('모요', channel_a), ('직영', channel_b)]:
        plan_name = ch.get('plan_name', '-')
        price     = ch.get('price', 0)
        spec = _spec_line(plan_name)
        if spec:
            lines.append(f'[{bracket_label}] {spec}')
        else:
            lines.append(f'[{bracket_label}]')
        lines.append(f'◎  {plan_name} : 총 {_man(price)}')
        lines.extend(_gift_breakdown_lines(ch.get('gift_texts', [])))
        lines.append('')

    link_line = _event_link_line(channel_b) or _event_link_line(channel_a)
    if link_line:
        lines.append(link_line)

    return '\n'.join(lines)


# ── 모요 vs 유모바일직영 vs KT엠모바일직영 3자 비교 ────────────────────────────

def format_moyo_vs_direct_multi(moyo_plans: list,
                                 umobile_band_max: dict,
                                 ktm_band_max: dict,
                                 moyo_provider: str = 'U+유모바일',
                                 gap_threshold: int = 100000) -> str:
    """
    모요 vs 유모바일직영 vs KT엠모바일직영 3자 구간별 비교 메시지
    umobile_band_max / ktm_band_max: {'5GB 이하': 480000, ...} (각 스크래퍼 Vision 파싱 결과)

    <code> 블록으로 감싼 표 형태 (price-monitor의 "현재 최저가" 표와 동일 스타일 - 정렬 + 복사 버튼).
    모요 대비 차이가 gap_threshold(기본 10만원) 이상 나는 값에는 바로 뒤에 '*' 붙이고,
    맨 아래에 범례 한 줄만 표시 (행마다 GAP 텍스트 반복하지 않음).
    """
    from datetime import datetime, timezone, timedelta
    KST   = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime('%Y-%m-%d')

    moyo_tier = compute_tier_max(moyo_plans, provider=moyo_provider)

    rows = []
    has_row  = False
    has_star = False
    for tier_label in TIER_ORDER:
        moyo_val    = moyo_tier.get(tier_label, 0)
        umobile_val = umobile_band_max.get(tier_label, 0)
        ktm_val     = ktm_band_max.get(tier_label, 0)
        if moyo_val == 0 and umobile_val == 0 and ktm_val == 0:
            continue
        has_row = True

        u_diff = umobile_val - moyo_val
        k_diff = ktm_val - moyo_val

        # 모요 칸은 유모/엠모 어느 쪽이든 모요가 10만원 이상 앞서면 표시
        moyo_star = (u_diff <= -gap_threshold) or (k_diff <= -gap_threshold)
        umobile_star = u_diff >= gap_threshold
        ktm_star = k_diff >= gap_threshold
        if moyo_star or umobile_star or ktm_star:
            has_star = True

        short = (tier_label
                 .replace('GB 이하', 'GB↓')
                 .replace('GB 이상', 'GB+'))

        moyo_txt    = _man(moyo_val) + ('*' if moyo_star else '')
        umobile_txt = _man(umobile_val) + ('*' if umobile_star else '')
        ktm_txt     = _man(ktm_val) + ('*' if ktm_star else '')

        rows.append([short, moyo_txt, umobile_txt, ktm_txt])

    if not has_row:
        return f'⚖️ 모요 vs 유모바일 vs 엠모바일 비교\n📅 {today}\n\nℹ️ 비교 데이터 없음'

    # [수정 20260927] len() 기반 :<N 대신 _disp_width()/_pad_disp() 사용(한글 셀
    # 정렬 문제) + <code> 대신 <pre>로 카드형 박스+복사버튼 스타일 적용.
    col_labels = ['구간', '모요', '유모', '엠모']
    col_w = [max(_disp_width(r[i]) for r in rows + [col_labels]) for i in range(4)]
    header = ''.join(_pad_disp(col_labels[i], col_w[i]) for i in range(4))
    body   = '\n'.join(''.join(_pad_disp(r[i], col_w[i]) for i in range(4)) for r in rows)
    table  = header + '\n' + '-' * _disp_width(header) + '\n' + body
    footer = f'\n* 다른 값과 {gap_threshold//10000}만원 이상 차이' if has_star else ''

    return (
        f'⚖️ 모요 vs 유모바일 vs 엠모바일 비교\n'
        f'📅 {today}\n\n'
        f'<pre>{table}</pre>{footer}'
    )