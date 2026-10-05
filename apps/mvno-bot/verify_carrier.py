"""
carrier_summary 값 검증 스크립트
- SKT/KT/LGU+ 문서의 inflows를 까서, MNO간 이동값이 total_out을 얼마나 부풀렸는지 확인
- Firestore 접속 필요 (GCP 환경에서 실행)
"""
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

DATE = "2026-07-27"

print(f"=== {DATE} MNO 3사 brand_in 문서의 inflows(from) 확인 ===\n")
for mno in ["SKT", "KT", "LGU+"]:
    doc = db.collection("ktoa_mvno_brand_in").document(f"{DATE}_{mno}").get()
    if not doc.exists:
        print(f"[{mno}] 문서 없음")
        continue
    d = doc.to_dict()
    inflows = d.get("inflows", {})
    mno_from = {k: v for k, v in inflows.items() if k in ("SKT", "KT", "LGU+") and v != 0}
    print(f"[{mno}] total_in={d.get('total_in')}")
    print(f"  MNO간 유입(from MNO 3사): {mno_from}")
    print(f"  MNO간 유입 합계: {sum(mno_from.values())}\n")

print(f"=== {DATE} carrier_summary 문서 ===\n")
cs = db.collection("ktoa_carrier_summary").document(DATE).get()
if cs.exists:
    d = cs.to_dict()
    print("matrix (to -> from -> count):")
    for to_c in ["SKT", "KT", "LGU+"]:
        row = d.get("matrix", {}).get(to_c, {})
        print(f"  {to_c}: {row}")
    print(f"\ntotal_in: {d.get('total_in')}")
    print(f"total_out: {d.get('total_out')}")
    print(f"net_change: {d.get('net_change')}")