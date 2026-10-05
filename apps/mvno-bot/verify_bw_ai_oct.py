import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import bw_engine
bw_engine._get_db = lambda: db

DATES = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06',
         '2026-10-07', '2026-10-08', '2026-10-13']

for ds in DATES:
    cands = bw_engine._get_knn_similar_days(ds, top_n=10)
    knn = bw_engine._calc_knn_bw(cands)
    fallback = bw_engine._calc_bw_fallback(ds)
    stored = db.collection('ktoa_daily').document(ds).get().to_dict() or {}
    print(f"{ds} | K-NN 후보수={len(cands)} | K-NN값={knn} | 폴백값={fallback} | 저장된 bw_ai_prev={stored.get('bw_ai_prev')}")
    if cands:
        for c in cands[:5]:
            print(f"      - {c['date']} bw={c['bw']} weight={c['weight']}")
