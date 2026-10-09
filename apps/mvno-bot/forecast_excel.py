"""
forecast_excel.py  v3.14
작성일: 2026-04-01

[수정 이력]
v3.14 | 2026-09-07 | 세종→고고 이관 시트 2개 추가 (Claude)
  - _load_month_migration(): ktoa_daily_sejong_migration 월 조회 (ktoa_firestore 위임)
  - _build_sejong_trend(): "고고 전환 추이" 시트 신규 — 전체 이력(월별 소계 + 전체 누계)
  - _build_s3_monthly_adjusted(): "일별실적(세종 이관 반영)" 시트 신규
    · _build_s3_monthly()과 동일 구조, MVNO IN/OUT의 SM/KM/LM만 이관값 차감
  - generate_report(): 위 두 시트를 "일별 실적" 시트 뒤에 추가 (기존 6개 시트 로직 변경 없음)
  - build_excel_caption(): Sheet 구성 안내에 신규 시트 2개 반영, 실제 삽입 위치(S2 직후)에 맞춰
    번호 재정렬 (S3:일별실적세종이관반영, S4:고고전환추이 → 기존 S3~S5는 S5~S7로 밀림)
v3.13 | 2026-06-12 | 월마감 캡션 - 순기별 예측 정확도로 변경
  - get_month_forecast_accuracy(): 월 전체 영업일에 대해
    get_daily_forecast_accuracy()를 호출해 1~10일/11~20일/21~말일 순기별
    + 전체 평균 정확도 산출 (T-Out/MVNO IN(SM)/MVNO OUT(SM))
  - build_excel_caption(is_month_closing=True): 기존 "당일(예: 5/30) 11~19시"
    단일 정확도 대신 위 순기별 정확도 표를 캡션에 표시
v3.12 | 2026-06-12 | 월마감 확정 엑셀 + 과거월 리포트 함수 추가
  - generate_month_closing_report(): 월마감일 기준 generate_report 재사용,
    파일명 'MVNO_월마감_YYYY-MM.xlsx'로 구분 (작업2)
  - find_last_business_day_of_month(): 해당 월 ktoa_daily 중 mvno_in 있는
    가장 늦은 날짜(마지막 영업일) 탐색 - 과거월 리포트 기준일 결정용
  - generate_month_report_for(): 지정 연/월의 마지막 영업일 데이터로
    generate_report 호출 (과거월 "N월 엑셀 추출" 대응, 작업3)
  - build_excel_caption(): is_month_closing 파라미터 추가, 월마감 캡션 분기
  - [추가] _build_s0_month_summary(): '월마감 요약' 시트 신규 (일마감 요약의
    월 전체 버전). generate_report에 include_month_summary 파라미터 추가,
    월마감 리포트에서만 맨 앞 시트로 삽입 (작업2)
  - [추가] S4 '실제마감/정확도' 컬럼이 calendar 말일(예: 5/31 휴무일) 기준이라
    항상 비어있던 버그 수정 → "마지막 영업일(실적 있는 날)" 기준으로 변경 (작업3)
  - [추가] _backfill_bw_performance(): 월마감 시 해당 월 전체 bw_performance
    계산/저장 (calc_bw_performance_mvno + get_month_avg_mvno_in 재사용).
    S4/S5의 '실적기반(bw_perf)' 컬럼이 항상 비어있던 문제 해결 (작업4)
v3.11 | 2026-05-09 | S4 예측값 개선
  - 순증감 예측 = MVNO IN 예측 - MVNO OUT 예측 (기존: bw 단독 계산)
  - DB 저장된 fc_ 전항목 우선 사용 (fc_mvno_in/fc_mno_out/fc_mvno_out/fc_net)
    없으면 기존 실시간 계산 폴백
v3.10 | 2026-04-21 | 엑셀 캡션용 일마감 예측 정확도 계산 함수 추가
  - get_daily_forecast_accuracy(): 11~19시 평균 예측값 vs 실제마감 비교
    · forecast_* 필드 우선, 없으면 현재값 × (10/경과시간) 폴백
    · 표시 항목: T Out(SKT), MVNO IN(SM), MVNO OUT(SM)
  - build_excel_caption(): 엑셀 전송 캡션 메시지 생성
    · 날짜 포맷: '26.4.21일 기준
    · 예측 정확도 3항목 + Sheet 구성 안내
v3.9 | 2026-04-20 | 시간별 예측 시트 대폭 개선
  - 수정1: D~L 셀 배경색 통일 (연한 회청색 #F0F4FA), 글자색만 정확도로 구분
  - 수정2: 정확도 위치 이동
    · 정확도(전체): 예측행(예 행) N열에 표시 (1행 위)
    · 정확도(11~13/14~16/17~19): % 행 O~Q열에 표시 (기존과 동일 행)
  - 색상 변경: 95%↑ 진초록(#1F6B3B) / 90%↑ 진파랑(#2E75B6) / 미만 회색(#808080)
    모두 흰 텍스트로 가독성 확보
v3.8 | 2026-04-20 | 추가 수정
  - 이슈1: 시간별 % 행 정확도 색상 - 조건부서식→Python 직접 계산으로 변경
    · 95%↑ 빨강(배경), 90%↑ 주황, 90%미만 파랑 (흰 텍스트, 10pt 볼드)
    · 시간별 예측값과 실제마감값 비교로 실시간 색상 결정
  - 이슈2: 영업일수 시트(S5) + 영업일수 예측 정확도(S6) 통합
    · S5에 오차(abs)/MAE누적/비고 컬럼 추가
    · 오차 색상: 0.05↓ 초록, 0.2↑ 주황
    · S6 별도 시트 제거
  - S4 달성률 행 제거 재확인
v3.7 | 2026-04-20 | 추가 수정 3건
  - 추가수정1: S4 달성률 행 제거 + A/B열 같은 값 셀 병합 (구분/항목)
  - 추가수정2: 영업일수 시트 그룹헤더 수동입력→후불기준 (컬럼 헤더는 기존과 동일)
  - 추가수정3: 시간별 예측 % 행 색상 조건부 적용
    · 95%↑ 빨강, 90%↑ 주황, 90% 미만 파랑
    · 폰트 크기 10pt 볼드 (실제마감과 동일)
    · 전체/구간별 정확도 모두 적용
v3.6 | 2026-04-20 | 4가지 수정
  - 수정1: 예측High 색상 _C['ai'](연초록) → _C['bad'](주황) 변경 (예측Low와 동일)
  - 수정2: 영업일수 시트 컬럼명 '수동입력(bw_manual)' → '후불기준(bw_manual)'
  - 수정3: 시트명 '예측 정확도' → '영업일수 예측 정확도'
  - 수정4: 시간별 예측(과거) 시트 정확도 3구간 컬럼 추가
    · 기존: 정확도(전체) 1개
    · 추가: 정확도(11~13시) / 정확도(14~16시) / 정확도(17~19시)
    · 각 구간: AVERAGE(해당 시간대 예측값들) vs 실제마감 비교
v3.5 | 2026-04-18 | S3 시간별 예측 시트 정시 문서 우선 적용
  - _build_s2_hourly() hourly_by_hour 구성 로직 2단계로 개선
    · 기존: collected_at 최신 덮어쓰기 → 10분단위(12:01)가 정시(12:00) 덮어씀
    · 수정: 1단계 정시(forecast_minute=0) 먼저 등록
            2단계 정시 없는 시간대만 10분단위로 채움
    · 효과: S3 시트 정시 예측값(975, 913 등)이 정확히 표시됨
v3.4 | 2026-04-16 | S4 전면 재작성 - 4개 섹션 + bw 소스 정리
  - MVNO IN/MNO Out/순증감/MVNO Out 각 low/mid/high 예측 추가
  - bw: ktoa_daily 필드만 사용, bw_map 폴백 완전 제거
  - 열 구조: A=구분/B=항목/C=실예/D~=날짜/말일마감/정확도
  - freeze_panes: D5 (구분+항목+실예 + 헤더 고정)
v3.3 | 2026-04-16 | 시트 순서 변경 + S4 월마감 예측 추이 전면 개편
  - 시트 순서: S1 일마감 요약 / S2 일별실적(구S3) / S3 시간별예측(구S2) / S4~ 동일
  - _build_s4_forecast() 전면 개편:
    · 열 구조: 1일~말일 (날짜가 열)
    · 행 구조: 누적T-Out실적 / 경과bw / 잔여bw / 영업일수별 월마감예측(Low/Mid/High)
    · bw 시나리오 3종: bw_manual(High) / bw_ai_prev(Mid) / bw_ai_w2(Low)
    · 오늘 열 강조, 미래 열 연회색, 영업0일 회색
v3.2 | 2026-04-16 | S2/과거시트 4가지 수정
  - 수정1: S7 구분 시트 "시간별 예측(과거) →" 추가
  - 수정2: S2 타이틀 hourly 실제 날짜로 표시 (s2_date)
  - 수정3: 과거 시트에 오늘(date_str) 포함 (d <= date_str)
  - 수정4: HOURS 11~19시로 변경 (20시 = 실제마감 컬럼과 중복이므로 제외)
  - 순증감 예측: forecast_net 없으면 mvno_in - mvno_out 자동 계산
  - _build_s2_hourly: sheet_name 파라미터 추가
v3.1 | 2026-04-15 | S2 시간별 예측 버그 2개 수정
  - _load_today_hourly(): order_by('collected_at') 제거 → Python 정렬로 대체
    (Firestore 복합 인덱스 없어서 에러 → 빈 배열 반환 → S2 공백 원인)
  - _build_s2_hourly(): forecast_hour 필드 우선 파싱, 없으면 reference_time 파싱
    (신버전 문서는 forecast_hour:int, 구버전은 reference_time:"13시")
  - generate_query_report(): 기존 로직 유지 (이슈1 원복)
    일마감 전이면 today_str=yesterday (S1 요약 + S2 hourly 모두 어제 기준)
v3.0 | 2026-04-08 | S5 영업일수 시트 컬럼 구조 전면 개편
  - 신규 컬럼: 일자|요일|계|SM|KM|LM(MVNO IN실적)|수동입력|AI예측(현재사용)|
               AI월초|AI1주차|AI2주차|AI3주차|AI4주차|실적기반|비고
  - MVNO IN 실적 (계/SM/KM/LM) 추가: 영업일수와 실제 시장 활동성 직접 비교
  - AI예측 컬럼 순서 변경: 현재사용(bw_ai_prev) 최우선 표시
  - bw_ai_w0(월초예측), bw_ai_w4(4주차) 컬럼 추가
  - 실적기반(bw_performance)을 마지막 컬럼으로 이동 (마감 후 채워지는 값)
  - 그룹 헤더 추가 (3행): 날짜/실적/수동입력/AI예측/실적기반 그룹 구분
  - 오차 감지 기준 완화: ±0.2 → ±0.15
v2.2 | 2026-04-07 | S1 일마감 요약 레이아웃 개선
  - 실적+비율+화살표를 1셀에 표시: "2,244 (19.6%) ↗️"
  - 점유율 별도 행 제거 → 당일/누적 각 1줄로 압축
  - 전일비교 화살표 7단계: ⏫⬆️↗️-↘️⬇️⏬ (점유율 ±0.1%p, 순증감 ±5건 기준)
  - 섹션 구조: MVNO IN / MNO Out / 순증감 / MVNO Out / SKT OUT
v2.1 | 2026-04-07 | 데이터 조회 버그 수정 + 시트명 변경
  - _load_month_daily(): __name__ 필터 → date 필드 필터로 변경 (데이터 없음 버그 수정)
  - _load_month_forecasts(): 동일하게 수정
  - S3 시트명: '월별 실적' → '일별 실적'
v2.0 | 2026-04-06 | 시트 전면 재구성 (S1~S6 6개 시트)
  - S1: 일마감 요약 (당일 실적 + 전일비교 + 월누적 + SKT OUT)
  - S2: 시간별 예측 (11~20시 예측 vs 실제 + 정확도%)
  - S3: 월별 실적 (날짜별 당일/누적 전체, 어제까지)
  - S4: 월마감 예측 추이 (날짜별 bw + SKT실적 + 저점/중앙/고점)
  - S5: 영업일수 (bw_manual/ai_prev/w1~w3/final)
  - S6: 예측 정확도 (날짜별 MAE 추이)
  - generate_report(): 통합 생성 함수 (일마감 자동발송 + 수동 조회 공용)
v1.0 | 2026-04-01 | 최초 작성
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from typing import Optional

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ── 색상 팔레트
_C = {
    'header':    'FF1F4E79',  # 진한 파랑
    'subhdr':    'FF2E75B6',  # 중간 파랑
    'section':   'FFD6E4F0',  # 연한 파랑
    'actual':    'FFFFD966',  # 노랑 (실제값)
    'good':      'FFE2EFDA',  # 연초록 (정확도 양호)
    'bad':       'FFFCE4D6',  # 연주황/빨강 (정확도 불량)
    'ai':        'FFE2EFDA',  # 연초록 (AI)
    'manual':    'FFFCE4D6',  # 연주황 (수동)
    'final':     'FFDEEBF7',  # 연파랑 (최종)
    'zero':      'FFF2F2F2',  # 회색 (영업0일)
    'white':     'FFFFFFFF',
    'lgray':     'FFF2F2F2',
    'today':     'FFFFF2CC',  # 연노랑 (오늘)
    'pos':       'FFE2EFDA',  # 양수
    'neg':       'FFFCE4D6',  # 음수
}


# ══════════════════════════════════════════════════════════════════
# DB / 데이터 조회 헬퍼
# ══════════════════════════════════════════════════════════════════

def _get_db():
    try:
        import firebase_admin
        from firebase_admin import credentials
        from google.cloud import firestore as fs
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault())
        return fs.Client(project='mvno-484509', database='mvno-data')
    except Exception as e:
        log.warning(f"Firestore 연결 실패: {e}")
        return None


def _load_today_hourly(date_str: str) -> list:
    db = _get_db()
    if not db:
        return []
    try:
        # ★ [v3.1] order_by 제거 (복합 인덱스 불필요) → Python에서 정렬
        docs = db.collection('ktoa_hourly').where('date', '==', date_str).stream()
        result = [d.to_dict() for d in docs]
        # collected_at 기준 정렬
        result.sort(key=lambda x: str(x.get('collected_at', '')))
        return result
    except Exception as e:
        log.error(f"hourly 조회 실패: {e}")
        return []


def _load_month_daily(year: int, month: int) -> dict:
    last = monthrange(year, month)[1]
    p1 = f"{year:04d}-{month:02d}-01"
    p2 = f"{year:04d}-{month:02d}-{last:02d}"
    db = _get_db()
    if not db:
        return {}
    try:
        # [수정] __name__ 필터 → date 필드 필터 (SDK 버전 호환성)
        docs = db.collection('ktoa_daily').where('date', '>=', p1).where('date', '<=', p2).stream()
        return {d.id: d.to_dict() for d in docs}
    except Exception as e:
        log.error(f"month_daily 조회 실패: {e}")
        return {}


def _load_month_migration(year: int, month: int) -> dict:
    """세종→고고 이관 월 데이터 조회. {date_str: {'daily':..,'cum':..}}"""
    try:
        import ktoa_firestore
        return ktoa_firestore.get_month_sejong_migration(year, month)
    except Exception as e:
        log.warning(f"세종이관 월 조회 실패: {e}")
        return {}


def _load_all_migration() -> dict:
    """세종→고고 이관 전체 이력 조회 (전체 누계 시트용). {date_str: payload}"""
    try:
        db = _get_db()
        if not db:
            return {}
        docs = db.collection('ktoa_daily_sejong_migration').stream()
        return {d.id: d.to_dict() for d in docs}
    except Exception as e:
        log.warning(f"세종이관 전체 조회 실패: {e}")
        return {}


def _load_month_19h_forecast(year: int, month: int) -> dict:
    """
    월 전체 날짜별 19시(마지막) hourly forecast 한 번에 조회
    → S4에서 날짜별 루프마다 Firestore 호출하지 않도록 미리 로드
    반환: {date_str: hourly_doc_dict}
    """
    last = monthrange(year, month)[1]
    p1 = f"{year:04d}-{month:02d}-01"
    p2 = f"{year:04d}-{month:02d}-{last:02d}"
    db = _get_db()
    if not db:
        return {}
    try:
        # 월 전체 hourly 한 번에 조회
        docs = (db.collection('ktoa_hourly')
                .where('date', '>=', p1)
                .where('date', '<=', p2)
                .stream())
        # 날짜별로 그룹핑 후 마지막 시간대(가장 큰 doc_id) 선택
        by_date = {}
        for doc in docs:
            d = doc.to_dict()
            date = d.get('date', doc.id[:10])
            # forecast 필드가 있는 문서만 (예측값 저장된 것)
            if not d.get('forecast_mno_out'):
                continue
            # 같은 날짜면 doc_id가 큰 것(최신)으로 교체
            if date not in by_date or doc.id > by_date[date]['_doc_id']:
                d['_doc_id'] = doc.id
                by_date[date] = d
        log.info(f"월 hourly forecast 로드: {len(by_date)}일치")
        return by_date
    except Exception as e:
        log.error(f"month_19h_forecast 조회 실패: {e}")
        return {}


def _load_month_forecasts(year: int, month: int) -> dict:
    last = monthrange(year, month)[1]
    p1 = f"{year:04d}-{month:02d}-01"
    p2 = f"{year:04d}-{month:02d}-{last:02d}"
    db = _get_db()
    if not db:
        return {}
    try:
        # [수정] __name__ 필터 → date 필드 필터
        docs = db.collection('ktoa_forecast').where('date', '>=', p1).where('date', '<=', p2).stream()
        return {d.id: d.to_dict() for d in docs}
    except Exception as e:
        return {}


def _parse_hour(ref_time: str) -> int:
    m = re.search(r'(\d+)시', ref_time or '')
    return int(m.group(1)) if m else -1


def _pct(a, b):
    return a / b * 100 if b else 0


def _sign_str(v):
    if v is None:
        return ''
    return f'+{v:,}' if v >= 0 else f'▲{abs(v):,}'


# ══════════════════════════════════════════════════════════════════
# 스타일 헬퍼
# ══════════════════════════════════════════════════════════════════

def _styles():
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    def fill(c):
        return PatternFill('solid', start_color=c, fgColor=c)

    def font(bold=False, size=9, color='FF000000', white=False):
        return Font(name='Arial', bold=bold, size=size,
                    color='FFFFFFFF' if white else color)

    def border():
        s = Side(style='thin', color='FF000000')
        return Border(left=s, right=s, top=s, bottom=s)

    def align(h='center', v='center', wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    return fill, font, border, align


# ══════════════════════════════════════════════════════════════════
# S1: 일마감 요약
# ══════════════════════════════════════════════════════════════════

def _trend_arrow_7(curr_pct: float, prev_pct: float, thr: float = 0.1,
                   streak: int = 1) -> str:
    """
    7단계 트렌드 화살표 (점유율 기준)
    streak: 연속 횟수 (1=1회, 2=2회, 3+=극단)
    """
    diff = curr_pct - prev_pct
    if abs(diff) < thr:
        return '-'
    up = diff > 0
    if streak >= 3:
        return '⏫' if up else '⏬'
    elif streak == 2:
        return '⬆️' if up else '⬇️'
    else:
        return '↗️' if up else '↘️'


def _trend_arrow_net(curr: int, prev: int, thr: int = 5,
                     streak: int = 1) -> str:
    """순증감 7단계 화살표 (건수 기준)"""
    diff = curr - prev
    if abs(diff) < thr:
        return '-'
    up = diff > 0
    if streak >= 3:
        return '⏫' if up else '⏬'
    elif streak == 2:
        return '⬆️' if up else '⬇️'
    else:
        return '↗️' if up else '↘️'


# ══════════════════════════════════════════════════════════════════
# S0: 월마감 요약 (월마감 확정 엑셀에서만 사용)
# ══════════════════════════════════════════════════════════════════

def _build_s0_month_summary(wb, year: int, month: int, date_str: str):
    """
    [v3.12] 월마감 요약 시트 - '일마감 요약'의 월 전체 버전.
    ktoa_context_period_builder._aggregate_records / _get_goals 재사용.
    generate_month_closing_report에서만 호출 (맨 앞 시트로 삽입).
    """
    fill, font, border, align = _styles()

    try:
        from ktoa_context_period_builder import _collect_daily_records, _aggregate_records, _get_goals
    except Exception as e:
        log.warning(f"S0 월마감 요약: period_builder import 실패 (스킵): {e}")
        return

    last_day = monthrange(year, month)[1]
    start_str = f"{year:04d}-{month:02d}-01"
    end_str   = f"{year:04d}-{month:02d}-{last_day:02d}"

    try:
        records = _collect_daily_records(start_str, end_str)
        agg = _aggregate_records(records) if records else {}
    except Exception as e:
        log.warning(f"S0 월마감 요약: 데이터 집계 실패 (스킵): {e}")
        agg = {}

    if not agg:
        log.warning(f"S0 월마감 요약: {year}-{month:02d} 집계 데이터 없음 → 시트 스킵")
        return

    try:
        t_out_goal, sm_net_goal, sm_ms_goal = _get_goals(year, month)
        sm_net_goal_val = sm_net_goal if sm_net_goal is not None else -5000
    except Exception:
        t_out_goal, sm_net_goal_val, sm_ms_goal = 37000, -5000, 19.0

    # 새 시트를 맨 앞에 생성 (기존 active 시트보다 먼저 오도록 index=0)
    ws = wb.create_sheet('월마감 요약', 0)

    for col, w in [('A', 12), ('B', 18), ('C', 18), ('D', 18), ('E', 16), ('F', 22)]:
        ws.column_dimensions[col].width = w

    r = 1

    def _hdr(row, text, n_cols=6):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        ws.row_dimensions[row].height = 22
        c = ws.cell(row=row, column=1, value=text)
        c.font = font(bold=True, size=12, white=True)
        c.fill = fill(_C['header'])
        c.alignment = align()
        c.border = border()
        for col in range(2, n_cols + 1):
            ws.cell(row=row, column=col).fill = fill(_C['header'])
            ws.cell(row=row, column=col).border = border()

    def _sec_hdr(row, text, n_cols=6):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        ws.row_dimensions[row].height = 16
        c = ws.cell(row=row, column=1, value=text)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.alignment = align('left')
        c.border = border()
        for col in range(2, n_cols + 1):
            ws.cell(row=row, column=col).fill = fill(_C['subhdr'])
            ws.cell(row=row, column=col).border = border()

    def _row(row, label, value, note='', bold=False, val_fill=None, num_fmt=None):
        ws.row_dimensions[row].height = 16
        c = ws.cell(row=row, column=1, value=label)
        c.font = font(bold=bold, size=9)
        c.fill = fill(_C['white'])
        c.alignment = align()
        c.border = border()

        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        c2 = ws.cell(row=row, column=2, value=value)
        c2.font = font(bold=bold, size=10)
        c2.fill = fill(val_fill or _C['white'])
        c2.alignment = align('right')
        c2.border = border()
        if num_fmt and isinstance(value, (int, float)):
            c2.number_format = num_fmt
        for col in (3, 4):
            ws.cell(row=row, column=col).fill = fill(val_fill or _C['white'])
            ws.cell(row=row, column=col).border = border()

        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=6)
        c3 = ws.cell(row=row, column=5, value=note)
        c3.font = font(size=9)
        c3.fill = fill(_C['white'])
        c3.alignment = align('left')
        c3.border = border()
        ws.cell(row=row, column=6).fill = fill(_C['white'])
        ws.cell(row=row, column=6).border = border()

    _hdr(r, f'■ {year}년 {month}월 월마감 요약 (실적: {agg["start"]} ~ {agg["end"]}, 영업일수 {agg["total_bw"]})')
    r += 1

    # ── T-Out
    _sec_hdr(r, '■ T Out (SKT MNO→MVNO) ★목표지표 1순위')
    r += 1
    on_track = '달성 ✅' if agg['t_out_sum'] <= t_out_goal else '목표 초과 ⚠️'
    _row(r, '월 누적 T-Out', agg['t_out_sum'],
         f"목표 {t_out_goal:,}건 이하 → {on_track}", bold=True,
         val_fill=_C['good'] if agg['t_out_sum'] <= t_out_goal else _C['bad'],
         num_fmt='#,##0')
    r += 1
    _row(r, '영업일수 일평균', agg['avg_t_out'], '', num_fmt='#,##0')
    r += 1
    if agg.get('fc_low'):
        track = '달성 가능 ✅' if agg.get('fc_on_track') else '목표 초과 위험 ⚠️'
        _row(r, '월마감 예측(DB)', f"{agg['fc_low']:,}~{agg['fc_mid']:,}건", track)
        r += 1

    # ── SM 순증감
    _sec_hdr(r, '■ SM 순증감 ★목표지표 2순위')
    r += 1
    sm_net_ok = agg['sm_net_sum'] >= sm_net_goal_val if sm_net_goal_val < 0 else agg['sm_net_sum'] <= sm_net_goal_val
    _row(r, '월 누적 순증감', agg['sm_net_sum'],
         f"목표 {sm_net_goal_val:,}건 이내 → {'달성 ✅' if sm_net_ok else '목표 초과 ⚠️'}",
         bold=True, val_fill=_C['good'] if sm_net_ok else _C['bad'], num_fmt='#,##0')
    r += 1
    _row(r, '영업일수 일평균', agg['avg_sm_net'], '', num_fmt='#,##0')
    r += 1

    # ── MVNO IN
    _sec_hdr(r, '■ MVNO IN (신규)')
    r += 1
    _row(r, 'SM / KM / LM / 계',
         f"{agg['sm_in_sum']:,} / {agg['km_in_sum']:,} / {agg['lm_in_sum']:,} / {agg['mvno_in_sum']:,}", '')
    r += 1
    ms_ok = agg['sm_in_ms'] >= sm_ms_goal
    _row(r, 'SM M/S', f"{agg['sm_in_ms']:.1f}%",
         f"목표 {sm_ms_goal:.0f}% → {'달성 ✅' if ms_ok else '미달 ⚠️'}",
         val_fill=_C['good'] if ms_ok else _C['bad'])
    r += 1

    # ── MVNO OUT
    _sec_hdr(r, '■ MVNO OUT (해지)')
    r += 1
    _row(r, 'SM / KM / LM / 계',
         f"{agg['sm_out_sum']:,} / {agg['km_out_sum']:,} / {agg['lm_out_sum']:,} / {agg['mvno_out_sum']:,}", '')
    r += 1
    BASE_SM_OUT = 19.4
    diff_out = agg['sm_out_ms'] - BASE_SM_OUT
    _row(r, 'SM 해지 M/S', f"{agg['sm_out_ms']:.1f}%",
         f"12월 기준선 {BASE_SM_OUT}% 대비 {diff_out:+.1f}%p {'악화 ⚠️' if diff_out > 0 else '개선 ✅'}")
    r += 1

    # ── 순증감 제로섬
    _sec_hdr(r, '■ 순증감 (제로섬 검증)')
    r += 1
    _row(r, 'MVNO 순증감 (SM/KM/LM/계)',
         f"{agg['sm_net_sum']:+,} / {agg['km_net_sum']:+,} / {agg['lm_net_sum']:+,} / {agg['mvno_net_sum']:+,}", '')
    r += 1
    _row(r, 'MNO 순증감 (S/K/L/계)',
         f"{agg['s_net_sum']:+,} / {agg['k_net_sum']:+,} / {agg['l_net_sum']:+,} / {agg['mno_net_sum']:+,}", '')
    r += 1
    zero = agg['mvno_net_sum'] + agg['mno_net_sum']
    _row(r, '제로섬 검증', f"{zero:+,}건",
         '✅ 정상' if abs(zero) <= 10 else '⚠️ 확인 필요',
         val_fill=_C['good'] if abs(zero) <= 10 else _C['bad'])
    r += 1

    # ── 군별 포지션
    _sec_hdr(r, '■ 군별 합산 포지션')
    r += 1
    _row(r, 'S군(SKT MNO+SM)', f"{agg['s_gun']:+,}건", '')
    r += 1
    _row(r, 'K군(KT MNO+KM)', f"{agg['k_gun']:+,}건", '')
    r += 1
    _row(r, 'L군(LGU MNO+LM)', f"{agg['l_gun']:+,}건", '')
    r += 1

    ws.freeze_panes = 'A2'


def _build_s1_summary(wb, date_str: str, daily: dict, prev_daily: dict,
                      year: int, month: int):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    fill, font, border, align = _styles()

    ws = wb.active
    ws.title = '일마감 요약'

    dt = datetime.strptime(date_str, '%Y-%m-%d')
    wd = ['월', '화', '수', '목', '금', '토', '일'][dt.weekday()]

    # 당일
    mi   = daily.get('mvno_in',    {})
    mo   = daily.get('mvno_out',   {})
    mno  = daily.get('mno_out',    {})
    net  = daily.get('net_change', {})
    cmi  = daily.get('cum_mvno_in',  {})
    cmo  = daily.get('cum_mvno_out', {})
    cmno = daily.get('cum_mno_out',  {})
    cnet = daily.get('cum_net',      {})

    # 전일
    has_prev = bool(prev_daily)
    pmi  = prev_daily.get('mvno_in',    {}) if has_prev else {}
    pmno = prev_daily.get('mno_out',    {}) if has_prev else {}
    pmo  = prev_daily.get('mvno_out',   {}) if has_prev else {}
    pnet = prev_daily.get('net_change', {}) if has_prev else {}

    def _arr_pct(curr_d, prev_d, key, thr=0.1):
        """점유율 기준 화살표"""
        if not prev_d:
            return ''
        c = _pct(curr_d.get(key, 0), curr_d.get('계', 1) or 1)
        p = _pct(prev_d.get(key, 0), prev_d.get('계', 1) or 1)
        return _trend_arrow_7(c, p, thr)

    def _arr_net(curr_d, prev_d, key, thr=5):
        """순증감 기준 화살표"""
        if not prev_d:
            return ''
        return _trend_arrow_net(
            curr_d.get(key, 0) or 0,
            prev_d.get(key, 0) or 0, thr)

    # SKT OUT
    try:
        from ktoa_telegram import get_tout_goal, calc_remaining_days
        tout_goal = get_tout_goal(year, month)
    except Exception:
        tout_goal = 0

    cum_tout = cmno.get('S', 0) or 0
    remaining_cum = max(tout_goal - cum_tout, 0)
    try:
        remaining_bw = calc_remaining_days(year, month, dt.day)
    except Exception:
        remaining_bw = 0
    remaining_avg = int(remaining_cum / remaining_bw) if remaining_bw > 0 else 0

    # ── 열 너비: A(항목) B(SM) C(KM) D(LM) E(계)
    for col, w in [('A', 10), ('B', 18), ('C', 18), ('D', 18), ('E', 14)]:
        ws.column_dimensions[col].width = w

    r = 1

    def _hdr(row, text, n_cols=5):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        ws.row_dimensions[row].height = 22
        c = ws.cell(row=row, column=1, value=text)
        c.font = font(bold=True, size=12, white=True)
        c.fill = fill(_C['header'])
        c.alignment = align()
        c.border = border()

    def _sec_hdr(row, text, n_cols=5):
        """섹션 헤더 (파랑 배경)"""
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        ws.row_dimensions[row].height = 16
        c = ws.cell(row=row, column=1, value=text)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.alignment = align('left')
        c.border = border()
        for col in range(2, n_cols + 1):
            ws.cell(row=row, column=col).fill = fill(_C['subhdr'])
            ws.cell(row=row, column=col).border = border()

    def _col_hdr(row):
        """컬럼 헤더: 항목 | SM | KM | LM | 계"""
        ws.row_dimensions[row].height = 16
        for col, val in [(1, '항목'), (2, 'SM'), (3, 'KM'), (4, 'LM'), (5, '계')]:
            c = ws.cell(row=row, column=col, value=val)
            c.font = font(bold=True, size=9, white=True)
            c.fill = fill(_C['subhdr'])
            c.alignment = align()
            c.border = border()

    def _data_row(row, label, d, keys, prev_d=None, arrow_fn=None,
                  val_fill=None, bold=False, net_mode=False):
        """
        데이터 행: 항목 | SM: 값(비율%) 화살표 | KM | LM | 계
        net_mode=True: 비율 대신 부호(▲/+)
        """
        ws.row_dimensions[row].height = 16
        total = d.get('계', 0) or 0
        cum_total = total  # 계 칸용

        # A: 항목명
        c = ws.cell(row=row, column=1, value=label)
        c.font = font(bold=bold, size=9)
        c.fill = fill(val_fill or _C['white'])
        c.alignment = align()
        c.border = border()

        # B~D: SM/KM/LM
        for col, k in zip([2, 3, 4], keys):
            val = d.get(k, 0) or 0
            if net_mode:
                # 순증감: ▲190 ↗️ 형식
                sign = '▲' if val < 0 else '+'
                val_str = f'{sign}{abs(val):,}'
                arr = arrow_fn(k) if arrow_fn else ''
                cell_val = f'{val_str} {arr}'.strip() if arr else val_str
            else:
                pct = _pct(val, total) if total else 0
                arr = arrow_fn(k) if arrow_fn else ''
                cell_val = f'{val:,} ({pct:.1f}%) {arr}'.strip() if arr else f'{val:,} ({pct:.1f}%)'

            c = ws.cell(row=row, column=col, value=cell_val)
            c.font = font(bold=bold, size=9)
            c.fill = fill(val_fill or _C['white'])
            c.alignment = align('right')
            c.border = border()

        # E: 계
        c = ws.cell(row=row, column=5,
                    value=f'{cum_total:,}' if not net_mode else
                          (f'▲{abs(cum_total):,}' if cum_total < 0 else f'+{cum_total:,}'))
        c.font = font(bold=True, size=9)
        c.fill = fill(val_fill or _C['white'])
        c.alignment = align('right')
        c.border = border()

    # ══ 타이틀 ══
    _hdr(r, f'■ 일마감 요약 — {date_str}({wd})')
    r += 1

    # ══ MVNO IN ══
    _sec_hdr(r, '◎ MVNO IN')
    r += 1
    _col_hdr(r)
    r += 1

    # ── 전주/전일 영업일 탐색 (휴무일 건너뜀)
    from bw_engine import is_zero_day

    def _find_prev_bizday(base_dt, days_back_start, max_search=14):
        """base_dt 기준 days_back_start일 전부터 역방향으로 첫 영업일 탐색"""
        db = _get_db()
        for i in range(days_back_start, days_back_start + max_search):
            prev_dt = base_dt - timedelta(days=i)
            ds = prev_dt.strftime('%Y-%m-%d')
            if is_zero_day(ds):
                continue
            doc = db.collection('ktoa_daily').document(ds).get()
            if doc.exists and doc.to_dict().get('mvno_in'):
                return ds, doc.to_dict()
        return None, {}

    # 전일 (휴무일이면 직전 영업일)
    prev_day_str, prev_day_data = _find_prev_bizday(dt, 1)
    prev_day_label = f'전일({datetime.strptime(prev_day_str, "%Y-%m-%d").strftime("%-m/%-d")})' if prev_day_str else '전일(-)'

    # 전주 동요일 (7일 전 영업일 없으면 6~8일 탐색)
    prev_week_str = (dt - timedelta(days=7)).strftime('%Y-%m-%d')
    if is_zero_day(prev_week_str):
        # 동요일이 휴무이면 전후 1일씩 탐색
        for delta in [1, -1, 2, -2]:
            candidate = (dt - timedelta(days=7-delta)).strftime('%Y-%m-%d')
            if not is_zero_day(candidate):
                prev_week_str = candidate
                break
    try:
        db2 = _get_db()
        pw_doc = db2.collection('ktoa_daily').document(prev_week_str).get()
        pw_full = pw_doc.to_dict() if pw_doc.exists else {}
    except Exception:
        pw_full = {}

    pw_dt = datetime.strptime(prev_week_str, '%Y-%m-%d')
    prev_week_label = f'전주({pw_dt.strftime("%-m/%-d")})'

    def _ref_row(row, label, d, keys, ref_fill=None):
        """전주/전일 참고 행 (회색 폰트, 작은 글씨)"""
        ws.row_dimensions[row].height = 14
        total = d.get('계', 0) or 0
        c = ws.cell(row=row, column=1, value=label)
        c.font = font(size=8, color='FF666666')
        c.fill = fill(ref_fill or _C['lgray'])
        c.alignment = align()
        c.border = border()
        for col, k in zip([2, 3, 4], keys):
            val = d.get(k, 0) or 0
            pct = _pct(val, total) if total else 0
            cell_val = f'{val:,} ({pct:.1f}%)' if val else '-'
            c = ws.cell(row=row, column=col, value=cell_val)
            c.font = font(size=8, color='FF666666')
            c.fill = fill(ref_fill or _C['lgray'])
            c.alignment = align('right')
            c.border = border()
        c = ws.cell(row=row, column=5, value=f'{total:,}' if total else '-')
        c.font = font(size=8, color='FF666666')
        c.fill = fill(ref_fill or _C['lgray'])
        c.alignment = align('right')
        c.border = border()

    # MVNO IN 전주/전일
    _ref_row(r, prev_week_label, pw_full.get('mvno_in', {}), ['SM', 'KM', 'LM'])
    r += 1
    _ref_row(r, prev_day_label, prev_day_data.get('mvno_in', {}), ['SM', 'KM', 'LM'])
    r += 1

    _data_row(r, '당일', mi, ['SM', 'KM', 'LM'],
              arrow_fn=lambda k: _arr_pct(mi, pmi, k),
              val_fill=_C['actual'], bold=True)
    r += 1
    _data_row(r, '누적', cmi, ['SM', 'KM', 'LM'], bold=False)
    r += 1

    # ══ MNO Out ══
    _sec_hdr(r, '◎ MNO Out')
    r += 1
    _col_hdr_mno(ws, r, font, fill, border, align, _C)
    r += 1

    # MNO Out 전주/전일
    _ref_row(r, prev_week_label, pw_full.get('mno_out', {}), ['S', 'K', 'L'])
    r += 1
    _ref_row(r, prev_day_label, prev_day_data.get('mno_out', {}), ['S', 'K', 'L'])
    r += 1

    mno_keys = ['S', 'K', 'L']
    _data_row(r, '당일', mno, mno_keys,
              arrow_fn=lambda k: _arr_pct(mno, pmno, k),
              val_fill=_C['actual'], bold=True)
    r += 1
    _data_row(r, '누적', cmno, mno_keys, bold=False)
    r += 1

    # ══ 순증감 ══
    _sec_hdr(r, '◎ 순증감')
    r += 1
    _col_hdr(r)
    r += 1

    # 순증감 전주/전일
    _ref_row(r, prev_week_label, pw_full.get('net_change', {}), ['SM', 'KM', 'LM'])
    r += 1
    _ref_row(r, prev_day_label, prev_day_data.get('net_change', {}), ['SM', 'KM', 'LM'])
    r += 1

    _data_row(r, '당일', net, ['SM', 'KM', 'LM'],
              arrow_fn=lambda k: _arr_net(net, pnet, k),
              val_fill=_C['actual'], bold=True, net_mode=True)
    r += 1
    _data_row(r, '누적', cnet, ['SM', 'KM', 'LM'],
              bold=False, net_mode=True)
    r += 1

    # ══ MVNO Out ══
    _sec_hdr(r, '◎ MVNO Out (MNP 해지)')
    r += 1
    _col_hdr(r)
    r += 1

    # MVNO Out 전주/전일
    _ref_row(r, prev_week_label, pw_full.get('mvno_out', {}), ['SM', 'KM', 'LM'])
    r += 1
    _ref_row(r, prev_day_label, prev_day_data.get('mvno_out', {}), ['SM', 'KM', 'LM'])
    r += 1

    _data_row(r, '당일', mo, ['SM', 'KM', 'LM'],
              arrow_fn=lambda k: _arr_pct(mo, pmo, k),
              val_fill=_C['actual'], bold=True)
    r += 1
    _data_row(r, '누적', cmo, ['SM', 'KM', 'LM'], bold=False)
    r += 1

    # ══ SKT OUT ══
    _sec_hdr(r, '◎ SKT OUT')
    r += 1

    # 잔여 영업일수(bw_final 합계) 계산
    try:
        from bw_engine import calc_remaining_bw
        remaining_bw_sum = calc_remaining_bw(year, month, dt.day)
    except Exception:
        remaining_bw_sum = remaining_bw

    skt_rows = [
        ('목표',                    f'{tout_goal:,}' if tout_goal else '-'),
        ('현누적(SKT)',              f'{cum_tout:,}'),
        ('잔여누적',                 f'{remaining_cum:,}'),
        ('잔여 영업일\n(bw_final)', f'{remaining_bw_sum:.2f}일' if remaining_bw_sum else '00일'),
        ('잔여 일평균',              f'{remaining_avg:,}'),
    ]
    for label, val_str in skt_rows:
        ws.row_dimensions[r].height = 18
        # A: 항목
        c1 = ws.cell(row=r, column=1, value=label)
        c1.font = font(size=9)
        c1.fill = fill(_C['white'])
        c1.alignment = align(wrap=True)
        c1.border = border()
        # B: 값 (병합 없이 B열만)
        c2 = ws.cell(row=r, column=2, value=val_str)
        c2.font = font(bold=True, size=9)
        c2.fill = fill(_C['actual'])
        c2.alignment = align('left')   # 좌측 정렬 → 숫자 항목 바로 옆
        c2.border = border()
        # C~E: 빈 칸 (테두리만)
        for col in range(3, 6):
            c = ws.cell(row=r, column=col)
            c.fill = fill(_C['actual'])
            c.border = border()
        r += 1

    ws.freeze_panes = 'A2'


def _col_hdr_mno(ws, row, font, fill, border, align, C):
    """MNO Out용 컬럼 헤더: S/K/L"""
    ws.row_dimensions[row].height = 16
    for col, val in [(1, '항목'), (2, 'S(SKT)'), (3, 'K(KT)'), (4, 'L(LGU+)'), (5, '계')]:
        c = ws.cell(row=row, column=col, value=val)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(C['subhdr'])
        c.alignment = align()
        c.border = border()



# ══════════════════════════════════════════════════════════════════
# S2: 시간별 예측 vs 실제
# ══════════════════════════════════════════════════════════════════

def _build_s2_hourly(wb, date_str: str, daily: dict, hourly_docs: list,
                     sheet_name: str = '시간별 예측'):
    """
    [v3.0] 시간별 예측 vs 실제 비교 시트
    항목: MVNO IN / MNO Out / 순증감 / MVNO Out (각 3사 + 계)
    각 시간대: 실제값 행 + 예측값 행 (forecast_* 필드)
    예측 정확도: 20시 예측 vs 실제마감 비교
    """
    from openpyxl.utils import get_column_letter
    fill, font, border, align = _styles()

    ws = wb.create_sheet(sheet_name)
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    wd = ['월', '화', '수', '목', '금', '토', '일'][dt.weekday()]

    HOURS = list(range(11, 20))  # 11~19시 (20시는 실제마감 컬럼과 동일하므로 제외)
    N_HOURS = len(HOURS)

    # ── 컬럼 구조
    # A: 구분, B: 항목, C: 실/예, D~M: 11~20시, N: 20시실제마감, O: 정확도(전체), P: 11~13시, Q: 14~16시, R: 17~19시
    COL_SEC   = 1   # 구분 (MVNO IN 등)
    COL_ITEM  = 2   # 항목 (SM/KM/LM/계)
    COL_TYPE  = 3   # 실/예
    COL_START = 4   # 11시 시작
    COL_ACT   = COL_START + N_HOURS      # 20시 실제마감
    COL_ACC   = COL_ACT + 1             # 예측정확도(전체)
    COL_ACC_A = COL_ACC + 1             # 정확도(11~13시)
    COL_ACC_B = COL_ACC + 2             # 정확도(14~16시)
    COL_ACC_C = COL_ACC + 3             # 정확도(17~19시)
    TOTAL_COLS = COL_ACC_C

    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 7
    ws.column_dimensions['C'].width = 5
    for i in range(N_HOURS):
        ws.column_dimensions[get_column_letter(COL_START + i)].width = 9
    ws.column_dimensions[get_column_letter(COL_ACT)].width = 12
    ws.column_dimensions[get_column_letter(COL_ACC)].width = 10
    ws.column_dimensions[get_column_letter(COL_ACC_A)].width = 11
    ws.column_dimensions[get_column_letter(COL_ACC_B)].width = 11
    ws.column_dimensions[get_column_letter(COL_ACC_C)].width = 11

    # hourly_docs를 시간별로 인덱싱
    # [v3.2] 정시(minute=0) 문서 우선 — 10분단위가 정시 슬롯 덮어쓰기 방지
    # 1단계: 정시 문서만 먼저 등록
    hourly_by_hour = {}
    for hd in sorted(hourly_docs, key=lambda x: str(x.get('collected_at', ''))):
        h = hd.get('forecast_hour')
        m = hd.get('forecast_minute', None)
        if h is None:
            h = _parse_hour(hd.get('reference_time', ''))
        if not isinstance(h, int) or not (11 <= h <= 20):
            continue
        # 정시(minute=0) 문서만 1단계 등록
        if m == 0:
            hourly_by_hour[h] = hd

    # 2단계: 정시 문서 없는 시간대만 10분단위로 채움 (최신값)
    for hd in sorted(hourly_docs, key=lambda x: str(x.get('collected_at', ''))):
        h = hd.get('forecast_hour')
        m = hd.get('forecast_minute', None)
        if h is None:
            h = _parse_hour(hd.get('reference_time', ''))
        if not isinstance(h, int) or not (11 <= h <= 20):
            continue
        if h not in hourly_by_hour:  # 정시 문서 없을 때만 사용
            hourly_by_hour[h] = hd

    # [수정 20260930, 되돌림] 시트 생성 시점에 hourly_by_hour의 모든 시간×8항목을
    # get_field_daily_forecast()로 매번 재계산하도록 했었는데, 시간당 최대 80회
    # DB조회 × 9시간 × 8항목 = 수천 건의 Firestore 조회가 발생해 리포트 생성이
    # 20분 넘게 걸리는(사실상 타임아웃) 심각한 성능 문제가 있어서 되돌림.
    # 대신 forecast_engine.predict_hourly()가 정시(minute==0)마다 저장 시점에
    # 이미 같은 요일필터+완료율곡선 방식으로 계산해서 ktoa_hourly에 저장하도록
    # 바꿨으므로, 이 시트는 그 저장값을 그대로 읽기만 하면 자동으로 통일됨
    # (배포 이후 시점의 정시 데이터부터 적용, 과거 데이터는 그대로 옛날 값).
    #
    # ★ [v3.1] 이슈2: 순증감 예측값 = forecast_mvno_in - forecast_mvno_out 계산
    # forecast_net 필드가 없으면 두 필드로 직접 계산
    for h, hd in hourly_by_hour.items():
        if not hd.get('forecast_net'):
            fin  = hd.get('forecast_mvno_in', {}) or {}
            fout = hd.get('forecast_mvno_out', {}) or {}
            hd['forecast_net'] = {
                k: (fin.get(k, 0) or 0) - (fout.get(k, 0) or 0)
                for k in set(list(fin.keys()) + list(fout.keys()))
            }

    # ── 실제 마감값
    actual = {
        'mvno_in':  daily.get('mvno_in',    {}),
        'mno_out':  daily.get('mno_out',    {}),
        'net':      daily.get('net_change', {}),
        'mvno_out': daily.get('mvno_out',   {}),
    }

    # ── 섹션 정의
    # (섹션명, 필드명, 예측필드명, [(항목명, 키)])
    SECTIONS = [
        ('MVNO IN',  'mvno_in',  'forecast_mvno_in',  [('SM','SM'),('KM','KM'),('LM','LM'),('계','계')]),
        ('MNO Out',  'mno_out',  'forecast_mno_out',  [('S','S'),  ('K','K'),  ('L','L'),  ('계','계')]),
        ('순증감',   'net_change','forecast_net',      [('SM','SM'),('KM','KM'),('LM','LM'),('계','계')]),
        ('MVNO Out', 'mvno_out', 'forecast_mvno_out', [('SM','SM'),('KM','KM'),('LM','LM'),('계','계')]),
    ]

    # ── 타이틀
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=TOTAL_COLS)
    ws.row_dimensions[1].height = 22
    t = ws.cell(row=1, column=1, value=f'시간별 예측/실제 비교 — {date_str}({wd})')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()

    # ── 헤더
    ws.row_dimensions[2].height = 18
    for col in range(1, TOTAL_COLS + 1):
        c = ws.cell(row=2, column=col)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.font = font(bold=True, size=9, white=True)
        c.alignment = align(wrap=True)

    ws.cell(row=2, column=COL_SEC,  value='구분')
    ws.cell(row=2, column=COL_ITEM, value='항목')
    ws.cell(row=2, column=COL_TYPE, value='실/예')
    ws.cell(row=2, column=COL_ACT, value='20시\n실제마감')
    for i, h in enumerate(HOURS):
        ws.cell(row=2, column=COL_START + i, value=f'{h}시')
    ws.cell(row=2, column=COL_ACC,   value='정확도\n(전체)')
    ws.cell(row=2, column=COL_ACC_A, value='정확도\n(11~13시)')
    ws.cell(row=2, column=COL_ACC_B, value='정확도\n(14~16시)')
    ws.cell(row=2, column=COL_ACC_C, value='정확도\n(17~19시)')
    for col in [COL_ACC_A, COL_ACC_B, COL_ACC_C]:
        c = ws.cell(row=2, column=col)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.font = font(bold=True, size=9, white=True)
        c.alignment = align(wrap=True)

    # ── 색상 상수 (정확도용)
    from openpyxl.styles import PatternFill as _PF
    _ROW_BG    = 'FFF0F4FA'  # D~L 시간별 통일 배경 (연한 회청색)
    _ROW_BG20  = _C['actual']  # 20시 실제마감 배경 (노랑)
    _CLR_GOOD  = ('FF1F6B3B', 'FFFFFFFF')  # 95%↑ 진초록+흰글자
    _CLR_OK    = ('FF2E75B6', 'FFFFFFFF')  # 90%↑ 진파랑+흰글자
    _CLR_SOSO  = ('FF808080', 'FFFFFFFF')  # 90%미만 회색+흰글자

    def _acc_fill_font(acc_ratio):
        """정확도 비율 → (fill, font_color)"""
        if acc_ratio >= 0.95:
            return _PF(fill_type='solid', fgColor=_CLR_GOOD[0]), _CLR_GOOD[1]
        elif acc_ratio >= 0.90:
            return _PF(fill_type='solid', fgColor=_CLR_OK[0]), _CLR_OK[1]
        else:
            return _PF(fill_type='solid', fgColor=_CLR_SOSO[0]), _CLR_SOSO[1]

    def _num_cell(ws, row, col, val, fc, bold=False, fmt='#,##0'):
        c = ws.cell(row=row, column=col, value=val if val else None)
        c.font = font(bold=bold, size=9)
        c.fill = fill(fc)
        c.alignment = align('right')
        c.border = border()
        if val is not None and val != 0:
            c.number_format = fmt
        return c

    cur_row = 3
    for sec_name, field, fc_field, items in SECTIONS:
        sec_start = cur_row

        for item_name, key in items:
            is_total = (item_name in ['계'])
            is_neg_possible = (sec_name == '순증감')
            fmt_num = '+#,##0;-#,##0;0' if is_neg_possible else '#,##0'

            # ── 실제값 행 (act_row)
            ws.row_dimensions[cur_row].height = 15
            for col in [COL_ITEM, COL_TYPE] + list(range(COL_START, COL_ACT+1)) + [COL_ACC, COL_ACC_A, COL_ACC_B, COL_ACC_C]:
                ws.cell(row=cur_row, column=col).fill = fill(_C['white'])
                ws.cell(row=cur_row, column=col).border = border()

            ws.cell(row=cur_row, column=COL_ITEM, value=item_name)
            ws.cell(row=cur_row, column=COL_ITEM).font = font(bold=is_total, size=9)
            ws.cell(row=cur_row, column=COL_ITEM).alignment = align()

            c_type = ws.cell(row=cur_row, column=COL_TYPE, value='실')
            c_type.font = font(size=8, bold=True, color='FF2E75B6')
            c_type.alignment = align()

            for i, h in enumerate(HOURS):
                hd = hourly_by_hour.get(h)
                val = hd.get(field, {}).get(key) if hd else None
                # [수정1] D~L 배경 통일 (20시만 노랑)
                bg = _ROW_BG20 if h == 20 else _ROW_BG
                _num_cell(ws, cur_row, COL_START + i, val, bg, bold=(h==20), fmt=fmt_num)

            # 실제마감
            act_val = daily.get('net_change', {}).get(key, 0) if field == 'net_change' \
                      else actual.get(field if field != 'net_change' else 'net', {}).get(key, 0)
            _num_cell(ws, cur_row, COL_ACT, act_val or None, _C['actual'],
                      bold=True, fmt=fmt_num)

            act_row = cur_row

            # ── [수정2] 정확도 4개 컬럼 미리 계산 (실 행에 표시하기 위해)
            # [수정 20260930] 기존엔 "예측값들을 먼저 평균→실제와 비교"라서
            # 어떤 시간은 과대·어떤 시간은 과소예측이면 평균 과정에서 서로
            # 상쇄돼 실제보다 정확해 보이는 문제가 있었음(사장님 지적: "컸다작았다
            # 하면 정확도가 좋아지잖아"). "시간대별로 먼저 정확도를 구하고 그걸
            # 평균"하는 방식으로 변경 + 0% 미만으로 안 내려가게 클램프.
            act_col = get_column_letter(COL_ACT)
            fc_key = key

            # 전체: 시간대별 정확도(클램프 0~100%) 리스트
            all_accs = []
            for h in HOURS:
                hd = hourly_by_hour.get(h)
                pv = hd.get(fc_field, {}).get(fc_key) if hd else None
                if pv and act_val and act_val != 0:
                    all_accs.append(max(0.0, 1 - abs(pv - act_val) / abs(act_val)))

            # 구간별: 시간대별 정확도 리스트
            seg_acc_map = {}  # {(i_start, i_end): [acc_ratios]}
            for i_start, i_end in [(0,2),(3,5),(6,8)]:
                seg_accs = []
                for si in range(i_start, i_end + 1):
                    hd = hourly_by_hour.get(HOURS[si])
                    sv = hd.get(fc_field, {}).get(fc_key) if hd else None
                    if sv and act_val and act_val != 0:
                        seg_accs.append(max(0.0, 1 - abs(sv - act_val) / abs(act_val)))
                seg_acc_map[(i_start, i_end)] = seg_accs

            cur_row += 1

            # ── 예측값 행 (est_row)
            ws.row_dimensions[cur_row].height = 14
            for col in [COL_ITEM, COL_TYPE] + list(range(COL_START, COL_ACT+1)) + [COL_ACC, COL_ACC_A, COL_ACC_B, COL_ACC_C]:
                ws.cell(row=cur_row, column=col).fill = fill(_ROW_BG)
                ws.cell(row=cur_row, column=col).border = border()

            ws.cell(row=cur_row, column=COL_ITEM).font = font(size=9)
            ws.cell(row=cur_row, column=COL_ITEM).alignment = align()

            c_type2 = ws.cell(row=cur_row, column=COL_TYPE, value='예')
            c_type2.font = font(size=8, bold=True, color='FF538135')
            c_type2.alignment = align()

            for i, h in enumerate(HOURS):
                hd = hourly_by_hour.get(h)
                fc_val = hd.get(fc_field, {}).get(fc_key) if hd else None
                _num_cell(ws, cur_row, COL_START + i, fc_val, _ROW_BG, fmt=fmt_num)

            ws.cell(row=cur_row, column=COL_ACT).fill = fill(_ROW_BG)

            est_row = cur_row
            cur_row += 1

            # ── % 행 (시간별 정확도)
            ws.row_dimensions[cur_row].height = 15
            for col in [COL_ITEM, COL_TYPE] + list(range(COL_START, TOTAL_COLS+1)):
                ws.cell(row=cur_row, column=col).fill = fill(_ROW_BG)
                ws.cell(row=cur_row, column=col).border = border()

            ws.cell(row=cur_row, column=COL_ITEM).font = font(size=9)
            ws.cell(row=cur_row, column=COL_ITEM).alignment = align()

            c_type3 = ws.cell(row=cur_row, column=COL_TYPE, value='%')
            c_type3.font = font(size=9, bold=True)
            c_type3.alignment = align()

            # D~L: 시간별 정확도 (% 행)
            for i, h in enumerate(HOURS):
                est_h_col = get_column_letter(COL_START + i)
                hd = hourly_by_hour.get(h)
                pred_val = hd.get(fc_field, {}).get(fc_key) if hd else None

                if act_val and act_val != 0:
                    formula = f'=IFERROR(MAX(0,1-ABS({est_h_col}{est_row}-{act_col}{act_row})/ABS({act_col}{act_row})),"-")'
                    pct_c = ws.cell(row=cur_row, column=COL_START + i, value=formula)
                    pct_c.number_format = '0%'
                    pct_c.alignment = align('right')
                    pct_c.border = border()
                    if pred_val and pred_val != 0:
                        acc_ratio = max(0.0, 1 - abs(pred_val - act_val) / abs(act_val))
                        af2, ac2 = _acc_fill_font(acc_ratio)
                        pct_c.fill = af2
                        pct_c.font = font(bold=True, size=9, color=ac2)
                    else:
                        pct_c.fill = fill(_ROW_BG)
                        pct_c.font = font(size=9)
                else:
                    c_e = ws.cell(row=cur_row, column=COL_START + i, value='-')
                    c_e.font = font(size=9)
                    c_e.fill = fill(_ROW_BG)
                    c_e.alignment = align('right')
                    c_e.border = border()

            # M(실제마감), N(전체정확도), O~Q(구간정확도) → % 행은 비움
            for col in [COL_ACT, COL_ACC, COL_ACC_A, COL_ACC_B, COL_ACC_C]:
                ws.cell(row=cur_row, column=col).fill = fill(_ROW_BG)
                ws.cell(row=cur_row, column=col).border = border()

            pct_row = cur_row  # 시간대별 정확도(클램프됨) 셀들이 있는 행 - 아래서 AVERAGE로 재사용
            cur_row += 1

            # ── [수정2] 정확도 4개 컬럼 → 실 행(act_row)에 소급 적용
            # [수정 20260930] "예측 먼저 평균→실제와 비교" 대신 "시간대별 정확도
            # 먼저 계산(위 % 행, 이미 0~100% 클램프됨)→그 정확도들을 평균"으로 변경.
            # 정확도(전체) → N열, 실 행
            if act_val and act_val != 0 and all_accs:
                acc_r = sum(all_accs) / len(all_accs)
                af, ac = _acc_fill_font(acc_r)
                first_fc_col = get_column_letter(COL_START)
                last_fc_col  = get_column_letter(COL_START + len(HOURS) - 1)
                acc_c = ws.cell(row=act_row, column=COL_ACC,
                                value=f'=IFERROR(AVERAGE({first_fc_col}{pct_row}:{last_fc_col}{pct_row}),"-")')
                acc_c.number_format = '0.0%'
                acc_c.fill = af
                acc_c.font = font(bold=True, size=10, color=ac)
                acc_c.alignment = align()
                acc_c.border = border()

            # 구간별 정확도 → O/P/Q열, 실 행
            for col_out, i_start, i_end in [
                (COL_ACC_A, 0, 2),
                (COL_ACC_B, 3, 5),
                (COL_ACC_C, 6, 8),
            ]:
                s_col = get_column_letter(COL_START + i_start)
                e_col = get_column_letter(COL_START + i_end)
                seg_accs = seg_acc_map[(i_start, i_end)]
                if act_val and act_val != 0:
                    c_seg = ws.cell(row=act_row, column=col_out,
                                    value=f'=IFERROR(AVERAGE({s_col}{pct_row}:{e_col}{pct_row}),"-")')
                    c_seg.number_format = '0%'
                    c_seg.alignment = align('right')
                    c_seg.border = border()
                    if seg_accs:
                        acc_ratio = sum(seg_accs) / len(seg_accs)
                        af3, ac3 = _acc_fill_font(acc_ratio)
                        c_seg.fill = af3
                        c_seg.font = font(bold=True, size=10, color=ac3)
                    else:
                        c_seg.fill = fill(_C['white'])
                        c_seg.font = font(size=9)
                else:
                    c_seg = ws.cell(row=act_row, column=col_out, value='-')
                    c_seg.fill = fill(_C['white'])
                    c_seg.font = font(size=9)
                    c_seg.alignment = align()
                    c_seg.border = border()

        # ── 섹션 레이블 (세로 병합)
        ws.merge_cells(start_row=sec_start, start_column=COL_SEC,
                       end_row=cur_row - 1, end_column=COL_SEC)
        sc = ws.cell(row=sec_start, column=COL_SEC, value=sec_name)
        sc.font = font(bold=True, size=9, white=True)
        sc.fill = fill(_C['subhdr'])
        sc.alignment = align()
        sc.border = border()
        for r2 in range(sec_start + 1, cur_row):
            ws.cell(row=r2, column=COL_SEC).fill = fill(_C['subhdr'])
            ws.cell(row=r2, column=COL_SEC).border = border()

    # ── [추가수정3] 정확도 % 행 색상: Python에서 직접 계산 후 적용
    # 95%↑ 빨강(FF0000), 90%↑ 주황(FF9900), 90% 미만 파랑(4472C4)
    from openpyxl.styles import PatternFill as _PF2

    def _acc_color_fill(formula_str):
        """수식을 실제 계산해서 색상 결정 (불가시 기본 흰색)"""
        # 조건부서식 대신: hourly_by_hour에서 실제 예측값과 act_val로 계산
        return _C['white']  # 기본값 (수식 평가 불가)

    RED_FILL    = _PF2(fill_type='solid', fgColor='FFFF0000')
    ORANGE_FILL = _PF2(fill_type='solid', fgColor='FFFF9900')
    BLUE_FILL   = _PF2(fill_type='solid', fgColor='FF4472C4')

    def _apply_acc_color(ws, row, col, act_val, pred_val):
        """예측값과 실제값으로 정확도 계산 후 색상 직접 적용"""
        if not act_val or not pred_val or act_val == 0:
            return
        acc = 1 - abs(pred_val - act_val) / abs(act_val)
        c = ws.cell(row=row, column=col)
        if acc >= 0.95:
            c.fill = RED_FILL
        elif acc >= 0.90:
            c.fill = ORANGE_FILL
        else:
            c.fill = BLUE_FILL
        c.font = font(bold=True, size=10,
                      color='FFFFFFFF')  # 흰 텍스트로 가독성 확보

    ws.freeze_panes = 'D3'




# ══════════════════════════════════════════════════════════════════
# S3: 월별 실적 (날짜별 당일/누적 전체)
# ══════════════════════════════════════════════════════════════════

def _build_s3_monthly(wb, year: int, month: int, month_daily: dict, today_day: int):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    fill, font, border, align = _styles()

    ws = wb.create_sheet('일별 실적')
    last_day = monthrange(year, month)[1]
    WD = ['월', '화', '수', '목', '금', '토', '일']

    # 헤더 구조
    # A:날짜 B:요일
    # MVNO IN 당일: C(SM) D(KM) E(LM) F(계)
    # MVNO IN 누적: G(SM) H(KM) I(LM) J(계)
    # MNO Out 당일: K(S) L(K) M(L) N(계)
    # MNO Out 누적: O(S) P(K) Q(L) R(계)
    # 순증감 당일:  S(SM) T(KM) U(LM) V(계)
    # 순증감 누적:  W(SM) X(KM) Y(LM) Z(계)
    # MVNO Out 당일: AA(SM) AB(KM) AC(LM) AD(계)
    # MVNO Out 누적: AE(SM) AF(KM) AG(LM) AH(계)

    col_groups = [
        ('날짜', ['날짜', '요일']),
        ('MVNO IN (당일)', ['SM', 'KM', 'LM', '계']),
        ('MVNO IN (누적)', ['SM', 'KM', 'LM', '계']),
        ('MNO Out (당일)', ['S', 'K', 'L', '계']),
        ('MNO Out (누적)', ['S', 'K', 'L', '계']),
        ('순증감 (당일)', ['SM', 'KM', 'LM', '계']),
        ('순증감 (누적)', ['SM', 'KM', 'LM', '계']),
        ('MVNO Out (당일)', ['SM', 'KM', 'LM', '계']),
        ('MVNO Out (누적)', ['SM', 'KM', 'LM', '계']),
    ]

    # 타이틀
    total_cols = sum(len(g[1]) for g in col_groups)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.row_dimensions[1].height = 22
    t = ws.cell(row=1, column=1, value=f'월별 실적 현황 — {year}년 {month}월')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()

    # 그룹 헤더
    ws.row_dimensions[2].height = 18
    col = 1
    for grp_name, sub_cols in col_groups:
        n = len(sub_cols)
        if n > 1:
            ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + n - 1)
        c = ws.cell(row=2, column=col, value=grp_name)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.alignment = align()
        c.border = border()
        for i in range(1, n):
            ws.cell(row=2, column=col + i).fill = fill(_C['subhdr'])
            ws.cell(row=2, column=col + i).border = border()
        col += n

    # 서브 헤더
    ws.row_dimensions[3].height = 16
    col = 1
    for grp_name, sub_cols in col_groups:
        for sc in sub_cols:
            c = ws.cell(row=3, column=col, value=sc)
            c.font = font(bold=True, size=9, white=True)
            c.fill = fill(_C['subhdr'])
            c.alignment = align()
            c.border = border()
            col += 1

    # 열 너비
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 5
    for i in range(3, total_cols + 1):
        ws.column_dimensions[get_column_letter(i)].width = 9

    # 데이터
    r = 4
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        dt2 = datetime(year, month, day)
        wd = WD[dt2.weekday()]
        is_today = (day == today_day)
        is_zero = (wd == '일')
        d = month_daily.get(ds, {})

        row_fc = _C['today'] if is_today else (_C['zero'] if is_zero else _C['white'])
        ws.row_dimensions[r].height = 14

        vals = [ds, wd]
        mi  = d.get('mvno_in',    {})
        cmi = d.get('cum_mvno_in', {})
        mno = d.get('mno_out',    {})
        cmno= d.get('cum_mno_out',{})
        net = d.get('net_change', {})
        cnet= d.get('cum_net',    {})
        mo  = d.get('mvno_out',   {})
        cmo = d.get('cum_mvno_out',{})

        vals += [mi.get('SM'), mi.get('KM'), mi.get('LM'), mi.get('계')]
        vals += [cmi.get('SM'), cmi.get('KM'), cmi.get('LM'), cmi.get('계')]
        vals += [mno.get('S'), mno.get('K'), mno.get('L'), mno.get('계')]
        vals += [cmno.get('S'), cmno.get('K'), cmno.get('L'), cmno.get('계')]
        vals += [net.get('SM'), net.get('KM'), net.get('LM'), net.get('계')]
        vals += [cnet.get('SM'), cnet.get('KM'), cnet.get('LM'), cnet.get('계')]
        vals += [mo.get('SM'), mo.get('KM'), mo.get('LM'), mo.get('계')]
        vals += [cmo.get('SM'), cmo.get('KM'), cmo.get('LM'), cmo.get('계')]

        for col, val in enumerate(vals, 1):
            c = ws.cell(row=r, column=col, value=val if val is not None else None)
            c.font = font(bold=is_today, size=9)
            c.fill = fill(row_fc)
            c.border = border()
            if isinstance(val, int):
                c.alignment = align('right')
                c.number_format = '+#,##0;-#,##0;-' if col >= 20 else '#,##0'  # 순증감 컬럼
            else:
                c.alignment = align()
        r += 1

    # 합계행
    ws.row_dimensions[r].height = 16
    ws.cell(row=r, column=1, value='합계').font = font(bold=True, size=9, white=True)
    for col in range(1, total_cols + 1):
        c = ws.cell(row=r, column=col)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.font = font(bold=True, size=9, white=True)
        if col >= 3:
            col_letter = get_column_letter(col)
            c.value = f'=SUM({col_letter}4:{col_letter}{r-1})'
            c.number_format = '#,##0'
            c.alignment = align('right')

    ws.freeze_panes = 'C4'


# ══════════════════════════════════════════════════════════════════
# 세종→고고 이관 시트 2개 (신규, Claude v3.14)
# ══════════════════════════════════════════════════════════════════

def _build_sejong_trend(wb):
    """
    '고고 전환 추이' 시트.
    전체 이력을 월별로 묶어 일자별 나열 + 월 소계 행 + 맨 위 전체 누계.
    """
    from openpyxl.styles import Font
    fill, font, border, align = _styles()

    ws = wb.create_sheet('고고 전환 추이')
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 10
    ws.column_dimensions['D'].width = 10

    all_mig = _load_all_migration()
    dates = sorted(all_mig.keys())

    ws.cell(row=1, column=1, value='* 고고 세종 가입자 이관 현황').font = font(bold=True, size=12)

    total_sm = sum((all_mig[d].get('daily', {}).get('SM') or 0) for d in dates)
    total_km = sum((all_mig[d].get('daily', {}).get('KM') or 0) for d in dates)
    total_lm = sum((all_mig[d].get('daily', {}).get('LM') or 0) for d in dates
                   if all_mig[d].get('daily', {}).get('LM') is not None)

    r = 3
    for col, val in enumerate(['', 'S망', 'K망', 'L망'], 1):
        c = ws.cell(row=r, column=col, value=val)
        c.font = font(bold=True, white=True)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.alignment = align()
    r += 1
    ws.cell(row=r, column=1, value='누적 합계').font = font(bold=True)
    ws.cell(row=r, column=2, value=total_sm).alignment = align('right')
    ws.cell(row=r, column=3, value=total_km).alignment = align('right')
    ws.cell(row=r, column=4, value=total_lm).alignment = align('right')
    for col in range(1, 5):
        ws.cell(row=r, column=col).border = border()
    r += 2

    # 헤더
    for col, val in enumerate(['일자', 'S망', 'K망', 'L망'], 1):
        c = ws.cell(row=r, column=col, value=val)
        c.font = font(bold=True, white=True)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.alignment = align()
    r += 1

    cur_month = None
    month_sum_sm = month_sum_km = month_sum_lm = 0
    month_start_row = r

    def _write_month_subtotal(row, ym_label):
        ws.cell(row=row, column=1, value=f'{ym_label} 소계').font = font(bold=True)
        ws.cell(row=row, column=2, value=month_sum_sm).alignment = align('right')
        ws.cell(row=row, column=3, value=month_sum_km).alignment = align('right')
        ws.cell(row=row, column=4, value=month_sum_lm).alignment = align('right')
        for col in range(1, 5):
            ws.cell(row=row, column=col).fill = fill(_C['subhdr'])
            ws.cell(row=row, column=col).border = border()
            ws.cell(row=row, column=col).font = font(bold=True, white=True)

    for ds in dates:
        d = all_mig[ds]
        ym = ds[:7]
        if cur_month is not None and ym != cur_month:
            _write_month_subtotal(r, cur_month[5:] + '월')
            r += 2
            month_sum_sm = month_sum_km = month_sum_lm = 0
            for col, val in enumerate(['일자', 'S망', 'K망', 'L망'], 1):
                c = ws.cell(row=r, column=col, value=val)
                c.font = font(bold=True, white=True)
                c.fill = fill(_C['subhdr'])
                c.border = border()
                c.alignment = align()
            r += 1
        cur_month = ym

        dt2 = datetime.strptime(ds, '%Y-%m-%d')
        daily = d.get('daily', {})
        sm, km, lm = daily.get('SM') or 0, daily.get('KM') or 0, daily.get('LM')

        ws.cell(row=r, column=1, value=f'{dt2.month}월 {dt2.day}일')
        ws.cell(row=r, column=2, value=sm if sm else None).alignment = align('right')
        ws.cell(row=r, column=3, value=km if km else None).alignment = align('right')
        ws.cell(row=r, column=4, value=(lm if lm else ('미확인' if lm is None else None))).alignment = align('right')
        for col in range(1, 5):
            ws.cell(row=r, column=col).border = border()

        month_sum_sm += sm
        month_sum_km += km
        if lm is not None:
            month_sum_lm += lm
        r += 1

    if cur_month is not None:
        _write_month_subtotal(r, cur_month[5:] + '월')


def _build_s3_monthly_adjusted(wb, year: int, month: int, month_daily: dict,
                                migration_month: dict, today_day: int):
    """
    '일별실적(세종 이관 반영)' 시트.
    _build_s3_monthly()과 완전히 동일한 구조이되, MVNO IN/OUT의 SM/KM/LM에서
    해당일 이관값(daily/cum)만큼 차감해서 표시. L망 미확인(None)이면 차감하지 않음.
    """
    from openpyxl.utils import get_column_letter
    fill, font, border, align = _styles()

    ws = wb.create_sheet('일별실적(세종 이관 반영)')
    last_day = monthrange(year, month)[1]
    WD = ['월', '화', '수', '목', '금', '토', '일']

    col_groups = [
        ('날짜', ['날짜', '요일']),
        ('MVNO IN (당일)', ['SM', 'KM', 'LM', '계']),
        ('MVNO IN (누적)', ['SM', 'KM', 'LM', '계']),
        ('MNO Out (당일)', ['S', 'K', 'L', '계']),
        ('MNO Out (누적)', ['S', 'K', 'L', '계']),
        ('순증감 (당일)', ['SM', 'KM', 'LM', '계']),
        ('순증감 (누적)', ['SM', 'KM', 'LM', '계']),
        ('MVNO Out (당일)', ['SM', 'KM', 'LM', '계']),
        ('MVNO Out (누적)', ['SM', 'KM', 'LM', '계']),
    ]

    total_cols = sum(len(g[1]) for g in col_groups)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.row_dimensions[1].height = 22
    t = ws.cell(row=1, column=1, value=f'월별 실적 현황(세종 이관 반영) — {year}년 {month}월')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()

    ws.row_dimensions[2].height = 18
    col = 1
    for grp_name, sub_cols in col_groups:
        n = len(sub_cols)
        if n > 1:
            ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + n - 1)
        c = ws.cell(row=2, column=col, value=grp_name)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.alignment = align()
        c.border = border()
        for i in range(1, n):
            ws.cell(row=2, column=col + i).fill = fill(_C['subhdr'])
            ws.cell(row=2, column=col + i).border = border()
        col += n

    ws.row_dimensions[3].height = 16
    col = 1
    for grp_name, sub_cols in col_groups:
        for sc in sub_cols:
            c = ws.cell(row=3, column=col, value=sc)
            c.font = font(bold=True, size=9, white=True)
            c.fill = fill(_C['subhdr'])
            c.alignment = align()
            c.border = border()
            col += 1

    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 5
    for i in range(3, total_cols + 1):
        ws.column_dimensions[get_column_letter(i)].width = 9

    def _sub(v, m):
        return v if m is None else v - m

    r = 4
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        dt2 = datetime(year, month, day)
        wd = WD[dt2.weekday()]
        is_today = (day == today_day)
        is_zero = (wd == '일')
        d = month_daily.get(ds, {})
        mig = migration_month.get(ds, {})
        mig_daily = mig.get('daily', {})
        mig_cum = mig.get('cum', {})

        row_fc = _C['today'] if is_today else (_C['zero'] if is_zero else _C['white'])
        ws.row_dimensions[r].height = 14

        mi_raw  = d.get('mvno_in',    {})
        cmi_raw = d.get('cum_mvno_in', {})
        mo_raw  = d.get('mvno_out',   {})
        cmo_raw = d.get('cum_mvno_out', {})
        mno = d.get('mno_out',    {})
        cmno= d.get('cum_mno_out',{})
        net = d.get('net_change', {})
        cnet= d.get('cum_net',    {})

        def _adj(raw, mig_d):
            out = {}
            for k in ('SM', 'KM', 'LM'):
                v = raw.get(k)
                out[k] = None if v is None else _sub(v, mig_d.get(k))
            out['계'] = sum(v for v in out.values() if v is not None) if raw else None
            return out

        mi  = _adj(mi_raw,  mig_daily) if mi_raw else {}
        mo  = _adj(mo_raw,  mig_daily) if mo_raw else {}
        cmi = _adj(cmi_raw, mig_cum)   if cmi_raw else {}
        cmo = _adj(cmo_raw, mig_cum)   if cmo_raw else {}

        vals = [ds, wd]
        vals += [mi.get('SM'), mi.get('KM'), mi.get('LM'), mi.get('계')]
        vals += [cmi.get('SM'), cmi.get('KM'), cmi.get('LM'), cmi.get('계')]
        vals += [mno.get('S'), mno.get('K'), mno.get('L'), mno.get('계')]
        vals += [cmno.get('S'), cmno.get('K'), cmno.get('L'), cmno.get('계')]
        vals += [net.get('SM'), net.get('KM'), net.get('LM'), net.get('계')]
        vals += [cnet.get('SM'), cnet.get('KM'), cnet.get('LM'), cnet.get('계')]
        vals += [mo.get('SM'), mo.get('KM'), mo.get('LM'), mo.get('계')]
        vals += [cmo.get('SM'), cmo.get('KM'), cmo.get('LM'), cmo.get('계')]

        for col, val in enumerate(vals, 1):
            c = ws.cell(row=r, column=col, value=val if val is not None else None)
            c.font = font(bold=is_today, size=9)
            c.fill = fill(row_fc)
            c.border = border()
            if isinstance(val, int):
                c.alignment = align('right')
                c.number_format = '+#,##0;-#,##0;-' if col >= 20 else '#,##0'
            else:
                c.alignment = align()
        r += 1

    ws.row_dimensions[r].height = 16
    ws.cell(row=r, column=1, value='합계').font = font(bold=True, size=9, white=True)
    for col in range(1, total_cols + 1):
        c = ws.cell(row=r, column=col)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.font = font(bold=True, size=9, white=True)
        if col >= 3:
            col_letter = get_column_letter(col)
            c.value = f'=SUM({col_letter}4:{col_letter}{r-1})'
            c.number_format = '#,##0'
            c.alignment = align('right')

    ws.freeze_panes = 'C4'


# ══════════════════════════════════════════════════════════════════
# S4: 월마감 예측 추이 (열=날짜, 행=항목, bw 3시나리오)
# ══════════════════════════════════════════════════════════════════

def _build_s4_forecast(wb, year: int, month: int, month_daily: dict,
                       month_fc: dict, bw_map: dict, today_day: int,
                       month_19h: dict = None):
    """
    [v3.4] S4 월마감 예측 추이 — 전면 개편
    열: 1일~말일 (날짜가 열)
    행 섹션:
      [영업일수] 경과bw / 잔여bw
      [SKT T-Out] 일별/누적/일평균/fc_low/fc_mid/fc_high/달성률
      [MVNO IN] SM/KM/LM/계 × (일별/누적/fc_low/fc_mid/fc_high/정확도)
      [MNO Out] S/K/L/계 × (일별/누적/fc_low/fc_mid/fc_high/정확도)
      [순증감]  SM/KM/LM/계 × (일별/누적/예측/정확도)
      [MVNO Out] SM/KM/LM/계 × (일별/누적/fc_low/fc_mid/fc_high/정확도)

    bw 소스: ktoa_daily 필드만 사용 (bw_map 폴백 제거, 섞임 방지)
      - 경과/잔여: bw_ai_prev
      - fc_low:   bw_ai_w2  (없으면 bw_ai_prev)
      - fc_mid:   bw_ai_prev
      - fc_high:  bw_manual (없으면 bw_ai_prev)

    예측값(A+B):
      A: ktoa_daily.fc_low/mid/high (일마감 시 저장값, 가장 정확)
      B: 소급 계산 (저장값 없는 과거)
    MVNO/MNO 예측: ktoa_hourly 19시 forecast값 기반 bw 시나리오 파생
    """
    from openpyxl.utils import get_column_letter
    from bw_engine import is_zero_day
    fill, font, border, align = _styles()

    ws = wb.create_sheet('월마감 예측 추이')
    last_day = monthrange(year, month)[1]
    WD = ['월', '화', '수', '목', '금', '토', '일']

    # ── 월 목표 조회
    try:
        from predict_gemini import get_tout_goal as _gtg
        monthly_goal = _gtg(year, month)
    except Exception:
        monthly_goal = int(os.environ.get('KTOA_TOUT_GOAL', '42000'))

    # ── bw: ktoa_daily 필드만 사용 (bw_map 폴백 제거)
    def _bw_from_daily(ds: str, field: str, fallback_field: str = 'bw_ai_prev') -> float:
        data = month_daily.get(ds, {})
        v = data.get(field)
        if not v:
            v = data.get(fallback_field)
        return float(v) if v else 0.0

    # 전체 월 bw 합산 (잔여bw 계산용)
    total_bw_ai  = sum(_bw_from_daily(f"{year:04d}-{month:02d}-{d:02d}", 'bw_ai_prev')
                       for d in range(1, last_day + 1))
    total_bw_man = sum(_bw_from_daily(f"{year:04d}-{month:02d}-{d:02d}", 'bw_manual', 'bw_ai_prev')
                       for d in range(1, last_day + 1))
    total_bw_w2  = sum(_bw_from_daily(f"{year:04d}-{month:02d}-{d:02d}", 'bw_ai_w2', 'bw_ai_prev')
                       for d in range(1, last_day + 1))

    # ── 열 헤더 그리기 공통 함수
    def _draw_header():
        ws.column_dimensions['A'].width = 7   # 구분
        ws.column_dimensions['B'].width = 8   # 항목
        ws.column_dimensions['C'].width = 7   # 실/예

        for r, lbl in [(2, '구분'), (3, '항목'), (4, '실/예')]:
            for c_idx, v in enumerate([lbl, '', ''], 1):
                c = ws.cell(row=r, column=c_idx, value=v if c_idx == 1 else '')
                c.font = font(bold=True, size=9, white=True)
                c.fill = fill(_C['header'])
                c.alignment = align()
                c.border = border()

        ws.row_dimensions[1].height = 22
        ws.row_dimensions[2].height = 16
        ws.row_dimensions[3].height = 14
        ws.row_dimensions[4].height = 14

        for day in range(1, last_day + 1):
            ds  = f"{year:04d}-{month:02d}-{day:02d}"
            dt2 = datetime(year, month, day)
            wd  = WD[dt2.weekday()]
            col = day + 3
            ws.column_dimensions[get_column_letter(col)].width = 9

            iz = is_zero_day(ds)
            it = (day == today_day)
            ifut = (day > today_day)

            hf = (_C['today'] if it else _C['zero'] if iz else
                  _C['lgray'] if ifut else _C['subhdr'])
            fw = not (iz or ifut or it)

            for r, v in [(2, f'{month}월'), (3, day), (4, wd)]:
                c = ws.cell(row=r, column=col, value=v)
                c.font = font(bold=(r==3), size=8 if r==4 else 9, white=fw,
                              color='FF666666' if (iz or ifut) and not fw else 'FF000000')
                c.fill = fill(hf)
                c.alignment = align()
                c.border = border()

        # 마지막 열: 4/30 실제마감 + 예측정확도
        fin_col = last_day + 4
        ws.column_dimensions[get_column_letter(fin_col)].width = 10
        ws.column_dimensions[get_column_letter(fin_col+1)].width = 9
        for r, v in [(2, f'{month}/말일'), (3, '실제마감'), (4, '')]:
            c = ws.cell(row=r, column=fin_col, value=v)
            c.font = font(bold=True, size=9, white=True)
            c.fill = fill(_C['actual'])
            c.alignment = align()
            c.border = border()
        for r, v in [(2, '예측'), (3, '정확도'), (4, '(%)')]:
            c = ws.cell(row=r, column=fin_col+1, value=v)
            c.font = font(bold=True, size=9, white=True)
            c.fill = fill(_C['subhdr'])
            c.alignment = align()
            c.border = border()

    # ── 타이틀
    total_cols = last_day + 5
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    t = ws.cell(row=1, column=1,
                value=f'일별 월마감 예측/실제 비교 — {year}년 {month}월  (T-Out 목표: {monthly_goal:,})')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()
    _draw_header()

    if month_19h is None:
        month_19h = {}

    # ── 날짜별 데이터 계산 (누적)
    cum = {k: 0 for k in ['skt','sm','km','lm','mi',
                           's','k','l','mo',
                           'net_sm','net_km','net_lm','net',
                           'mo_sm','mo_km','mo_lm','mo_out']}
    cum_bw_ai = cum_bw_man = cum_bw_w2 = 0.0
    day_data = {}  # ds → computed values

    # 19시 hourly forecast: 미리 로드된 month_19h 딕셔너리에서 조회 (Firestore 추가 호출 없음)
    def _get_19h(ds: str) -> dict:
        return month_19h.get(ds, {})

    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d  = month_daily.get(ds, {})

        bw_ai  = _bw_from_daily(ds, 'bw_ai_prev')
        bw_man = _bw_from_daily(ds, 'bw_manual', 'bw_ai_prev')
        bw_w2  = _bw_from_daily(ds, 'bw_ai_w2',  'bw_ai_prev')

        if day <= today_day and d:
            # 실적 누적 (영업일만)
            if bw_ai > 0:
                cum_bw_ai  += bw_ai
                cum_bw_man += bw_man
                cum_bw_w2  += bw_w2
                cum['skt']    += d.get('mno_out',    {}).get('S',  0) or 0
                cum['sm']     += d.get('mvno_in',    {}).get('SM', 0) or 0
                cum['km']     += d.get('mvno_in',    {}).get('KM', 0) or 0
                cum['lm']     += d.get('mvno_in',    {}).get('LM', 0) or 0
                cum['mi']     += d.get('mvno_in',    {}).get('계', 0) or 0
                cum['s']      += d.get('mno_out',    {}).get('S',  0) or 0
                cum['k']      += d.get('mno_out',    {}).get('K',  0) or 0
                cum['l']      += d.get('mno_out',    {}).get('L',  0) or 0
                cum['mo']     += d.get('mno_out',    {}).get('계', 0) or 0
                cum['net_sm'] += d.get('net_change', {}).get('SM', 0) or 0
                cum['net_km'] += d.get('net_change', {}).get('KM', 0) or 0
                cum['net_lm'] += d.get('net_change', {}).get('LM', 0) or 0
                cum['net']    += d.get('net_change', {}).get('계', 0) or 0
                cum['mo_sm']  += d.get('mvno_out',   {}).get('SM', 0) or 0
                cum['mo_km']  += d.get('mvno_out',   {}).get('KM', 0) or 0
                cum['mo_lm']  += d.get('mvno_out',   {}).get('LM', 0) or 0
                cum['mo_out'] += d.get('mvno_out',   {}).get('계', 0) or 0

            rem_ai  = total_bw_ai  - cum_bw_ai  + bw_ai
            rem_man = total_bw_man - cum_bw_man + bw_man
            rem_w2  = total_bw_w2  - cum_bw_w2  + bw_w2

            # T-Out 예측 (A안: DB저장값 우선, B안: 실시간 계산)
            avg_skt = round(cum['skt'] / cum_bw_ai, 1) if cum_bw_ai > 0 else 0
            if d.get('fc_low') and d.get('fc_high'):
                fc_skt = {'low': d['fc_low'], 'mid': d.get('fc_mid', (d['fc_low']+d['fc_high'])//2),
                          'high': d['fc_high']}
            elif avg_skt > 0:
                fc_skt = {'low':  int(cum['skt'] + avg_skt * rem_w2),
                          'mid':  int(cum['skt'] + avg_skt * rem_ai),
                          'high': int(cum['skt'] + avg_skt * rem_man)}
            else:
                fc_skt = {'low': None, 'mid': None, 'high': None}

            # DB에 저장된 fc_ 전항목 값 확인 (있으면 우선 사용)
            db_fc_mi   = d.get('fc_mvno_in',  {}) or {}
            db_fc_mo   = d.get('fc_mno_out',  {}) or {}
            db_fc_mout = d.get('fc_mvno_out', {}) or {}
            db_fc_net  = d.get('fc_net',      {}) or {}

            def _use_db_or_calc(db_val, calc_val):
                """DB 저장값 우선, 없으면 실시간 계산값 사용"""
                if db_val and db_val.get('mid'):
                    return db_val
                return calc_val

            # MVNO/MNO 예측: DB값 우선, 없으면 19시 forecast 기반 bw 시나리오 파생
            h19 = _get_19h(ds) if bw_ai > 0 else {}
            def _fc_trio(actual_cum: int, h19_val: int, rem_w2_: float,
                         rem_ai_: float, rem_man_: float, avg_bw_: float) -> dict:
                """일평균 × 잔여bw로 low/mid/high 계산"""
                if avg_bw_ <= 0 or actual_cum <= 0:
                    return {'low': None, 'mid': None, 'high': None}
                avg = round(actual_cum / avg_bw_, 1)
                return {'low':  int(actual_cum + avg * rem_w2_),
                        'mid':  int(actual_cum + avg * rem_ai_),
                        'high': int(actual_cum + avg * rem_man_)}

            fc_mi  = _use_db_or_calc(db_fc_mi.get('계'), _fc_trio(cum['mi'],  h19.get('forecast_mvno_in',{}).get('계',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_sm  = _use_db_or_calc(db_fc_mi.get('SM'), _fc_trio(cum['sm'],  h19.get('forecast_mvno_in',{}).get('SM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_km  = _use_db_or_calc(db_fc_mi.get('KM'), _fc_trio(cum['km'],  h19.get('forecast_mvno_in',{}).get('KM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_lm  = _use_db_or_calc(db_fc_mi.get('LM'), _fc_trio(cum['lm'],  h19.get('forecast_mvno_in',{}).get('LM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_s   = _use_db_or_calc(db_fc_mo.get('S'),  _fc_trio(cum['s'],   h19.get('forecast_mno_out',{}).get('S',0),  rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_k   = _use_db_or_calc(db_fc_mo.get('K'),  _fc_trio(cum['k'],   h19.get('forecast_mno_out',{}).get('K',0),  rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_l   = _use_db_or_calc(db_fc_mo.get('L'),  _fc_trio(cum['l'],   h19.get('forecast_mno_out',{}).get('L',0),  rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_mo  = _use_db_or_calc(db_fc_mo.get('계'), _fc_trio(cum['mo'],  h19.get('forecast_mno_out',{}).get('계',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            # 순증감 예측 = MVNO IN 예측 - MVNO OUT 예측
            def _fc_net_from_inout(fc_in, fc_out):
                """순증감 예측 = MVNO IN 예측 - MVNO OUT 예측"""
                result = {}
                for k in ['low', 'mid', 'high']:
                    v_in  = fc_in.get(k)
                    v_out = fc_out.get(k)
                    result[k] = (v_in - v_out) if (v_in is not None and v_out is not None) else None
                return result

            fc_mo_sm  = _use_db_or_calc(db_fc_mout.get('SM'), _fc_trio(cum['mo_sm'], h19.get('forecast_mvno_out',{}).get('SM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_mo_km  = _use_db_or_calc(db_fc_mout.get('KM'), _fc_trio(cum['mo_km'], h19.get('forecast_mvno_out',{}).get('KM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_mo_lm  = _use_db_or_calc(db_fc_mout.get('LM'), _fc_trio(cum['mo_lm'], h19.get('forecast_mvno_out',{}).get('LM',0), rem_w2, rem_ai, rem_man, cum_bw_ai))
            fc_mo_out = _use_db_or_calc(db_fc_mout.get('계'), _fc_trio(cum['mo_out'],h19.get('forecast_mvno_out',{}).get('계',0), rem_w2, rem_ai, rem_man, cum_bw_ai))

            # 순증감 예측 = MVNO IN 예측 - MVNO OUT 예측
            fc_net_sm = _fc_net_from_inout(fc_sm, fc_mo_sm)
            fc_net_km = _fc_net_from_inout(fc_km, fc_mo_km)
            fc_net_lm = _fc_net_from_inout(fc_lm, fc_mo_lm)
            fc_net    = _fc_net_from_inout(fc_mi, fc_mo_out)

            day_data[ds] = {
                'bw_ai': bw_ai, 'bw_man': bw_man, 'bw_w2': bw_w2,
                'cum_bw_ai': round(cum_bw_ai, 3), 'rem_bw_ai': round(rem_ai, 3),
                # T-Out
                'skt': d.get('mno_out',{}).get('S',0) or 0,
                'cum_skt': cum['skt'], 'avg_skt': avg_skt,
                'fc_skt': fc_skt,
                'ach': cum['skt'] / monthly_goal if monthly_goal else 0,
                # MVNO IN
                'sm':cum['sm'],'km':cum['km'],'lm':cum['lm'],'mi':cum['mi'],
                'sm_d':d.get('mvno_in',{}).get('SM',0) or 0,
                'km_d':d.get('mvno_in',{}).get('KM',0) or 0,
                'lm_d':d.get('mvno_in',{}).get('LM',0) or 0,
                'mi_d':d.get('mvno_in',{}).get('계',0) or 0,
                'fc_sm':fc_sm,'fc_km':fc_km,'fc_lm':fc_lm,'fc_mi':fc_mi,
                # MNO Out
                's_d':d.get('mno_out',{}).get('S',0) or 0,
                'k_d':d.get('mno_out',{}).get('K',0) or 0,
                'l_d':d.get('mno_out',{}).get('L',0) or 0,
                'mo_d':d.get('mno_out',{}).get('계',0) or 0,
                'cum_s':cum['s'],'cum_k':cum['k'],'cum_l':cum['l'],'cum_mo':cum['mo'],
                'fc_s':fc_s,'fc_k':fc_k,'fc_l':fc_l,'fc_mo':fc_mo,
                # 순증감
                'net_sm_d':d.get('net_change',{}).get('SM',0) or 0,
                'net_km_d':d.get('net_change',{}).get('KM',0) or 0,
                'net_lm_d':d.get('net_change',{}).get('LM',0) or 0,
                'net_d':d.get('net_change',{}).get('계',0) or 0,
                'cum_net_sm':cum['net_sm'],'cum_net_km':cum['net_km'],
                'cum_net_lm':cum['net_lm'],'cum_net':cum['net'],
                'fc_net_sm':fc_net_sm,'fc_net_km':fc_net_km,
                'fc_net_lm':fc_net_lm,'fc_net':fc_net,
                # MVNO Out
                'mo_sm_d':d.get('mvno_out',{}).get('SM',0) or 0,
                'mo_km_d':d.get('mvno_out',{}).get('KM',0) or 0,
                'mo_lm_d':d.get('mvno_out',{}).get('LM',0) or 0,
                'mo_out_d':d.get('mvno_out',{}).get('계',0) or 0,
                'cum_mo_sm':cum['mo_sm'],'cum_mo_km':cum['mo_km'],
                'cum_mo_lm':cum['mo_lm'],'cum_mo_out':cum['mo_out'],
                'fc_mo_sm':fc_mo_sm,'fc_mo_km':fc_mo_km,
                'fc_mo_lm':fc_mo_lm,'fc_mo_out':fc_mo_out,
            }
        else:
            day_data[ds] = {}

    # ── [v3.12] 실제마감/정확도 기준일: 말일이 아닌 "마지막 영업일(실적 있는 날)"
    last_business_day = last_day
    for _d in range(last_day, 0, -1):
        _ds = f"{year:04d}-{month:02d}-{_d:02d}"
        if day_data.get(_ds):
            last_business_day = _d
            break

    # ── 행 출력 공통 함수
    cur_row = [5]  # mutable row counter

    def _write_row(label_a: str, label_b: str, label_c: str,
                   values: list, row_fill: str, num_fmt: str = '#,##0',
                   is_section: bool = False, bold_label: bool = False):
        """한 행 출력. values: [day1_val, day2_val, ..., final_val, acc_val]"""
        r = cur_row[0]
        ws.row_dimensions[r].height = 14

        sf = _C['header'] if is_section else (_C['subhdr'] if bold_label else row_fill)
        fw = is_section or bold_label

        for ci, (col, val) in enumerate([(1, label_a), (2, label_b), (3, label_c)]):
            c = ws.cell(row=r, column=col, value=val)
            c.font = font(bold=fw, size=9, white=fw)
            c.fill = fill(sf)
            c.alignment = align('left' if col <= 2 else 'center')
            c.border = border()

        fin_col = last_day + 4
        for day in range(1, last_day + 1):
            col = day + 3
            val = values[day - 1] if day - 1 < len(values) else None
            ds  = f"{year:04d}-{month:02d}-{day:02d}"
            iz  = is_zero_day(ds)
            it  = (day == today_day)
            ifu = (day > today_day)

            cf = (_C['today'] if it else _C['zero'] if iz else
                  _C['lgray'] if ifu else row_fill)
            c = ws.cell(row=r, column=col, value=val if val else None)
            c.font = font(bold=it, size=9,
                          color='FF888888' if ifu else 'FF000000')
            c.fill = fill(cf)
            c.border = border()
            c.number_format = num_fmt
            c.alignment = align('right' if val else 'center')

        # 실제마감 / 정확도
        final_val = values[last_day] if len(values) > last_day else None
        acc_val   = values[last_day+1] if len(values) > last_day+1 else None
        for col, val, cf in [(fin_col, final_val, _C['actual']),
                              (fin_col+1, acc_val, _C['good'] if acc_val else _C['white'])]:
            c = ws.cell(row=r, column=col, value=val)
            c.font = font(bold=False, size=9)
            c.fill = fill(cf)
            c.border = border()
            c.number_format = num_fmt if col == fin_col else '0.0%'
            c.alignment = align('right' if val else 'center')

        cur_row[0] += 1

    def _section_header(title: str):
        _write_row(title, '', '', [None]*(last_day+2), _C['header'],
                   is_section=True)

    def _vals(key_d: str, key_final: str = None):
        """날짜별 값 리스트 생성"""
        result = []
        for day in range(1, last_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            result.append(day_data.get(ds, {}).get(key_d))
        # 실제마감: 마지막 영업일 누적값
        last_ds = f"{year:04d}-{month:02d}-{last_business_day:02d}"
        result.append(day_data.get(last_ds, {}).get(key_final or key_d))
        result.append(None)  # 정확도 placeholder
        return result

    def _fc_vals(key_fc: str, fc_type: str, key_actual_final: str = None):
        """예측값(low/mid/high) 리스트"""
        result = []
        for day in range(1, last_day + 1):
            ds  = f"{year:04d}-{month:02d}-{day:02d}"
            fc  = day_data.get(ds, {}).get(key_fc, {})
            result.append(fc.get(fc_type) if fc else None)
        result.append(None)  # 실제마감 없음
        # 정확도: fc_mid vs 마지막 영업일 실제값
        if fc_type == 'mid' and key_actual_final:
            last_ds  = f"{year:04d}-{month:02d}-{last_business_day:02d}"
            act_final = day_data.get(last_ds, {}).get(key_actual_final)
            # 마지막 영업일 fc_mid
            last_fc  = day_data.get(last_ds, {}).get(key_fc, {})
            fc_final = last_fc.get('mid') if last_fc else None
            if act_final and fc_final and act_final > 0:
                result.append(round((fc_final - act_final) / act_final, 3))
            else:
                result.append(None)
        else:
            result.append(None)
        return result

    # ════════════════════════════════════════
    # 영업일수 섹션
    # ════════════════════════════════════════
    _section_header('■ 영업일수')
    _write_row('영업일수', '', '경과(bw)',
               [day_data.get(f"{year:04d}-{month:02d}-{d:02d}",{}).get('cum_bw_ai')
                for d in range(1, last_day+1)] + [None, None],
               _C['section'], '0.000', bold_label=True)
    _write_row('영업일수', '', '잔여(bw)',
               [day_data.get(f"{year:04d}-{month:02d}-{d:02d}",{}).get('rem_bw_ai')
                for d in range(1, last_day+1)] + [None, None],
               _C['section'], '0.000', bold_label=True)

    # ════════════════════════════════════════
    # SKT T-Out 섹션
    # ════════════════════════════════════════
    _section_header('■ SKT T-Out (MNO Out S)')
    _write_row('T-Out', 'S', '일별',   _vals('skt'), _C['white'])
    _write_row('T-Out', 'S', '누적',   _vals('cum_skt'), _C['actual'])
    _write_row('T-Out', 'S', '일평균', _vals('avg_skt'), _C['white'])
    _write_row('T-Out', 'S', '예측Low', _fc_vals('fc_skt','low'), _C['bad'])
    _write_row('T-Out', 'S', '예측Mid', _fc_vals('fc_skt','mid','cum_skt'), _C['good'])
    _write_row('T-Out', 'S', '예측High',_fc_vals('fc_skt','high'), _C['bad'])

    # ════════════════════════════════════════
    # MVNO IN 섹션
    # ════════════════════════════════════════
    _section_header('■ MVNO IN')
    for grp, d_key, cum_key, fc_key in [
        ('SM', 'sm_d', 'sm', 'fc_sm'),
        ('KM', 'km_d', 'km', 'fc_km'),
        ('LM', 'lm_d', 'lm', 'fc_lm'),
        ('계',  'mi_d', 'mi', 'fc_mi'),
    ]:
        _write_row('MVNO IN', grp, '일별',    _vals(d_key),  _C['white'])
        _write_row('MVNO IN', grp, '누적',    _vals(cum_key), _C['actual'])
        _write_row('MVNO IN', grp, '예측Low',  _fc_vals(fc_key,'low'),  _C['bad'])
        _write_row('MVNO IN', grp, '예측Mid',  _fc_vals(fc_key,'mid', cum_key), _C['good'])
        _write_row('MVNO IN', grp, '예측High', _fc_vals(fc_key,'high'), _C['bad'])

    # ════════════════════════════════════════
    # MNO Out 섹션
    # ════════════════════════════════════════
    _section_header('■ MNO Out')
    for grp, d_key, cum_key, fc_key in [
        ('S',  's_d',  'cum_s',  'fc_s'),
        ('K',  'k_d',  'cum_k',  'fc_k'),
        ('L',  'l_d',  'cum_l',  'fc_l'),
        ('계', 'mo_d', 'cum_mo', 'fc_mo'),
    ]:
        _write_row('MNO Out', grp, '일별',    _vals(d_key),  _C['white'])
        _write_row('MNO Out', grp, '누적',    _vals(cum_key), _C['actual'])
        _write_row('MNO Out', grp, '예측Low',  _fc_vals(fc_key,'low'),  _C['bad'])
        _write_row('MNO Out', grp, '예측Mid',  _fc_vals(fc_key,'mid', cum_key), _C['good'])
        _write_row('MNO Out', grp, '예측High', _fc_vals(fc_key,'high'), _C['bad'])

    # ════════════════════════════════════════
    # 순증감 섹션
    # ════════════════════════════════════════
    _section_header('■ 순증감')
    for grp, d_key, cum_key, fc_key in [
        ('SM', 'net_sm_d', 'cum_net_sm', 'fc_net_sm'),
        ('KM', 'net_km_d', 'cum_net_km', 'fc_net_km'),
        ('LM', 'net_lm_d', 'cum_net_lm', 'fc_net_lm'),
        ('계',  'net_d',   'cum_net',    'fc_net'),
    ]:
        _write_row('순증감', grp, '일별',    _vals(d_key),  _C['white'])
        _write_row('순증감', grp, '누적',    _vals(cum_key), _C['actual'])
        _write_row('순증감', grp, '예측Low',  _fc_vals(fc_key,'low'),  _C['bad'])
        _write_row('순증감', grp, '예측Mid',  _fc_vals(fc_key,'mid', cum_key), _C['good'])
        _write_row('순증감', grp, '예측High', _fc_vals(fc_key,'high'), _C['bad'])

    # ════════════════════════════════════════
    # MVNO Out 섹션
    # ════════════════════════════════════════
    _section_header('■ MVNO Out')
    for grp, d_key, cum_key, fc_key in [
        ('SM', 'mo_sm_d',  'cum_mo_sm',  'fc_mo_sm'),
        ('KM', 'mo_km_d',  'cum_mo_km',  'fc_mo_km'),
        ('LM', 'mo_lm_d',  'cum_mo_lm',  'fc_mo_lm'),
        ('계',  'mo_out_d', 'cum_mo_out', 'fc_mo_out'),
    ]:
        _write_row('MVNO Out', grp, '일별',    _vals(d_key),  _C['white'])
        _write_row('MVNO Out', grp, '누적',    _vals(cum_key), _C['actual'])
        _write_row('MVNO Out', grp, '예측Low',  _fc_vals(fc_key,'low'),  _C['bad'])
        _write_row('MVNO Out', grp, '예측Mid',  _fc_vals(fc_key,'mid', cum_key), _C['good'])
        _write_row('MVNO Out', grp, '예측High', _fc_vals(fc_key,'high'), _C['bad'])

    # 열 고정: A(구분)/B(항목)/C(실/예) + 4행(요일) 고정
    ws.freeze_panes = 'D5'

    # ── [추가수정1] A열(구분)/B열(항목) 같은 값 연속 행 셀 병합
    from openpyxl.styles import Alignment as _Aln
    max_row = ws.max_row

    # A열 병합: 섹션헤더(■) 아닌 데이터 행에서 같은 값 연속 병합
    r = 5
    while r <= max_row:
        a_val = ws.cell(r, 1).value
        if a_val and not str(a_val).startswith('■'):
            merge_start = r
            while r + 1 <= max_row and ws.cell(r + 1, 1).value == a_val:
                r += 1
            if r > merge_start:
                ws.merge_cells(start_row=merge_start, start_column=1,
                               end_row=r, end_column=1)
                ws.cell(merge_start, 1).alignment = _Aln(
                    horizontal='center', vertical='center', wrap_text=True)
        r += 1

    # B열 병합: 같은 구분 내에서 같은 항목값 연속 병합
    r = 5
    while r <= max_row:
        b_val = ws.cell(r, 2).value
        a_val = ws.cell(r, 1).value
        if b_val and not str(a_val or '').startswith('■'):
            merge_start = r
            while r + 1 <= max_row and ws.cell(r + 1, 2).value == b_val:
                r += 1
            if r > merge_start:
                ws.merge_cells(start_row=merge_start, start_column=2,
                               end_row=r, end_column=2)
                ws.cell(merge_start, 2).alignment = _Aln(
                    horizontal='center', vertical='center', wrap_text=True)
        r += 1


# ══════════════════════════════════════════════════════════════════
# S5: 영업일수 (기존 _build_bw_sheet 유지)
# ══════════════════════════════════════════════════════════════════

def _build_s5_bw(wb, year: int, month: int, month_daily: dict, bw_map: dict):
    """
    [v3.0] S5 영업일수 시트 - 신규 컬럼 구조
    컬럼: 일자 | 요일 | 계 | SM | KM | LM (실적) | 수동입력 | AI예측(현재사용) |
           AI월초 | AI1주차 | AI2주차 | AI3주차 | AI4주차 | 실적기반 | 비고
    """
    from openpyxl.utils import get_column_letter
    from bw_engine import is_zero_day
    fill, font, border, align = _styles()

    ws = wb.create_sheet('영업일수')
    last_day = monthrange(year, month)[1]
    WD = ['월', '화', '수', '목', '금', '토', '일']

    # ── 컬럼 정의
    # A:일자 B:요일 C:계 D:SM E:KM F:LM G:수동입력 H:AI예측(현재) I:AI월초
    # J:AI1주차 K:AI2주차 L:AI3주차 M:AI4주차 N:실적기반 O:오차(abs) P:MAE누적 Q:비고
    col_widths = [12, 5, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 18]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    total_cols = len(col_widths)  # 17

    # ── billing_weights에서 bw_manual 전체 로드 (ktoa_daily 없는 날 보완)
    billing_weights = {}
    try:
        db = _get_db()
        ym = f'{year:04d}-{month:02d}'
        bw_doc = (db.collection('ktoa_config').document('billing_weights')
                  .collection('monthly').document(ym).get())
        if bw_doc.exists:
            weights = bw_doc.to_dict().get('weights', {})
            for day_num, val in weights.items():
                ds = f'{year:04d}-{month:02d}-{int(day_num):02d}'
                billing_weights[ds] = float(val)
    except Exception as e:
        log.warning(f"billing_weights 로드 실패: {e}")

    # ── date 필드 없는 문서도 포함해서 전체 데이터 로드
    try:
        db_s5 = _get_db()
        all_bw_data = {}
        for day in range(1, last_day + 1):
            ds = f'{year:04d}-{month:02d}-{day:02d}'
            if ds in month_daily:
                all_bw_data[ds] = month_daily[ds]
            else:
                doc = db_s5.collection('ktoa_daily').document(ds).get()
                all_bw_data[ds] = doc.to_dict() if doc.exists else {}
    except Exception as e:
        log.warning(f"bw 직접 조회 실패: {e}")
        all_bw_data = month_daily

    # ── 타이틀
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.row_dimensions[1].height = 22
    t = ws.cell(row=1, column=1, value=f'영업일수 현황 — {year}년 {month}월')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()

    # ── 범례
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws.row_dimensions[2].height = 14
    leg = ws.cell(row=2, column=1,
                  value='■ 노랑=실적(MVNO IN)  ■ 연초록=AI예측  ■ 연주황=수동입력  ■ 연파랑=실적기반  ■ 회색=영업없는날')
    leg.font = font(size=8)
    leg.fill = fill(_C['white'])
    leg.alignment = align('left')

    # ── 그룹 헤더 (3행)
    ws.row_dimensions[3].height = 18
    group_headers = [
        (1, 2, '날짜/요일',    _C['subhdr']),
        (3, 6, 'MVNO IN 실적', _C['actual']),
        (7, 7, '후불기준',     _C['manual']),
        (8, 13, 'AI 예측',     _C['ai']),
        (14, 14, '실적기반',   _C['final']),
        (15, 17, '영업일수 예측 정확도', _C['good']),
    ]
    for s, e, label, fc in group_headers:
        if s < e:
            ws.merge_cells(start_row=3, start_column=s, end_row=3, end_column=e)
        c = ws.cell(row=3, column=s, value=label)
        c.font = font(bold=True, size=9, white=(fc not in [_C['white'], _C['actual'], _C['manual'], _C['ai'], _C['final']]))
        c.fill = fill(fc)
        c.alignment = align()
        c.border = border()
        for col in range(s+1, e+1):
            ws.cell(row=3, column=col).fill = fill(fc)
            ws.cell(row=3, column=col).border = border()

    # ── 컬럼 헤더 (4행)
    ws.row_dimensions[4].height = 32
    headers = [
        ('일자',              _C['subhdr']),
        ('요일',              _C['subhdr']),
        ('계\n(MVNO IN)',     _C['actual']),
        ('SM',               _C['actual']),
        ('KM',               _C['actual']),
        ('LM',               _C['actual']),
        ('후불기준\n(bw_manual)', _C['manual']),
        ('AI예측\n(현재사용)', _C['ai']),
        ('AI월초\n(bw_ai_w0)', _C['ai']),
        ('AI1주차\n(bw_ai_w1)', _C['ai']),
        ('AI2주차\n(bw_ai_w2)', _C['ai']),
        ('AI3주차\n(bw_ai_w3)', _C['ai']),
        ('AI4주차\n(bw_ai_w4)', _C['ai']),
        ('실적기반\n(bw_perf)', _C['final']),
        ('오차\n(abs)',        _C['good']),
        ('MAE\n누적',          _C['good']),
        ('비고',               _C['good']),
    ]
    for ci, (label, fc) in enumerate(headers, 1):
        c = ws.cell(row=4, column=ci, value=label)
        c.font = font(bold=True, size=8, white=(fc == _C['subhdr']))
        c.fill = fill(fc)
        c.alignment = align(wrap=True)
        c.border = border()

    # ── 합계 추적 컬럼 (bw 값들)
    col_sums = {i: [] for i in range(7, 15)}  # G~N
    mae_errors = []  # MAE 계산용

    # ── 데이터 행 (5행~)
    r = 5
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        dt2 = datetime(year, month, day)
        wd = WD[dt2.weekday()]
        zero = is_zero_day(ds)

        d = all_bw_data.get(ds, {})

        # MVNO IN 실적
        mi = d.get('mvno_in', {})
        mi_total = mi.get('계', None)
        mi_sm    = mi.get('SM', None)
        mi_km    = mi.get('KM', None)
        mi_lm    = mi.get('LM', None)

        # bw 값들
        bw_manual = d.get('bw_manual') or billing_weights.get(ds) or None
        bw_ai_cur = d.get('bw_ai_prev') or None   # 현재사용 (최신 예측)
        bw_ai_w0  = d.get('bw_ai_w0')  or None   # AI월초
        bw_ai_w1  = d.get('bw_ai_w1')  or None
        bw_ai_w2  = d.get('bw_ai_w2')  or None
        bw_ai_w3  = d.get('bw_ai_w3')  or None
        bw_ai_w4  = d.get('bw_ai_w4')  or None
        bw_perf   = d.get('bw_performance') or None
        bw_final  = bw_map.get(ds, 0.0) or None

        # 비고 + 오차/MAE 계산
        abs_err = None
        mae_cum = None
        note = ''
        if zero:
            note = '공휴일/일요일'
        elif bw_perf and bw_ai_cur:
            abs_err = round(abs(bw_perf - bw_ai_cur), 3)
            mae_errors.append(abs_err)
            mae_cum = round(sum(mae_errors) / len(mae_errors), 3)
            if abs_err >= 0.2:
                note = '⚠️ 오차 큼'
            elif abs_err <= 0.05:
                note = '✅ 정확'

        row_fc = _C['zero'] if zero else _C['white']
        ws.row_dimensions[r].height = 15

        # 값 + 색상 매핑 (O:오차, P:MAE누적, Q:비고 추가)
        row_vals = [
            (ds,        _C['subhdr'] if not zero else _C['zero']),
            (wd,        _C['subhdr'] if not zero else _C['zero']),
            (mi_total,  _C['actual'] if mi_total else row_fc),
            (mi_sm,     _C['actual'] if mi_sm else row_fc),
            (mi_km,     _C['actual'] if mi_km else row_fc),
            (mi_lm,     _C['actual'] if mi_lm else row_fc),
            (bw_manual, _C['manual'] if bw_manual else row_fc),
            (bw_ai_cur, _C['ai']     if bw_ai_cur else row_fc),
            (bw_ai_w0,  _C['ai']     if bw_ai_w0 else row_fc),
            (bw_ai_w1,  _C['ai']     if bw_ai_w1 else row_fc),
            (bw_ai_w2,  _C['ai']     if bw_ai_w2 else row_fc),
            (bw_ai_w3,  _C['ai']     if bw_ai_w3 else row_fc),
            (bw_ai_w4,  _C['ai']     if bw_ai_w4 else row_fc),
            (bw_perf,   _C['final']  if bw_perf else row_fc),
            # 오차: 0.05↓ 초록, 0.2↑ 주황, 그 사이 흰색
            (abs_err,   (_C['good'] if abs_err <= 0.05
                         else _C['bad'] if abs_err >= 0.2
                         else row_fc) if abs_err is not None else row_fc),
            (mae_cum,   _C['white'] if mae_cum else row_fc),
            (note,      row_fc),
        ]

        for ci, (val, fc) in enumerate(row_vals, 1):
            c = ws.cell(row=r, column=ci, value=val if val is not None else None)
            c.font = font(size=9,
                         white=(fc == _C['subhdr']),
                         color='FFCC0000' if ('⚠️' in str(val)) else 'FF000000')
            c.fill = fill(fc)
            c.border = border()
            if isinstance(val, float):
                c.alignment = align('right')
                c.number_format = '0.000'
            elif isinstance(val, int):
                c.alignment = align('right')
                c.number_format = '#,##0'
            else:
                c.alignment = align()

        # 합계 누적 (bw 컬럼만, 영업일에만)
        for ci, val in [(7, bw_manual), (8, bw_ai_cur), (9, bw_ai_w0),
                        (10, bw_ai_w1), (11, bw_ai_w2), (12, bw_ai_w3),
                        (13, bw_ai_w4), (14, bw_perf)]:
            if val and not zero:
                col_sums[ci].append(float(val))

        r += 1

    # ── 합계 행
    ws.row_dimensions[r].height = 16
    for ci in range(1, total_cols + 1):
        c = ws.cell(row=r, column=ci)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.alignment = align('right')
    ws.cell(row=r, column=1, value='영업일수 합계').alignment = align()

    for ci, vals in col_sums.items():
        if vals:
            c = ws.cell(row=r, column=ci, value=round(sum(vals), 3))
            c.number_format = '0.000'
            c.font = font(bold=True, size=9, white=True)

    ws.freeze_panes = 'A5'


# ══════════════════════════════════════════════════════════════════
# S6: 예측 정확도
# ══════════════════════════════════════════════════════════════════

def _build_s6_accuracy(wb, year: int, month: int, month_daily: dict):
    from openpyxl.utils import get_column_letter
    from bw_engine import is_zero_day
    fill, font, border, align = _styles()

    ws = wb.create_sheet('영업일수 예측 정확도')
    last_day = monthrange(year, month)[1]
    WD = ['월', '화', '수', '목', '금', '토', '일']

    COLS = ['날짜', '요일', 'bw_ai_prev', 'bw_final', 'bw_perf(실적)', '오차(abs)', 'MAE누적', '비고']

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLS))
    ws.row_dimensions[1].height = 22
    t = ws.cell(row=1, column=1, value=f'영업일수 예측 정확도 추이 — {year}년 {month}월')
    t.font = font(bold=True, size=12, white=True)
    t.fill = fill(_C['header'])
    t.alignment = align()

    ws.row_dimensions[2].height = 18
    for ci, col_name in enumerate(COLS, 1):
        c = ws.cell(row=2, column=ci, value=col_name)
        c.font = font(bold=True, size=9, white=True)
        c.fill = fill(_C['subhdr'])
        c.alignment = align()
        c.border = border()

    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 5
    ws.column_dimensions['H'].width = 18
    for i in range(3, 8):
        ws.column_dimensions[get_column_letter(i)].width = 13

    r = 3
    errors = []
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        dt2 = datetime(year, month, day)
        wd = WD[dt2.weekday()]
        zero = is_zero_day(ds)

        d = month_daily.get(ds, {})
        bw_ai   = d.get('bw_ai_prev')     or None
        bw_fin  = d.get('bw_final') or bw_ai or None
        bw_perf = d.get('bw_performance') or None

        abs_err = None
        mae_cum = None
        note = ''

        if bw_perf and bw_fin and not zero:
            abs_err = abs(bw_perf - bw_fin)
            errors.append(abs_err)
            mae_cum = sum(errors) / len(errors)
            if abs_err >= 0.2:
                note = '⚠️ 오차 큼'
            elif abs_err <= 0.05:
                note = '✅ 정확'

        row_fc = _C['zero'] if zero else _C['white']
        ws.row_dimensions[r].height = 15

        vals = [ds, wd, bw_ai, bw_fin, bw_perf, abs_err, mae_cum, note]
        for ci, val in enumerate(vals, 1):
            c = ws.cell(row=r, column=ci, value=val if val is not None else None)
            c.font = font(size=9)
            c.fill = fill(
                _C['bad'] if (ci == 6 and abs_err and abs_err >= 0.2) else
                _C['good'] if (ci == 6 and abs_err and abs_err < 0.1) else
                row_fc
            )
            c.border = border()
            if isinstance(val, float):
                c.alignment = align('right')
                c.number_format = '0.000'
            else:
                c.alignment = align()
        r += 1

    # 최종 MAE
    ws.row_dimensions[r].height = 16
    for ci in range(1, len(COLS) + 1):
        c = ws.cell(row=r, column=ci)
        c.fill = fill(_C['subhdr'])
        c.border = border()
        c.font = font(bold=True, size=9, white=True)
        c.alignment = align()
    ws.cell(row=r, column=1, value='최종 MAE')
    if errors:
        mae_final = sum(errors) / len(errors)
        c = ws.cell(row=r, column=7, value=mae_final)
        c.number_format = '0.000'
        c.alignment = align('right')
        c.font = font(bold=True, size=9, white=True)

    ws.freeze_panes = 'A3'


# ══════════════════════════════════════════════════════════════════
# 통합 생성 함수
# ══════════════════════════════════════════════════════════════════

def generate_report(date_str: str, daily_data: dict,
                    output_dir: str = '/tmp',
                    hourly_override: list = None,
                    hourly_date: str = None,
                    today_is_closed: bool = True,
                    include_month_summary: bool = False) -> Optional[str]:
    """
    MVNO 월간 리포트 엑셀 생성 (6개 시트)
    - date_str: 기준 날짜 (S1/S3/S4 기준)
    - hourly_override: S2용 hourly 데이터
    - include_month_summary: True면 '월마감 요약' 시트를 맨 앞에 추가 (월마감용)
    - today_is_closed: False면 S2 실제마감값 비움
    """
    try:
        from openpyxl import Workbook
        from bw_engine import get_month_bw_map
    except ImportError as e:
        log.error(f"import 실패: {e}")
        return None

    dt   = datetime.strptime(date_str, '%Y-%m-%d')
    year, month, day = dt.year, dt.month, dt.day

    log.info(f"엑셀 리포트 생성 시작: {date_str}")

    # 데이터 로드
    hourly_docs = hourly_override if hourly_override is not None else _load_today_hourly(date_str)
    month_daily = _load_month_daily(year, month)
    month_fc    = _load_month_forecasts(year, month)
    bw_map      = get_month_bw_map(year, month)
    # [v3.4] S4용 월 전체 hourly forecast 미리 로드 (날짜별 루프에서 개별 조회 방지)
    month_19h   = _load_month_19h_forecast(year, month)

    # 전일 데이터
    prev_ds = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
    prev_daily = month_daily.get(prev_ds)
    if not prev_daily:
        # 7일 이내 가장 최근 데이터
        for i in range(2, 8):
            prev_ds2 = (dt - timedelta(days=i)).strftime('%Y-%m-%d')
            if prev_ds2 in month_daily:
                prev_daily = month_daily[prev_ds2]
                break

    wb = Workbook()

    # S1: 일마감 요약
    _build_s1_summary(wb, date_str, daily_data, prev_daily, year, month)

    # S0: 월마감 요약 (월마감 확정 엑셀에서만, 맨 앞으로 삽입)
    if include_month_summary:
        _build_s0_month_summary(wb, year, month, date_str)

    # S2: 일별 실적 (구 S3) ← 순서 변경
    _build_s3_monthly(wb, year, month, month_daily, day)

    # [v3.14] 세종→고고 이관 반영 시트 2개 (Claude)
    try:
        migration_month = _load_month_migration(year, month)
        _build_s3_monthly_adjusted(wb, year, month, month_daily, migration_month, day)
        _build_sejong_trend(wb)
    except Exception as e:
        log.warning(f"세종이관 시트 생성 실패 (무시하고 계속 진행): {e}")

    # S3: 시간별 예측 (구 S2) ← 순서 변경
    s2_daily = daily_data if today_is_closed else {}
    s2_date  = hourly_date if hourly_date else date_str
    _build_s2_hourly(wb, s2_date, s2_daily, hourly_docs)

    # S4: 월마감 예측 추이
    _build_s4_forecast(wb, year, month, month_daily, month_fc, bw_map, day, month_19h)

    # S5: 영업일수
    _build_s5_bw(wb, year, month, month_daily, bw_map)

    # S6: 영업일수 예측 정확도 → S5에 통합됨 (별도 시트 불필요)

    # S7: 구분 시트 "시간별 예측(과거) →"
    ws_sep = wb.create_sheet('시간별 예측(과거) →')
    ws_sep.sheet_properties.tabColor = '4472C4'
    ws_sep['A1'] = '↓ 아래 시트: 과거 영업일별 시간별 예측/실제 비교 (마감 완료일만)'

    # S8~: 과거 마감 완료 영업일별 시트 (오늘 제외, 역순)
    # ★ date_str이 어제일 수 있으므로 today_str 기준으로 필터
    db = _get_db()
    if db:
        past_dates = sorted(
            [d for d in month_daily.keys()
             if month_daily[d].get('mvno_in')],  # 마감 완료일만
            reverse=True
        )
        for past_ds in past_dates:
            try:
                past_hourly = _load_today_hourly(past_ds)
                if not past_hourly:
                    continue
                sheet_name = past_ds[5:]  # "MM-DD"
                _build_s2_hourly_named(wb, sheet_name, past_ds,
                                       month_daily[past_ds], past_hourly)
                log.info(f"과거 시트 추가: {past_ds} ({len(past_hourly)}건)")
            except Exception as e:
                log.warning(f"과거 시트 실패 ({past_ds}): {e}")

    filename = f'MVNO_리포트_{date_str}.xlsx'
    out_path = os.path.join(output_dir, filename)
    wb.save(out_path)
    log.info(f"엑셀 리포트 저장: {out_path}")
    return out_path


# 하위 호환성 유지
def generate_daily_report(date_str: str, daily_data: dict,
                           output_dir: str = '/tmp') -> Optional[str]:
    return generate_report(date_str, daily_data, output_dir, today_is_closed=True)


def find_last_business_day_of_month(year: int, month: int,
                                     up_to_day: int = None) -> Optional[dict]:
    """
    [v3.12] 해당 연/월 중 ktoa_daily에 mvno_in(실적)이 존재하는
    가장 늦은 날짜의 daily 데이터를 반환.
    - up_to_day: 지정 시 해당 일자까지만 탐색 (없으면 월 전체)
    - 반환: {'date': 'YYYY-MM-DD', **daily_dict} 또는 None (실적 없음)
    """
    from calendar import monthrange
    db = _get_db()
    if not db:
        return None

    last_day = monthrange(year, month)[1]
    end_day = up_to_day if up_to_day else last_day
    end_day = min(end_day, last_day)

    for day in range(end_day, 0, -1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get('mvno_in'):
                data['date'] = ds
                return data

    return None


def generate_month_report_for(year: int, month: int,
                               output_dir: str = '/tmp') -> Optional[str]:
    """
    [v3.12] 지정한 연/월의 마지막 영업일(실적 있는 날) 기준으로
    generate_report 호출. 과거월 "N월 엑셀 추출" 요청 대응.
    - 현재 진행 중인 월(today_str 포함월)은 generate_query_report() 사용 권장
    - 해당 월 실적이 전혀 없으면 None 반환
    """
    daily_data = find_last_business_day_of_month(year, month)
    if not daily_data:
        log.warning(f"generate_month_report_for: {year}-{month:02d} 실적 데이터 없음")
        return None

    report_date_str = daily_data['date']
    today_hourly = _load_today_hourly(report_date_str)

    return generate_report(report_date_str, daily_data, output_dir,
                           hourly_override=today_hourly,
                           hourly_date=report_date_str,
                           today_is_closed=True)


def _backfill_bw_performance(year: int, month: int) -> int:
    """
    [v3.12] 월마감 시 해당 월 전체 영업일의 bw_performance를 계산/저장.
    - calc_bw_performance_mvno(date, mvno_in_total, month_avg_mvno_in) 재사용
    - month_avg_mvno_in: 그 시점까지의 영업일 MVNO IN 일평균 (get_month_avg_mvno_in)
    - 이미 bw_performance가 있는 날은 건너뜀 (재계산 비용 절감)
    반환: 새로 저장한 일수
    """
    from calendar import monthrange as _mr
    try:
        from bw_engine import (calc_bw_performance_mvno, get_month_avg_mvno_in,
                                save_bw_to_daily, is_zero_day)
    except Exception as e:
        log.warning(f"bw_performance 백필: bw_engine import 실패 (스킵): {e}")
        return 0

    db = _get_db()
    if not db:
        return 0

    last_day = _mr(year, month)[1]
    saved = 0

    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        if is_zero_day(ds):
            continue
        try:
            doc = db.collection('ktoa_daily').document(ds).get()
            if not doc.exists:
                continue
            data = doc.to_dict()
            if data.get('bw_performance'):
                continue  # 이미 계산됨

            mvno_in_total = (data.get('mvno_in') or {}).get('계', 0) or 0
            if not mvno_in_total:
                continue

            month_avg = get_month_avg_mvno_in(year, month, day)
            if month_avg <= 0:
                continue

            bw_perf = calc_bw_performance_mvno(ds, mvno_in_total, month_avg)
            if bw_perf > 0:
                save_bw_to_daily(ds, 'bw_performance', bw_perf)
                saved += 1
        except Exception as e:
            log.warning(f"bw_performance 계산 실패 ({ds}, 무시): {e}")

    if saved:
        log.info(f"bw_performance 백필 완료: {year}-{month:02d} {saved}일")
    return saved


def generate_month_closing_report(date_str: str, daily_data: dict,
                                   output_dir: str = '/tmp') -> Optional[str]:
    """
    [v3.12] 월마감(잔여bw=0) 확정 엑셀 생성.
    generate_report를 그대로 재사용하되, 파일명만
    'MVNO_월마감_YYYY-MM.xlsx'로 구분하여 일반 daily 엑셀과 분리.
    """
    try:
        from openpyxl import Workbook  # noqa: F401  (generate_report 내부에서도 사용)
    except ImportError as e:
        log.error(f"import 실패: {e}")
        return None

    dt = datetime.strptime(date_str, '%Y-%m-%d')

    # ── [v3.12] S4/S5 '실적기반(bw_performance)' 컬럼 채우기 위해
    #    월마감 시점에 해당 월 전체 bw_performance 계산/저장
    try:
        _backfill_bw_performance(dt.year, dt.month)
        # bw_performance가 daily_data(오늘)에도 반영되도록 재조회
        db_rl = _get_db()
        if db_rl:
            _refreshed = db_rl.collection('ktoa_daily').document(date_str).get()
            if _refreshed.exists:
                daily_data = _refreshed.to_dict()
    except Exception as e:
        log.warning(f"bw_performance 백필 실패 (무시): {e}")

    # generate_report와 동일한 본문을 만들되, 저장 파일명만 다르게 처리
    tmp_path = generate_report(date_str, daily_data, output_dir, today_is_closed=True,
                                include_month_summary=True)
    if not tmp_path:
        return None

    new_filename = f'MVNO_월마감_{dt.year:04d}-{dt.month:02d}.xlsx'
    new_path = os.path.join(output_dir, new_filename)

    try:
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(tmp_path, new_path)
    except Exception as e:
        log.warning(f"월마감 파일명 변경 실패 (원본 경로 사용): {e}")
        return tmp_path

    log.info(f"월마감 확정 엑셀 저장: {new_path}")
    return new_path


def get_daily_forecast_accuracy(date_str: str, daily_data: dict) -> dict:
    """
    일마감 예측 정확도 계산
    - 시간별 예측 시트와 동일한 로직
    - 11~19시 각 시간의 예측값(forecast_*) AVERAGE vs 실제 마감값
    - SKT: forecast_engine._get_hour_completion_ratio() 기반(실제 배포된 예측과
      동일 로직) 사용. MVNO IN/OUT(SM)은 아직 별도 개선 전이라 기존 시간비례
      (현재값 × 10/경과시간) 방식 유지.
    표시 항목: T Out(SKT), MVNO IN(SM), MVNO OUT(SM)

    [수정 20260930] 이 함수가 실제 배포된 forecast_engine.predict_monthly()의
    fc_daily 계산(완료율곡선 기반)과 전혀 다른, 옛날 "시간비례" 공식을 독자적으로
    써서 SKT 정확도를 계산하고 있었음 - 그래서 캡션에 뜨는 "예측 정확도 95.4%"가
    실제 사용자가 받는 "월마감 예측" 메시지의 정확도와 무관한 딴 숫자였음(사장님
    지적: "저렇게 정확하지 않았거든" - 실측 체감과 캡션 수치가 안 맞음). SKT만
    forecast_engine의 실제 예측 로직으로 교체.
    """
    result = {}
    try:
        db = _get_db()
        if not db:
            return result

        # date_str: daily_data에서 실제 날짜 사용 (오늘/어제 혼동 방지)
        target_date = daily_data.get('date', date_str)

        # 11~19시 각 시간대 정시 문서 1개씩만 조회 (엑셀과 동일)
        # 정시 없으면 해당 시간대 가장 가까운 문서 사용
        hourly_docs = []
        for hour in range(11, 20):
            found = None
            for minute in ['00', '01', '10', '50', '59']:
                doc_id = f"{target_date}_{hour:02d}{minute}"
                doc = db.collection('ktoa_hourly').document(doc_id).get()
                if doc.exists:
                    d = doc.to_dict()
                    d['_hour'] = hour
                    found = d
                    if minute == '00':  # 정시 있으면 바로 사용
                        break
            if found:
                hourly_docs.append(found)

        log.info(f"hourly 문서 조회: {target_date} → {len(hourly_docs)}개 (시간대별 1개)")

        # 실제 마감값
        act_skt   = (daily_data.get('mno_out',  {}) or {}).get('S',  0) or 0
        act_mi_sm = (daily_data.get('mvno_in',  {}) or {}).get('SM', 0) or 0
        act_mo_sm = (daily_data.get('mvno_out', {}) or {}).get('SM', 0) or 0

        if not act_skt or not act_mi_sm or not act_mo_sm:
            return result

        import re as _re
        from forecast_engine import get_field_daily_forecast as _gdf

        fc_skt_list   = []
        fc_mi_sm_list = []
        fc_mo_sm_list = []

        for d in hourly_docs:
            # 시간 추출 (_hour 태그 우선, 없으면 reference_time에서 파싱)
            hour = d.get('_hour')
            if hour is None:
                m = _re.search(r'(\d+)시', d.get('reference_time', ''))
                hour = int(m.group(1)) if m else -1
            if not (11 <= hour <= 19):
                continue

            cur_skt   = (d.get('mno_out',  {}) or {}).get('S',  0) or 0
            cur_mi_sm = (d.get('mvno_in',  {}) or {}).get('SM', 0) or 0
            cur_mo_sm = (d.get('mvno_out', {}) or {}).get('SM', 0) or 0

            # [수정 20260930] MVNO IN/OUT(SM)도 SKT와 동일하게 요일필터+완료율곡선
            # 방식으로 통일(156일 백테스트: SM IN 10.7%→6.7%, SM OUT 10.3%→5.5%,
            # get_field_daily_forecast() 참고). 표본 부족 시 균일페이스로 자동 폴백.
            if cur_skt:
                fc_skt_list.append(_gdf(target_date, hour, 'mno_out', 'S', cur_skt))
            if cur_mi_sm:
                fc_mi_sm_list.append(_gdf(target_date, hour, 'mvno_in', 'SM', cur_mi_sm))
            if cur_mo_sm:
                fc_mo_sm_list.append(_gdf(target_date, hour, 'mvno_out', 'SM', cur_mo_sm))

        def _acc(pred_list, actual):
            """[수정 20260930] 기존엔 예측값들을 먼저 평균 낸 뒤 실제값과
            비교했는데, 이러면 어떤 시간엔 과대예측·어떤 시간엔 과소예측이
            섞여도 평균 과정에서 서로 상쇄돼 실제보다 정확해 보이는 문제가
            있었음(사장님 지적: "컸다작았다하면 정확도가 좋아지잖아"). 시간대별로
            먼저 정확도(1-오차율)를 구하고, 그 정확도들을 평균내는 방식으로 변경.
            개별 시간 오차가 100% 넘어가는 극단치는 0%로 클램프해서 정확도가
            음수로 나오지 않게(항상 0~100% 이내) 함."""
            if not pred_list or not actual or actual == 0:
                return None
            hourly_acc = [max(0.0, 1 - abs(p - actual) / abs(actual)) for p in pred_list]
            return round(sum(hourly_acc) / len(hourly_acc) * 100, 1)

        result['skt']         = _acc(fc_skt_list,   act_skt)
        result['mvno_in_sm']  = _acc(fc_mi_sm_list, act_mi_sm)
        result['mvno_out_sm'] = _acc(fc_mo_sm_list, act_mo_sm)

        log.info(f"예측 정확도 계산: {date_str} → {result} "
                 f"(skt:{len(fc_skt_list)}개, mi_sm:{len(fc_mi_sm_list)}개, mo_sm:{len(fc_mo_sm_list)}개)")

    except Exception as e:
        log.warning(f"예측 정확도 계산 실패: {e}")

    return result


def get_month_forecast_accuracy(year: int, month: int) -> dict:
    """
    [v3.13] 월 전체 일마감 예측 정확도를 1~10일/11~20일/21~말일 순기별 + 전체로 집계.
    get_daily_forecast_accuracy()를 영업일마다 호출해 평균.

    반환: {
      'skt':         {'total': float|None, 'd1': .., 'd2': .., 'd3': ..},
      'mvno_in_sm':  {...},
      'mvno_out_sm': {...},
    }
    각 값은 0~100 (퍼센트), 데이터 없으면 None.
    """
    from calendar import monthrange as _mr
    from bw_engine import is_zero_day

    last_day = _mr(year, month)[1]
    db = _get_db()

    # 순기 구간: (1~10), (11~20), (21~말일)
    decades = [(1, 10), (11, 20), (21, last_day)]

    keys = ['skt', 'mvno_in_sm', 'mvno_out_sm']
    per_decade = {k: [[] for _ in decades] for k in keys}
    overall = {k: [] for k in keys}

    if db:
        for day in range(1, last_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            if is_zero_day(ds):
                continue
            try:
                doc = db.collection('ktoa_daily').document(ds).get()
                if not doc.exists:
                    continue
                daily_data = doc.to_dict()
                if not daily_data.get('mvno_in'):
                    continue
                acc = get_daily_forecast_accuracy(ds, daily_data)
            except Exception as e:
                log.warning(f"get_month_forecast_accuracy: {ds} 정확도 계산 실패 (무시): {e}")
                continue

            for di, (dstart, dend) in enumerate(decades):
                if dstart <= day <= dend:
                    for k in keys:
                        v = acc.get(k)
                        if v is not None:
                            per_decade[k][di].append(v)
                            overall[k].append(v)
                    break

    def _avg(vals):
        return round(sum(vals) / len(vals), 1) if vals else None

    result = {}
    for k in keys:
        result[k] = {
            'total': _avg(overall[k]),
            'd1': _avg(per_decade[k][0]),
            'd2': _avg(per_decade[k][1]),
            'd3': _avg(per_decade[k][2]),
        }
    return result


def build_excel_caption(date_str: str, daily_data: dict,
                         is_month_closing: bool = False) -> str:
    """엑셀 전송 시 텔레그램 캡션 메시지 생성

    [v3.12] is_month_closing=True 면 월마감 확정본 캡션으로 분기
    """
    from datetime import datetime as _dt
    try:
        d = _dt.strptime(date_str, '%Y-%m-%d')
        date_label = f"'{str(d.year)[2:]}.{d.month}.{d.day}"
    except Exception:
        date_label = date_str

    acc = get_daily_forecast_accuracy(date_str, daily_data)

    def _fmt(v):
        return f'{v}%' if v is not None else '-'

    acc_lines = (
        f'📈 일마감 예측 정확도 (11~19시 평균)\n'
        f'ㆍT Out(SKT) : {_fmt(acc.get("skt"))}\n'
        f'ㆍMVNO IN(SM) : {_fmt(acc.get("mvno_in_sm"))}\n'
        f'ㆍMVNO OUT(SM) : {_fmt(acc.get("mvno_out_sm"))}'
    )

    sheet_lines = (
        '📋 Sheet 구성\n'
        'S1:일마감요약  S2:일별실적\n'
        'S3:일별실적(세종이관반영)  S4:고고전환추이\n'
        'S5:시간별예측  S6:월마감예측추이  S7:영업일수(AI)'
    )

    if is_month_closing:
        try:
            ym_label = f"{d.year}년 {d.month}월"
        except Exception:
            ym_label = date_str[:7]

        try:
            macc = get_month_forecast_accuracy(d.year, d.month)

            def _mfmt(v):
                return f'{v}%' if v is not None else '0%'

            def _block(title, k):
                a = macc.get(k, {})
                return (
                    f'ㆍ{title} : {_mfmt(a.get("total"))}\n'
                    f'      1~10일 : {_mfmt(a.get("d1"))}\n'
                    f'     11~20일 : {_mfmt(a.get("d2"))}\n'
                    f'     21~말일 : {_mfmt(a.get("d3"))}'
                )

            acc_lines = (
                f'📈 {ym_label} 월마감 예측 정확도\n\n'
                f'{_block("T Out(SKT)", "skt")}\n\n'
                f'{_block("MVNO IN(SM)", "mvno_in_sm")}\n\n'
                f'{_block("MVNO OUT(SM)", "mvno_out_sm")}'
            )
        except Exception as e:
            log.warning(f"월별 정확도 계산 실패 (일별 정확도로 대체): {e}")

        return (
            f'📦 {ym_label} 월마감 확정 리포트 ({date_label} 기준)\n\n'
            f'{acc_lines}\n\n'
            f'{sheet_lines}'
        )

    return (
        f'📊 일마감 리포트({date_label}일 기준)\n\n'
        f'{acc_lines}\n\n'
        f'{sheet_lines}'
    )


def _build_s2_hourly_named(wb, sheet_name: str, date_str: str,
                            daily: dict, hourly_docs: list):
    """과거 일별 시간별 예측 시트 — 시트명 지정 버전"""
    _build_s2_hourly(wb, date_str, daily, hourly_docs, sheet_name=sheet_name)


# ══════════════════════════════════════════════════════════════════
# 리포트 생성 (통합)
# ══════════════════════════════════════════════════════════════════

def generate_query_report(output_dir: str = '/tmp') -> Optional[str]:
    """
    텔레그램 "엑셀 추출" 명령어용
    - S1 일마감 요약: 당일 실적(mvno_in) 있으면 오늘, 없으면 최근 14일 내
                     실적이 있는 가장 최근 영업일 자동 탐색
    - S2 시간별: 항상 오늘 hourly (현재까지 수집된 시간대 표시)
    """
    now_kst   = datetime.now(KST)
    today_str = now_kst.strftime('%Y-%m-%d')

    db = _get_db()
    daily_data = {}
    report_date_str = today_str

    if db:
        try:
            # 오늘부터 최대 14일 역탐색 → 실적(mvno_in)이 있는 가장 최근 영업일
            for i in range(0, 15):
                candidate = (now_kst - timedelta(days=i)).strftime('%Y-%m-%d')
                doc = db.collection('ktoa_daily').document(candidate).get()
                if doc.exists and doc.to_dict().get('mvno_in'):
                    daily_data = doc.to_dict()
                    report_date_str = candidate
                    log.info(f"S1 기준 날짜: {candidate} (오늘에서 {i}일 전)")
                    break
        except Exception as e:
            log.error(f"daily 조회 실패: {e}")

    # ★ S2 hourly 날짜 결정
    # - 영업일(월~토) 10:10 이후: 오늘 hourly
    # - 10:10 이전 또는 일요일/공휴일: 직전 영업일 hourly 유지
    import datetime as _dt_mod
    now_time = now_kst.time()
    now_weekday = now_kst.weekday()  # 0=월 ... 6=일
    is_sunday = (now_weekday == 6)

    # 공휴일 체크 (bw_engine 없어도 동작하도록 try/except)
    try:
        from bw_engine import _is_holiday as _bw_hol
        is_holiday = _bw_hol(today_str)
    except Exception:
        is_holiday = False

    is_zero = is_sunday or is_holiday
    is_before_first_data = now_time < _dt_mod.time(10, 10)

    if is_zero or is_before_first_data:
        # 직전 영업일 찾기
        hourly_date = today_str
        for i in range(1, 8):
            candidate = (now_kst - timedelta(days=i)).strftime('%Y-%m-%d')
            cand_dt = now_kst - timedelta(days=i)
            cand_weekday = cand_dt.weekday()
            try:
                from bw_engine import _is_holiday as _bw_hol2
                cand_holiday = _bw_hol2(candidate)
            except Exception:
                cand_holiday = False
            if cand_weekday != 6 and not cand_holiday:
                hourly_date = candidate
                break
        log.info(f"S2 hourly → 직전 영업일: {hourly_date} (오늘={today_str}, zero={is_zero}, before={is_before_first_data})")
    else:
        hourly_date = today_str
        log.info(f"S2 hourly → 오늘: {hourly_date}")

    today_hourly = _load_today_hourly(hourly_date)
    log.info(f"hourly 조회: {len(today_hourly)}건 ({hourly_date})")

    # hourly 날짜가 오늘이고 오늘 미마감이면 → S2 실제마감 비움
    # hourly 날짜 태깅 (generate_report에서 판별용)
    today_is_closed = (report_date_str == today_str and bool(daily_data.get('mvno_in')))

    return generate_report(report_date_str, daily_data, output_dir,
                           hourly_override=today_hourly,
                           hourly_date=hourly_date,
                           today_is_closed=today_is_closed)


# ══════════════════════════════════════════════════════════════════
# 기존 함수들 유지 (bw_excel, forecast 저장 등)
# ══════════════════════════════════════════════════════════════════

def generate_bw_excel(year: int, month: int, output_dir: str = '/tmp') -> str:
    """영업일수 전용 엑셀 (텔레그램 명령어 응답용)"""
    try:
        from openpyxl import Workbook
        from bw_engine import get_month_bw_map
    except ImportError as e:
        log.error(f"import 실패: {e}")
        return None

    wb = Workbook()
    wb.remove(wb.active)

    month_daily = _load_month_daily(year, month)
    bw_map = get_month_bw_map(year, month)
    _build_s5_bw(wb, year, month, month_daily, bw_map)

    filename = f'영업일수_{year:04d}{month:02d}.xlsx'
    out_path = os.path.join(output_dir, filename)
    wb.save(out_path)
    log.info(f"영업일수 엑셀 저장: {out_path}")
    return out_path


def save_forecast_to_firestore(date_str: str, fc_low: int,
                                fc_high: int, fc_mid: int, bw: float) -> bool:
    try:
        db = _get_db()
        db.collection('ktoa_forecast').document(date_str).set({
            'date': date_str, 'forecast_low': fc_low,
            'forecast_high': fc_high, 'forecast': fc_mid,
            'bw': bw, 'updated_at': datetime.utcnow(),
        }, merge=True)
        return True
    except Exception as e:
        log.error(f"forecast 저장 실패: {e}")
        return False


def save_hourly_forecast(date_str: str, hour: int,
                          sm_in: int, km_in: int, lm_in: int,
                          skt_out: int, fc_low: int, fc_high: int,
                          fc_mid: int) -> bool:
    try:
        db = _get_db()
        db.collection('ktoa_forecast_hourly').document(f"{date_str}_{hour:02d}").set({
            'date': date_str, 'hour': hour,
            'sm_in': sm_in, 'km_in': km_in, 'lm_in': lm_in,
            'skt_out': skt_out, 'fc_low': fc_low,
            'fc_high': fc_high, 'fc_mid': fc_mid,
            'saved_at': datetime.utcnow(),
        }, merge=True)
        return True
    except Exception as e:
        log.error(f"hourly_forecast 저장 실패: {e}")
        return False