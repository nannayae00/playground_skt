"""
mvno_period_utils.py  v1.2
작성일: 2026-08-03

[수정 이력]
v1.2 (2026-08-07): get_bw_for_date()에 use_formula_fallback 파라미터 추가
  (bw_lite.py v1.1과 연동) - 그 달 전체에 실측 bw 데이터가 없는 과거
  구간(2016~2023 등) 백필용. 기본값 False로 기존 동작 그대로 유지.
v1.1 (2026-08-07): import 대상을 bw_engine.py(ktoa-collector 소유, brand-report/
  배포에 없어서 ModuleNotFoundError 발생) 대신 경량판 bw_lite.py로 변경.
  bw_engine.py 전체(K-NN+Gemini 예측 포함)를 중복 배치하는 대신 필요한 두
  함수만 재작성한 버전 사용 - 이유는 bw_lite.py 파일 헤더 참고.
v1.0 (2026-08-03): 최초 작성. 주간/월간 리포트 공용 유틸 (설계문서
  주간월간_리포트_설계_20260803.md 2/3/5번 그대로 구현).
  - week1_monday() / week_of_month(): 주차 라벨링 규칙 (검증 완료 로직 이식)
  - last_week_range(): 오늘(월요일 실행 기준) 기준 "지난주"(월~토) 범위
  - is_month_end(): 월말 판단 (기존 main.py `_is_month_end` 로직 재사용,
    bw_engine.is_zero_day 사용)
  - weighted_avg(): sum(값)/sum(bw) 가중평균 공식 (design 5번 최종 확정 방식)
  - get_bw_for_date(): bw_performance 우선, 없으면 get_bw_final() 우선순위로 대체
"""

from datetime import date, timedelta
from calendar import monthrange

from bw_lite import is_zero_day, get_bw_final


def week1_monday(year: int, month: int) -> date:
    """그 달의 1주차가 시작하는 월요일. 1일이 토/일이면 다음 월요일."""
    first = date(year, month, 1)
    wd = first.weekday()  # 월=0 ... 일=6
    if wd >= 5:
        days_to_next_monday = 7 - wd
        return first + timedelta(days=days_to_next_monday)
    return first - timedelta(days=wd)


def week_of_month(target_date: date):
    """
    target_date가 속한 주(월~토)의 (year, month, week_num, monday, saturday) 반환.
    검증된 사례: 2026-07-27(월)~2026-08-01(토) = 2026년 7월 5주차,
                2026-08-03(월)~2026-08-08(토) = 2026년 8월 1주차.
    """
    weekday = target_date.weekday()
    monday = target_date - timedelta(days=weekday)
    saturday = monday + timedelta(days=5)

    y, m = monday.year, monday.month
    w1_mon = week1_monday(y, m)
    if monday < w1_mon:
        # 이전 달 1주차 구간에 속함
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
        w1_mon = week1_monday(y, m)

    week_num = (monday - w1_mon).days // 7 + 1
    return y, m, week_num, monday, saturday


def last_week_range(today: date):
    """
    today(=실행일, 통상 월요일) 기준 "지난주"(월~토) 범위를 반환.
    트리거 조건(대상일=어제=일요일)에서 today는 어제+1일, 즉 실행 당일.
    """
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_saturday = last_monday + timedelta(days=5)
    return last_monday, last_saturday


def current_business_week_range(target_date: date):
    """
    [버그수정, Claude] target_date(=어제, 주간요약 트리거 판단에 쓰인 날짜) 기준
    "이번 주"(월~토) 범위를 반환.

    기존 last_week_range(today)는 "오늘=월요일 실행"만 가정하고 today의 요일과
    무관하게 무조건 "오늘이 속한 주의 지난주"를 반환했음. run_mvno_brand_job.py의
    주간요약 트리거는 (1) 어제=일요일 (2) 어제 실적합계=0(공휴일 등) 두 가지인데,
    last_week_range(today_kst)를 그대로 넘기면 (2) 케이스에서 today_kst가 월요일이
    아닐 수 있어(예: 토요일에 실행) "지난주"가 실제로는 2주 전을 가리키고 정작
    직전 실적이 있는 주는 건너뛰는 문제가 있었음(사장님 지적: "기간에 맞지않은
    메시지가 왔네" - 2026-09-26 실행, 최신실적 09-25인데 09-14~09-19 리포트 발송됨).

    target_date가 일요일이면(월~토 범위 밖 요일이므로) 그 전날(토)이 속한, 즉
    방금 끝난 주를 반환 - 기존 "일요일 트리거 → 지난주" 의도와 동일한 결과.
    target_date가 평일/토요일이면(실적0 폴백 케이스) target_date가 속한 "이번
    주"(직전 실적이 반영된 주)를 그대로 반환.
    """
    anchor = target_date - timedelta(days=1) if target_date.weekday() == 6 else target_date
    monday = anchor - timedelta(days=anchor.weekday())
    saturday = monday + timedelta(days=5)
    return monday, saturday


def is_month_end(target_date: date) -> bool:
    """
    target_date부터 그 달 말일까지 남은 날 중 영업일(0건 아닌 날)이
    하나도 없으면 True (기존 main.py `_is_month_end` 로직 재사용).
    """
    y, m, d = target_date.year, target_date.month, target_date.day
    last_day = monthrange(y, m)[1]
    return not any(
        not is_zero_day(f"{y:04d}-{m:02d}-{dd:02d}")
        for dd in range(d + 1, last_day + 1)
    )


def weighted_avg(value_sum: float, bw_sum: float) -> float:
    """sum(값)/sum(bw) 가중평균. bw_sum이 0이면 0 반환."""
    if not bw_sum:
        return 0.0
    return round(value_sum / bw_sum, 1)


def get_bw_for_date(date_str: str, daily_doc: dict | None, use_formula_fallback: bool = False) -> float:
    """
    ktoa_daily/{date} 문서의 bw_performance 우선 사용.
    없으면 get_bw_final()과 동일 우선순위로 대체:
    bw_ai_prev > bw_manual > bw_ai_w3 > bw_ai_w2 > bw_ai_w1
    (설계 5번: 이미 지난 기간 집계이므로 예측치보다 실측치를 우선 사용하기로 확정)
    그 이하로도 없으면: use_formula_fallback=True인 경우에만
    bw_lite.estimate_bw_formula()로 대체(그 달 전체에 실측 bw가 없는 과거
    구간 전용 - 2026-08-07 사용자 확정 공식). 기본은 기존처럼 경고+0.0.
    daily_doc은 호출측에서 미리 벌크 조회해서 넘기는 것을 전제(N+1 쿼리 방지).
    """
    doc = daily_doc or {}
    bw_perf = doc.get("bw_performance")
    if bw_perf is not None and float(bw_perf) > 0:
        return float(bw_perf)
    return get_bw_final(date_str, doc, use_formula_fallback=use_formula_fallback)
