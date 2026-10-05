"""
실무자 원본(Raw_당월, row-level)을 6x6 carrier 매트릭스로 직접 집계하여
우리 ktoa_carrier_summary와 셀 단위로 정밀 대조.
"""
import sys
import pandas as pd
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

RAW_XLSX = sys.argv[1] if len(sys.argv) > 1 else "mnp_260727.xlsx"
DATE = sys.argv[2] if len(sys.argv) > 2 else "2026-07-27"

if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project="mvno-484509", database="mvno-data")

CARRIERS = ["SKT", "KT", "LGU+", "S-MVNO", "K-MVNO", "L-MVNO"]
NET_MAP = {"SKT": "SKT", "KT": "KT", "LGU+": "LGU+", "SMVNO": "S-MVNO", "KMVNO": "K-MVNO", "LMVNO": "L-MVNO"}

# 실무자 원본 로드 및 집계
df = pd.read_excel(RAW_XLSX, sheet_name="Raw_당월", header=None)
df.columns = df.iloc[0]
df = df[3:].reset_index(drop=True)
df["Date"] = pd.to_datetime(df["Date"])
d = df[df["Date"] == DATE].copy()
d["to_net"] = d["MNP사업자_NW"].map(NET_MAP)
d["from_net"] = d["전사업자_NW"].map(NET_MAP)
d["건수"] = d["건수"].astype(int)

gold_matrix = d.groupby(["to_net", "from_net"])["건수"].sum().unstack(fill_value=0)
gold_matrix = gold_matrix.reindex(index=CARRIERS, columns=CARRIERS, fill_value=0)

# 우리 carrier_summary 로드
cs = db.collection("ktoa_carrier_summary").document(DATE).get()
our_matrix_raw = cs.to_dict()["matrix"]

print(f"=== {DATE} 셀 단위 정밀 대조 (골드 vs 우리) ===\n")
print(f"{'to':10s} {'from':10s} {'골드':>8s} {'우리':>8s} {'차이':>8s}")
total_diff = 0
mismatch_count = 0
for to_c in CARRIERS:
    for from_c in CARRIERS:
        gold_v = int(gold_matrix.loc[to_c, from_c])
        our_v = int(our_matrix_raw.get(to_c, {}).get(from_c, 0))
        diff = our_v - gold_v
        total_diff += abs(diff)
        if diff != 0:
            mismatch_count += 1
            print(f"{to_c:10s} {from_c:10s} {gold_v:8d} {our_v:8d} {diff:+8d}")

print(f"\n총 셀 개수: {len(CARRIERS)**2}, 불일치 셀: {mismatch_count}, 절대오차 합계: {total_diff}")