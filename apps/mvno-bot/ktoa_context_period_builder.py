#!/usr/bin/env python3
"""
ktoa_context_period_builder.py  v1.0
작성일: 2026-05-13

[수정 이력]
v1.3 | 2026-06-18 | GOALS_BY_MONTH 하드코딩 딕셔너리 완전 제거 (Claude)
  - _get_goals()를 target_goal_reader.get_goals_tuple() 위임으로 교체
  - forecast_excel.py가 이 함수를 import해서 쓰므로, 그쪽 코드는 수정 불필요
    (함수 이름/시그니처 유지, 내부 구현만 DB 조회로 교체)
v1.1 | 2026-05-13 | 월별 목표 동적 적용 + 전기비교 0건 처리
  - GOALS_BY_MONTH: 월별 T Out/SM순증/SM M/S 목표 동적 적용
  - 전기 데이터 없을 때 비율 계산 스킵
  - SM M/S 목표 달성 여부 표시
v1.0 | 2026-05-13 | 신규 생성
  - save_weekly_context(): 주차별 context 생성/저장 (ktoa_context_week/{YYYY-WW})
  - save_decade_context(): 순기별 context 생성/저장 (ktoa_context_decade/{YYYY-MM-D})
  - save_monthly_context(): 월별 context 생성/저장 (ktoa_context_month/{YYYY-MM})
  - backfill_weekly(): 주차별 일괄 backfill
  - backfill_decade(): 순기별 일괄 backfill
  - backfill_monthly(): 월별 일괄 backfill
  - get_period_context(): 질문 intent에 따라 적절한 period context 조회
  - 저장 구조:
      ktoa_context_week/{YYYY-WW}    예: 2026-W19
      ktoa_context_decade/{YYYY-MM-D} 예: 2026-05-1 (1순기), 2026-05-2, 2026-05-3
      ktoa_context_month/{YYYY-MM}   예: 2026-05
"""

import logging
from datetime import datetime, timedelta, timezone, date as _date
from calendar import monthrange

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def _get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


def _n(v, default=0):
    return int(v) if v else default


def _f(v, default=0.0):
    return float(v) if v else default


def _pct(a, b):
    return round(a / b * 100, 1) if b else 0.0


def _sign(v):
    return f"+{v:,}" if v >= 0 else f"{v:,}"


def _bw_fmt(v):
    if v is None:
        return 'N/A'
    f = float(v)
    if f == int(f):
        return f"{f:.1f}"
    return f"{f:.2f}".rstrip('0').rstrip('.') or '0'


def _collect_daily_records(start_date: str, end_date: str) -> list:
    """start_date~end_date 범위의 ktoa_daily 레코드 수집"""
    db = _get_db()
    records = []
    sd = datetime.strptime(start_date, '%Y-%m-%d')
    ed = datetime.strptime(end_date, '%Y-%m-%d')
    cur = sd
    while cur <= ed:
        ds = cur.strftime('%Y-%m-%d')
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            dd = doc.to_dict()
            if dd.get('mvno_in') or dd.get('mno_out'):
                dd['_date'] = ds
                records.append(dd)
        cur += timedelta(days=1)
    return records


def _aggregate_records(records: list) -> dict:
    """레코드 목록을 집계하여 핵심 수치 딕셔너리 반환"""
    if not records:
        return {}

    # bw 합계
    total_bw = sum(_f(r.get('bw_manual') or r.get('bw_ai_prev') or 1.0) for r in records)
    total_bw_ai = sum(_f(r.get('bw_ai_prev') or 1.0) for r in records)

    # 당기 합계 (일별 실적 합산)
    t_out_sum = sum(_n((r.get('mno_out') or {}).get('S')) for r in records)
    sm_net_sum = sum(_n((r.get('net_change') or {}).get('SM')) for r in records)
    sm_in_sum  = sum(_n((r.get('mvno_in') or {}).get('SM')) for r in records)
    sm_out_sum = sum(_n((r.get('mvno_out') or {}).get('SM')) for r in records)
    km_in_sum  = sum(_n((r.get('mvno_in') or {}).get('KM')) for r in records)
    lm_in_sum  = sum(_n((r.get('mvno_in') or {}).get('LM')) for r in records)
    km_out_sum = sum(_n((r.get('mvno_out') or {}).get('KM')) for r in records)
    lm_out_sum = sum(_n((r.get('mvno_out') or {}).get('LM')) for r in records)
    mvno_in_sum= sum(_n((r.get('mvno_in') or {}).get('계')) for r in records)
    mvno_out_sum=sum(_n((r.get('mvno_out') or {}).get('계')) for r in records)
    mno_out_sum= sum(_n((r.get('mno_out') or {}).get('계')) for r in records)
    km_net_sum = sum(_n((r.get('net_change') or {}).get('KM')) for r in records)
    lm_net_sum = sum(_n((r.get('net_change') or {}).get('LM')) for r in records)
    mvno_net_sum=sum(_n((r.get('net_change') or {}).get('계')) for r in records)
    mno_net_sum= sum(_n((r.get('net_change') or {}).get('MNO계')) for r in records)
    s_net_sum  = sum(_n((r.get('net_change') or {}).get('S')) for r in records)
    k_net_sum  = sum(_n((r.get('net_change') or {}).get('K')) for r in records)
    l_net_sum  = sum(_n((r.get('net_change') or {}).get('L')) for r in records)
    total_sum  = sum(_n(r.get('total')) for r in records)
    total_mno  = sum(_n(r.get('total_mno')) for r in records)
    total_mvno = sum(_n(r.get('total_mvno')) for r in records)

    # 마지막 레코드의 누적값 (월 누적 기준)
    last = records[-1]
    cum_t_out  = _n((last.get('cum_mno_out') or {}).get('S'))
    cum_sm_net = _n((last.get('cum_net') or {}).get('SM'))
    cum_sm_in  = _n((last.get('cum_mvno_in') or {}).get('SM'))
    cum_in_tot = _n((last.get('cum_mvno_in') or {}).get('계'))

    # bw보정 일평균
    avg_t_out  = round(t_out_sum / total_bw, 1) if total_bw else 0
    avg_sm_net = round(sm_net_sum / total_bw, 1) if total_bw else 0
    avg_sm_in  = round(sm_in_sum / total_bw, 1) if total_bw else 0
    avg_mvno_in= round(mvno_in_sum / total_bw, 1) if total_bw else 0
    avg_mno_out= round(mno_out_sum / total_bw, 1) if total_bw else 0

    # SM M/S
    sm_in_ms   = _pct(sm_in_sum, mvno_in_sum)
    sm_out_ms  = _pct(sm_out_sum, mvno_out_sum)

    # 군별 합산
    s_gun = s_net_sum + sm_net_sum
    k_gun = k_net_sum + km_net_sum
    l_gun = l_net_sum + lm_net_sum

    return {
        'records': records,
        'dates': [r['_date'] for r in records],
        'start': records[0]['_date'],
        'end': records[-1]['_date'],
        'days': len(records),
        'total_bw': round(total_bw, 2),
        'total_bw_ai': round(total_bw_ai, 2),
        # 합계
        't_out_sum': t_out_sum,
        'sm_net_sum': sm_net_sum,
        'sm_in_sum': sm_in_sum,
        'sm_out_sum': sm_out_sum,
        'km_in_sum': km_in_sum, 'lm_in_sum': lm_in_sum,
        'km_out_sum': km_out_sum, 'lm_out_sum': lm_out_sum,
        'mvno_in_sum': mvno_in_sum, 'mvno_out_sum': mvno_out_sum,
        'mno_out_sum': mno_out_sum,
        'km_net_sum': km_net_sum, 'lm_net_sum': lm_net_sum,
        'mvno_net_sum': mvno_net_sum, 'mno_net_sum': mno_net_sum,
        's_net_sum': s_net_sum, 'k_net_sum': k_net_sum, 'l_net_sum': l_net_sum,
        'total_sum': total_sum, 'total_mno': total_mno, 'total_mvno': total_mvno,
        # 누적 (마지막 레코드)
        'cum_t_out': cum_t_out, 'cum_sm_net': cum_sm_net,
        'cum_sm_in': cum_sm_in, 'cum_in_tot': cum_in_tot,
        # bw보정 일평균
        'avg_t_out': avg_t_out, 'avg_sm_net': avg_sm_net,
        'avg_sm_in': avg_sm_in, 'avg_mvno_in': avg_mvno_in,
        'avg_mno_out': avg_mno_out,
        # M/S
        'sm_in_ms': sm_in_ms, 'sm_out_ms': sm_out_ms,
        # 군별
        's_gun': s_gun, 'k_gun': k_gun, 'l_gun': l_gun,
        # 마지막 레코드 fc값
        'fc_low': last.get('fc_low'), 'fc_mid': last.get('fc_mid'),
        'fc_high': last.get('fc_high'), 'fc_on_track': last.get('fc_on_track'),
    }


def _get_goals(year: int, month: int) -> tuple:
    """
    (t_out_goal, sm_net_goal, sm_ms_goal) 반환.
    [v1.3] 하드코딩 GOALS_BY_MONTH 제거 → target_goal_reader 단일 소스로 위임.
    forecast_excel.py가 이 함수를 그대로 import해서 쓰고 있어서
    함수 시그니처/이름은 유지하고 내부 구현만 교체함 (호출부 수정 불필요).
    """
    try:
        from target_goal_reader import get_goals_tuple
        return get_goals_tuple(year, month)
    except Exception:
        return (34000, -5000, 20.0)  # 최후 폴백


def _build_period_text(agg: dict, title: str, period_type: str,
                       prev_agg: dict = None) -> str:
    """집계 데이터로 context 텍스트 생성"""
    if not agg:
        return f"[{title}] 데이터 없음"

    # 월별 목표 추출
    try:
        _start = agg.get('start', '')
        _sy, _sm = int(_start[:4]), int(_start[5:7])
        _t_out_goal, _sm_net_goal, _sm_ms_goal = _get_goals(_sy, _sm)
        _sm_goal_val = _sm_net_goal if _sm_net_goal is not None else -5000
    except Exception:
        _t_out_goal, _sm_goal_val, _sm_ms_goal = 36000, -5000, 19.0

    L = []
    sep = '━' * 28

    L.append(f"[MVNO {period_type} AI컨텍스트 | {title}]")
    L.append(f"※ 모든 수치는 확정값. 재계산 금지. 해석만 할 것.")
    L.append(f"기간: {agg['start']} ~ {agg['end']} ({agg['days']}일 / 영업일수 {agg['total_bw']})")

    # [추가 20260924] SUMMARY 블록 - ktoa_context_builder.py(일간)와 동일한 패턴으로
    # "이 블록만 읽어도 이번 주기 핵심 파악 가능"하게 설계. 사장님 피드백("일간분석 보면
    # 오늘 시장 전반을 알 수 있어야, 인사이트 잘 빼야") 반영해 주간/월간도 동일 원칙 적용.
    _alerts, _normals = [], []
    _t_out_pct = _pct(agg['cum_t_out'], _t_out_goal) if _t_out_goal else 0
    if agg['cum_t_out'] > _t_out_goal:
        _alerts.append(f"T Out 누적 {agg['cum_t_out']:,}건이 이미 월목표({_t_out_goal:,}건) 초과")
    elif agg.get('fc_low') and not agg.get('fc_on_track'):
        _alerts.append(f"T Out 마감예측 목표 초과 위험 (누적 {agg['cum_t_out']:,}건, 소진율 {_t_out_pct:.0f}%)")
    else:
        _normals.append(f"T Out 소진율 {_t_out_pct:.0f}% — 목표 이내 관리 중")

    _remaining = agg['cum_sm_net'] - _sm_goal_val
    if _sm_goal_val < 0:
        if _remaining < -1000:
            _alerts.append(f"SM순증 목표 잔여여유 {_sign(_remaining)}건 — 위험 수위 (누적 {_sign(agg['cum_sm_net'])} / 목표 {_sm_goal_val:,}건 이내)")
        elif _remaining < 0:
            _alerts.append(f"SM순증 목표 잔여여유 {_sign(_remaining)}건 — 관리 필요")
        else:
            _normals.append(f"SM순증 잔여여유 {_sign(_remaining)}건 — 여유 있음")

    if agg['sm_in_ms'] < _sm_ms_goal - 2:
        _alerts.append(f"SM신규 M/S {agg['sm_in_ms']:.1f}% — 목표 {_sm_ms_goal:.0f}% 대비 {agg['sm_in_ms']-_sm_ms_goal:+.1f}%p 미달")
    else:
        _normals.append(f"SM신규 M/S {agg['sm_in_ms']:.1f}% — 목표 {_sm_ms_goal:.0f}% 대비 {agg['sm_in_ms']-_sm_ms_goal:+.1f}%p")

    _BASE_OUT = 19.4
    if agg['sm_out_ms'] > _BASE_OUT + 0.5:
        _alerts.append(f"SM해지 M/S {agg['sm_out_ms']:.1f}% — 기준선({_BASE_OUT}%) 초과 악화")
    else:
        _normals.append(f"SM해지 M/S {agg['sm_out_ms']:.1f}% — 기준선({_BASE_OUT}%) 이내")

    if prev_agg and prev_agg.get('avg_t_out', 0) > 0:
        _t_diff_pct = _pct(agg['avg_t_out'] - prev_agg['avg_t_out'], prev_agg['avg_t_out'])
        if abs(_t_diff_pct) >= 15:
            _dir = "감소 ✅" if _t_diff_pct < 0 else "증가 ⚠️"
            _alerts.append(f"T Out 일평균 전기 대비 {_t_diff_pct:+.1f}% {_dir} (이상치)")

    L.append(f"\n{sep}\n■ SUMMARY (AI 해석 우선순위)\n{sep}")
    for a in _alerts:
        L.append(f"  ⚠️ ALERT: {a}")
    for n in _normals:
        L.append(f"  ✅ NORMAL: {n}")
    if not _alerts and not _normals:
        L.append(f"  ℹ️ 데이터 부족")
    if agg['total_sum']:
        L.append(f"  시장 규모: MVNO가 MNO의 {_pct(agg['total_mvno'], agg['total_mno']):.1f}%")
    L.append(f"※ 상세 수치는 하단 각 섹션 참조")

    # ── 시장 사이즈
    L.append(f"\n{sep}\n■ 시장 사이즈\n{sep}")
    L.append(f"MNP 총량: {agg['total_sum']:,}건 / 영업일수 일평균: {round(agg['total_sum']/agg['total_bw']):,}건" if agg['total_bw'] else "MNP 총량: N/A")
    if agg['total_sum']:
        L.append(f"MNO: {agg['total_mno']:,}건({_pct(agg['total_mno'],agg['total_sum']):.1f}%) / MVNO: {agg['total_mvno']:,}건({_pct(agg['total_mvno'],agg['total_sum']):.1f}%)")
    L.append(f"MVNO IN 영업일수 일평균: {agg['avg_mvno_in']:,}건 / MNO Out 영업일수 일평균: {agg['avg_mno_out']:,}건")

    # ── T Out
    L.append(f"\n{sep}\n■ T Out (SKT MNO→MVNO) ★목표지표 1순위\n{sep}")
    L.append(f"기간 합계: {agg['t_out_sum']:,}건 / 영업일수 일평균: {agg['avg_t_out']:,}건")
    L.append(f"월 목표: {_t_out_goal:,}건 이하")
    if prev_agg and prev_agg.get('avg_t_out', 0) > 0:
        diff = agg['avg_t_out'] - prev_agg['avg_t_out']
        sign = '+' if diff >= 0 else ''
        _pct_str = f'({sign}{_pct(diff, prev_agg["avg_t_out"]):.1f}%)' if prev_agg['avg_t_out'] > 0 else '(전기 데이터 없음)'
        L.append(f"전기 대비: {sign}{diff:.1f}건/일 {_pct_str} {'개선 ✅' if diff < 0 else '악화 ⚠️'}")
    if agg.get('fc_low'):
        track = '달성 가능 ✅' if agg.get('fc_on_track') else '목표 초과 위험 ⚠️'
        L.append(f"월마감 예측(DB): {agg['fc_low']:,}~{agg['fc_mid']:,}건 → {track}")

    # ── SM 순증감
    L.append(f"\n{sep}\n■ SM 순증감 ★목표지표 2순위\n{sep}")
    L.append(f"기간 합계: {_sign(agg['sm_net_sum'])}건 / 영업일수 일평균: {_sign(int(agg['avg_sm_net']))}건")
    L.append(f"월 목표: {_sm_goal_val:,}건 이내")
    if prev_agg:
        diff_n = agg['avg_sm_net'] - prev_agg['avg_sm_net']
        sign_n = '+' if diff_n >= 0 else ''
        L.append(f"전기 대비: {sign_n}{diff_n:.1f}건/일 {'개선 ✅' if diff_n > 0 else '악화 ⚠️'}")

    # ── MVNO IN
    L.append(f"\n{sep}\n■ MVNO IN (신규)\n{sep}")
    L.append(f"SM: {agg['sm_in_sum']:,}건 / KM: {agg['km_in_sum']:,}건 / LM: {agg['lm_in_sum']:,}건 / 계: {agg['mvno_in_sum']:,}건")
    L.append(f"SM M/S: {agg['sm_in_ms']:.1f}% (목표 {_sm_ms_goal:.0f}% {'✅' if agg['sm_in_ms'] >= _sm_ms_goal else '미달 ⚠️'}) / 영업일수 일평균: {agg['avg_sm_in']:,}건")
    if prev_agg:
        diff_ms = agg['sm_in_ms'] - prev_agg['sm_in_ms']
        L.append(f"전기 SM M/S 대비: {diff_ms:+.1f}%p {'개선 ✅' if diff_ms > 0 else '악화 ⚠️'}")

    # ── MVNO OUT
    L.append(f"\n{sep}\n■ MVNO OUT (해지)\n{sep}")
    L.append(f"SM: {agg['sm_out_sum']:,}건({agg['sm_out_ms']:.1f}%) / KM: {agg['km_out_sum']:,}건 / LM: {agg['lm_out_sum']:,}건 / 계: {agg['mvno_out_sum']:,}건")
    BASE_SM_OUT = 19.4
    diff_out = agg['sm_out_ms'] - BASE_SM_OUT
    L.append(f"SM 해지 M/S: {agg['sm_out_ms']:.1f}% (12월 기준선 {BASE_SM_OUT}% 대비 {diff_out:+.1f}%p {'악화 ⚠️' if diff_out > 0 else '개선 ✅'})")

    # ── 순증감 제로섬
    L.append(f"\n{sep}\n■ 순증감 (제로섬)\n{sep}")
    L.append(f"MVNO: SM {_sign(agg['sm_net_sum'])} / KM {_sign(agg['km_net_sum'])} / LM {_sign(agg['lm_net_sum'])} / 계 {_sign(agg['mvno_net_sum'])}")
    L.append(f"MNO:  S  {_sign(agg['s_net_sum'])} / K  {_sign(agg['k_net_sum'])} / L  {_sign(agg['l_net_sum'])} / 계 {_sign(agg['mno_net_sum'])}")
    zero = agg['mvno_net_sum'] + agg['mno_net_sum']
    L.append(f"제로섬 검증: {zero:+,}건 {'✅' if abs(zero) <= 10 else '확인필요 ⚠️'}")
    L.append(f"")
    L.append(f"군별 합산 포지션:")
    L.append(f"  S군(SKT MNO+SM): {_sign(agg['s_gun'])}건")
    L.append(f"  K군(KT MNO+KM):  {_sign(agg['k_gun'])}건")
    L.append(f"  L군(LGU MNO+LM): {_sign(agg['l_gun'])}건")

    # ── 일별 트렌드 테이블 (최대 10일)
    records = agg.get('records', [])
    if records:
        L.append(f"\n{sep}\n■ 일별 트렌드\n{sep}")
        L.append(f"날짜        영업일수  T-Out  보정   SM순증  SM신규  SM신규%")
        for r in records[-10:]:  # 최근 10일
            bw = _f(r.get('bw_manual') or r.get('bw_ai_prev') or 1.0)
            t = _n((r.get('mno_out') or {}).get('S'))
            t_adj = round(t / bw) if bw else t
            sn = _n((r.get('net_change') or {}).get('SM'))
            si = _n((r.get('mvno_in') or {}).get('SM'))
            si_tot = _n((r.get('mvno_in') or {}).get('계'))
            ms = _pct(si, si_tot)
            L.append(f"{r['_date']}  {_bw_fmt(bw):>4}  {t:>6,}  {t_adj:>6,}  {_sign(sn):>7}  {si:>6,}  {ms:.1f}%")

    return '\n'.join(L)


# ============================================================
# 주차별 Context
# ============================================================

def _get_week_key(date_str: str) -> str:
    """날짜 → 주차 키 (예: 2026-W19)"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{dt.year}-W{dt.isocalendar()[1]:02d}"


def _get_week_range(year: int, week: int) -> tuple:
    """주차 → (시작일, 종료일) 문자열"""
    # ISO 주차 기준 월요일~일요일
    jan4 = _date(year, 1, 4)
    start = jan4 + timedelta(weeks=week-1, days=-jan4.weekday())
    end = start + timedelta(days=6)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def save_weekly_context(end_date_str: str) -> bool:
    """
    end_date_str 기준 주차의 context 생성/저장
    ktoa_scraper에서 토요일 20:01에 호출
    """
    try:
        db = _get_db()
        dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        week_key = _get_week_key(end_date_str)
        year, week = dt.year, dt.isocalendar()[1]
        start_str, end_str = _get_week_range(year, week)

        # 해당 주 레코드 수집
        records = _collect_daily_records(start_str, end_str)
        if not records:
            log.warning(f"[weekly] 데이터 없음: {week_key}")
            return False

        agg = _aggregate_records(records)

        # 전주 비교
        prev_start, prev_end = _get_week_range(year, week-1) if week > 1 else _get_week_range(year-1, 52)
        prev_records = _collect_daily_records(prev_start, prev_end)
        prev_agg = _aggregate_records(prev_records) if prev_records else None

        title = f"{week_key} ({start_str}~{end_str})"
        text = _build_period_text(agg, title, "주차별", prev_agg)

        db.collection('ktoa_context_week').document(week_key).set({
            'week_key': week_key,
            'start_date': start_str,
            'end_date': end_str,
            'text': text,
            'saved_at': datetime.now(KST),
            'version': 'v1.0',
        })
        log.info(f"[weekly] 저장 완료: {week_key} ({len(text):,}자)")
        return True

    except Exception as e:
        log.error(f"[save_weekly_context] 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ============================================================
# 순기별 Context (1순기: 1~10일, 2순기: 11~20일, 3순기: 21~말일)
# ============================================================

def _get_decade_key(date_str: str) -> str:
    """날짜 → 순기 키 (예: 2026-05-1, 2026-05-2, 2026-05-3)"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    d = dt.day
    decade = 1 if d <= 10 else 2 if d <= 20 else 3
    return f"{dt.year}-{dt.month:02d}-{decade}"


def _get_decade_range(year: int, month: int, decade: int) -> tuple:
    """순기 → (시작일, 종료일) 문자열"""
    last_day = monthrange(year, month)[1]
    if decade == 1:
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-10"
    elif decade == 2:
        return f"{year}-{month:02d}-11", f"{year}-{month:02d}-20"
    else:
        return f"{year}-{month:02d}-21", f"{year}-{month:02d}-{last_day:02d}"


def save_decade_context(end_date_str: str) -> bool:
    """
    end_date_str 기준 순기의 context 생성/저장
    ktoa_scraper에서 10일/20일/말일 20:01에 호출
    """
    try:
        db = _get_db()
        dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        decade_key = _get_decade_key(end_date_str)
        decade = int(decade_key[-1])
        start_str, end_str = _get_decade_range(dt.year, dt.month, decade)

        records = _collect_daily_records(start_str, end_str)
        if not records:
            log.warning(f"[decade] 데이터 없음: {decade_key}")
            return False

        agg = _aggregate_records(records)

        # 전순기 비교
        if decade == 1:
            prev_month = dt.month - 1 if dt.month > 1 else 12
            prev_year = dt.year if dt.month > 1 else dt.year - 1
            prev_start, prev_end = _get_decade_range(prev_year, prev_month, 3)
        else:
            prev_start, prev_end = _get_decade_range(dt.year, dt.month, decade-1)
        prev_records = _collect_daily_records(prev_start, prev_end)
        prev_agg = _aggregate_records(prev_records) if prev_records else None

        decade_name = ['1순기(1~10일)', '2순기(11~20일)', '3순기(21~말일)'][decade-1]
        title = f"{dt.year}년 {dt.month}월 {decade_name} ({start_str}~{end_str})"
        text = _build_period_text(agg, title, "순기별", prev_agg)

        db.collection('ktoa_context_decade').document(decade_key).set({
            'decade_key': decade_key,
            'start_date': start_str,
            'end_date': end_str,
            'decade': decade,
            'text': text,
            'saved_at': datetime.now(KST),
            'version': 'v1.0',
        })
        log.info(f"[decade] 저장 완료: {decade_key} ({len(text):,}자)")
        return True

    except Exception as e:
        log.error(f"[save_decade_context] 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ============================================================
# 월별 Context
# ============================================================

def save_monthly_context(year: int, month: int) -> bool:
    """
    월별 context 생성/저장
    ktoa_scraper에서 말일 20:01에 호출
    """
    try:
        db = _get_db()
        last_day = monthrange(year, month)[1]
        start_str = f"{year}-{month:02d}-01"
        end_str   = f"{year}-{month:02d}-{last_day:02d}"
        month_key = f"{year}-{month:02d}"

        records = _collect_daily_records(start_str, end_str)
        if not records:
            log.warning(f"[monthly] 데이터 없음: {month_key}")
            return False

        agg = _aggregate_records(records)

        # 전월 비교
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        prev_last  = monthrange(prev_year, prev_month)[1]
        prev_start = f"{prev_year}-{prev_month:02d}-01"
        prev_end   = f"{prev_year}-{prev_month:02d}-{prev_last:02d}"
        prev_records = _collect_daily_records(prev_start, prev_end)
        prev_agg = _aggregate_records(prev_records) if prev_records else None

        title = f"{year}년 {month}월 전체 ({start_str}~{end_str})"
        text = _build_period_text(agg, title, "월별", prev_agg)

        db.collection('ktoa_context_month').document(month_key).set({
            'month_key': month_key,
            'year': year,
            'month': month,
            'start_date': start_str,
            'end_date': end_str,
            'text': text,
            'saved_at': datetime.now(KST),
            'version': 'v1.0',
        })
        log.info(f"[monthly] 저장 완료: {month_key} ({len(text):,}자)")
        return True

    except Exception as e:
        log.error(f"[save_monthly_context] 실패: {e}")
        import traceback; traceback.print_exc()
        return False


# ============================================================
# Backfill 함수들
# ============================================================

def backfill_weekly(start_date: str, end_date: str) -> int:
    """주차별 context 일괄 생성"""
    saved = 0
    sd = datetime.strptime(start_date, '%Y-%m-%d')
    ed = datetime.strptime(end_date, '%Y-%m-%d')

    # 각 주의 토요일(주 마지막 날) 기준으로 생성
    cur = sd
    seen_weeks = set()
    while cur <= ed:
        week_key = _get_week_key(cur.strftime('%Y-%m-%d'))
        if week_key not in seen_weeks:
            # 해당 주의 토요일 찾기
            year, week = cur.year, cur.isocalendar()[1]
            _, week_end = _get_week_range(year, week)
            week_end_dt = datetime.strptime(week_end, '%Y-%m-%d')
            # end_date 초과 시 end_date 사용
            actual_end = min(week_end_dt, ed)
            ok = save_weekly_context(actual_end.strftime('%Y-%m-%d'))
            if ok:
                saved += 1
                log.info(f"backfill_weekly: {week_key} 완료")
            seen_weeks.add(week_key)
        cur += timedelta(days=1)

    log.info(f"backfill_weekly 완료: {start_date}~{end_date}, {saved}건")
    return saved


def backfill_decade(start_date: str, end_date: str) -> int:
    """순기별 context 일괄 생성"""
    saved = 0
    sd = datetime.strptime(start_date, '%Y-%m-%d')
    ed = datetime.strptime(end_date, '%Y-%m-%d')

    seen = set()
    cur = sd
    while cur <= ed:
        dk = _get_decade_key(cur.strftime('%Y-%m-%d'))
        if dk not in seen:
            decade = int(dk[-1])
            year, month = cur.year, cur.month
            _, decade_end = _get_decade_range(year, month, decade)
            actual_end = min(datetime.strptime(decade_end, '%Y-%m-%d'), ed)
            ok = save_decade_context(actual_end.strftime('%Y-%m-%d'))
            if ok:
                saved += 1
                log.info(f"backfill_decade: {dk} 완료")
            seen.add(dk)
        cur += timedelta(days=1)

    log.info(f"backfill_decade 완료: {start_date}~{end_date}, {saved}건")
    return saved


def backfill_monthly(start_year: int, start_month: int,
                     end_year: int, end_month: int) -> int:
    """월별 context 일괄 생성"""
    saved = 0
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        ok = save_monthly_context(year, month)
        if ok:
            saved += 1
            log.info(f"backfill_monthly: {year}-{month:02d} 완료")
        month += 1
        if month > 12:
            month = 1
            year += 1

    log.info(f"backfill_monthly 완료: {saved}건")
    return saved


# ============================================================
# 조회 함수 (context_bundler에서 호출)
# ============================================================

def get_period_context(intent: str, date_str: str) -> list:
    """
    질문 intent에 따라 적절한 period context 조회
    context_bundler._attach_context_texts에서 호출

    intent 매핑:
      'weekly'  → ktoa_context_week
      'decade'  → ktoa_context_decade
      'monthly' → ktoa_context_month
    """
    try:
        db = _get_db()

        if intent == 'weekly':
            # 해당 날짜 포함 주차 + 전주
            keys = []
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            for offset in range(2):
                target = dt - timedelta(weeks=offset)
                keys.append(_get_week_key(target.strftime('%Y-%m-%d')))
            results = []
            for k in keys:
                doc = db.collection('ktoa_context_week').document(k).get()
                if doc.exists and doc.to_dict().get('text'):
                    results.append({'key': k, 'text': doc.to_dict()['text']})
            return results

        elif intent == 'decade':
            # 해당 순기 + 전순기
            keys = []
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            cur_key = _get_decade_key(date_str)
            keys.append(cur_key)
            # 전순기
            decade = int(cur_key[-1])
            if decade == 1:
                prev_month = dt.month - 1 if dt.month > 1 else 12
                prev_year = dt.year if dt.month > 1 else dt.year - 1
                keys.append(f"{prev_year}-{prev_month:02d}-3")
            else:
                keys.append(f"{dt.year}-{dt.month:02d}-{decade-1}")
            results = []
            for k in keys:
                doc = db.collection('ktoa_context_decade').document(k).get()
                if doc.exists and doc.to_dict().get('text'):
                    results.append({'key': k, 'text': doc.to_dict()['text']})
            return results

        elif intent == 'monthly':
            # 해당 월 + 전월
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            keys = [f"{dt.year}-{dt.month:02d}"]
            prev_month = dt.month - 1 if dt.month > 1 else 12
            prev_year = dt.year if dt.month > 1 else dt.year - 1
            keys.append(f"{prev_year}-{prev_month:02d}")
            results = []
            for k in keys:
                doc = db.collection('ktoa_context_month').document(k).get()
                if doc.exists and doc.to_dict().get('text'):
                    results.append({'key': k, 'text': doc.to_dict()['text']})
            return results

        return []

    except Exception as e:
        log.warning(f"[get_period_context] 실패: {e}")
        return []


# ============================================================
# CLI 실행
# ============================================================

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if len(sys.argv) < 2:
        print("사용법:")
        print("  python ktoa_context_period_builder.py weekly 2026-01-01 2026-05-11")
        print("  python ktoa_context_period_builder.py decade 2026-01-01 2026-05-11")
        print("  python ktoa_context_period_builder.py monthly 2026 1 2026 5")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'weekly':
        count = backfill_weekly(sys.argv[2], sys.argv[3])
        print(f"주차별 backfill 완료: {count}건")

    elif cmd == 'decade':
        count = backfill_decade(sys.argv[2], sys.argv[3])
        print(f"순기별 backfill 완료: {count}건")

    elif cmd == 'monthly':
        count = backfill_monthly(int(sys.argv[2]), int(sys.argv[3]),
                                 int(sys.argv[4]), int(sys.argv[5]))
        print(f"월별 backfill 완료: {count}건")

    else:
        print(f"알 수 없는 명령: {cmd}")