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
    """(ratio, days_ago, actual_final) 튜플, 최신순"""
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
            samples.append((cum / actual, days_ago, actual))
    return sorted(samples, key=lambda x: x[1])


WINDOW = 15
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

acc_D = {h: [] for h in HOURS}
acc_cross = {h: [] for h in HOURS}
acc_blend = {h: [] for h in HOURS}
acc_D_overall, acc_cross_overall, acc_blend_overall = [], [], []

for ds in test_dates:
    daily = cached_daily(ds)
    hdocs = cached_hourly(ds)
    on_hour = {}
    for h in hdocs:
        dd = h.to_dict()
        if dd.get('forecast_minute') == 0:
            on_hour[dd.get('forecast_hour')] = dd

    for hour in HOURS:
        hdoc = on_hour.get(hour)
        if not hdoc:
            continue

        field_data = {}  # (group,key) -> dict
        for group, key in FIELDS:
            actual = (daily.get(group, {}) or {}).get(key, 0) or 0
            today_val = (hdoc.get(group, {}) or {}).get(key, 0) or 0
            if not actual or not today_val:
                continue
            samples = get_samples(ds, hour, group, key, max_n=40)[:WINDOW]
            if len(samples) < 5:
                continue
            ratios = [r for r, _, _ in samples]
            anchors = [a for _, _, a in samples]
            ratio_med = statistics.median(ratios)
            anchor_med = statistics.median(anchors)
            if ratio_med <= 0 or anchor_med <= 0:
                continue
            fc_D = today_val / ratio_med
            pace = fc_D / anchor_med
            field_data[(group, key)] = {
                'actual': actual, 'fc_D': fc_D, 'anchor': anchor_med, 'pace': pace
            }

        if len(field_data) < 5:
            continue

        consensus_pace = statistics.median(v['pace'] for v in field_data.values())

        day_accs_D, day_accs_cross, day_accs_blend = [], [], []
        for (group, key), v in field_data.items():
            actual = v['actual']
            fc_D = v['fc_D']
            fc_cross = v['anchor'] * consensus_pace
            fc_blend = (fc_D + fc_cross) / 2

            acc_d = max(0.0, 100 - abs(fc_D - actual) / actual * 100)
            acc_c = max(0.0, 100 - abs(fc_cross - actual) / actual * 100)
            acc_b = max(0.0, 100 - abs(fc_blend - actual) / actual * 100)

            acc_D[hour].append(acc_d)
            acc_cross[hour].append(acc_c)
            acc_blend[hour].append(acc_b)
            day_accs_D.append(acc_d)
            day_accs_cross.append(acc_c)
            day_accs_blend.append(acc_b)

        if day_accs_D:
            acc_D_overall.append(sum(day_accs_D) / len(day_accs_D))
            acc_cross_overall.append(sum(day_accs_cross) / len(day_accs_cross))
            acc_blend_overall.append(sum(day_accs_blend) / len(day_accs_blend))

print(f"{'시간':>4} {'D(기준)':>10} {'교차검증':>10} {'D+교차블렌드':>12}")
for hour in HOURS:
    dv = acc_D[hour]
    cv = acc_cross[hour]
    bv = acc_blend[hour]
    if dv:
        print(f"{hour:>4} {sum(dv)/len(dv):>9.1f}% {sum(cv)/len(cv):>9.1f}% {sum(bv)/len(bv):>11.1f}%")

print()
print(f"전체(11-19h) 평균: D(기준) {sum(acc_D_overall)/len(acc_D_overall):.2f}% | "
      f"교차검증 {sum(acc_cross_overall)/len(acc_cross_overall):.2f}% | "
      f"블렌드 {sum(acc_blend_overall)/len(acc_blend_overall):.2f}%")
