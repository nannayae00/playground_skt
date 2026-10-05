"""
'KCT' 순수 이름이 우리 brand_in에 있는지, 그리고 우리가 스크래핑한 코드/이름 매핑 중
KCT 관련 항목 전체를 확인.
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

print("=== 우리 brand_in에서 이름에 'KCT' 포함된 문서 전체 ===")
docs = db.collection("ktoa_mvno_brand_in").where("date", "==", DATE).stream()
for doc in docs:
    d = doc.to_dict()
    if "KCT" in d["brand"]:
        print(f"  brand={d['brand']!r} code={d.get('brand_code')!r} network={d.get('network')!r} total_in={d.get('total_in')}")

# 순수 'KCT' 문서 자체가 있는지
doc = db.collection("ktoa_mvno_brand_in").document(f"{DATE}_KCT").get()
print(f"\n'{DATE}_KCT' 문서 존재?: {doc.exists}")
if doc.exists:
    print(doc.to_dict())