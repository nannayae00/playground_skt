from ktoa_mvno_period_aggregator import _get_db

db = _get_db()

def delete_collection(collection_name, batch_size=400):
    coll_ref = db.collection(collection_name)
    total = 0
    while True:
        docs = list(coll_ref.limit(batch_size).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        total += len(docs)
        print(f"{collection_name}: {total}건 삭제됨...")
    print(f"{collection_name}: 삭제 완료, 총 {total}건")

delete_collection("ktoa_mvno_flow")
delete_collection("ktoa_mvno_flow_pivot")
