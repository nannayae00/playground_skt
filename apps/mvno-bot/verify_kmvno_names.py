"""
K-MVNO 그룹 사업자명을 실무자 원본과 우리 brand_in 컬렉션에서 각각 뽑아 이름 매칭 확인.
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

gold_names = set(d[d["MNP사업자_NW"] == "KMVNO"]["MNP사업자명_원본"].unique()) | \
             set(d[d["전사업자_NW"] == "KMVNO"]["전사업자명_원본"].unique())

docs = db.collection("ktoa_mvno_brand_in").where("date", "==", DATE).where("network", "==", "KT").stream()
our_names = set(doc.to_dict()["brand"] for doc in docs)

print("=== 골드(실무자 원본) K-MVNO 이름 목록 ===")
print(sorted(gold_names))
print(f"\n=== 우리 network=KT brand_in 이름 목록 ===")
print(sorted(our_names))

print(f"\n=== 골드에는 있는데 우리한텐 없는 이름 ===")
print(sorted(gold_names - our_names))
print(f"\n=== 우리한텐 있는데 골드에는 없는 이름 ===")
print(sorted(our_names - gold_names))