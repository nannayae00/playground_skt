import google.oauth2.credentials
from google.cloud import firestore

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

DATES = ['2026-09-22', '2026-09-23', '2026-09-29', '2026-09-30']
MNO_SELF = {'SKT', 'KT', 'LGU+'}

per_date_brand = {}
per_date_total = {}

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

print("===== 검증 =====")
for ds in DATES:
    doc = db.collection('ktoa_daily').document(ds).get()
    dd = doc.to_dict() if doc.exists else {}
    official = (dd.get('mno_out', {}) or {}).get('S')
    print(f"  {ds} | 공식={official} | 브랜드합산={per_date_total.get(ds)} | {'✓' if official==per_date_total.get(ds) else '✗'}")

baseline_dates = ['2026-09-22', '2026-09-23']
all_brands = set()
for ds in DATES:
    all_brands.update(per_date_brand.get(ds, {}).keys())

rows = []
for brand in all_brands:
    base_vals = [per_date_brand[ds].get(brand, 0) for ds in baseline_dates]
    base_avg = sum(base_vals) / len(base_vals)
    v29 = per_date_brand['2026-09-29'].get(brand, 0)
    v30 = per_date_brand['2026-09-30'].get(brand, 0)
    d29 = v29 - base_avg
    d30 = v30 - base_avg
    rows.append((brand, base_avg, v29, d29, v30, d30, d29 + d30))

rows.sort(key=lambda x: -x[6])

print()
print(f"{'순위':>3} {'브랜드':<16} {'베이스라인(9/22-23평균)':>14} {'9/29':>8} {'9/29증가':>9} {'9/30':>8} {'9/30증가':>9}")
for i, (brand, base, v29, d29, v30, d30, total_d) in enumerate(rows[:20], 1):
    print(f"{i:>3} {brand:<16} {base:>14.1f} {v29:>8} {d29:>+9.1f} {v30:>8} {d30:>+9.1f}")

print()
total_base = sum(r[1] for r in rows)
total_29 = sum(r[2] for r in rows)
total_30 = sum(r[4] for r in rows)
print(f"전체 합계: 베이스라인 {total_base:.1f} | 9/29 {total_29} (증가 {total_29-total_base:+.1f}) | 9/30 {total_30} (증가 {total_30-total_base:+.1f})")

top20_d29 = sum(r[3] for r in rows[:20])
top20_d30 = sum(r[5] for r in rows[:20])
print(f"TOP20 증가분 합: 9/29 {top20_d29:+.1f} ({top20_d29/(total_29-total_base)*100:.1f}%) | 9/30 {top20_d30:+.1f} ({top20_d30/(total_30-total_base)*100:.1f}%)")
