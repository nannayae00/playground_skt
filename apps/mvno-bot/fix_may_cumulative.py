"""
fix_may_cumulative.py
5월 1일·2일 Firestore 일별 + 누적값 전체 수정 스크립트

[수정 이력]
v1.1 | 2026-05-04 | 일별값(mvno_in, mvno_out, mno_out, net_change) 수정 추가
v1.0 | 2026-05-04 | 최초 작성 (누적값만 수정)
"""

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs


def get_db():
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


# ──────────────────────────────────────────────
# ★ 정상값 (엑셀 이미지 기준)
# ──────────────────────────────────────────────

CORRECT = {
    '2026-05-01': {
        # 당일 마감 (월 첫 영업일 → 누적과 동일)
        'mvno_in':    {'SM': 1202, 'KM': 2739, 'LM': 4161, '계': 8102},
        'mno_out':    {'S':  1145, 'K':  419,  'L':  572,  '계': 2136},
        'net_change': {'SM': -374, 'KM': -78,  'LM': -169, '계': -621},
        'mvno_out':   {'SM': 1576, 'KM': 2817, 'LM': 4330, '계': 8723},
        # 누적 (= 당일과 동일)
        'cum_mvno_in':  {'SM': 1202, 'KM': 2739, 'LM': 4161, '계': 8102},
        'cum_mno_out':  {'S':  1145, 'K':  419,  'L':  572,  '계': 2136},
        'cum_net':      {'SM': -374, 'KM': -78,  'LM': -169, '계': -621},
        'cum_mvno_out': {'SM': 1576, 'KM': 2817, 'LM': 4330, '계': 8723},
    },
    '2026-05-02': {
        # 당일 마감
        'mvno_in':    {'SM': 904,  'KM': 1999, 'LM': 3203, '계': 6106},
        'mno_out':    {'S':  989,  'K':  390,  'L':  469,  '계': 1848},
        'net_change': {'SM': -230, 'KM': -17,  'LM': 3,    '계': -244},
        'mvno_out':   {'SM': 1134, 'KM': 2016, 'LM': 3200, '계': 6350},
        # 누적 (5/1 누적 + 5/2 당일)
        'cum_mvno_in':  {'SM': 2106, 'KM': 4738, 'LM': 7364,  '계': 14208},
        'cum_mno_out':  {'S':  2134, 'K':  809,  'L':  1041,  '계': 3984},
        'cum_net':      {'SM': -604, 'KM': -95,  'LM': -166,  '계': -865},
        'cum_mvno_out': {'SM': 2710, 'KM': 4833, 'LM': 7530,  '계': 15073},
    },
}

FIELDS_LABEL = {
    'mvno_in':      '당일 MVNO IN',
    'mno_out':      '당일 MNO Out',
    'net_change':   '당일 순증감',
    'mvno_out':     '당일 MVNO Out',
    'cum_mvno_in':  '누적 MVNO IN',
    'cum_mno_out':  '누적 MNO Out',
    'cum_net':      '누적 순증감',
    'cum_mvno_out': '누적 MVNO Out',
}


def fix():
    db = get_db()

    for date_str, correct in CORRECT.items():
        doc_ref = db.collection('ktoa_daily').document(date_str)
        doc = doc_ref.get()

        if not doc.exists:
            print(f"⚠️  {date_str} 문서 없음 → 스킵")
            continue

        current = doc.to_dict()

        print(f"\n{'='*60}")
        print(f"📅 {date_str}")
        print(f"{'='*60}")

        for field, label in FIELDS_LABEL.items():
            old_val = current.get(field, '없음')
            new_val = correct[field]
            mark = '🔴 변경' if old_val != new_val else '✅ 동일'
            print(f"\n  [{label}]  {mark}")
            print(f"  수정 전: {old_val}")
            print(f"  수정 후: {new_val}")

        confirm = input(f"\n  ➡️  {date_str} 수정하시겠어요? (y/n): ").strip().lower()
        if confirm == 'y':
            doc_ref.update(correct)
            print(f"  ✔️  {date_str} 수정 완료!")
        else:
            print(f"  ⏭️  {date_str} 스킵")

    print("\n\n🎉 전체 작업 완료!")


if __name__ == '__main__':
    fix()