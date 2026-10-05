"""
upload_tout_goal.py
월별 SKT T Out 목표값 → Firestore ktoa_config/tout_goal/monthly/{YYYY-MM} 업로드

사용법:
  python3 upload_tout_goal.py

Firestore 구조:
ktoa_config/tout_goal/monthly/{YYYY-MM}
├── goal: 42000
├── memo: "3월 SKT T Out 목표"
└── updated_at
"""

import sys
sys.path.insert(0, '/home/mclee_cecilia/.local/lib/python3.12/site-packages')

from google.cloud import firestore

db = firestore.Client(project='mvno-484509', database='mvno-data')

# ── 월별 목표값 ───────────────────────────────────────────────────────────────
# 새 달 추가 시 여기에만 추가하면 됨
TOUT_GOALS = {
    '2026-03': {'goal': 42000, 'memo': '3월 SKT T Out 목표'},
    '2026-04': {'goal': 40000, 'memo': '4월 SKT T Out 목표'},
    # '2026-05': {'goal': 40000, 'memo': '5월 SKT T Out 목표'},
}

# ── 업로드 ────────────────────────────────────────────────────────────────────
for ym, data in TOUT_GOALS.items():
    doc_ref = (
        db.collection('ktoa_config')
          .document('tout_goal')
          .collection('monthly')
          .document(ym)
    )
    doc_ref.set({
        'ym':        ym,
        'goal':      data['goal'],
        'memo':      data['memo'],
        'updated_at': firestore.SERVER_TIMESTAMP,
    })
    print(f"✅ {ym}: {data['goal']:,}건 ({data['memo']})")

print(f"\n완료! {len(TOUT_GOALS)}건 업로드")