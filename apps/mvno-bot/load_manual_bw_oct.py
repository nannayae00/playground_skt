import google.oauth2.credentials
from google.cloud import firestore
import datetime as dt

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# 실무자 제공 "26년 10월 MVNO 영업일수 안내" 표 - 후불일별 행
# 누적(후불) 행과 차분 대조로 검증 완료 (25일=0이 맞음, 표 직독시 1.3으로 오인하기 쉬움)
MANUAL_BW_POSTPAID = {
    1: 1.3, 2: 1.2, 3: 0.5, 4: 0.0, 5: 0.5, 6: 1.5, 7: 1.3, 8: 1.0, 9: 0.5,
    10: 0.5, 11: 0.0, 12: 1.5, 13: 1.2, 14: 1.1, 15: 1.0, 16: 1.1, 17: 0.5,
    18: 0.0, 19: 1.3, 20: 1.0, 21: 1.1, 22: 1.0, 23: 1.1, 24: 0.5, 25: 0.0,
    26: 1.3, 27: 1.0, 28: 1.1, 29: 1.1, 30: 1.4, 31: 0.5,
}

batch = db.batch()
for day, val in MANUAL_BW_POSTPAID.items():
    ds = f"2026-10-{day:02d}"
    ref = db.collection('ktoa_daily').document(ds)
    batch.set(ref, {'bw_manual': val, 'date': ds}, merge=True)
batch.commit()
print(f"bw_manual 저장 완료: {len(MANUAL_BW_POSTPAID)}일")
print()

print(f"{'날짜':>12} {'요일':>4} {'실무자(후불)':>10} {'AI(bw_ai_prev)':>14} {'차이':>7} {'비율':>7}")
for day in range(1, 32):
    ds = f"2026-10-{day:02d}"
    doc = db.collection('ktoa_daily').document(ds).get().to_dict() or {}
    ai = doc.get('bw_ai_prev')
    manual = MANUAL_BW_POSTPAID.get(day)
    wd = ['월','화','수','목','금','토','일'][dt.datetime.strptime(ds,'%Y-%m-%d').weekday()]
    if ai is not None and manual is not None:
        diff = ai - manual
        ratio = (ai / manual * 100) if manual > 0 else (0 if ai == 0 else float('inf'))
        ratio_str = f"{ratio:.0f}%" if ratio != float('inf') else "N/A"
        print(f"{ds:>12} {wd:>4} {manual:>10.1f} {ai:>14.3f} {diff:>+7.3f} {ratio_str:>7}")
    else:
        print(f"{ds:>12} {wd:>4} {manual:>10.1f} {'(없음)':>14}")
