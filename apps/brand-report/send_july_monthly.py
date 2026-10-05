from ktoa_mvno_period_aggregator import _get_db, aggregate_period
from ktoa_mvno_period_report import build_monthly_report, send_telegram_report
from datetime import date

db = _get_db()
agg = aggregate_period(db, date(2026, 7, 1), date(2026, 7, 31))
messages = build_monthly_report(db, agg, 2026, 7, date(2026, 7, 1), date(2026, 7, 31))
send_telegram_report(messages)
print("발송 완료")
