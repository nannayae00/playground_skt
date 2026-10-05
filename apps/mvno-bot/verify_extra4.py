"""
신규 추가 4개(KCT/SK텔링크/LG헬로비전KT/세종텔레콤(KT)) 실제 값 확인
- total_in이 0에 가까운지, 유의미한 규모인지
- 이제 carrier_summary가 공식 리포트값과 얼마나 가까워졌는지 재검증
"""
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

DATE = "2026-07-27"
EXTRA = ["KCT(미사용)", "SK텔링크(미사용)", "LG헬로비전KT", "세종텔레콤(KT)"]

print(f"=== {DATE} 신규 4개 사업자 total_in 확인 ===\n")
for name in EXTRA:
    doc = db.collection("ktoa_mvno_brand_in").document(f"{DATE}_{name}").get()
    if doc.exists:
        d = doc.to_dict()
        print(f"{name}: total_in={d.get('total_in')}, network={d.get('network')}")
    else:
        print(f"{name}: 문서 없음")

print(f"\n=== carrier_summary 재검증 (MNO Out, 순증감) ===\n")
cs = db.collection("ktoa_carrier_summary").document(DATE).get()
d = cs.to_dict()
print("mvno_out:", d.get("mvno_out"))
print("mvno_in:", d.get("mvno_in"))
print("mvno_net_change:", d.get("mvno_net_change"))
print("\n공식: MNO Out S=1419/K=885/L=975, 순증감 S=+22/K=-198/L=+439")

print(f"\n=== MVNO IN/OUT 재검증 ===\n")
matrix = d["matrix"]
CARRIERS = ["SKT","KT","LGU+","S-MVNO","K-MVNO","L-MVNO"]
for g in ["S-MVNO","K-MVNO","L-MVNO"]:
    vin = sum(matrix[g].values())
    vout = sum(matrix[c2].get(g,0) for c2 in CARRIERS)
    print(f"{g}: IN={vin} OUT={vout}")
print("공식 IN: SM 2,620 / KM 4,542 / LM 6,661")
print("공식 OUT: SM 2,733 / KM 5,173 / LM 6,180")