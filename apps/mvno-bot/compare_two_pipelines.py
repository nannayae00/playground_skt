"""
기존 파이프라인(ktoa_daily, 6사 요약 화면 기반)과
신규 파이프라인(ktoa_carrier_summary, 전체 130개 사업자 상세 기반 합산)을
같은 날짜에 대해 직접 대조.
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

MVNO = ["S-MVNO", "K-MVNO", "L-MVNO"]
MNO = ["SKT", "KT", "LGU+"]
LABEL = {"S-MVNO": "SM", "K-MVNO": "KM", "L-MVNO": "LM", "SKT": "S", "KT": "K", "LGU+": "L"}
OLD_KEY = {"S-MVNO": "SM", "K-MVNO": "KM", "L-MVNO": "LM", "SKT": "S", "KT": "K", "LGU+": "L"}

# 기존 파이프라인
old_doc = db.collection("ktoa_daily").document(DATE).get()
if not old_doc.exists:
    print(f"[기존] ktoa_daily/{DATE} 문서 없음")
    old = {}
else:
    old = old_doc.to_dict()

# 신규 파이프라인
new_doc = db.collection("ktoa_carrier_summary").document(DATE).get()
if not new_doc.exists:
    print(f"[신규] ktoa_carrier_summary/{DATE} 문서 없음")
    sys.exit(1)
new = new_doc.to_dict()

old_mi = old.get("mvno_in", {})
old_mo = old.get("mvno_out", {})
old_mno = old.get("mno_out", {})
old_net = old.get("net_change", {})

new_total_in = new.get("total_in", {})
new_total_out = new.get("total_out", {})
new_mvno_out = new.get("mvno_out", {})

def line(label, old_v, new_v):
    diff = new_v - old_v
    flag = "  <-- 차이!" if diff != 0 else ""
    print(f"{label:20s} 기존={old_v:>8,}  신규={new_v:>8,}  차이={diff:>+6,}{flag}")

print(f"=== {DATE} 기존(ktoa_daily) vs 신규(ktoa_carrier_summary) ===\n")

print("-- MVNO IN --")
for g in MVNO:
    line(g, old_mi.get(OLD_KEY[g], 0), new_total_in.get(g, 0))
line("계", old_mi.get("계", 0), sum(new_total_in.get(g, 0) for g in MVNO))

print("\n-- MVNO OUT --")
for g in MVNO:
    line(g, old_mo.get(OLD_KEY[g], 0), new_total_out.get(g, 0))
line("계", old_mo.get("계", 0), sum(new_total_out.get(g, 0) for g in MVNO))

print("\n-- MNO Out --")
for m in MNO:
    line(m, old_mno.get(OLD_KEY[m], 0), new_mvno_out.get(m, 0))
line("계", old_mno.get("계", 0), sum(new_mvno_out.get(m, 0) for m in MNO))

print("\n-- 순증감 (MVNO) --")
for g in MVNO:
    old_v = old_net.get(OLD_KEY[g], 0)
    new_v = new_total_in.get(g, 0) - new_total_out.get(g, 0)
    line(g, old_v, new_v)

print("\n-- 순증감 (MNO) --")
for m in MNO:
    old_v = old_net.get(OLD_KEY[m], 0)
    new_v = new_total_in.get(m, 0) - new_total_out.get(m, 0)
    line(m, old_v, new_v)