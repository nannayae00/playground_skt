import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO)

import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

import forecast_engine
import bw_engine
forecast_engine._get_db = lambda: db
bw_engine._get_db = lambda: db

# 1) 06-02 19시 완료율 계산에 실제로 어떤 과거 표본이 잡혔는지 원본으로 재현
from datetime import datetime, timedelta
import statistics

date_str = '2026-06-02'
hour = 19
d = datetime.strptime(date_str, '%Y-%m-%d')
cur = d - timedelta(days=1)
checked = 0
top_n = 20
print(f"=== {date_str} {hour}시 완료율 계산에 쓰인 과거 표본(D-1부터 역순) ===")
samples = []
while len(samples) < top_n and checked < top_n * 3:
    ds = cur.strftime('%Y-%m-%d')
    checked += 1
    cur -= timedelta(days=1)
    if (d - cur).days > 90:
        break
    daily_doc = db.collection('ktoa_daily').document(ds).get()
    if not daily_doc.exists:
        continue
    actual = daily_doc.to_dict().get('mno_out', {}).get('S')
    if not actual or actual <= 0:
        continue
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    if not candidates:
        print(f"  {ds}: 실제마감={actual}  -> {hour}시대 hourly 문서 없음 (스킵)")
        continue
    cum = candidates[0].to_dict().get('mno_out', {}).get('S')
    doc_id_used = candidates[0].id
    if cum and cum > 0:
        ratio = cum / actual
        samples.append(ratio)
        print(f"  {ds}: 실제마감={actual:>5}  {hour}시누적({doc_id_used})={cum:>5}  ratio={ratio:.4f} ({ratio*100:.1f}%)")
    else:
        print(f"  {ds}: 실제마감={actual}  {hour}시 문서({doc_id_used})에 mno_out.S 없음/0 (스킵)")

print()
print(f"표본 수: {len(samples)}")
if samples:
    print(f"평균 ratio = {statistics.mean(samples):.4f} ({statistics.mean(samples)*100:.2f}%)")
    print(f"중앙값 ratio = {statistics.median(samples):.4f} ({statistics.median(samples)*100:.2f}%)")
    print(f"min={min(samples):.4f}  max={max(samples):.4f}")

print()
print("=== 실제 predict_monthly() 호출 재현 (오늘=06-02, 실적19h=1699, mask 적용) ===")

# 마스킹: 06-02 자신의 mno_out.S 숨기기 (실시간 상황 재현)
_doc_cache = {}
class _MaskedSnapshot:
    def __init__(self, snap):
        self._snap = snap
    @property
    def exists(self):
        return self._snap.exists
    def to_dict(self):
        dd = dict(self._snap.to_dict() or {})
        mo = dict(dd.get('mno_out') or {})
        mo.pop('S', None)
        dd['mno_out'] = mo
        return dd

class _CachedDocRef:
    def __init__(self, coll, doc_id):
        self.coll, self.doc_id = coll, doc_id
    def get(self):
        key = (self.coll, self.doc_id)
        if key not in _doc_cache:
            _doc_cache[key] = db.collection(self.coll).document(self.doc_id).get()
        snap = _doc_cache[key]
        if self.coll == 'ktoa_daily' and self.doc_id == date_str:
            return _MaskedSnapshot(snap)
        return snap
    def set(self, *a, **kw): pass
    def update(self, *a, **kw): pass

class _CachedCollection:
    def __init__(self, name): self.name = name
    def document(self, doc_id): return _CachedDocRef(self.name, doc_id)
    def where(self, *a, **kw): return db.collection(self.name).where(*a, **kw)

class _CachedClient:
    def collection(self, name): return _CachedCollection(name)

masked_db = _CachedClient()
forecast_engine._get_db = lambda: masked_db
bw_engine._get_db = lambda: masked_db

result = forecast_engine.predict_monthly(date_str, 1699, save_to_daily=False, current_hour=19)
print()
print("결과:", {k: result[k] for k in ['fc_low','fc_mid','fc_high','fc_daily','cum_skt','progress_ratio']})
