import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

FIELDS = [
    ('mno_out', 'S'), ('mno_out', 'K'), ('mno_out', 'L'),
    ('mvno_in', 'SM'), ('mvno_in', 'KM'), ('mvno_in', 'LM'),
    ('mvno_out', 'SM'), ('mvno_out', 'KM'), ('mvno_out', 'LM'),
]

def day_accuracy(ds):
    daily = db.collection('ktoa_daily').document(ds).get().to_dict()
    if not daily:
        return None
    docs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    on_hour = [d.to_dict() for d in docs if d.to_dict().get('forecast_minute') == 0]
    if not on_hour:
        return None
    field_accs = []
    hour11_accs = []
    hour18_accs = []
    for group, key in FIELDS:
        actual = (daily.get(group, {}) or {}).get(key, 0) or 0
        if not actual:
            continue
        accs = []
        for d in on_hour:
            fc = (d.get(f'forecast_{group}', {}) or {}).get(key, 0) or 0
            hour = d.get('forecast_hour')
            if fc:
                err = abs(fc - actual) / actual * 100
                acc = max(0.0, 100 - err)
                accs.append(acc)
                if hour == 11:
                    hour11_accs.append(acc)
                if hour == 18:
                    hour18_accs.append(acc)
        if accs:
            field_accs.append(sum(accs) / len(accs))
    if not field_accs:
        return None
    return {
        'overall': sum(field_accs) / len(field_accs),
        'hour11': sum(hour11_accs) / len(hour11_accs) if hour11_accs else None,
        'hour18': sum(hour18_accs) / len(hour18_accs) if hour18_accs else None,
    }

d = datetime.strptime('2026-09-30', '%Y-%m-%d')
results = []
while len(results) < 8:
    ds = d.strftime('%Y-%m-%d')
    r = day_accuracy(ds)
    if r:
        results.append((ds, r))
    d -= timedelta(days=1)

print(f"{'날짜':>12} {'전체(11-19h)':>12} {'11시':>8} {'18시':>8}")
today_r = day_accuracy('2026-10-01')
print(f"{'2026-10-01(오늘)':>12} {today_r['overall']:>11.1f}% {today_r['hour11']:>7.1f}% {today_r['hour18']:>7.1f}%")
for ds, r in results:
    h11 = f"{r['hour11']:.1f}%" if r['hour11'] is not None else 'N/A'
    h18 = f"{r['hour18']:.1f}%" if r['hour18'] is not None else 'N/A'
    print(f"{ds:>12} {r['overall']:>11.1f}% {h11:>8} {h18:>8}")

overalls = [r['overall'] for _, r in results]
h11s = [r['hour11'] for _, r in results if r['hour11'] is not None]
h18s = [r['hour18'] for _, r in results if r['hour18'] is not None]
print()
print(f"최근 8일 평균: 전체 {sum(overalls)/len(overalls):.1f}% | 11시 {sum(h11s)/len(h11s):.1f}% | 18시 {sum(h18s)/len(h18s):.1f}%")
