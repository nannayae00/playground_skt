"""
cleanup_old_pattern.py
기존 140키 패턴 문서 삭제 (새 28키와 혼재 방지)
140키: {숫자}_{숫자}_{band} 형식 → 언더스코어 2개
28키:  {숫자}_{band}          형식 → 언더스코어 1개
"""
from google.cloud import firestore

db = firestore.Client(project='mvno-484509', database='mvno-data')

docs = list(db.collection('ktoa_hourly_pattern').stream())
print(f"전체 문서: {len(docs)}개\n")

old_keys = []
new_keys = []
for doc in docs:
    parts = doc.id.split('_')
    if len(parts) == 3:  # {wd}_{week}_{band} → 140키
        old_keys.append(doc.id)
    else:                # {wd}_{band} → 28키
        new_keys.append(doc.id)

print(f"기존 140키: {len(old_keys)}개")
for k in sorted(old_keys):
    print(f"  삭제 예정: {k}")

print(f"\n새 28키: {len(new_keys)}개")
for k in sorted(new_keys):
    n = docs[[d.id for d in docs].index(k)].to_dict().get('sample_count', 0)
    print(f"  유지: {k} (n={n})")

if not old_keys:
    print("\n삭제할 문서 없음")
else:
    ans = input(f"\n{len(old_keys)}개 삭제할까요? (y/n): ")
    if ans.lower() == 'y':
        for key in old_keys:
            db.collection('ktoa_hourly_pattern').document(key).delete()
            print(f"  ✅ 삭제: {key}")
        print(f"\n완료: {len(old_keys)}개 삭제")
    else:
        print("취소")