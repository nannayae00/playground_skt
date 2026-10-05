"""
upload_billing_weights.py
후불일별 가중치를 Firestore ktoa_config/billing_weights/monthly/{YYYY-MM}에 업로드

사용법:
  python3 upload_billing_weights.py
"""

import sys
sys.path.insert(0, '/home/mclee_cecilia/.local/lib/python3.12/site-packages')

from google.cloud import firestore

# Cloud Shell은 gcloud 인증으로 자동 처리
db = firestore.Client(project='mvno-484509', database='mvno-data')

# ============================================
# 월별 후불일별 가중치 데이터
# ============================================

WEIGHTS_DATA = {
    '2026-03': {
        1:0, 2:0.7, 3:1.4, 4:1.2, 5:1, 6:1, 7:0.6, 8:0,
        9:1.2, 10:1, 11:1.1, 12:1, 13:1, 14:0.6, 15:0,
        16:1.2, 17:1, 18:1.1, 19:1, 20:1, 21:0.6, 22:0,
        23:1.2, 24:1, 25:1.1, 26:1, 27:1, 28:0.6, 29:0,
        30:1.3, 31:1.3
    },
    '2026-04': {
        1:1.3, 2:1.1, 3:1, 4:0.6, 5:0, 6:1.2, 7:1, 8:1.1, 9:1, 10:1,
        11:0.6, 12:0, 13:1.2, 14:1, 15:1.1, 16:1, 17:1, 18:0.6, 19:0,
        20:1.2, 21:1, 22:1.1, 23:1, 24:1, 25:0.6, 26:0, 27:1.2, 28:1,
        29:1.1, 30:1.3
    },
    # 추후 월 추가 시 여기에 추가
    # '2026-05': { 1: ..., ... }
}

# ============================================
# 업로드
# ============================================
for ym, weights in WEIGHTS_DATA.items():
    # Firestore는 int key를 string으로 저장하므로 string으로 변환
    str_weights = {str(k): v for k, v in weights.items()}

    doc_ref = (
        db.collection('ktoa_config')
          .document('billing_weights')
          .collection('monthly')
          .document(ym)
    )
    doc_ref.set({
        'ym':        ym,
        'weights':   str_weights,
        'updated_at': firestore.SERVER_TIMESTAMP,
    })
    total = sum(weights.values())
    print(f"✅ {ym} 업로드 완료 (월 총 영업일수: {total:.1f}일)")

print("\n완료!")