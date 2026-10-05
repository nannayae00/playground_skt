"""
bw_engine.py  v3.1
작성일: 2026-04-01

[수정 이력]
v3.2 | 2026-06-01 | 지방선거 공휴일 추가 + 월말 마지막 영업일 가중치 반영
  - _HOLIDAYS에 '2026-06-03' (지방선거) 추가
  - _is_month_end_bizday(): 월말 마지막 영업일 감지 함수 추가
  - _holiday_structure(): 'month_end' 케이스 추가
  - _get_knn_similar_days(): 월말 영업일끼리 매칭 조건 추가
  - Gemini 프롬프트: 월말 마지막 영업일 컨텍스트 추가
  - _calc_bw_fallback(): 월말 마지막 영업일 × 1.25 보정
v3.1 | 2026-04-20 | 공휴일 0일 처리 범위 축소 + 영업 공휴일 K-NN 개선
  - is_zero_day(): 설날 당일·추석 당일만 0, 나머지 공휴일은 영업일 취급
  - _ZERO_HOLIDAYS: 진짜 영업 0인 날 별도 관리 (설/추석 당일만)
  - _HOLIDAYS: K-NN 공휴일 구조 매칭용으로만 사용 (기존 역할 유지)
  - _calc_bw_fallback(): 공휴일이어도 영업일이면 토요일 수준(0.6) 적용
  - _HOLIDAYS 2026-05-25(석가탄신일) 추가
  - _get_knn_similar_days(): 영업 공휴일은 과거 토요일·공휴일 데이터로 매칭
    (하드코딩 없이 데이터 기반으로 자동 토요일 수준 예측)
v3.0 | 2026-04-08 | K-NN + Gemini 하이브리드 예측 도입 (자동 정확도 향상)
  - calc_bw_ai(): 하드코딩 테이블 → Firestore 실측 기반 K-NN + Gemini 하이브리드
    1단계: Firestore에서 유사 과거일 조회 (요일×주차×공휴일구조 매칭)
    2단계: 최신 우선 가중 평균 (최근3개월×3, 3~9개월×2, 9개월+×1)
    3단계: Gemini가 트렌드·연휴구조·전주실적 종합 판단
    4단계: Gemini 실패 시 K-NN 결과로 자동 폴백
  - 데이터 쌓일수록 자동 정확도 향상 (코드 추가 수정 불필요)
  - get_bw_final() 우선순위 변경:
    bw_ai_prev(최신예측) > bw_manual > bw_ai_w3 > bw_ai_w2 > bw_ai_w1
  - save_bw_to_daily(): date 필드 자동 추가 (조회 누락 방지)
  - get_month_bw_map(): 문서ID 직접 조회 (date 필드 없는 문서 포함)
  - 중복 코드 제거 (v2.0 파일에 구버전 코드 중복 존재 → 정리)
v2.0 | 2026-04-08 | MVNO IN 기반 bw_performance 재정의 + 주차 보정 추가
v1.0 | 2026-04-01 | 최초 작성

[설계 근거]
  bw = MVNO 시장 활동성 지수 = 당일 MVNO IN ÷ 월 일평균 MVNO IN
  MNO Out(T-Out)은 bw에 연동된 파생 지표

  정확도 예상:
    v2.0 (하드코딩+주차보정): MAE ≈ 0.10~0.14, 정확도 80~85%
    v3.0 즉시:               MAE ≈ 0.06~0.08, 정확도 88~92%
    6개월 후 데이터 축적:    MAE ≈ 0.03~0.05, 정확도 93~96%
    장기 수렴:               95~97% (나머지 3~5%는 예측불가 이벤트)

[bw_final 우선순위 v3.0]
  bw_ai_prev(최신예측) > bw_manual(참고) > bw_ai_w3 > bw_ai_w2 > bw_ai_w1 > calc_bw_ai()

[자동 업데이트 구조]
  매일 20시 마감: bw_performance 저장 → 다음날 bw_ai_prev 재계산
  7/14/21일:      w1/w2/w3 실적 피드백 보정 (ktoa_scraper.py)
  월말:           다음달 전체 bw_ai_prev 사전 계산 (ktoa_scraper.py)
  공휴일 목록:    연 1회 수동 업데이트 (_HOLIDAYS)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ── 폴백용 월×요일 테이블 (K-NN 실패 시 사용, MVNO IN 기반 2주차 기준값)
# 인덱스: [월요일, 화요일, 수요일, 목요일, 금요일, 토요일]
_BW_TABLE_FALLBACK = {
    1:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    2:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    3:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    4:  [1.050, 0.963, 1.020, 0.949, 0.984, 0.575],
    5:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    6:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    7:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    8:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    9:  [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    10: [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    11: [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
    12: [1.220, 1.008, 1.062, 1.029, 1.059, 0.658],
}

# 주차 보정계수 (폴백 전용, 2주차=1.0 기준)
_WEEK_FACTOR = {
    1: [1.084, 1.051, 1.108, 1.113, 1.030, 1.102],
    2: [1.000, 1.000, 1.000, 1.000, 1.000, 1.000],
    3: [0.951, 0.941, 0.961, 0.988, 0.916, 0.891],
    4: [0.898, 0.920, 0.912, 0.936, 0.886, 0.845],
    5: [0.898, 0.920, 0.912, 0.936, 0.886, 0.845],
}

# 공휴일 목록 — K-NN 공휴일 구조 매칭용 (bw 예측 컨텍스트)
# 연 1회 수동 업데이트
# [2026-09-22] 크리스마스(12/25) 전체 제거 - 실무자 시뮬레이션(2025년 실측) 확인 결과
# 감소 없이 평상시와 동일한 값이었음. 이 업종(MNP)은 크리스마스 영향이 없는 것으로 확인됨.
_HOLIDAYS = {
    '2024-01-01','2024-02-09','2024-02-10','2024-02-11','2024-02-12',
    '2024-03-01','2024-04-10','2024-05-05','2024-05-06','2024-05-15',
    '2024-06-06','2024-08-15','2024-09-16','2024-09-17','2024-09-18',
    '2024-10-03','2024-10-09',
    '2025-01-01','2025-01-28','2025-01-29','2025-01-30',
    '2025-03-01','2025-05-05','2025-05-06','2025-06-06',
    '2025-08-15','2025-10-03','2025-10-05','2025-10-06',
    '2025-10-07','2025-10-08','2025-10-09',
    '2026-01-01','2026-01-27','2026-01-28','2026-01-29','2026-01-30',
    '2026-03-01','2026-05-05','2026-05-24','2026-05-25',
    '2026-06-03',   # ★ 지방선거 (2026-06-01 추가)
    '2026-06-06',
    '2026-07-17',   # ★ 제헌절, 2026년부터 18년 만에 공휴일 재지정 (매년 반복 예정,
                     #   내년 이후에도 계속 추가 필요 - 실무자 실측 확인: bw 0.4로 하락)
    '2026-08-17',
    '2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-09',
    # [수정 20261001] 2026-10-03(개천절)이 토요일이라 월요일 2026-10-05가
    # 대체공휴일 - 실무자 지적으로 누락 발견(기존엔 10/5가 평일 월요일로
    # 취급돼 bw 1.204로 높게 잡혔음, 실제론 공휴일 수준으로 낮아야 함)
    '2026-10-05',
}

# 진짜 영업 0인 날 — 설날 당일·추석 당일만
# (일요일은 is_zero_day에서 별도 처리)
# 연 1회 수동 업데이트
# [2026-09-22] 2026 추석: 실무자 확인 결과 9/25(금)~9/27(일) MNP 시스템 자체가 휴무
# (9/24 목은 연휴 첫날이지만 소량 영업 있음 - bw 0.4, _HOLIDAYS에서 0.6 폴백값 적용)
_ZERO_HOLIDAYS = {
    # 설날 당일
    '2024-02-10',
    '2025-01-29',
    '2026-01-29',
    # 추석 당일
    '2024-09-17',
    '2025-10-06',
    '2026-09-25', '2026-09-26', '2026-09-27',
}


def _is_holiday(date_str: str) -> bool:
    """공휴일 여부 (K-NN 구조 매칭용)"""
    return date_str in _HOLIDAYS


def is_zero_day(date_str: str) -> bool:
    """영업 0일: 일요일 또는 설날/추석 당일만
    근로자의날·어린이날 등 기타 공휴일은 영업일 취급 (토요일 수준 bw)
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return d.weekday() == 6 or date_str in _ZERO_HOLIDAYS


def _is_month_end_bizday(date_str: str) -> bool:
    """
    월말 마지막 영업일 여부
    해당 일 이후 말일까지 모두 zero_day(일요일/설추석)이거나 공휴일이면 True
    ex) 6/30(화) → True / 5/29(금, 30토 31일) → True
    """
    from calendar import monthrange
    d = datetime.strptime(date_str, '%Y-%m-%d')
    if is_zero_day(date_str):
        return False
    last_day = monthrange(d.year, d.month)[1]
    if d.day == last_day:
        return True
    # d.day+1 ~ last_day 중 영업일(non-zero, non-holiday) 있으면 False
    for day in range(d.day + 1, last_day + 1):
        ds = f"{d.year:04d}-{d.month:02d}-{day:02d}"
        if not is_zero_day(ds) and not _is_holiday(ds):
            return False
    return True


def _bizdays_until_month_end(date_str: str) -> Optional[int]:
    """
    [추가 20261002] date_str로부터 몇 번째 영업일이 월말 마지막 영업일인지(1 or 2).
    해당 없으면(3영업일 이상 남았거나 월 넘어가면) None.
    18개월 백테스트(팀장님 MVNO MNP 영업일수 테이블 검증 과정에서 발견):
    월말 마지막영업일 D-1 bw비율 평균 1.148(n=21), D-2 평균 1.134(n=19) -
    평시(1.0) 대비 유의미하게 높은 "월마감 전 막판 가입 몰림" 패턴 확인.
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    if is_zero_day(date_str) or _is_holiday(date_str):
        return None
    cur = d
    biz_count = 0
    for _ in range(10):
        cur += timedelta(days=1)
        if cur.month != d.month:
            return None
        cds = cur.strftime('%Y-%m-%d')
        if is_zero_day(cds) or _is_holiday(cds):
            continue
        biz_count += 1
        if _is_month_end_bizday(cds):
            return biz_count
        if biz_count >= 2:
            return None
    return None


def _get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


def _get_week_of_month(d: datetime) -> int:
    """월 내 주차 (1~5)"""
    return (d.day - 1) // 7 + 1


def _holiday_structure(date_str: str) -> str:
    """
    공휴일 구조 분류 (K-NN 매칭 조건)
    none / before_single / before_multi / after / month_end / month_start /
    before_month_end1 / before_month_end2
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    tomorrow  = (d + timedelta(days=1)).strftime('%Y-%m-%d')
    d2        = (d + timedelta(days=2)).strftime('%Y-%m-%d')
    yesterday = (d - timedelta(days=1)).strftime('%Y-%m-%d')

    # ★ 월말 마지막 영업일 우선 체크 (before_single보다 우선)
    if _is_month_end_bizday(date_str):
        return 'month_end'
    # [수정 20261001] 월초(1~2일) 프리미엄 - 22개월 실측 백테스트 결과 1일
    # 평균 bw비율 1.240, 2일 1.201, 3일부터 1.007로 평시 복귀(실무자 지적:
    # "월초는 영업일수를 더 줬던 것 같다"). 기존엔 요일+주차(±1) 매칭이라
    # 2주차 동요일 등 평시 데이터와 섞여 희석됨(10/1 K-NN 1.002로 과소예측).
    # month_end와 동일하게 요일 무관, 과거 월초 1~2일끼리 매칭.
    if d.day in (1, 2):
        return 'month_start'
    # [추가 20261002] 월말 마지막영업일 D-1/D-2: _bizdays_until_month_end() 백테스트 근거 참조
    d_before_end = _bizdays_until_month_end(date_str)
    if d_before_end == 1:
        return 'before_month_end1'
    elif d_before_end == 2:
        return 'before_month_end2'
    # [수정 20261001] before/after 판정이 is_zero_day()(일요일·설추석 당일)만
    # 체크해서 "영업은 하지만 줄어드는 공휴일"(개천절 대체휴무, 한글날 등)을
    # 놓치고 있었음 - 실측: 10/6(화, 전날 10/5 개천절 대체휴무)이 'none'으로
    # 분류됨(실무자 지적으로 발견). _is_holiday()도 함께 체크하도록 수정.
    tomorrow_off  = is_zero_day(tomorrow) or _is_holiday(tomorrow)
    d2_off        = is_zero_day(d2) or _is_holiday(d2)
    yesterday_off = is_zero_day(yesterday) or _is_holiday(yesterday)
    if tomorrow_off and d2_off:
        return 'before_multi'
    elif tomorrow_off:
        return 'before_single'
    elif yesterday_off:
        return 'after'
    return 'none'


def _get_knn_similar_days(date_str: str, top_n: int = 10) -> list:
    """
    [v3.1] K-NN: Firestore에서 유사 과거일 조회
    매칭 조건:
      - 일반 영업일: 같은 요일 + 같은 주차(±1) + 유사 공휴일 구조
      - 영업 공휴일: 요일 무관, 과거 토요일·공휴일(영업일) 데이터로 매칭
    가중치: 최근 3개월×3, 3~9개월×2, 9개월+×1
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()
    week = _get_week_of_month(d)
    hol_struct = _holiday_structure(date_str)
    is_biz_holiday = _is_holiday(date_str) and not is_zero_day(date_str)
    cutoff = (d - timedelta(days=548)).strftime('%Y-%m-%d')  # 약 18개월

    try:
        db = _get_db()
        docs = (db.collection('ktoa_daily')
                .where('date', '>=', cutoff)
                .where('date', '<', date_str)
                .stream())

        candidates = []
        for doc in docs:
            dd = datetime.strptime(doc.id, '%Y-%m-%d')

            if is_biz_holiday:
                # 영업 공휴일: 과거 토요일 or 영업 공휴일만 참고
                doc_is_sat = dd.weekday() == 5
                doc_is_biz_hol = _is_holiday(doc.id) and not is_zero_day(doc.id)
                if not (doc_is_sat or doc_is_biz_hol):
                    continue
            elif hol_struct == 'month_end':
                # ★ 월말 마지막 영업일: 과거 월말 영업일끼리 매칭
                # [수정 20261002] 요일 무관 매칭이 평일 월말(백테스트 평균 1.463)과
                # 토요일 월말(평균 0.899)을 섞어서, 월말이 토요일인 달에도 평일
                # 수준으로 과대예측하는 버그 발견(10/31 실측 1.293, 팀장님 manual
                # 0.9). 요일타입(평일/토요일) 일치 샘플만 쓰도록 하드필터 추가 -
                # 표본 부족시 calc_bw_ai()가 자동으로 테이블 폴백(요일별 가중 적용됨)
                if not _is_month_end_bizday(doc.id):
                    continue
                if (dd.weekday() == 5) != (wd == 5):
                    continue
            elif hol_struct == 'month_start':
                # ★ 월초 1~2일: 과거 월초 1~2일끼리 매칭 (요일 무관)
                if dd.day not in (1, 2):
                    continue
            elif hol_struct in ('before_month_end1', 'before_month_end2'):
                # [추가 20261002] 월말 마지막영업일 D-1/D-2: 요일 무관, 같은
                # D-n 거리의 과거 샘플끼리 매칭 (_bizdays_until_month_end 백테스트 근거)
                if _bizdays_until_month_end(doc.id) != (1 if hol_struct == 'before_month_end1' else 2):
                    continue
            elif hol_struct in ('before_single', 'before_multi', 'after'):
                # [수정 20261001] 연휴 전/후: 같은 요일 + 주차(±1) 제한을 쓰면
                # 과거 "같은 요일 + 공휴일 연휴 구조" 샘플이 특정 월의 특정
                # 주차에만 존재해서 거의 항상 매칭 범위 밖으로 빠짐 - 그 결과
                # hol_match(구조 일치 가중치)가 사실상 전부 0.6으로 깔려서
                # "연휴 전/후" 보정 자체가 평균에 반영되지 않는 문제가 있었음
                # (실측: 10/6 화요일 K-NN이 평범한 화요일과 다를 바 없는 0.982로
                # 나옴). 주차 제한을 풀고 같은 요일 전체 이력(최대 18개월)에서
                # 찾게 해서, 드물게 있는 진짜 "연휴 전/후" 같은요일 샘플이
                # hol_match=1.0으로 제대로 가중되도록 함.
                if dd.weekday() != wd:
                    continue
            else:
                # 일반 영업일: 같은 요일 + 주차(±1)
                if dd.weekday() != wd:
                    continue
                doc_week = _get_week_of_month(dd)
                if abs(doc_week - week) > 1:
                    continue

            data = doc.to_dict()
            bw_perf = data.get('bw_performance')
            if not bw_perf or float(bw_perf) <= 0:
                continue

            # 공휴일 구조 유사도
            doc_hol = _holiday_structure(doc.id)
            hol_match = 1.0 if doc_hol == hol_struct else 0.6

            if is_biz_holiday:
                # [수정 20261002] 영업공휴일과 토요일은 수준이 다름(18개월
                # 백테스트: 영업공휴일 평균 0.554 vs 토요일 테이블기준 0.658,
                # +18%). 둘 다 doc_hol='none'으로 같이 묶여 hol_match=1.0이던
                # 문제 - 진짜 과거 영업공휴일 샘플에 더 높은 가중치 부여
                hol_match *= 1.0 if doc_is_biz_hol else 0.6

            # 시간 가중치 (최신 우선)
            days_ago = (d - dd).days
            if days_ago <= 90:
                time_weight = 3.0
            elif days_ago <= 270:
                time_weight = 2.0
            else:
                time_weight = 1.0

            candidates.append({
                'date':   doc.id,
                'bw':     float(bw_perf),
                'weight': time_weight * hol_match,
            })

        candidates.sort(key=lambda x: x['weight'], reverse=True)
        return candidates[:top_n]

    except Exception as e:
        log.warning(f"K-NN 조회 실패: {e}")
        return []


def _calc_knn_bw(candidates: list) -> Optional[float]:
    """K-NN 후보들의 가중 평균 계산"""
    if not candidates:
        return None
    total_w = sum(c['weight'] for c in candidates)
    if total_w <= 0:
        return None
    weighted = sum(c['bw'] * c['weight'] for c in candidates)
    return round(weighted / total_w, 3)


def _get_prev_week_mvno_in(date_str: str) -> int:
    """전주 동요일 MVNO IN 계 조회 (Gemini 컨텍스트용)"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        prev_week = (d - timedelta(days=7)).strftime('%Y-%m-%d')
        db = _get_db()
        doc = db.collection('ktoa_daily').document(prev_week).get()
        if doc.exists:
            return doc.to_dict().get('mvno_in', {}).get('계', 0) or 0
    except Exception:
        pass
    return 0


def _call_gemini_bw(date_str: str, knn_result: float,
                    candidates: list, prev_week_mvno: int) -> Optional[float]:
    """
    [v3.0] Gemini에게 bw 최종 판단 요청
    K-NN 결과 + 컨텍스트 → Gemini 종합 판단
    """
    try:
        import google.generativeai as genai
        key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
        if not key:
            return None
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        d = datetime.strptime(date_str, '%Y-%m-%d')
        wd_name = ['월', '화', '수', '목', '금', '토', '일'][d.weekday()]
        week = _get_week_of_month(d)
        hol_struct = _holiday_structure(date_str)
        hol_desc = {
            'none':          '주변 공휴일 없음',
            'before_single': '내일 단일 공휴일',
            'before_multi':  '내일부터 연속 공휴일',
            'after':         '어제 공휴일',
            'month_end':     '★ 월말 마지막 영업일 (번호이동 몰림 현상, 단 평일이면 bw 평균 1.46배로 매우 높고 '
                              '토요일이면 0.9배 수준으로 평일보다 훨씬 낮음 - 오늘 요일 꼭 고려할 것)',
            'month_start':   '★ 월초 1~2일 (실측상 bw 평균 1.2배 높음, 3일부터 평시 복귀)',
            'before_month_end1': '★ 월말 마지막영업일 하루 전 (막판 가입 몰림, 실측상 bw 평균 1.15배)',
            'before_month_end2': '★ 월말 마지막영업일 이틀 전 (막판 가입 몰림 시작, 실측상 bw 평균 1.13배)',
        }.get(hol_struct, '없음')

        similar_summary = '\n'.join([
            f"  {c['date']}({['월','화','수','목','금','토'][datetime.strptime(c['date'],'%Y-%m-%d').weekday()]}): "
            f"bw={c['bw']:.3f} (가중치{c['weight']:.1f})"
            for c in candidates[:5]
        ])

        prompt = f"""당신은 MVNO 알뜰폰 시장 영업일수(bw) 예측 전문가입니다.
bw = 당일 MVNO IN ÷ 월 일평균 MVNO IN (시장 활동성 지수)
bw > 1.0: 평균보다 활발, bw < 1.0: 평균보다 저조
영업일 범위: 평일 0.8~1.4, 토요일 0.4~0.8

예측 대상: {date_str} ({wd_name}요일, {week}주차)
공휴일 구조: {hol_desc}
전주 동요일 MVNO IN: {prev_week_mvno:,}건 (0이면 데이터 없음)
K-NN 가중평균 결과: {knn_result:.3f}

유사 과거일 top5:
{similar_summary}

위 정보를 종합해서 {date_str}의 bw를 예측하세요.
소수점 3자리 숫자만 출력 (예: 1.085). 다른 텍스트 없이 숫자만."""

        # [수정 20261001] gemini-2.5-flash는 기본적으로 reasoning(thinking) 토큰을
        # 먼저 소비하는 모델인데, 기존 max_output_tokens=20은 thinking 중간에
        # 잘려서 응답이 멀티파트가 되거나("response.text quick accessor...는
        # simple text에서만 동작" 에러로 매번 K-NN 폴백) 혹은 사고가 끝나기도
        # 전에 억지로 잘려 의미없는 "1.0"만 찍히는 문제가 있었음(실측: 10월
        # bw_ai_prev 8개 날짜가 K-NN 입력값(1.002~1.174)과 무관하게 전부
        # 정확히 1.0으로 저장 - 실무자 지적처럼 월초 bw가 실제보다 낮게
        # 나온 원인). 토큰 여유를 늘리고, quick accessor 대신 parts를 순회해서
        # thought 파트를 건너뛰고 실제 답변 텍스트만 추출하도록 수정.
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1, max_output_tokens=300
            )
        )
        text = ''
        for part in resp.candidates[0].content.parts:
            if getattr(part, 'thought', False):
                continue
            if getattr(part, 'text', None):
                text += part.text
        text = text.strip()
        if not text:
            log.warning(f"Gemini bw 응답 비어있음 (K-NN 폴백): {date_str}")
            return None
        val = float(text)
        if 0.3 <= val <= 2.0:
            log.info(f"Gemini bw 예측: {date_str} → {val} (K-NN: {knn_result})")
            return round(val, 3)
        return None
    except Exception as e:
        log.warning(f"Gemini bw 예측 실패 (K-NN 폴백): {e}")
        return None


def _calc_bw_fallback(date_str: str) -> float:
    """K-NN + Gemini 모두 실패 시 테이블 기반 폴백"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()
    if is_zero_day(date_str):   # 일요일 or 설/추석 당일만 0
        return 0.0
    # 영업 공휴일(근로자의날·어린이날 등): 토요일 수준으로 처리
    if _is_holiday(date_str):
        return 0.6

    table = _BW_TABLE_FALLBACK.get(d.month, _BW_TABLE_FALLBACK[4])
    bw = table[wd]
    week = _get_week_of_month(d)
    bw *= _WEEK_FACTOR.get(week, _WEEK_FACTOR[4])[wd]

    hol_struct = _holiday_structure(date_str)
    if hol_struct == 'before_multi':
        bw *= 0.75
    elif hol_struct == 'before_single':
        bw *= 0.91
    elif hol_struct == 'after':
        if wd == 4:   bw *= 1.23
        elif wd == 1: bw *= 1.11
        # [2026-09-22] 월요일 배수 0.95(감소)는 방향이 반대였음 - 실무자 시뮬레이션
        # 확인 결과(2025년 10월 연휴 직후) 월요일 rush가 평소 대비 최대 2배까지
        # 나타남. 매번 그 정도는 아니겠지만 최소한 증가 방향으로 반영
        elif wd == 0: bw *= 1.35
    elif hol_struct == 'month_end':
        bw *= 1.25   # ★ 월말 마지막 영업일 가중 (번호이동 몰림)
    elif hol_struct == 'month_start':
        bw *= 1.2    # ★ 월초 1~2일 가중 (22개월 실측 평균 1.2배, 3일부터 평시 복귀)
    elif hol_struct == 'before_month_end1':
        bw *= 1.148  # [추가 20261002] 월말 D-1 가중 (18개월 백테스트 평균, n=21)
    elif hol_struct == 'before_month_end2':
        bw *= 1.134  # [추가 20261002] 월말 D-2 가중 (18개월 백테스트 평균, n=19)

    return round(bw, 3)


def calc_bw_ai(date_str: str) -> float:
    """
    [v3.0] K-NN + Gemini 하이브리드 bw 예측

    흐름:
      1. K-NN: Firestore 유사 과거일 가중 평균
      2. Gemini: K-NN 결과 + 컨텍스트 종합 판단
      3. 폴백: K-NN 단독 → 테이블 기반

    데이터 쌓일수록 자동 정확도 향상 (코드 수정 불필요)
    Returns 0.0 if 일요일/공휴일
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    if is_zero_day(date_str):   # 일요일 or 설/추석 당일만 0
        return 0.0

    # 1단계: K-NN 유사 과거일 조회
    candidates = _get_knn_similar_days(date_str, top_n=10)
    knn_result = _calc_knn_bw(candidates)

    if knn_result and len(candidates) >= 3:
        # 2단계: Gemini 종합 판단
        prev_week_mvno = _get_prev_week_mvno_in(date_str)
        gemini_result = _call_gemini_bw(date_str, knn_result,
                                         candidates, prev_week_mvno)
        if gemini_result:
            return gemini_result
        # Gemini 실패 → K-NN 단독 사용
        log.info(f"K-NN 단독 사용: {date_str} → {knn_result}")
        return knn_result

    # 3단계: 데이터 부족 → 테이블 폴백
    fallback = _calc_bw_fallback(date_str)
    log.info(f"테이블 폴백: {date_str} → {fallback} (K-NN 샘플 {len(candidates)}개)")
    return fallback


def calc_bw_performance_mvno(date_str: str, mvno_in_total: int,
                              month_avg_mvno_in: float) -> float:
    """[v2.0] MVNO IN 기반 bw_performance 계산"""
    if is_zero_day(date_str) or month_avg_mvno_in <= 0:
        return 0.0
    return round(mvno_in_total / month_avg_mvno_in, 3)


def get_month_avg_mvno_in(year: int, month: int, up_to_day: int) -> float:
    """월초~up_to_day까지 MVNO IN 일평균 (영업일 기준)"""
    try:
        db = _get_db()
        total_mvno = 0
        biz_days = 0
        for day in range(1, up_to_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            doc = db.collection('ktoa_daily').document(ds).get()
            if not doc.exists:
                continue
            data = doc.to_dict()
            bw = get_bw_final(ds, data)
            if bw <= 0:
                continue
            mvno = data.get('mvno_in', {}).get('계', 0) or 0
            if mvno > 0:
                total_mvno += mvno
                biz_days += 1
        return round(total_mvno / biz_days, 1) if biz_days > 0 else 0.0
    except Exception as e:
        log.warning(f"월평균 MVNO IN 조회 실패: {e}")
        return 0.0


def get_bw_final(date_str: str, firestore_data: Optional[dict] = None) -> float:
    """
    [v3.0] 우선순위 기반 최종 영업일수 반환
    bw_ai_prev(최신예측) > bw_manual > bw_ai_w3 > bw_ai_w2 > bw_ai_w1 > calc_bw_ai()
    """
    if is_zero_day(date_str):
        return 0.0

    if firestore_data is None:
        try:
            db = _get_db()
            doc = db.collection('ktoa_daily').document(date_str).get()
            firestore_data = doc.to_dict() if doc.exists else {}
        except Exception as e:
            log.warning(f"get_bw_final 조회 실패: {e}")
            firestore_data = {}

    # [v3.0] bw_ai_prev 최우선 (가장 최신 예측값)
    for field in ['bw_ai_prev', 'bw_manual', 'bw_ai_w3', 'bw_ai_w2', 'bw_ai_w1']:
        val = firestore_data.get(field)
        if val is not None and float(val) > 0:
            return float(val)

    return calc_bw_ai(date_str)


def get_month_bw_map(year: int, month: int) -> dict:
    """월 전체 날짜별 bw_final 맵 (date 필드 없는 문서도 포함)"""
    from calendar import monthrange
    last_day = monthrange(year, month)[1]

    try:
        db = _get_db()
        fs_data = {}
        for day in range(1, last_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            doc = db.collection('ktoa_daily').document(ds).get()
            if doc.exists:
                fs_data[ds] = doc.to_dict()
    except Exception as e:
        log.warning(f"get_month_bw_map 실패: {e}")
        fs_data = {}

    return {
        f"{year:04d}-{month:02d}-{day:02d}":
        get_bw_final(f"{year:04d}-{month:02d}-{day:02d}",
                     fs_data.get(f"{year:04d}-{month:02d}-{day:02d}", {}))
        for day in range(1, last_day + 1)
    }


def calc_remaining_bw(year: int, month: int, today_day: int) -> float:
    """today_day 다음날부터 월말까지 잔여 영업일수 합산"""
    from calendar import monthrange
    bw_map = get_month_bw_map(year, month)
    last_day = monthrange(year, month)[1]
    total = sum(
        bw_map.get(f"{year:04d}-{month:02d}-{day:02d}", 0.0)
        for day in range(today_day + 1, last_day + 1)
    )
    return round(total, 3)


def save_bw_to_daily(date_str: str, bw_field: str, bw_value: float) -> bool:
    """ktoa_daily/{date_str}에 bw 필드 저장 (date 필드 자동 추가)"""
    valid = {'bw_ai_prev', 'bw_ai_prev_old', 'bw_ai_w1', 'bw_ai_w2', 'bw_ai_w3',
             'bw_manual', 'bw_performance', 'bw_final'}
    if bw_field not in valid:
        log.error(f"유효하지 않은 bw 필드: {bw_field}")
        return False
    try:
        db = _get_db()
        db.collection('ktoa_daily').document(date_str).set(
            {bw_field: bw_value,
             'date': date_str,
             f'{bw_field}_updated_at': datetime.utcnow()},
            merge=True)
        log.info(f"저장: ktoa_daily/{date_str}.{bw_field} = {bw_value}")
        return True
    except Exception as e:
        log.error(f"bw 저장 실패: {e}")
        return False


def generate_month_bw_ai_prev(year: int, month: int) -> int:
    """
    [v3.0] 월 전체 bw_ai_prev 사전 계산 → Firestore 저장 (K-NN+Gemini)

    [수정 20261002] bw_ai_prev(패턴기반)의 월 합계가 구조적으로 영업일수 근처로
    수렴하는데(정의상 "그 달 영업일 평균 대비 상대적 비중"), bw_manual(실무자
    수기 테이블)에 월 전체 "총량 성장" 가정이 깔려있으면 두 숫자가 애초에 다른
    것을 측정해서 격차가 남는 문제 발견(10월 사례: AI 26.6 vs 팀장님 manual 29.0,
    +7.4%). 날짜별 "모양"은 K-NN/Gemini가 맞추게 그대로 두고, bw_manual이 있으면
    그 월 합계에 맞춰 전체를 스케일하는 성장계수를 적용하도록 변경.
    원래(스케일 전) 패턴값은 bw_ai_prev_old에 별도 보관해서 두 버전을 항상
    비교 가능하게 함 - 성장계수 가정이 실측과 안 맞으면 bw_ai_prev_old 기준으로
    되돌릴 수 있음.
    """
    from calendar import monthrange
    last_day = monthrange(year, month)[1]

    db = _get_db()
    raw = {}
    manual = {}
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        raw[ds] = calc_bw_ai(ds)
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            m = doc.to_dict().get('bw_manual')
            if m is not None and float(m) > 0:
                manual[ds] = float(m)

    # 성장계수: bw_manual과 raw가 둘 다 있는 날이 충분할 때만 적용 (표본 10일 미만이면 1.0)
    paired = [(raw[ds], manual[ds]) for ds in manual if raw.get(ds, 0) > 0]
    if len(paired) >= 10:
        raw_sum = sum(r for r, _ in paired)
        manual_sum = sum(m for _, m in paired)
        factor = round(manual_sum / raw_sum, 4) if raw_sum > 0 else 1.0
        factor = max(0.8, min(1.3, factor))  # 과도한 보정 방지
    else:
        factor = 1.0
    log.info(f"{year}-{month:02d} bw 성장계수: {factor} (bw_manual 표본 {len(paired)}일)")

    saved = 0
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        r = raw[ds]
        save_bw_to_daily(ds, 'bw_ai_prev_old', r)
        scaled = round(r * factor, 3) if r > 0 else 0.0
        if save_bw_to_daily(ds, 'bw_ai_prev', scaled):
            saved += 1
    log.info(f"{year}-{month:02d} bw_ai_prev(v3.1, 성장계수 {factor}) {saved}/{last_day}일 저장")
    return saved