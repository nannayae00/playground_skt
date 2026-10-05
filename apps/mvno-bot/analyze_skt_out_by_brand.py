import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

DATES = [f"2026-09-{d:02d}" for d in range(15, 31)]
MNO_SELF = {'SKT', 'KT', 'LGU+'}

per_date_brand = {}   # date -> {brand: skt_inflow}
per_date_total = {}   # date -> sum (검증용, mno_out.S와 비교)

for ds in DATES:
    docs = list(db.collection('ktoa_mvno_brand_in').where('date', '==', ds).stream())
    brand_vals = {}
    total = 0
    for doc in docs:
        d = doc.to_dict()
        brand = d.get('brand')
        if brand in MNO_SELF:
            continue
        v = (d.get('inflows', {}) or {}).get('SKT', 0) or 0
        if v:
            brand_vals[brand] = v
            total += v
    per_date_brand[ds] = brand_vals
    per_date_total[ds] = total

print("===== 검증: 브랜드 합산 vs mno_out.S =====\n")
for ds in DATES:
    doc = db.collection('ktoa_daily').document(ds).get()
    dd = doc.to_dict() if doc.exists else {}
    official = (dd.get('mno_out', {}) or {}).get('S')
    calc = per_date_total.get(ds)
    match = '✓' if official == calc else '✗'
    print(f"  {ds} | 공식 mno_out.S={official} | 브랜드합산={calc} | {match}")

# 기준선(베이스라인): 9/15~9/24 중 데이터 있는 평일 평균
baseline_dates = [ds for ds in DATES if ds <= '2026-09-24' and per_date_total.get(ds, 0) > 0]
spike_dates = ['2026-09-28', '2026-09-29', '2026-09-30']

all_brands = set()
for ds in DATES:
    all_brands.update(per_date_brand.get(ds, {}).keys())

rows = []
for brand in all_brands:
    baseline_vals = [per_date_brand[ds].get(brand, 0) for ds in baseline_dates]
    spike_vals = [per_date_brand[ds].get(brand, 0) for ds in spike_dates]
    baseline_avg = sum(baseline_vals) / len(baseline_vals) if baseline_vals else 0
    spike_avg = sum(spike_vals) / len(spike_vals) if spike_vals else 0
    delta = spike_avg - baseline_avg
    rows.append((brand, baseline_avg, spike_avg, delta))

rows.sort(key=lambda x: -x[3])

print()
print(f"===== 베이스라인(9/15~9/24 평일, {len(baseline_dates)}일 평균) vs 스파이크(9/28~9/30 평균) - 증가분 TOP 15 =====\n")
print(f"{'브랜드':<16} {'베이스라인평균':>12} {'스파이크평균':>10} {'증가분':>8}")
for brand, base, spike, delta in rows[:15]:
    print(f"{brand:<16} {base:>12.1f} {spike:>10.1f} {delta:>+8.1f}")

total_baseline = sum(r[1] for r in rows)
total_spike = sum(r[2] for r in rows)
total_delta = sum(r[3] for r in rows)
print()
print(f"전체 합계: 베이스라인 {total_baseline:.1f} -> 스파이크 {total_spike:.1f} (증가 {total_delta:+.1f})")
print()
print("===== TOP 5 브랜드의 일자별 상세 추이 (9/15~9/30) =====\n")
top5 = [r[0] for r in rows[:5]]
header = "날짜       | " + " | ".join(f"{b:>12}" for b in top5)
print(header)
for ds in DATES:
    line = f"{ds} | " + " | ".join(f"{per_date_brand.get(ds,{}).get(b,0):>12}" for b in top5)
    print(line)
