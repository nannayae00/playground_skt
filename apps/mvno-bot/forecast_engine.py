# force-rebuild-2026-05-07
"""
forecast_engine.py  v1.3
작성일: 2026-04-17

[수정 이력]
v3.0 | 2026-10-06 | 월마감 mid를 전월 동일시점 잔여속도법으로 교체 (Claude)
  - _get_prev_month_analog_pred(): 직전 2개월 잔여 bw당 속도(pure)와 이번달 수준
    반영분(scaled)을 50:50 → × 이번달 잔여bw. 기존 mid는 계산 불가 시 폴백
  - 백테스트 330개 시점 평균오차 6.07% → 4.77%
v2.8 | 2026-06-18 | Firestore 경로 tout_goal → target_goal 변경 (Claude)
  - get_tout_goal(): ktoa_config/tout_goal → ktoa_config/target_goal
  - 환경변수 폴백: KTOA_TOUT_GOAL → KTOA_TARGET_GOAL
v2.7 | 2026-06-11 | avg 4종(avg5/avg10 × rbw_ai/rbw_man) → sorted → low/mid/high
  - _calc_weighted_avg(history, max_w=5.0): max_w 파라미터 추가 (가중치 0.5~max_w)
  - _get_rolling_avg(date_str, top_n=10, max_w=5.0): max_w 전달
  - avg5  = _get_rolling_avg(date_str, 10, max_w=5.0)  (기존 방식)
  - avg10 = _get_rolling_avg(date_str, 10, max_w=10.0) (최근일 가중 강화, 추세 빠른 반영)
  - p1=avg5×rbw_ai, p2=avg5×rbw_man, p3=avg10×rbw_ai, p4=avg10×rbw_man
  - sorted([p1,p2,p3,p4]) → fc_low=min, fc_high=max, fc_mid=중간 2개 평균
v2.6 | 2026-06-10 | rbw B방식 통일 + Low/Mid/High 정렬 보장
  - rbw 계산: total - elapsed (last_biz 제거) → 월말 수렴 개선
  - rbw_low  = total_ai  - elapsed (B방식, 보수적)
  - rbw_mid  = (rbw_low + rbw_high) / 2 (중간값)
  - rbw_high = total_man - elapsed_man (manual, 낙관적)
  - fc_low/mid/high = sorted([p1, p2, p3]) → 항상 정렬 보장
v2.5 | 2026-06-02 | fc_low avg_simple → avg_recent 통일
  - fc_w2(low) 계산을 avg_simple(단순평균) → avg_recent(rolling avg)로 변경
  - 월초 elapsed_bw 극소 시 avg_simple 과대계산 문제 해결
  - low/mid/high 모두 동일 avg 사용, bw 시나리오만 다르게 → 정렬 자연 보장
v2.4 | 2026-06-01 | D-10 rolling window avg — 월 경계 자연스럽게 넘어감
  - _get_rolling_avg(): D-1부터 최근 10 영업일 역순 조회
    · 월 경계 무관하게 항상 최근 10일 사용
    · 6/1: 5/30~5/16 전월 10일, 6/5: 6/4~6/1(4일)+5월(6일) 혼합
    · elapsed_bw 분기 완전 제거 (당월/전월 구분 불필요)
  - _get_prev_month_avg(), 월초 분기 로직 제거
  - avg_recent = _get_rolling_avg() 단일 경로로 통일
v2.3 | 2026-06-01 | 월초 전월 실적 기반 avg 초기화 + 이중가중 avg 전면 적용
  - _calc_weighted_avg(): 신규 — 이중가중 avg 계산 (bw정규화 × 일자감쇠 5→0.5)
  - _get_prev_month_avg(): 전월 마지막 10 영업일 이중가중 avg (전항목)
v2.2 | 2026-05-15 | 잔여bw 계산 엑셀과 동일하게 수정
  - 기존: range(day, 32) → 오늘부터 합산
  - 변경: total_bw - elapsed_bw(전일까지) 방식
  - 엑셀: rem_ai = total_bw_ai - cum_bw_ai(1~day-1) → 오늘 포함
v2.1 | 2026-05-15 | 경과bw를 bw_ai_prev 고정으로 수정 (엑셀과 동일)
  - 기존: bw_ai_w3>w2>w1>ai_prev>manual 우선순위 → w1이 경과bw 왜곡
  - 변경: 경과bw = bw_ai_prev (엑셀 _build_s4_forecast와 동일)
  - 잔여bw: fc_low=bw_ai_w2, fc_mid=bw_ai_prev, fc_high=bw_manual (엑셀 동일)
  - avg_skt = cum_skt / cum_bw_ai_prev (엑셀과 동일)
v2.0 | 2026-05-14 | predict_monthly 로직 최종 정리
  - cum_skt = cum_skt_db 전일 확정 누적만 (fc_daily 미포함)
  - 경과bw: bw_ai_w3>w2>w1>ai_prev>manual 우선순위 적용
  - 잔여bw: 오늘(day) 포함 (day+1 → day 시작)
  - avg_skt 속도보정: 17시 이후에만 적용
  - ktoa_scraper._trio()와 경과bw 계산 방식 통일
v1.9 | 2026-05-14 | predict_monthly 엑셀과 동일한 로직으로 수정
  - cum_skt = cum_skt_db (전일 확정 누적만)
  - avg_skt = avg_recent (전일까지 일평균)
  - 오늘 추이 보정: 17시 이후에만 적용 (오전엔 실적 미미 → 왜곡)
  - fc = cum_skt + avg_skt × rbw (엑셀 _fc_trio와 동일)
  - 기존: cum_skt = cum_skt_db + fc_daily → 오늘 예측값을 누적에 더함 (잘못됨)
  - 변경: cum_skt = cum_skt_db (전일까지 확정값만)
  - 오늘 추이 반영: fc_daily로 avg_skt 보정 (빠르면 상향, 느리면 하향 ±20%)
  - fc 계산: cum_skt + avg_skt_adj × rbw (엑셀 _fc_trio와 동일)
v1.8 | 2026-05-14 | fc_daily 계산 방식 수정
  - 기존: ktoa_hourly의 forecast_mno_out.S (시간별→19시 예측) 사용
    → 오전 이른 시간엔 실적이 적어 저평가 (11시 120건 → 658 예측)
  - 변경: avg_recent × bw_today 우선 사용 (일평균 기반 오늘 예측)
    → 정시 예측값은 현재 진행률 보정에만 활용
    → 속도가 빠르면 상향, 느리면 하향 (±30% 제한)
    → 누락 시에도 avg_recent × bw로 안정적 예측
v1.7 | 2026-05-14 | 정시 예측값 누락 시 폴백 강화
  - fc_daily 계산: 정시 예측값 없을 때 최근 정시 예측값 탐색 (최대 2시간 전까지)
  - 최근 정시 예측값도 없으면 avg_recent × bw 사용 (일평균 기반, 단순 비례보다 정확)
  - 누락 1회로 인한 월마감 예측 왜곡 방지
v1.6 | 2026-05-07 | predict_gemini 의존성 제거 — get_elapsed_stats 인라인 구현
  - predict_monthly(): get_elapsed_stats() 호출 제거
  - ktoa_daily 직접 조회로 cum_skt_db, avg_simple, avg_recent 계산
  - predict_gemini 구버전 배포 문제로 인한 월마감 예측 오류 근본 해결
  - predict_monthly(): cum_skt = 전일누적 + fc_daily(정시 예측값 우선)
  - avg 분리: avg_simple(전체 평균) / avg_recent(최근 5일 2배 가중)
    · fc_low  = avg_simple × rbw_w2  (보수적)
    · fc_mid  = avg_recent × rbw_ai  (트렌드 반영 기준)
    · fc_high = avg_recent × rbw_man (낙관적)
    · 4월 검증: 월중반 오차 25~30% 감소 확인
  - predict_gemini.get_elapsed_stats(): mno_out.S 없는 날 elapsed_bw 제외
    · daily_avg_skt_recent 필드 추가 (최근 5일 2배 가중 평균)
v1.4 | 2026-04-30 | 월마감 예측 cum_skt 오늘 실적 누락 버그 수정 + 말일 0~0 버그 수정
  - predict_monthly(): cum_skt = 전일누적(DB) + today_skt(실시간) 반영
    · 기존: ktoa_daily는 20시 마감 후 저장 → 당일 실적 누락된 채 계산
    · 수정: cum_skt_db + today_skt로 실시간 누적 반영
    · avg_skt도 오늘 bw 포함 경과bw로 재계산
  - predict_monthly(): rbw=0(말일, 잔여 영업일 없음) 시 0~0 버그 수정
    · fc = (cum_skt - today_skt) + fc_daily (_base 폴백)
v1.3 | 2026-04-18 | 10분단위 속도보정 로직 완전 재설계
  - 보정 기준을 time_linear → 직전 정시 예측값으로 변경
    · speed_ratio = 실제증가속도 / 예상증가속도
    · adj_s = prev_fc_s × speed_ratio (정시 예측값 기준 상하향)
    · 속도 동일 → 정시 예측값 유지, 빠름 → 상향, 느림 → 하향
    · 제약: 하한=현재실적값, 상한=직전정시예측×1.5
  - expected_rate 계산 수정: 분모를 정시→19시 전체구간으로 고정
    · 기존: remain_min + elapsed_min (매 10분마다 달라짐)
    · 수정: 600 - (hour-10)×60 (정시 기준 고정)
  - 각 항목 보정을 time_linear 기반 → 직전 정시 예측값 기반으로 변경
    · est_mno 보정: prev_fc × adj_ratio
    · est_mi, est_mo도 동일하게 정시 예측값 기준 적용

v1.2 | 2026-04-18 | predict_monthly current_hour 파라미터 추가
  - fc_daily 계산을 19시 고정 → 실제 현재 시각 기반으로 수정
    · 기존: elapsed_h = max(1, 19-10) 고정
    · 수정: elapsed_h = max(1, current_hour-10)
  - ktoa_telegram에서 _ref_hour 전달

v1.1 | 2026-04-18 | predict_monthly bw 3시나리오 기반 월마감 범위 개선
  - fc_low/mid/high를 ±%밴드 → bw 3시나리오 실제 차이로 변경
    · fc_low: bw_ai_w2 잔여합 (보수적)
    · fc_mid: bw_ai_prev 잔여합 (기준)
    · fc_high: bw_manual 잔여합 (낙관적)
  - remaining_avg/today_goal을 Gemini 블록 밖으로 이동 (예외 안전)
  - forecast_net DB 저장 추가 (ktoa_hourly)

v1.0 | 2026-04-17 | 최초 작성 — 모든 예측 로직 일원화
  - predict_hourly(): 시간별 예측 (패턴보간 → past_hourly → time_linear)
  - predict_monthly(): 월마감 예측 (bw 3시나리오 기반 Low/Mid/High)
  - get_tout_goal(): 월 목표 조회 (Firestore → 환경변수 폴백)

[설계 원칙]
  예측 계산은 이 파일에서만 수행
  다른 파일(ktoa_scraper, ktoa_telegram, forecast_excel)은
  이 파일의 함수를 호출하거나 DB 저장값을 읽어서 사용

[데이터 흐름]
  [시간별]
  ktoa_scraper → forecast_engine.predict_hourly()
    → ktoa_hourly/{doc_id} 저장
    → dict 반환 → send_ktoa_message(forecast=...)
    → build_message()에서 forecast 직접 사용

  [월마감]
  ktoa_scraper(20시 마감) → forecast_engine.predict_monthly()
    → ktoa_daily/{date_str} 저장 (fc_low, fc_mid, fc_high)
    → dict 반환

  [엑셀 S4]
  forecast_excel → ktoa_daily.fc_* 읽기 (저장값 우선)
                → 없으면 predict_monthly() 소급 계산

[예측 우선순위 — 시간별]
  1순위: 패턴 기반 + 선형 보간 (get_hourly_pattern, 신뢰도 HIGH/MED)
  2순위: 과거 동요일 동시간대 진행률 평균 (최근 8주)
  3순위: 단순 시간 비례 외삽 (time_linear, 폴백)
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# [추가 20260930] 완료율곡선 계산용 Firestore 읽기 캐시 (프로세스 생존 기간 내 유지).
# 과거 확정일(D-7, D-14, ...) 데이터는 한 번 저장되면 절대 안 바뀌므로 무기한
# 캐싱해도 안전함. 캐싱 전엔 메시지 하나에 항목 8개(S/K/L/SM/KM/LM×2) × 시간대별
# 완료율 계산이 전부 독립적으로 Firestore를 훑어서, 같은 날짜를 여러 번 반복
# 조회하느라 메시지 하나 만드는 데 수십 초~수 분이 걸리는 성능 문제가 있었음
# (엑셀 시트에 9시간×8항목까지 적용했을 때는 20분 넘게 걸려 사실상 타임아웃).
# 날짜 단위로 ktoa_daily 문서/ktoa_hourly 문서목록을 캐싱해서, 같은 날짜를
# 필요로 하는 다른 hour·group·key 조회끼리 재사용하도록 함.
_daily_doc_cache: dict = {}
_hourly_docs_cache: dict = {}


def _cached_daily_dict(db, ds: str) -> Optional[dict]:
    if ds not in _daily_doc_cache:
        doc = db.collection('ktoa_daily').document(ds).get()
        _daily_doc_cache[ds] = doc.to_dict() if doc.exists else None
    return _daily_doc_cache[ds]


def _cached_hourly_docs(db, ds: str) -> list:
    if ds not in _hourly_docs_cache:
        _hourly_docs_cache[ds] = list(db.collection('ktoa_hourly').where('date', '==', ds).stream())
    return _hourly_docs_cache[ds]

# [v1.9] 과거배수법→avg법 전환 진행률 임계값 (w_hist = 1 - progress/THRESHOLD, 0~1 클램프)
# avg(실적추이)는 "월경계 rush"(월말+월초 며칠이 평상시보다 15~40% 높게 나오는 패턴,
# bw 정규화로도 완전히 안 걸러짐 - 실측 확인됨) 때문에 월 중반까지도 체계적으로
# 과대추정하는 것으로 백테스트에서 확인됨. 0.65/0.70/0.75/0.80/0.85/0.90/1.0 비교 결과
# 컷오프를 늦출수록(=과거배수법을 더 오래 신뢰할수록) 꾸준히 개선되다가, 아예 컷오프를
# 없앤(1.0 = 월 전체에 걸쳐 자연 감쇠, 100% 도달해야 완전히 0) 경우가 최적으로 확인됨
# (평균절대오차 9.00%→7.83%, 6~8월 3개월×4개 진행률 지점 기준).
HIST_BLEND_THRESHOLD = 1.0

# [v2.0] 진행률 구간별 잔차(편향) 보정 테이블
# HIST_BLEND_THRESHOLD=1.0까지 적용해도 진행률 10~40% 구간엔 여전히 +5~20%
# 과대추정이 "체계적으로" 남아있는 것을 6·7·8월 일별 백테스트(88개 지점)로 확인함
# (half_life/lookback을 바꿔도 이 편향은 거의 안 움직임 → 노이즈가 아니라 구조적 편향).
# 7·8월로 학습한 보정곡선을 6월(학습에 안 씀)에 적용해 평균절대오차 7.1%→3.1%로
# 개선되는 것을 아웃오브샘플로 검증 후, 6·7·8월 전체로 최종 테이블 재산출.
# 값 = 그 구간에서 fc_mid가 실제보다 평균적으로 초과한 비율 (보정 시 나눠서 상쇄)
BIAS_CORRECTION_TABLE = {
    0: 0.0261, 10: 0.2009, 20: 0.1299, 30: 0.0796, 40: 0.0505,
    50: 0.0071, 60: -0.0121, 70: -0.0085, 80: -0.0007, 90: -0.0007, 100: 0.0,
}


def _bias_correction(progress_ratio: float) -> float:
    """진행률(0~1)에 해당하는 보정치를 10%구간 선형보간으로 반환

    [수정 20261002] BIAS_CORRECTION_TABLE은 "진행률 10~40%" 구간에서만
    6·7·8월 88개 지점으로 검증된 건데, 코드는 0%부터(0→10% 구간 0.0261→0.2009
    선형보간) 적용하고 있었음 - 검증 범위 밖인 월초(진행률 5~8%, D-1 실적만
    아는 시점)에 과도한 보정(-10%+)이 걸려 실무자 지적("3.1만은 너무 낮다,
    추세가 느려보이지 않는다")으로 발견. 과거 12개월의 "day1 체크포인트"로
    역검증한 결과 10% 미만 구간은 보정을 끄는 쪽이 평균오차 16.40%→11.70%로
    오히려 더 정확함(9개월 중 7개월 개선). progress_ratio<0.10이면 0.0 반환.
    """
    if progress_ratio < 0.10:
        return 0.0
    pct = max(0.0, min(100.0, progress_ratio * 100))
    lo = int(pct // 10) * 10
    hi = min(lo + 10, 100)
    if lo not in BIAS_CORRECTION_TABLE or hi not in BIAS_CORRECTION_TABLE:
        return 0.0
    frac = (pct - lo) / 10 if hi > lo else 0.0
    return BIAS_CORRECTION_TABLE[lo] * (1 - frac) + BIAS_CORRECTION_TABLE[hi] * frac


# ══════════════════════════════════════════════════════════════════
# DB 헬퍼
# ══════════════════════════════════════════════════════════════════

def _get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault())
    return fs.Client(project='mvno-484509', database='mvno-data')


# ══════════════════════════════════════════════════════════════════
# 공통 유틸
# ══════════════════════════════════════════════════════════════════

def get_tout_goal(year: int, month: int) -> int:
    """월별 T-Out 목표 조회 (Firestore → 환경변수 폴백)"""
    ym = f'{year:04d}-{month:02d}'
    try:
        db = _get_db()
        doc = (db.collection('ktoa_config').document('target_goal')
               .collection('monthly').document(ym).get())
        if doc.exists:
            goal = doc.to_dict().get('goal', 0)
            if goal > 0:
                return int(goal)
    except Exception as e:
        log.warning(f"T-Out 목표 조회 실패: {e}")
    return int(os.environ.get('KTOA_TARGET_GOAL', '42000'))


def _calc_weighted_avg(history: list, max_w: float = 5.0) -> float:
    """
    이중가중 avg 계산
    - bw 정규화: unit = val / bw  (영업일 bw=1.0 기준 표준화)
    - 일자 감쇠: 최근일 max_w, 0.5 ~ max_w 사이 균등 step → n일째 0.5
    history: [(val, bw), ...] 최신순 정렬 (index 0 = 가장 최근)
    max_w: 최근일 가중치 상한 (기본 5.0, 추세 빠른 반영용 10.0 등)
    Returns 0.0 if 데이터 없음
    """
    if not history:
        return 0.0
    n = len(history)
    if n == 1:
        weights = [max_w]
    else:
        step = (max_w - 0.5) / (n - 1)
        weights = [max(0.5, max_w - step * i) for i in range(n)]
    w_num = w_den = 0.0
    for (val, bw), w in zip(history, weights):
        if bw > 0:
            w_num += (val / bw) * w
            w_den += w
    return round(w_num / w_den, 1) if w_den > 0 else 0.0


def _get_prev_month_avg(year: int, month: int, top_n: int = 10) -> dict:
    """
    전월 마지막 top_n 영업일의 이중가중 avg (전항목)
    반환: {'S': avg, 'SM_IN': avg, 'KM_IN': avg, 'LM_IN': avg,
           'SM_OUT': avg, 'KM_OUT': avg, 'LM_OUT': avg}
    월초 elapsed_bw < 3.0 시 avg 초기값으로 사용
    """
    from calendar import monthrange
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    last_day   = monthrange(prev_year, prev_month)[1]

    empty = {'S': 0.0, 'SM_IN': 0.0, 'KM_IN': 0.0, 'LM_IN': 0.0,
             'SM_OUT': 0.0, 'KM_OUT': 0.0, 'LM_OUT': 0.0}
    try:
        db = _get_db()
        hist = {k: [] for k in empty}

        for d in range(last_day, 0, -1):
            if all(len(v) >= top_n for v in hist.values()):
                break
            ds = f"{prev_year:04d}-{prev_month:02d}-{d:02d}"
            doc = db.collection('ktoa_daily').document(ds).get()
            if not doc.exists:
                continue
            data = doc.to_dict()
            bw = float(data.get('bw_ai_prev') or data.get('bw_manual') or 0)
            if bw <= 0:
                continue
            mi   = data.get('mvno_in',  {}) or {}
            mo   = data.get('mno_out',  {}) or {}
            mout = data.get('mvno_out', {}) or {}
            vals = {
                'S':      mo.get('S'),
                'SM_IN':  mi.get('SM'),
                'KM_IN':  mi.get('KM'),
                'LM_IN':  mi.get('LM'),
                'SM_OUT': mout.get('SM'),
                'KM_OUT': mout.get('KM'),
                'LM_OUT': mout.get('LM'),
            }
            if not vals['S']:  # T-Out 없으면 유효 영업일 아님
                continue
            for k, v in vals.items():
                if v and len(hist[k]) < top_n:
                    hist[k].append((int(v), bw))

        result = {k: _calc_weighted_avg(v) for k, v in hist.items()}
        log.info(f"[forecast_engine] 전월({prev_year}-{prev_month:02d}) avg: "
                 f"S={result['S']:,.1f} SM_IN={result['SM_IN']:,.1f}")
        return result

    except Exception as e:
        log.warning(f"전월 avg 조회 실패: {e}")
        return empty


def _get_rolling_avg(date_str: str, top_n: int = 10, max_w: float = 5.0) -> float:
    """
    D-1부터 최근 top_n 영업일의 이중가중 T-Out avg
    월 경계 무관하게 자연스럽게 전월 데이터 포함
    max_w: 최근일 가중치 상한 (5.0=기존, 10.0=추세 빠른 반영)
    Returns 0.0 if 데이터 없음
    """
    from datetime import timedelta
    d = datetime.strptime(date_str, '%Y-%m-%d')
    history = []  # [(skt, bw), ...] 최신순

    try:
        db = _get_db()
        cur = d - timedelta(days=1)  # D-1부터 시작
        while len(history) < top_n:
            ds = cur.strftime('%Y-%m-%d')
            doc = db.collection('ktoa_daily').document(ds).get()
            if doc.exists:
                data = doc.to_dict()
                skt = data.get('mno_out', {}).get('S')
                bw  = float(data.get('bw_ai_prev') or data.get('bw_manual') or 0)
                if skt and bw > 0:
                    history.append((int(skt), bw))
            cur -= timedelta(days=1)
            # 너무 오래 전 데이터 탐색 방지 (최대 60일)
            if (d - cur).days > 60:
                break

        avg = _calc_weighted_avg(history, max_w=max_w)
        log.info(f"[forecast_engine] rolling avg({date_str}, n={len(history)}, max_w={max_w}): {avg:,.1f}")
        return avg

    except Exception as e:
        log.warning(f"rolling avg 조회 실패: {e}")
        return 0.0


def _get_hour_completion_ratio(date_str: str, hour: int, top_n: int = 40) -> float:
    """
    [추가 20260928] D-1부터 최근 top_n 영업일 중, 그 시각(hour)까지의 누적 SKT OUT이
    그날 최종 마감치 대비 차지한 비율(진행률)의 대표값.

    기존 fc_daily_raw = today_skt * 10 / elapsed_h는 "시간당 페이스가 하루종일
    균일하다"고 가정했는데, 실제로는 오전이 느리고 오후로 갈수록 빨라지는 패턴이
    뚜렷함(예: 11시=10.5%, 15시=49.9%, 19시=92.7% - 균일 가정이면 11시=10%,
    19시=90%로 거의 맞지만 중간 구간 왜곡 있음). 균일 가정 대신 이 실측 진행률로
    today_skt를 나누는 방식이 백테스트(60일, 트레일링 윈도우, 미래데이터 미사용)에서
    전 시간대(11~19시)에 걸쳐 더 정확했음(MAE 77.1→60.1, 특히 17~19시는 2~3배 개선).

    [수정 20260930-1] 오전(11~14시) 오차가 여전히 6~10%대로 커서("11시 예측이
    19시 실적한테도 밀린다" 지적) 90일치 데이터로 후보 5개(top20평균/top20중앙값/
    top30가중평균/top40중앙값/가산모델) 재백테스트. 표본을 20→40일로 늘리고
    평균→중앙값으로 바꾼 게 전 시간대에서 가장 정확했음(11시 10.4%→9.9%,
    12시 7.8%→7.4%, 13시 7.0%→6.8%, 14시 6.4%→6.3%, 그 외 시간대도 동률이거나
    소폭 개선, 악화된 시간대 없음). 가산모델(오늘누적+과거잔여량평균)은 시도해봤으나
    15~22%로 훨씬 나빠서 채택 안 함 - 나눗셈 기반 비율방식이 맞는 방향이었음.
    표본이 많아질수록(top_n↑) 이상치(캠페인 push 등으로 유독 이른 시간 튄 날) 영향이
    평균보다 중앙값에서 훨씬 덜 반영되는 게 핵심 개선 포인트.

    [수정 20260930-2] 사장님 제안("요일별로 해보는건 어때") - 156일치로 "전체표본
    median40" vs "같은 요일만 median" vs "영업일수(bw) 유사일 median20" 3파전
    백테스트. 같은 요일만 쓰는 방식이 전 시간대에서 압도적으로 승리(11시 10.7%→9.8%,
    12시 8.3%→6.4%, 13시 7.8%→5.6%, 14시 7.0%→4.6%, 15시 5.5%→3.9%). 완료율 곡선의
    모양 자체가 bw(영업일수 가중치)보다 요일(근무 리듬/캠페인 요일 패턴)에 더 크게
    좌우된다는 뜻. 이제 7일 간격(=같은 요일)으로만 과거를 훑도록 변경 - 매일 훑고
    요일로 걸러내는 것보다 조회량도 훨씬 적음(1/7).

    표본 부족(5일 미만) 시 0.0 반환 - 호출측에서 기존 균일페이스 공식으로 폴백.
    """
    from datetime import timedelta
    import statistics
    d = datetime.strptime(date_str, '%Y-%m-%d')
    ratios = []

    try:
        db = _get_db()
        cur = d - timedelta(days=7)  # 지난주 같은 요일부터, 7일 간격으로만 조회
        checked = 0
        while len(ratios) < top_n and checked < top_n * 2:
            ds = cur.strftime('%Y-%m-%d')
            checked += 1
            cur -= timedelta(days=7)
            if (d - cur).days > 280:  # 최대 40주(약 9개월) 전까지만 탐색
                break

            daily_dict = _cached_daily_dict(db, ds)
            if not daily_dict:
                continue
            actual = daily_dict.get('mno_out', {}).get('S')
            if not actual or actual <= 0:
                continue

            hdocs = _cached_hourly_docs(db, ds)
            candidates = sorted(
                (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
                key=lambda h: h.id
            )
            if not candidates:
                continue
            cum = candidates[0].to_dict().get('mno_out', {}).get('S')
            if cum and cum > 0:
                ratios.append(cum / actual)

    except Exception as e:
        log.warning(f"[forecast_engine] 시간대별 진행률 조회 실패: {e}")
        return 0.0

    if len(ratios) < 5:
        return 0.0
    ratio = statistics.median(ratios)
    log.info(f"[forecast_engine] {hour}시 진행률({date_str}, n={len(ratios)}): {ratio*100:.1f}%")
    return ratio


def _get_hour_completion_ratio_field(date_str: str, hour: int, group: str, key: str,
                                      top_n: int = 15) -> float:
    """
    [추가 20260930] _get_hour_completion_ratio()의 일반화 버전 - SKT(mno_out.S) 전용
    로직을, MNO Out K/L·MVNO IN/OUT SM/KM/LM에도 그대로 쓸 수 있게 group/key를
    파라미터화(같은 요일 + 그 시각까지 완료율의 중앙값, top_n=40, 7일 간격 탐색).
    156일 백테스트로 8개 항목 전부 기존 패턴기반(predict_hourly) 대비 MAPE
    25~49% 감소 확인 후 전면 적용(MNO Out K 7.7%→5.8%, L 8.0%→5.7%, MVNO IN
    SM 10.7%→6.7%/KM 9.4%→5.9%/LM 12.0%→6.2%, MVNO OUT SM 10.3%→5.5%/
    KM 9.4%→5.6%/LM 10.6%→5.4%).

    [수정 20261001] top_n 40→15(가장 최근 같은요일 15회만 사용). 아래쪽 루프가
    이미 최신순으로 표본을 채우므로 top_n만 줄이면 됨. 윈도우 그리드서치
    (8/10/12/15/18/20/25/30/40) 결과 15가 거의 최적점(전체 95.35%, 초반
    11-14시 92.83%, 40 대비 전체 +0.19%p·초반 +0.36%p) - 표본이 늘수록
    오래된 계절/정책 변화가 희석되어 최근 추세 반영력이 떨어지는 반면,
    15 밑으로는 표본부족 영향이 커짐. 블렌딩(과거 평균 앵커에 수렴)과
    교차필드 컨센서스(다른 지표 페이스로 보정) 둘 다 백테스트에서 이
    방식보다 나빠서 기각, 이 윈도우축소만 적용.
    group: 'mno_out' | 'mvno_in' | 'mvno_out', key: 그 안의 필드명(S/K/L/SM/KM/LM)
    """
    from datetime import timedelta
    import statistics
    d = datetime.strptime(date_str, '%Y-%m-%d')
    ratios = []

    try:
        db = _get_db()
        cur = d - timedelta(days=7)
        checked = 0
        while len(ratios) < top_n and checked < top_n * 2:
            ds = cur.strftime('%Y-%m-%d')
            checked += 1
            cur -= timedelta(days=7)
            if (d - cur).days > 280:
                break

            daily_dict = _cached_daily_dict(db, ds)
            if not daily_dict:
                continue
            actual = daily_dict.get(group, {}).get(key)
            if not actual or actual <= 0:
                continue

            hdocs = _cached_hourly_docs(db, ds)
            candidates = sorted(
                (h for h in hdocs if h.id.startswith(f"{ds}_{hour:02d}")),
                key=lambda h: h.id
            )
            if not candidates:
                continue
            cum = candidates[0].to_dict().get(group, {}).get(key)
            if cum and cum > 0:
                ratios.append(cum / actual)

    except Exception as e:
        log.warning(f"[forecast_engine] {group}.{key} {hour}시 진행률 조회 실패: {e}")
        return 0.0

    if len(ratios) < 5:
        return 0.0
    return statistics.median(ratios)


def get_field_daily_forecast(date_str: str, hour: int, group: str, key: str, today_val: int) -> int:
    """group.key 항목의 오늘 일마감 예측치 (요일필터 완료율곡선, 표본 부족 시 균일페이스 폴백)."""
    if today_val <= 0:
        return 0
    ratio = _get_hour_completion_ratio_field(date_str, hour, group, key)
    if ratio > 0:
        return int(today_val / ratio)
    elapsed = max(1, hour - 10)
    return int(today_val * 10 / elapsed)


def _get_past_same_hour_rates(db, date_str: str, hour: int) -> list:
    """
    과거 같은 요일 + 같은 시간대의 MVNO IN 진행률(당시/마감) 조회
    → 패턴 없을 때 2순위 외삽에 사용 (최근 8주 동요일)
    """
    from bw_engine import is_zero_day

    d = datetime.strptime(date_str, '%Y-%m-%d')
    rates = []

    try:
        for weeks_back in range(1, 9):
            past_d   = d - timedelta(days=7 * weeks_back)
            past_str = past_d.strftime('%Y-%m-%d')

            if is_zero_day(past_str):
                continue

            # 같은 시간대 hourly 조회 (정시 → ±10분 탐색)
            hourly_doc = None
            for suffix in [f'{hour:02d}00', f'{hour:02d}10', f'{hour:02d}50']:
                doc = db.collection('ktoa_hourly').document(f"{past_str}_{suffix}").get()
                if doc.exists:
                    hourly_doc = doc
                    break

            if not hourly_doc:
                continue

            h_data    = hourly_doc.to_dict()
            h_mvno_in = h_data.get('mvno_in', {}).get('계', 0) or 0

            daily_doc = db.collection('ktoa_daily').document(past_str).get()
            if not daily_doc.exists:
                continue

            d_mvno_in = daily_doc.to_dict().get('mvno_in', {}).get('계', 0) or 0

            if h_mvno_in > 0 and d_mvno_in > 0:
                rate = h_mvno_in / d_mvno_in
                if 0.1 <= rate <= 1.0:
                    rates.append(rate)

    except Exception as e:
        log.warning(f"과거 동시간대 진행률 조회 실패: {e}")

    return rates


# ══════════════════════════════════════════════════════════════════
# 시간별 예측
# ══════════════════════════════════════════════════════════════════

def predict_hourly(date_str: str, hour: int, minute: int,
                   current_vals: dict, doc_id: str) -> dict:
    """
    시간별 예측값 계산 → ktoa_hourly DB 저장 → dict 반환

    Parameters
    ----------
    date_str     : 'YYYY-MM-DD'
    hour         : 현재 시 (reference_time 기준)
    minute       : 현재 분 (선형 보간용)
    current_vals : {
        'mvno_in':  {'SM':..,'KM':..,'LM':..,'계':..},
        'mno_out':  {'S':..,'K':..,'L':..,'계':..},
        'mvno_out': {'SM':..,'KM':..,'LM':..,'계':..},
    }
    doc_id       : ktoa_hourly 문서 ID (예: '2026-04-17_1801')

    Returns
    -------
    {
        'mvno_in':  예측값 dict,
        'mno_out':  예측값 dict,
        'mvno_out': 예측값 dict,
        'net':      순증감 예측 dict,
        'source':   'pattern' | 'past_hourly' | 'time_linear',
    }
    또는 {} (계산 실패 시)
    """
    from bw_engine import get_bw_final

    mi  = current_vals.get('mvno_in',  {})
    mno = current_vals.get('mno_out',  {})
    mo  = current_vals.get('mvno_out', {})

    est_mi  = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0}
    est_mno = {'S': 0,  'K': 0,  'L': 0,  '계': 0}
    est_mo  = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0}
    source  = 'none'

    try:
        # ★ 패턴 키용 bw: bw_manual 우선, 없으면 get_bw_final
        try:
            _db_bw = _get_db()
            _dd_bw = _db_bw.collection('ktoa_daily').document(date_str).get().to_dict() or {}
            _m = float(_dd_bw.get('bw_manual') or 0)
            bw = _m if _m > 0 else get_bw_final(date_str)
        except Exception:
            bw = get_bw_final(date_str)
        from predict_gemini import get_hourly_pattern
        pat = get_hourly_pattern(date_str, hour, bw, minute)

        if pat.get('available') and pat.get('rate_at_hour', 0) > 0:
            # ── 1순위: 패턴 기반 + 선형 보간
            rates   = pat.get('rates', {})
            r_skt   = rates.get('skt')    or pat['rate_at_hour']
            r_sm    = rates.get('sm')     or r_skt
            r_km    = rates.get('km')     or r_skt
            r_lm    = rates.get('lm')     or r_skt
            r_smout = rates.get('sm_out') or r_skt
            r_kmout = rates.get('km_out') or r_skt
            r_lmout = rates.get('lm_out') or r_skt

            def _d(v, r): return int(v / r) if r and r > 0 else 0

            est_mi  = {'SM': _d(mi['SM'], r_sm),
                       'KM': _d(mi['KM'], r_km),
                       'LM': _d(mi['LM'], r_lm), '계': 0}
            est_mi['계'] = sum(est_mi[k] for k in ['SM','KM','LM'])

            est_mno = {'S':  _d(mno['S'],  r_skt),
                       'K':  _d(mno['K'],  r_skt),
                       'L':  _d(mno['L'],  r_skt), '계': 0}
            est_mno['계'] = sum(est_mno[k] for k in ['S','K','L'])

            est_mo  = {'SM': _d(mo['SM'], r_smout),
                       'KM': _d(mo['KM'], r_kmout),
                       'LM': _d(mo['LM'], r_lmout), '계': 0}
            est_mo['계'] = sum(est_mo[k] for k in ['SM','KM','LM'])

            interp = pat.get('interpolated', False)
            source = f'pattern(n={pat["sample_count"]}{"_interp" if interp else ""})'

        else:
            # ── 2순위: 과거 동시간대 진행률 평균
            db = _get_db()
            past_rates = _get_past_same_hour_rates(db, date_str, hour)

            if past_rates:
                avg_rate = sum(past_rates) / len(past_rates)
                if avg_rate > 0:
                    def _s(v): return int(v / avg_rate)
                    est_mi  = {'SM': _s(mi['SM']), 'KM': _s(mi['KM']),
                               'LM': _s(mi['LM']), '계': 0}
                    est_mi['계'] = sum(est_mi[k] for k in ['SM','KM','LM'])
                    est_mno = {'S': _s(mno['S']), 'K': _s(mno['K']),
                               'L': _s(mno['L']), '계': 0}
                    est_mno['계'] = sum(est_mno[k] for k in ['S','K','L'])
                    est_mo  = {'SM': _s(mo['SM']), 'KM': _s(mo['KM']),
                               'LM': _s(mo['LM']), '계': 0}
                    est_mo['계'] = sum(est_mo[k] for k in ['SM','KM','LM'])
                    source = f'past_hourly(n={len(past_rates)})'

            if source == 'none':
                # ── 3순위: 단순 시간 비례 외삽 (time_linear)
                elapsed_h = max(1, hour - 10)
                scale = 10.0 / elapsed_h
                est_mi  = {k: int(mi[k]  * scale) for k in ['SM','KM','LM']}
                est_mno = {k: int(mno[k] * scale) for k in ['S','K','L']}
                est_mo  = {k: int(mo[k]  * scale) for k in ['SM','KM','LM']}
                est_mi['계']  = sum(est_mi[k]  for k in ['SM','KM','LM'])
                est_mno['계'] = sum(est_mno[k] for k in ['S','K','L'])
                est_mo['계']  = sum(est_mo[k]  for k in ['SM','KM','LM'])
                source = 'time_linear'

    except Exception as e:
        log.warning(f"predict_hourly 계산 실패: {e}")
        return {}

    if est_mi.get('계', 0) <= 0:
        return {}

    # ── 10분단위: 직전 정시 예측값 기준으로 속도 보정
    # 정시(minute=0)는 보정 없음, 10분단위만 적용
    if minute > 0:
        try:
            prev_hour_id = f"{date_str}_{hour:02d}00"
            db = _get_db()
            prev_doc = db.collection('ktoa_hourly').document(prev_hour_id).get()

            if prev_doc.exists:
                prev_data = prev_doc.to_dict()
                prev_fc   = prev_data.get('forecast_mno_out', {})
                prev_mno  = prev_data.get('mno_out', {})

                prev_fc_s = prev_fc.get('S', 0)
                prev_s    = prev_mno.get('S', 0)
                curr_s    = mno.get('S', 0)

                if prev_fc_s > 0 and prev_s > 0 and curr_s > prev_s:
                    elapsed_min  = minute
                    # 정시부터 19시까지 전체 잔여 분 (속도 기준)
                    total_remain = max(1, 600 - (hour - 10) * 60)

                    # 실제 증가 속도 (분당)
                    actual_rate   = (curr_s - prev_s) / elapsed_min
                    # 정시 예측 기준 예상 증가 속도 (정시→19시 전체 구간)
                    expected_rate = (prev_fc_s - prev_s) / total_remain

                    if expected_rate > 0:
                        speed_ratio = actual_rate / expected_rate

                        # 보정 기준 = 직전 정시 예측값 (time_linear 아님!)
                        # 속도 빠르면 정시 예측보다 상향, 느리면 하향, 같으면 유지
                        adj_s = int(prev_fc_s * speed_ratio)

                        # 제약:
                        # 하한: 현재 실적값 (이미 이 수치는 넘었으니)
                        # 상한: 직전 정시 예측값 × 1.5
                        adj_s = max(curr_s, min(int(prev_fc_s * 1.5), adj_s))

                        # 전 항목에 동일 비율 적용
                        adj_ratio = adj_s / prev_fc_s if prev_fc_s > 0 else 1.0

                        # 직전 정시 예측값 기준으로 각 항목 보정
                        prev_fc_mi  = prev_data.get('forecast_mvno_in',  {})
                        prev_fc_mo  = prev_data.get('forecast_mvno_out', {})

                        est_mno = {k: max(current_vals['mno_out'].get(k, 0),
                                         int(prev_fc.get(k, est_mno[k]) * adj_ratio))
                                   for k in ['S', 'K', 'L']}
                        est_mno['계'] = sum(est_mno[k] for k in ['S', 'K', 'L'])
                        est_mi  = {k: max(current_vals['mvno_in'].get(k, 0),
                                         int(prev_fc_mi.get(k, est_mi[k]) * adj_ratio))
                                   for k in ['SM', 'KM', 'LM']}
                        est_mi['계']  = sum(est_mi[k] for k in ['SM', 'KM', 'LM'])
                        est_mo  = {k: max(current_vals['mvno_out'].get(k, 0),
                                         int(prev_fc_mo.get(k, est_mo[k]) * adj_ratio))
                                   for k in ['SM', 'KM', 'LM']}
                        est_mo['계']  = sum(est_mo[k] for k in ['SM', 'KM', 'LM'])

                        source += f'_adj({adj_ratio:.2f})'
                        log.info(f"[forecast_engine] 속도보정: {hour}:{minute:02d} "
                                 f"실제{actual_rate:.2f}/예상{expected_rate:.2f} "
                                 f"→ 계수{adj_ratio:.2f} 예측S={adj_s:,}")

        except Exception as e:
            log.debug(f"속도 보정 실패 (무시): {e}")

    # [수정 20260930] DB(ktoa_hourly)에 저장되는 예측값도 화면에 보여주는 값과
    # 통일 - 기존 3단계 캐스케이드(패턴/과거동시간대/시간비례) 대신 요일필터+
    # 완료율곡선(get_field_daily_forecast) 방식 사용. 156일 백테스트로 MNO Out
    # K/L, MVNO IN/OUT SM/KM/LM 전부 정확도 개선 확인(MAPE 25~49% 감소).
    # DB 조회 비용 때문에 정시(minute==0)에만 적용 - 10분단위는 어차피
    # 메시지에 본문 예측 섹션이 안 뜨므로(has_est는 정시에만 True) 기존
    # 캐스케이드 결과를 그대로 둬도 무방함.
    est_mni, est_moall = {}, {}  # MNO 유입/전체이탈 (정시에만 계산)
    if minute == 0:
        try:
            _cur_mno = current_vals.get('mno_out', {}) or {}
            _cur_mi  = current_vals.get('mvno_in', {}) or {}
            _cur_mo  = current_vals.get('mvno_out', {}) or {}
            for k in ['S', 'K', 'L']:
                v = _cur_mno.get(k, 0) or 0
                if v > 0:
                    est_mno[k] = get_field_daily_forecast(date_str, hour, 'mno_out', k, v)
            est_mno['계'] = sum(est_mno[k] for k in ['S', 'K', 'L'])
            for k in ['SM', 'KM', 'LM']:
                vi = _cur_mi.get(k, 0) or 0
                vo = _cur_mo.get(k, 0) or 0
                if vi > 0:
                    est_mi[k] = get_field_daily_forecast(date_str, hour, 'mvno_in', k, vi)
                if vo > 0:
                    est_mo[k] = get_field_daily_forecast(date_str, hour, 'mvno_out', k, vo)
            est_mi['계'] = sum(est_mi[k] for k in ['SM', 'KM', 'LM'])
            est_mo['계'] = sum(est_mo[k] for k in ['SM', 'KM', 'LM'])
            source = 'completion_ratio_dow'

            # [추가 20261007] MNO 유입(mno_in)/MNO 전체이탈(mno_out_all) S/K/L 일마감 예측
            # (같은 방식). 최근 15영업일 검증 평균오차 - mno_in 12/15/18시 7.2/4.6/3.3%,
            # mno_out_all 5.3/4.1/3.1% (기존 mno_out 6.5/3.3/1.5%와 비슷한 수준).
            for _g, _dst in (('mno_in', est_mni), ('mno_out_all', est_moall)):
                _cur = current_vals.get(_g, {}) or {}
                for k in ['S', 'K', 'L']:
                    v = _cur.get(k, 0) or 0
                    if v > 0:
                        _dst[k] = get_field_daily_forecast(date_str, hour, _g, k, v)
                if all(k in _dst for k in ('S', 'K', 'L')):
                    _dst['계'] = sum(_dst[k] for k in ['S', 'K', 'L'])
        except Exception as e:
            log.warning(f"[forecast_engine] 완료율곡선 예측 실패, 기존 캐스케이드 유지: {e}")

    # 순증감 = MVNO IN - MVNO OUT
    est_net = {k: est_mi.get(k, 0) - est_mo.get(k, 0) for k in ['SM','KM','LM']}
    est_net['계'] = sum(est_net[k] for k in ['SM','KM','LM'])
    # MNO 순증 = MNO 유입 - MNO 전체이탈 (S/K/L/MNO계, net_change 키와 동일)
    if all(k in est_mni and k in est_moall for k in ('S', 'K', 'L')):
        for k in ('S', 'K', 'L'):
            est_net[k] = est_mni[k] - est_moall[k]
        est_net['MNO계'] = sum(est_net[k] for k in ('S', 'K', 'L'))

    result = {
        'mvno_in':  est_mi,
        'mno_out':  est_mno,
        'mvno_out': est_mo,
        'net':      est_net,
        'mno_in':      est_mni,
        'mno_out_all': est_moall,
        'source':   source,
    }

    # ktoa_hourly DB 저장 (S3 시간별 예측 시트 + 이력 보관)
    try:
        _get_db().collection('ktoa_hourly').document(doc_id).set({
            'forecast_mvno_in':  est_mi,
            'forecast_mno_out':  est_mno,
            'forecast_mvno_out': est_mo,
            'forecast_net':      est_net,
            'forecast_source':   source,
            'forecast_hour':     hour,
            'forecast_minute':   minute,
            **({'forecast_mno_in': est_mni} if est_mni else {}),
            **({'forecast_mno_out_all': est_moall} if est_moall else {}),
        }, merge=True)
        log.info(f"[forecast_engine] hourly 저장: {doc_id} ({source}, {hour}:{minute:02d})")
    except Exception as e:
        log.warning(f"[forecast_engine] hourly DB 저장 실패 (메시지는 계속): {e}")

    return result


# ══════════════════════════════════════════════════════════════════
# 과거 동일시점 배수법 (월초 예측 보강용)
# ══════════════════════════════════════════════════════════════════

_month_series_cache: dict = {}  # {(year, month): series} - 마감된(과거) 달만 캐싱, 당월은 매번 새로 조회

def _get_month_daily_series(year: int, month: int) -> list:
    """
    [v1.0] 해당 월의 (누적bw, 누적skt) 시계열 반환.
    - bw: bw_ai_prev 우선, 없으면 bw_manual (시기별로 필드명이 달라서 둘 다 폴백)
    - cum_mno_out.S 필드를 그대로 사용 (매월 0으로 리셋되는 당월 누적값, 실측 확인됨)

    [수정 20261005] 과거(마감된) 달은 프로세스 생존 기간 동안 캐싱 - 적응형 방식
    선택(_select_adaptive_method) 도입으로 predict_monthly() 1회 호출당 이 함수가
    최대 4번(현재+직전3달) x 24개월 lookback = 최대 96번 호출될 수 있어, 캐싱 없이는
    매번 Firestore range query를 반복해서 느려짐. 당월(오늘이 속한 달)은 데이터가
    계속 바뀌므로 캐싱 제외 - 매번 새로 조회.
    """
    now = datetime.now()
    is_current_month = (year == now.year and month == now.month)
    cache_key = (year, month)
    if not is_current_month and cache_key in _month_series_cache:
        return _month_series_cache[cache_key]

    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end   = f"{year:04d}-{month:02d}-{last_day:02d}"

    try:
        db = _get_db()
        docs = db.collection('ktoa_daily') \
            .where('date', '>=', start).where('date', '<=', end) \
            .order_by('date').stream()
    except Exception as e:
        log.warning(f"[hist_ratio] {year}-{month:02d} 조회 실패: {e}")
        return []

    series = []  # (누적bw, 누적skt)
    cum_bw = 0.0
    for doc in docs:
        d = doc.to_dict()
        bw = float(d.get('bw_ai_prev') or d.get('bw_manual') or 0)
        cum_bw += bw
        skt = (d.get('cum_mno_out') or {}).get('S')
        if skt is None:
            continue
        series.append((cum_bw, int(skt)))

    if not is_current_month:
        _month_series_cache[cache_key] = series
    return series


def _get_historical_month_ratio(date_str: str, progress_ratio: float,
                                lookback_months: int = 24,
                                half_life_months: float = 6.0) -> Optional[dict]:
    """
    [v1.6] "과거 동일시점 배수법" — 전체기간 + 최근 가중치 (가중중앙값)
    과거 lookback_months개월(기본 24개월 = 사실상 전체 히스토리)에서 이번 달과
    같은 월진행률(progress_ratio) 지점의 누적실적 대비 그 달 마감 실적의 배수를
    구해, 최근일수록 가중치를 높인 가중중앙값(weighted median)을 반환.
    - 가중치는 half_life_months 기준 지수감쇠: i개월 전 배수의 가중치 = 0.5^(i/half_life)
      → half_life=6이면 6개월 전은 가중치 절반, 12개월 전은 1/4, ...
    - 2025년 4~12월(유심사태로 실적 변동폭이 비정상적으로 컸던 구간)을 하드코딩으로
      제외하는 대신, "오래될수록 자동으로 덜 반영"되게 해서 데이터가 쌓일수록
      별도 유지보수 없이 자연스럽게 잊혀지도록 함.
    - [v1.6] 가중평균(mean) 대신 가중중앙값(median) 사용: 월진행률이 낮을수록
      배수 자체의 분산이 커서 mean은 이상치(변동 큰 달)에 쉽게 끌려가고, 심지어
      recency 감쇠를 세게 걸어도(half_life=3) mean은 거의 개선되지 않았음
      (백테스트 확인). median은 half_life 값에 덜 민감하면서 오차를 크게 줄임.
    → 월초처럼 이번달 실측 표본이 적을 때, avg×잔여bw 방식 대신/함께 사용해
      "과거에 이 페이스였던 달들이 결국 얼마로 마감됐는지"로 예측(mid)을 보강.
    ※ 밴드(low~high)는 predict_monthly()에서 폭 1000 고정으로 별도 처리하므로
      여기선 ratio_mid(가중중앙값)만 사용한다.
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    y, m = d.year, d.month

    weighted = []  # (ratio, weight)
    for i in range(1, lookback_months + 1):
        _m, _y = m - i, y
        while _m <= 0:
            _m += 12
            _y -= 1
        series = _get_month_daily_series(_y, _m)
        if len(series) < 5:
            continue
        total_bw, month_final = series[-1]
        if total_bw <= 0 or month_final <= 0:
            continue
        target_bw = progress_ratio * total_bw
        cum_at_point = min(series, key=lambda p: abs(p[0] - target_bw))[1]
        if cum_at_point <= 0:
            continue
        ratio = month_final / cum_at_point
        weight = 0.5 ** (i / half_life_months)
        weighted.append((ratio, weight))

    if len(weighted) < 2:
        return None

    # 가중중앙값: ratio 오름차순 정렬 후, 누적가중치가 전체의 절반을 넘는 지점
    weighted.sort(key=lambda x: x[0])
    total_w = sum(w for _, w in weighted)
    if total_w <= 0:
        return None
    cum_w = 0.0
    mid = weighted[-1][0]
    for ratio, w in weighted:
        cum_w += w
        if cum_w >= total_w / 2:
            mid = ratio
            break

    return {'ratio_mid': mid, 'n': len(weighted)}


def _get_historical_month_regression(date_str: str, progress_ratio: float,
                                      remaining_bw_this: Optional[float] = None,
                                      lookback_months: int = 24, half_life_months: float = 6.0) -> Optional[dict]:
    """
    [v2.0, 추가 20261003] "과거 동일시점 배수법"(가중중앙값, _get_historical_month_ratio)을
    대체하는 절편 없는 가중회귀(원점을 지나는 직선) 방식 - 실무자 지적("월마감 예측이
    오늘 페이스를 전혀 반영 못 함 + 숫자가 말이 안 됨")으로 재설계. 기존 가중중앙값
    방식은 "배수"(final/cum) 하나만 보고 판단해서, 소수 극단치(이상치 달)에 비율 자체가
    끌려가기 쉬웠음. final = b×cum (가중최소제곱, 절편=0) 형태로 24개월 전체 데이터에
    맞춰보니, 보정(_bias_correction) 적용한 기존 방식보다도 더 정확했음(18개 체크포인트
    백테스트: 평균오차 6.12% vs 기존 7.60%, 13/18 케이스에서 더 정확). 절편을 0으로
    고정한 이유: 절편 있는 일반 회귀(최소제곱)로 테스트해봤더니 소표본(n=24)에 과적합돼
    절편이 비정상적으로 커지면서(예: 18,839) 오히려 더 나빠짐(평균오차 10.46%) - "cum=0이면
    final도 0에 가까워야 한다"는 물리적 제약을 걸어주는 게 과적합을 막아줌.
    이 방식은 _bias_correction()과 함께 쓰지 않음(절편 없는 회귀 자체가 이미 전체
    데이터에 맞춰진 기울기라 추가 보정이 불필요 - 백테스트에서도 보정 얹은 조합은
    테스트 안 했고, 보정 없는 이 방식 자체로 이미 충분히 더 정확함을 확인).

    [수정 20261003] remaining_bw_this(이번달 "잔여" bw_ai_prev, 성장계수 반영분 포함)가
    주어지면 'bw_scale' 키를 추가 반환 - 이번달 잔여bw ÷ (비교대상 달들의 잔여bw
    가중평균). 실무자 지적("영업일수(bw)도 10월이 더 큰데 저렇게 적게 나오나,
    잔여 영업일수도 계산 들어가지?")로 추가. 호출부(predict_monthly)에서 이미
    "실현된" cum_skt_db 부분은 그대로 두고, 모델이 암묵적으로 추정한 "잔여분"에만
    이 배수를 곱하는 방식으로 사용해야 함 - 전체 예측치를 통째로 곱하면 이미 확정된
    실적까지 덩달아 스케일되는 결함이 있었음(최초 테스트에서 발견, 수정판으로 교체).
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    y, m = d.year, d.month

    num, den, n = 0.0, 0.0, 0
    w_sum, remaining_w_sum = 0.0, 0.0
    for i in range(1, lookback_months + 1):
        _m, _y = m - i, y
        while _m <= 0:
            _m += 12
            _y -= 1
        series = _get_month_daily_series(_y, _m)
        if len(series) < 5:
            continue
        total_bw, month_final = series[-1]
        if total_bw <= 0 or month_final <= 0:
            continue
        target_bw = progress_ratio * total_bw
        idx = min(range(len(series)), key=lambda k: abs(series[k][0] - target_bw))
        bw_at_point, cum_at_point = series[idx]
        if cum_at_point <= 0:
            continue
        weight = 0.5 ** (i / half_life_months)
        num += weight * cum_at_point * month_final
        den += weight * cum_at_point * cum_at_point
        n += 1
        w_sum += weight
        remaining_w_sum += weight * (total_bw - bw_at_point)

    if n < 5 or den <= 0:
        return None

    result = {'b': num / den, 'n': n}
    if remaining_bw_this is not None and w_sum > 0:
        avg_remaining_hist = remaining_w_sum / w_sum
        if avg_remaining_hist > 0:
            result['bw_scale'] = remaining_bw_this / avg_remaining_hist
    return result


_daily_bw_skt_cache: dict = {}  # {date_str: (bw, skt_daily) | None} - 과거 날짜만 캐싱

def _get_daily_bw_skt(date_str: str) -> Optional[tuple]:
    """[v1.0, 추가 20261005] 특정 날짜의 (bw, 당일skt증분) 단건 조회 - 월경계 무관.
    _get_recent_trend_pred()가 "최근 N영업일"을 월 경계 넘어서까지 모을 때 사용."""
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    if date_str != today_str and date_str in _daily_bw_skt_cache:
        return _daily_bw_skt_cache[date_str]
    try:
        doc = _get_db().collection('ktoa_daily').document(date_str).get()
    except Exception:
        return None
    if not doc.exists:
        result = None
    else:
        d = doc.to_dict()
        bw = d.get('bw_ai_prev') or d.get('bw_manual') or 0
        skt = (d.get('mno_out') or {}).get('S')
        result = None if skt is None else (float(bw), int(skt))
    if date_str != today_str:
        _daily_bw_skt_cache[date_str] = result
    return result


def _get_recent_trend_pred(date_str: str, cum_at_point: float, remaining_bw: float,
                            window_days: int = 7) -> Optional[float]:
    """[v1.0, 추가 20261005] "최근 N영업일 bw가중평균 일률 × 잔여영업일" 방식.
    date_str로부터 거슬러 올라가며 bw>0인 영업일을 window_days개 모음(월경계 넘어감,
    실무자 지적 "영업일 부족하면 전월말꺼 가져와야" 반영). 24개월 역사적회귀와는
    완전히 다른 정보(이번달 "바로 최근" 실제 속도)를 쓰는 방법으로, 백테스트 결과
    진행률 35~65%(월 중반) 구간에서만 역사적회귀보다 유의미하게 더 정확함이 확인됨
    (예: 50% 지점 평균오차 8.89%→1.49%). 월초/월말은 오히려 역사적회귀가 낫음
    (_select_adaptive_method가 매번 직전 실적으로 둘 중 승자를 가려서 선택)."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
    except Exception:
        return None
    collected_bw, collected_skt, found, tries = 0.0, 0, 0, 0
    cursor = d
    while found < window_days and tries < 60:
        ds = cursor.strftime('%Y-%m-%d')
        v = _get_daily_bw_skt(ds)
        if v is not None:
            bw, skt = v
            if bw > 0:
                collected_bw += bw
                collected_skt += skt
                found += 1
        cursor -= timedelta(days=1)
        tries += 1
    if collected_bw <= 0:
        return None
    rate = collected_skt / collected_bw
    return cum_at_point + rate * remaining_bw


def _backtest_methods_for_month(year: int, month: int, progress_ratio: float) -> Optional[tuple]:
    """[v1.0, 추가 20261005] 마감된 과거 (year, month)에서, 지정된 progress_ratio
    지점에 각각 origin_reg(24개월 회귀)와 recent_trend(최근7영업일) 방식을 적용했다면
    오차가 얼마였을지 계산. _select_adaptive_method()가 "직전 N개월 중 어느 방식이
    더 잘 맞았는지" 비교하는 데 사용 (워크포워드, 미래정보 누수 없음 - year/month
    시점에서 실제로 쓸 수 있었던 정보만 사용)."""
    series = _get_month_daily_series(year, month)
    if len(series) < 5:
        return None
    total_bw, month_final = series[-1]
    if total_bw <= 0 or month_final <= 0:
        return None
    target_bw = progress_ratio * total_bw
    idx = min(range(len(series)), key=lambda k: abs(series[k][0] - target_bw))
    day = idx + 1
    if day < 2 or day > 29:
        return None
    bw_at_point, cum_at_point = series[idx]
    if cum_at_point <= 0:
        return None
    date_str = f"{year:04d}-{month:02d}-{day:02d}"
    remaining_bw = total_bw - bw_at_point

    hist = _get_historical_month_regression(date_str, bw_at_point / total_bw)
    if hist is None:
        return None
    pred_origin = cum_at_point * hist['b']
    pred_trend = _get_recent_trend_pred(date_str, cum_at_point, remaining_bw)
    if pred_trend is None:
        return None
    err_origin = abs(pred_origin - month_final) / month_final
    err_trend = abs(pred_trend - month_final) / month_final
    return err_origin, err_trend


def _select_adaptive_method(date_str: str, progress_ratio: float, trailing_months: int = 2) -> str:
    """[v1.0, 추가 20261005] 직전 trailing_months개월의 "이 진행률 지점" 성과를 비교해서
    origin_reg(과거24개월회귀)와 recent_trend(최근7영업일추세) 중 승자를 고름.
    매번 재계산되므로 패턴이 바뀌면 자동으로 따라감(실무자 요청: "앞으로 계속 월이
    추가되면 다시계산해서 로직바뀌는지"). 직전 데이터가 부족하면 안전하게 'origin'
    반환(기존 동작 유지, 회귀 위험 없음).

    [수정 20261005] trailing_months 기본값 3→2로 변경. 6~9월 워크포워드 재검증
    결과 TM=3(평균 5.32%)은 6월 저진행률 지점에서 잘못된 선택(20% 지점 10.0%→28.6%
    악화)이 나와 origin단독(4.58%)보다도 못했음. TM=2(평균 4.49%)가 그 실수를
    피하면서 origin단독보다도 소폭 더 정확해 최종 채택. TM=1(5.72%)은 표본이 너무
    작아 더 불안정."""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    y, m = d.year, d.month
    origin_errs, trend_errs = [], []
    for i in range(1, trailing_months + 1):
        _m, _y = m - i, y
        while _m <= 0:
            _m += 12
            _y -= 1
        r = _backtest_methods_for_month(_y, _m, progress_ratio)
        if r is None:
            continue
        origin_errs.append(r[0])
        trend_errs.append(r[1])
    if len(origin_errs) < trailing_months or len(trend_errs) < trailing_months:
        return 'origin'
    avg_origin = sum(origin_errs) / len(origin_errs)
    avg_trend = sum(trend_errs) / len(trend_errs)
    return 'trend' if avg_trend < avg_origin else 'origin'


# ══════════════════════════════════════════════════════════════════
# 전월 동일시점 잔여속도법 (v3.0, 추가 20261006)
# ══════════════════════════════════════════════════════════════════
# 실무자 지적: "10월이 9월보다 영업일수가 길어서 3.7~3.8만은 나올 것 같은데 36.8천이
# 나온다. 9월 6일까지 누적/잔여영업일수/마감 vs 10월 6일까지로 계산해보라" -
# 9월 6일 이후 잔여 실적 25,409 ÷ 잔여bw 20.57 = 1,235/bw 를 10월 잔여bw 23.40에
# 적용하면 37.5천. 기존 방식(24개월 배수회귀 84% + 최근avg 16%, 진행률 16% 기준)은
# 오늘 실적을 배수회귀에서 빼고, 잔여영업일수가 늘어난 효과도 약하게만 반영해서 낮았음.
#
# 방식: 직전 2개월 각각에서 "같은 날짜까지 누적 → 그 달 마감"을 보고
#   - pure   = 그 달의 잔여 bw당 속도 (전월 흐름 그대로)
#   - scaled = pure × (이번달 경과 속도 ÷ 그 달 같은 시점 경과 속도) (이번달 수준 반영)
#   를 50:50으로 섞고(직전월 가중 2:1), 이번달 잔여bw를 곱해 누적에 더함.
#   이번달 수준이 전월과 크게 다르면 scaled 쪽이 그만큼 따라감.
# 경과 속도(수준 비교)는 bw가 아니라 달력가중(평일 1.0, 토요일·공휴일 0.66, bw=0인
# 날 0)으로 계산 - 10월처럼 bw_manual에 월초 몰림(1일 1.7, 2일 1.6)을 넣어둔 달은
# bw로 나누면 경과 속도가 낮게 잡혀 예측이 3.5만대로 떨어졌음(달마다 bw 입력
# 방식이 달라 비교가 안 됨). 잔여 구간은 실무자 bw 그대로 사용.
# 백테스트(2025-06~2026-09, 유심사태 3개월 제외 15개월, 매 영업일 330개 시점):
#   진행률 0-20/20-40/40-60/60-80/80-90% 평균오차
#   기존  12.0 / 9.2 / 5.2 / 2.0 / 1.1  → 전체 6.07% (편향 +3.4%)
#   이방식  9.4 / 6.7 / 3.6 / 2.3 / 1.5  → 전체 4.77%
ANALOG_REF_MONTHS = 2     # 참조할 직전 마감월 수 (1~3 비교 → 2가 가장 안정)
ANALOG_SCALED_W   = 0.5   # scaled 비중 (0/0.25/0.5/0.75/1 비교 → 0.5)
ANALOG_LIGHT_DAY_W = 0.66  # 토요일·공휴일 달력가중 (2025-08~ 토요일/같은주 평일 중앙값)

_month_days_cache: dict = {}  # {(year, month): [(date_str, bw, {group: {key: val}})]} - 과거 달만


def _get_month_days(year: int, month: int) -> list:
    """해당 월 ktoa_daily 일별 (date_str, bw, {'mno_out':{..},'mvno_in':{..},'mvno_out':{..}})
    목록. 과거 달은 캐싱."""
    now = datetime.now(KST)
    is_current_month = (year == now.year and month == now.month)
    key = (year, month)
    if not is_current_month and key in _month_days_cache:
        return _month_days_cache[key]
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    try:
        docs = _get_db().collection('ktoa_daily') \
            .where('date', '>=', f"{year:04d}-{month:02d}-01") \
            .where('date', '<=', f"{year:04d}-{month:02d}-{last_day:02d}") \
            .order_by('date').stream()
        days = []
        for doc in docs:
            d = doc.to_dict()
            vals = {g: (d.get(g) or {}) for g in ('mno_out', 'mvno_in', 'mvno_out',
                                                 'mno_in', 'mno_out_all')}
            # bw_ai_prev가 0.0으로 명시된 날(추석 등 휴무)은 그대로 0 - `or` 폴백으로
            # bw_manual(엑셀 0.4 등)을 집으면 실적 없는 날에 bw가 생겨 그 달 전체가
            # "데이터 결손"으로 빠짐(20261007, 9/25~26 사례). 필드가 없을 때만 manual.
            bw = float(d['bw_ai_prev'] if d.get('bw_ai_prev') is not None
                       else (d.get('bw_manual') or 0))
            days.append((d.get('date'), bw, vals))
    except Exception as e:
        log.warning(f"[analog] {year}-{month:02d} 조회 실패: {e}")
        return []
    if not is_current_month:
        _month_days_cache[key] = days
    return days


def _calendar_weight(date_str: str, bw: float) -> float:
    if bw <= 0:
        return 0.0
    import holidays as _hol
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    if d.weekday() == 5 or d in _hol.KR(years=d.year):
        return ANALOG_LIGHT_DAY_W
    return 1.0


def _get_prev_month_analog_pred(date_str: str, cum_this: float,
                                include_today: bool, group: str = 'mno_out',
                                key: str = 'S') -> Optional[dict]:
    """전월 동일시점 잔여속도법 월마감 예측 (위 설명 참고).
    cum_this: 이번달 경과 누적(오늘 포함 시 오늘 일마감 예측치까지 더한 값)
    include_today: cum_this에 오늘이 들어있는지 (False면 어제까지가 경과)
    group/key: 대상 항목 (mno_out·mno_in·mno_out_all S/K/L, mvno_in·mvno_out SM/KM/LM).
      [20261007] 전 항목 확장 - 백테스트(330개 시점)에서 12개 항목 모두 기존
      단순방식(최근10영업일 avg × 잔여bw)보다 정확 (예: mvno_in 계 5.4→3.6%,
      mno_out K 7.4→5.8%, mvno_out SM 6.5→5.1%). 순증은 IN예측-OUT예측으로 계산."""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    ref_day = d.day if include_today else d.day - 1
    if ref_day < 1 or cum_this <= 0:
        return None

    this_days = _get_month_days(d.year, d.month)
    elapsed_cw = sum(_calendar_weight(ds, bw) for ds, bw, _ in this_days
                     if int(ds[8:]) <= ref_day)
    remaining_bw = sum(bw for ds, bw, _ in this_days if int(ds[8:]) > ref_day)
    if elapsed_cw <= 0:
        return None
    this_rate = cum_this / elapsed_cw

    refs = []  # (경과 달력가중당 속도, 잔여 bw당 속도, 'YYYY-MM')
    y, m = d.year, d.month
    for _ in range(6):  # 데이터 결손 달은 건너뛰고 최대 6개월 전까지
        if len(refs) >= ANALOG_REF_MONTHS:
            break
        m -= 1
        if m <= 0:
            m += 12
            y -= 1
        days = _get_month_days(y, m)
        if not days or any(v[group].get(key) is None and bw > 0 for _, bw, v in days):
            continue
        el = [(ds, bw, v[group].get(key) or 0) for ds, bw, v in days if int(ds[8:]) <= ref_day]
        fu = [(ds, bw, v[group].get(key) or 0) for ds, bw, v in days if int(ds[8:]) > ref_day]
        cum = sum(s for *_, s in el)
        e_cw = sum(_calendar_weight(ds, bw) for ds, bw, _ in el)
        r_bw = sum(bw for _, bw, _ in fu)
        if cum <= 0 or e_cw <= 0 or r_bw <= 0:
            continue
        refs.append((cum / e_cw, sum(s for *_, s in fu) / r_bw, f"{y:04d}-{m:02d}"))
    if len(refs) < ANALOG_REF_MONTHS:
        return None

    ws = [0.5 ** i for i in range(len(refs))]
    pure = sum(w * r[1] for w, r in zip(ws, refs)) / sum(ws)
    scaled = sum(w * r[1] * this_rate / r[0] for w, r in zip(ws, refs)) / sum(ws)
    rate = (1 - ANALOG_SCALED_W) * pure + ANALOG_SCALED_W * scaled
    return {
        'pred': cum_this + rate * remaining_bw,
        'pred_pure': cum_this + pure * remaining_bw,
        'pred_scaled': cum_this + scaled * remaining_bw,
        'rate': rate, 'pure': pure, 'scaled': scaled,
        'remaining_bw': remaining_bw, 'refs': [r[2] for r in refs],
    }


# ══════════════════════════════════════════════════════════════════
# 월마감 예측
# ══════════════════════════════════════════════════════════════════

def predict_monthly(date_str: str, today_skt: int,
                    hourly_docs: list = None,
                    save_to_daily: bool = True,
                    current_hour: int = 19) -> dict:
    """
    [v1.1] 월마감 예측 — bw 3시나리오 기반 Low/Mid/High
    - fc_low  : bw_ai_w2 잔여합 (최신 주차 반영, 보수적)
    - fc_mid  : bw_ai_prev 잔여합 (현재 사용 기준)
    - fc_high : bw_manual 잔여합 (수동 입력, 낙관적)
    - ±% 밴드 완전 제거 → 실제 영업일수 차이로 범위 결정
    """
    from bw_engine import get_bw_final
    from calendar import monthrange
    from predict_gemini import (get_similar_days,
                                get_hourly_pattern, call_gemini_forecast)

    d = datetime.strptime(date_str, '%Y-%m-%d')
    year, month, day = d.year, d.month, d.day
    wd_name = ['월','화','수','목','금','토','일'][d.weekday()]

    goal = get_tout_goal(year, month)
    bw   = get_bw_final(date_str)

    # ── get_elapsed_stats 인라인 구현 (predict_gemini 구버전 의존성 제거)
    cum_skt_db = 0
    cum_mvno   = 0
    elapsed_bw = 0.0
    history    = []  # (skt, bw) 확정 실적 이력
    _today_confirmed = False  # 오늘(day)이 이미 일마감돼 위 루프에 포함됐는지

    try:
        _db2 = _get_db()
        for _d in range(1, day + 1):
            _ds = f"{year:04d}-{month:02d}-{_d:02d}"
            _doc = _db2.collection('ktoa_daily').document(_ds).get()
            if not _doc.exists:
                continue
            _dd = _doc.to_dict()
            # 경과bw: bw_ai_prev 고정 (엑셀과 동일, w1~w3 미사용)
            _bw = float(_dd.get('bw_ai_prev') or _dd.get('bw_manual') or 0)
            if not _bw or _bw <= 0:
                continue
            _skt = _dd.get('mno_out', {}).get('S', None)
            if _skt is None:
                continue  # 실적 미집계 → elapsed_bw 제외
            _mvno = _dd.get('mvno_in', {}).get('계', 0) or 0
            elapsed_bw += _bw
            cum_skt_db += int(_skt)
            cum_mvno   += int(_mvno)
            history.append((int(_skt), _bw))
            if _d == day:
                _today_confirmed = True  # 오늘이 이미 마감 확정됨(예: RECHECK 20:25 이후)
    except Exception as _e:
        pass

    # ── avg 계산: D-1부터 최근 10 영업일 rolling window 이중가중
    # 월 경계 무관하게 자연스럽게 전월 데이터 포함
    # ex) 6/1: 전월 10일, 6/5: 당월 4일 + 전월 6일
    avg_recent = _get_rolling_avg(date_str, top_n=10, max_w=5.0)   # avg5 (기존)
    avg_trend  = _get_rolling_avg(date_str, top_n=10, max_w=10.0)  # avg10 (최근일 가중 강화)
    avg_simple = round(cum_skt_db / elapsed_bw, 1) if elapsed_bw > 0 else avg_recent

    # ── 오늘 일마감 예측 (시간대별 진행률곡선 우선, 부족하면 균일페이스 폴백)
    # [수정 20260928] 기존엔 "ktoa_hourly의 정시(_HH00) 예측값 우선, 없으면 균일페이스
    # (today_skt*10/elapsed_h)"였는데, 확인해보니 스케줄러가 정각이 아니라
    # :01,:11,:21...에 돌아서 _HH00 문서가 실제로 한 번도 존재한 적이 없었음(14일
    # 599건 중 0건) - 즉 그 "정시 예측값 우선" 분기는 사실상 죽은 코드였고 항상
    # 균일페이스만 쓰이고 있었음. 마침 백테스트해보니 그 정시 예측값(AI/패턴 기반)
    # 자체도 균일페이스보다 부정확해서(MAE 119.3 vs 79.2) 그 lookup을 고칠 필요는
    # 없었음. 대신 "균일페이스" 가정 자체를 시간대별 실측 진행률곡선으로 교체한 게
    # 더 정확해서(MAE 77.1→60.1, 전 시간대 승 - _get_hour_completion_ratio 참고)
    # 이걸로 교체. 진행률 표본 부족 시에만 기존 균일페이스로 폴백.
    elapsed_h = max(1, current_hour - 10)
    fc_daily_raw = int(today_skt * 10 / elapsed_h) if today_skt > 0 else 0
    # [수정 20261003] 10시대(current_hour=10)에 완료율곡선이 극도로 불안정해서
    # 터무니없는 값을 낸 버그 발견(실측: 10/3 토 10:20, 오늘누적 36건인데
    # fc_daily=4,126 - 당일목표 716의 5.8배). 원인은 과거 토요일 10시 완료율
    # 자체가 중앙값 0.87%로 극히 작은데(27개 표본 전부 0.4~1.7%), 이렇게 작은
    # 분모로 나누면 오늘누적의 사소한 변동에도 결과가 폭발적으로 흔들림 -
    # 토요일만의 문제가 아니라 10시대 자체가 이 방식이 애초에 백테스트/검증된
    # 범위(11~19시) 밖. ktoa_telegram.py에 이미 "10시대는 미표시" 의도가 있었지만
    # (fc_daily<=0일 때만 적용되는 폴백 분기) 완료율곡선이 작지만 0보다 큰 값을
    # 반환하는 이번 케이스는 그 가드를 타지 않고 지나가서 놓쳤음. 10~19시 중
    # 11시부터만 완료율곡선을 쓰도록 제한 - 10시대엔 fc_daily=0을 반환해서
    # 기존 "10시대는 미표시" 폴백이 정상적으로 발동하게 함.
    _ratio = _get_hour_completion_ratio(date_str, current_hour) if (today_skt > 0 and current_hour >= 11) else 0.0
    fc_daily = int(today_skt / _ratio) if _ratio > 0 else (fc_daily_raw if current_hour >= 11 else 0)

    avg_skt = avg_recent  # 메시지/잔여 일평균 계산용 기준

    # ── bw 3시나리오별 잔여 영업일수 (ktoa_daily 필드 직접 합산)
    last_day = monthrange(year, month)[1]
    rbw_ai  = 0.0  # bw_ai_prev → Low (보수적)
    rbw_w2  = 0.0  # (ai+man)/2 → Mid (중간값)
    rbw_man = 0.0  # bw_manual  → High (낙관적)
    _total_ai = 0.0  # 이번달 bw_ai_prev 전체 합(성장계수 반영분 포함) - bw_scale 계산용
    _rbw_includes_today = False  # 정상 경로만 "오늘 미마감 시 오늘 포함" (아래 참고)

    try:
        db = _get_db()
        # 잔여bw = total - elapsed (B방식, last_biz 제거 → 월말 수렴)
        _total_ai = _total_w2 = _total_man = 0.0
        for d2 in range(1, last_day + 1):
            ds2  = f"{year:04d}-{month:02d}-{d2:02d}"
            data = (db.collection('ktoa_daily').document(ds2).get().to_dict() or {})
            _total_ai  += float(data.get('bw_ai_prev') or 0)
            _total_w2  += float(data.get('bw_ai_w2') or data.get('bw_ai_prev') or 0)
            _total_man += float(data.get('bw_manual') or data.get('bw_ai_prev') or 0)
        # B방식: last_biz 제거 → 월말 수렴 개선. elapsed_bw가 오늘 미마감 시 오늘을
        # 제외하므로(위 루프 참고), 이 rbw_*는 그 경우 "오늘 포함 잔여"가 됨.
        rbw_ai  = round(_total_ai  - elapsed_bw, 3)  # Low (보수적, bw_ai_prev)
        rbw_man = round(_total_man - elapsed_bw, 3)  # High (낙관적, bw_manual)
        rbw_w2  = round((rbw_ai + rbw_man) / 2, 3)  # Mid (중간값)
        _rbw_includes_today = not _today_confirmed
    except Exception as e:
        log.warning(f"bw 시나리오 조회 실패, 단일 폴백: {e}")
        from bw_engine import get_month_bw_map
        bw_map = get_month_bw_map(year, month)
        rbw_ai = rbw_w2 = rbw_man = round(sum(
            bw_map.get(f"{year:04d}-{month:02d}-{d2:02d}", 0.0)
            for d2 in range(day + 1, last_day + 1)), 3)  # 폴백은 항상 오늘 제외

    rbw = rbw_w2  # 기준값 (remaining_avg 계산용, mid 기준)

    # ── cum_skt: 오늘 실시간 반영 (사장님 요청 - "정시에 일마감 예측수치가 계산에
    # 반영돼야 함. 늘어날수도 있고 소폭 줄어들수도 있지")
    # [수정 20260928] 기존엔 "전일까지 확정 누적만"이라 오늘 하루 안에서는 몇 시에
    # 불러도(11시든 17시든) 입력값이 동일해 월마감 예측이 절대 안 바뀌었음(사장님
    # 지적: "11시 1579, 17시 1843인데 월마감 예측이 동일한데 맞는건가?"). 오늘이 아직
    # 마감 전(_today_confirmed=False)이면 cum_skt에 그 시각의 일마감 예측치(fc_daily)를
    # 그대로 더함 - avg_recent와 섞어서 완만하게 만들지 않음(한때 노이즈 우려로
    # 경과율 가중 블렌딩을 넣었었는데, "선형으로 부드럽게 늘어나는 건 의미 없고 정시
    # 예측치가 그대로 반영돼야 한다 - 늘어날 수도 소폭 줄어들 수도 있다"는 피드백으로
    # 되돌림). rbw_*가 오늘을 포함하고 있을 때만(_rbw_includes_today) 오늘 자신의
    # bw를 전액 빼서 avg×잔여 계산이 오늘을 또 평균으로 이중 추정하지 않도록 함(오늘 =
    # fc_daily로 직접 반영, 잔여 = 오늘 제외한 순수 미래일 평균 반영). 폴백 경로는
    # 애초에 오늘을 안 세므로 추가로 빼면 안 됨 - _rbw_includes_today로 구분.
    # 오늘이 이미 마감 확정됐다면(RECHECK 20:25 이후 등) 기존과 동일하게 cum_skt_db
    # 그대로 사용(오늘이 이미 elapsed 쪽에 반영돼 있어 추가 조정 불필요).
    if _today_confirmed:
        cum_skt = cum_skt_db
    else:
        cum_skt = cum_skt_db + fc_daily
        if _rbw_includes_today:
            rbw_ai  = round(max(0.0, rbw_ai  - bw), 3)
            rbw_man = round(max(0.0, rbw_man - bw), 3)
            rbw_w2  = round((rbw_ai + rbw_man) / 2, 3)
            rbw     = rbw_w2

    # ── 수식 기반 일평균 보정 (avg가 여전히 0인 극단적 케이스만)
    # rolling avg가 정상이면 여기 안 탐
    if avg_skt <= 0 or elapsed_bw <= 0:
        if avg_recent > 0:
            avg_skt = avg_recent
            log.info(f"[forecast_engine] avg 폴백: rolling avg={avg_recent:,.1f}")
        else:
            avg_skt = int(goal / (rbw + bw)) if (rbw + bw) > 0 else 0
            log.warning(f"[forecast_engine] avg 목표역산 폴백: {avg_skt:,}")

    # ── bw 시나리오별 월마감 예측
    # fc_low  = rolling avg × bw_w2  (보수적)
    # fc_mid  = rolling avg × bw_ai  (기준)
    # fc_high = rolling avg × bw_man (낙관적)
    # avg 통일: avg_simple 제거 → 월초 왜곡 방지
    _base  = cum_skt
    # avg 2종(avg5/avg10) × rbw 2종(rbw_ai/rbw_man) → 4값
    # avg5  = 기존 가중(0.5~5.0), avg10 = 추세 빠른 반영(0.5~10.0)
    # rbw_ai  = bw_ai_prev 기준 (보수적)
    # rbw_man = bw_manual  기준 (낙관적)
    _p1 = int(cum_skt + avg_recent * rbw_ai)  if rbw_ai  > 0 else _base  # avg5  × rbw_ai
    _p2 = int(cum_skt + avg_recent * rbw_man) if rbw_man > 0 else _base  # avg5  × rbw_man
    _p3 = int(cum_skt + avg_trend  * rbw_ai)  if rbw_ai  > 0 else _base  # avg10 × rbw_ai
    _p4 = int(cum_skt + avg_trend  * rbw_man) if rbw_man > 0 else _base  # avg10 × rbw_man

    # 정렬 → fc_low=최소, fc_high=최대, fc_mid=중간 2개 평균
    _sorted = sorted([_p1, _p2, _p3, _p4])
    fc_low, fc_high = _sorted[0], _sorted[3]
    fc_mid = int(round((_sorted[1] + _sorted[2]) / 2))
    fc_w2 = fc_low; fc_ai = fc_mid; fc_man = fc_high  # 하위 호환

    # ── [v1.9] 과거 동일시점 배수법 블렌딩 (HIST_BLEND_THRESHOLD 참고)
    # avg×잔여bw 방식은 "월경계 rush"를 못 걸러내서 월 중반까지도 체계적 과대추정.
    # 과거배수법이 거의 전 구간에서 더 정확해서, 컷오프 없이 월 전체에 걸쳐
    # 자연 감쇠(w_hist=1-progress)시키는 게 최적으로 확인됨.
    _total_bw_mid = elapsed_bw + rbw_w2
    progress_ratio = elapsed_bw / _total_bw_mid if _total_bw_mid > 0 else 0
    hist_ratio_used = False
    _remaining_bw_this = max(0.0, _total_ai - elapsed_bw)
    try:
        hist = _get_historical_month_regression(date_str, progress_ratio,
                                                  remaining_bw_this=_remaining_bw_this)
    except Exception as e:
        log.warning(f"[forecast_engine] 과거 회귀법 실패 (avg법 유지): {e}")
        hist = None

    # 과거배수법은 중간값(fc_mid) 보정에만 사용 — 밴드(low~high)는 아래에서
    # 별도로 "깔끔한 폭"으로 고정. (히스토리 배수 기반 밴드는 표본이 작아
    # 비현실적으로 넓어지는 문제가 있었고, 실무적으로도 폭 1000 넘는 범위는
    # 정확도보다 신뢰도를 깎아먹는다는 피드백 반영 — 적중률보다 "깔끔한 숫자" 우선)
    _avg_half = (fc_high - fc_low) / 2  # avg법 4변형 스프레드
    if hist and cum_skt_db > 0:
        w_hist = max(0.0, min(1.0, 1 - progress_ratio / HIST_BLEND_THRESHOLD))
        if w_hist > 0:
            # [추가 20261005] 적응형 방식 선택: 매번 직전 3개월의 "이 진행률 지점"
            # 실적을 돌아보고 origin_reg(과거24개월회귀) vs recent_trend(최근7영업일
            # 추세) 중 더 잘 맞았던 쪽을 고름. 워크포워드 백테스트(7~9월)로 검증:
            # 고정 origin_reg 단독 4.67% / 고정 50:50블렌드 6.74% 대비 적응형선택
            # 4.26%로 가장 정확 - 진행률 7~30%/90%는 origin이, 50~70%는 trend가
            # 일관되게 승자로 뽑힘(하드코딩 아니라 매달 재계산되므로 패턴이 바뀌면
            # 자동 추종). 직전 데이터 부족하면 _select_adaptive_method가 안전하게
            # 'origin' 반환(기존 동작 그대로).
            try:
                _method = _select_adaptive_method(date_str, progress_ratio)
            except Exception as e:
                log.warning(f"[forecast_engine] 적응형 방식 선택 실패 (origin 유지): {e}")
                _method = 'origin'

            hist_mid = None
            if _method == 'trend':
                hist_mid = _get_recent_trend_pred(date_str, cum_skt_db, _remaining_bw_this)

            if hist_mid is None:
                # origin_reg 경로 (적응형이 origin을 고르거나, trend 계산 실패 시 폴백)
                _method = 'origin'
                # [수정 20260929] ratio_mid는 progress_ratio(경과bw 기준, 오늘 미포함)
                # 시점의 "확정 누적 대비 월마감" 배수로 캘리브레이션됨. cum_skt(오늘
                # fc_daily 반영분 포함)를 곱하면 오늘 실시간반영 도입 후 진행률과
                # 누적치 기준이 어긋나 월초처럼 배수가 클 때(예: 17배) 오늘 추정치까지
                # 같이 뻥튀기되는 문제가 있었음(6~8월 백테스트로 확인, 예: 06-02
                # 34,168 실제 대비 58,133로 과다예측). cum_skt_db(확정 누적, progress_ratio와
                # 동일 기준)로 곱하도록 수정.
                hist_mid = cum_skt_db * hist['b']
                # [추가 20261003] bw_scale: 이미 "실현된" cum_skt_db는 그대로 두고,
                # 모델이 암묵적으로 추정한 "잔여분"(hist_mid - cum_skt_db)에만 이번달
                # 잔여영업일(bw) 성장계수를 곱함. 전체를 통째로 곱하면 실현분까지
                # 스케일되는 결함이 있어 잔여분에만 한정 (18개 체크포인트 백테스트로
                # 검증: 결함판 평균오차 6.87% → 이 수정판 6.64%, 무보정 6.12%).
                # trend 경로는 "최근 실제 속도"를 이미 쓰고 있어 별도 bw_scale 불필요.
                _bw_scale = hist.get('bw_scale')
                if _bw_scale:
                    hist_mid = cum_skt_db + (hist_mid - cum_skt_db) * _bw_scale

            fc_mid = int(round(w_hist * hist_mid + (1 - w_hist) * fc_mid))
            hist_ratio_used = True
            log.info(f"[forecast_engine] 월마감보정 반영(mid만): method={_method} "
                     f"w_hist={w_hist:.2f} progress={progress_ratio:.2f} "
                     f"n={hist['n']} b={hist['b']:.2f} → fc_mid={fc_mid:,}")

    # [수정 20261003] 절편 없는 회귀(_get_historical_month_regression)로 교체하면서
    # 이 편향보정은 더 이상 적용 안 함 - 회귀 자체가 이미 24개월 전체 데이터에 맞춰진
    # 기울기라 추가 보정이 중복/과도 적용될 위험이 있고, 백테스트도 "보정 없는 회귀
    # 단독"으로 검증했음(6.12%, 기존 보정판 7.60%보다 정확). _bias_correction()은
    # 혹시 다른 곳에서 필요할 수 있어 함수 자체는 유지.

    # [v3.0, 20261006] 전월 동일시점 잔여속도법으로 mid 교체 (위 _get_prev_month_analog_pred
    # 설명 참고). 직전 2개월 데이터가 없는 등 계산 불가 시에만 위 기존 mid 유지.
    try:
        _analog = _get_prev_month_analog_pred(
            date_str, cum_skt, include_today=(_today_confirmed or fc_daily > 0))
    except Exception as e:
        log.warning(f"[forecast_engine] 전월 잔여속도법 실패 (기존 mid 유지): {e}")
        _analog = None
    if _analog:
        log.info(f"[forecast_engine] 전월 잔여속도법: refs={_analog['refs']} "
                 f"rate={_analog['rate']:,.0f}(pure {_analog['pure']:,.0f}/scaled "
                 f"{_analog['scaled']:,.0f}) × 잔여bw {_analog['remaining_bw']:.2f} "
                 f"→ fc_mid {fc_mid:,} → {int(round(_analog['pred'])):,}")
        fc_mid = int(round(_analog['pred']))

    # [v1.9] 밴드폭 최대 1000 고정 (mid 중심 대칭). avg법 스프레드가 이보다
    # 좁으면 그대로 쓰고, 넓으면 ±500으로 압축.
    _half = min(_avg_half, 500)
    fc_low  = int(round(fc_mid - _half))
    fc_high = int(round(fc_mid + _half))

    band = round((fc_high - fc_low) / fc_mid, 3) if fc_mid > 0 else 0

    # [v1.5] SKT OUT은 초과 이탈이 문제 → 목표 미달은 정상, 초과(105%+)일 때만 경고로 반전
    on_track = fc_mid <= goal * 1.05
    remaining_cum = max(0, goal - cum_skt_db)
    need_avg = int(remaining_cum / rbw) if rbw > 0 else 0
    ach_rate = round(cum_skt / goal * 100, 1) if goal > 0 else 0

    # remaining_avg/today_goal: Gemini 블록과 무관하게 먼저 계산
    _remaining_bw_incl = rbw + bw
    remaining_avg = int(remaining_cum / _remaining_bw_incl) if _remaining_bw_incl > 0 else 0
    today_goal    = int(remaining_avg * bw) if bw > 0 else 0
    pct_of_goal   = round(today_skt / today_goal * 100) if today_goal > 0 else 0

    # ── Gemini: comment + on_track 판단에만 사용 (fc_low/high는 수식 고정)
    comment = ''
    source  = 'formula'
    try:
        similar = get_similar_days(date_str, bw)
        pat     = get_hourly_pattern(date_str, 19, bw, 0)
        pat_info = (f"진행률 패턴: 19시 {pat['rate_at_hour']*100:.1f}% "
                    f"({pat['confidence']}, n={pat['sample_count']})"
                    if pat.get('available') else
                    f"패턴 학습 중 (n={pat.get('sample_count',0)})")

        ctx = {
            'date_str':       date_str,
            'wd_name':        wd_name,
            'bw':             bw,
            'current_hour':   19,
            'current_skt':    today_skt,
            'today_goal':     today_goal,
            'pct_of_goal':    pct_of_goal,
            'remaining_avg':  remaining_avg,
            'monthly_goal':   goal,
            'cum_skt':        cum_skt,
            'daily_avg':      avg_skt,
            'remaining_bw':   rbw,
            'need_avg':       need_avg,
            'fc_low':         fc_low,
            'fc_high':        fc_high,
            'ach_rate':       ach_rate,
            'on_track_formula': on_track,
            'similar_count':  similar['count'],
            'similar_dates':  similar['dates'],
            'similar_p25':    similar['p25'],
            'similar_p75':    similar['p75'],
            'similar_median': similar['median'],
            'pattern_info':   pat_info,
            'pattern_conf':   pat.get('confidence', 'LOW'),
            'pattern_n':      pat.get('sample_count', 0),
            'daily_fc_formula': fc_daily,
        }
        gemini = call_gemini_forecast(ctx)
        if gemini:
            # Gemini fc_low/high는 무시, comment + on_track만 사용
            comment  = gemini.get('comment', '')
            on_track = gemini.get('on_track', on_track)
            source   = 'gemini_comment'
    except Exception as e:
        log.debug(f"Gemini 호출 실패 (수식 결과 사용): {e}")

    result = {
        'fc_low':   fc_low,
        'fc_mid':   fc_mid,
        'fc_high':  fc_high,
        'fc_daily': fc_daily,
        'rbw':      rbw,
        'on_track': on_track,
        'comment':  comment,
        'source':   source,
        'band_pct': band,
        'need_avg': need_avg,
        'ach_rate': ach_rate,
        'cum_skt':  cum_skt,
        'goal':     goal,
        'bw':       bw,
        'remaining_avg': remaining_avg,
        'today_goal':    today_goal,
        'pct_of_goal':   pct_of_goal,
        'progress_ratio':   round(progress_ratio, 3),
        'hist_ratio_used':  hist_ratio_used,
    }

    # ktoa_daily DB 저장 (일마감 시만, S4 시트 A안 소스)
    if save_to_daily:
        try:
            _get_db().collection('ktoa_daily').document(date_str).set({
                'fc_low':      fc_low,
                'fc_mid':      fc_mid,
                'fc_high':     fc_high,
                'fc_daily':    fc_daily,
                'fc_bw':       bw,
                'fc_comment':  comment,
                'fc_on_track': on_track,
                'fc_saved_at': datetime.now(KST),
            }, merge=True)
            log.info(f"[forecast_engine] monthly 저장: {date_str} "
                     f"{fc_low:,}~{fc_high:,} ({source})")
        except Exception as e:
            log.warning(f"[forecast_engine] monthly DB 저장 실패: {e}")

    return result