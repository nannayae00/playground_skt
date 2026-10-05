import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

DATES = [f"2026-09-{d:02d}" for d in range(15, 31)]

print("===== 1) ktoa_daily.mno_out.S (T Out / SKT OUT 전체) 일자별 추이 =====\n")
daily_vals = {}
for ds in DATES:
    doc = db.collection('ktoa_daily').document(ds).get()
    d = doc.to_dict() if doc.exists else {}
    s = (d.get('mno_out', {}) or {}).get('S')
    wd = ['월','화','수','목','금','토','일'][datetime.strptime(ds,'%Y-%m-%d').weekday()]
    daily_vals[ds] = s
    print(f"  {ds} {wd} | mno_out.S = {s}")

print()
print("===== 2) ktoa_mvno_brand_out/{date}_SKT 문서 존재 여부 + total_out =====\n")
for ds in DATES:
    doc_id = f"{ds}_SKT"
    doc = db.collection('ktoa_mvno_brand_out').document(doc_id).get()
    d = doc.to_dict() if doc.exists else None
    if d:
        print(f"  {ds} | brand_out 문서 있음 | total_out={d.get('total_out')} | outflows 항목수={len(d.get('outflows', {}))}")
    else:
        print(f"  {ds} | brand_out 문서 없음")
