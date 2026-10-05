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

def get_samples(date_str, hour, group, key, top_n=40):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    samples = []
    cur = d - timedelta(days=7)
    checked = 0
    while len(samples) < top_n and checked < top_n * 2:
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
    return samples

def method_baseline(samples):
    ratios = [r for r, _ in samples]
    return statistics.median(ratios) if len(ratios) >= 5 else None

def method_recent15(samples):
    recent = sorted(samples, key=lambda x: x[1])[:15]
    ratios = [r for r, _ in recent]
    return statistics.median(ratios) if len(ratios) >= 5 else None

DATE = '2026-10-01'  # live before/after D comparison
FIELDS = [
    ('mno_out', 'S', 'SKT Out'), ('mno_out', 'K', 'KT Out'), ('mno_out', 'L', 'LGU+ Out'),
    ('mvno_in', 'SM', 'MVNO IN SM'), ('mvno_in', 'KM', 'MVNO IN KM'), ('mvno_in', 'LM', 'MVNO IN LM'),
    ('mvno_out', 'SM', 'MVNO OUT SM'), ('mvno_out', 'KM', 'MVNO OUT KM'), ('mvno_out', 'LM', 'MVNO OUT LM'),
]
HOURS = range(11, 20)

daily = cached_daily(DATE)
hdocs = cached_hourly(DATE)
on_hour = {}
for h in hdocs:
    dd = h.to_dict()
    if dd.get('forecast_minute') == 0:
        on_hour[dd.get('forecast_hour')] = dd

field_acc_base = {}
field_acc_d = {}
hour_acc_base = {h: [] for h in HOURS}
hour_acc_d = {h: [] for h in HOURS}

for group, key, label in FIELDS:
    actual = (daily.get(group, {}) or {}).get(key, 0) or 0
    if not actual:
        continue
    accs_base, accs_d = [], []
    for hour in HOURS:
        hdoc = on_hour.get(hour)
        if not hdoc:
            continue
        today_val = (hdoc.get(group, {}) or {}).get(key, 0) or 0
        if not today_val:
            continue
        samples = get_samples(DATE, hour, group, key)
        if len(samples) < 5:
            continue
        r_base = method_baseline(samples)
        r_d = method_recent15(samples)
        if r_base and r_base > 0:
            fc = today_val / r_base
            acc = max(0.0, 100 - abs(fc - actual) / actual * 100)
            accs_base.append(acc)
            hour_acc_base[hour].append(acc)
        if r_d and r_d > 0:
            fc = today_val / r_d
            acc = max(0.0, 100 - abs(fc - actual) / actual * 100)
            accs_d.append(acc)
            hour_acc_d[hour].append(acc)
    if accs_base:
        field_acc_base[label] = sum(accs_base) / len(accs_base)
        field_acc_d[label] = sum(accs_d) / len(accs_d)

print(f"{'지표':>14} {'기존(A)':>10} {'최근15주(D)':>12} {'차이':>8}")
for label in field_acc_base:
    a = field_acc_base[label]
    b = field_acc_d[label]
    print(f"{label:>14} {a:>9.1f}% {b:>11.1f}% {b-a:>+7.1f}%p")

print()
print(f"{'시간':>4} {'기존(A)':>10} {'최근15주(D)':>12} {'차이':>8}")
for hour in HOURS:
    a = hour_acc_base[hour]
    b = hour_acc_d[hour]
    if a:
        avg_a = sum(a)/len(a)
        avg_b = sum(b)/len(b)
        print(f"{hour:>4} {avg_a:>9.1f}% {avg_b:>11.1f}% {avg_b-avg_a:>+7.1f}%p")

overall_a = sum(field_acc_base.values()) / len(field_acc_base)
overall_d = sum(field_acc_d.values()) / len(field_acc_d)
print()
print(f"오늘(10/1) 9개 지표 전체 평균: 기존 {overall_a:.1f}% -> 최근15주(D) {overall_d:.1f}%")
