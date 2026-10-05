from ktoa_mvno_period_aggregator import _get_db, aggregate_period
from ktoa_mvno_period_report import build_weekly_report
from datetime import date

db = _get_db()
agg = aggregate_period(db, date(2026, 7, 27), date(2026, 8, 1))
messages = build_weekly_report(db, agg, 2026, 7, 5, date(2026, 7, 27), date(2026, 8, 1))

print(messages[2])

from ktoa_mvno_period_report import send_telegram_report
send_telegram_report(messages)
