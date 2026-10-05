import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
_real_db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

_doc_cache = {}
_hourly_where_cache = {}

class _CachedDocRef:
    def __init__(self, coll, doc_id):
        self.coll, self.doc_id = coll, doc_id
    def get(self):
        key = (self.coll, self.doc_id)
        if key not in _doc_cache:
            _doc_cache[key] = _real_db.collection(self.coll).document(self.doc_id).get()
        return _doc_cache[key]

class _StaticStream:
    def __init__(self, items): self.items = items
    def stream(self): return iter(self.items)

class _CachedCollection:
    def __init__(self, name): self.name = name
    def document(self, doc_id): return _CachedDocRef(self.name, doc_id)
    def where(self, field, op, value):
        if self.name == 'ktoa_hourly' and field == 'date' and op == '==':
            if value not in _hourly_where_cache:
                _hourly_where_cache[value] = list(_real_db.collection(self.name).where(field, op, value).stream())
            return _StaticStream(_hourly_where_cache[value])
        return _real_db.collection(self.name).where(field, op, value)

class _CachedClient:
    def collection(self, name): return _CachedCollection(name)

db = _CachedClient()

import forecast_engine
forecast_engine._get_db = lambda: db

date_str = '2026-09-30'
daily = db.collection('ktoa_daily').document(date_str).get().to_dict()
act_skt = daily.get('mno_out', {}).get('S')
print(f"실제마감 SKT OUT ({date_str}): {act_skt}")
print()

fc_crude_list = []
fc_ratio_list = []

print(f"{'시각':>4} {'실적누적':>8} {'구방식(균일페이스)':>18} {'신방식(요일별완료율곡선)':>22} {'완료율':>8}")
for hour in range(11, 20):
    found = None
    for minute in ['00', '01', '10', '50', '59']:
        doc_id = f"{date_str}_{hour:02d}{minute}"
        doc = db.collection('ktoa_hourly').document(doc_id).get()
        if doc.exists:
            found = doc.to_dict()
            if minute == '00':
                break
    if not found:
        continue
    cur_skt = found.get('mno_out', {}).get('S', 0) or 0
    if not cur_skt:
        continue
    elapsed = max(1, hour - 10)
    fc_crude = int(cur_skt * 10 / elapsed)
    ratio = forecast_engine._get_hour_completion_ratio(date_str, hour)
    fc_ratio = int(cur_skt / ratio) if ratio > 0 else fc_crude
    fc_crude_list.append(fc_crude)
    fc_ratio_list.append(fc_ratio)
    ratio_str = f"{ratio*100:.1f}%" if ratio > 0 else "N/A(폴백)"
    print(f"{hour:>3}시 {cur_skt:>8,} {fc_crude:>18,} {fc_ratio:>22,} {ratio_str:>8}")

def acc(preds, actual):
    if not preds or not actual:
        return None
    avg = sum(preds) / len(preds)
    return round((1 - abs(avg - actual) / abs(actual)) * 100, 1), avg

print()
print(f"실제 마감값: {act_skt:,}")
a_old = acc(fc_crude_list, act_skt)
a_new = acc(fc_ratio_list, act_skt)
print(f"[구방식] 11~19시 예측 평균={a_old[1]:,.0f}  |  정확도={a_old[0]}%")
print(f"[신방식] 11~19시 예측 평균={a_new[1]:,.0f}  |  정확도={a_new[0]}%")
