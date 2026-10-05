import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

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

from bw_engine import is_zero_day

# ── 최근 7영업일 (9/30 기준, 실적 확정된 날만) ──
anchor = datetime(2026, 9, 30)
dates = []
d = anchor
while len(dates) < 7:
    ds = d.strftime('%Y-%m-%d')
    if not is_zero_day(ds):
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            actual = doc.to_dict().get('mno_out', {}).get('S')
            if actual and actual > 0:
                dates.append(ds)
    d -= timedelta(days=1)
dates.reverse()
print(f"검증 대상 7영업일: {dates}")
print()

HOURS = list(range(11, 20))

def get_hour_doc(ds, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
        key=lambda h: h.id
    )
    return candidates[0].to_dict() if candidates else None

def acc_list(pred_list, actual):
    """[수정된 방식] 시간대별 정확도 먼저 계산 후 평균, 0~100% 클램프"""
    if not pred_list or not actual:
        return None
    accs = [max(0.0, 1 - abs(p - actual) / abs(actual)) for p in pred_list]
    return round(sum(accs) / len(accs) * 100, 1)

print(f"{'날짜':>12} {'실제마감':>8}   {'구방식(패턴) 평균예측':>12} {'구정확도':>8}   {'신방식(완료율곡선) 평균예측':>14} {'신정확도':>8}")

summary = []
for ds in dates:
    daily = db.collection('ktoa_daily').document(ds).get().to_dict()
    actual = daily.get('mno_out', {}).get('S')
    if not actual:
        continue

    old_preds = []
    new_preds = []
    for hour in HOURS:
        hd = get_hour_doc(ds, hour)
        if not hd:
            continue
        cur = hd.get('mno_out', {}).get('S', 0) or 0
        if not cur:
            continue
        # 구방식: 그 당시 저장된 패턴기반 예측값 (실제 그때 메시지에 뜬 값)
        old_fc = hd.get('forecast_mno_out', {}).get('S', 0) or 0
        if old_fc:
            old_preds.append(old_fc)
        # 신방식: 지금 배포된 요일필터 완료율곡선으로 재계산 (트레일링 윈도우, 미래데이터 없음)
        ratio = forecast_engine._get_hour_completion_ratio(ds, hour)
        elapsed = max(1, hour - 10)
        new_fc = int(cur / ratio) if ratio > 0 else int(cur * 10 / elapsed)
        new_preds.append(new_fc)

    old_avg = sum(old_preds) / len(old_preds) if old_preds else None
    new_avg = sum(new_preds) / len(new_preds) if new_preds else None
    old_acc = acc_list(old_preds, actual)
    new_acc = acc_list(new_preds, actual)

    print(f"{ds:>12} {actual:>8,}   {old_avg:>12,.0f} {old_acc if old_acc is not None else '-':>7}%   {new_avg:>14,.0f} {new_acc if new_acc is not None else '-':>7}%")
    summary.append((ds, actual, old_acc, new_acc))

print()
valid = [(o, n) for _, _, o, n in summary if o is not None and n is not None]
if valid:
    avg_old = sum(o for o, n in valid) / len(valid)
    avg_new = sum(n for o, n in valid) / len(valid)
    print(f"[7일 평균] 구방식(패턴) 정확도={avg_old:.1f}%  |  신방식(완료율곡선) 정확도={avg_new:.1f}%")
