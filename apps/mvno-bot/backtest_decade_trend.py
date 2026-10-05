import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

from bw_engine import is_zero_day

today = datetime.now()
dates = []
d = today - timedelta(days=1)
while len(dates) < 175 and (today - d).days < 185:
    ds = d.strftime('%Y-%m-%d')
    if not is_zero_day(ds):
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            actual = doc.to_dict().get('mno_out', {}).get('S')
            if actual and actual > 0:
                dates.append(ds)
    d -= timedelta(days=1)
dates.reverse()
print(f"수집된 날짜 수: {len(dates)}  ({dates[0]} ~ {dates[-1]})")

HOURS = [11, 12, 13, 14, 15]

def get_hour_cum(ds, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    if not candidates:
        return None
    return candidates[0].to_dict().get('mno_out', {}).get('S')

def decade(ds):
    day = int(ds[8:10])
    if day <= 10: return 0
    if day <= 20: return 1
    return 2

actuals = {}
weekdays = {}
decades = {}
hour_cum_cache = {}
for ds in dates:
    doc = db.collection('ktoa_daily').document(ds).get()
    actuals[ds] = doc.to_dict().get('mno_out', {}).get('S')
    weekdays[ds] = datetime.strptime(ds, '%Y-%m-%d').weekday()
    decades[ds] = decade(ds)
    for h in HOURS:
        hour_cum_cache[(ds, h)] = get_hour_cum(ds, h)

print("데이터 수집 완료, 백테스트 시작")

results = {h: {c: [] for c in ['D_dow_only', 'K_decade_only', 'L_dow_and_decade']} for h in HOURS}

for idx, test_ds in enumerate(dates):
    prior = dates[:idx]
    if len(prior) < 15:
        continue
    test_actual = actuals[test_ds]
    if not test_actual:
        continue
    test_wd = weekdays[test_ds]
    test_dec = decades[test_ds]

    for h in HOURS:
        today_cum = hour_cum_cache.get((test_ds, h))
        if not today_cum or today_cum <= 0:
            continue

        pairs_dow = []
        pairs_decade = []
        pairs_both = []
        for pd in reversed(prior):
            a = actuals.get(pd)
            c = hour_cum_cache.get((pd, h))
            if a and a > 0 and c and c > 0:
                if weekdays[pd] == test_wd:
                    pairs_dow.append((c, a))
                if decades[pd] == test_dec:
                    pairs_decade.append((c, a))
                if weekdays[pd] == test_wd and decades[pd] == test_dec:
                    pairs_both.append((c, a))
            if len(pairs_dow) >= 40 and len(pairs_decade) >= 40 and len(pairs_both) >= 40:
                break

        if len(pairs_dow) >= 8:
            ratios = [c / a for c, a in pairs_dow[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['D_dow_only'].append(abs(fc - test_actual) / test_actual * 100)

        if len(pairs_decade) >= 8:
            ratios = [c / a for c, a in pairs_decade[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['K_decade_only'].append(abs(fc - test_actual) / test_actual * 100)

        if len(pairs_both) >= 5:
            ratios = [c / a for c, a in pairs_both[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['L_dow_and_decade'].append(abs(fc - test_actual) / test_actual * 100)

print()
print(f"{'시간':>4}   " + "  ".join(f"{c:>18}" for c in ['D_dow_only', 'K_decade_only', 'L_dow_and_decade']))
for h in HOURS:
    row = f"{h:>4}시  "
    for c in ['D_dow_only', 'K_decade_only', 'L_dow_and_decade']:
        vals = results[h][c]
        mape = statistics.mean(vals) if vals else float('nan')
        row += f"{mape:>12.1f}%(n={len(vals):>3})  "
    print(row)
