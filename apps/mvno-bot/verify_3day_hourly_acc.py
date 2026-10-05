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

DATES = ['2026-09-28', '2026-09-29', '2026-09-30']
HOURS = list(range(11, 20))

def get_hour_doc(ds, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    return candidates[0].to_dict() if candidates else None

def acc(pred, actual):
    if not pred or not actual:
        return None
    return round(max(0.0, 1 - abs(pred - actual) / abs(actual)) * 100, 1)

for ds in DATES:
    daily = db.collection('ktoa_daily').document(ds).get().to_dict()
    actual = daily.get('mno_out', {}).get('S')
    print(f"=== {ds}  (실제마감={actual:,}) ===")
    print(f"{'시각':>4} {'실적누적':>8} {'구방식예측':>10} {'구정확도':>8} {'신방식예측':>10} {'신정확도':>8}")

    old_preds, new_preds = [], []
    for hour in HOURS:
        hd = get_hour_doc(ds, hour)
        if not hd:
            continue
        cur = hd.get('mno_out', {}).get('S', 0) or 0
        if not cur:
            continue
        old_fc = hd.get('forecast_mno_out', {}).get('S', 0) or 0
        ratio = forecast_engine._get_hour_completion_ratio(ds, hour)
        elapsed = max(1, hour - 10)
        new_fc = int(cur / ratio) if ratio > 0 else int(cur * 10 / elapsed)

        old_acc = acc(old_fc, actual) if old_fc else None
        new_acc = acc(new_fc, actual)

        if old_fc: old_preds.append(old_fc)
        new_preds.append(new_fc)

        print(f"{hour:>3}시 {cur:>8,} {old_fc:>10,} {(str(old_acc)+'%') if old_acc is not None else '-':>8} {new_fc:>10,} {(str(new_acc)+'%') if new_acc is not None else '-':>8}")

    # 평균 정확도 (시간대별 정확도 먼저 → 평균)
    old_accs = [acc(p, actual) for p in old_preds]
    new_accs = [acc(p, actual) for p in new_preds]
    old_avg_acc = round(sum(old_accs) / len(old_accs), 1) if old_accs else None
    new_avg_acc = round(sum(new_accs) / len(new_accs), 1) if new_accs else None
    print(f"[일평균 정확도] 구방식={old_avg_acc}%  |  신방식={new_avg_acc}%")
    print()
