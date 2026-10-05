"""
MNO 순증감을 여러 가지 방식으로 계산해서 공식값(S+22/K-198/L+439, 7/27 기준)과 대조.
실무자 원본(Raw_당월)을 직접 사용.
"""
import sys
import pandas as pd

RAW_XLSX = sys.argv[1] if len(sys.argv) > 1 else "mnp_260727.xlsx"
DATE = sys.argv[2] if len(sys.argv) > 2 else "2026-07-27"

df = pd.read_excel(RAW_XLSX, sheet_name="Raw_당월", header=None)
df.columns = df.iloc[0]
df = df[3:].reset_index(drop=True)
df["Date"] = pd.to_datetime(df["Date"])
d = df[df["Date"] == DATE].copy()
d["건수"] = d["건수"].astype(int)

NET_MAP = {"SKT":"SKT","KT":"KT","LGU+":"LGU+","SMVNO":"S-MVNO","KMVNO":"K-MVNO","LMVNO":"L-MVNO"}
d["to_net"] = d["MNP사업자_NW"].map(NET_MAP)
d["from_net"] = d["전사업자_NW"].map(NET_MAP)

MVNO = ["S-MVNO","K-MVNO","L-MVNO"]
MNO = ["SKT","KT","LGU+"]
CARRIERS = MNO + MVNO

matrix = d.groupby(["to_net","from_net"])["건수"].sum().unstack(fill_value=0).reindex(index=CARRIERS, columns=CARRIERS, fill_value=0)

print("=== 방법1: MVNO 기준만 (mvno_in - mvno_out) ===")
for m in MNO:
    mvno_out = sum(matrix.loc[g, m] for g in MVNO)
    mvno_in = sum(matrix.loc[m, g] for g in MVNO)
    print(f"{m}: in={mvno_in} out={mvno_out} net={mvno_in-mvno_out}")

print("\n=== 방법2: 전체 기준 (total_in - total_out, MNO간 포함) ===")
for m in MNO:
    total_in = matrix.loc[m].sum()
    total_out = matrix[m].sum()
    print(f"{m}: in={total_in} out={total_out} net={total_in-total_out}")

print("\n공식 순증감(MNO, 7/27): S=+22, K=-198, L=+439")
print("공식 MNO Out(7/27): S=1419, K=885, L=975")

# MNO Out + 순증감으로 역산한 "진짜 MNO IN"
print("\n=== 역산: 공식 MNO IN = 공식 MNO Out + 공식 순증감 ===")
print("S:", 1419+22, " K:", 885-198, " L:", 975+439)