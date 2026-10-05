"""
fix_may_all.py
5월 1일~9일 Firestore 수정 스크립트

[수정 이력]
v2.0 | 2026-05-12 | MNO 키 유지, 5월 3일(일요일) 제외
  - net_change / cum_net: 기존 MNO 키(S/K/L/MNO계) 유지
    MVNO 키(SM/KM/LM/계)만 엑셀값으로 덮어씀
  - mvno_in / mno_out / mvno_out: 전체 덮어쓰기
  - cum_mvno_in / cum_mno_out / cum_mvno_out: 전체 덮어쓰기
  - 5월 3일(일요일): 문서 생성 안 함
v1.0 | 2026-05-12 | 최초 작성
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
# ★ 엑셀 기준 정상값
# net_change / cum_net: MVNO 키만 정의 (MNO 키는 기존 DB값 유지)
# ──────────────────────────────────────────────

CORRECT = {
    '2026-05-01': {
        'mvno_in':      {'SM': 1202,  'KM': 2739,  'LM': 4161,  '계': 8102},
        'mno_out':      {'S':  1145,  'K':  419,   'L':  572,   '계': 2136},
        'net_change':   {'SM': -374,  'KM': -78,   'LM': -169,  '계': -621},  # MVNO만
        'mvno_out':     {'SM': 1576,  'KM': 2817,  'LM': 4330,  '계': 8723},
        'cum_mvno_in':  {'SM': 1202,  'KM': 2739,  'LM': 4161,  '계': 8102},
        'cum_mno_out':  {'S':  1145,  'K':  419,   'L':  572,   '계': 2136},
        'cum_net':      {'SM': -374,  'KM': -78,   'LM': -169,  '계': -621},  # MVNO만
        'cum_mvno_out': {'SM': 1576,  'KM': 2817,  'LM': 4330,  '계': 8723},
    },
    '2026-05-02': {
        'mvno_in':      {'SM': 904,   'KM': 1999,  'LM': 3203,  '계': 6106},
        'mno_out':      {'S':  989,   'K':  390,   'L':  469,   '계': 1848},
        'net_change':   {'SM': -230,  'KM': -17,   'LM': 3,     '계': -244},
        'mvno_out':     {'SM': 1134,  'KM': 2016,  'LM': 3200,  '계': 6350},
        'cum_mvno_in':  {'SM': 2106,  'KM': 4738,  'LM': 7364,  '계': 14208},
        'cum_mno_out':  {'S':  2134,  'K':  809,   'L':  1041,  '계': 3984},
        'cum_net':      {'SM': -604,  'KM': -95,   'LM': -166,  '계': -865},
        'cum_mvno_out': {'SM': 2710,  'KM': 4833,  'LM': 7530,  '계': 15073},
    },
    # 5월 3일(일요일) → 문서 생성 안 함
    '2026-05-04': {
        'mvno_in':      {'SM': 2201,  'KM': 4806,  'LM': 6716,  '계': 13723},
        'mno_out':      {'S':  2000,  'K':  779,   'L':  994,   '계': 3773},
        'net_change':   {'SM': -996,  'KM': -146,  'LM': -203,  '계': -1345},
        'mvno_out':     {'SM': 3197,  'KM': 4952,  'LM': 6919,  '계': 15068},
        'cum_mvno_in':  {'SM': 4307,  'KM': 9544,  'LM': 14080, '계': 27931},
        'cum_mno_out':  {'S':  4134,  'K':  1588,  'L':  2035,  '계': 7757},
        'cum_net':      {'SM': -1600, 'KM': -241,  'LM': -369,  '계': -2210},
        'cum_mvno_out': {'SM': 5907,  'KM': 9785,  'LM': 14449, '계': 30141},
    },
    '2026-05-05': {
        'mvno_in':      {'SM': 525,   'KM': 1265,  'LM': 2158,  '계': 3948},
        'mno_out':      {'S':  563,   'K':  248,   'L':  311,   '계': 1122},
        'net_change':   {'SM': -243,  'KM': -247,  'LM': -62,   '계': -552},
        'mvno_out':     {'SM': 768,   'KM': 1512,  'LM': 2220,  '계': 4500},
        'cum_mvno_in':  {'SM': 4832,  'KM': 10809, 'LM': 16238, '계': 31879},
        'cum_mno_out':  {'S':  4697,  'K':  1836,  'L':  2346,  '계': 8879},
        'cum_net':      {'SM': -1843, 'KM': -488,  'LM': -431,  '계': -2762},
        'cum_mvno_out': {'SM': 6675,  'KM': 11297, 'LM': 16669, '계': 34641},
    },
    '2026-05-06': {
        'mvno_in':      {'SM': 2091,  'KM': 3827,  'LM': 6057,  '계': 11975},
        'mno_out':      {'S':  1439,  'K':  626,   'L':  770,   '계': 2835},
        'net_change':   {'SM': -596,  'KM': -80,   'LM': -97,   '계': -773},
        'mvno_out':     {'SM': 2687,  'KM': 3907,  'LM': 6154,  '계': 12748},
        'cum_mvno_in':  {'SM': 6923,  'KM': 14636, 'LM': 22295, '계': 43854},
        'cum_mno_out':  {'S':  6136,  'K':  2462,  'L':  3116,  '계': 11714},
        'cum_net':      {'SM': -2439, 'KM': -568,  'LM': -528,  '계': -3535},
        'cum_mvno_out': {'SM': 9362,  'KM': 15204, 'LM': 22823, '계': 47389},
    },
    '2026-05-07': {
        'mvno_in':      {'SM': 2130,  'KM': 3858,  'LM': 5975,  '계': 11963},
        'mno_out':      {'S':  1586,  'K':  690,   'L':  774,   '계': 3050},
        'net_change':   {'SM': -509,  'KM': 265,   'LM': 124,   '계': -120},
        'mvno_out':     {'SM': 2639,  'KM': 3593,  'LM': 5851,  '계': 12083},
        'cum_mvno_in':  {'SM': 9053,  'KM': 18494, 'LM': 28270, '계': 55817},
        'cum_mno_out':  {'S':  7722,  'K':  3152,  'L':  3890,  '계': 14764},
        'cum_net':      {'SM': -2948, 'KM': -303,  'LM': -404,  '계': -3655},
        'cum_mvno_out': {'SM': 12001, 'KM': 18797, 'LM': 28674, '계': 59472},
    },
    '2026-05-08': {
        'mvno_in':      {'SM': 2157,  'KM': 3797,  'LM': 5927,  '계': 11881},
        'mno_out':      {'S':  1451,  'K':  637,   'L':  796,   '계': 2884},
        'net_change':   {'SM': -381,  'KM': 80,    'LM': -6,    '계': -307},
        'mvno_out':     {'SM': 2538,  'KM': 3717,  'LM': 5933,  '계': 12188},
        'cum_mvno_in':  {'SM': 11210, 'KM': 22291, 'LM': 34197, '계': 67698},
        'cum_mno_out':  {'S':  9173,  'K':  3789,  'L':  4686,  '계': 17648},
        'cum_net':      {'SM': -3329, 'KM': -223,  'LM': -410,  '계': -3962},
        'cum_mvno_out': {'SM': 14539, 'KM': 22514, 'LM': 34607, '계': 71660},
    },
    '2026-05-09': {
        'mvno_in':      {'SM': 1067,  'KM': 2430,  'LM': 3921,  '계': 7418},
        'mno_out':      {'S':  1025,  'K':  460,   'L':  656,   '계': 2141},
        'net_change':   {'SM': -330,  'KM': 152,   'LM': -92,   '계': -270},
        'mvno_out':     {'SM': 1397,  'KM': 2278,  'LM': 4013,  '계': 7688},
        'cum_mvno_in':  {'SM': 12277, 'KM': 24721, 'LM': 38118, '계': 75116},
        'cum_mno_out':  {'S':  10198, 'K':  4249,  'L':  5342,  '계': 19789},
        'cum_net':      {'SM': -3659, 'KM': -71,   'LM': -502,  '계': -4232},
        'cum_mvno_out': {'SM': 15936, 'KM': 24792, 'LM': 38620, '계': 79348},
    },
}

# net_change / cum_net 는 MVNO 키만 update (MNO 키는 DB에서 유지)
# → Firestore update()는 필드 단위가 아닌 맵 전체를 덮어쓰므로
#   MVNO 키만 개별 필드로 update 해야 MNO 키 보존됨
NET_MVNO_KEYS = ['SM', 'KM', 'LM', '계']


def fix():
    db = get_db()
    total_fixed = 0

    print("\n" + "="*60)
    print("📋 5월 1일~9일 DB 수정 시작 (일요일 5/3 제외)")
    print("="*60)

    for date_str, correct in CORRECT.items():
        doc_ref = db.collection('ktoa_daily').document(date_str)
        doc = doc_ref.get()

        print(f"\n{'='*60}")
        print(f"📅 {date_str}")
        print(f"{'='*60}")

        if not doc.exists:
            print("  ⚠️  문서 없음 → 스킵")
            continue

        current = doc.to_dict()

        # ── update payload 구성 ──────────────────────────
        update_payload = {}

        # 일반 필드: 전체 덮어쓰기
        for field in ['mvno_in', 'mno_out', 'mvno_out',
                      'cum_mvno_in', 'cum_mno_out', 'cum_mvno_out']:
            update_payload[field] = correct[field]

        # net_change / cum_net: MVNO 키만 개별 update (MNO 키 보존)
        for net_field in ['net_change', 'cum_net']:
            for k in NET_MVNO_KEYS:
                # Firestore 점 표기법으로 중첩 필드만 수정
                update_payload[f'{net_field}.{k}'] = correct[net_field][k]

        # ── 변경사항 출력 ────────────────────────────────
        changed = False
        for field in ['mvno_in', 'mno_out', 'mvno_out',
                      'cum_mvno_in', 'cum_mno_out', 'cum_mvno_out']:
            if current.get(field) != correct[field]:
                print(f"  🔴 {field}")
                print(f"     현재: {current.get(field)}")
                print(f"     정상: {correct[field]}")
                changed = True

        for net_field in ['net_change', 'cum_net']:
            cur = current.get(net_field, {})
            for k in NET_MVNO_KEYS:
                if cur.get(k) != correct[net_field][k]:
                    print(f"  🔴 {net_field}.{k}: {cur.get(k)} → {correct[net_field][k]}")
                    changed = True

        if not changed:
            print("  ✅ 모든 값 정상 — 수정 불필요")
            continue

        doc_ref.update(update_payload)
        print(f"  ✔️  수정 완료!")
        total_fixed += 1

    print(f"\n\n🎉 전체 완료! 총 {total_fixed}일 수정됨")


if __name__ == '__main__':
    fix()