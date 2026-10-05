import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime
from calendar import monthrange

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
_real_db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# ── 문서 단건 조회(get) + ktoa_hourly date-where 쿼리 캐싱 프록시:
# 같은 문서/쿼리가 여러 날짜의 예측 계산에서 반복 조회되는 것(월 전체 bw합,
# D-10 rolling avg, 시간대별 진행률 lookback 등)을 캐싱해 Firestore 왕복을 대폭 줄임.
_doc_cache = {}
_hourly_where_cache = {}

# ★ 백테스트 대상 날짜(target date)의 ktoa_daily 문서는 이미 과거라 mno_out.S가
# 실제로는 마감 확정돼 있음. 하지만 실제 프로덕션에서 predict_monthly()가 19시에
# 불렸을 때는 그 시점에 아직 20:25 마감 전이라 오늘 값이 미확정 상태였음.
# 이 마스킹 없이 부르면 구로직/신로직 모두 "이미 확정된 오늘 실적"을 그대로 갖다써서
# _today_confirmed=True가 되어 둘 다 동일한(사실상 정답을 아는) 값이 나와버림.
# → 테스트 대상 날짜만 mno_out.S를 숨겨서 "그날 19시 시점"을 재현.
_simulate_open_date = [None]

class _MaskedSnapshot:
    def __init__(self, snap):
        self._snap = snap
    @property
    def exists(self):
        return self._snap.exists
    def to_dict(self):
        d = dict(self._snap.to_dict() or {})
        mo = dict(d.get('mno_out') or {})
        mo.pop('S', None)
        d['mno_out'] = mo
        return d

class _CachedDocRef:
    def __init__(self, coll, doc_id):
        self.coll, self.doc_id = coll, doc_id
    def get(self):
        key = (self.coll, self.doc_id)
        if key not in _doc_cache:
            _doc_cache[key] = _real_db.collection(self.coll).document(self.doc_id).get()
        snap = _doc_cache[key]
        if self.coll == 'ktoa_daily' and self.doc_id == _simulate_open_date[0]:
            return _MaskedSnapshot(snap)
        return snap
    def update(self, *a, **kw):
        return _real_db.collection(self.coll).document(self.doc_id).update(*a, **kw)
    def set(self, *a, **kw):
        return _real_db.collection(self.coll).document(self.doc_id).set(*a, **kw)

class _StaticStream:
    def __init__(self, items):
        self.items = items
    def stream(self):
        return iter(self.items)

class _CachedCollection:
    def __init__(self, name):
        self.name = name
    def document(self, doc_id):
        return _CachedDocRef(self.name, doc_id)
    def where(self, field, op, value):
        if self.name == 'ktoa_hourly' and field == 'date' and op == '==':
            if value not in _hourly_where_cache:
                _hourly_where_cache[value] = list(_real_db.collection(self.name).where(field, op, value).stream())
            return _StaticStream(_hourly_where_cache[value])
        return _real_db.collection(self.name).where(field, op, value)

class _CachedClient:
    def collection(self, name):
        return _CachedCollection(name)

db = _CachedClient()

import forecast_engine
import bw_engine

forecast_engine._get_db = lambda: db
bw_engine._get_db = lambda: db

import functools
_orig_series = forecast_engine._get_month_daily_series
forecast_engine._get_month_daily_series = functools.lru_cache(maxsize=300)(_orig_series)

from bw_engine import is_zero_day, get_bw_final

# ── 실제 월마감 값 조회 ──────────────────────────────────
def get_month_actual(year, month):
    last_day = monthrange(year, month)[1]
    for d in range(last_day, 0, -1):
        ds = f"{year:04d}-{month:02d}-{d:02d}"
        doc = db.collection('ktoa_daily').document(ds).get()
        if not doc.exists:
            continue
        data = doc.to_dict()
        v = (data.get('cum_mno_out') or {}).get('S')
        if v:
            return int(v)
    return None

def get_today_skt_at_hour(date_str, hour):
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', date_str).stream())
    candidates = sorted(
        (h for h in hdocs if h.id.startswith(f"{date_str}_{hour:02d}")),
        key=lambda h: h.id
    )
    if not candidates:
        return None
    return candidates[0].to_dict().get('mno_out', {}).get('S')

# ── OLD 로직: cum_skt = cum_skt_db (오늘 미반영, 전일까지 확정 누적만) ──
def predict_monthly_old(date_str, today_skt, current_hour=19):
    from predict_gemini import get_similar_days, get_hourly_pattern, call_gemini_forecast

    d = datetime.strptime(date_str, '%Y-%m-%d')
    year, month, day = d.year, d.month, d.day

    goal = forecast_engine.get_tout_goal(year, month)
    bw = get_bw_final(date_str)

    cum_skt_db = 0
    elapsed_bw = 0.0
    try:
        for _d in range(1, day + 1):
            _ds = f"{year:04d}-{month:02d}-{_d:02d}"
            _doc = db.collection('ktoa_daily').document(_ds).get()
            if not _doc.exists:
                continue
            _dd = _doc.to_dict()
            _bw = float(_dd.get('bw_ai_prev') or _dd.get('bw_manual') or 0)
            if not _bw or _bw <= 0:
                continue
            _skt = _dd.get('mno_out', {}).get('S', None)
            if _skt is None:
                continue
            elapsed_bw += _bw
            cum_skt_db += int(_skt)
    except Exception:
        pass

    avg_recent = forecast_engine._get_rolling_avg(date_str, top_n=10, max_w=5.0)
    avg_trend = forecast_engine._get_rolling_avg(date_str, top_n=10, max_w=10.0)

    last_day = monthrange(year, month)[1]
    _total_ai = _total_man = 0.0
    for d2 in range(1, last_day + 1):
        ds2 = f"{year:04d}-{month:02d}-{d2:02d}"
        data = (db.collection('ktoa_daily').document(ds2).get().to_dict() or {})
        _total_ai += float(data.get('bw_ai_prev') or 0)
        _total_man += float(data.get('bw_manual') or data.get('bw_ai_prev') or 0)
    rbw_ai = round(_total_ai - elapsed_bw, 3)
    rbw_man = round(_total_man - elapsed_bw, 3)

    # ★ OLD: 오늘 실적 cum_skt에 미반영 (fc_daily 계산 안 하고 안 더함)
    cum_skt = cum_skt_db

    _p1 = int(cum_skt + avg_recent * rbw_ai) if rbw_ai > 0 else cum_skt
    _p2 = int(cum_skt + avg_recent * rbw_man) if rbw_man > 0 else cum_skt
    _p3 = int(cum_skt + avg_trend * rbw_ai) if rbw_ai > 0 else cum_skt
    _p4 = int(cum_skt + avg_trend * rbw_man) if rbw_man > 0 else cum_skt
    _sorted = sorted([_p1, _p2, _p3, _p4])
    fc_low, fc_high = _sorted[0], _sorted[3]
    fc_mid = int(round((_sorted[1] + _sorted[2]) / 2))

    # 과거배수법 + 편향보정 (신구 공통 로직이라 동일 적용)
    rbw_w2 = round((rbw_ai + rbw_man) / 2, 3)
    _total_bw_mid = elapsed_bw + rbw_w2
    progress_ratio = elapsed_bw / _total_bw_mid if _total_bw_mid > 0 else 0
    try:
        hist = forecast_engine._get_historical_month_ratio(date_str, progress_ratio)
    except Exception:
        hist = None
    if hist and cum_skt > 0:
        w_hist = max(0.0, min(1.0, 1 - progress_ratio / forecast_engine.HIST_BLEND_THRESHOLD))
        if w_hist > 0:
            hist_mid = cum_skt * hist['ratio_mid']
            fc_mid = int(round(w_hist * hist_mid + (1 - w_hist) * fc_mid))
    _bias = forecast_engine._bias_correction(progress_ratio)
    if _bias:
        fc_mid = int(round(fc_mid / (1 + _bias)))

    return {'fc_mid': fc_mid, 'cum_skt': cum_skt, 'progress': progress_ratio}


def predict_monthly_new(date_str, today_skt, current_hour=19):
    r = forecast_engine.predict_monthly(date_str, today_skt, save_to_daily=False, current_hour=current_hour)
    return {'fc_mid': r['fc_mid'], 'cum_skt': r['cum_skt'], 'progress': r['progress_ratio']}


# ── 백테스트 실행 ──────────────────────────────────────────
results = []  # (date, old_mid, new_mid, actual_month)

for (year, month) in [(2026, 6), (2026, 7), (2026, 8)]:
    actual = get_month_actual(year, month)
    if not actual:
        print(f"{year}-{month:02d}: 실제 마감값 없음, 스킵")
        continue
    last_day = monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        if is_zero_day(date_str):
            continue
        today_skt = get_today_skt_at_hour(date_str, 19)
        if today_skt is None:
            continue
        try:
            _simulate_open_date[0] = date_str
            old = predict_monthly_old(date_str, today_skt, current_hour=19)
            new = predict_monthly_new(date_str, today_skt, current_hour=19)
        except Exception as e:
            print(f"{date_str}: 계산 실패 {e}")
            continue
        finally:
            _simulate_open_date[0] = None
        results.append((date_str, old['fc_mid'], new['fc_mid'], actual))
        print(f"{date_str}  실적19h={today_skt:>5}  구로직={old['fc_mid']:>6,}  신로직={new['fc_mid']:>6,}  실제마감={actual:>6,}  "
              f"구오차={abs(old['fc_mid']-actual):>5,}  신오차={abs(new['fc_mid']-actual):>5,}")

print()
print(f"샘플 수: {len(results)}")
if results:
    old_errs = [abs(o - a) for _, o, n, a in results]
    new_errs = [abs(n - a) for _, o, n, a in results]
    old_mae = sum(old_errs) / len(old_errs)
    new_mae = sum(new_errs) / len(new_errs)
    old_mape = sum(abs(o - a) / a for _, o, n, a in results) / len(results) * 100
    new_mape = sum(abs(n - a) / a for _, o, n, a in results) / len(results) * 100
    print(f"[전체] 구로직 MAE={old_mae:,.1f} (MAPE {old_mape:.2f}%)  |  신로직 MAE={new_mae:,.1f} (MAPE {new_mape:.2f}%)")
    win = sum(1 for _, o, n, a in results if abs(n - a) < abs(o - a))
    print(f"신로직이 더 정확한 날: {win}/{len(results)}")

    print()
    print("[월별]")
    for (year, month) in [(2026, 6), (2026, 7), (2026, 8)]:
        sub = [(o, n, a) for ds, o, n, a in results if ds.startswith(f"{year:04d}-{month:02d}")]
        if not sub:
            continue
        om = sum(abs(o - a) for o, n, a in sub) / len(sub)
        nm = sum(abs(n - a) for o, n, a in sub) / len(sub)
        print(f"  {year}-{month:02d} (n={len(sub)}): 구로직 MAE={om:,.1f}  |  신로직 MAE={nm:,.1f}")
