import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

from bw_engine import is_zero_day, get_bw_final

today = datetime.now()
dates = []
d = today - timedelta(days=1)
while len(dates) < 175 and (today - d).days < 185:
    ds = d.strftime('%Y-%m-%d')
    if not is_zero_day(ds):
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            data = doc.to_dict()
            actual = data.get('mno_out', {}).get('S')
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
weekdays = {}
bw_map = {}
hour_cum_cache = {}
for ds in dates:
    doc = db.collection('ktoa_daily').document(ds).get()
    actuals[ds] = doc.to_dict().get('mno_out', {}).get('S')
    weekdays[ds] = datetime.strptime(ds, '%Y-%m-%d').weekday()
    bw_map[ds] = get_bw_final(ds, doc.to_dict())
    for h in HOURS:
        hour_cum_cache[(ds, h)] = get_hour_cum(ds, h)

print("데이터 수집 완료, 백테스트 시작")

results = {h: {c: [] for c in ['D_all_median40', 'G_dow_median', 'H_bw_median20']} for h in HOURS}
WD_NAMES = ['월', '화', '수', '목', '금', '토', '일']

for idx, test_ds in enumerate(dates):
    prior = dates[:idx]
    if len(prior) < 15:
        continue
    test_actual = actuals[test_ds]
    if not test_actual:
        continue
    test_wd = weekdays[test_ds]
    test_bw = bw_map[test_ds]

    for h in HOURS:
        today_cum = hour_cum_cache.get((test_ds, h))
        if not today_cum or today_cum <= 0:
            continue

        pairs_all = []       # (cum, actual) 최신순, 전체
        pairs_dow = []       # 같은 요일만
        pairs_bw = []        # (bw차이, cum, actual) - 이후 정렬
        for pd in reversed(prior):
            a = actuals.get(pd)
            c = hour_cum_cache.get((pd, h))
            if a and a > 0 and c and c > 0:
                pairs_all.append((c, a))
                if weekdays[pd] == test_wd:
                    pairs_dow.append((c, a))
                pairs_bw.append((abs(bw_map[pd] - test_bw), c, a))
            if len(pairs_all) >= 40 and len(pairs_dow) >= 40:
                break

        # D: 전체 top40 중앙값 (현재 배포된 방식)
        if len(pairs_all) >= 10:
            ratios = [c / a for c, a in pairs_all[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['D_all_median40'].append(abs(fc - test_actual) / test_actual * 100)

        # G: 같은 요일만, 중앙값 (표본 되는대로, 최소 8개)
        if len(pairs_dow) >= 8:
            ratios = [c / a for c, a in pairs_dow[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['G_dow_median'].append(abs(fc - test_actual) / test_actual * 100)

        # H: bw(영업일수) 가장 비슷한 날 top20, 중앙값
        if len(pairs_bw) >= 10:
            pairs_bw_sorted = sorted(pairs_bw, key=lambda x: x[0])[:20]
            ratios = [c / a for _, c, a in pairs_bw_sorted]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['H_bw_median20'].append(abs(fc - test_actual) / test_actual * 100)

print()
print(f"{'시간':>4}   " + "  ".join(f"{c:>10}(n)" for c in ['D_all_median40', 'G_dow_median', 'H_bw_median20']))
for h in HOURS:
    row = f"{h:>4}시  "
    for c in ['D_all_median40', 'G_dow_median', 'H_bw_median20']:
        vals = results[h][c]
        mape = statistics.mean(vals) if vals else float('nan')
        row += f"{mape:>8.1f}%(n={len(vals):>3})  "
    print(row)
