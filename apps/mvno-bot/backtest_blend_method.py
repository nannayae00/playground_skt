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
    """동일 요일, 7일 간격 과거 샘플들의 (cum_at_hour, final_actual) 쌍 수집"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    samples = []
    cur = d - timedelta(days=7)
    checked = 0
    while len(samples) < top_n and checked < top_n * 2:
        ds = cur.strftime('%Y-%m-%d')
        checked += 1
        cur -= timedelta(days=7)
        if (d - cur).days > 280:
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
            samples.append((cum, actual))
    return samples


def forecast_both(date_str, hour, group, key, today_val):
    samples = get_samples(date_str, hour, group, key)
    if len(samples) < 5 or today_val <= 0:
        return None, None, None
    ratios = [c / a for c, a in samples]
    anchors = [a for c, a in samples]
    ratio_med = statistics.median(ratios)
    anchor_med = statistics.median(anchors)
    if ratio_med <= 0:
        return None, None, None
    fc_current = today_val / ratio_med
    fc_blend = today_val + (1 - ratio_med) * anchor_med
    return fc_current, fc_blend, ratio_med


FIELDS = [
    ('mno_out', 'S'), ('mno_out', 'K'), ('mno_out', 'L'),
    ('mvno_in', 'SM'), ('mvno_in', 'KM'), ('mvno_in', 'LM'),
    ('mvno_out', 'SM'), ('mvno_out', 'KM'), ('mvno_out', 'LM'),
]
HOURS = range(11, 20)

# 테스트 기간: 최근 12영업일 (10/1 제외, 학습 누수 방지 위해 trailing만 사용하는
# get_samples 구조상 문제 없음 - 항상 테스트일 이전 데이터만 씀)
d = datetime.strptime('2026-09-30', '%Y-%m-%d')
test_dates = []
while len(test_dates) < 12:
    ds = d.strftime('%Y-%m-%d')
    daily = cached_daily(ds)
    if daily and (daily.get('mno_out', {}) or {}).get('S'):
        test_dates.append(ds)
    d -= timedelta(days=1)

print(f"테스트 기간: {len(test_dates)}일 ({test_dates[-1]} ~ {test_dates[0]})\n")

acc_cur_by_hour = {h: [] for h in HOURS}
acc_blend_by_hour = {h: [] for h in HOURS}
acc_cur_overall = []
acc_blend_overall = []

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
        field_cur_accs = []
        field_blend_accs = []
        for hour in HOURS:
            hdoc = on_hour.get(hour)
            if not hdoc:
                continue
            today_val = (hdoc.get(group, {}) or {}).get(key, 0) or 0
            if not today_val:
                continue
            fc_cur, fc_blend, ratio = forecast_both(ds, hour, group, key, today_val)
            if fc_cur is None:
                continue
            acc_c = max(0.0, 100 - abs(fc_cur - actual) / actual * 100)
            acc_b = max(0.0, 100 - abs(fc_blend - actual) / actual * 100)
            acc_cur_by_hour[hour].append(acc_c)
            acc_blend_by_hour[hour].append(acc_b)
            field_cur_accs.append(acc_c)
            field_blend_accs.append(acc_b)
        if field_cur_accs:
            acc_cur_overall.append(sum(field_cur_accs) / len(field_cur_accs))
            acc_blend_overall.append(sum(field_blend_accs) / len(field_blend_accs))

print(f"{'시간':>4} {'기존방식':>10} {'블렌딩':>10} {'개선폭':>8} {'n':>5}")
for hour in HOURS:
    c = acc_cur_by_hour[hour]
    b = acc_blend_by_hour[hour]
    if c:
        avg_c = sum(c) / len(c)
        avg_b = sum(b) / len(b)
        print(f"{hour:>4} {avg_c:>9.1f}% {avg_b:>9.1f}% {avg_b-avg_c:>+7.1f}%p {len(c):>5}")

print()
print(f"전체(11-19h) 평균: 기존 {sum(acc_cur_overall)/len(acc_cur_overall):.1f}% -> "
      f"블렌딩 {sum(acc_blend_overall)/len(acc_blend_overall):.1f}%")
