import sys
sys.path.insert(0, '.')
import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta
import statistics

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

_daily_cache = {}
_hourly_cache = {}

def cached_daily(ds):
    if ds not in _daily_cache:
        doc = db.collection('ktoa_daily').document(ds).get()
        _daily_cache[ds] = doc.to_dict() if doc.exists else None
    return _daily_cache[ds]

def cached_hourly(ds):
    if ds not in _hourly_cache:
        _hourly_cache[ds] = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    return _hourly_cache[ds]

def get_samples(date_str, hour, group, key, max_n=40):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    samples = []
    cur = d - timedelta(days=7)
    checked = 0
    while len(samples) < max_n and checked < max_n * 2:
        ds = cur.strftime('%Y-%m-%d')
        checked += 1
        days_ago = (d - cur).days
        cur -= timedelta(days=7)
        if days_ago > 280:
            break
        daily_dict = cached_daily(ds)
        if not daily_dict:
            continue
        actual = daily_dict.get(group, {}).get(key)
        if not actual or actual <= 0:
            continue
        hdocs = cached_hourly(ds)
        candidates = sorted(
            (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
            key=lambda h: h.id
        )
        if not candidates:
            continue
        cum = candidates[0].to_dict().get(group, {}).get(key)
        if cum and cum > 0:
            samples.append((cum / actual, days_ago))
    return sorted(samples, key=lambda x: x[1])  # 최신순 정렬


WINDOWS = [8, 10, 12, 15, 18, 20, 25, 30, 40]

FIELDS = [
    ('mno_out', 'S'), ('mno_out', 'K'), ('mno_out', 'L'),
    ('mvno_in', 'SM'), ('mvno_in', 'KM'), ('mvno_in', 'LM'),
    ('mvno_out', 'SM'), ('mvno_out', 'KM'), ('mvno_out', 'LM'),
]
HOURS = range(11, 20)

d = datetime.strptime('2026-09-30', '%Y-%m-%d')
test_dates = []
while len(test_dates) < 14:
    ds = d.strftime('%Y-%m-%d')
    daily = cached_daily(ds)
    if daily and (daily.get('mno_out', {}) or {}).get('S'):
        test_dates.append(ds)
    d -= timedelta(days=1)

print(f"테스트 기간: {len(test_dates)}일 ({test_dates[-1]} ~ {test_dates[0]})\n")

acc_overall = {w: [] for w in WINDOWS}
acc_early = {w: [] for w in WINDOWS}  # 11-14시만

for ds in test_dates:
    daily = cached_daily(ds)
    hdocs = cached_hourly(ds)
    on_hour = {}
    for h in hdocs:
        dd = h.to_dict()
        if dd.get('forecast_minute') == 0:
            on_hour[dd.get('forecast_hour')] = dd

    for group, key in FIELDS:
        actual = (daily.get(group, {}) or {}).get(key, 0) or 0
        if not actual:
            continue
        field_accs = {w: [] for w in WINDOWS}
        field_accs_early = {w: [] for w in WINDOWS}
        for hour in HOURS:
            hdoc = on_hour.get(hour)
            if not hdoc:
                continue
            today_val = (hdoc.get(group, {}) or {}).get(key, 0) or 0
            if not today_val:
                continue
            samples = get_samples(ds, hour, group, key, max_n=40)
            if len(samples) < 5:
                continue
            for w in WINDOWS:
                sub = samples[:w]
                ratios = [r for r, _ in sub]
                if len(ratios) < 5:
                    continue
                ratio = statistics.median(ratios)
                if ratio <= 0:
                    continue
                fc = today_val / ratio
                acc = max(0.0, 100 - abs(fc - actual) / actual * 100)
                field_accs[w].append(acc)
                if hour <= 14:
                    field_accs_early[w].append(acc)
        for w in WINDOWS:
            if field_accs[w]:
                acc_overall[w].append(sum(field_accs[w]) / len(field_accs[w]))
            if field_accs_early[w]:
                acc_early[w].append(sum(field_accs_early[w]) / len(field_accs_early[w]))

print(f"{'윈도우':>6} {'전체(11-19h)':>12} {'초반(11-14h)':>12}")
for w in WINDOWS:
    o = acc_overall[w]
    e = acc_early[w]
    avg_o = sum(o)/len(o) if o else 0
    avg_e = sum(e)/len(e) if e else 0
    print(f"{w:>6} {avg_o:>11.2f}% {avg_e:>11.2f}%")
