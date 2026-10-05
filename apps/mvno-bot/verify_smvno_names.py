"""
S-MVNO 그룹 사업자명을 실무자 원본과 우리 brand_in 컬렉션에서 각각 뽑아 이름 매칭 확인.
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

df = pd.read_excel(RAW_XLSX, sheet_name="Raw_당월", header=None)
df.columns = df.iloc[0]
df = df[3:].reset_index(drop=True)
df["Date"] = pd.to_datetime(df["Date"])
d = df[df["Date"] == DATE]

gold_names = set(d[d["MNP사업자_NW"] == "SMVNO"]["MNP사업자명_원본"].unique()) | \
             set(d[d["전사업자_NW"] == "SMVNO"]["전사업자명_원본"].unique())

docs = db.collection("ktoa_mvno_brand_in").where("date", "==", DATE).where("network", "==", "SKT").stream()
our_names = set(doc.to_dict()["brand"] for doc in docs)
our_names.discard("SKT")  # 원조사 자체는 제외하고 MVNO만

print("=== 골드 S-MVNO 이름 ===")
print(sorted(gold_names))
print(f"\n=== 우리 network=SKT(MVNO) 이름 ===")
print(sorted(our_names))
print(f"\n=== 골드에는 있는데 우리한텐 없는 이름 ===")
print(sorted(gold_names - our_names))
print(f"\n=== 우리한텐 있는데 골드에는 없는 이름 ===")
print(sorted(our_names - gold_names))

# 개별 사업자별 그날 total_in 비교 (골드 vs 우리)
print(f"\n=== S-MVNO 개별 사업자 total_in 비교 ({DATE}) ===")
gold_totals = d[d["MNP사업자_NW"]=="SMVNO"].groupby("MNP사업자명_원본")["건수"].sum()
for name in sorted(gold_names):
    gold_v = int(gold_totals.get(name, 0))
    doc = db.collection("ktoa_mvno_brand_in").document(f"{DATE}_{name}").get()
    our_v = doc.to_dict().get("total_in") if doc.exists else "문서없음"
    flag = "  <-- 차이!" if (isinstance(our_v, int) and our_v != gold_v) or our_v == "문서없음" else ""
    print(f"{name:15s} 골드={gold_v:6d}  우리={our_v}{flag}")