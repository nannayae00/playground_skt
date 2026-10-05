"""
ktoa_telegram.py  v3.27
작성일: 2026-03-16

[수정 이력]
v3.27.1 | 2026-09-20 | _sign() ▲/▼ 반전건 원복 (Claude)
  - "▲N = 순감, +N = 순증"이 이 팀의 의도된 표기라 확인됨 (오해로 잠깐
    _trend_arrow() 관례에 맞춰 반전했다가 원복). 표기 자체는 문제없음.
v3.27 | 2026-09-07 | 세종이관 메시지 문구 수정 (Claude)
  - "◎ 세종 → 고고 이관, 누적(+전일증감)" → "◎ 세종 → 고고, {N}월누적(+전일증감)"
    (월 하드코딩 아님 — date_str 기준 당월 자동 반영, 리딩 제로 없이 표기)
v3.26 | 2026-09-07 | 세종→고고 이관 보정 마감 메시지 빌더 추가 (Claude)
  - build_sejong_correction_message(): build_closing_message() 재사용 패턴
    · SKT OUT 섹션 제거 → "세종 → 고고 이관" 섹션으로 교체
    · MVNO IN/OUT (당일·월누적) SM/KM/LM에서 이관값만큼 차감 후 % 재계산
    · 순증감 / MNO Out 섹션은 원본 그대로 (영향 없음)
v3.25 | 2026-06-18 | Firestore 경로 tout_goal → target_goal 변경 (Claude)
  - get_tout_goal(): ktoa_config/tout_goal → ktoa_config/target_goal
  - 환경변수 폴백: KTOA_TOUT_GOAL → KTOA_TARGET_GOAL
  - 함수명 get_tout_goal()은 T-Out 변수명과 일치해 그대로 유지
v3.24 | 2026-06-01 | 오늘 목표 영업일수 표기 변경
  - '×{bw}, 영업일수' → 'x{bw:.2f}, AI영업일수' (소수점 2자리, AI 명시)
  - 정시/10분단위/폴백 3곳 동일하게 적용
v3.23 | 2026-05-08 | MNO S/K/L 순증감 화살표 추가
  - build_message(): S/K/L 순증감에 arr_net() 적용 (7단계 화살표)
    · net_S/net_K/net_L streak은 ktoa_firestore.py v3.7에서 계산
v3.22 | 2026-05-07 | 월마감 예측 Exception 상세 로그 추가
  - except 블록: traceback 전체 출력으로 원인 파악
  - print flush=True로 Cloud Run 로그 즉시 반영
  - calc_stats(): mno_in, mno_out_all 신규 계산
    · mno_in[S]       = matrix['SKT']['소계'] (SKT로 들어온 전체)
    · mno_out_all[S]  = MNO→타MNO + MNO→MVNO 전체 (자사→자사 제외)
    · mno_net[S]      = mno_in[S] - mno_out_all[S]
  - net_change 반환 dict에 S/K/L/MNO계 키 추가 (MVNO SM/KM/LM/계 유지)
  - build_message(): 정시 메시지 ◎ 순증감 하단에 MNO 3사 순증감 추가
  - build_closing_message(): 일마감 ◎ 순증감(당일/월누적) 하단에 MNO 3사 추가
v3.20 | 2026-04-16 | (기존 유지)
v3.19 | 2026-04-16 | 일마감 예측값 DB 읽기로 전환 (단일 소스)
  - build_message(): 직접 계산 제거 → ktoa_hourly DB forecast 읽어옴
    · 상단 SKT OUT '예상 X' = DB forecast_mno_out.S → 완전 일치 보장
    · 본문 MNO Out/MVNO IN/Out 예측도 동일 DB값 사용
    · DB에 없으면 시간비례 외삽 폴백 (정시에만)
    · 정시/10분단위 모두 표시 (_has_est 항상 True if DB 있음)
v3.18 | 2026-04-16 | MNO Out 일마감 예측값을 predict_gemini 결과로 통일
  - build_message(): _hourly_docs 있으면 get_forecast()의 daily_forecast를 _est_mno['S'] 기준으로 사용
    · 상단 SKT OUT `예상 X` 와 본문 `MNO Out 일마감 예측 S` 값 불일치 해소
    · 패턴 역산 방식 유지하되, predict_gemini daily_forecast를 S 기준 상한으로 고정
    · SM/KM/LM은 기존 패턴 비율로 유지, 계 = daily_forecast 기준 역산 합산
  - calc_monthly_forecast() ±10% 고정→동적 밴드는 predict_gemini.py v1.1에서 처리
  - daily['date'] → daily.get('date', today_str) : KeyError 방지
  - cum_mvno_out 키 없을 때 빈 dict 폴백
  - _hourly_docs 없을 때 build_skt_closing 폴백 처리
  - send_closing_message: 전체 try/except로 에러 시 로그 출력 후 계속 진행
v3.16 | 2026-04-02 | 일마감 예측 섹션 정시에만 표시 + 오늘 목표 계산 수정
  - 일마감 예측 섹션: 정시(XX:00)에만 표시, 10분 단위는 제외
  - 오늘 목표: daily_avg가 0이면 잔여일평균 직접 사용
v3.15 | 2026-04-01 | SKT OUT 섹션 → Gemini 예측 엔진으로 교체
  - build_message(): predict_gemini.build_skt_section() 사용
    - 동적 bw (월×요일×주차+연휴보정), 월마감 예측범위, Gemini 코멘트
  - build_closing_message(): predict_gemini.build_skt_closing() 사용
    - 달성률, 일평균 대비 오늘 실적, 월마감 예측, Gemini 분석
  - 기존 get_billing_weights/calc_remaining_days 유지 (폴백용)
v3.14 | 2026-04-01 | 시간별 SKT OUT 잔여 일평균 목표에 월목표 표시 추가
  - 42000 → 4.2만, 36500 → 3.65만 형식
  - 잔여 일평균 목표: 1,520(월목표 4만) 형식으로 변경
v3.13 | 2026-04-01 | cum_tout 조회 당월 기준으로 수정
  - 직전 영업일 누적 조회 → 당월 데이터만 조회 (월 초기화 문제 해결)
  - 오늘 포함 당월 내에서 가장 최근 ktoa_daily 조회
v3.12 | 2026-03-31 | SKT OUT 목표 초과 시 메시지 수정 + 목표값 Firestore 관리
  - get_tout_goal(): 월별 목표값 Firestore ktoa_config/tout_goal/monthly/{YYYY-MM} 조회
  - 폴백: 환경변수 KTOA_TARGET_GOAL
  - build_message(): 누적 T Out >= 목표 시 SKT OUT 섹션 전체 제외
  - build_closing_message(): 누적 T Out >= 목표 시 잔여누적 줄 삭제
v3.11 | 2026-03-23 | 시간별 SKT OUT 오늘 목표치 추가
  - 오늘 목표 = 잔여 일평균 × 오늘 가중치
  - 당일 소진률 = 당일 T Out ÷ 오늘 목표
v3.10 | 2026-03-23 | 시간별 잔여 일평균 오늘 포함 유지 (today_day - 1)
v3.9  | 2026-03-23 | Firestore 조회 공통 함수 _get_telegram_db()로 통일
  - firebase_admin 중복 초기화 문제 해결
  - get_billing_weights(), calc_recent3_avg(), build_message() 모두 공통 함수 사용
v3.8  | 2026-03-23 | 시간별 SKT OUT 누적 T Out 조회 로직 수정
  - 오늘 ktoa_daily 없으면 직전 영업일 ktoa_daily에서 cum_mno_out.S 조회
  - calc_recent3_avg() 가중치 합산 방식으로 수정 (T Out 합 ÷ 가중치 합)
v3.7  | 2026-03-21 | 영업일수 Firestore 관리 + 요일별 기본값 자동 계산
  - get_billing_weights(): Firestore ktoa_config/billing_weights/{YYYY-MM} 조회
  - 없으면 요일/공휴일 기반 자동 계산 (일:0, 월:1.2, 화:1, 수:1.2, 목:1, 금:1, 토:0.6, 공휴일:0.6)
  - calc_remaining_days(): get_billing_weights() 기반으로 변경
v3.6  | 2026-03-21 | SKT OUT 섹션 추가
  - build_message(): 시간별 메시지 상단에 SKT OUT 섹션 추가
  - build_closing_message(): 일마감 메시지 상단에 SKT OUT 섹션 추가
  - calc_remaining_days(): 후불일별표 기반 잔여 영업일수 계산
v3.5  | 2026-03-19 | 화살표 이모지 7단계로 변경
  - ⏫ ⬆️ ↗️ - ↘️ ⬇️ ⏬ 7단계 이모지로 통일
v3.4  | 2026-03-19 | 전 시간 대비 증감 화살표 추가
  - _trend_arrow(): 연속성 기반 화살표 반환 함수
  - 점유율 ±0.1%p / 순증감 ±5건 기준, 동등: -
v3.3  | 2026-03-18 | 일마감 메시지 순증감 비율 제거
v3.2  | 2026-03-18 | MNP(MVNO) 비율 추가
v3.1  | 2026-03-18 | 시간별 메시지 시간 표시를 사이트 기준시각으로 변경
v3.0  | 2026-03-16 | 일마감 메시지 추가 (build_closing_message)
v2.0  | 2026-03-16 | 메시지 포맷 확정
v1.0  | 2026-03-16 | 최초 작성
"""

import os
import re
import logging
import requests

log = logging.getLogger(__name__)


def _fmt_man(v: int) -> str:
    """만 단위 표기: 42000→4.2만, 36500→3.65만, 40000→4만"""
    man = v / 10000
    if man == int(man):
        return f'{int(man)}만'
    # 소수점 불필요한 0 제거
    s = f'{man:.2f}'.rstrip('0').rstrip('.')
    return f'{s}만'


def _get_telegram_db():
    """Firestore 클라이언트 반환 (telegram 모듈용)"""
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as _fs
    if not firebase_admin._apps:
        _cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(_cred)
    return _fs.Client(project='mvno-484509', database='mvno-data')

# 요일별 기본 가중치 (Firestore 데이터 없을 때 사용)
# 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
_WEEKDAY_WEIGHTS = {0: 1.2, 1: 1.0, 2: 1.2, 3: 1.0, 4: 1.0, 5: 0.6, 6: 0.0}
_HOLIDAY_WEIGHT  = 0.6


def get_billing_weights(year: int, month: int) -> dict:
    """
    월별 영업일수 가중치 조회.
    Firestore ktoa_config/billing_weights/{YYYY-MM} 에서 먼저 조회,
    없으면 요일/공휴일 기반 자동 계산.
    반환: {1: 0.7, 2: 1.4, ..., 31: 1.3}
    """
    import calendar
    import holidays as _hol
    from datetime import date as _date

    ym_str = f'{year:04d}-{month:02d}'

    # Firestore 조회 시도
    try:
        _db = _get_telegram_db()
        doc = _db.collection('ktoa_config').document('billing_weights').collection('monthly').document(ym_str).get()
        if doc.exists:
            weights = doc.to_dict().get('weights', {})
            # key가 string으로 저장될 수 있으므로 int로 변환
            return {int(k): v for k, v in weights.items()}
    except Exception as e:
        log.warning(f"billing_weights Firestore 조회 실패 (자동계산): {e}")

    # 자동 계산 (요일/공휴일 기반)
    kr_holidays = _hol.KR()
    month_days  = calendar.monthrange(year, month)[1]
    weights = {}
    for d in range(1, month_days + 1):
        dt = _date(year, month, d)
        if dt in kr_holidays:
            weights[d] = _HOLIDAY_WEIGHT
        else:
            weights[d] = _WEEKDAY_WEIGHTS.get(dt.weekday(), 1.0)
    log.info(f"billing_weights 자동계산: {ym_str}")
    return weights


def get_tout_goal(year: int, month: int) -> int:
    """
    월별 SKT T Out 목표값 조회
    Firestore ktoa_config/tout_goal/monthly/{YYYY-MM} 우선 조회
    없으면 환경변수 KTOA_TARGET_GOAL 폴백
    """
    ym_str = f'{year:04d}-{month:02d}'
    try:
        _db = _get_telegram_db()
        doc = _db.collection('ktoa_config').document('target_goal')                  .collection('monthly').document(ym_str).get()
        if doc.exists:
            goal = doc.to_dict().get('goal', 0)
            if goal > 0:
                log.info(f"T Out 목표 조회: {ym_str} → {goal:,}")
                return int(goal)
    except Exception as e:
        log.warning(f"T Out 목표 Firestore 조회 실패 (환경변수 폴백): {e}")
    # 폴백: 환경변수
    return int(os.environ.get('KTOA_TARGET_GOAL', '42000'))


def calc_remaining_days(year: int, month: int, from_day: int) -> float:
    """from_day 다음날부터 말일까지 잔여 영업일수 합산"""
    import calendar
    weights = get_billing_weights(year, month)
    month_last = calendar.monthrange(year, month)[1]
    remaining = 0.0
    for d in range(from_day + 1, month_last + 1):
        remaining += weights.get(d, 1.0)
    return remaining


def calc_recent3_avg(cum_tout: int, date_str: str) -> int:
    """
    최근 3 영업일 T Out 일평균 계산 (가중치 합산 방식)
    공식: T Out 합계 ÷ 가중치 합계
    예: (1400+1423+1164) ÷ (1.0+1.0+0.6) = 3987 ÷ 2.6 = 1533
    """
    try:
        _db = _get_telegram_db()
        from datetime import datetime, timedelta
        base = datetime.strptime(date_str, '%Y-%m-%d')

        tout_values  = []
        weight_values = []
        _weights = get_billing_weights(base.year, base.month)

        for i in range(1, 15):
            prev_dt  = base - timedelta(days=i)
            prev_str = prev_dt.strftime('%Y-%m-%d')
            doc = _db.collection('ktoa_daily').document(prev_str).get()
            if doc.exists:
                data = doc.to_dict()
                tout = data.get('mno_out', {}).get('S', 0)
                if tout > 0:
                    w = _weights.get(prev_dt.day, 1.0)
                    tout_values.append(tout)
                    weight_values.append(w)
                if len(tout_values) >= 3:
                    break

        if tout_values and sum(weight_values) > 0:
            return int(sum(tout_values) / sum(weight_values))
    except Exception as e:
        log.warning(f"최근3일 T Out 조회 실패: {e}")
    return 0

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["TELEGRAM_CHAT_ID"]

ALL_KEYS  = ['SKT', 'KT', 'LGU', 'MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']
MVNO_KEYS = ['MVNO_SKT', 'MVNO_KT', 'MVNO_LGU']
MNO_KEYS  = ['SKT', 'KT', 'LGU']


def calc_stats(matrix: dict) -> dict:
    """matrix에서 MVNO IN/OUT, MNO Out, 순증감, total 계산
    matrix 구조: matrix[도착사업자][출발사업자] (소계 = 해당 사업자로 들어온 전체)
    """

    # MVNO IN = 해당 MVNO 소계 (모든 출발사업자에서 들어온 합)
    sm_in = matrix['MVNO_SKT']['소계']
    km_in = matrix['MVNO_KT']['소계']
    lm_in = matrix['MVNO_LGU']['소계']
    total_mvno_in = sm_in + km_in + lm_in

    # MVNO OUT = 각 출발사업자 행에서 해당 MVNO로 나간 수의 합
    sm_out = sum(matrix[k]['MVNO_SKT'] for k in ALL_KEYS)
    km_out = sum(matrix[k]['MVNO_KT']  for k in ALL_KEYS)
    lm_out = sum(matrix[k]['MVNO_LGU'] for k in ALL_KEYS)
    total_mvno_out = sm_out + km_out + lm_out

    # MVNO 순증감 = IN - OUT
    sm_net = sm_in - sm_out
    km_net = km_in - km_out
    lm_net = lm_in - lm_out
    total_mvno_net = sm_net + km_net + lm_net

    # MNO Out (기존) = MNO → MVNO 만
    s_mno = sum(matrix[k]['SKT'] for k in MVNO_KEYS)
    k_mno = sum(matrix[k]['KT']  for k in MVNO_KEYS)
    l_mno = sum(matrix[k]['LGU'] for k in MVNO_KEYS)
    total_mno_out = s_mno + k_mno + l_mno

    # MNO IN = 해당 MNO 소계 (모든 출발사업자에서 들어온 합)
    s_in = matrix['SKT']['소계']
    k_in = matrix['KT']['소계']
    l_in = matrix['LGU']['소계']
    total_mno_in = s_in + k_in + l_in

    # MNO OUT_ALL = MNO → 타MNO + MNO → MVNO 전체 (자사→자사 제외)
    # matrix[도착][출발] 구조이므로: 출발=SKT인 모든 도착 중 SKT 제외 합산
    s_out_all = sum(matrix[dest]['SKT'] for dest in ALL_KEYS if dest != 'SKT')
    k_out_all = sum(matrix[dest]['KT']  for dest in ALL_KEYS if dest != 'KT')
    l_out_all = sum(matrix[dest]['LGU'] for dest in ALL_KEYS if dest != 'LGU')
    total_mno_out_all = s_out_all + k_out_all + l_out_all

    # MNO 순증감 = mno_in - mno_out_all
    s_mno_net = s_in - s_out_all
    k_mno_net = k_in - k_out_all
    l_mno_net = l_in - l_out_all
    total_mno_net = s_mno_net + k_mno_net + l_mno_net

    # total
    total_mno  = s_in + k_in + l_in
    total_mvno = total_mvno_in
    total      = total_mno + total_mvno

    return {
        'mvno_in':     {'SM': sm_in,  'KM': km_in,  'LM': lm_in,  '계': total_mvno_in},
        'mvno_out':    {'SM': sm_out, 'KM': km_out, 'LM': lm_out, '계': total_mvno_out},
        'mno_out':     {'S': s_mno,   'K': k_mno,   'L': l_mno,   '계': total_mno_out},
        'mno_in':      {'S': s_in,    'K': k_in,    'L': l_in,    '계': total_mno_in},
        'mno_out_all': {'S': s_out_all, 'K': k_out_all, 'L': l_out_all, '계': total_mno_out_all},
        # net: MVNO(SM/KM/LM/계) + MNO(S/K/L/MNO계) 통합
        'net': {
            'SM': sm_net, 'KM': km_net, 'LM': lm_net, '계': total_mvno_net,
            'S': s_mno_net, 'K': k_mno_net, 'L': l_mno_net, 'MNO계': total_mno_net,
        },
        'total':      total,
        'total_mno':  total_mno,
        'total_mvno': total_mvno,
    }


def _pct(v, t):
    return f'{v/t*100:.1f}%' if t and t != 0 else '-'

def _sign(v):
    """[v3.28에서 ▲/▼ 반전으로 "수정"했다가 되돌림] "▲N"은 순감(N 감소)을
    뜻하는 이 팀의 의도된 표기 - 순증은 "+N"으로 별도 표기. _trend_arrow()의
    ↗↘(시간대별 추세 화살표)와는 별개 표기 체계라 서로 안 맞아 보이는 게
    정상."""
    return f'+{v:,}' if v >= 0 else f'▲{abs(v):,}'

def _sign_pct(v, t):
    """부호 포함 퍼센트 (순증감용)"""
    if not t or t == 0:
        return '-'
    p = v / t * 100
    return f'+{p:.1f}%' if p >= 0 else f'▲{abs(p):.1f}%'

def _k(v):
    """천 단위 표기: 1500 → 1.5천, 27600 → 27.6천"""
    if abs(v) >= 1000:
        return f'{v/1000:.1f}천'
    return f'{v:,}'


def _trend_arrow(curr: float, prev: float, streak: int, threshold: float) -> str:
    """
    전 시간 대비 증감 화살표 반환 (5단계 이모지)
    streak: 연속 횟수 (양수=상승연속, 음수=하락연속)
    threshold: 동등 기준 (점유율 0.1, 순증감 5)
    단계: ⏫ ⬆️ ↗️ - ↘️ ⬇️ ⏬
    """
    diff = curr - prev
    if abs(diff) <= threshold:
        return '-'
    elif diff > 0:
        if streak >= 2:
            return '⏫'
        elif streak == 1:
            return '⬆️'
        else:
            return '↗️'
    else:
        if streak <= -2:
            return '⏬'
        elif streak == -1:
            return '⬇️'
        else:
            return '↘️'


def _ref_time_to_hhmm(ref_time: str) -> str:
    """'20시 00분 이전' → '2000'"""
    m = re.search(r'(\d+)시\s*(\d+)분', ref_time)
    if m:
        return f'{int(m.group(1)):02d}{int(m.group(2)):02d}'
    return ref_time.replace(' ', '')


def build_message(stats: dict, prev_stats: dict = None,
                  forecast: dict = None) -> str:
    """시간별 메시지 - 날짜/시간은 사이트 기준시각 사용
    [v3.19] forecast: _save_hourly_forecast() 반환값 직접 수신
            DB 읽기 완전 제거 → 단일 소스 보장
    """
    from datetime import datetime
    site_date = stats.get('date', stats['collected_at'].strftime('%Y-%m-%d'))
    dt = datetime.strptime(site_date, '%Y-%m-%d')
    weekday  = ['월', '화', '수', '목', '금', '토', '일'][dt.weekday()]
    date_str = dt.strftime('%m%d')
    ref_time = _ref_time_to_hhmm(stats.get('reference_time', ''))
    matrix   = stats.get('matrix', {})
    c = calc_stats(matrix)

    mi  = c['mvno_in']
    mo  = c['mvno_out']
    mno = c['mno_out']
    net = c['net']

    # 전 시간 데이터 파싱
    has_prev = prev_stats is not None and prev_stats.get('matrix')
    if has_prev:
        pc = calc_stats(prev_stats['matrix'])
        pmi  = pc['mvno_in']
        pmo  = pc['mvno_out']
        pmno = pc['mno_out']
        pnet = pc['net']
        streak = prev_stats.get('streak', {})
    else:
        streak = {}

    def _s(key): return streak.get(key, 0)

    def _pct_val(v, t): return v / t * 100 if t else 0

    # 화살표 생성 (점유율 기준 0.1%p, 순증감 기준 5건)
    PCT_THR = 0.1
    NET_THR = 5

    def arr_pct(key, curr_dict, prev_dict, total_key='계'):
        if not has_prev: return ''
        curr = _pct_val(curr_dict[key], curr_dict[total_key])
        prev = _pct_val(prev_dict[key], prev_dict[total_key])
        return ' ' + _trend_arrow(curr, prev, _s(f'pct_{key}'), PCT_THR)

    def arr_net(key):
        if not has_prev: return ''
        return ' ' + _trend_arrow(net[key], pnet[key], _s(f'net_{key}'), NET_THR)

    def arr_mno(key):
        if not has_prev: return ''
        curr = _pct_val(mno[key], mno['계'])
        prev = _pct_val(pmno[key], pmno['계'])
        return ' ' + _trend_arrow(curr, prev, _s(f'mno_{key}'), PCT_THR)

    # ── 일마감 예측값: scraper에서 계산 후 직접 전달 (단일 소스)
    _fc = forecast or {}
    _est_mi  = _fc.get('mvno_in',  {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    _est_mno = _fc.get('mno_out',  {'S': 0,  'K': 0,  'L': 0,  '계': 0})
    _est_mo  = _fc.get('mvno_out', {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    _est_net = _fc.get('net',      {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})

    import re as _re2
    _min_match = _re2.search(r'(\d+)시\s*(\d+)분', stats.get('reference_time', ''))
    _ref_minute2 = int(_min_match.group(2)) if _min_match else 0
    _is_on_hour = (_ref_minute2 == 0)

    # 정시 + 예측값 있을 때만 예측 섹션 표시 (10분단위는 DB 저장만, 메시지 표시 안함)
    _has_est = bool(_is_on_hour and _fc and _est_mno.get('S', 0) > 0)

    import re as _re2
    _min_match = _re2.search(r'(\d+)시\s*(\d+)분', stats.get('reference_time', ''))
    _ref_minute2 = int(_min_match.group(2)) if _min_match else 0

    # ── SKT OUT 섹션 — forecast_engine 사용
    today_day  = dt.day
    today_tout = mno['S']
    _hourly_docs = stats.get('_hourly_docs', [])
    _ref_hour = int(re.search(r'(\d+)시', stats.get('reference_time','')).group(1)) \
                if re.search(r'(\d+)시', stats.get('reference_time','')) else dt.hour
    _min_m = re.search(r'\d+시\s*(\d+)분', stats.get('reference_time', ''))
    _ref_minute = int(_min_m.group(1)) if _min_m else 0
    _on_hour = (_ref_minute == 0)
    _db_fc_s = _est_mno.get('S', 0) if _has_est else 0

    try:
        tout_goal = get_tout_goal(dt.year, dt.month)

        if _on_hour:
            # 정시에만 월마감 예측 계산 (Gemini + bw 시나리오, 무거운 작업)
            from forecast_engine import predict_monthly as _pm
            _mfc = _pm(site_date, today_tout, save_to_daily=False,
                       current_hour=_ref_hour)
            cum_tout      = _mfc['cum_skt']
            goal_achieved = cum_tout >= tout_goal
            icon = '✅' if _mfc['on_track'] else '⚠️'
            # [수정 20260930] 기존엔 _db_fc_s(predict_hourly()의 패턴기반 예측,
            # forecast_mno_out.S)를 우선 쓰고 fc_daily(완료율곡선 기반)는 그게 없을
            # 때만 쓰는 폴백이었음 - 근데 패턴기반은 이미 9월 세션 초반 백테스트에서
            # 완료율곡선보다 훨씬 부정확한 걸로 확인됐었음(MAE 119.3 vs ~60).
            # 9/30 실측으로도 확인: 11시 패턴예측 1,545/12시 1,710 (실제마감 2,080
            # 대비 오차 25.7%/17.8%) vs 완료율곡선 11시 2,110/12시 1,896(오차
            # 1.4%/8.8%) - 압도적으로 완료율곡선이 정확함. 우선순위를 뒤집고,
            # 본문 'MNO Out(일마감예측)' S/K/L도 같은 값 기준으로 비례 재조정해서
            # 상단 '예상'값과 다시 불일치나지 않도록 함(v3.18에서 통일했던 것과 동일 취지).
            _completion_fc = _mfc.get('fc_daily', 0)
            if _completion_fc > 0:
                _daily_est = _completion_fc
            else:
                _daily_est = _db_fc_s if _db_fc_s > 0 else today_tout

            # [수정 20260930-2] SKT(S)에서 검증된 "요일필터+완료율곡선(중앙값)" 방식을
            # MNO Out K/L, MVNO IN/OUT SM/KM/LM에도 그대로 적용 - 156일 백테스트로
            # 8개 항목 전부 패턴기반보다 정확함을 확인(MAPE 25~49% 감소, get_field_
            # daily_forecast() 참고). K/L을 S 비율로 비례재조정하던 방식(20260930-1)
            # 대신 각 항목을 직접 완료율곡선으로 재계산하도록 교체.
            from forecast_engine import get_field_daily_forecast as _gdf
            if mno.get('K', 0) > 0:
                _est_mno['K'] = _gdf(site_date, _ref_hour, 'mno_out', 'K', mno['K'])
            if mno.get('L', 0) > 0:
                _est_mno['L'] = _gdf(site_date, _ref_hour, 'mno_out', 'L', mno['L'])
            if _completion_fc > 0:
                _est_mno['S'] = _completion_fc
            _est_mno['계'] = _est_mno['S'] + _est_mno['K'] + _est_mno['L']

            for _key in ('SM', 'KM', 'LM'):
                if mi.get(_key, 0) > 0:
                    _est_mi[_key] = _gdf(site_date, _ref_hour, 'mvno_in', _key, mi[_key])
                if mo.get(_key, 0) > 0:
                    _est_mo[_key] = _gdf(site_date, _ref_hour, 'mvno_out', _key, mo[_key])
            _est_mi['계'] = sum(_est_mi[k] for k in ('SM', 'KM', 'LM'))
            _est_mo['계'] = sum(_est_mo[k] for k in ('SM', 'KM', 'LM'))
            _est_net = {k: _est_mi[k] - _est_mo[k] for k in ('SM', 'KM', 'LM')}
            _est_net['계'] = sum(_est_net[k] for k in ('SM', 'KM', 'LM'))
            skt_lines = [
                '◎ SKT OUT',
                f'잔여 일평균 목표: {_mfc["remaining_avg"]:,}(월목표 {_fmt_man(tout_goal)})',
                f'오늘 목표 : {_mfc["today_goal"]:,} (x{round(_mfc["bw"],2)}, AI영업일수)',
                f'당일 소진률 : {today_tout:,} ({_mfc["pct_of_goal"]}%) → 예상 {_daily_est:,}',
                f'월마감 예측 : {_mfc["fc_low"]:,} ~ {_mfc["fc_high"]:,}  {icon}',
            ]
            if _mfc.get('comment'):
                skt_lines.append(f'💬 {_mfc["comment"]}')
        else:
            # 10분 단위: 직전 정시 예측값 사용 (속도보정 제거 — 정시 기준 유지)
            from forecast_engine import predict_monthly as _pm
            _mfc = _pm(site_date, today_tout, save_to_daily=False,
                       current_hour=_ref_hour)
            cum_tout      = _mfc['cum_skt']
            goal_achieved = cum_tout >= tout_goal

            # [수정 20261003] 주석은 "직전 정시 예측값 사용"이라 돼있었지만 실제로는
            # 매 10분마다 today_tout(분자)만 커진 채로 fc_daily를 다시 계산하고
            # 있었음 - 비율은 정시 시점에 캘리브레이션된 건데 분자만 갱신하면 같은
            # 시간대 안에서 숫자가 계속 치솟음(실측 10/3: 11:01→1,198, 11:11→1,430,
            # 11:21→1,722, 11:31→1,943). "정시 고정값이 10분단위 재계산보다 정확"함을
            # 이미 10/2 백테스트로 확인했었는데(94.93% vs 84.84%) 본문(predict_hourly)
            # 에만 적용하고 이 헤더 줄은 놓쳤던 것 - 이제 정시 문서의 실측 누적치(토요일
            # 11:01의 119 등, forecast 아닌 원본 mno_out.S)를 가져와 그 값과 같은
            # 완료율로 고정 계산해서 다음 정시까지 값이 안 바뀌게 함.
            _completion_fc = 0
            if _ref_hour >= 11:
                _on_hour_today_val = 0
                try:
                    _db = _get_telegram_db()
                    for _delta in [1, 0, 2, -1]:
                        _try_id = f"{site_date}_{_ref_hour:02d}{_delta:02d}"
                        _on_hour_doc = _db.collection('ktoa_hourly').document(_try_id).get()
                        if _on_hour_doc.exists:
                            _v = (_on_hour_doc.to_dict().get('mno_out', {}) or {}).get('S', 0) or 0
                            if _v > 0:
                                _on_hour_today_val = _v
                                break
                except Exception:
                    pass
                if _on_hour_today_val > 0:
                    from forecast_engine import _get_hour_completion_ratio as _ghcr
                    _ratio = _ghcr(site_date, _ref_hour)
                    if _ratio > 0:
                        _completion_fc = int(_on_hour_today_val / _ratio)

            if _completion_fc > 0:
                _daily_est = _completion_fc
            elif _ref_hour <= 10:
                _daily_est = 0  # 10시대는 미표시
            else:
                # 완료율곡선 계산이 안 될 때만(표본 부족 등) 직전 정시 DB의
                # forecast_mno_out.S(패턴기반) 폴백
                _prev_hour_fc_s = 0
                try:
                    _db = _get_telegram_db()
                    for _delta in [0, 1, 2, -1]:
                        _try_id = f"{site_date}_{_ref_hour:02d}{_delta:02d}"
                        _prev_doc = _db.collection('ktoa_hourly').document(_try_id).get()
                        if _prev_doc.exists:
                            _v = _prev_doc.to_dict().get('forecast_mno_out', {}).get('S', 0) or 0
                            if _v > 0:
                                _prev_hour_fc_s = _v
                                break
                except Exception:
                    pass
                _daily_est = _prev_hour_fc_s

            skt_lines = [
                '◎ SKT OUT',
                f'잔여 일평균 목표: {_mfc["remaining_avg"]:,}(월목표 {_fmt_man(tout_goal)})',
                f'오늘 목표 : {_mfc["today_goal"]:,} (x{round(_mfc["bw"],2)}, AI영업일수)',
                f'당일 소진률 : {today_tout:,} ({_mfc["pct_of_goal"]}%)'
                + (f' → 예상 {_daily_est:,}' if _daily_est > 0 else ''),
            ]

        skt_out_lines = [] if goal_achieved else ['\n'.join(skt_lines), '']

    except Exception as e:
        import traceback
        print(f"SKT OUT 섹션 실패, 폴백: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        tout_goal  = get_tout_goal(dt.year, dt.month)
        remaining_days = calc_remaining_days(dt.year, dt.month, today_day - 1)
        remaining_avg  = int(max(0, tout_goal) / remaining_days) if remaining_days > 0 else 0
        today_weight   = get_billing_weights(dt.year, dt.month).get(today_day, 1.0)
        today_goal     = int(remaining_avg * today_weight)
        pct_of_goal    = round(today_tout / today_goal * 100) if today_goal > 0 else 0
        _daily_est     = _db_fc_s if _db_fc_s > 0 else today_tout
        skt_out_lines  = ['\n'.join([
            '◎ SKT OUT',
            f'잔여 일평균 목표: {remaining_avg:,}(월목표 {_fmt_man(tout_goal)})',
            f'오늘 목표 : {today_goal:,} (x{round(today_weight,2)}, AI영업일수)',
            f'당일 소진률 : {today_tout:,} ({pct_of_goal}%) → 예상 {_daily_est:,}',
        ]), '']

    lines = [
        f'■ 실적현황_{date_str}({weekday})_{ref_time}',
        '',
        *skt_out_lines,
        # ── MVNO IN 현재
        '◎ MVNO IN',
        f'SM  {mi["SM"]:,} ({_pct(mi["SM"], mi["계"])}){arr_pct("SM", mi, pmi) if has_prev else ""}',
        f'KM  {mi["KM"]:,} ({_pct(mi["KM"], mi["계"])}){arr_pct("KM", mi, pmi) if has_prev else ""}',
        f'LM  {mi["LM"]:,} ({_pct(mi["LM"], mi["계"])}){arr_pct("LM", mi, pmi) if has_prev else ""}',
        f'계   {mi["계"]:,}',
        '',
        # ── MVNO IN 일마감 예측
        *([
            '◎ MVNO IN (일마감 예측)',
            f'SM  {_est_mi["SM"]:,} ({_pct(_est_mi["SM"], _est_mi["계"])})',
            f'KM  {_est_mi["KM"]:,} ({_pct(_est_mi["KM"], _est_mi["계"])})',
            f'LM  {_est_mi["LM"]:,} ({_pct(_est_mi["LM"], _est_mi["계"])})',
            f'계   {_est_mi["계"]:,}',
            '',
        ] if _has_est else []),
        # ── MNO Out 현재
        '◎ MNO Out',
        f'S  {mno["S"]:,} ({_pct(mno["S"], mno["계"])}){arr_mno("S") if has_prev else ""}',
        f'K  {mno["K"]:,} ({_pct(mno["K"], mno["계"])}){arr_mno("K") if has_prev else ""}',
        f'L  {mno["L"]:,} ({_pct(mno["L"], mno["계"])}){arr_mno("L") if has_prev else ""}',
        f'계  {mno["계"]:,}',
        '',
        # ── MNO Out 일마감 예측
        *([
            '◎ MNO Out (일마감 예측)',
            f'S  {_est_mno["S"]:,} ({_pct(_est_mno["S"], _est_mno["계"])})',
            f'K  {_est_mno["K"]:,} ({_pct(_est_mno["K"], _est_mno["계"])})',
            f'L  {_est_mno["L"]:,} ({_pct(_est_mno["L"], _est_mno["계"])})',
            f'계  {_est_mno["계"]:,}',
            '',
        ] if _has_est else []),
        # ── 순증감 현재
        '◎ 순증감',
        f'SM  {_sign(net["SM"])}{arr_net("SM") if has_prev else ""}',
        f'KM  {_sign(net["KM"])}{arr_net("KM") if has_prev else ""}',
        f'LM  {_sign(net["LM"])}{arr_net("LM") if has_prev else ""}',
        f'MVNO 계   {_sign(net["계"])}',
        '',
        *([
            f'S   {_sign(net["S"])}{arr_net("S") if has_prev else ""}',
            f'K   {_sign(net["K"])}{arr_net("K") if has_prev else ""}',
            f'L   {_sign(net["L"])}{arr_net("L") if has_prev else ""}',
            f'MNO 계  {_sign(net["MNO계"])}',
            '',
        ] if _is_on_hour else []),
        # ── 순증감 일마감 예측 (mvno_in - mvno_out)
        *([
            '◎ 순증감 (일마감 예측)',
            f'SM  {_sign(_est_net["SM"])}',
            f'KM  {_sign(_est_net["KM"])}',
            f'LM  {_sign(_est_net["LM"])}',
            f'계   {_sign(_est_net["계"])}',
            '',
        ] if _has_est else []),
        # ── MVNO Out 현재
        '◎ MVNO Out',
        f'SM  {mo["SM"]:,} ({_pct(mo["SM"], mo["계"])}){arr_pct("SM", mo, pmo) if has_prev else ""}',
        f'KM  {mo["KM"]:,} ({_pct(mo["KM"], mo["계"])}){arr_pct("KM", mo, pmo) if has_prev else ""}',
        f'LM  {mo["LM"]:,} ({_pct(mo["LM"], mo["계"])}){arr_pct("LM", mo, pmo) if has_prev else ""}',
        f'계   {mo["계"]:,}',
        '',
        # ── MVNO Out 일마감 예측
        *([
            '◎ MVNO Out (일마감 예측)',
            f'SM  {_est_mo["SM"]:,} ({_pct(_est_mo["SM"], _est_mo["계"])})',
            f'KM  {_est_mo["KM"]:,} ({_pct(_est_mo["KM"], _est_mo["계"])})',
            f'LM  {_est_mo["LM"]:,} ({_pct(_est_mo["LM"], _est_mo["계"])})',
            f'계   {_est_mo["계"]:,}',
            '',
        ] if _has_est else []),
        f'MNP(총계)  {c["total"]:,}',
        f'MNP(MNO)  {c["total_mno"]:,} ({_pct(c["total_mno"], c["total"])})',
        f'MNP(MVNO) {c["total_mvno"]:,} ({_pct(c["total_mvno"], c["total"])})',
    ]
    return '\n'.join(lines)


def build_closing_message(daily: dict, prev_daily: dict = None) -> str:
    """
    20시 일마감 메시지.
    daily = save_ktoa_daily() 반환값
    prev_daily = 전일 마감 데이터 (화살표 비교용)
    """
    # [v3.17] date 필드 없을 때 폴백
    import datetime as _dt
    _today_str = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).strftime('%Y-%m-%d')
    date_str = daily.get('date', _today_str)
    dt = _dt.datetime.strptime(date_str, '%Y-%m-%d')
    weekday  = ['월', '화', '수', '목', '금', '토', '일'][dt.weekday()]
    mmdd     = dt.strftime('%m%d')
    month    = dt.strftime('%m')

    # [v3.17] 각 필드 없을 때 빈 dict 폴백
    mi   = daily.get('mvno_in',    {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    mo   = daily.get('mvno_out',   {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    mno  = daily.get('mno_out',    {'S': 0,  'K': 0,  'L': 0,  '계': 0})
    net  = daily.get('net_change', {'SM': 0, 'KM': 0, 'LM': 0, '계': 0, 'S': 0, 'K': 0, 'L': 0, 'MNO계': 0})
    cmi  = daily.get('cum_mvno_in',  {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    cmo  = daily.get('cum_mvno_out', {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    cmno = daily.get('cum_mno_out',  {'S': 0,  'K': 0,  'L': 0,  '계': 0})
    cnet = daily.get('cum_net',      {'SM': 0, 'KM': 0, 'LM': 0, '계': 0, 'S': 0, 'K': 0, 'L': 0, 'MNO계': 0})

    # 전일 마감 비교용
    has_prev = prev_daily is not None
    pmi  = prev_daily.get('mvno_in',  {}) if has_prev else {}
    pmo  = prev_daily.get('mvno_out', {}) if has_prev else {}
    pmno = prev_daily.get('mno_out',  {}) if has_prev else {}
    pnet = prev_daily.get('net_change', {}) if has_prev else {}

    PCT_THR = 0.1
    NET_THR = 5

    def _pv(v, t): return v / t * 100 if t else 0

    def arr_pct(key, curr_d, prev_d):
        if not has_prev or not prev_d: return ''
        curr = _pv(curr_d.get(key, 0), curr_d.get('계', 1))
        prev = _pv(prev_d.get(key, 0), prev_d.get('계', 1))
        return ' ' + _trend_arrow(curr, prev, 0, PCT_THR)

    def arr_mno(key):
        if not has_prev or not pmno: return ''
        curr = _pv(mno.get(key, 0), mno.get('계', 1))
        prev = _pv(pmno.get(key, 0), pmno.get('계', 1))
        return ' ' + _trend_arrow(curr, prev, 0, PCT_THR)

    def arr_net(key):
        if not has_prev or not pnet: return ''
        return ' ' + _trend_arrow(net.get(key, 0), pnet.get(key, 0), 0, NET_THR)

    # SKT OUT 섹션 — predict_gemini 엔진
    today_tout = mno.get('S', 0)
    _hourly_docs = daily.get('_hourly_docs', [])

    try:
        if not _hourly_docs:
            raise ValueError("_hourly_docs 없음 → 폴백")  # [v3.17] hourly 없으면 바로 폴백
        from predict_gemini import build_skt_closing as _build_skt_c
        skt_section = _build_skt_c(date_str, today_tout, _hourly_docs)
        tout_goal   = get_tout_goal(dt.year, dt.month)
        cum_tout    = cmno.get('S', 0)
        goal_achieved = cum_tout >= tout_goal
    except Exception as e:
        log.warning(f"predict_gemini closing 실패, 폴백: {e}")
        tout_goal    = get_tout_goal(dt.year, dt.month)
        cum_tout     = cmno.get('S', 0)
        today_day    = dt.day
        remaining_days = calc_remaining_days(dt.year, dt.month, today_day)
        remaining_cum = tout_goal - cum_tout
        remaining_avg = int(remaining_cum / remaining_days) if remaining_days > 0 else 0
        recent3_avg   = calc_recent3_avg(cum_tout, date_str)
        goal_achieved = cum_tout >= tout_goal
        skt_section = '\n'.join([
            '◎ SKT OUT',
            f'목표 : {tout_goal:,}',
            f'현누적 : {cum_tout:,} (최근3일 일평균 {recent3_avg:,})',
            *([] if goal_achieved else [f'잔여누적 : {remaining_cum:,} (잔여 일평균 {remaining_avg:,})']),
        ])

    lines = [
        f'■ 실적 현황 보고_{mmdd}({weekday})',
        '',
        # ── SKT OUT (예측 포함)
        skt_section,
        '',
        # ── MVNO IN 당일
        '◎ MVNO IN (당일)',
        f'SM  {mi["SM"]:,} ({_pct(mi["SM"], mi["계"])}){arr_pct("SM", mi, pmi)}',
        f'KM  {mi["KM"]:,} ({_pct(mi["KM"], mi["계"])}){arr_pct("KM", mi, pmi)}',
        f'LM  {mi["LM"]:,} ({_pct(mi["LM"], mi["계"])}){arr_pct("LM", mi, pmi)}',
        f'계  {mi["계"]:,}',
        '',
        # ── MVNO IN 월 누적
        f'◎ MVNO IN ({month}월 누적)',
        f'SM  {_k(cmi["SM"])} ({_pct(cmi["SM"], cmi["계"])})',
        f'KM  {_k(cmi["KM"])} ({_pct(cmi["KM"], cmi["계"])})',
        f'LM  {_k(cmi["LM"])} ({_pct(cmi["LM"], cmi["계"])})',
        f'계  {_k(cmi["계"])}',
        '',
        # ── MNO Out 당일
        '◎ MNO Out (당일)',
        f'S  {mno["S"]:,} ({_pct(mno["S"], mno["계"])}){arr_mno("S")}',
        f'K  {mno["K"]:,} ({_pct(mno["K"], mno["계"])}){arr_mno("K")}',
        f'L  {mno["L"]:,} ({_pct(mno["L"], mno["계"])}){arr_mno("L")}',
        f'계  {mno["계"]:,}',
        '',
        # ── MNO Out 월 누적
        f'◎ MNO Out ({month}월 누적)',
        f'S  {_k(cmno["S"])} ({_pct(cmno["S"], cmno["계"])})',
        f'K  {_k(cmno["K"])} ({_pct(cmno["K"], cmno["계"])})',
        f'L  {_k(cmno["L"])} ({_pct(cmno["L"], cmno["계"])})',
        f'계  {_k(cmno["계"])}',
        '',
        # ── 순증감 당일
        '◎ 순증감 (당일)',
        f'SM  {_sign(net["SM"])}{arr_net("SM")}',
        f'KM  {_sign(net["KM"])}{arr_net("KM")}',
        f'LM  {_sign(net["LM"])}{arr_net("LM")}',
        f'MVNO 계  {_sign(net["계"])}',
        '',
        f'S   {_sign(net["S"])}',
        f'K   {_sign(net["K"])}',
        f'L   {_sign(net["L"])}',
        f'MNO 계  {_sign(net["MNO계"])}',
        '',
        # ── 순증감 월 누적
        f'◎ 순증감 ({month}월 누적)',
        f'SM  {_sign(cnet["SM"])}',
        f'KM  {_sign(cnet["KM"])}',
        f'LM  {_sign(cnet["LM"])}',
        f'MVNO 계  {_sign(cnet["계"])}',
        '',
        f'S   {_sign(cnet.get("S", 0))}',
        f'K   {_sign(cnet.get("K", 0))}',
        f'L   {_sign(cnet.get("L", 0))}',
        f'MNO 계  {_sign(cnet.get("MNO계", 0))}',
        '',
        # ── MVNO Out 당일
        '◎ MVNO Out (당일)',
        f'SM  {mo["SM"]:,} ({_pct(mo["SM"], mo["계"])}){arr_pct("SM", mo, pmo)}',
        f'KM  {mo["KM"]:,} ({_pct(mo["KM"], mo["계"])}){arr_pct("KM", mo, pmo)}',
        f'LM  {mo["LM"]:,} ({_pct(mo["LM"], mo["계"])}){arr_pct("LM", mo, pmo)}',
        f'계  {mo["계"]:,}',
        '',
        # ── MVNO Out 월 누적
        f'◎ MVNO Out ({month}월 누적)',
        f'SM  {_k(cmo["SM"])} ({_pct(cmo["SM"], cmo["계"])})',
        f'KM  {_k(cmo["KM"])} ({_pct(cmo["KM"], cmo["계"])})',
        f'LM  {_k(cmo["LM"])} ({_pct(cmo["LM"], cmo["계"])})',
        f'계  {_k(cmo["계"])}',
    ]
    return '\n'.join(lines)


def build_sejong_correction_message(daily: dict, migration: dict,
                                     prev_daily: dict = None) -> str:
    """
    세종→고고 이관 보정 마감 메시지.
    daily     = 원본 ktoa_daily (당일 마감 데이터, get_previous_daily_for_closing 등으로 조회)
    migration = ktoa_daily_sejong_migration 문서 (해당일 이관 daily/cum)
    prev_daily = 전일 마감 데이터 (화살표 비교용, build_closing_message와 동일)

    build_closing_message()와 동일한 구조를 쓰되:
      - SKT OUT 섹션 → "세종 → 고고 이관" 섹션으로 교체
      - MVNO IN/OUT (당일·월누적)의 SM/KM/LM에서 이관값만큼 차감 후 %/합계 재계산
      - 순증감, MNO Out 섹션은 원본 그대로 (영향 없음)
    """
    import datetime as _dt
    _today_str = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).strftime('%Y-%m-%d')
    date_str = daily.get('date', _today_str)
    dt = _dt.datetime.strptime(date_str, '%Y-%m-%d')
    weekday  = ['월', '화', '수', '목', '금', '토', '일'][dt.weekday()]
    mmdd     = dt.strftime('%m%d')
    month    = dt.strftime('%m')

    mig_daily = migration.get('daily', {}) if migration else {}
    mig_cum   = migration.get('cum', {})   if migration else {}

    def _sub(v, m):
        """None(미확인)이면 차감하지 않고 원본 그대로 사용"""
        if m is None:
            return v
        return v - m

    # 원본값
    mi_raw  = daily.get('mvno_in',    {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    mo_raw  = daily.get('mvno_out',   {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    cmi_raw = daily.get('cum_mvno_in',  {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    cmo_raw = daily.get('cum_mvno_out', {'SM': 0, 'KM': 0, 'LM': 0, '계': 0})
    mno     = daily.get('mno_out',    {'S': 0,  'K': 0,  'L': 0,  '계': 0})
    net     = daily.get('net_change', {'SM': 0, 'KM': 0, 'LM': 0, '계': 0, 'S': 0, 'K': 0, 'L': 0, 'MNO계': 0})
    cnet    = daily.get('cum_net',    {'SM': 0, 'KM': 0, 'LM': 0, '계': 0, 'S': 0, 'K': 0, 'L': 0, 'MNO계': 0})

    # 이관값 차감
    def _adjust(d, mig):
        out = {}
        for k in ('SM', 'KM', 'LM'):
            out[k] = _sub(d.get(k, 0), mig.get(k))
        out['계'] = sum(v for v in out.values() if v is not None)
        return out

    mi  = _adjust(mi_raw,  mig_daily)
    mo  = _adjust(mo_raw,  mig_daily)
    cmi = _adjust(cmi_raw, mig_cum)
    cmo = _adjust(cmo_raw, mig_cum)

    has_prev = prev_daily is not None
    pmi = prev_daily.get('mvno_in',  {}) if has_prev else {}
    pmo = prev_daily.get('mvno_out', {}) if has_prev else {}

    PCT_THR = 0.1

    def arr_pct(key, curr_d, prev_d):
        if not has_prev or not prev_d:
            return ''
        curr = _pv(curr_d.get(key, 0), curr_d.get('계', 1) or 1)
        prev = _pv(prev_d.get(key, 0), prev_d.get('계', 1) or 1)
        return ' ' + _trend_arrow(curr, prev, 0, PCT_THR)

    def _pv(v, t):
        return v / t * 100 if t else 0

    def _fmt(v):
        return f'{v:,}' if v is not None else '미확인'

    migration_section = '\n'.join([
        f'◎ 세종 → 고고, {dt.month}월누적(+전일증감)',
        f' S망 : {_fmt(mig_cum.get("SM"))}건(+{_fmt(mig_daily.get("SM"))})',
        f' K망 : {_fmt(mig_cum.get("KM"))}(+{_fmt(mig_daily.get("KM"))})',
        f' L망 : {_fmt(mig_cum.get("LM"))}(+{_fmt(mig_daily.get("LM"))})',
    ])

    lines = [
        f'📋 수정 일마감 메시지 ({date_str} {weekday})',
        ' [ 세종 이관 제외 ]',
        '',
        migration_section,
        '',
        '◎ MVNO IN (당일)',
        f'SM  {mi["SM"]:,} ({_pct(mi["SM"], mi["계"])}){arr_pct("SM", mi, pmi)}',
        f'KM  {mi["KM"]:,} ({_pct(mi["KM"], mi["계"])}){arr_pct("KM", mi, pmi)}',
        f'LM  {mi["LM"]:,} ({_pct(mi["LM"], mi["계"])}){arr_pct("LM", mi, pmi)}',
        f'계  {mi["계"]:,}',
        '',
        f'◎ MVNO IN ({month}월 누적)',
        f'SM  {_k(cmi["SM"])} ({_pct(cmi["SM"], cmi["계"])})',
        f'KM  {_k(cmi["KM"])} ({_pct(cmi["KM"], cmi["계"])})',
        f'LM  {_k(cmi["LM"])} ({_pct(cmi["LM"], cmi["계"])})',
        f'계  {_k(cmi["계"])}',
        '',
        '◎ MNO Out (당일)',
        f'S  {mno["S"]:,} ({_pct(mno["S"], mno["계"])})',
        f'K  {mno["K"]:,} ({_pct(mno["K"], mno["계"])})',
        f'L  {mno["L"]:,} ({_pct(mno["L"], mno["계"])})',
        f'계  {mno["계"]:,}',
        '',
        f'◎ MNO Out ({month}월 누적)',
        f'S  {_k(daily.get("cum_mno_out", {}).get("S", 0))}',
        f'K  {_k(daily.get("cum_mno_out", {}).get("K", 0))}',
        f'L  {_k(daily.get("cum_mno_out", {}).get("L", 0))}',
        f'계  {_k(daily.get("cum_mno_out", {}).get("계", 0))}',
        '',
        '◎ 순증감 (당일)',
        f'SM  {_sign(net["SM"])}',
        f'KM  {_sign(net["KM"])}',
        f'LM  {_sign(net["LM"])}',
        f'MVNO 계  {_sign(net["계"])}',
        '',
        f'S   {_sign(net["S"])}',
        f'K   {_sign(net["K"])}',
        f'L   {_sign(net["L"])}',
        f'MNO 계  {_sign(net["MNO계"])}',
        '',
        f'◎ 순증감 ({month}월 누적)',
        f'SM  {_sign(cnet["SM"])}',
        f'KM  {_sign(cnet["KM"])}',
        f'LM  {_sign(cnet["LM"])}',
        f'MVNO 계  {_sign(cnet["계"])}',
        '',
        f'S   {_sign(cnet.get("S", 0))}',
        f'K   {_sign(cnet.get("K", 0))}',
        f'L   {_sign(cnet.get("L", 0))}',
        f'MNO 계  {_sign(cnet.get("MNO계", 0))}',
        '',
        '◎ MVNO Out (당일)',
        f'SM  {mo["SM"]:,} ({_pct(mo["SM"], mo["계"])}){arr_pct("SM", mo, pmo)}',
        f'KM  {mo["KM"]:,} ({_pct(mo["KM"], mo["계"])}){arr_pct("KM", mo, pmo)}',
        f'LM  {mo["LM"]:,} ({_pct(mo["LM"], mo["계"])}){arr_pct("LM", mo, pmo)}',
        f'계  {mo["계"]:,}',
        '',
        f'◎ MVNO Out ({month}월 누적)',
        f'SM  {_k(cmo["SM"])} ({_pct(cmo["SM"], cmo["계"])})',
        f'KM  {_k(cmo["KM"])} ({_pct(cmo["KM"], cmo["계"])})',
        f'LM  {_k(cmo["LM"])} ({_pct(cmo["LM"], cmo["계"])})',
        f'계  {_k(cmo["계"])}',
    ]
    return '\n'.join(lines)


def send_ktoa_message(stats: dict, prev_stats: dict = None,
                      forecast: dict = None) -> None:
    """시간별 메시지 전송"""
    msg = build_message(stats, prev_stats, forecast=forecast)
    _send(msg)


def send_closing_message(daily: dict, prev_daily: dict = None) -> None:
    """일마감 메시지 전송"""
    try:
        msg = build_closing_message(daily, prev_daily)
        log.info(f'마감 메시지:\n{msg}')
        _send(msg)
    except Exception as e:
        log.error(f'build_closing_message 실패: {e}')
        # [v3.17] 최소 폴백 메시지라도 전송
        try:
            import datetime as _dt
            _today = daily.get('date', _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).strftime('%Y-%m-%d'))
            _total = daily.get('total', '?')
            _send(f'■ 일마감 ({_today})\n합계: {_total}\n※ 메시지 생성 오류 — 로그 확인 필요')
        except Exception as e2:
            log.error(f'폴백 메시지 전송도 실패: {e2}')


def _send(msg: str) -> None:
    url     = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': msg}
    try:
        resp   = requests.post(url, json=payload, timeout=10)
        result = resp.json()
        if result.get('ok'):
            log.info('텔레그램 전송 완료')
        else:
            log.error(f'텔레그램 전송 실패: {result}')
    except Exception as e:
        log.error(f'텔레그램 전송 오류: {e}')