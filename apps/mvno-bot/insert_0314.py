"""
insert_0314.py
2026-03-14 (토) 데이터 ktoa_daily에 수동 입력

실행:
    cd ~/mvno-bot-cloudrun/mvno-bot-cloudrun
    export $(cat ~/ktoa-collector/.env | xargs)
    python3 insert_0314.py
"""

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

def _get_db():
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')

def main():
    db = _get_db()

    data = {
        'date':         '2026-03-14',
        # 당일값
        'mvno_in':      {'SM': 1226,   'KM': 2531,   'LM': 3818,   '계': 7575},
        'mvno_out':     {'SM': 1210,   'KM': 2076,   'LM': 3673,   '계': 6959},
        'mno_out':      {'S':  1288,   'K':  651,    'L':  721,    '계': 2660},
        'net_change':   {'SM': 16,     'KM': 455,    'LM': 145,    '계': 616},
        # 누적값
        'cum_mvno_in':  {'SM': 27600,  'KM': 47100,  'LM': 69900,  '계': 144600},
        'cum_mvno_out': {'SM': 28744,  'KM': 41364,  'LM': 68869,  '계': 138977},
        'cum_mno_out':  {'S':  23700,  'K':  9500,   'L':  11400,  '계': 44600},
        'cum_net':      {'SM': -1131,  'KM': 5698,   'LM': 1103,   '계': 5670},
    }

    db.collection('ktoa_daily').document('2026-03-14').set(data)
    print('✅ ktoa_daily/2026-03-14 저장 완료!')

if __name__ == '__main__':
    main()