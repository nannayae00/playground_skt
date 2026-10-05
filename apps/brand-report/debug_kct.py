from ktoa_mvno_period_aggregator import _get_db, aggregate_period
from ktoa_mvno_report import clean_brand_name, shorten_brand_name
from datetime import date

db = _get_db()
agg = aggregate_period(db, date(2026,7,27), date(2026,8,1))

for brand, d in agg["brands"].items():
    short = shorten_brand_name(clean_brand_name(brand))
    if "KCT" in short or "KCT" in brand:
        print(repr(brand), "| clean:", repr(clean_brand_name(brand)), "| short:", repr(short), "| network:", d["network"])
