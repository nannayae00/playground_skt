import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

# ── 날짜 범위: 최근 90일 영업일 (D-1까지 확정된 날만) ──
import sys as _s
sys.path.insert(0, os.path.dirname(__file__))
from bw_engine import is_zero_day

today = datetime.now()
dates = []
d = today - timedelta(days=1)
while len(dates) < 90:
    ds = d.strftime('%Y-%m-%d')
    if not is_zero_day(ds):
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            data = doc.to_dict()
            actual = data.get('mno_out', {}).get('S')
            if actual and actual > 0:
                dates.append(ds)
    d -= timedelta(days=1)
dates.reverse()  # 오래된 순
print(f"수집된 날짜 수: {len(dates)}  ({dates[0]} ~ {dates[-1]})")

# ── 각 날짜의 hour별 cumulative 캐시 ──
HOURS = [11, 12, 13, 14, 15, 17, 19]

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
hour_cum_cache = {}  # (ds, hour) -> cum
for ds in dates:
    doc = db.collection('ktoa_daily').document(ds).get()
    actuals[ds] = doc.to_dict().get('mno_out', {}).get('S')
    for h in HOURS:
        hour_cum_cache[(ds, h)] = get_hour_cum(ds, h)

print("데이터 수집 완료, 백테스트 시작")

def weighted_mean(vals, max_w=5.0):
    # vals: 최신순 리스트
    n = len(vals)
    if n == 0:
        return None
    if n == 1:
        return vals[0]
    step = (max_w - 0.5) / (n - 1)
    weights = [max(0.5, max_w - step * i) for i in range(n)]
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)

# ── 후보 방식별 오차 집계 ──
results = {h: {c: [] for c in ['A_mean20', 'B_median20', 'C_wmean30', 'D_median40', 'E_add_mean20', 'F_add_median20']} for h in HOURS}

TOP_N_STD = 20

for idx, test_ds in enumerate(dates):
    prior = dates[:idx]  # 트레일링 윈도우 (미래데이터 없음)
    if len(prior) < 10:
        continue
    test_actual = actuals[test_ds]
    if not test_actual:
        continue

    for h in HOURS:
        today_cum = hour_cum_cache.get((test_ds, h))
        if not today_cum or today_cum <= 0:
            continue

        # 과거 데이터에서 (cum, actual) 쌍 최신순 수집
        pairs = []
        for pd in reversed(prior):
            a = actuals.get(pd)
            c = hour_cum_cache.get((pd, h))
            if a and a > 0 and c and c > 0:
                pairs.append((c, a))
            if len(pairs) >= 40:
                break

        if len(pairs) < 10:
            continue

        ratios_20 = [c / a for c, a in pairs[:TOP_N_STD]]
        ratios_40 = [c / a for c, a in pairs[:40]]
        remain_20 = [a - c for c, a in pairs[:TOP_N_STD]]

        # A: 현재 방식 (top20 평균)
        r = statistics.mean(ratios_20)
        if r > 0:
            fc = today_cum / r
            results[h]['A_mean20'].append(abs(fc - test_actual) / test_actual * 100)

        # B: top20 중앙값
        r = statistics.median(ratios_20)
        if r > 0:
            fc = today_cum / r
            results[h]['B_median20'].append(abs(fc - test_actual) / test_actual * 100)

        # C: top30 가중평균(최근일 가중, max_w=5)
        pool30 = ratios_40[:30] if len(ratios_40) >= 30 else ratios_40
        r = weighted_mean(pool30, max_w=5.0)
        if r and r > 0:
            fc = today_cum / r
            results[h]['C_wmean30'].append(abs(fc - test_actual) / test_actual * 100)

        # D: top40 중앙값
        if len(ratios_40) >= 20:
            r = statistics.median(ratios_40)
            if r > 0:
                fc = today_cum / r
                results[h]['D_median40'].append(abs(fc - test_actual) / test_actual * 100)

        # E: 가산모델 (잔여량 평균)
        rem = statistics.mean(remain_20)
        fc = today_cum + rem
        if fc > 0:
            results[h]['E_add_mean20'].append(abs(fc - test_actual) / test_actual * 100)

        # F: 가산모델 (잔여량 중앙값)
        rem = statistics.median(remain_20)
        fc = today_cum + rem
        if fc > 0:
            results[h]['F_add_median20'].append(abs(fc - test_actual) / test_actual * 100)

print()
print(f"{'시간':>4} {'n':>4}  " + "  ".join(f"{c:>15}" for c in ['A_mean20', 'B_median20', 'C_wmean30', 'D_median40', 'E_add_mean20', 'F_add_median20']))
for h in HOURS:
    n = len(results[h]['A_mean20'])
    row = f"{h:>4}시 {n:>4}  "
    for c in ['A_mean20', 'B_median20', 'C_wmean30', 'D_median40', 'E_add_mean20', 'F_add_median20']:
        vals = results[h][c]
        mape = statistics.mean(vals) if vals else float('nan')
        row += f"{mape:>14.1f}%  "
    print(row)
