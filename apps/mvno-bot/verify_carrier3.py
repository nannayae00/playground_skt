"""
MVNO(SM/KM/LM) IN/OUT과 MNO 순증감을 여러 정의로 계산해서
공식 리포트값과 전부 대조.

공식 리포트 (2026-07-27):
  MVNO IN (당일):  SM 2,620 / KM 4,542 / LM 6,661 / 계 13,823
  MVNO Out (당일): SM 2,733 / KM 5,173 / LM 6,180 / 계 14,086
  순증감(MVNO):    SM +113  / KM -631  / LM +481(부호 원문 확인 필요)
  MNO Out (당일):  S 1,419 / K 885 / L 975 / 계 3,279
  순증감(MNO):     S +22 / K -198 / L +439
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
CARRIERS = MNO + MVNO_GROUPS

cs = db.collection("ktoa_carrier_summary").document(DATE).get()
d = cs.to_dict()
matrix = d["matrix"]

print("=== MVNO IN (그룹 기준 전체 유입 = total_in 그대로) ===")
for g in MVNO_GROUPS:
    v = sum(matrix[g].values())
    print(f"{g}: {v}")
print(f"계: {sum(sum(matrix[g].values()) for g in MVNO_GROUPS)}")
print("공식: SM 2,620 / KM 4,542 / LM 6,661 / 계 13,823\n")

print("=== MVNO OUT (그룹 기준 전체 유출 = total_out 그대로) ===")
for g in MVNO_GROUPS:
    v = sum(matrix[c2].get(g, 0) for c2 in CARRIERS)
    print(f"{g}: {v}")
total_mvno_out = sum(sum(matrix[c2].get(g, 0) for c2 in CARRIERS) for g in MVNO_GROUPS)
print(f"계: {total_mvno_out}")
print("공식: SM 2,733 / KM 5,173 / LM 6,180 / 계 14,086\n")

print("=== MNO 순증감 (mvno_in - mvno_out, MVNO 기준만) ===")
for m in MNO:
    mvno_out = sum(matrix[g].get(m, 0) for g in MVNO_GROUPS)
    mvno_in = sum(matrix[m].get(g, 0) for g in MVNO_GROUPS)
    print(f"{m}: in={mvno_in} out={mvno_out} net={mvno_in - mvno_out}")
print("공식 순증감: S +22 / K -198 / L +439\n")

print("=== MNO 순증감 (전체 기준: total_in - total_out, MNO간 포함) ===")
for m in MNO:
    total_in = sum(matrix[m].values())
    total_out = sum(matrix[c2].get(m, 0) for c2 in CARRIERS)
    print(f"{m}: in={total_in} out={total_out} net={total_in - total_out}")