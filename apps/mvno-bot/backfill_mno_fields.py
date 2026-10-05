"""
backfill_mno_fields.py  v2.0
작성일: 2026-05-07

[수정 이력]
v2.0 | 2026-05-07 | XLS 의존 제거 → Firestore ktoa_daily matrix 기반으로 변경
  - ktoa_daily 문서의 기존 matrix 필드로 mno_in/mno_out_all/mno_net 재계산
  - 월별 누적 자동 초기화 (월 경계에서 0 리셋)
  - 기존 SM/KM/LM/계 필드 보존, MNO 키만 추가 (merge=True)
v1.0 | 2026-05-07 | XLS 기반 최초 작성
"""

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# ── Firestore 연결
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project='mvno-484509', database='mvno-data')

ALL_KEYS = ['SKT', 'KT', 'LGU', 'MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']


def calc_mno_fields(matrix: dict) -> dict:
    """matrix[도착][출발] → mno_in / mno_out_all / mno_net 계산"""
    s_in = int(matrix['SKT']['소계'])
    k_in = int(matrix['KT']['소계'])
    l_in = int(matrix['LGU']['소계'])

    s_out_all = int(sum(matrix[d]['SKT'] for d in ALL_KEYS if d != 'SKT'))
    k_out_all = int(sum(matrix[d]['KT']  for d in ALL_KEYS if d != 'KT'))
    l_out_all = int(sum(matrix[d]['LGU'] for d in ALL_KEYS if d != 'LGU'))

    return {
        'mno_in':      {'S': s_in,      'K': k_in,      'L': l_in,      '계': s_in+k_in+l_in},
        'mno_out_all': {'S': s_out_all, 'K': k_out_all, 'L': l_out_all, '계': s_out_all+k_out_all+l_out_all},
        'mno_net':     {
            'S': s_in-s_out_all, 'K': k_in-k_out_all, 'L': l_in-l_out_all,
            'MNO계': (s_in-s_out_all)+(k_in-k_out_all)+(l_in-l_out_all)
        },
    }


# ── ktoa_daily 전체 문서 조회 (날짜순 정렬)
log.info("ktoa_daily 전체 문서 조회 중...")
docs = list(db.collection('ktoa_daily').stream())
docs = sorted(docs, key=lambda d: d.id)  # YYYY-MM-DD 정렬
log.info(f"총 {len(docs)}개 문서")

# ── 월별 누적 초기화
current_ym = None
cum_mno_in      = {'S':0,'K':0,'L':0,'계':0}
cum_mno_out_all = {'S':0,'K':0,'L':0,'계':0}
cum_mno_net     = {'S':0,'K':0,'L':0,'MNO계':0}

stats_ok = 0; stats_skip_no_matrix = 0; stats_skip_no_data = 0

for doc in docs:
    date_str = doc.id
    data = doc.to_dict()

    # matrix 없으면 스킵 (bw_ai_prev만 있는 문서 등)
    matrix = data.get('matrix')
    if not matrix:
        log.warning(f"  SKIP (matrix 없음): {date_str}")
        stats_skip_no_matrix += 1
        continue

    # MNP 데이터 없는 날(0값) 스킵
    if not data.get('total') or data.get('total', 0) == 0:
        log.info(f"  SKIP (total=0, 휴일): {date_str}")
        stats_skip_no_data += 1
        continue

    # 월 바뀌면 누적 초기화
    ym = date_str[:7]  # 'YYYY-MM'
    if ym != current_ym:
        current_ym = ym
        cum_mno_in      = {'S':0,'K':0,'L':0,'계':0}
        cum_mno_out_all = {'S':0,'K':0,'L':0,'계':0}
        cum_mno_net     = {'S':0,'K':0,'L':0,'MNO계':0}
        log.info(f"── {ym} 누적 초기화")

    # 신규 필드 계산
    f = calc_mno_fields(matrix)

    # 누적 합산
    for k in ['S','K','L','계']:
        cum_mno_in[k]      += f['mno_in'][k]
        cum_mno_out_all[k] += f['mno_out_all'][k]
    for k in ['S','K','L','MNO계']:
        cum_mno_net[k] += f['mno_net'][k]

    # net_change 기존값에 MNO 키만 추가 (SM/KM/LM/계 보존)
    existing_net = data.get('net_change', {})
    merged_net = dict(existing_net)
    merged_net['S']    = f['mno_net']['S']
    merged_net['K']    = f['mno_net']['K']
    merged_net['L']    = f['mno_net']['L']
    merged_net['MNO계'] = f['mno_net']['MNO계']

    # cum_net 기존값에 MNO 키만 추가
    existing_cum_net = data.get('cum_net', {})
    merged_cum_net = dict(existing_cum_net)
    merged_cum_net['S']    = cum_mno_net['S']
    merged_cum_net['K']    = cum_mno_net['K']
    merged_cum_net['L']    = cum_mno_net['L']
    merged_cum_net['MNO계'] = cum_mno_net['MNO계']

    payload = {
        'mno_in':          f['mno_in'],
        'mno_out_all':     f['mno_out_all'],
        'net_change':      merged_net,
        'cum_mno_in':      dict(cum_mno_in),
        'cum_mno_out_all': dict(cum_mno_out_all),
        'cum_net':         merged_cum_net,
    }

    db.collection('ktoa_daily').document(date_str).set(payload, merge=True)
    log.info(f"  OK {date_str} | MNO순증 S={f['mno_net']['S']:+} K={f['mno_net']['K']:+} L={f['mno_net']['L']:+} MNO계={f['mno_net']['MNO계']:+} | 누적MNO계={cum_mno_net['MNO계']:+}")
    stats_ok += 1

log.info(f"\n{'='*50}")
log.info(f"완료: 업데이트={stats_ok}건 / matrix없음={stats_skip_no_matrix}건 / 휴일스킵={stats_skip_no_data}건")