import sys, os, logging, time
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import forecast_engine
forecast_engine._get_db = lambda: db

DATES = ['2026-09-28', '2026-09-29', '2026-09-30']
HOURS = list(range(11, 20))
FIELDS = [
    ('mno_out', 'S', 'SKT OUT'),
    ('mno_out', 'K', 'MNO Out K'),
    ('mno_out', 'L', 'MNO Out L'),
    ('mvno_in', 'SM', 'MVNO IN SM'),
    ('mvno_in', 'KM', 'MVNO IN KM'),
    ('mvno_in', 'LM', 'MVNO IN LM'),
    ('mvno_out', 'SM', 'MVNO OUT SM'),
    ('mvno_out', 'KM', 'MVNO OUT KM'),
    ('mvno_out', 'LM', 'MVNO OUT LM'),
]

def get_hour_doc(ds, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    return candidates[0].to_dict() if candidates else None

def acc(pred, actual):
    if not pred or not actual:
        return None
    return max(0.0, 1 - abs(pred - actual) / abs(actual)) * 100

t0 = time.time()
results = {}  # (group,key) -> {ds: {'old':acc, 'new':acc}}
for group, key, label in FIELDS:
    results[(group, key)] = {}

for ds in DATES:
    daily = db.collection('ktoa_daily').document(ds).get().to_dict()
    for group, key, label in FIELDS:
        actual = daily.get(group, {}).get(key)
        if not actual:
            continue
        old_accs, new_accs = [], []
        for hour in HOURS:
            hd = get_hour_doc(ds, hour)
            if not hd:
                continue
            cur = hd.get(group, {}).get(key, 0) or 0
            if not cur:
                continue
            old_fc = hd.get({'mno_out':'forecast_mno_out','mvno_in':'forecast_mvno_in','mvno_out':'forecast_mvno_out'}[group], {}).get(key, 0) or 0
            new_fc = forecast_engine.get_field_daily_forecast(ds, hour, group, key, cur)
            if old_fc:
                a = acc(old_fc, actual)
                if a is not None: old_accs.append(a)
            a2 = acc(new_fc, actual)
            if a2 is not None: new_accs.append(a2)
        old_avg = sum(old_accs)/len(old_accs) if old_accs else None
        new_avg = sum(new_accs)/len(new_accs) if new_accs else None
        results[(group,key)][ds] = {'old': old_avg, 'new': new_avg}

t1 = time.time()
print(f"[소요시간: {t1-t0:.1f}초]")
print()
hdr = f"{'항목':>14}  " + "  ".join(f"{ds[5:]:>16}" for ds in DATES) + "   3일평균"
print(hdr)
overall_old, overall_new = [], []
for group, key, label in FIELDS:
    row = f"{label:>14}  "
    day_olds, day_news = [], []
    for ds in DATES:
        r = results[(group,key)].get(ds, {})
        o, n = r.get('old'), r.get('new')
        if o is not None: day_olds.append(o)
        if n is not None: day_news.append(n)
        o_s = f"{o:.1f}" if o is not None else "-"
        n_s = f"{n:.1f}" if n is not None else "-"
        row += f"{o_s:>7}/{n_s:>7}  "
    avg_o = sum(day_olds)/len(day_olds) if day_olds else None
    avg_n = sum(day_news)/len(day_news) if day_news else None
    if avg_o is not None: overall_old.append(avg_o)
    if avg_n is not None: overall_new.append(avg_n)
    row += f"  {avg_o:.1f}/{avg_n:.1f}" if avg_o is not None and avg_n is not None else ""
    print(row)

print()
if overall_old and overall_new:
    print(f"[전체 9항목 평균] 구방식={sum(overall_old)/len(overall_old):.1f}%  신방식={sum(overall_new)/len(overall_new):.1f}%")
