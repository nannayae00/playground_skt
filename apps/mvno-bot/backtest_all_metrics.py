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
            data = doc.to_dict()
            if data.get('mvno_in') and data.get('mvno_out'):
                dates.append(ds)
    d -= timedelta(days=1)
dates.reverse()
print(f"수집된 날짜 수: {len(dates)}  ({dates[0]} ~ {dates[-1]})")

HOURS = list(range(11, 20))

# ── 필드 정의: (그룹, 키, 실적dict키, 예측dict키)
FIELDS = [
    ('mno_out', 'K'),
    ('mno_out', 'L'),
    ('mvno_in', 'SM'),
    ('mvno_in', 'KM'),
    ('mvno_in', 'LM'),
    ('mvno_out', 'SM'),
    ('mvno_out', 'KM'),
    ('mvno_out', 'LM'),
]
FC_FIELD_MAP = {'mno_out': 'forecast_mno_out', 'mvno_in': 'forecast_mvno_in', 'mvno_out': 'forecast_mvno_out'}

# ── 일별 실적(마감) + 시간별 문서 캐시 ──
actuals = {}   # ds -> {group: {key: val}}
hourly_cache = {}  # ds -> {hour: doc_dict}
for ds in dates:
    daily = db.collection('ktoa_daily').document(ds).get().to_dict()
    actuals[ds] = {g: (daily.get(g, {}) or {}) for g in ['mno_out', 'mvno_in', 'mvno_out']}
    hdocs = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    by_hour = {}
    for h in HOURS:
        cands = sorted((hd for hd in hdocs if hd.id.startswith(f"{ds}_{h:02d}")), key=lambda x: x.id)
        if cands:
            by_hour[h] = cands[0].to_dict()
    hourly_cache[ds] = by_hour

print("데이터 수집 완료, 백테스트 시작")

weekdays = {ds: datetime.strptime(ds, '%Y-%m-%d').weekday() for ds in dates}

def weekday_median_ratio(prior, test_wd, group, key, hour, top_n=40):
    ratios = []
    for pd in reversed(prior):
        if weekdays[pd] != test_wd:
            continue
        a = actuals[pd][group].get(key)
        hd = hourly_cache[pd].get(hour)
        c = hd.get(group, {}).get(key) if hd else None
        if a and a > 0 and c and c > 0:
            ratios.append(c / a)
        if len(ratios) >= top_n:
            break
    if len(ratios) < 8:
        return None
    return statistics.median(ratios)

results = {}  # field -> {'old': [], 'new': []}
for group, key in FIELDS:
    results[(group, key)] = {'old': [], 'new': []}

for idx, test_ds in enumerate(dates):
    prior = dates[:idx]
    if len(prior) < 20:
        continue
    test_wd = weekdays[test_ds]

    for group, key in FIELDS:
        actual = actuals[test_ds][group].get(key)
        if not actual or actual <= 0:
            continue
        fc_field = FC_FIELD_MAP[group]

        for hour in HOURS:
            hd = hourly_cache[test_ds].get(hour)
            if not hd:
                continue
            cur = hd.get(group, {}).get(key, 0) or 0
            if not cur:
                continue

            # OLD: 그 시점에 저장된 패턴기반 예측값
            old_fc = hd.get(fc_field, {}).get(key, 0) or 0
            if old_fc:
                results[(group, key)]['old'].append(abs(old_fc - actual) / actual * 100)

            # NEW: 요일필터 median 완료율곡선 (일반화)
            ratio = weekday_median_ratio(prior, test_wd, group, key, hour)
            elapsed = max(1, hour - 10)
            new_fc = (cur / ratio) if ratio and ratio > 0 else (cur * 10 / elapsed)
            results[(group, key)]['new'].append(abs(new_fc - actual) / actual * 100)

print()
print(f"{'항목':>14}   {'구방식(패턴) MAPE':>18}   {'신방식(요일필터곡선) MAPE':>22}   n")
for group, key in FIELDS:
    r = results[(group, key)]
    old_mape = statistics.mean(r['old']) if r['old'] else float('nan')
    new_mape = statistics.mean(r['new']) if r['new'] else float('nan')
    print(f"{group}.{key:>6}   {old_mape:>16.1f}%   {new_mape:>20.1f}%   old_n={len(r['old'])} new_n={len(r['new'])}")
