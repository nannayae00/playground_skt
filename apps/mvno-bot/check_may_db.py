"""
check_may_db.py
5월 1일~9일 Firestore 현재값 조회 + Web발신값 비교

[수정 이력]
v2.0 | 2026-05-12 | Web발신값과 자동 비교 추가
v1.0 | 2026-05-12 | 최초 작성 (조회만)
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
# ★ Web발신(실무자) 기준값
# 05-09 누적값만 있으므로 해당 날짜만 비교
# ──────────────────────────────────────────────
WEB = {
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
    '2026-05-11': {
        'mvno_in':      {'SM': 2119,  'KM': 4806,  'LM': 6435,  '계': 13360},
        'mno_out':      {'S':  1560,  'K':  739,   'L':  991,   '계': 3290},
        'net_change':   {'SM': -850,  'KM': 381,   'LM': -534,  '계': -1003},
        'mvno_out':     {'SM': 2969,  'KM': 4425,  'LM': 6969,  '계': 14363},
        'cum_mvno_in':  {'SM': 14400, 'KM': 29500, 'LM': 44500, '계': 88400},  # 천단위 근사
        'cum_mno_out':  {'S':  11800, 'K':  5000,  'L':  6300,  '계': 23100},
        'cum_net':      {'SM': -4509, 'KM': 310,   'LM': -1047, '계': -5256},
        'cum_mvno_out': {'SM': 18905, 'KM': 29217, 'LM': 45589, '계': 93711},
    },
}

DATES = [
    '2026-05-01', '2026-05-02', '2026-05-04', '2026-05-05',
    '2026-05-06', '2026-05-07', '2026-05-08', '2026-05-09',
]

FIELDS = [
    ('mvno_in',      '당일 MVNO IN  '),
    ('mno_out',      '당일 MNO Out  '),
    ('net_change',   '당일 순증감   '),
    ('mvno_out',     '당일 MVNO Out '),
    ('cum_mvno_in',  '누적 MVNO IN  '),
    ('cum_mno_out',  '누적 MNO Out  '),
    ('cum_net',      '누적 순증감   '),
    ('cum_mvno_out', '누적 MVNO Out '),
]


def check():
    db = get_db()

    for date_str in DATES:
        doc = db.collection('ktoa_daily').document(date_str).get()

        print(f"\n{'='*60}")
        print(f"📅 {date_str}")
        print(f"{'='*60}")

        if not doc.exists:
            print("  ⚠️  문서 없음")
            continue

        data = doc.to_dict()
        web = WEB.get(date_str)

        for field, label in FIELDS:
            db_val = data.get(field, '없음')
            print(f"  [{label}] {db_val}")

            # Web발신값 있는 날짜면 비교
            if web and field in web:
                web_val = web[field]
                # 키별 비교
                diff_keys = []
                for k, wv in web_val.items():
                    dv = db_val.get(k) if isinstance(db_val, dict) else None
                    if dv != wv:
                        diff_keys.append(f"{k}: DB={dv} Web={wv} (△{dv-wv if dv else '?'})")
                if diff_keys:
                    print(f"    ⚠️  Web발신 차이: {', '.join(diff_keys)}")
                else:
                    print(f"    ✅ Web발신 일치")


if __name__ == '__main__':
    check()