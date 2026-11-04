"""순증 매트릭스 저장 (다른 시스템에서 바로 읽도록 계산된 값을 Firestore에 보관)

[추가 20261104] 실무 요청 - 텔레그램 순증 매트릭스 이미지(net_matrix_image)와 같은 숫자를
다른 시스템이 각자 계산하지 않고 문서 하나로 읽을 수 있게 저장. 원본(ktoa_daily.matrix,
ktoa_hourly.matrix)에서 언제든 다시 만들 수 있는 파생 데이터.

컬렉션
  ktoa_net_matrix/{YYYY-MM-DD}              일마감 확정값 (20:01 일마감, 20:25·아침 재검증 때 갱신)
  ktoa_net_matrix_hourly/{YYYY-MM-DD}_{HH}00  정시 중간값 (매시 00분 기준)

문서 필드
  day[기준][상대] = 기준 사업자가 상대에게서 받은 건수 - 상대에게 준 건수 (당일)
  cum[기준][상대] = 같은 값의 월 누적 (월초~당일. 정시 문서는 전일까지 확정 + 당일 정시)
  기준/상대 키: SKT, KT, LGU, MVNO_SKT, MVNO_KT, MVNO_LGU (ktoa_daily.matrix와 같음)
  상대 자리에 MNO계, MVNO계, 합계(= 그 기준의 순증감, ktoa_daily.net_change와 같음)도 있음.
  자기 자신 칸은 없음.

재생성: python3 net_matrix_store.py backfill  (원본 전체로 두 컬렉션을 다시 씀)
"""
import logging
import re
from datetime import datetime, timezone

from net_matrix_image import _pair

log = logging.getLogger(__name__)

NODES = ['MVNO_SKT', 'MVNO_KT', 'MVNO_LGU', 'SKT', 'KT', 'LGU']
MNO = ['SKT', 'KT', 'LGU']
MVNO = ['MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']
LABELS = {'MVNO_SKT': 'S-MVNO', 'MVNO_KT': 'K-MVNO', 'MVNO_LGU': 'L-MVNO',
          'SKT': 'SKT', 'KT': 'KT', 'LGU': 'LGU+'}
DEFINITION = '값 = 기준(바깥 키) 사업자가 상대(안쪽 키)에게서 받은 건수 - 준 건수. 출처 ktoa_daily.matrix / ktoa_hourly.matrix'
DAILY_COL = 'ktoa_net_matrix'
HOURLY_COL = 'ktoa_net_matrix_hourly'


def compute_net(matrix: dict) -> dict:
    """matrix[도착지][출발지] → {기준: {상대: 순증, MNO계, MVNO계, 합계}}"""
    out = {}
    for base in NODES:
        row = {other: _pair(matrix, base, other) for other in NODES if other != base}
        row['MNO계'] = sum(v for k, v in row.items() if k in MNO)
        row['MVNO계'] = sum(v for k, v in row.items() if k in MVNO)
        row['합계'] = row['MNO계'] + row['MVNO계']
        out[base] = row
    return out


def add_matrix(acc: dict, matrix: dict) -> dict:
    """matrix 합산 ('소계' 제외)"""
    for r, row in (matrix or {}).items():
        for c, v in (row or {}).items():
            if c == '소계':
                continue
            acc.setdefault(r, {})
            acc[r][c] = acc[r].get(c, 0) + (v or 0)
    return acc


def _db():
    from ktoa_firestore import _get_db
    return _get_db()


def _month_matrices_before(db, date_str: str) -> dict:
    """월초 ~ date_str 전날까지 matrix 합"""
    acc = {}
    for d in (db.collection('ktoa_daily')
                .where('date', '>=', date_str[:8] + '01')
                .where('date', '<', date_str).stream()):
        add_matrix(acc, d.to_dict().get('matrix'))
    return acc


def _close_doc(date_str: str, day_matrix: dict, cum_matrix: dict) -> dict:
    return {'date': date_str, 'basis': 'close', 'ref_time': '마감',
            'day': compute_net(day_matrix), 'cum': compute_net(cum_matrix),
            'cum_from': date_str[:8] + '01', 'labels': LABELS, 'definition': DEFINITION,
            'source': 'ktoa_daily.matrix', 'updated_at': datetime.now(timezone.utc)}


def _hourly_doc(date_str: str, hour: int, day_matrix: dict, cum_matrix: dict, src_id: str) -> dict:
    return {'date': date_str, 'hour': hour, 'basis': 'hourly', 'ref_time': f'{hour:02d}:00',
            'day': compute_net(day_matrix), 'cum': compute_net(cum_matrix),
            'cum_from': date_str[:8] + '01', 'labels': LABELS, 'definition': DEFINITION,
            'source': f'ktoa_hourly/{src_id}' if src_id else 'ktoa_hourly.matrix',
            'updated_at': datetime.now(timezone.utc)}


def save_close(daily: dict) -> bool:
    """일마감(확정) 순증 매트릭스 저장. 실패해도 예외를 밖으로 내지 않음."""
    date_str = (daily or {}).get('date')
    if not date_str or not daily.get('matrix'):
        return False
    try:
        db = _db()
        cum = add_matrix(_month_matrices_before(db, date_str), daily['matrix'])
        db.collection(DAILY_COL).document(date_str).set(_close_doc(date_str, daily['matrix'], cum))
        log.info(f'순증 매트릭스 저장: {DAILY_COL}/{date_str}')
        return True
    except Exception as e:
        log.warning(f'순증 매트릭스 저장 실패 (무시): {e}')
        return False


def save_hourly(stats: dict) -> bool:
    """정시(매시 00분) 순증 매트릭스 저장. 10분 단위 값은 저장하지 않음."""
    m = re.search(r'(\d+)시\s*(\d+)분', (stats or {}).get('reference_time', ''))
    date_str = (stats or {}).get('date')
    if not m or int(m.group(2)) != 0 or not date_str or not stats.get('matrix'):
        return False
    hour = int(m.group(1))
    try:
        db = _db()
        cum = add_matrix(_month_matrices_before(db, date_str), stats['matrix'])
        doc_id = f'{date_str}_{hour:02d}00'
        db.collection(HOURLY_COL).document(doc_id).set(
            _hourly_doc(date_str, hour, stats['matrix'], cum, stats.get('_doc_id', '')))
        log.info(f'순증 매트릭스 저장: {HOURLY_COL}/{doc_id}')
        return True
    except Exception as e:
        log.warning(f'정시 순증 매트릭스 저장 실패 (무시): {e}')
        return False


def backfill() -> None:
    """원본 전체로 두 컬렉션 재생성 (일마감 → 정시 순)."""
    db = _db()
    daily = {}
    for s in db.collection('ktoa_daily').select(['date', 'matrix']).stream():
        x = s.to_dict()
        if x.get('matrix'):
            daily[s.id] = x['matrix']

    batch, n = db.batch(), 0
    cum_before = {}   # date -> 월초~전날 누적 (정시용)
    month, acc = None, {}
    for ds in sorted(daily):
        if ds[:7] != month:
            month, acc = ds[:7], {}
        cum_before[ds] = add_matrix({}, acc)
        add_matrix(acc, daily[ds])
        batch.set(db.collection(DAILY_COL).document(ds), _close_doc(ds, daily[ds], add_matrix({}, acc)))
        n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()
    print(f'{DAILY_COL}: {n}건')

    # 정시: 시간대별 첫 정시 스냅샷(reference_time 'HH시 00분')
    picks = {}
    for s in db.collection('ktoa_hourly').select(['date', 'reference_time', 'matrix']).stream():
        x = s.to_dict()
        m = re.search(r'(\d+)시\s*(\d+)분', x.get('reference_time') or '')
        if not m or int(m.group(2)) != 0 or not x.get('matrix') or not x.get('date'):
            continue
        key = (x['date'], int(m.group(1)))
        if key not in picks or s.id < picks[key][0]:
            picks[key] = (s.id, x['matrix'])
    batch, n = db.batch(), 0
    for (ds, hour), (src, mat) in sorted(picks.items()):
        before = cum_before.get(ds)
        if before is None:   # 그날 일마감이 아직 없으면 DB의 월초~전날로
            before = {}
            for k in sorted(daily):
                if k[:7] == ds[:7] and k < ds:
                    add_matrix(before, daily[k])
        cum = add_matrix(add_matrix({}, before), mat)
        batch.set(db.collection(HOURLY_COL).document(f'{ds}_{hour:02d}00'),
                  _hourly_doc(ds, hour, mat, cum, src))
        n += 1
        if n % 400 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()
    print(f'{HOURLY_COL}: {n}건')


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'backfill':
        backfill()
    else:
        print(__doc__)
