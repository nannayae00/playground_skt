import sys, os, logging, statistics
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.WARNING)

import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

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

# 날짜별 시간대별 "단일 최초값"과 "10분단위 평균값" 둘 다 미리 계산
actuals = {}
single_cache = {}   # (ds,hour) -> 단일값(:01 등 최초)
avg_cache = {}       # (ds,hour) -> 그 시간대 모든 샘플 평균값
for ds in dates:
    doc = db.collection('ktoa_daily').document(ds).get()
    actuals[ds] = doc.to_dict().get('mno_out', {}).get('S')
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    for h in HOURS:
        candidates = sorted((hd for hd in hdocs if hd.id.startswith(f"{ds}_{h:02d}")), key=lambda x: x.id)
        if not candidates:
            continue
        single_cache[(ds, h)] = candidates[0].to_dict().get('mno_out', {}).get('S')
        vals = [c.to_dict().get('mno_out', {}).get('S') for c in candidates]
        vals = [v for v in vals if v]
        if vals:
            avg_cache[(ds, h)] = sum(vals) / len(vals)

print("데이터 수집 완료, 백테스트 시작")

weekdays = {ds: datetime.strptime(ds, '%Y-%m-%d').weekday() for ds in dates}

results = {h: {'A_single': [], 'B_avg_smooth': []} for h in HOURS}

for idx, test_ds in enumerate(dates):
    prior = dates[:idx]
    if len(prior) < 15:
        continue
    test_actual = actuals[test_ds]
    if not test_actual:
        continue
    test_wd = weekdays[test_ds]

    for h in HOURS:
        # 오늘(테스트일) 값은 실제 리포트 생성 시점과 동일하게 "단일 최초값" 사용
        today_cum = single_cache.get((test_ds, h))
        if not today_cum or today_cum <= 0:
            continue

        pairs_single = []  # (cum, actual)
        pairs_avg = []
        for pd in reversed(prior):
            if weekdays[pd] != test_wd:
                continue
            a = actuals.get(pd)
            c1 = single_cache.get((pd, h))
            c2 = avg_cache.get((pd, h))
            if a and a > 0:
                if c1 and c1 > 0:
                    pairs_single.append((c1, a))
                if c2 and c2 > 0:
                    pairs_avg.append((c2, a))
            if len(pairs_single) >= 40 and len(pairs_avg) >= 40:
                break

        if len(pairs_single) >= 8:
            ratios = [c / a for c, a in pairs_single[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['A_single'].append(abs(fc - test_actual) / test_actual * 100)

        if len(pairs_avg) >= 8:
            ratios = [c / a for c, a in pairs_avg[:40]]
            r = statistics.median(ratios)
            if r > 0:
                fc = today_cum / r
                results[h]['B_avg_smooth'].append(abs(fc - test_actual) / test_actual * 100)

print()
print(f"{'시간':>4}   {'A_single(현재배포)':>20}   {'B_avg_smooth(10분평균)':>22}")
for h in HOURS:
    a = results[h]['A_single']
    b = results[h]['B_avg_smooth']
    a_mape = statistics.mean(a) if a else float('nan')
    b_mape = statistics.mean(b) if b else float('nan')
    print(f"{h:>4}시   {a_mape:>18.1f}%(n={len(a)})   {b_mape:>20.1f}%(n={len(b)})")
