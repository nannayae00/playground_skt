"""
resolve 실패 이름 3개(폐업_케이티스, KCT, CJ헬로(미사용))가
실제로 S-MVNO 소속인지, 그리고 그날 값이 얼마인지 원본에서 직접 확인.
"""
import sys
import pandas as pd

RAW_XLSX = sys.argv[1] if len(sys.argv) > 1 else "mnp_260727.xlsx"
DATE = sys.argv[2] if len(sys.argv) > 2 else "2026-07-27"

df = pd.read_excel(RAW_XLSX, sheet_name="Raw_당월", header=None)
df.columns = df.iloc[0]
df = df[3:].reset_index(drop=True)
df["Date"] = pd.to_datetime(df["Date"])
d = df[df["Date"] == DATE]

targets = ["폐업_케이티스", "KCT", "CJ헬로(미사용)"]

for name in targets:
    print(f"\n=== '{name}' ===")
    as_to = d[d["MNP사업자명_원본"] == name]
    as_from = d[d["전사업자명_원본"] == name]
    print(f"  to로 등장: {len(as_to)}건, 합계={as_to['건수'].sum()}, NW={as_to['MNP사업자_NW'].unique().tolist()}")
    print(f"  from로 등장: {len(as_from)}건, 합계={as_from['건수'].sum()}, NW={as_from['전사업자_NW'].unique().tolist()}")
    if len(as_from) > 0:
        print(f"  from 상세 (to별):")
        print(as_from.groupby("MNP사업자명_원본")["건수"].sum().to_string())