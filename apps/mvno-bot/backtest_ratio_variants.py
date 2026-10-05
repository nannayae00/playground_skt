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
    """(ratio, days_ago) 쌍 수집"""
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

def method_recency_weighted(samples):
    if len(samples) < 5:
        return None
    def w(days_ago):
        if days_ago <= 90: return 3.0
        if days_ago <= 270: return 2.0
        return 1.0
    pairs = sorted(samples, key=lambda x: x[0])
    total_w = sum(w(da) for _, da in pairs)
    half = total_w / 2
    acc = 0
    for r, da in pairs:
        acc += w(da)
        if acc >= half:
            return r
    return pairs[-1][0]

def method_trimmed_mean(samples, trim=2):
    ratios = sorted(r for r, _ in samples)
    if len(ratios) < 5:
        return None
    if len(ratios) > trim * 2:
        ratios = ratios[trim:-trim]
    return statistics.mean(ratios)

def method_recent15(samples):
    recent = sorted(samples, key=lambda x: x[1])[:15]
    ratios = [r for r, _ in recent]
    return statistics.median(ratios) if len(ratios) >= 5 else None


METHODS = {
    'A_baseline(median40)': method_baseline,
    'B_recency_weighted': method_recency_weighted,
    'C_trimmed_mean': method_trimmed_mean,
    'D_recent15_median': method_recent15,
}

FIELDS = [
    ('mno_out', 'S'), ('mno_out', 'K'), ('mno_out', 'L'),
    ('mvno_in', 'SM'), ('mvno_in', 'KM'), ('mvno_in', 'LM'),
    ('mvno_out', 'SM'), ('mvno_out', 'KM'), ('mvno_out', 'LM'),
]
HOURS = range(11, 20)

d = datetime.strptime('2026-09-30', '%Y-%m-%d')
test_dates = []
while len(test_dates) < 12:
    ds = d.strftime('%Y-%m-%d')
    daily = cached_daily(ds)
    if daily and (daily.get('mno_out', {}) or {}).get('S'):
        test_dates.append(ds)
    d -= timedelta(days=1)

print(f"테스트 기간: {len(test_dates)}일 ({test_dates[-1]} ~ {test_dates[0]})\n")

acc_by_method_hour = {m: {h: [] for h in HOURS} for m in METHODS}
acc_by_method_overall = {m: [] for m in METHODS}

for ds in test_dates:
    daily = cached_daily(ds)
    hdocs = cached_hourly(ds)
    on_hour = {}
    for h in hdocs:
        dd = h.to_dict()
        hour_tag = dd.get('forecast_hour')
        minute_tag = dd.get('forecast_minute')
        if hour_tag is not None and minute_tag == 0:
            on_hour[hour_tag] = dd

    for group, key in FIELDS:
        actual = (daily.get(group, {}) or {}).get(key, 0) or 0
        if not actual:
            continue
        field_accs = {m: [] for m in METHODS}
        for hour in HOURS:
            hdoc = on_hour.get(hour)
            if not hdoc:
                continue
            today_val = (hdoc.get(group, {}) or {}).get(key, 0) or 0
            if not today_val:
                continue
            samples = get_samples(ds, hour, group, key)
            if len(samples) < 5:
                continue
            for mname, mfunc in METHODS.items():
                ratio = mfunc(samples)
                if not ratio or ratio <= 0:
                    continue
                fc = today_val / ratio
                acc = max(0.0, 100 - abs(fc - actual) / actual * 100)
                acc_by_method_hour[mname][hour].append(acc)
                field_accs[mname].append(acc)
        for mname in METHODS:
            if field_accs[mname]:
                acc_by_method_overall[mname].append(sum(field_accs[mname]) / len(field_accs[mname]))

print(f"{'시간':>4}", end='')
for m in METHODS:
    print(f" {m:>22}", end='')
print()
for hour in HOURS:
    print(f"{hour:>4}", end='')
    for m in METHODS:
        vals = acc_by_method_hour[m][hour]
        avg = sum(vals)/len(vals) if vals else 0
        print(f" {avg:>21.1f}%", end='')
    print()

print()
print("전체(11-19h) 평균:")
for m in METHODS:
    vals = acc_by_method_overall[m]
    avg = sum(vals)/len(vals) if vals else 0
    print(f"  {m:>22}: {avg:.1f}%")
