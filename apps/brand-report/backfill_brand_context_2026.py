"""
backfill_brand_context_2026.py
2026년 Context DB(ktoa_brand_context_daily/weekly/monthly) 백필 스크립트.

텔레그램 발송 없음 - build_all_reports()/build_weekly_report()/build_monthly_report()
자체가 텔레그램을 보내지 않고(send_telegram()/send_telegram_report()는 별도로
불러야만 발송됨), Context DB 저장은 이 함수들 내부에 이미 박혀있어서 호출만
하면 저장까지 같이 됨.

날짜 범위: daily는 2026-01-01~어제(KST) 전체. weekly/monthly는 "완결된"
주/달만 대상(진행 중인 이번 주·이번 달은 제외 - 기존 텔레그램 발송 로직과
동일한 기준).

사용법 (brand-report/ 폴더에서):
    python3 backfill_brand_context_2026.py                 # daily+weekly+monthly 전부
    python3 backfill_brand_context_2026.py --daily-only     # daily만
    python3 backfill_brand_context_2026.py --period-only    # weekly+monthly만

날짜당 사업자 130개+ 각각 4주 baseline을 Firestore에서 조회하는 구조라
daily 전체(1~8월, 약 240일)는 시간이 꽤 걸릴 수 있음. 백그라운드 실행 권장:
    nohup python3 backfill_brand_context_2026.py > backfill_2026.log 2>&1 &
    tail -f backfill_2026.log

[수정 이력]
- v1.0 (2026-08-27): 최초 작성
"""

import argparse
import time
from calendar import monthrange
from datetime import date, timedelta, timezone, datetime

KST = timezone(timedelta(hours=9))
YEAR = 2026


def get_yesterday_kst() -> date:
    return (datetime.now(KST) - timedelta(days=1)).date()


def _date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def backfill_daily(start: date, end: date) -> None:
    from ktoa_mvno_report import build_all_reports

    days = list(_date_range(start, end))
    print(f"[daily] 백필 시작: {start} ~ {end} ({len(days)}일)", flush=True)
    for i, d in enumerate(days, 1):
        t0 = time.time()
        try:
            build_all_reports(d)
            print(f"[daily] ({i}/{len(days)}) {d} 완료 ({time.time() - t0:.1f}초)", flush=True)
        except Exception as e:
            print(f"[daily] ({i}/{len(days)}) {d} 실패: {e}", flush=True)
    print("[daily] 백필 종료\n", flush=True)


def _completed_week_mondays(yesterday: date):
    """YEAR년의 "완결된"(토요일까지 이미 지난) 주만, 실제 물리적 월요일 순서대로
    생성. week_of_month()로 연/월/주차 라벨을 다시 계산해서 YEAR년 라벨만 채택
    (예: 1/1이 목요일이면 그 주의 월요일은 2025년 12월이라 라벨도 2025년으로
    나와서 자동으로 걸러짐 - mvno_period_utils 규칙과 일치)."""
    from mvno_period_utils import week_of_month

    d = date(YEAR, 1, 1)
    d -= timedelta(days=d.weekday())  # 그 주의 월요일로 이동
    seen = set()
    while d + timedelta(days=5) <= yesterday:  # 토요일까지 이미 지난 주만
        year, month, week, _, _ = week_of_month(d)
        key = (year, month, week)
        if year == YEAR and key not in seen:
            seen.add(key)
            yield d, year, month, week
        d += timedelta(days=7)


def backfill_weekly(yesterday: date) -> None:
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period
    from ktoa_mvno_period_report import build_weekly_report

    db = _get_db()
    entries = list(_completed_week_mondays(yesterday))
    print(f"[weekly] 백필 시작: {len(entries)}주", flush=True)
    for i, (monday, year, month, week) in enumerate(entries, 1):
        sat = monday + timedelta(days=5)
        try:
            agg = aggregate_period(db, monday, sat)
            build_weekly_report(db, agg, year, month, week, monday, sat)
            print(f"[weekly] ({i}/{len(entries)}) {year}년{month}월{week}주차 ({monday}~{sat}) 완료", flush=True)
        except Exception as e:
            print(f"[weekly] ({i}/{len(entries)}) {year}년{month}월{week}주차 실패: {e}", flush=True)
    print("[weekly] 백필 종료\n", flush=True)


def backfill_monthly(yesterday: date) -> None:
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period
    from ktoa_mvno_period_report import build_monthly_report

    db = _get_db()
    is_month_end = yesterday.day == monthrange(yesterday.year, yesterday.month)[1]
    last_completed_month = yesterday.month if is_month_end else yesterday.month - 1

    months = list(range(1, last_completed_month + 1)) if last_completed_month >= 1 else []
    print(f"[monthly] 백필 시작: {YEAR}년 {months}월", flush=True)
    for i, month in enumerate(months, 1):
        period_start = date(YEAR, month, 1)
        period_end = date(YEAR, month, monthrange(YEAR, month)[1])
        try:
            agg = aggregate_period(db, period_start, period_end)
            build_monthly_report(db, agg, YEAR, month, period_start, period_end)
            print(f"[monthly] ({i}/{len(months)}) {YEAR}-{month:02d} 완료", flush=True)
        except Exception as e:
            print(f"[monthly] ({i}/{len(months)}) {YEAR}-{month:02d} 실패: {e}", flush=True)
    print("[monthly] 백필 종료\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="2026년 Context DB 백필 (텔레그램 발송 없음)")
    parser.add_argument("--daily-only", action="store_true")
    parser.add_argument("--period-only", action="store_true", help="weekly+monthly만")
    args = parser.parse_args()

    yesterday = get_yesterday_kst()
    print(f"기준일(어제, KST): {yesterday}\n", flush=True)

    if not args.period_only:
        backfill_daily(date(YEAR, 1, 1), yesterday)
    if not args.daily_only:
        backfill_weekly(yesterday)
        backfill_monthly(yesterday)

    print("=== 전체 백필 종료 ===", flush=True)


if __name__ == "__main__":
    main()
