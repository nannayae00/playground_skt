import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

DATE = '2026-10-01'

daily = db.collection('ktoa_daily').document(DATE).get().to_dict()
if not daily:
    print("오늘 마감 데이터 없음")
    raise SystemExit

print(f"===== {DATE} 실제 마감값 =====")
mno = daily.get('mno_out', {}) or {}
mi = daily.get('mvno_in', {}) or {}
mo = daily.get('mvno_out', {}) or {}
print(f"MNO Out: S={mno.get('S')} K={mno.get('K')} L={mno.get('L')} 계={mno.get('계')}")
print(f"MVNO IN: SM={mi.get('SM')} KM={mi.get('KM')} LM={mi.get('LM')} 계={mi.get('계')}")
print(f"MVNO OUT: SM={mo.get('SM')} KM={mo.get('KM')} LM={mo.get('LM')} 계={mo.get('계')}")
print()

docs = list(db.collection('ktoa_hourly').where('date', '==', DATE).stream())
on_hour = []
for doc in docs:
    d = doc.to_dict()
    if d.get('forecast_minute') == 0:
        on_hour.append(d)
on_hour.sort(key=lambda d: d.get('forecast_hour', 0))

FIELDS = [
    ('mno_out', 'S', 'SKT Out'), ('mno_out', 'K', 'KT Out'), ('mno_out', 'L', 'LGU+ Out'),
    ('mvno_in', 'SM', 'MVNO IN SM'), ('mvno_in', 'KM', 'MVNO IN KM'), ('mvno_in', 'LM', 'MVNO IN LM'),
    ('mvno_out', 'SM', 'MVNO OUT SM'), ('mvno_out', 'KM', 'MVNO OUT KM'), ('mvno_out', 'LM', 'MVNO OUT LM'),
]

print(f"===== 정시별 예측 vs 실제 마감 =====\n")
field_accs = {}
for group, key, label in FIELDS:
    actual = (daily.get(group, {}) or {}).get(key, 0) or 0
    if not actual:
        continue
    hourly_acc = []
    rows = []
    for d in on_hour:
        hour = d.get('forecast_hour')
        fc = (d.get(f'forecast_{group}', {}) or {}).get(key, 0) or 0
        if fc:
            err = abs(fc - actual) / actual * 100
            acc = max(0.0, 100 - err)
            hourly_acc.append(acc)
            rows.append((hour, fc, acc))
    if hourly_acc:
        avg_acc = sum(hourly_acc) / len(hourly_acc)
        field_accs[label] = avg_acc
        print(f"-- {label} (실제 마감 {actual}) --")
        for hour, fc, acc in rows:
            print(f"   {hour:>2}시 예측 {fc:>6} | 정확도 {acc:>5.1f}%")
        print(f"   => 평균 정확도: {avg_acc:.1f}%\n")

print("===== 전체 요약 =====")
for label, acc in field_accs.items():
    print(f"  {label:>14}: {acc:.1f}%")
if field_accs:
    overall = sum(field_accs.values()) / len(field_accs)
    print(f"\n  9개 지표 평균 정확도: {overall:.1f}%")
