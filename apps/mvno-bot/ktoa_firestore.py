"""
ktoa_firestore.py  v3.8
작성일: 2026-03-16

[수정 이력]
v3.8 | 2026-09-07 | 세종→고고 이관 보정 데이터 저장/조회 함수 추가 (Claude)
  - 컬렉션 신규: ktoa_daily_sejong_migration/{YYYY-MM-DD}
    · daily: {'SM','KM','LM'} 당일 이관 건수 (LM은 미확인 시 None)
    · cum: {'SM','KM','LM'} 월 누적 (ktoa_daily와 동일하게 월 경계에서 리셋)
  - get_previous_sejong_migration_cum(): 직전 영업일 누적 조회 (월 경계 리셋, get_previous_daily와 동일 패턴)
  - save_sejong_migration(): 당일 입력값 저장 + 누적 자동 계산
  - get_sejong_migration(): 특정일 조회
  - get_month_sejong_migration(): 월 전체 조회 (엑셀 시트용)
v3.7 | 2026-05-08 | MNO S/K/L 순증감 streak 추가
  - calc_streak(): net_S / net_K / net_L 키 추가
    → build_message()의 arr_net('S'/'K'/'L') 화살표 동작
v3.6 | 2026-05-07 | MNO 순증감 필드 추가
  - _zero_cum(): cum_mno_in, cum_mno_out_all 추가 / cum_net에 S/K/L/MNO계 추가
  - save_ktoa_to_firestore(): mno_in, mno_out_all 저장 추가
  - save_ktoa_daily(): mno_in, mno_out_all 당일/누적 저장 추가
    · cum_mno_in: MNO 월 누적 IN
    · cum_mno_out_all: MNO 월 누적 OUT_ALL (MNO→타MNO + MNO→MVNO)
    · cum_net: S/K/L/MNO계 키 추가 (기존 SM/KM/LM/계 유지)
  - get_previous_daily(): cum_mno_in 없는 구문서 호환 처리 (0 폴백)
v3.5 | 2026-05-04 | 월 경계 초기화 버그 수정
  - get_previous_daily(): 탐색 시 월(月)이 달라지면 즉시 중단 → 0으로 초기화
    → 매월 1일 첫 영업일에 전월 누적값이 이월되던 버그 해결
    → 월 첫 영업일: 당일 마감값 = 월 누계값 (정상 동작)
v3.4 | 2026-04-07 | 휴무일 이후 누적값 처리 개선
  - get_previous_daily(): cum_mvno_in 없는 문서 건너뜀
    → 주말/공휴일 다음 첫 영업일도 직전 영업일 누적값 정확히 가져옴
  - 탐색 범위 7일 → 14일로 확장 (연휴 최대 9일 대비)
v1.0 | 2026-03-16 | 최초 작성
v2.0 | 2026-03-16 | 저장 구조 확정
v2.1 | 2026-03-16 | Firestore client 호출 방식 수정
v2.2 | 2026-03-16 | 컬렉션 분리 (ktoa_hourly)
v2.3 | 2026-03-16 | get_latest_reference_time() 추가
v3.0 | 2026-03-16 | 일마감 처리 추가
  - save_ktoa_daily(): ktoa_daily 컬렉션 저장
  - get_previous_daily(): 직전 영업일 누적값 조회
v3.1 | 2026-03-19 | 직전 hourly 조회 + streak 계산 함수 추가
  - get_previous_hourly(): 당일 직전 시간 ktoa_hourly 데이터 조회
  - calc_streak(): 각 지표별 연속 상승/하락 횟수 계산 (1회만)
  - get_previous_daily_for_closing(): 전일 마감 데이터 조회 (일마감 비교용)
v3.3 | 2026-03-21 | get_latest_total() 추가 (중복 체크 방식 변경)
  - reference_time 대신 total 값으로 중복 체크
  - get_latest_total(): 당일 ktoa_hourly 최근 저장 문서의 total 반환
v3.2 | 2026-03-19 | calc_streak() 연속 횟수 계산 고도화
  - 최근 4개 hourly 데이터 조회 → 연속 방향 횟수 정확히 계산
  - 7단계: ⏫(3회+) ⬆️(2회) ↗️(1회) -(동등) ↘️(1회) ⬇️(2회) ⏬(3회+)
  - 동등(-) 발생 시 streak 리셋
"""

import logging
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

from ktoa_telegram import calc_stats

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _get_db():
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


def get_latest_reference_time(date_str: str) -> str:
    """오늘 ktoa_hourly에서 가장 최근 reference_time 반환"""
    try:
        db = _get_db()
        docs = (
            db.collection('ktoa_hourly')
            .where('date', '==', date_str)
            .order_by('collected_at', direction=fs.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            ref_time = doc.to_dict().get('reference_time', '')
            log.info(f"마지막 저장 기준시각: {ref_time}")
            return ref_time
    except Exception as e:
        log.warning(f"마지막 기준시각 조회 실패 (무시): {e}")
    return None


def get_latest_total(date_str: str) -> int:
    """당일 ktoa_hourly에서 가장 최근 저장된 total 값 반환 (중복 체크용)"""
    try:
        db = _get_db()
        docs = (
            db.collection('ktoa_hourly')
            .where('date', '==', date_str)
            .order_by('collected_at', direction=fs.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            total = doc.to_dict().get('total')
            log.info(f"마지막 저장 total: {total}")
            return total
    except Exception as e:
        log.warning(f"latest total 조회 실패 (무시): {e}")
    return None


def get_previous_hourly(date_str: str, current_doc_id: str) -> dict:
    """
    당일 직전 시간 ktoa_hourly 데이터 조회.
    current_doc_id: 현재 문서 ID (예: 2026-03-19_1240)
    반환: 직전 hourly dict (없으면 None)
    """
    try:
        db = _get_db()
        docs = (
            db.collection('ktoa_hourly')
            .where('date', '==', date_str)
            .order_by('collected_at', direction=fs.Query.DESCENDING)
            .limit(5)
            .stream()
        )
        results = []
        for doc in docs:
            if doc.id != current_doc_id:
                results.append(doc.to_dict())
        if results:
            log.info(f"직전 hourly 데이터: {results[0].get('reference_time', '')}")
            return results[0]
    except Exception as e:
        log.warning(f"직전 hourly 조회 실패 (무시): {e}")
    return None


def calc_streak(date_str: str, current_stats: dict, current_doc_id: str) -> dict:
    """
    각 지표별 연속 상승/하락 횟수 계산 (7단계).
    최근 4개 hourly 데이터 조회 → 연속 방향 횟수 계산.
    동등(-) 발생 시 streak 리셋.

    반환: {'pct_SM_in': 3, 'pct_KM_in': -2, 'net_SM': 1, ...}
    양수=상승연속 횟수, 음수=하락연속 횟수, 0=동등/첫비교
    """
    from ktoa_telegram import calc_stats as _calc

    PCT_THR = 0.1
    NET_THR = 5

    def _pv(v, t): return v / t * 100 if t else 0

    # 최근 4개 hourly 데이터 조회 (현재 포함)
    try:
        db = _get_db()
        docs = (
            db.collection('ktoa_hourly')
            .where('date', '==', date_str)
            .order_by('collected_at', direction=fs.Query.DESCENDING)
            .limit(4)
            .stream()
        )
        history = []
        for doc in docs:
            history.append(doc.to_dict())
        # 오래된 것부터 정렬 (index 0이 가장 오래된 것)
        history.reverse()
    except Exception as e:
        log.warning(f"streak용 hourly 조회 실패 (무시): {e}")
        return {}

    if len(history) < 2:
        return {}

    # 현재 데이터가 마지막에 있어야 함
    # history[-1]이 현재, history[-2]가 직전 ...
    curr_stats = current_stats
    curr_c = _calc(curr_stats.get('matrix', {}))

    # 지표별 방향 시퀀스 계산
    def get_direction(curr_d, prev_d, key, threshold):
        curr_val = _pv(curr_d.get(key, 0), curr_d.get('계', 1))
        prev_val = _pv(prev_d.get(key, 0), prev_d.get('계', 1))
        diff = curr_val - prev_val
        if abs(diff) <= threshold:
            return 0   # 동등
        return 1 if diff > 0 else -1

    def get_net_direction(curr_net, prev_net, key, threshold):
        diff = curr_net.get(key, 0) - prev_net.get(key, 0)
        if abs(diff) <= threshold:
            return 0
        return 1 if diff > 0 else -1

    def calc_consecutive(directions):
        """방향 리스트에서 연속 횟수 계산 (마지막 기준, 동등=리셋)"""
        if not directions:
            return 0
        last = directions[-1]
        if last == 0:
            return 0
        count = 0
        for d in reversed(directions):
            if d == last:
                count += 1
            else:
                break
        return count if last == 1 else -count

    # history로 각 지표별 방향 시퀀스 구성
    streak = {}
    keys_pct = [
        ('pct_SM_in',  'mvno_in',  'SM'),
        ('pct_KM_in',  'mvno_in',  'KM'),
        ('pct_LM_in',  'mvno_in',  'LM'),
        ('pct_S_mno',  'mno_out',  'S'),
        ('pct_K_mno',  'mno_out',  'K'),
        ('pct_L_mno',  'mno_out',  'L'),
        ('pct_SM_out', 'mvno_out', 'SM'),
        ('pct_KM_out', 'mvno_out', 'KM'),
        ('pct_LM_out', 'mvno_out', 'LM'),
    ]

    for streak_key, cat, k in keys_pct:
        directions = []
        # history는 [oldest, ..., prev] + current
        all_data = history + [curr_stats]
        for i in range(1, len(all_data)):
            prev_c = _calc(all_data[i-1].get('matrix', {}))
            curr_c_i = _calc(all_data[i].get('matrix', {}))
            d = get_direction(curr_c_i[cat], prev_c[cat], k, PCT_THR)
            directions.append(d)
        streak[streak_key] = calc_consecutive(directions)

    for k in ['SM', 'KM', 'LM', 'S', 'K', 'L']:
        directions = []
        all_data = history + [curr_stats]
        for i in range(1, len(all_data)):
            prev_c = _calc(all_data[i-1].get('matrix', {}))
            curr_c_i = _calc(all_data[i].get('matrix', {}))
            d = get_net_direction(curr_c_i['net'], prev_c['net'], k, NET_THR)
            directions.append(d)
        streak[f'net_{k}'] = calc_consecutive(directions)

    return streak


def get_daily(date_str: str) -> dict:
    """특정일 ktoa_daily 마감 데이터 직접 조회. 없으면 None. [v3.8, Claude]"""
    try:
        db = _get_db()
        doc = db.collection('ktoa_daily').document(date_str).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        log.warning(f"get_daily({date_str}) 조회 실패: {e}")
        return None


def get_previous_daily_for_closing(date_str: str) -> dict:
    """전일 마감 데이터 조회 (일마감 메시지 비교용)"""
    try:
        db = _get_db()
        base = datetime.strptime(date_str, '%Y-%m-%d')
        for i in range(1, 8):
            prev = (base - timedelta(days=i)).strftime('%Y-%m-%d')
            doc = db.collection('ktoa_daily').document(prev).get()
            if doc.exists:
                log.info(f"전일 마감 데이터: {prev}")
                return doc.to_dict()
    except Exception as e:
        log.warning(f"전일 마감 조회 실패 (무시): {e}")
    return None


def _zero_cum() -> dict:
    """누적값 0 초기화 dict 반환"""
    zero      = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0}
    zero_mno  = {'S': 0, 'K': 0, 'L': 0, '계': 0}
    zero_net  = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0,   # MVNO
                 'S': 0,  'K': 0,  'L': 0,  'MNO계': 0} # MNO
    return {
        'cum_mvno_in':    zero.copy(),
        'cum_mvno_out':   zero.copy(),
        'cum_mno_out':    zero_mno.copy(),
        'cum_mno_in':     zero_mno.copy(),      # 신규
        'cum_mno_out_all': zero_mno.copy(),     # 신규
        'cum_net':        zero_net.copy(),      # MVNO + MNO 통합
    }


def get_previous_daily(date_str: str) -> dict:
    """
    직전 영업일 ktoa_daily 누적값 조회.
    ★ 같은 월(月) 내에서만 탐색 — 월 경계를 넘으면 즉시 중단 후 0 반환.
    → 매월 첫 영업일에 전월 누적값이 이월되는 버그 방지.

    탐색 조건 (모두 충족해야 반환):
      1) 같은 월이어야 함  ← v3.5 신규
      2) 문서가 존재해야 함
      3) cum_mvno_in 필드가 있어야 함 (bw_ai_prev만 있는 문서 제외)

    없으면 모두 0인 dict 반환 (월 첫 영업일 or 데이터 없음).
    """
    try:
        db = _get_db()
        base = datetime.strptime(date_str, '%Y-%m-%d')
        base_ym = base.strftime('%Y-%m')  # ★ 기준 연월

        for i in range(1, 15):  # 최대 14일 탐색 (연휴 대비)
            prev_dt = base - timedelta(days=i)
            prev_str = prev_dt.strftime('%Y-%m-%d')

            # ★ [v3.5] 월이 달라지면 탐색 중단 → 0으로 초기화
            if prev_dt.strftime('%Y-%m') != base_ym:
                log.info(
                    f"월 경계 도달 ({prev_str}, 기준월: {base_ym}) "
                    f"→ 누적 0으로 초기화 (월 첫 영업일)"
                )
                break

            doc = db.collection('ktoa_daily').document(prev_str).get()
            if not doc.exists:
                continue

            data = doc.to_dict()

            # [v3.4] cum_mvno_in 없는 문서(bw_ai_prev만 있는 문서) 건너뜀
            if not data.get('cum_mvno_in'):
                log.info(f"직전 일 {prev_str}: cum_mvno_in 없음 → 더 탐색")
                continue

            log.info(f"직전 영업일 데이터 조회: {prev_str}")
            return data

    except Exception as e:
        log.warning(f"직전 영업일 조회 실패 (무시): {e}")

    # 데이터 없으면 0으로 초기화 (월 첫 영업일 or 조회 실패)
    log.info("직전 영업일 데이터 없음 → 누적 0으로 시작")
    return _zero_cum()


def _add_dicts(a: dict, b: dict) -> dict:
    """두 dict 값 합산"""
    result = {}
    for k in a:
        result[k] = a.get(k, 0) + b.get(k, 0)
    return result


def save_ktoa_to_firestore(stats: dict) -> None:
    """ktoa_hourly/{YYYY-MM-DD_HHmm} 저장"""
    db = _get_db()
    collected_at = stats['collected_at']
    doc_id = collected_at.strftime('%Y-%m-%d_%H%M')

    matrix = stats.get('matrix', {})
    c = calc_stats(matrix)

    payload = {
        'date':           stats['date'],
        'reference_time': stats.get('reference_time', ''),
        'collected_at':   collected_at,
        'total':          c['total'],
        'total_mno':      c['total_mno'],
        'total_mvno':     c['total_mvno'],
        'mvno_in':        c['mvno_in'],
        'mvno_out':       c['mvno_out'],
        'mno_out':        c['mno_out'],
        'mno_in':         c['mno_in'],         # 신규
        'mno_out_all':    c['mno_out_all'],    # 신규 (MNO→타MNO + MNO→MVNO)
        'net_change':     c['net'],            # MVNO + MNO 순증감 통합
        'matrix':         matrix,
    }

    db.collection('ktoa_hourly').document(doc_id).set(payload)
    log.info(f'Firestore 저장 완료: ktoa_hourly/{doc_id}')


def save_ktoa_daily(stats: dict) -> dict:
    """
    일마감 시 ktoa_daily/{YYYY-MM-DD} 저장.
    직전 영업일 누적값 + 금일 마감값 = 금일 누적값.
    ★ 월 첫 영업일: get_previous_daily()가 0을 반환하므로 당일값 = 누적값.

    반환: 저장된 payload (텔레그램 전송용)
    """
    db = _get_db()
    date_str = stats['date']

    matrix = stats.get('matrix', {})
    c = calc_stats(matrix)

    # 당일 마감값
    today = {
        'mvno_in':    c['mvno_in'],
        'mvno_out':   c['mvno_out'],
        'mno_out':    c['mno_out'],
        'mno_in':     c['mno_in'],       # 신규
        'mno_out_all': c['mno_out_all'], # 신규
        'net':        c['net'],          # MVNO + MNO 통합
    }

    # 직전 영업일 누적값 (월 첫 영업일이면 모두 0)
    prev = get_previous_daily(date_str)

    # MNO 누적용 zero 기본값 (구문서 호환)
    _z_mno = {'S': 0, 'K': 0, 'L': 0, '계': 0}
    _z_net = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0, 'S': 0, 'K': 0, 'L': 0, 'MNO계': 0}

    # 누적 계산
    cum_mvno_in    = _add_dicts(prev.get('cum_mvno_in',    {'SM':0,'KM':0,'LM':0,'계':0}), today['mvno_in'])
    cum_mvno_out   = _add_dicts(prev.get('cum_mvno_out',   {'SM':0,'KM':0,'LM':0,'계':0}), today['mvno_out'])
    cum_mno_out    = _add_dicts(prev.get('cum_mno_out',    _z_mno.copy()),                  today['mno_out'])
    cum_mno_in     = _add_dicts(prev.get('cum_mno_in',     _z_mno.copy()),                  today['mno_in'])     # 신규
    cum_mno_out_all= _add_dicts(prev.get('cum_mno_out_all',_z_mno.copy()),                  today['mno_out_all'])# 신규
    cum_net        = _add_dicts(prev.get('cum_net',        _z_net.copy()),                  today['net'])        # MVNO+MNO

    payload = {
        'date':            date_str,
        'reference_time':  stats.get('reference_time', ''),
        'collected_at':    stats['collected_at'],
        # 당일
        'mvno_in':         today['mvno_in'],
        'mvno_out':        today['mvno_out'],
        'mno_out':         today['mno_out'],
        'mno_in':          today['mno_in'],        # 신규
        'mno_out_all':     today['mno_out_all'],   # 신규
        'net_change':      today['net'],           # MVNO + MNO 통합
        # 누적
        'cum_mvno_in':     cum_mvno_in,
        'cum_mvno_out':    cum_mvno_out,
        'cum_mno_out':     cum_mno_out,
        'cum_mno_in':      cum_mno_in,             # 신규
        'cum_mno_out_all': cum_mno_out_all,        # 신규
        'cum_net':         cum_net,                # MVNO + MNO 통합
        # raw
        'total':           c['total'],
        'total_mno':       c['total_mno'],
        'total_mvno':      c['total_mvno'],
        'matrix':          matrix,
    }

    db.collection('ktoa_daily').document(date_str).set(payload, merge=True)
    log.info(f'Firestore 저장 완료: ktoa_daily/{date_str}')

    return payload

# ══════════════════════════════════════════════════════════════════
# 세종 → 고고 이관 보정 데이터 (별도 컬렉션)
# ══════════════════════════════════════════════════════════════════

SEJONG_MIG_COLLECTION = 'ktoa_daily_sejong_migration'


def get_previous_sejong_migration_cum(date_str: str) -> dict:
    """
    직전 영업일 세종이관 누적값 조회.
    ★ ktoa_daily.get_previous_daily()와 동일하게 월 경계에서 리셋.
    없으면 0으로 초기화 (월 첫날 또는 데이터 없음).
    """
    zero = {'SM': 0, 'KM': 0, 'LM': 0}
    try:
        db = _get_db()
        base = datetime.strptime(date_str, '%Y-%m-%d')
        base_ym = base.strftime('%Y-%m')

        for i in range(1, 15):
            prev_dt = base - timedelta(days=i)
            prev_str = prev_dt.strftime('%Y-%m-%d')

            if prev_dt.strftime('%Y-%m') != base_ym:
                log.info(f"[세종이관] 월 경계 도달 ({prev_str}) → 누적 0으로 초기화")
                break

            doc = db.collection(SEJONG_MIG_COLLECTION).document(prev_str).get()
            if not doc.exists:
                continue

            data = doc.to_dict()
            if not data.get('cum'):
                continue

            log.info(f"[세종이관] 직전 영업일 누적 조회: {prev_str}")
            return data['cum']

    except Exception as e:
        log.warning(f"[세종이관] 직전 영업일 조회 실패 (무시): {e}")

    return zero.copy()


def save_sejong_migration(date_str: str, sm: int, km: int, lm) -> dict:
    """
    세종→고고 이관 당일 입력값 저장.
    lm=None이면 '미확인' (누적 계산에서 제외, 화면엔 미확인으로 표시).
    같은 날짜 재입력 시 덮어씀 (merge=False로 daily 전체 교체).
    """
    db = _get_db()
    prev_cum = get_previous_sejong_migration_cum(date_str)

    daily = {'SM': sm or 0, 'KM': km or 0, 'LM': lm}

    cum = {
        'SM': prev_cum.get('SM', 0) + (sm or 0),
        'KM': prev_cum.get('KM', 0) + (km or 0),
        'LM': (prev_cum.get('LM') or 0) + lm if lm is not None else prev_cum.get('LM'),
    }

    payload = {
        'date':       date_str,
        'daily':      daily,
        'cum':        cum,
        'updated_at': datetime.now(KST),
    }

    db.collection(SEJONG_MIG_COLLECTION).document(date_str).set(payload)
    log.info(f'[세종이관] Firestore 저장 완료: {SEJONG_MIG_COLLECTION}/{date_str}')
    return payload


def get_sejong_migration(date_str: str) -> dict:
    """특정일 세종이관 데이터 조회. 없으면 None."""
    try:
        db = _get_db()
        doc = db.collection(SEJONG_MIG_COLLECTION).document(date_str).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        log.warning(f"[세종이관] 조회 실패: {e}")
        return None


def get_month_sejong_migration(year: int, month: int) -> dict:
    """월 전체 세종이관 데이터 조회. {date_str: payload} 형태 (엑셀 시트용)."""
    result = {}
    try:
        db = _get_db()
        prefix = f'{year:04d}-{month:02d}'
        docs = db.collection(SEJONG_MIG_COLLECTION).stream()
        for doc in docs:
            if doc.id.startswith(prefix):
                result[doc.id] = doc.to_dict()
    except Exception as e:
        log.warning(f"[세종이관] 월 조회 실패: {e}")
    return result