"""
bw_lite.py  v1.1
작성일: 2026-08-07

[수정 이력]
v1.1 (2026-08-07): "bw 데이터가 아예 없는 달"(2016~2023 등 과거 확장 구간
  대상) 전용 수동 추정 공식 추가(사용자 확정, 2026-08-07). get_bw_final()에
  use_formula_fallback 파라미터 신설 - True로 부르면 실측 bw 필드가 전부
  없을 때 경고+0.0 대신 estimate_bw_formula()로 추정치를 돌려줌. 호출측
  (ktoa_mvno_period_aggregator.py)이 "그 달 전체에 실측 bw가 하나도 없는
  경우"에만 이 플래그를 True로 넘기도록 설계 - 최근 달처럼 대부분은 실측
  있고 공휴일 하루 정도만 빠진 경우엔 기존처럼 그 날만 제외(0.0)하는 게
  맞다고 판단(사용자 확정: "bw없는 달만 이 로직을 사용").

  공식(사용자 확정):
    - 일요일: 0 (기존 is_zero_day와 동일 취급 - 집계에서 제외)
    - 공휴일 또는 토요일: 0.6
    - 그 달의 첫 영업일(공휴일/토·일 아닌 첫 날): 1.4
    - 공휴일 다음날인 평일: 1.1
    - 그 외 평일: 월요일 1.2 / 수요일 1.1 / 화·목·금 1.0
  우선순위: 일요일 > 공휴일/토요일 > 월 첫 영업일 > 공휴일 다음날 > 요일별 기본값
  (월 첫 영업일이 동시에 "공휴일 다음날"이 될 수 있는 경우 - 예: 1일이
  공휴일이라 3일이 첫영업일이면서 2일 공휴일의 다음날이기도 한 경우 -
  첫영업일 규칙이 우선함)

  공휴일 판정은 `holidays` 패키지(PyPI, KR 로케일)를 사용 - 대체공휴일
  규칙까지 포함해서 검증된 라이브러리로 정확히 계산(직접 8년치를 손으로
  입력하면 실수 위험이 커서 라이브러리로 대체하기로 확정). requirements.txt에
  `holidays` 추가 필요.

v1.0 (2026-08-07): 최초 작성.
  배경: brand-report/ 배포 시 `ModuleNotFoundError: No module named 'bw_engine'`
  발생 - bw_engine.py는 ktoa-collector 쪽 파일이라 brand-report/에 없었음.
  단순히 bw_engine.py(553줄, K-NN+Gemini 하이브리드 예측 포함)를 통째로
  복사하면 두 가지 문제:
    (1) 두 파일을 앞으로 계속 동기화해야 하는 유지보수 부담(사용자 지적)
    (2) get_bw_final()의 최후 fallback인 calc_bw_ai()가 Gemini API + K-NN을
        호출하는데, 주간/월간 집계는 전부 "이미 지난 기간"만 다루므로
        (bw 필드는 매일 20시 마감 시 자동 저장 - bw_engine.py 설계 근거 참고)
        이 fallback까지 갈 일이 사실상 없어야 정상. 그런데도 통째로
        가져오면 백필처럼 대량 반복 호출 시 만에 하나 필드 누락된 날짜가
        있을 때 Gemini API를 수백 번 호출하게 되는 위험이 생김.
  해결: 필요한 두 함수(is_zero_day/get_bw_final)만 재작성하고, get_bw_final의
  fallback 체인 끝을 calc_bw_ai() 호출 대신 경고 로그 + 0.0 반환으로 끊음.

  ⚠️ 동기화 필요 지점은 딱 하나: _ZERO_HOLIDAYS(설날/추석 당일 날짜 목록,
  2024~2026 실측 검증된 "진짜 영업 0인 날"). 원본 bw_engine.py도 "연 1회
  수동 업데이트"라고 명시돼 있으므로, 그 타이밍에 이 파일의 _ZERO_HOLIDAYS도
  같이 갱신할 것. v1.1의 holidays 패키지 기반 공휴일 판정과는 별개 목적
  (_ZERO_HOLIDAYS는 "완전 제외", holidays 패키지는 "0.6 가중치 부여") -
  둘 다 필요하고 서로 대체 관계 아님.
"""

import logging
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Optional

import holidays as holidays_lib

log = logging.getLogger(__name__)

# bw_engine.py의 _ZERO_HOLIDAYS와 동일 값. 연 1회(공휴일 갱신 시) 원본과 함께 동기화할 것.
# (2024~2026만 실측 검증된 "영업 0일" - 그 이전 연도는 is_zero_day에서 일요일만 적용됨,
# 대신 estimate_bw_formula()가 공휴일을 0.6으로 별도 처리하므로 문제 없음)
_ZERO_HOLIDAYS = {
    # 설날 당일
    '2024-02-10', '2025-01-29', '2026-01-29',
    # 추석 당일
    '2024-09-17', '2025-10-06', '2026-09-25',
}

# estimate_bw_formula() 전용 공휴일 판정 - 2016~2026 넉넉하게 커버.
# holidays 패키지가 대체공휴일 규칙까지 반영해서 계산해줌.
_KR_HOLIDAYS = holidays_lib.KR(years=range(2016, 2027))


def is_zero_day(date_str: str) -> bool:
    """영업 0일: 일요일 또는 설날/추석 당일만 (bw_engine.py의 is_zero_day와 동일 로직/결과)."""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return d.weekday() == 6 or date_str in _ZERO_HOLIDAYS


def _is_public_holiday(date_str: str) -> bool:
    """holidays 패키지 기준 공휴일 여부 (대체공휴일 포함). estimate_bw_formula() 전용."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    return d in _KR_HOLIDAYS


def _first_bizday_of_month(year: int, month: int) -> str:
    """그 달의 첫 영업일(일요일도 공휴일도 아닌 첫 날) 날짜 문자열."""
    last_day = monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d = datetime.strptime(ds, '%Y-%m-%d')
        if d.weekday() == 6:  # 일요일
            continue
        if d.weekday() == 5 or _is_public_holiday(ds):  # 토요일/공휴일
            continue
        return ds
    return f"{year:04d}-{month:02d}-01"  # 이론상 도달 안 함(한 달에 영업일이 0일일 수 없음)


def estimate_bw_formula(date_str: str) -> float:
    """
    bw 실측/예측 데이터가 아예 없는 달(2016~2023 등) 전용 수동 추정 공식.
    (get_bw_final()이 use_formula_fallback=True일 때만 호출)
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    weekday = d.weekday()  # 월=0 ... 일=6

    if weekday == 6:
        return 0.0

    if weekday == 5 or _is_public_holiday(date_str):
        return 0.6

    if date_str == _first_bizday_of_month(d.year, d.month):
        return 1.4

    prev = d - timedelta(days=1)
    prev_str = prev.strftime('%Y-%m-%d')
    if prev.weekday() != 6 and (prev.weekday() == 5 or _is_public_holiday(prev_str)):
        # 전날이 토요일이면 원래 그 다음날은 일요일이라 이 분기 도달 자체가 안 됨 -
        # 여기 걸리는 건 사실상 "전날이 평일 공휴일"인 경우만.
        return 1.1

    weekday_map = {0: 1.2, 2: 1.1}  # 월요일=1.2, 수요일=1.1, 나머지(화/목/금)=1.0
    return weekday_map.get(weekday, 1.0)


def get_bw_final(
    date_str: str,
    firestore_data: Optional[dict] = None,
    use_formula_fallback: bool = False,
) -> float:
    """
    bw_engine.get_bw_final()의 경량판. 우선순위(bw_ai_prev > bw_manual >
    bw_ai_w3 > bw_ai_w2 > bw_ai_w1)까지는 원본과 완전히 동일한 로직.
    그 이하로 떨어지면(=필드가 전부 없음):
      - use_formula_fallback=True: estimate_bw_formula()로 추정치 반환
        (그 달 전체에 실측 bw가 없는 경우 - 호출측이 판단해서 넘김)
      - use_formula_fallback=False(기본): 경고 로그 + 0.0 반환(기존 동작 -
        최근 달처럼 대부분 실측 있고 특정 날짜만 빠진 경우)
    firestore_data는 호출측에서 이미 벌크 조회해서 넘기는 것을 전제로 함
    (N+1 쿼리 방지) - None으로 부르면 안 됨.
    """
    if is_zero_day(date_str):
        return 0.0

    data = firestore_data or {}
    for field in ['bw_ai_prev', 'bw_manual', 'bw_ai_w3', 'bw_ai_w2', 'bw_ai_w1']:
        val = data.get(field)
        if val is not None and float(val) > 0:
            return float(val)

    if use_formula_fallback:
        return estimate_bw_formula(date_str)

    log.warning(
        f"{date_str}: bw 필드 전부 없음(bw_ai_prev~w1) - calc_bw_ai() 미실행(bw_lite.py는 의도적으로 "
        f"이 fallback을 안 씀), 0.0 처리되어 이 날짜는 주간/월간 집계에서 제외됨. "
        f"자주 뜨면 ktoa_daily 문서에 bw 필드가 정상 저장되고 있는지 확인 필요."
    )
    return 0.0
