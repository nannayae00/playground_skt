import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import google.oauth2.credentials
from google.cloud import firestore
from datetime import datetime, timedelta

TOKEN = open('/tmp/gcp_token.txt').read().strip()
creds = google.oauth2.credentials.Credentials(TOKEN)
db = firestore.Client(project='mvno-484509', database='mvno-data', credentials=creds)

PERIODS = [
    ('7월',      '2026-07-01', '2026-07-31'),
    ('8월',      '2026-08-01', '2026-08-31'),
    ('9월(1~15)', '2026-09-01', '2026-09-15'),
]

OPS = ['SKT', 'KT', 'LGU', 'MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']

def daterange(d1, d2):
    d = datetime.strptime(d1, '%Y-%m-%d')
    end = datetime.strptime(d2, '%Y-%m-%d')
    while d <= end:
        yield d.strftime('%Y-%m-%d')
        d += timedelta(days=1)

def sum_matrix(start, end):
    """해당 기간 ktoa_daily.matrix를 셀 단위로 합산"""
    total = {r: {c: 0 for c in OPS} for r in OPS}
    days = 0
    for ds in daterange(start, end):
        doc = db.collection('ktoa_daily').document(ds).get()
        if not doc.exists:
            continue
        m = doc.to_dict().get('matrix', {})
        if not m:
            continue
        days += 1
        for r in OPS:
            row = m.get(r, {})
            for c in OPS:
                total[r][c] += row.get(c, 0) or 0
    return total, days

def net(m, dest_rows, origin_cols):
    """IN(행=dest_rows, 열=origin_cols 합) - OUT(행=origin_cols, 열=dest_rows 합)"""
    inflow = sum(m[r][c] for r in dest_rows for c in origin_cols)
    outflow = sum(m[r][c] for r in origin_cols for c in dest_rows)
    return inflow - outflow

def fmt_k(v):
    """천 단위, +/△ 표기"""
    k = v / 1000
    if abs(k) < 0.05:
        return '등가'
    sign = '+' if k > 0 else '△'
    return f'{sign}{abs(k):.1f}천'

GROUPS = [
    ('SKT', ['SKT'], ['MVNO_SKT']),
    ('KT',  ['KT'],  ['MVNO_KT']),
    ('LGU+',['LGU'], ['MVNO_LGU']),
]
MNO_ALL  = ['SKT', 'KT', 'LGU']
MVNO_ALL = ['MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']

print(f"{'구분':>10} {'항목':>6}  " + "  ".join(f"{p[0]:>22}" for p in PERIODS))

period_matrices = {}
for p_name, start, end in PERIODS:
    m, days = sum_matrix(start, end)
    period_matrices[p_name] = m
    print(f"[{p_name}] 집계된 영업일 수: {days}")
print()

for grp_name, mno_rows, mvno_rows in GROUPS:
    # [수정] "계" 행은 그룹 합쳐서 새로 net() 계산하면 그룹 내부 흐름(예: SKT<->SM)이
    # 통째로 빠져버려 이미지와 안 맞음 - "자체(MNO)" 행 + "MVNO계열" 행을 각각
    # 계산한 뒤 산술합산해야 이미지와 정확히 일치함(각 행의 "자기 관점"을 유지).
    per_period_vals = {}  # label -> {p_name: (n_mno, n_mvno)}
    for label, rows in [('자체(MNO)', mno_rows), ('MVNO계열', mvno_rows)]:
        per_period_vals[label] = {}
        line = f"{grp_name:>10} {label:>6}  "
        for p_name, start, end in PERIODS:
            m = period_matrices[p_name]
            other_mno = [x for x in MNO_ALL if x not in rows]
            n_mno  = net(m, rows, other_mno)
            n_mvno = net(m, rows, [x for x in MVNO_ALL if x not in rows])
            per_period_vals[label][p_name] = (n_mno, n_mvno)
            n_tot = n_mno + n_mvno
            line += f"  對MNO{fmt_k(n_mno):>8}/對MVNO{fmt_k(n_mvno):>8}/계{fmt_k(n_tot):>8}"
        print(line)

    line = f"{grp_name:>10} {'계':>6}  "
    for p_name, start, end in PERIODS:
        n_mno  = per_period_vals['자체(MNO)'][p_name][0] + per_period_vals['MVNO계열'][p_name][0]
        n_mvno = per_period_vals['자체(MNO)'][p_name][1] + per_period_vals['MVNO계열'][p_name][1]
        n_tot  = n_mno + n_mvno
        line += f"  對MNO{fmt_k(n_mno):>8}/對MVNO{fmt_k(n_mvno):>8}/계{fmt_k(n_tot):>8}"
    print(line)
