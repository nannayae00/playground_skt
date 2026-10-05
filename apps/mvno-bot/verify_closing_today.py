import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# 최근 ktoa_daily 문서들의 날짜를 훑어서 가장 최신 날짜 확인
today = datetime.now()
print(f"[로컬시각 기준 오늘] {today.strftime('%Y-%m-%d %H:%M')}")
print()

recent_dates = []
for delta in range(0, 10):
    ds = (today - timedelta(days=delta)).strftime('%Y-%m-%d')
    doc = db.collection('ktoa_daily').document(ds).get()
    if doc.exists:
        d = doc.to_dict()
        recent_dates.append((ds, d))

print("[최근 ktoa_daily 존재 날짜]")
for ds, d in recent_dates[:6]:
    mno = d.get('mno_out', {})
    mi = d.get('mvno_in', {})
    print(f"  {ds} | mno_out.계={mno.get('계')} | mvno_in.계={mi.get('계')} | collected_hours={d.get('collected_hours', '?')}")
