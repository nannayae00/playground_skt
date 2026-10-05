"""
backfill_hourly_pattern.py  v1.4
소급 학습 스크립트 — ktoa_hourly → ktoa_hourly_pattern / ktoa_hourly_pattern_28

[수정 이력]
v1.5 | 2026-06-01 | 단일 컬렉션 28키 전환 + bw_manual 우선 + _band 5단계
  - COL_140 제거, ktoa_hourly_pattern 단일 컬렉션 28키 운영
  - bw 결정: bw_ai_prev 우선 → bw_manual 우선, 없으면 bw_ai_prev
  - _band() 5단계: zero/low/mid/base/high
  - make_key_140 제거, make_key_28만 사용
v1.4 | 2026-05-15 | 28키 컬렉션 동시 backfill 추가
  - 140키(기존): 요일 × 주차 × bw밴드  ex) '1_3_base'
  - 28키(신규):  요일 × bw밴드          ex) '1_base'
    · 컬렉션: ktoa_hourly_pattern_28
    · 주차 정보 제거 → 키당 데이터 5배 증가
    · 43일치 backfill 시 즉시 n=6~8 확보, 3개월 내 MED(n=10) 도달
  - save_pattern(): 140키 + 28키 동시 저장 (트랜잭션 아님, 각 독립)
  - main(): 두 컬렉션 before/after 현황 모두 출력
  - 운영 방식:
    · 예측 시 140키 우선 (주차별 특수 패턴)
    · 140키 LOW(n<10) → 28키 폴백 (더 안정적)
    · 6개월 후 140키 MED 도달 시 자연스럽게 주력 전환

v1.3 | 2026-05-15 | 초기 중복 DB 필터링 + 누락 시간대 보간
  - 정상 10분단위 문서(MM=01/11/21/31/41/51) 최우선 선택
  - 누락 시간대 선형 보간 (앞뒤 시간으로 추정)
  - 날짜별 문서 품질 요약 로그

v1.2 | 2026-05-15 | 버그 수정 + 성능 개선
v1.1 | 2026-03-17 | 최초 작성

실행 방법:
  cd ~/mvno-bot-cloudrun/mvno-bot-cloudrun
  python3 backfill_hourly_pattern.py

대상 범위: 2026-03-16 ~ 어제 (자동 계산)
소요 시간: 약 3~5분 (두 컬렉션 동시 저장)
"""

import sys
import os
import re as _re
import copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date, timedelta
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore as fs

# ── Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
db = fs.Client(project='mvno-484509', database='mvno-data')

# ── 컬렉션 이름
COL = 'ktoa_hourly_pattern'  # 요일 × bw밴드 (28키 단일 컬렉션)

# ── 대상 날짜 범위
START_DATE = date(2026, 3, 16)
END_DATE   = date.today() - timedelta(days=1)  # 어제까지

# ── 정상 10분단위 문서의 분(MM) 집합
#    실제 수집: 10:11, 10:21, ... → 분은 항상 X1 (01/11/21/31/41/51)
VALID_MINUTES = {'01', '11', '21', '31', '41', '51'}


# ══════════════════════════════════════════════════════
# 키 생성
# ══════════════════════════════════════════════════════

def _band(v: float) -> str:
    if v == 0.0:  return 'zero'
    if v <= 0.6:  return 'low'   # 토요일/선거일/공휴일영업
    if v <= 0.9:  return 'mid'   # 공휴일전날/연휴낀날
    if v <= 1.1:  return 'base'  # 일반 평일
    return 'high'                 # 월말/월초/공휴일다음날반등


def make_key(date_str: str, bw: float) -> str:
    """요일 × bw밴드 (28키)  ex) '1_base'"""
    d  = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()
    return f"{wd}_{_band(bw)}"


# ══════════════════════════════════════════════════════
# 데이터 bulk 로드
# ══════════════════════════════════════════════════════

def load_all_daily(start_date: date, end_date: date) -> dict:
    """ktoa_daily 전체 bulk 로드 → {date_str: dict}"""
    print("ktoa_daily 전체 로드 중...", flush=True)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str   = end_date.strftime('%Y-%m-%d')
    by_date = {}
    try:
        docs = (db.collection('ktoa_daily')
                .where('date', '>=', start_str)
                .where('date', '<=', end_str)
                .stream())
        for doc in docs:
            by_date[doc.id] = doc.to_dict()
        print(f"  → {len(by_date)}일치 daily 로드 완료")
    except Exception as e:
        print(f"  ⚠ daily 전체 로드 실패: {e}")
    return by_date


def load_all_hourly(start_date: date, end_date: date) -> dict:
    """
    ktoa_hourly 전체 bulk 로드 → 날짜별 정제된 [doc, ...] 반환

    정제 기준 (시간별 최적 문서 선택):
      1순위: 분(MM)이 01/11/21/31/41/51인 정상 10분단위 문서 (이른 분 우선)
      2순위: 정상 문서 없는 시간대만 비정상 문서 수용
    """
    print("ktoa_hourly 전체 로드 중...", flush=True)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str   = end_date.strftime('%Y-%m-%d')

    by_date_hour: dict = {}
    raw_count = 0

    try:
        docs = (db.collection('ktoa_hourly')
                .order_by('__name__')
                .start_at({'__name__': f'{start_str}_0000'})
                .end_at({'__name__': f'{end_str}_2359'})
                .stream())

        for doc in docs:
            d        = doc.to_dict()
            ds       = doc.id[:10]
            doc_min  = doc.id[13:15] if len(doc.id) >= 15 else 'XX'
            is_valid = doc_min in VALID_MINUTES

            ref  = d.get('reference_time', '')
            m    = _re.search(r'(\d+)시', ref)
            if not m:
                continue
            hour = int(m.group(1))
            if not (10 <= hour <= 19):
                continue

            raw_count += 1
            slot = by_date_hour.setdefault(ds, {})

            if hour not in slot:
                slot[hour] = {'doc': d, 'has_valid': is_valid, 'min': doc_min}
            else:
                existing = slot[hour]
                if is_valid and not existing['has_valid']:
                    slot[hour] = {'doc': d, 'has_valid': True, 'min': doc_min}
                elif is_valid and existing['has_valid']:
                    if doc_min < existing['min']:
                        slot[hour] = {'doc': d, 'has_valid': True, 'min': doc_min}

        by_date: dict = {}
        valid_total = fallback_total = 0
        for ds, hour_map in by_date_hour.items():
            docs_list = []
            for h in sorted(hour_map.keys()):
                entry = hour_map[h]
                entry['doc']['_hour']      = h
                entry['doc']['_has_valid'] = entry['has_valid']
                entry['doc']['_doc_min']   = entry['min']
                docs_list.append(entry['doc'])
                if entry['has_valid']:
                    valid_total += 1
                else:
                    fallback_total += 1
            by_date[ds] = docs_list

        total_docs = sum(len(v) for v in by_date.values())
        print(f"  → 원본 {raw_count}개 → 정제 후 {total_docs}개 "
              f"({valid_total}정상/{fallback_total}비정상수용), {len(by_date)}일치")

    except Exception as e:
        print(f"  ⚠ hourly 전체 로드 실패: {e}")
        by_date = {}

    return by_date


# ══════════════════════════════════════════════════════
# 누락 시간대 선형 보간
# ══════════════════════════════════════════════════════

def _interpolate_missing_hours(hourly_docs: list) -> tuple:
    """
    10~19시 중 누락된 시간대를 앞뒤 값으로 선형 보간.
    Returns: (filled_docs, interp_hours, skip_hours)
    """
    FIELDS_INTERP = [
        ('mno_out',    ['S', 'K', 'L', '계']),
        ('mvno_in',    ['SM', 'KM', 'LM', '계']),
        ('mvno_out',   ['SM', 'KM', 'LM', '계']),
        ('net_change', ['SM', 'KM', 'LM', '계']),
    ]

    hour_map: dict = {}
    for doc in hourly_docs:
        h = doc.get('_hour')
        if h is None:
            ref = doc.get('reference_time', '')
            mm  = _re.search(r'(\d+)시', ref)
            h   = int(mm.group(1)) if mm else None
        if h is not None and 10 <= h <= 19:
            hour_map[h] = doc

    if not hour_map:
        return hourly_docs, [], []

    filled       = []
    interp_hours = []
    skip_hours   = []

    for hour in range(10, 20):
        if hour in hour_map:
            filled.append(hour_map[hour])
            continue

        prev_h = max((h for h in hour_map if h < hour), default=None)
        next_h = min((h for h in hour_map if h > hour), default=None)

        if prev_h is None or next_h is None:
            skip_hours.append(hour)
            continue

        ratio    = (hour - prev_h) / (next_h - prev_h)
        prev_doc = hour_map[prev_h]
        next_doc = hour_map[next_h]
        new_doc  = copy.deepcopy(prev_doc)
        new_doc['_hour']          = hour
        new_doc['_interpolated']  = True
        new_doc['reference_time'] = f'{hour}시 00분 이전 (보간)'

        for field, keys in FIELDS_INTERP:
            pd = prev_doc.get(field, {})
            nd = next_doc.get(field, {})
            new_doc[field] = {
                k: int((pd.get(k, 0) or 0) + ((nd.get(k, 0) or 0) - (pd.get(k, 0) or 0)) * ratio)
                for k in keys
            }

        filled.append(new_doc)
        interp_hours.append(hour)

    filled.sort(key=lambda x: x.get('_hour', 99))
    return filled, interp_hours, skip_hours


# ══════════════════════════════════════════════════════
# 컬렉션 저장 헬퍼
# ══════════════════════════════════════════════════════

def _write_to_collection(col_name: str, key: str, hour_rates: dict) -> bool:
    """
    hour_rates를 지정 컬렉션의 key 문서에 누적 저장.
    Returns: True(성공) / False(실패)
    """
    try:
        ref_doc  = db.collection(col_name).document(key)
        snap     = ref_doc.get()
        existing = snap.to_dict() if snap.exists else {}
        n        = existing.get('sample_count', 0)

        for field_key, h_rates in hour_rates.items():
            if not h_rates:
                continue
            field_name   = f'hours_{field_key}'
            existing_hrs = existing.get(field_name, {})
            for h, rate in h_rates.items():
                hk = str(h)
                existing_hrs.setdefault(hk, [])
                existing_hrs[hk].append(rate)
                if len(existing_hrs[hk]) > 90:
                    existing_hrs[hk] = existing_hrs[hk][-90:]
            existing[field_name] = existing_hrs

        existing['key']          = key
        existing['sample_count'] = n + 1
        existing['last_updated'] = datetime.now(tz=None)  # utcnow 대신
        ref_doc.set(existing, merge=True)
        return True

    except Exception as e:
        print(f"  ⚠ {col_name}/{key} 저장 오류: {e}")
        return False


# ══════════════════════════════════════════════════════
# 패턴 저장 (140키 + 28키 동시)
# ══════════════════════════════════════════════════════

def save_pattern(date_str: str, hourly_docs: list,
                 closing_skt: int, bw: float) -> tuple:
    """
    ktoa_hourly_pattern 단일 컬렉션 28키 저장

    Returns:
      (result: str, info: dict)
      result: 'ok' | 'skip_no_closing' | 'skip_no_skt' | 'skip_no_hourly' | 'error'
    """
    if bw <= 0:
        return 'skip_no_closing', {}

    key = make_key(date_str, bw)

    # ── 누락 시간대 보간
    filled_docs, interp_hours, skip_hours = _interpolate_missing_hours(hourly_docs)
    info = {
        'interp':     interp_hours,
        'skip':       skip_hours,
        'n_docs':     len(filled_docs),
        'n_fallback': sum(1 for d in hourly_docs if not d.get('_has_valid', True)),
        'key':        key,
    }

    # ── 마감 기준 문서 (19시 이후 최근값)
    closing_doc = None
    for doc in reversed(filled_docs):
        if (doc.get('_hour') or 0) >= 19:
            closing_doc = doc
            break
    if not closing_doc:
        closing_doc = filled_docs[-1] if filled_docs else None
    if not closing_doc:
        return 'skip_no_hourly', info

    # ── 마감값 결정 (ktoa_daily 확정값 우선)
    _base_skt = closing_skt if closing_skt > 0 \
                else (closing_doc.get('mno_out', {}).get('S', 0) or 0)
    if _base_skt <= 0:
        return 'skip_no_skt', info

    closing_vals = {
        'skt':    _base_skt,
        'sm':     closing_doc.get('mvno_in',    {}).get('SM', 0) or 0,
        'km':     closing_doc.get('mvno_in',    {}).get('KM', 0) or 0,
        'lm':     closing_doc.get('mvno_in',    {}).get('LM', 0) or 0,
        'sm_out': closing_doc.get('mvno_out',   {}).get('SM', 0) or 0,
        'km_out': closing_doc.get('mvno_out',   {}).get('KM', 0) or 0,
        'lm_out': closing_doc.get('mvno_out',   {}).get('LM', 0) or 0,
        'net_sm': closing_doc.get('net_change', {}).get('SM', 0) or 0,
        'net_km': closing_doc.get('net_change', {}).get('KM', 0) or 0,
        'net_lm': closing_doc.get('net_change', {}).get('LM', 0) or 0,
    }

    # ── 시간대별 진행률 계산 (공통 — 두 컬렉션에 동일 사용)
    hour_rates: dict = {k: {} for k in closing_vals}
    for doc in filled_docs:
        hour = doc.get('_hour')
        if hour is None:
            ref = doc.get('reference_time', '')
            mm  = _re.search(r'(\d+)시', ref)
            hour = int(mm.group(1)) if mm else None
        if hour is None or not (10 <= hour <= 19):
            continue

        vals = {
            'skt':    doc.get('mno_out',    {}).get('S',  0) or 0,
            'sm':     doc.get('mvno_in',    {}).get('SM', 0) or 0,
            'km':     doc.get('mvno_in',    {}).get('KM', 0) or 0,
            'lm':     doc.get('mvno_in',    {}).get('LM', 0) or 0,
            'sm_out': doc.get('mvno_out',   {}).get('SM', 0) or 0,
            'km_out': doc.get('mvno_out',   {}).get('KM', 0) or 0,
            'lm_out': doc.get('mvno_out',   {}).get('LM', 0) or 0,
            'net_sm': doc.get('net_change', {}).get('SM', 0) or 0,
            'net_km': doc.get('net_change', {}).get('KM', 0) or 0,
            'net_lm': doc.get('net_change', {}).get('LM', 0) or 0,
        }
        for k, cv in closing_vals.items():
            if cv != 0:
                r = round(vals[k] / cv, 4)
                if 0.01 <= r <= 1.05:
                    hour_rates[k][hour] = r

    if not hour_rates.get('skt'):
        return 'skip_no_skt', info

    # ── 단일 컬렉션 저장
    ok = _write_to_collection(COL, key, hour_rates)
    return ('ok' if ok else 'error'), info


# ══════════════════════════════════════════════════════
# 컬렉션 현황 출력 헬퍼
# ══════════════════════════════════════════════════════

def _print_collection_status(col_name: str, before_snap: dict, label: str):
    after_list = list(db.collection(col_name).stream())
    print(f"\n=== [{label}] {col_name} 현황 (총 {len(after_list)}키) ===")
    for p in sorted(after_list, key=lambda x: x.id):
        pd        = p.to_dict()
        n         = pd.get('sample_count', 0)
        n_before  = before_snap.get(p.id, 0)
        delta_str = f'+{n - n_before}' if n > n_before else '-'
        conf      = 'HIGH' if n >= 30 else ('MED ' if n >= 10 else 'LOW ')
        h_skt = len(pd.get('hours_skt', {}))
        h_sm  = len(pd.get('hours_sm',  {}))
        h_km  = len(pd.get('hours_km',  {}))
        h_lm  = len(pd.get('hours_lm',  {}))
        print(f"  {p.id:20s}  n={n:3d}({delta_str:>4s})  [{conf}]  "
              f"skt={h_skt}h sm={h_sm}h km={h_km}h lm={h_lm}h")


# ══════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("소급 학습 (backfill) 시작")
    print(f"대상 범위: {START_DATE} ~ {END_DATE}")
    print(f"정상 분(MM) 기준: {sorted(VALID_MINUTES)}")
    print(f"저장 컬렉션: {COL} (28키, bw_manual 우선)")
    print("=" * 60)
    print()

    # ── before 스냅샷
    before = {p.id: p.to_dict().get('sample_count', 0)
              for p in db.collection(COL).stream()}
    print(f"[before] {COL}: {len(before)}키")
    print()

    # ── bulk 로드
    all_daily  = load_all_daily(START_DATE, END_DATE)
    all_hourly = load_all_hourly(START_DATE, END_DATE)
    print()

    counts = {'ok': 0, 'skip_zero': 0, 'skip_hourly': 0, 'skip_no_skt': 0, 'fail': 0}
    item_ok      = {k: 0 for k in ['sm','km','lm','sm_out','km_out','lm_out']}
    total_interp = total_skip = total_fallback = 0

    current    = START_DATE
    total_days = (END_DATE - START_DATE).days + 1
    idx        = 0

    while current <= END_DATE:
        date_str = current.strftime('%Y-%m-%d')
        idx += 1
        print(f"[{idx:3d}/{total_days}] {date_str}", end='  ', flush=True)

        dd          = all_daily.get(date_str, {})
        closing_skt = int(dd.get('mno_out', {}).get('S', 0) or 0)
        # ★ bw_manual 우선, 없으면 bw_ai_prev
        _m = float(dd.get('bw_manual') or 0)
        bw = _m if _m > 0 else float(dd.get('bw_ai_prev') or 0)

        if bw <= 0:
            print("스킵 (bw=0 → 공휴일/일요일)")
            counts['skip_zero'] += 1
            current += timedelta(days=1)
            continue

        hourly_docs = all_hourly.get(date_str, [])
        if len(hourly_docs) < 3:
            print(f"스킵 (hourly {len(hourly_docs)}개 부족)")
            counts['skip_hourly'] += 1
            current += timedelta(days=1)
            continue

        result, info = save_pattern(date_str, hourly_docs, closing_skt, bw)

        total_interp   += len(info.get('interp', []))
        total_skip     += len(info.get('skip',   []))
        total_fallback += info.get('n_fallback', 0)

        if result == 'ok':
            closing_doc = next(
                (doc for doc in reversed(hourly_docs) if (doc.get('_hour') or 0) >= 19),
                hourly_docs[-1] if hourly_docs else {}
            )
            for item, fld, sub in [
                ('sm',     'mvno_in',  'SM'), ('km',     'mvno_in',  'KM'),
                ('lm',     'mvno_in',  'LM'), ('sm_out', 'mvno_out', 'SM'),
                ('km_out', 'mvno_out', 'KM'), ('lm_out', 'mvno_out', 'LM'),
            ]:
                if closing_doc.get(fld, {}).get(sub, 0):
                    item_ok[item] += 1

            interp_str = f" 보간:{info['interp']}" if info['interp'] else ''
            skip_str   = f" 스킵:{info['skip']}"   if info['skip']   else ''
            print(f"✅  key={info.get('key','')}  skt={closing_skt:,}  bw={bw}"
                  f"{interp_str}{skip_str}")
            counts['ok'] += 1

        elif result == 'skip_no_skt':
            print("스킵 (T-Out=0)")
            counts['skip_no_skt'] += 1
        elif result in ('skip_no_hourly', 'skip_no_closing'):
            print(f"스킵 ({result})")
            counts['skip_hourly'] += 1
        else:
            print("❌ 오류")
            counts['fail'] += 1

        current += timedelta(days=1)

    # ── 결과 요약
    print()
    print("=" * 60)
    print(f"  성공          : {counts['ok']}일")
    print(f"  스킵(bw=0)    : {counts['skip_zero']}일  ← 공휴일/일요일")
    print(f"  스킵(hourly)  : {counts['skip_hourly']}일  ← 데이터 부족")
    print(f"  스킵(skt=0)   : {counts['skip_no_skt']}일")
    print(f"  오류          : {counts['fail']}일")
    print()
    print(f"  누락 보간 적용  : 총 {total_interp}시간대")
    print(f"  보간 불가 스킵  : 총 {total_skip}시간대")
    print(f"  비정상 문서 수용: 총 {total_fallback}건")
    print()
    if counts['ok'] > 0:
        print(f"  항목별 coverage (성공 {counts['ok']}일 기준):")
        for item, cnt in item_ok.items():
            pct = int(cnt / counts['ok'] * 100)
            bar = '█' * (pct // 5)
            print(f"    {item:8s}: {cnt:3d}일 ({pct:3d}%)  {bar}")

    # ── after 현황
    _print_collection_status(COL, before, 'after')
    print()
    print("※ MED(n≥10): 패턴 기반 예측 시작 / HIGH(n≥30): 주력 예측")


if __name__ == '__main__':
    main()