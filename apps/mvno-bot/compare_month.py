"""
7월 전체 날짜에 대해 기존(ktoa_daily) vs 신규(ktoa_carrier_summary)를 일괄 대조.
날짜별 요약(일치/불일치)만 출력, 불일치 시에는 상세 차이도 같이 출력.
"""
import sys
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

YM = sys.argv[1] if len(sys.argv) > 1 else "2026-07"

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

MVNO = ["S-MVNO", "K-MVNO", "L-MVNO"]
MNO = ["SKT", "KT", "LGU+"]
OLD_KEY = {"S-MVNO": "SM", "K-MVNO": "KM", "L-MVNO": "LM", "SKT": "S", "KT": "K", "LGU+": "L"}

new_docs = list(
    db.collection("ktoa_carrier_summary")
    .where("date", ">=", f"{YM}-01")
    .where("date", "<=", f"{YM}-31")
    .stream()
)
new_docs.sort(key=lambda d: d.id)

print(f"=== {YM} 전체 일괄 대조 ({len(new_docs)}일) ===\n")

total_mismatch_days = 0
for doc in new_docs:
    date_str = doc.id
    new = doc.to_dict()
    old_doc = db.collection("ktoa_daily").document(date_str).get()

    if not old_doc.exists:
        print(f"{date_str}: [기존 문서 없음 - 스킵]")
        continue

    old = old_doc.to_dict()
    old_mi = old.get("mvno_in", {})
    old_mo = old.get("mvno_out", {})
    old_mno = old.get("mno_out", {})

    new_total_in = new.get("total_in", {})
    new_total_out = new.get("total_out", {})
    new_mvno_out = new.get("mvno_out", {})

    diffs = []
    for g in MVNO:
        d1 = new_total_in.get(g, 0) - old_mi.get(OLD_KEY[g], 0)
        d2 = new_total_out.get(g, 0) - old_mo.get(OLD_KEY[g], 0)
        if d1 != 0: diffs.append(f"IN.{g}={d1:+d}")
        if d2 != 0: diffs.append(f"OUT.{g}={d2:+d}")
    old_net = old.get("net_change", {})
    for m in MNO:
        d3 = new_mvno_out.get(m, 0) - old_mno.get(OLD_KEY[m], 0)
        d4 = (new_total_in.get(m, 0) - new_total_out.get(m, 0)) - old_net.get(OLD_KEY[m], 0)
        if d3 != 0: diffs.append(f"MNOOut.{m}={d3:+d}")
        if d4 != 0: diffs.append(f"MNONet.{m}={d4:+d}")

    if diffs:
        total_mismatch_days += 1
        print(f"{date_str}: 불일치 -> {', '.join(diffs)}")
    else:
        print(f"{date_str}: 일치")

print(f"\n총 {len(new_docs)}일 중 불일치 {total_mismatch_days}일")