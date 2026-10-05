"""
MNO Out(SKT -> SM+KM+LM) 지표를 carrier_summary matrix에서 직접 계산해서
공식 리포트값(S=1,419 / K=885 / L=975)과 대조.
"""
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

DATE = "2026-07-27"
MVNO_GROUPS = ["S-MVNO", "K-MVNO", "L-MVNO"]
MNO = ["SKT", "KT", "LGU+"]

cs = db.collection("ktoa_carrier_summary").document(DATE).get()
d = cs.to_dict()
matrix = d["matrix"]

print(f"=== {DATE} 'MNO -> MVNO만' Out 계산 (공식 MNO Out과 비교 대상) ===\n")
for mno in MNO:
    # mno가 from인 경우: MVNO 3그룹(to) 각각의 matrix[to][mno] 값을 합산
    out_to_mvno = {g: matrix[g].get(mno, 0) for g in MVNO_GROUPS}
    total = sum(out_to_mvno.values())
    print(f"{mno} -> MVNO만 Out: {out_to_mvno} 합계={total}")

print(f"\n=== 참고: {mno} -> MNO(원조사간) Out ===\n")
for mno in MNO:
    out_to_mno = {m2: matrix[m2].get(mno, 0) for m2 in MNO if m2 != mno}
    print(f"{mno} -> MNO간 Out: {out_to_mno} 합계={sum(out_to_mno.values())}")

print(f"\n공식 리포트 MNO Out (7/27): S=1419, K=885, L=975")