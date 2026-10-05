"""
NAME_ALIASES 적용 시뮬레이션: Firestore를 실제로 갱신하지 않고,
현재 brand_in 데이터 + 별칭 매핑을 메모리에서만 재계산해서
골드 스탠다드와 셀 단위로 다시 대조.
"""
import sys
import pandas as pd
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

RAW_XLSX = sys.argv[1] if len(sys.argv) > 1 else "mnp_260727.xlsx"
DATE = sys.argv[2] if len(sys.argv) > 2 else "2026-07-27"
YM = DATE[:7]

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

CARRIERS = ["SKT", "KT", "LGU+", "S-MVNO", "K-MVNO", "L-MVNO"]
NAME_ALIASES = {
    "세종텔레콤": "세종텔레콤(KT)",
    "SK텔링크": "SK텔링크(재판매)",
    "KCT": "KCT(미사용)",
}

# brand_in에서 이번 달 전체 문서 로드 (build_carrier_summary와 동일 로직)
docs = list(
    db.collection("ktoa_mvno_brand_in")
    .where("date", ">=", f"{YM}-01")
    .where("date", "<=", f"{YM}-31")
    .stream()
)
docs_data = [doc.to_dict() for doc in docs]
name_to_network = {d["brand"]: d.get("network") for d in docs_data}
# KCT는 실제로 SKT 소속(S-MVNO)인데 기존 저장 데이터엔 KT로 잘못 박혀 있음 -> 시뮬레이션에서 강제 보정
if "KCT(미사용)" in name_to_network:
    name_to_network["KCT(미사용)"] = "SKT"

def resolve_carrier(name):
    if name == "SKT": return "SKT"
    if name == "KT": return "KT"
    if name in ("LGU+", "LGT"): return "LGU+"
    lookup = NAME_ALIASES.get(name, name)
    net = name_to_network.get(lookup)
    return {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}.get(net)

matrix = {c: {c2: 0 for c2 in CARRIERS} for c in CARRIERS}
unresolved = set()
for d in docs_data:
    if d["date"] != DATE:
        continue
    to_c = resolve_carrier(d["brand"])
    if not to_c:
        unresolved.add(d["brand"])
        continue
    for from_name, cnt in d.get("inflows", {}).items():
        from_c = resolve_carrier(from_name)
        if not from_c:
            unresolved.add(from_name)
            continue
        matrix[to_c][from_c] += cnt

print("resolve 실패(무시된) 이름들:", unresolved)

# 골드 로드
df = pd.read_excel(RAW_XLSX, sheet_name="Raw_당월", header=None)
df.columns = df.iloc[0]
df = df[3:].reset_index(drop=True)
df["Date"] = pd.to_datetime(df["Date"])
d = df[df["Date"] == DATE].copy()
NET_MAP = {"SKT":"SKT","KT":"KT","LGU+":"LGU+","SMVNO":"S-MVNO","KMVNO":"K-MVNO","LMVNO":"L-MVNO"}
d["to_net"] = d["MNP사업자_NW"].map(NET_MAP)
d["from_net"] = d["전사업자_NW"].map(NET_MAP)
d["건수"] = d["건수"].astype(int)
gold = d.groupby(["to_net","from_net"])["건수"].sum().unstack(fill_value=0).reindex(index=CARRIERS, columns=CARRIERS, fill_value=0)

print(f"\n=== 시뮬레이션 후 셀 단위 재대조 ===")
print(f"{'to':10s} {'from':10s} {'골드':>8s} {'시뮬':>8s} {'차이':>8s}")
mismatch = 0
total_diff = 0
for to_c in CARRIERS:
    for from_c in CARRIERS:
        g = int(gold.loc[to_c, from_c])
        o = matrix[to_c][from_c]
        diff = o - g
        total_diff += abs(diff)
        if diff != 0:
            mismatch += 1
            print(f"{to_c:10s} {from_c:10s} {g:8d} {o:8d} {diff:+8d}")
print(f"\n불일치 셀: {mismatch}/36, 절대오차 합계: {total_diff}")