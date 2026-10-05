import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
_real_db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# 캐싱 프록시 (문서 get + ktoa_hourly date-where 쿼리)
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

from bw_engine import is_zero_day

today = datetime.now()
dates = []
d = today - timedelta(days=1)
while len(dates) < 156:
    ds = d.strftime('%Y-%m-%d')
    if not is_zero_day(ds):
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            actual = doc.to_dict().get('mno_out', {}).get('S')
            if actual and actual > 0:
                dates.append(ds)
    d -= timedelta(days=1)
dates.reverse()
print(f"수집된 날짜 수: {len(dates)}  ({dates[0]} ~ {dates[-1]})")

HOURS = [11, 12, 13, 14, 15]

def get_hour_cum(ds, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    if not candidates:
        return None
    return candidates[0].to_dict().get('mno_out', {}).get('S')

actuals = {}
hour_cum_cache = {}
for ds in dates:
    doc = db.collection('ktoa_daily').document(ds).get()
    actuals[ds] = doc.to_dict().get('mno_out', {}).get('S')
    for h in HOURS:
        hour_cum_cache[(ds, h)] = get_hour_cum(ds, h)

print("데이터 수집 완료, 실제 forecast_engine._get_hour_completion_ratio()로 검증 시작")

# ── 트레일링 윈도우: _get_hour_completion_ratio는 항상 "그 날짜 기준 과거"만 보므로
# (Firestore에 미래 날짜 데이터가 없어 자동으로 트레일링 윈도우가 됨) 그대로 호출.
results = {h: [] for h in HOURS}
for test_ds in dates:
    test_actual = actuals[test_ds]
    if not test_actual:
        continue
    for h in HOURS:
        today_cum = hour_cum_cache.get((test_ds, h))
        if not today_cum or today_cum <= 0:
            continue
        ratio = forecast_engine._get_hour_completion_ratio(test_ds, h)
        if ratio <= 0:
            continue
        fc = today_cum / ratio
        results[h].append(abs(fc - test_actual) / test_actual * 100)

print()
for h in HOURS:
    vals = results[h]
    mape = statistics.mean(vals) if vals else float('nan')
    print(f"{h:>4}시  MAPE={mape:.1f}%  (n={len(vals)})")
