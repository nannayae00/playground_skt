from google.cloud import firestore

db = firestore.Client(project='mvno-484509', database='mvno-data')

invalid_dates = [
    '2026-12-23', '2026-12-27', '2026-12-29', '2026-12-30', 
    '2026-12-31', '2026-25-12', '2026-26-12'
]

collection_ref = db.collection('mvno_records')

for date_id in invalid_dates:
    try:
        collection_ref.document(date_id).delete()
        print(f"✅ {date_id} 삭제 완료")
    except Exception as e:
        print(f"❌ {date_id} 삭제 실패: {e}")

print("완료!")
