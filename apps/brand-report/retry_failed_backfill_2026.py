"""
retry_failed_backfill_2026.py
2026년 Context DB 백필 1차 실행(backfill_brand_context_2026.py)에서 실패한
항목만 재시도. 실패 사유는 전부 '_UnaryStreamMultiCallable' object has no
attribute '_retry' - Firestore 클라이언트의 일시적 오류로 추정, 재시도로
대부분 해결됨. 텔레그램 발송 없음.

사용법 (brand-report/ 폴더에서):
    python3 retry_failed_backfill_2026.py

[수정 이력]
- v1.0 (2026-08-27): 최초 작성 - 1차 백필 로그 기준 실패 목록 반영
  (daily 3건, weekly 2건, monthly 1건)
"""

from calendar import monthrange
from datetime import date

FAILED_DAYS = [
    date(2026, 2, 18),
    date(2026, 7, 1),
    date(2026, 8, 3),
]

# (year, month, week, monday, saturday)
FAILED_WEEKS = [
    (2026, 4, 4, date(2026, 4, 20), date(2026, 4, 25)),
    (2026, 8, 1, date(2026, 8, 3), date(2026, 8, 8)),
]

FAILED_MONTHS = [5]  # 2026년


def retry_days():
    from ktoa_mvno_report import build_all_reports

    for d in FAILED_DAYS:
        try:
            build_all_reports(d)
            print(f"[daily] {d} 재시도 성공", flush=True)
        except Exception as e:
            print(f"[daily] {d} 재시도 실패: {e}", flush=True)


def retry_weeks():
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period
    from ktoa_mvno_period_report import build_weekly_report

    db = _get_db()
    for year, month, week, monday, sat in FAILED_WEEKS:
        try:
            agg = aggregate_period(db, monday, sat)
            build_weekly_report(db, agg, year, month, week, monday, sat)
            print(f"[weekly] {year}년{month}월{week}주차 재시도 성공", flush=True)
        except Exception as e:
            print(f"[weekly] {year}년{month}월{week}주차 재시도 실패: {e}", flush=True)


def retry_months():
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period
    from ktoa_mvno_period_report import build_monthly_report

    db = _get_db()
    for month in FAILED_MONTHS:
        year = 2026
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
        try:
            agg = aggregate_period(db, period_start, period_end)
            build_monthly_report(db, agg, year, month, period_start, period_end)
            print(f"[monthly] {year}-{month:02d} 재시도 성공", flush=True)
        except Exception as e:
            print(f"[monthly] {year}-{month:02d} 재시도 실패: {e}", flush=True)


if __name__ == "__main__":
    retry_days()
    retry_weeks()
    retry_months()
    print("=== 재시도 종료 ===", flush=True)
