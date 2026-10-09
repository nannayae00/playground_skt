"""
predict_gemini.py  v1.3
작성일: 2026-04-01

[수정 이력]
v1.3 | 2026-05-06 | get_elapsed_stats() 실적 없는 날 elapsed_bw 제외
  - mno_out.S None인 날(마감 전 당일 등) elapsed_bw 미포함
  - 기존: bw는 포함되고 skt=0 → avg 낮아져 월마감 예측 왜곡
  - 수정: 실적 확정된 날만 경과bw/누적에 포함
v1.2 | 2026-04-16 | rbw 계산 정확도 수정
  - calc_monthly_forecast(): calc_remaining_bw() → get_month_bw_map() 직접 합산
    · calc_remaining_bw()가 미래날짜 calc_bw_ai() 폴백 시 부정확한 값 반환 가능
    · get_month_bw_map()은 이미 로드된 데이터 사용 → 동일 기준 보장
v1.1 | 2026-04-16 | 월마감 예측 범위 동적 축소
  - calc_monthly_forecast(): ±10% 고정 밴드 → 잔여 영업일수 기반 동적 밴드
    · 잔여 bw >= 15일: ±10% (기존)
    · 잔여 bw 10~14일: ±7%
    · 잔여 bw 5~9일: ±5%
    · 잔여 bw 3~4일: ±3%
    · 잔여 bw <= 2일: ±1.5%
  - 유사일 분포(p25~p75)와 교차 검증하여 범위를 더 좁힘
v1.0 | 2026-04-01 | 최초 작성
  - get_elapsed_stats()   : 월초~오늘 경과 실적/bw 집계
  - calc_monthly_forecast(): 월 마감 예측 (실질 일평균 × 잔여 bw)
  - get_similar_days()    : 유사 과거일 마감값 분포 (일별 데이터 기반)
  - call_gemini_forecast(): Gemini 멀티시그널 예측 호출
  - get_forecast()        : 메인 진입점 (Gemini 실패 시 수식 폴백)
  - build_skt_section()   : 시간별 메시지 SKT OUT 섹션 조립
  - build_skt_closing()   : 일마감 메시지 SKT OUT 섹션 조립

[예측 로직]
  Python: 실질 일평균, 잔여bw, 유사 과거일 분포 계산 (수식)
  Gemini: 뽐뿌 트렌드, 경쟁사 변화, 이벤트, 시간대 컨텍스트 종합 판단
  폴백  : Gemini 실패 시 Python 수식 결과 그대로 사용

[시간대 패턴]
  ktoa_hourly_pattern/{key} 에 누적 저장 (매일 마감 후 자동 학습)
  키 구조 변경: {요일}_{주차}_{bw밴드}(140키) → {요일}_{bw밴드}(28키)
  bw 결정: get_bw_final(bw_ai_prev우선) → bw_manual 우선, 없으면 bw_ai_prev
  _band() 4단계 → 5단계 (zero/low/mid/base/high)
  _get_bw_for_pattern(): 패턴 키용 bw 조회 신규 함수
  get_similar_days(): _bw_band() 5단계로 통일
  n < 10: 신뢰도 LOW, n < 30: MED, n >= 30: HIGH
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from daily_memo import memo_daily  # [추가 20261009] Firestore 읽기 절감

log = logging.getLogger(__name__)

KTOA_TOUT_GOAL = int(os.environ.get('KTOA_TOUT_GOAL', 42000))

_gemini_model = None


def _get_model():
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai
        key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY', '')
        genai.configure(api_key=key)
        _gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    return _gemini_model


def _get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


def get_tout_goal(year: int, month: int) -> int:
    """월별 T Out 목표 조회 (Firestore 우선, 환경변수 폴백)"""
    ym = f'{year:04d}-{month:02d}'
    try:
        db = _get_db()
        doc = (db.collection('ktoa_config').document('tout_goal')
               .collection('monthly').document(ym).get())
        if doc.exists:
            goal = doc.to_dict().get('goal', 0)
            if goal > 0:
                return int(goal)
    except Exception as e:
        log.warning(f"T Out 목표 조회 실패: {e}")
    return int(os.environ.get('KTOA_TOUT_GOAL', '42000'))


def get_elapsed_stats(year: int, month: int, today_day: int) -> dict:
    """
    월초~오늘까지 경과 실적/bw 집계
    Returns:
        cum_skt_out, cum_mvno_in, elapsed_bw, daily_avg_skt, daily_avg_mvno
    """
    from bw_engine import get_bw_final, is_zero_day
    from calendar import monthrange

    db = _get_db()
    p1 = f"{year:04d}-{month:02d}-01"
    p2 = f"{year:04d}-{month:02d}-{today_day:02d}"

    try:
        docs = (db.collection('ktoa_daily')
                .where('date', '>=', p1)
                .where('date', '<=', p2)
                .stream())
        fs_data = {doc.id: doc.to_dict() for doc in docs}
    except Exception as e:
        log.error(f"get_elapsed_stats 조회 실패: {e}")
        fs_data = {}

    cum_skt = 0
    cum_mvno = 0
    elapsed_bw = 0.0
    history = []  # (skt, bw) 확정 실적 이력

    for day in range(1, today_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        data = fs_data.get(ds, {})
        bw = get_bw_final(ds, data)
        if bw <= 0:
            continue
        # 실적 미집계(마감 전 당일 등): mno_out.S 없으면 경과bw에서 제외
        skt = data.get('mno_out', {}).get('S', None)
        if skt is None:
            continue
        mvno = data.get('mvno_in', {}).get('계', 0) or 0
        elapsed_bw += bw
        cum_skt  += int(skt)
        cum_mvno += int(mvno)
        history.append((int(skt), bw))

    # ── 단순 bw가중 평균
    daily_avg_skt  = round(cum_skt  / elapsed_bw, 1) if elapsed_bw > 0 else 0
    daily_avg_mvno = round(cum_mvno / elapsed_bw, 1) if elapsed_bw > 0 else 0

    # ── 최근 5일 2배 가중 평균 (트렌드 반영)
    # 단위: 건/bw → rbw와 동일 기준이라 fc = cum + avg_recent × rbw 로 사용 가능
    if len(history) >= 3:
        recent = history[-5:]
        older  = history[:-5]
        r_skt = sum(s for s, b in recent)
        r_bw  = sum(b for s, b in recent)
        o_skt = sum(s for s, b in older)
        o_bw  = sum(b for s, b in older)
        w_skt = r_skt * 2 + o_skt
        w_bw  = r_bw  * 2 + o_bw
        daily_avg_skt_recent = round(w_skt / w_bw, 1) if w_bw > 0 else daily_avg_skt
    else:
        daily_avg_skt_recent = daily_avg_skt  # 데이터 부족 시 단순 평균 사용

    return {
        'cum_skt_out':         cum_skt,
        'cum_mvno_in':         cum_mvno,
        'elapsed_bw':          round(elapsed_bw, 3),
        'daily_avg_skt':       daily_avg_skt,        # 전체 단순 bw가중 평균
        'daily_avg_skt_recent': daily_avg_skt_recent, # 최근 5일 2배 가중 평균
        'daily_avg_mvno':      daily_avg_mvno,
    }


def calc_monthly_forecast(year: int, month: int, today_day: int,
                          monthly_goal: int, elapsed: dict) -> dict:
    """월 마감 예측
    [v1.2] rbw 계산: calc_remaining_bw() → get_month_bw_map() 직접 합산
    미래 날짜 bw_ai_prev 없을 때 calc_bw_ai() 폴백이 부정확할 수 있어서
    get_month_bw_map()으로 이미 로드된 데이터 기준으로 통일
    """
    from bw_engine import get_month_bw_map
    from calendar import monthrange

    cum  = elapsed['cum_skt_out']
    avg  = elapsed['daily_avg_skt']

    # [v1.2] rbw: get_month_bw_map 직접 합산 (today_day 다음날~말일)
    bw_map   = get_month_bw_map(year, month)
    last_day = monthrange(year, month)[1]
    rbw = round(sum(
        bw_map.get(f"{year:04d}-{month:02d}-{d:02d}", 0.0)
        for d in range(today_day + 1, last_day + 1)
    ), 3)

    # elapsed_bw=0 (월초 첫날 등) → 잔여일평균으로 추정
    _elapsed_bw = elapsed.get('elapsed_bw', 0)
    if _elapsed_bw <= 0 or avg <= 0:
        _total_bw = rbw
        avg = int(monthly_goal / _total_bw) if _total_bw > 0 else 0
    forecast      = int(cum + avg * rbw)

    # [v1.1] 잔여 영업일수 기반 동적 밴드 (잔여일 적을수록 범위 축소)
    if rbw >= 15:
        _band = 0.10    # ±10%
    elif rbw >= 10:
        _band = 0.07    # ±7%
    elif rbw >= 5:
        _band = 0.05    # ±5%
    elif rbw >= 3:
        _band = 0.03    # ±3%
    else:
        _band = 0.015   # ±1.5%

    forecast_low  = int(forecast * (1 - _band))
    forecast_high = int(forecast * (1 + _band))
    remaining     = max(0, monthly_goal - cum)
    need_avg      = int(remaining / rbw) if rbw > 0 else 0
    ach_rate      = round(cum / monthly_goal * 100, 1) if monthly_goal > 0 else 0
    # [v1.3] SKT OUT은 초과 이탈이 문제 → 목표 미달은 정상, 초과(105%+)일 때만 경고로 반전
    on_track      = forecast <= monthly_goal * 1.05

    return {
        'forecast':        forecast,
        'forecast_low':    forecast_low,
        'forecast_high':   forecast_high,
        'remaining_bw':    rbw,
        'remaining_goal':  remaining,
        'daily_avg_need':  need_avg,
        'achievement_rate': ach_rate,
        'on_track':        on_track,
        'band_pct':        _band,       # 디버그용
    }


@memo_daily
def get_similar_days(date_str: str, bw: float, top_n: int = 5) -> dict:
    """
    유사 과거일 마감값 분포
    같은 요일 × 주차(±1) × bw구간에서 최근 날들 조회
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()
    week = (d.day - 1) // 7 + 1

    def _bw_band(v):
        if v == 0.0:  return 'zero'
        if v <= 0.6:  return 'low'
        if v <= 0.9:  return 'mid'
        if v <= 1.1:  return 'base'
        return 'high'

    cutoff = (d - timedelta(days=548)).strftime('%Y-%m-%d')
    try:
        db = _get_db()
        docs = (db.collection('ktoa_daily')
                .where('date', '>=', cutoff)
                .where('date', '<',  date_str)
                .stream())
        candidates = []
        for doc in docs:
            dd = datetime.strptime(doc.id, '%Y-%m-%d')
            if dd.weekday() != wd:
                continue
            doc_week = (dd.day - 1) // 7 + 1
            if abs(doc_week - week) > 1:
                continue
            data = doc.to_dict()
            doc_bw = data.get('bw_final') or data.get('bw_performance') or 0
            if doc_bw > 0 and _bw_band(float(doc_bw)) != _bw_band(bw):
                continue
            val = data.get('mno_out', {}).get('S', 0) or 0
            if val > 0:
                candidates.append({'date': doc.id, 'value': val})
    except Exception as e:
        log.error(f"get_similar_days 실패: {e}")
        return {'count': 0, 'median': 0, 'p25': 0, 'p75': 0, 'dates': []}

    if not candidates:
        return {'count': 0, 'median': 0, 'p25': 0, 'p75': 0, 'dates': []}

    candidates.sort(key=lambda x: x['date'], reverse=True)
    candidates = candidates[:top_n * 3]
    vals = sorted([c['value'] for c in candidates])
    mid = vals[len(vals) // 2]
    clean = [c for c in candidates if c['value'] < mid * 2.0][:top_n]

    if not clean:
        return {'count': 0, 'median': 0, 'p25': 0, 'p75': 0, 'dates': []}

    v = sorted([c['value'] for c in clean])
    n = len(v)
    return {
        'count':  n,
        'median': v[n // 2],
        'p25':    v[max(0, n // 4)],
        'p75':    v[min(n - 1, (3 * n) // 4)],
        'dates':  [c['date'] for c in clean],
    }


def get_hourly_pattern(date_str: str, current_hour: int, bw: float,
                       current_minute: int = 0) -> dict:
    """
    시간대별 항목별 진행률 패턴 조회 + 분(minute) 기반 선형 보간 (C안)

    [v1.1] current_minute 추가:
      - 정시(minute=0): 기존과 동일, 해당 시간 패턴률 사용
      - 10분 단위(minute>0): 현재 시간과 다음 시간 패턴률을 선형 보간
        예) 16:30 → rate = rate_16 + (rate_17 - rate_16) × 0.5
        → 시간이 지날수록 다음 시간 예측에 자연스럽게 수렴
      - 다음 시간 패턴 없으면 보간 포기, 현재 시간 패턴률 그대로 사용 (안전 폴백)

    Returns: {
        'available': bool, 'sample_count': int, 'confidence': str,
        'rate_at_hour': float,  # SKT 진행률 (기존 호환)
        'rates': {'skt':0.18, 'sm':0.17, ...},
        'interpolated': bool,   # 보간 적용 여부
        'interp_ratio': float,  # 보간 비율 (0.0~1.0)
    }
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()
    week = (d.day - 1) // 7 + 1

    def _band(v):
        if v == 0.0:  return 'zero'
        if v <= 0.6:  return 'low'   # 토요일/선거일/공휴일영업
        if v <= 0.9:  return 'mid'   # 공휴일전날/연휴낀날
        if v <= 1.1:  return 'base'  # 일반 평일
        return 'high'                 # 월말/월초/공휴일다음날반등

    key = f"{wd}_{_band(bw)}"  # 28키 (주차 제거)
    FIELDS = ['skt','sm','km','lm','sm_out','km_out','lm_out','net_sm','net_km','net_lm']

    def _extract_rates(data_dict, hour):
        rates = {}
        for fk in FIELDS:
            fn = f'hours_{fk}'
            hrs = data_dict.get(fn, {})
            if not hrs and fk == 'skt':
                hrs = data_dict.get('hours', {})
            r = hrs.get(str(hour), [])
            if not r:
                for adj in [hour - 1, hour + 1]:
                    r = hrs.get(str(adj), [])
                    if r: break
            rates[fk] = round(sum(r) / len(r), 4) if r else None
        return rates

    def _load_data_dict(db):
        """패턴 문서 조회 (키 없으면 같은 bw밴드 전체 평균)"""
        doc = db.collection('ktoa_hourly_pattern').document(key).get()
        if not doc.exists:
            log.info(f"패턴 키 {key} 없음 → bw밴드({_band(bw)}) 전체 평균 시도")
            all_docs = list(db.collection('ktoa_hourly_pattern').stream())
            # 28키 구조: {wd}_{band} → 같은 bw밴드 전체 (요일 무관)
            same_band = [
                dc.to_dict() for dc in all_docs
                if dc.id.endswith(f"_{_band(bw)}")
            ]
            if not same_band:
                return None, 0
            merged = {}
            total_n = 0
            for sd in same_band:
                total_n += sd.get('sample_count', 1)
                for fk in FIELDS:
                    fn = f'hours_{fk}'
                    src = sd.get(fn, sd.get('hours', {}) if fk == 'skt' else {})
                    for h, rv in src.items():
                        merged.setdefault(fn, {}).setdefault(h, [])
                        merged[fn][h].extend(rv if isinstance(rv, list) else [rv])
            avg_data = {fn: {h: [sum(v)/len(v)] for h,v in hrs.items()} for fn,hrs in merged.items()}
            avg_data['sample_count'] = total_n
            return avg_data, total_n
        return doc.to_dict(), doc.to_dict().get('sample_count', 0)

    try:
        db = _get_db()
        data_dict, n = _load_data_dict(db)

        if data_dict is None:
            return {'available': False, 'confidence': 'LOW', 'sample_count': 0}

        n = data_dict.get('sample_count', n)
        rates = _extract_rates(data_dict, current_hour)

        if rates.get('skt') is None:
            return {'available': False, 'confidence': 'LOW', 'sample_count': n}

        confidence = 'HIGH' if n >= 30 else ('MED' if n >= 10 else 'LOW')

        # [v1.1] 분(minute) > 0 이면 다음 시간 패턴률로 선형 보간
        interpolated = False
        interp_ratio = 0.0

        if current_minute > 0 and current_hour < 19:
            next_hour = current_hour + 1
            rates_next = _extract_rates(data_dict, next_hour)

            if rates_next.get('skt') is not None:
                # 보간 비율: 분/60 (16:30 → 0.5, 16:10 → 0.167, 16:50 → 0.833)
                interp_ratio = current_minute / 60.0
                interpolated_rates = {}
                for fk in FIELDS:
                    r_cur  = rates.get(fk)
                    r_next = rates_next.get(fk)
                    if r_cur is not None and r_next is not None:
                        interpolated_rates[fk] = round(
                            r_cur + (r_next - r_cur) * interp_ratio, 4
                        )
                    else:
                        interpolated_rates[fk] = r_cur  # 한쪽 없으면 현재값 유지
                rates = interpolated_rates
                interpolated = True
                log.debug(f"패턴 보간: {current_hour}:{current_minute:02d} "
                          f"ratio={interp_ratio:.3f} "
                          f"skt {rates.get('skt'):.4f}")
            else:
                # 다음 시간 패턴 없음 → 안전 폴백 (현재 시간 패턴 그대로)
                log.debug(f"다음 시간({next_hour}시) 패턴 없음 → 보간 스킵, 현재 패턴 유지")

        return {
            'available':    True,
            'rate_at_hour': rates['skt'],
            'rates':        rates,
            'sample_count': n,
            'confidence':   confidence,
            'interpolated': interpolated,
            'interp_ratio': interp_ratio,
        }
    except Exception as e:
        log.warning(f"hourly_pattern 조회 실패: {e}")
        return {'available': False, 'confidence': 'LOW', 'sample_count': 0}

def _interpolate_missing_hours(hourly_docs: list) -> list:
    """
    누락된 시간 데이터를 앞뒤 보간으로 채움
    예: 11시 누락 → 10시/12시 데이터로 보간
    보간 불가 시 해당 시간 스킵 (안전 폴백)
    """
    import re as _re2
    import copy

    # 시간별 문서 매핑
    hour_map = {}
    for doc in hourly_docs:
        ref = doc.get('reference_time', '')
        m = _re2.search(r'(\d+)시', ref)
        if m:
            h = int(m.group(1))
            if 10 <= h <= 19:
                hour_map[h] = doc

    result = []
    all_hours = sorted(hour_map.keys())
    if not all_hours:
        return hourly_docs

    min_h, max_h = all_hours[0], all_hours[-1]

    for hour in range(min_h, max_h + 1):
        if hour in hour_map:
            result.append(hour_map[hour])
            continue

        # 누락 시간 → 앞뒤 보간
        prev_h = max((h for h in all_hours if h < hour), default=None)
        next_h = min((h for h in all_hours if h > hour), default=None)

        if prev_h is None or next_h is None:
            log.debug(f"보간 스킵: {hour}시 (앞뒤 데이터 없음)")
            continue

        prev_doc = hour_map[prev_h]
        next_doc = hour_map[next_h]
        ratio = (hour - prev_h) / (next_h - prev_h)

        def _interp_dict(prev_d, next_d, keys):
            """딕셔너리 값 선형 보간"""
            result = {}
            for k in keys:
                pv = prev_d.get(k, 0) or 0
                nv = next_d.get(k, 0) or 0
                result[k] = int(pv + (nv - pv) * ratio)
            return result

        interp_doc = copy.deepcopy(prev_doc)
        interp_doc['reference_time'] = f'{hour}시 00분 이전 (보간)'
        interp_doc['_interpolated'] = True

        # 각 항목 보간
        prev_mno = prev_doc.get('mno_out', {})
        next_mno = next_doc.get('mno_out', {})
        interp_doc['mno_out'] = _interp_dict(prev_mno, next_mno, ['S','K','L','계'])

        prev_mi = prev_doc.get('mvno_in', {})
        next_mi = next_doc.get('mvno_in', {})
        interp_doc['mvno_in'] = _interp_dict(prev_mi, next_mi, ['SM','KM','LM','계'])

        prev_mo = prev_doc.get('mvno_out', {})
        next_mo = next_doc.get('mvno_out', {})
        interp_doc['mvno_out'] = _interp_dict(prev_mo, next_mo, ['SM','KM','LM','계'])

        prev_net = prev_doc.get('net_change', {})
        next_net = next_doc.get('net_change', {})
        interp_doc['net_change'] = _interp_dict(prev_net, next_net, ['SM','KM','LM','계'])

        log.info(f"시간별 보간: {hour}시 ({prev_h}시~{next_h}시, ratio={ratio:.2f})")
        result.append(interp_doc)

    return result


def save_hourly_pattern(date_str: str, hourly_docs: list, closing_skt: int) -> bool:
    """
    [v1.1] 누락 시간 보간 추가: _interpolate_missing_hours()로 전처리
    일마감 후 시간대별 항목별 진행률 패턴 저장
    항목: skt(T-Out), sm/km/lm (MVNO IN), sm_out/km_out/lm_out (MVNO Out),
          net_sm/net_km/net_lm (순증감 — 마감값 기준 비율)
    """
    if closing_skt <= 0:
        return False
    import re as _re

    # ★ 패턴 키용 bw: bw_manual 우선, 없으면 bw_ai_prev
    try:
        _db0 = _get_db()
        _dd0 = _db0.collection('ktoa_daily').document(date_str).get().to_dict() or {}
        _m = float(_dd0.get('bw_manual') or 0)
        bw = _m if _m > 0 else float(_dd0.get('bw_ai_prev') or 0)
    except Exception:
        from bw_engine import get_bw_final
        bw = get_bw_final(date_str)

    d = datetime.strptime(date_str, '%Y-%m-%d')
    wd = d.weekday()

    def _band(v):
        if v == 0.0:  return 'zero'
        if v <= 0.6:  return 'low'   # 토요일/선거일/공휴일영업
        if v <= 0.9:  return 'mid'   # 공휴일전날/연휴낀날
        if v <= 1.1:  return 'base'  # 일반 평일
        return 'high'                 # 월말/월초/공휴일다음날반등

    key = f"{wd}_{_band(bw)}"  # 28키 (주차 제거)

    # 마감 hourly_docs에서 마감값 추출 (19시 또는 최근값)
    closing_doc = None
    for doc in reversed(hourly_docs):
        ref = doc.get('reference_time', '')
        m = _re.search(r'(\d+)시', ref)
        if m and int(m.group(1)) >= 19:
            closing_doc = doc
            break
    if not closing_doc and hourly_docs:
        closing_doc = hourly_docs[-1]

    if not closing_doc:
        return False

    # 마감 기준값
    closing_vals = {
        'skt':     closing_doc.get('mno_out',  {}).get('S',  0) or 0,
        'sm':      closing_doc.get('mvno_in',  {}).get('SM', 0) or 0,
        'km':      closing_doc.get('mvno_in',  {}).get('KM', 0) or 0,
        'lm':      closing_doc.get('mvno_in',  {}).get('LM', 0) or 0,
        'sm_out':  closing_doc.get('mvno_out', {}).get('SM', 0) or 0,
        'km_out':  closing_doc.get('mvno_out', {}).get('KM', 0) or 0,
        'lm_out':  closing_doc.get('mvno_out', {}).get('LM', 0) or 0,
        'net_sm':  closing_doc.get('net_change', {}).get('SM', 0) or 0,
        'net_km':  closing_doc.get('net_change', {}).get('KM', 0) or 0,
        'net_lm':  closing_doc.get('net_change', {}).get('LM', 0) or 0,
    }

    # 시간대별 진행률 계산 (누락 시간 보간 적용)
    hourly_docs = _interpolate_missing_hours(hourly_docs)
    hour_rates = {k: {} for k in closing_vals}

    for doc in hourly_docs:
        ref = doc.get('reference_time', '')
        m = _re.search(r'(\d+)시', ref)
        if not m: continue
        hour = int(m.group(1))
        if not (10 <= hour <= 19): continue

        vals = {
            'skt':    doc.get('mno_out',   {}).get('S',  0) or 0,
            'sm':     doc.get('mvno_in',   {}).get('SM', 0) or 0,
            'km':     doc.get('mvno_in',   {}).get('KM', 0) or 0,
            'lm':     doc.get('mvno_in',   {}).get('LM', 0) or 0,
            'sm_out': doc.get('mvno_out',  {}).get('SM', 0) or 0,
            'km_out': doc.get('mvno_out',  {}).get('KM', 0) or 0,
            'lm_out': doc.get('mvno_out',  {}).get('LM', 0) or 0,
            'net_sm': doc.get('net_change',{}).get('SM', 0) or 0,
            'net_km': doc.get('net_change',{}).get('KM', 0) or 0,
            'net_lm': doc.get('net_change',{}).get('LM', 0) or 0,
        }
        for k, cv in closing_vals.items():
            if cv != 0:
                hour_rates[k][hour] = round(vals[k] / cv, 4)

    if not hour_rates.get('skt'):
        return False

    try:
        db = _get_db()
        ref_doc = db.collection('ktoa_hourly_pattern').document(key)
        existing = ref_doc.get().to_dict() if ref_doc.get().exists else {}
        n = existing.get('sample_count', 0)

        for field_key, h_rates in hour_rates.items():
            field_name = f'hours_{field_key}'
            existing_hrs = existing.get(field_name, {})
            for h, rate in h_rates.items():
                hk = str(h)
                existing_hrs.setdefault(hk, [])
                existing_hrs[hk].append(rate)
                if len(existing_hrs[hk]) > 90:
                    existing_hrs[hk] = existing_hrs[hk][-90:]
            existing[field_name] = existing_hrs

        existing['key'] = key
        existing['sample_count'] = n + 1
        existing['last_updated'] = datetime.utcnow()
        ref_doc.set(existing, merge=True)
        log.info(f"hourly_pattern 저장 (항목별): {key}")
        return True
    except Exception as e:
        log.error(f"hourly_pattern 저장 실패: {e}")
        return False


def call_gemini_forecast(ctx: dict) -> Optional[dict]:
    """Gemini 호출 → JSON 결과

    [수정 20261009] 기본 비활성화 - 운영 로그상 2026-09-10 이후 성공 0건
    (09-23까지 인증 오류, 이후 응답 JSON 파싱 오류 - 숫자에 천단위 쉼표가 섞여 옴).
    항상 None(폴백)이었으므로 끄더라도 메시지는 동일하고, 과금만 되던 호출이 사라짐.
    다시 쓰려면 파싱을 고친 뒤 환경변수 KTOA_GEMINI_COMMENT=1로 켤 것.
    """
    if os.environ.get('KTOA_GEMINI_COMMENT') != '1':
        return None
    status_word = "정상 범위" if ctx['on_track_formula'] else "목표 초과 위험"
    prompt = f"""당신은 MVNO 번호이동 실적 분석 전문가입니다. JSON만 출력하세요.

※ SKT OUT(타사 이탈)은 많을수록 나쁜 지표입니다. 월마감 예측이 월목표를 "밑도는" 것은
정상/양호이며 경고 대상이 아닙니다. 예측치가 월목표를 초과(105% 이상)할 것으로 보일 때만
on_track=false로 판단하세요. 미달을 이유로 on_track=false를 주지 마세요.

=== 오늘 ({ctx['date_str']}, {ctx['wd_name']}요일, 영업일수={ctx['bw']}) ===
현재 {ctx['current_hour']}시 | SKT T-Out: {ctx['current_skt']:,}건
오늘 목표: {ctx['today_goal']:,}건 | 달성률: {ctx['pct_of_goal']}%

=== 수식 계산 결과 ===
월누적: {ctx['cum_skt']:,}건 (달성률 {ctx['ach_rate']}%)
실질 일평균: {ctx['daily_avg']:,}건
잔여 영업일수: {ctx['remaining_bw']}일
월마감 예측(수식): {ctx['fc_low']:,} ~ {ctx['fc_high']:,}건 ({status_word})

=== 유사 과거일 패턴 ===
참조 날짜 {ctx['similar_count']}일: {', '.join(ctx['similar_dates'][:3])}
유사일 마감 분포: {ctx['similar_p25']:,} ~ {ctx['similar_p75']:,}건 (중앙값 {ctx['similar_median']:,})

=== 시간대 패턴 ===
{ctx['pattern_info']}

다음 JSON만 출력 (마크다운 없이):
{{"daily_forecast": <일마감 정수>, "monthly_forecast_low": <정수>, "monthly_forecast_high": <정수>, "on_track": <true/false>, "comment": "<한국어 1줄 최대 35자>"}}

comment: 현재 페이스 평가 + 주목 포인트. 이모지 금지."""

    try:
        import google.generativeai as genai
        model = _get_model()
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=250)
        )
        text = re.sub(r'```(?:json)?', '', resp.text).strip('`').strip()
        result = json.loads(text)
        for f in ['daily_forecast', 'monthly_forecast_low', 'monthly_forecast_high', 'on_track', 'comment']:
            if f not in result:
                raise ValueError(f"필드 누락: {f}")
        if not (0 < result['daily_forecast'] < 50000):
            raise ValueError(f"비정상 daily_forecast: {result['daily_forecast']}")
        log.info(f"Gemini 예측 성공: {result}")
        return result
    except Exception as e:
        log.warning(f"Gemini 실패 (폴백): {e}")
        return None


def get_forecast(date_str: str, current_skt: int, current_hour: int,
                 hourly_docs: list, current_minute: int = 0) -> dict:
    """
    메인 예측 진입점. Gemini 실패 시 수식 폴백.
    [v1.1] current_minute 추가: 10분 단위 보간 패턴 적용
    Returns: {daily_forecast, monthly_forecast_low, monthly_forecast_high,
              on_track, comment, source, ctx}
    """
    from bw_engine import get_bw_final

    d = datetime.strptime(date_str, '%Y-%m-%d')
    year, month, day = d.year, d.month, d.day
    wd_name = ['월','화','수','목','금','토','일'][d.weekday()]

    bw        = get_bw_final(date_str)
    goal      = get_tout_goal(year, month)
    elapsed   = get_elapsed_stats(year, month, day)
    fc        = calc_monthly_forecast(year, month, day, goal, elapsed)
    similar   = get_similar_days(date_str, bw)
    # [v1.1] current_minute 전달 → 10분 단위 선형 보간
    pattern   = get_hourly_pattern(date_str, current_hour, bw, current_minute)

    daily_avg   = elapsed['daily_avg_skt']
    # 오늘 목표 = 잔여일평균 × 오늘 bw (실적기반 daily_avg 아닌 잔여 기준)
    _remaining_cum = max(0, goal - elapsed['cum_skt_out'])
    _remaining_bw_incl = fc['remaining_bw'] + bw  # 오늘 포함 잔여
    remaining_avg = int(_remaining_cum / _remaining_bw_incl) if _remaining_bw_incl > 0 else 0
    today_goal  = int(remaining_avg * bw) if bw > 0 else 0
    pct_of_goal = round(current_skt / today_goal * 100) if today_goal > 0 else 0

    # 일마감 수식 예측
    if pattern.get('available') and pattern['rate_at_hour'] > 0:
        daily_fc_formula = int(current_skt / pattern['rate_at_hour'])
        _time_label = (f"{current_hour}:{current_minute:02d}"
                       if pattern.get('interpolated') else f"{current_hour}시")
        pattern_info = (f"진행률 패턴: {_time_label} 기준 {pattern['rate_at_hour']*100:.1f}% "
                        f"({pattern['confidence']}, n={pattern['sample_count']}"
                        f"{', 보간' if pattern.get('interpolated') else ''})")
    elif similar['count'] > 0:
        daily_fc_formula = similar['median']
        pattern_info = f"시간대 패턴 학습 중 (n={pattern['sample_count']}) — 유사일 중앙값 사용"
    else:
        # [v1.2] 패턴/유사일 없으면 time_linear (경과시간 기반 외삽)
        # Gemini 조정값 대신 실제값 기반 계산 → 본문 MNO Out 예측과 일치
        _elapsed_h = max(1, current_hour - 10)
        daily_fc_formula = int(current_skt * 10 / _elapsed_h)
        pattern_info = f"패턴 학습 중 (n=0) — 시간비례 외삽"

    ctx = {
        'date_str':       date_str,
        'wd_name':        wd_name,
        'bw':             bw,
        'current_hour':   current_hour,
        'current_skt':    current_skt,
        'today_goal':     today_goal,
        'pct_of_goal':    pct_of_goal,
        'remaining_avg':  remaining_avg,
        'monthly_goal':   goal,
        'cum_skt':        elapsed['cum_skt_out'],
        'daily_avg':      daily_avg,
        'remaining_bw':   fc['remaining_bw'],
        'need_avg':       fc['daily_avg_need'],
        'fc_low':         fc['forecast_low'],
        'fc_high':        fc['forecast_high'],
        'ach_rate':       fc['achievement_rate'],
        'on_track_formula': fc['on_track'],
        'similar_count':  similar['count'],
        'similar_dates':  similar['dates'],
        'similar_p25':    similar['p25'],
        'similar_p75':    similar['p75'],
        'similar_median': similar['median'],
        'pattern_info':   pattern_info,
        'pattern_conf':   pattern['confidence'],
        'pattern_n':      pattern['sample_count'],
        'daily_fc_formula': daily_fc_formula,
    }

    gemini = call_gemini_forecast(ctx)
    if gemini:
        # [v1.2] Gemini daily_forecast는 무시, 수식값 고정
        # Gemini는 월마감 범위(low/high) + comment + on_track만 활용
        return {
            'daily_forecast':        daily_fc_formula,   # 수식값 고정
            'monthly_forecast_low':  gemini.get('monthly_forecast_low',  fc['forecast_low']),
            'monthly_forecast_high': gemini.get('monthly_forecast_high', fc['forecast_high']),
            'on_track':              gemini.get('on_track', fc['on_track']),
            'comment':               gemini.get('comment', ''),
            'source':                'gemini_monthly',
            'ctx':                   ctx,
        }

    return {
        'daily_forecast':        daily_fc_formula,
        'monthly_forecast_low':  fc['forecast_low'],
        'monthly_forecast_high': fc['forecast_high'],
        'on_track':              fc['on_track'],
        'comment':               '',
        'source':                'fallback',
        'ctx':                   ctx,
    }


def build_skt_section(date_str: str, current_skt: int, current_hour: int,
                      hourly_docs: list, is_on_the_hour: bool = False,
                      current_minute: int = 0,
                      db_forecast_s: int = None) -> str:
    """시간별 메시지 SKT OUT 섹션
    [v1.2] db_forecast_s: ktoa_hourly DB의 forecast_mno_out.S
           있으면 Gemini daily_forecast 대신 이 값을 예상으로 표시 → 상단/본문 완전 일치
    """
    def _fmt_man(v):
        man = v / 10000
        s = f'{man:.2f}'.rstrip('0').rstrip('.')
        return f'{int(man)}만' if man == int(man) else f'{s}만'

    try:
        fc  = get_forecast(date_str, current_skt, current_hour, hourly_docs, current_minute)
        ctx = fc['ctx']
        icon = '✅' if fc['on_track'] else '⚠️'
        need_avg = ctx.get('remaining_avg', ctx['need_avg'])
        # [v1.2] DB 저장값 우선 → 없으면 Gemini/수식 결과
        display_forecast = db_forecast_s if (db_forecast_s and db_forecast_s > 0) \
                           else fc['daily_forecast']
        lines = [
            '◎ SKT OUT',
            f'잔여 일평균 목표: {need_avg:,}(월목표 {_fmt_man(ctx["monthly_goal"])})',
            f'오늘 목표 : {ctx["today_goal"]:,} (×{ctx["bw"]}, 영업일수)',
            f'당일 소진률 : {current_skt:,} ({ctx["pct_of_goal"]}%) → 예상 {display_forecast:,}',
        ]
        if is_on_the_hour:
            lines.append(f'월마감 예측 : {fc["monthly_forecast_low"]:,} ~ {fc["monthly_forecast_high"]:,}  {icon}')
            if fc.get('comment'):
                lines.append(f'💬 {fc["comment"]}')
        if ctx['pattern_conf'] == 'LOW':
            lines.append(f'※ 시간대 패턴 학습 중 (n={ctx["pattern_n"]})')
        return '\n'.join(lines)
    except Exception as e:
        log.error(f"build_skt_section 실패: {e}")
        return f'◎ SKT OUT\n당일 : {current_skt:,}'


def build_skt_closing(date_str: str, today_actual_skt: int,
                      hourly_docs: list) -> str:
    """일마감 메시지 SKT OUT 섹션"""
    def _fmt_man(v):
        man = v / 10000
        s = f'{man:.2f}'.rstrip('0').rstrip('.')
        return f'{int(man)}만' if man == int(man) else f'{s}만'

    try:
        fc  = get_forecast(date_str, today_actual_skt, 19, hourly_docs)
        ctx = fc['ctx']
        icon = '✅' if fc['on_track'] else '⚠️'
        vs_avg = round(today_actual_skt / ctx['daily_avg'] * 100) if ctx['daily_avg'] > 0 else 0
        lines = [
            '◎ SKT OUT',
            f'목표 : {ctx["monthly_goal"]:,}',
            f'현누적 : {ctx["cum_skt"]:,} (달성률 {ctx["ach_rate"]}%)',
            f'오늘 실적 : {today_actual_skt:,} (일평균 대비 {vs_avg}%)',
            f'잔여 일평균 목표: {ctx["need_avg"]:,} (잔여 {ctx["remaining_bw"]}일)',
            f'월마감 예측 : {fc["monthly_forecast_low"]:,} ~ {fc["monthly_forecast_high"]:,}  {icon}',
        ]
        if fc.get('comment'):
            lines.append(f'💬 {fc["comment"]}')
        return '\n'.join(lines)
    except Exception as e:
        log.error(f"build_skt_closing 실패: {e}")
        return f'◎ SKT OUT\n오늘 : {today_actual_skt:,}'# rebuilt Thu May  7 03:31:45 AM UTC 2026