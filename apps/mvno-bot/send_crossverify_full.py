"""
두 파이프라인(기존 ktoa_daily / 신규 ktoa_carrier_summary) 전체 항목을
'기존 | 사업자별 | 비교' 3열 형태로 정리해 둘만 있는 텔레그램 방으로 전송.
"""
import os
import sys
import requests
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-27"

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
PRIVATE_CHAT_ID = "-1003761301521"

MVNO = ["S-MVNO", "K-MVNO", "L-MVNO"]
MNO = ["SKT", "KT", "LGU+"]
OLD_KEY = {"S-MVNO": "SM", "K-MVNO": "KM", "L-MVNO": "LM", "SKT": "S", "KT": "K", "LGU+": "L"}
LABEL = OLD_KEY

YM = DATE[:7]

# 당일 문서
old = db.collection("ktoa_daily").document(DATE).get().to_dict() or {}
new = db.collection("ktoa_carrier_summary").document(DATE).get().to_dict() or {}

# 월누적 (신규는 직접 합산, 기존은 이미 cum_* 필드가 있음)
new_docs = list(
    db.collection("ktoa_carrier_summary")
    .where("date", ">=", f"{YM}-01")
    .where("date", "<=", DATE)
    .stream()
)
cum_new_in = {c: 0 for c in MVNO + MNO}
cum_new_out = {c: 0 for c in MVNO + MNO}
cum_new_mvno_out = {m: 0 for m in MNO}
for doc in new_docs:
    d = doc.to_dict()
    for c in MVNO + MNO:
        cum_new_in[c] += d.get("total_in", {}).get(c, 0)
        cum_new_out[c] += d.get("total_out", {}).get(c, 0)
    for m in MNO:
        cum_new_mvno_out[m] += d.get("mvno_out", {}).get(m, 0)

def fmt_signed(v):
    return f"▲{abs(v):,}" if v < 0 else f"+{v:,}"

def row(label, old_v, new_v):
    diff = new_v - old_v
    mark = "✅" if diff == 0 else f"⚠️{diff:+,}"
    return f"{label:6s} {old_v:>8,} | {new_v:>8,} | {mark}"

def row_signed(label, old_v, new_v):
    diff = new_v - old_v
    mark = "✅" if diff == 0 else f"⚠️{diff:+,}"
    return f"{label:6s} {fmt_signed(old_v):>8s} | {fmt_signed(new_v):>8s} | {mark}"

lines = []
lines.append(f"📋 MNP 데이터 교차검증 (기존|사업자별|비교) — {DATE}")
lines.append("(기존: KTOA MVNO통합탭 / 사업자별: 전체 130개 상세 합산)")
lines.append("")

lines.append("◎ MVNO IN (당일)")
old_mi, new_ti = old.get("mvno_in", {}), new.get("total_in", {})
for g in MVNO:
    lines.append(row(LABEL[g], old_mi.get(LABEL[g], 0), new_ti.get(g, 0)))
lines.append(row("계", old_mi.get("계", 0), sum(new_ti.get(g, 0) for g in MVNO)))
lines.append("")

lines.append(f"◎ MVNO IN ({DATE[5:7]}월 누적)")
cmi = old.get("cum_mvno_in", {})
for g in MVNO:
    lines.append(row(LABEL[g], cmi.get(LABEL[g], 0), cum_new_in.get(g, 0)))
lines.append(row("계", cmi.get("계", 0), sum(cum_new_in.get(g, 0) for g in MVNO)))
lines.append("")

lines.append("◎ MNO Out (당일)")
old_mno, new_mo = old.get("mno_out", {}), new.get("mvno_out", {})
for m in MNO:
    lines.append(row(LABEL[m], old_mno.get(LABEL[m], 0), new_mo.get(m, 0)))
lines.append(row("계", old_mno.get("계", 0), sum(new_mo.get(m, 0) for m in MNO)))
lines.append("")

lines.append(f"◎ MNO Out ({DATE[5:7]}월 누적)")
cmno = old.get("cum_mno_out", {})
for m in MNO:
    lines.append(row(LABEL[m], cmno.get(LABEL[m], 0), cum_new_mvno_out.get(m, 0)))
lines.append(row("계", cmno.get("계", 0), sum(cum_new_mvno_out.values())))
lines.append("")

lines.append("◎ 순증감 (당일)")
old_net, new_to = old.get("net_change", {}), new.get("total_out", {})
mvno_net_sum_old, mvno_net_sum_new = 0, 0
for g in MVNO:
    ov = old_net.get(LABEL[g], 0)
    nv = new_ti.get(g, 0) - new_to.get(g, 0)
    mvno_net_sum_old += ov
    mvno_net_sum_new += nv
    lines.append(row_signed(LABEL[g], ov, nv))
lines.append(row_signed("MVNO계", old_net.get("계", 0), mvno_net_sum_new))
mno_net_sum_old, mno_net_sum_new = 0, 0
for m in MNO:
    ov = old_net.get(LABEL[m], 0)
    nv = new_ti.get(m, 0) - new_to.get(m, 0)
    mno_net_sum_old += ov
    mno_net_sum_new += nv
    lines.append(row_signed(LABEL[m], ov, nv))
lines.append(row_signed("MNO계", old_net.get("MNO계", 0), mno_net_sum_new))
lines.append("")

lines.append(f"◎ 순증감 ({DATE[5:7]}월 누적)")
cnet = old.get("cum_net", {})
cmvno_net_new = 0
for g in MVNO:
    nv = cum_new_in.get(g, 0) - cum_new_out.get(g, 0)
    cmvno_net_new += nv
    lines.append(row_signed(LABEL[g], cnet.get(LABEL[g], 0), nv))
lines.append(row_signed("MVNO계", cnet.get("계", 0), cmvno_net_new))
cmno_net_new = 0
for m in MNO:
    nv = cum_new_in.get(m, 0) - cum_new_out.get(m, 0)
    cmno_net_new += nv
    lines.append(row_signed(LABEL[m], cnet.get(LABEL[m], 0), nv))
lines.append(row_signed("MNO계", cnet.get("MNO계", 0), cmno_net_new))
lines.append("")

lines.append("◎ MVNO Out (당일)")
old_mo2 = old.get("mvno_out", {})
for g in MVNO:
    lines.append(row(LABEL[g], old_mo2.get(LABEL[g], 0), new_to.get(g, 0)))
lines.append(row("계", old_mo2.get("계", 0), sum(new_to.get(g, 0) for g in MVNO)))
lines.append("")

lines.append(f"◎ MVNO Out ({DATE[5:7]}월 누적)")
cmo = old.get("cum_mvno_out", {})
for g in MVNO:
    lines.append(row(LABEL[g], cmo.get(LABEL[g], 0), cum_new_out.get(g, 0)))
lines.append(row("계", cmo.get("계", 0), sum(cum_new_out.get(g, 0) for g in MVNO)))

msg = "\n".join(lines)
print(msg)
print(f"\n--- 메시지 길이: {len(msg)}자 ---")

url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
resp = requests.post(url, json={"chat_id": PRIVATE_CHAT_ID, "text": msg}, timeout=10)
result = resp.json()
print("전송 완료" if result.get("ok") else f"전송 실패: {result}")