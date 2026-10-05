"""
공식 일마감 리포트 메시지 형태(MVNO IN/OUT, MNO Out, 순증감 - 당일)를
carrier_summary에서 직접 계산하여 텍스트로 대조 가능한 형태로 출력.
"""
import sys
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-27"

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

CARRIERS = ["SKT", "KT", "LGU+", "S-MVNO", "K-MVNO", "L-MVNO"]
MVNO = ["S-MVNO", "K-MVNO", "L-MVNO"]
MNO = ["SKT", "KT", "LGU+"]
LABEL = {"S-MVNO": "SM", "K-MVNO": "KM", "L-MVNO": "LM", "SKT": "S", "KT": "K", "LGU+": "L"}

doc = db.collection("ktoa_carrier_summary").document(DATE).get()
if not doc.exists:
    print(f"{DATE} 문서 없음")
    sys.exit(1)
d = doc.to_dict()
matrix = d["matrix"]
total_in = d["total_in"]
total_out = d["total_out"]

print(f"=== {DATE} carrier_summary 기반 리포트 형태 재구성 ===\n")

print("◎ MVNO IN (당일) [= total_in 그대로, 그룹 전체 유입]")
mvno_in_total = sum(total_in[g] for g in MVNO)
for g in MVNO:
    pct = total_in[g] / mvno_in_total * 100
    print(f"{LABEL[g]}  {total_in[g]:,} ({pct:.1f}%)")
print(f"계  {mvno_in_total:,}\n")

print("◎ MNO Out (당일) [= MNO에서 MVNO로만 나간 값]")
mno_out = {m: sum(matrix[g].get(m, 0) for g in MVNO) for m in MNO}
mno_out_total = sum(mno_out.values())
for m in MNO:
    pct = mno_out[m] / mno_out_total * 100
    print(f"{LABEL[m]}  {mno_out[m]:,} ({pct:.1f}%)")
print(f"계  {mno_out_total:,}\n")

print("◎ MVNO Out (당일) [= total_out 그대로, 그룹 전체 유출]")
mvno_out_total = sum(total_out[g] for g in MVNO)
for g in MVNO:
    pct = total_out[g] / mvno_out_total * 100
    print(f"{LABEL[g]}  {total_out[g]:,} ({pct:.1f}%)")
print(f"계  {mvno_out_total:,}\n")

print("◎ 순증감 (당일) - MVNO")
mvno_net_total = 0
for g in MVNO:
    net = total_in[g] - total_out[g]
    mvno_net_total += net
    sign = "▲" if net < 0 else "+"
    print(f"{LABEL[g]}  {sign}{abs(net):,}")
sign = "▲" if mvno_net_total < 0 else "+"
print(f"MVNO 계  {sign}{abs(mvno_net_total):,}\n")

print("◎ 순증감 (당일) - MNO [전체 기준: total_in - total_out, MNO간 이동 포함 — 골드 대조로 검증된 정의]")
mno_net_total = 0
for m in MNO:
    net = total_in[m] - total_out[m]
    mno_net_total += net
    sign = "▲" if net < 0 else "+"
    print(f"{LABEL[m]}  {sign}{abs(net):,}")
sign = "▲" if mno_net_total < 0 else "+"
print(f"MNO 계  {sign}{abs(mno_net_total):,}")