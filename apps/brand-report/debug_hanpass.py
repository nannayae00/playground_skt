"""
debug_hanpass.py  v1.0
작성일: 2026-08-17

[수정 이력]
v1.0 (2026-08-17): 최초 작성. "한패스" 관련 원본 브랜드명이 몇 개로
  쪼개져 있는지, 어느 망에 어떤 실적이 잡히는지 확인용 - KCT 때와 같은
  패턴(원본 브랜드명이 미묘하게 달라서 clean_brand_name()으로 안 합쳐지는
  케이스)인지 판단하기 위함.

사용법:
    python3 debug_hanpass.py
"""

from ktoa_mvno_period_aggregator import _get_db
from ktoa_mvno_report import clean_brand_name

db = _get_db()

print("=== ktoa_mvno_operator_registry에서 '한패스' 포함 코드 ===")
for doc in db.collection("ktoa_mvno_operator_registry").stream():
    d = doc.to_dict()
    if "한패스" in (d.get("name") or ""):
        print(f"{d.get('code')}\t{d.get('name')}\t{d.get('network')}\tfirst_in:{d.get('first_in_date')}\tfirst_seen:{d.get('first_seen_at')}")

print("\n=== ktoa_mvno_monthly_summary에서 '한패스' 포함 brand (clean_name 변환 결과 포함) ===")
seen = {}
for doc in db.collection("ktoa_mvno_monthly_summary").stream():
    d = doc.to_dict()
    brand = d.get("brand") or ""
    if "한패스" in brand:
        key = (brand, d.get("network"))
        if key not in seen:
            seen[key] = {"sum_in": 0, "months": 0}
        seen[key]["sum_in"] += d.get("sum_in") or 0
        seen[key]["months"] += 1

for (brand, network), stats in sorted(seen.items()):
    clean = clean_brand_name(brand)
    print(f"raw='{brand}' network={network} clean_name='{clean}' -> 누적IN={stats['sum_in']:,} ({stats['months']}개월치 존재)")

print("\n=== ktoa_mvno_brand_insights에서 '한패스' 포함 문서ID ===")
for doc in db.collection("ktoa_mvno_brand_insights").stream():
    if "한패스" in doc.id:
        d = doc.to_dict()
        nets = list(d.get("networks", {}).keys())
        print(f"문서ID='{doc.id}' networks={nets}")