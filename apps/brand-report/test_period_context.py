"""
test_period_context.py
주간/월간 build_*_report() 호출해서 Context DB(ktoa_brand_context_weekly/monthly)
저장이 잘 되는지 확인하는 테스트 스크립트. 텔레그램은 안 보냄
(send_telegram_report()를 안 부르므로).

사용법 (brand-report/ 폴더에 이 파일 놓고):
    python3 test_period_context.py

[수정 이력]
- v1.0 (2026-08-27): 최초 작성
"""

from datetime import date
from calendar import monthrange

from ktoa_mvno_period_aggregator import _get_db, aggregate_period
from ktoa_mvno_period_report import build_weekly_report, build_monthly_report


def test_weekly(db):
    print("=== 주간 테스트 시작 (2026-08-17~2026-08-22, 8월3주차) ===", flush=True)
    period_start, period_end = date(2026, 8, 17), date(2026, 8, 22)
    agg = aggregate_period(db, period_start, period_end)
    messages = build_weekly_report(db, agg, 2026, 8, 3, period_start, period_end)
    print(f"[주간] 메시지 개수: {len(messages)}", flush=True)
    print(f"[주간] 저장 위치: ktoa_brand_context_weekly/{period_start.isoformat()}", flush=True)
    print("=== 주간 테스트 완료 ===\n", flush=True)


def test_monthly(db):
    print("=== 월간 테스트 시작 (2026년 7월) ===", flush=True)
    year, month = 2026, 7
    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    agg = aggregate_period(db, period_start, period_end)
    messages = build_monthly_report(db, agg, year, month, period_start, period_end)
    print(f"[월간] 메시지 개수: {len(messages)}", flush=True)
    print(f"[월간] 저장 위치: ktoa_brand_context_monthly/{period_start.isoformat()}", flush=True)
    print("=== 월간 테스트 완료 ===\n", flush=True)


if __name__ == "__main__":
    db = _get_db()
    test_weekly(db)
    test_monthly(db)
    print("전체 테스트 완료 - Firestore 콘솔에서 두 문서 확인하세요.", flush=True)
