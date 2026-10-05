#!/usr/bin/env python3
"""
ktoa_context_builder.py  v_cb | 2026-06-10 | 영업일수 기반 예측 줄 제거 (DB fc값으로 통일)
v1.0
작성일: 2026-05-13

[수정 이력]
v1.8 | 2026-06-18 | GOALS_BY_MONTH 하드코딩 딕셔너리 완전 제거 (Claude)
  - target_goal_reader.get_goals_tuple(year, month) 호출로 교체
  - 이 파일과 ktoa_context_period_builder.py가 각자 따로 들고 있던 사본 제거
    (2026-01 sm_net_goal이 두 파일에서 서로 다르게 박혀있던 사례 있었음)
  - 목표값은 Firestore ktoa_config/target_goal/monthly/{YYYY-MM}에서 조회
    (update_target_goal.py로 DB 생성 완료 시 단일 소스 완성)
v1.6 | 2026-05-20 | SUMMARY 블록 추가 (AI 해석 우선순위 자동 생성)
  - Header 직후 ■ SUMMARY 섹션 삽입
  - ⚠️ ALERT / ✅ NORMAL 자동 판별 (T Out 이상치/목표, SM순증, SM해지 M/S)
  - 다른 AI 시스템이 SUMMARY만 읽어도 핵심 파악 가능하도록 설계
v1.5 | 2026-05-13 | 월별 텍스트 동적화 + 목표 방향 수정
  - "5월" 하드코딩 → f"{month}월" 동적으로 전체 교체
  - 1월/2월/3월 SM 순증 목표 양수로 수정
  - _sm_goal_label: 양수/음수 목표 표현 구분
  - remaining_goal: cum_sm_net - _sm_goal_val 로 수정
v1.4 | 2026-05-13 | 월별 목표 동적 적용 + 데이터 없음 처리
  - GOALS_BY_MONTH: 월별 T Out/SM순증/SM M/S 목표 동적 적용
  - MNO IN/OUT 없을 때 "데이터 없음(2026-05-07 이전)" 표시
  - 전월 동기 0건 나누기 오류 방지
  - MNO 데이터 없으면 제로섬 검증 스킵
v1.2 | 2026-05-13 | fc Low/Mid/High 정렬 보정 + 잔여여유 표현 개선
  - _fc3(): DB 저장 순서 오류 대비 오름차순 정렬 보정
  - SM 순증감 잔여여유: 초과 시 "목표 초과: N건 이미 초과" 명확 표현
v1.1 | 2026-05-13 | 계산 오류 4건 수정
  - SM 신규 이상치 판단: M/S% 비교로 변경 (건수×비율 곱 오류 수정)
  - needed_ms: 잔여기간 필요 M/S% 계산식 수정 (수백만% 오류 수정)
  - 전월동기 T Out 라벨 명확화
  - 시장사이즈 전월동기: total 미존재 필드 참조 오류 수정
v1.0 | 2026-05-13 | 신규 생성
  - ktoa_scraper.py에서 분리 (단일 책임 원칙)
  - build_context_message(): AI 질의응답용 컨텍스트 텍스트 생성
  - save_context_message(): ktoa_context/{date} Firestore 저장
  - backfill_context(): 과거 날짜 일괄 재생성
  - 저장 구조: ktoa_context/{YYYY-MM-DD} → {date, text, saved_at, version}
"""

import logging
from datetime import datetime, timedelta, timezone

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


def _save_context_message_internal(date_str: str, daily: dict, _result: dict = None) -> None:
    """
    [v3.6] 일마감 후 AI 질의응답용 컨텍스트 메시지 생성 → ktoa_context/{date_str} 저장
    - 모든 수치를 Python에서 계산 완료 후 텍스트로 저장
    - AI는 이 텍스트를 읽고 해석만 수행 (재계산 금지)
    - 포함 내용: 영업일수, 시장사이즈, T Out, SM순증감, MVNO IN/OUT,
                MNO Out, MNO IN/OUT전체, 순증감 제로섬, 트렌드, 목표현황, AI해석가이드
    """
    from calendar import monthrange
    from datetime import datetime, timedelta
    from ktoa_firestore import _get_db

    # bw_engine 없는 환경(mvno-bot) 대비 인라인 폴백
    try:
        from bw_engine import is_zero_day
    except ImportError:
        def is_zero_day(ds):
            return datetime.strptime(ds, '%Y-%m-%d').weekday() == 6

    db = _get_db()
    if not db:
        return

    try:
        year  = int(date_str[:4])
        month = int(date_str[5:7])
        day   = int(date_str[8:10])
        last_day = monthrange(year, month)[1]
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        weekday_names = ['월','화','수','목','금','토','일']
        weekday_kr = weekday_names[dt.weekday()]
        day_type = '주말' if dt.weekday() >= 5 else '평일'

        # ── 헬퍼 함수들 ──────────────────────────────────────
        def _bw_fmt(v):
            """영업일수 표시: 1.000→1.0, 0.971→0.97"""
            if v is None:
                return 'N/A'
            f = float(v)
            if f == int(f):
                return f"{f:.1f}"
            s = f"{f:.2f}".rstrip('0')
            return s if not s.endswith('.') else s + '0'

        def _n(v, default=0):
            """숫자 안전 추출"""
            return int(v) if v else default

        def _pct(a, b):
            """비율 계산"""
            return round(a / b * 100, 1) if b else 0.0

        def _fc3(fc_dict, key):
            """fc Low/Mid/High 추출 — 정렬 보정 포함"""
            d = (fc_dict.get(key) or {}) if fc_dict else {}
            lo = d.get('low')
            mi = d.get('mid')
            hi = d.get('high')
            if lo is None and mi is None:
                return 'N/A'
            vals = sorted([v for v in [lo, mi, hi] if v is not None])
            if len(vals) == 3:
                lo, mi, hi = vals[0], vals[1], vals[2]
            elif len(vals) == 2:
                lo, hi = vals[0], vals[1]
            def _fmt(x):
                return f"{x:,}건" if x is not None else '-'
            return f"Low {_fmt(lo)} / Mid {_fmt(mi)} / High {_fmt(hi)}"

        def _sign(v):
            return f"+{v:,}" if v >= 0 else f"{v:,}"

        # ── 당일 데이터 추출 ──────────────────────────────────
        mvno_in   = daily.get('mvno_in',   {}) or {}
        mvno_out  = daily.get('mvno_out',  {}) or {}
        mno_out   = daily.get('mno_out',   {}) or {}
        mno_in    = daily.get('mno_in',    {}) or {}
        mno_out_all = daily.get('mno_out_all', {}) or {}
        net       = daily.get('net_change', {}) or {}
        cum_mi    = daily.get('cum_mvno_in',    {}) or {}
        cum_mo    = daily.get('cum_mno_out',    {}) or {}
        cum_mout  = daily.get('cum_mvno_out',   {}) or {}
        cum_net   = daily.get('cum_net',        {}) or {}
        cum_mno_in    = daily.get('cum_mno_in',    {}) or {}
        cum_mno_out_all = daily.get('cum_mno_out_all', {}) or {}
        total     = _n(daily.get('total'))
        total_mno = _n(daily.get('total_mno'))
        total_mvno= _n(daily.get('total_mvno'))

        fc_mno_out  = daily.get('fc_mno_out',  {}) or {}
        fc_mvno_in  = daily.get('fc_mvno_in',  {}) or {}
        fc_mvno_out = daily.get('fc_mvno_out', {}) or {}
        fc_net_db   = daily.get('fc_net',      {}) or {}
        fc_low  = daily.get('fc_low')
        fc_mid  = daily.get('fc_mid')
        fc_high = daily.get('fc_high')
        fc_on_track = daily.get('fc_on_track', False)

        # ── 영업일수 계산 ──────────────────────────────────────
        today_bw_man = float(daily.get('bw_manual') or daily.get('bw_ai_prev') or 1.0)
        today_bw_ai  = float(daily.get('bw_ai_prev') or 1.0)

        cum_bw_man = 0.0
        cum_bw_ai  = 0.0
        rem_bw_man = 0.0
        rem_bw_ai  = 0.0
        elapsed_days = 0

        for d in range(1, last_day + 1):
            ds = f'{year:04d}-{month:02d}-{d:02d}'
            if is_zero_day(ds):
                continue
            doc = db.collection('ktoa_daily').document(ds).get()
            dd  = doc.to_dict() if doc.exists else {}
            bw_man = float(dd.get('bw_manual') or dd.get('bw_ai_prev') or 1.0)
            bw_ai  = float(dd.get('bw_ai_prev') or 0.0)
            if d <= day:
                cum_bw_man += bw_man
                cum_bw_ai  += bw_ai
                if bw_man > 0:
                    elapsed_days += 1
            else:
                rem_bw_man += bw_man
                rem_bw_ai  += bw_ai

        total_bw_man = cum_bw_man + rem_bw_man
        total_bw_ai  = cum_bw_ai  + rem_bw_ai

        # ── 영업일수 기반 일평균 ───────────────────────────────
        def _avg(val):
            return round(val / cum_bw_man, 0) if cum_bw_man > 0 else 0

        avg_t_out   = _avg(_n(cum_mo.get('S')))
        avg_sm_net  = _avg(_n(cum_net.get('SM')))
        avg_sm_in   = _avg(_n(cum_mi.get('SM')))
        avg_mno_out = _avg(_n(cum_mo.get('계')))
        avg_mvno_in = _avg(_n(cum_mi.get('계')))

        # ── 전주 4주 동일요일 데이터 수집 ──────────────────────
        same_wd_records = []  # [{date, bw, t_out, sm_net, sm_in_ms, sm_out_ms, mno_out_계, total}]
        for w in range(1, 5):
            prev_dt  = dt - timedelta(days=7 * w)
            prev_str = prev_dt.strftime('%Y-%m-%d')
            pdoc = db.collection('ktoa_daily').document(prev_str).get()
            if not pdoc.exists:
                continue
            pd = pdoc.to_dict()
            pbw = float(pd.get('bw_manual') or pd.get('bw_ai_prev') or 1.0)
            if pbw <= 0:
                continue
            p_mi    = pd.get('mvno_in',  {}) or {}
            p_mo    = pd.get('mno_out',  {}) or {}
            p_mout  = pd.get('mvno_out', {}) or {}
            p_net   = pd.get('net_change', {}) or {}
            p_total = _n(pd.get('total'))
            p_t_out = _n(p_mo.get('S'))
            p_mi_sm = _n(p_mi.get('SM'))
            p_mi_tot= _n(p_mi.get('계'))
            p_mout_sm = _n(p_mout.get('SM'))
            p_mout_tot= _n(p_mout.get('계'))
            p_mno_out_계 = _n(p_mo.get('계'))
            same_wd_records.append({
                'date'       : prev_str,
                'bw'         : pbw,
                'bw_fmt'     : _bw_fmt(pbw),
                't_out'      : p_t_out,
                't_out_adj'  : round(p_t_out / pbw) if pbw else p_t_out,
                'sm_net'     : _n(p_net.get('SM')),
                'sm_net_adj' : round(_n(p_net.get('SM')) / pbw) if pbw else 0,
                'sm_in_ms'   : _pct(p_mi_sm, p_mi_tot),
                'sm_out_ms'  : _pct(p_mout_sm, p_mout_tot),
                'mno_out_계' : p_mno_out_계,
                'mno_out_adj': round(p_mno_out_계 / pbw) if pbw else p_mno_out_계,
                'total'      : p_total,
                'total_adj'  : round(p_total / pbw) if pbw else p_total,
                # [추가 20260924] MVNO 시장 자체의 규모(신규 계) - "MVNO가 MNO의 X% 규모"만
                # 있으면 활발/저조 판단 근거가 없어서, MVNO 시장 신규 자체의 4주 동일요일
                # 평균 대비 추세를 계산해 판단 근거로 삼음 (사장님 지시: "MVNO 시장위주로,
                # 최근 대비해서 어떤지")
                'mvno_in_tot'    : p_mi_tot,
                'mvno_in_tot_adj': round(p_mi_tot / pbw) if pbw else p_mi_tot,
            })

        def _wd_avg(key):
            vals = [r[key] for r in same_wd_records if r.get(key) is not None]
            return round(sum(vals) / len(vals)) if vals else 0

        wd_avg_t_out   = _wd_avg('t_out_adj')
        wd_avg_sm_net  = _wd_avg('sm_net_adj')
        wd_avg_sm_ms   = round(sum(r['sm_in_ms'] for r in same_wd_records) / len(same_wd_records), 1) if same_wd_records else 0
        wd_avg_mno_out = _wd_avg('mno_out_adj')
        wd_avg_total   = _wd_avg('total_adj')
        wd_avg_mvno_in = _wd_avg('mvno_in_tot_adj')

        # 이상치 판단 (±15%)
        def _anomaly(today_val, avg_val, label):
            if avg_val == 0:
                return f"{label}: 비교 불가"
            diff_pct = (today_val - avg_val) / avg_val * 100
            mark = ''
            if abs(diff_pct) >= 15:
                mark = ' ← 이상치 ⚠️'
            elif abs(diff_pct) >= 10:
                mark = ' ← 주목'
            sign = '+' if diff_pct >= 0 else ''
            return f"{label}: 오늘 {today_val:,} vs 4주평균 {avg_val:,} ({sign}{diff_pct:.1f}%){mark}"

        # ── 전월 동기 데이터 수집 ──────────────────────────────
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        prev_cum_doc = None
        for d2 in range(day, 0, -1):
            ds2 = f'{prev_year:04d}-{prev_month:02d}-{d2:02d}'
            pdoc2 = db.collection('ktoa_daily').document(ds2).get()
            if pdoc2.exists:
                pd2 = pdoc2.to_dict()
                if pd2.get('cum_mvno_in'):
                    prev_cum_doc = pd2
                    break

        prev_sync = {}
        if prev_cum_doc:
            pc_mi  = prev_cum_doc.get('cum_mvno_in',  {}) or {}
            pc_mo  = prev_cum_doc.get('cum_mno_out',  {}) or {}
            pc_net = prev_cum_doc.get('cum_net',       {}) or {}
            pc_bw  = cum_bw_man  # 경과 영업일수 동일 기준으로 비교
            prev_sync = {
                't_out'  : _n(pc_mo.get('S')),
                'sm_net' : _n(pc_net.get('SM')),
                'sm_in'  : _n(pc_mi.get('SM')),
                'sm_in_tot': _n(pc_mi.get('계')),
                'total'  : _n(prev_cum_doc.get('total')),
            }

        # ── 최근 5영업일 트렌드 ────────────────────────────────
        trend_rows = []
        check_dt = dt
        found = 0
        for _ in range(30):
            ds3 = check_dt.strftime('%Y-%m-%d')
            tdoc = db.collection('ktoa_daily').document(ds3).get()
            if tdoc.exists:
                td = tdoc.to_dict()
                tbw = float(td.get('bw_manual') or td.get('bw_ai_prev') or 0)
                t_mi  = td.get('mvno_in',  {}) or {}
                t_mo  = td.get('mno_out',  {}) or {}
                t_mout= td.get('mvno_out', {}) or {}
                t_net = td.get('net_change', {}) or {}
                t_mi_sm  = _n(t_mi.get('SM'))
                t_mi_tot = _n(t_mi.get('계'))
                t_mout_sm= _n(t_mout.get('SM'))
                t_mout_tot=_n(t_mout.get('계'))
                t_t_out  = _n(t_mo.get('S'))
                t_adj    = round(t_t_out / tbw) if tbw > 0 else t_t_out
                if t_mi_tot > 0 or t_t_out > 0:
                    wk = weekday_names[check_dt.weekday()]
                    dtype = '주말' if check_dt.weekday() >= 5 else '평일'
                    trend_rows.append({
                        'date'    : ds3,
                        'wd'      : wk,
                        'dtype'   : dtype,
                        'bw'      : _bw_fmt(tbw),
                        't_out'   : t_t_out,
                        't_adj'   : t_adj,
                        'sm_net'  : _n(t_net.get('SM')),
                        'sm_in'   : t_mi_sm,
                        'sm_in_ms': _pct(t_mi_sm, t_mi_tot),
                        'sm_out_ms': _pct(t_mout_sm, t_mout_tot),
                        'mno_out' : _n(t_mo.get('계')),
                    })
                    found += 1
                    if found >= 5:
                        break
            check_dt -= timedelta(days=1)
        trend_rows.reverse()

        # ── 월별 목표 — target_goal_reader 단일 소스로 조회 (하드코딩 제거) ──
        try:
            from target_goal_reader import get_goals_tuple
            _t_out_goal, _sm_net_goal, _sm_ms_goal = get_goals_tuple(year, month)
        except Exception as _goal_e:
            log.warning(f"target_goal_reader 조회 실패, 폴백값 사용: {_goal_e}")
            _t_out_goal, _sm_net_goal, _sm_ms_goal = 34000, -5000, 20.0
        _sm_goal_val = _sm_net_goal if _sm_net_goal is not None else -5000
        _sm_goal_label = (
            f"+{_sm_goal_val:,}건 이상" if _sm_goal_val > 0
            else f"{_sm_goal_val:,}건 이내" if _sm_goal_val < 0
            else "목표 없음"
        )

        # [수정 20260924] fc_on_track(위 157행에서 daily.get('fc_on_track')으로 읽은 값)은
        # 이 파일 밖의 별도 배치 잡이 미리 계산해 ktoa_daily 문서에 저장해둔 값이라, DB의
        # 월 목표(t_out_goal)가 나중에 바뀌어도 재계산되지 않을 위험이 있음 - SM 순증감
        # 목표를 -6000으로 바꿨을 때 겪었던 캐시 문제와 동일 패턴. fc_mno_out.S.mid(T Out
        # 마감예측)를 지금 막 조회한 최신 목표(_t_out_goal)와 직접 비교해 라이브로
        # 재계산 - fc_mno_out.S.mid가 없을 때만(구형 문서 등) 저장된 값으로 폴백.
        _s_fc_mid_live = (fc_mno_out.get('S') or {}).get('mid')
        if _s_fc_mid_live is not None:
            fc_on_track = _s_fc_mid_live <= _t_out_goal

        # ── 수치 계산 완료 → 메시지 생성 ──────────────────────
        L = []  # 메시지 라인

        def sec(title):
            L.append(f"\n{'━'*28}")
            L.append(f"■ {title}")
            L.append('━'*28)

        # 오늘 당일 bw 보정값
        today_t_out   = _n(mno_out.get('S'))
        today_t_adj   = round(today_t_out / today_bw_man) if today_bw_man > 0 else today_t_out
        today_mi_sm   = _n(mvno_in.get('SM'))
        today_mi_tot  = _n(mvno_in.get('계'))
        today_mout_sm = _n(mvno_out.get('SM'))
        today_mout_tot= _n(mvno_out.get('계'))
        today_mno_out_계 = _n(mno_out.get('계'))
        today_mno_adj = round(today_mno_out_계 / today_bw_man) if today_bw_man > 0 else today_mno_out_계
        today_sm_net  = _n(net.get('SM'))
        today_total_adj = round(total / today_bw_man) if today_bw_man > 0 else total

        # 흡수율
        absorb_rate = _pct(today_mi_sm, today_t_out) if today_t_out else 0

        # Header
        L.append(f"[MVNO 일마감 AI컨텍스트 | {date_str}({weekday_kr}) | 20시 기준]")
        L.append("※ 모든 수치는 확정값. 재계산 금지. 해석만 할 것.")

        # ── SUMMARY 블록 (AI 해석 우선순위) ────────────────────
        # 이 블록만 읽어도 오늘 핵심 상황 파악 가능하도록 설계
        # 상세 수치는 하단 각 섹션 참조
        _sum_alerts  = []
        _sum_normals = []

        # [0] MVNO 시장 규모 활발/저조 판단 - [수정 20260924] 기존엔 "MVNO가 MNO의 X%
        # 규모"라는 정적 비율만 있어서 활발/저조를 판단할 근거가 없었음(비율이 높다고
        # 꼭 활발한 게 아님 - MNO쪽이 줄어도 비율은 오를 수 있음). MVNO 시장 자체의
        # 신규 건수를 4주 동일요일 평균과 비교해 활발/보통/저조를 판단하도록 변경
        # (사장님 지시: "MVNO시장 위주로, 최근 대비해서 어떤지")
        # [수정 20260924 2차] "영업일수 대비로 비교해야 - 공휴일은 당연히 적음" 지적
        # 반영: today_mi_tot(원본, bw 미보정)을 wd_avg_mvno_in(bw 보정된 4주 평균)과
        # 직접 비교하던 버그 수정 - 오늘도 영업일수로 보정한 today_mi_tot_adj를 사용
        # (T Out 등 다른 지표는 이미 today_t_adj처럼 보정해서 비교하고 있었는데
        # 이 지표만 보정을 빼먹었음)
        today_mi_tot_adj = round(today_mi_tot / today_bw_man) if today_bw_man > 0 else today_mi_tot
        _market_pct = ((today_mi_tot_adj - wd_avg_mvno_in) / wd_avg_mvno_in * 100) if wd_avg_mvno_in else 0
        if _market_pct >= 10:
            _market_judge = "활발"
        elif _market_pct <= -10:
            _market_judge = "저조"
        else:
            _market_judge = "보통"
        _market_line = (
            f"MVNO 시장 신규 {today_mi_tot:,}건(영업일수 {today_bw_man:.1f}일), "
            f"영업일수 1.0일 보정시 {today_mi_tot_adj:,}건 — 4주 동일요일 영업일수보정 평균"
            f"({wd_avg_mvno_in:,}건) 대비 {_market_pct:+.1f}% — {_market_judge} "
            f"(MNO 대비 규모: {_pct(total_mvno, total_mno):.1f}%)"
        )

        # [0-1] MNO Out 중 T Out 비중 - 평시(4주 동일요일 평균) 대비 판단
        # [추가 20260924 3차] 사장님 요청: "Mno out 중 t out 비율이 평시대비 낮은수준을
        # 유지하고 잇어 긍정적" 같은 해석을 daily 분석에 넣어달라 - 기존엔 섹션6 상세에
        # "4월 마감 45~50%" 하드코딩값만 있어서(9월 기준으로 이미 stale) daily 분석에
        # 반영 안 되고 있었음. 4주 동일요일 평균으로 동적 baseline 계산해 SUMMARY에 추가.
        # today_t_out/today_mno_out_계는 둘 다 당일 원본값이라 bw 나눠도 비율 자체는
        # 안 바뀌므로(분자분모 동일 bw로 상쇄) 원본값 그대로 비율 계산해도 무방.
        _tout_ratio_pct  = _pct(today_t_out, today_mno_out_계) if today_mno_out_계 else 0
        _tout_ratio_base = _pct(wd_avg_t_out, wd_avg_mno_out) if wd_avg_mno_out else 0
        _tout_ratio_diff = _tout_ratio_pct - _tout_ratio_base
        if _tout_ratio_diff <= -3:
            _tout_ratio_judge = "평시 대비 낮은 수준 — 긍정적 흐름"
        elif _tout_ratio_diff >= 3:
            _tout_ratio_judge = "평시 대비 높은 수준 — 주의"
        else:
            _tout_ratio_judge = "평시 수준 유지"
        _tout_ratio_line = (
            f"MNO Out 중 T Out 비중 {_tout_ratio_pct:.1f}%, 4주 동일요일 평균"
            f"({_tout_ratio_base:.1f}%) 대비 {_tout_ratio_diff:+.1f}%p — {_tout_ratio_judge}"
        )

        # [1] T Out 이상치 판단 (4주 동일요일 평균 대비 ±15%)
        _tout_pct = ((today_t_adj - wd_avg_t_out) / wd_avg_t_out * 100) if wd_avg_t_out else 0
        if abs(_tout_pct) >= 15:
            _dir = "↓ 감소" if _tout_pct < 0 else "↑ 증가"
            _sum_alerts.append(
                f"T Out 4주평균 대비 {_tout_pct:+.1f}% 이상치 "
                f"(오늘 {today_t_adj:,} vs 평균 {wd_avg_t_out:,}) {_dir}"
            )
        elif abs(_tout_pct) >= 10:
            _sum_alerts.append(
                f"T Out 4주평균 대비 {_tout_pct:+.1f}% 주목 구간 "
                f"(오늘 {today_t_adj:,} vs 평균 {wd_avg_t_out:,})"
            )

        # [2] T Out 월 목표 마감예측
        cum_t_out_pre = _n(cum_mo.get('S'))  # 섹션2보다 먼저 필요하므로 여기서 계산
        if not fc_on_track:
            _sum_alerts.append(
                f"T Out 마감예측 목표 초과 위험 "
                f"(누적 {cum_t_out_pre:,}건 / 목표 {_t_out_goal:,}건 이하)"
            )
        else:
            _sum_normals.append(
                f"T Out 소진율 {_pct(cum_t_out_pre, _t_out_goal):.1f}% — 목표 이내 관리 중"
            )

        # [3] SM 순증 목표 잔여여유
        cum_sm_net_pre  = _n(cum_net.get('SM'))
        remaining_pre   = cum_sm_net_pre - _sm_goal_val
        if _sm_goal_val < 0:  # 순감 한도 목표
            if remaining_pre < -1000:
                _sum_alerts.append(
                    f"SM순증 목표 잔여여유 {_sign(remaining_pre)}건 — 위험 수위 "
                    f"(누적 {_sign(cum_sm_net_pre)} / 목표 {_sm_goal_label})"
                )
            elif remaining_pre < 0:
                _sum_alerts.append(
                    f"SM순증 목표 잔여여유 {_sign(remaining_pre)}건 — 관리 필요 "
                    f"(누적 {_sign(cum_sm_net_pre)} / 목표 {_sm_goal_label})"
                )
            else:
                _sum_normals.append(
                    f"SM순증 잔여여유 {_sign(remaining_pre)}건 — 여유 있음"
                )

        # [4] SM 해지 M/S (기준선 19.4%)
        _BASE_OUT_MS = 19.4
        _sm_out_ms_pre = _pct(_n(mvno_out.get('SM')), _n(mvno_out.get('계')))
        if _sm_out_ms_pre > _BASE_OUT_MS + 0.5:
            _sum_alerts.append(
                f"SM해지 M/S {_sm_out_ms_pre:.1f}% — 기준선({_BASE_OUT_MS}%) 초과 악화"
            )
        else:
            _sum_normals.append(
                f"SM해지 M/S {_sm_out_ms_pre:.1f}% — 기준선({_BASE_OUT_MS}%) 이내"
            )

        # [5] SM 신규 M/S
        _sm_in_ms_pre = _pct(_n(mvno_in.get('SM')), _n(mvno_in.get('계')))
        if _sm_in_ms_pre >= _sm_ms_goal:
            _sum_normals.append(
                f"SM신규 M/S {_sm_in_ms_pre:.1f}% — 목표 {_sm_ms_goal:.0f}% 달성"
            )
        elif _sm_in_ms_pre >= _sm_ms_goal - 2:
            _sum_alerts.append(
                f"SM신규 M/S {_sm_in_ms_pre:.1f}% — 목표 {_sm_ms_goal:.0f}% 대비 "
                f"{_sm_in_ms_pre - _sm_ms_goal:+.1f}%p (근접 관리 중)"
            )
        else:
            _sum_alerts.append(
                f"SM신규 M/S {_sm_in_ms_pre:.1f}% — 목표 {_sm_ms_goal:.0f}% 대비 "
                f"{_sm_in_ms_pre - _sm_ms_goal:+.1f}%p 미달"
            )

        # [6] 최근 5영업일 SM순증감 추이 - [추가 20260925] 사장님 피드백: "과거대비
        # 오늘 실적 분석깊이가 얕다 - 그럼 미래 액션권고도 약해질 수밖에". trend_rows
        # (최근 5영업일, 섹션9에서 상세 표로만 쓰임)와 prev_sync(전월 동기, 섹션5/6/10
        # 상세에서만 쓰임)가 이미 계산돼 있는데 정작 daily 분석 SUMMARY엔 안 들어가고
        # 있었음 - 4주 동일요일 평균이라는 "한 시점 비교"만 있고, "오늘이 며칠째
        # 이어지는 흐름인지"(일시적 vs 구조적 악화·개선 구분)가 빠져있던 게 얕은 분석의
        # 원인. 연속 며칠 개선/악화인지 + 5일 평균을 SUMMARY에 추가해 지속성 판단 근거 제공.
        _trend5_line = ""
        if len(trend_rows) >= 2:
            _net_seq = [r['sm_net'] for r in trend_rows]
            _streak_dir, _streak_days = None, 0
            for _i in range(len(_net_seq) - 1, 0, -1):
                _diff = _net_seq[_i] - _net_seq[_i - 1]
                _d = "개선" if _diff > 0 else ("악화" if _diff < 0 else None)
                if _d is None:
                    break
                if _streak_dir is None:
                    _streak_dir, _streak_days = _d, 1
                elif _d == _streak_dir:
                    _streak_days += 1
                else:
                    break
            _trend5_avg_net = round(sum(_net_seq) / len(_net_seq))
            _trend5_avg_ms  = round(sum(r['sm_in_ms'] for r in trend_rows) / len(trend_rows), 1)
            _streak_note = f", {_streak_days}일 연속 {_streak_dir}" if _streak_dir and _streak_days >= 2 else ""
            _trend5_line = (
                f"최근 {len(trend_rows)}영업일 SM순증감 평균 {_sign(_trend5_avg_net)}건{_streak_note} "
                f"/ SM신규 M/S 5일평균 {_trend5_avg_ms:.1f}%"
            )

        # [7] 전월 동기 비교 - 같은 경과 영업일수 기준, 이번달이 전월보다 나은지/나쁜지
        _prevmonth_line = ""
        if prev_sync and cum_bw_man:
            _prev_net_avg = round(prev_sync['sm_net'] / cum_bw_man)
            _diff_prev = int(avg_sm_net) - _prev_net_avg
            _prevmonth_line = (
                f"SM순증감 일평균 {_sign(int(avg_sm_net))}건, 전월 동기({_sign(_prev_net_avg)}건) 대비 "
                f"{_sign(_diff_prev)}건 {'개선' if _diff_prev > 0 else '악화' if _diff_prev < 0 else '동일'}"
            )

        # SUMMARY 출력
        L.append(f"")
        L.append(f"{'━'*28}")
        L.append(f"■ SUMMARY (AI 해석 우선순위)")
        L.append(f"{'━'*28}")
        L.append(f"  📊 MARKET: {_market_line}")
        L.append(f"  📊 TOUT_RATIO: {_tout_ratio_line}")
        if _trend5_line:
            L.append(f"  📈 TREND5: {_trend5_line}")
        if _prevmonth_line:
            L.append(f"  📅 PREVMONTH: {_prevmonth_line}")
        if _sum_alerts:
            for _a in _sum_alerts:
                L.append(f"  ⚠️ ALERT: {_a}")
        if _sum_normals:
            for _n2 in _sum_normals:
                L.append(f"  ✅ NORMAL: {_n2}")
        if not _sum_alerts and not _sum_normals:
            L.append(f"  ℹ️ 데이터 부족 — 상세 섹션 참조")
        L.append(f"※ 상세 수치는 하단 각 섹션(0~11) 참조")

        # ── 섹션 0: 영업일수 ────────────────────────────────────
        sec("0. 영업일수")
        L.append(f"당일 영업일수: {_bw_fmt(today_bw_man)}")
        L.append(f"경과: {elapsed_days}영업일 / 경과 영업일수 합계: {_bw_fmt(cum_bw_man)}")
        L.append(f"잔여 영업일수: {_bw_fmt(rem_bw_man)}일")
        L.append(f"{month}월 전체 영업일수: {_bw_fmt(total_bw_man)}일")
        L.append(f"※ 월마감 DB예측은 AI영업일수({_bw_fmt(rem_bw_ai)}일 잔여) 기반")

        # ── 섹션 1: 시장 사이즈 ─────────────────────────────────
        sec("1. 시장 사이즈 (금일 번호이동 전체)")
        mvno_mno_ratio = _pct(total_mvno, total_mno) if total_mno else 0
        L.append(f"[당일 MNP 총량]")
        L.append(f"전체: {total:,}건 / 영업일수 보정: {today_total_adj:,}건")
        L.append(f"MNO: {total_mno:,}건({_pct(total_mno,total):.1f}%) / MVNO: {total_mvno:,}건({_pct(total_mvno,total):.1f}%)")
        L.append(f"MVNO가 MNO의 {mvno_mno_ratio:.1f}% 규모")
        if wd_avg_total:
            diff_total = _pct(today_total_adj - wd_avg_total, wd_avg_total)
            sign = '+' if diff_total >= 0 else ''
            L.append(f"전주 동일요일({weekday_kr}) 보정 평균: {wd_avg_total:,}건 → 오늘 {sign}{diff_total:.1f}%")
        L.append(f"")
        L.append(f"[MNO 시장]")
        for s_key, label in [('S','SKT'),('K','KT'),('L','LGU')]:
            mn_in  = _n(mno_in.get(s_key))
            mn_out = _n(mno_out_all.get(s_key))
            mn_net = mn_in - mn_out
            L.append(f"{label}({s_key}) — 수신: {mn_in:,}건 / 발신전체: {mn_out:,}건 / 순증감: {_sign(mn_net)}건")
        L.append(f"MNO 전체 순증감: {_sign(_n(net.get('MNO계')))}건")
        L.append(f"")
        L.append(f"[MVNO 시장]")
        L.append(f"SM: {today_mi_sm:,}건({_pct(today_mi_sm,today_mi_tot):.1f}%) / "
                 f"KM: {_n(mvno_in.get('KM')):,}건({_pct(_n(mvno_in.get('KM')),today_mi_tot):.1f}%) / "
                 f"LM: {_n(mvno_in.get('LM')):,}건({_pct(_n(mvno_in.get('LM')),today_mi_tot):.1f}%) / 계: {today_mi_tot:,}건")
        L.append(f"MVNO 전체 순증감: {_sign(_n(net.get('계')))}건 (MNO와 제로섬)")
        L.append(f"")
        L.append(f"[SKT 포지션]")
        L.append(f"T Out(SKT→MVNO): {today_t_out:,}건 — 전체 시장의 {_pct(today_t_out,total):.1f}%")
        L.append(f"SM 신규: {today_mi_sm:,}건 — MVNO 시장의 {_pct(today_mi_sm,today_mi_tot):.1f}% / 목표 19% 대비 {_pct(today_mi_sm,today_mi_tot)-19:+.1f}%p")
        L.append(f"SM 흡수율(SM신규÷T Out): {today_mi_sm:,}÷{today_t_out:,} = {absorb_rate:.1f}%")
        if absorb_rate >= 100:
            L.append(f"→ SKT 이탈 1명당 SM이 {absorb_rate/100:.2f}명 흡수, 타사 이탈분까지 흡수 중")
        else:
            L.append(f"→ T Out 대비 SM 흡수 부족, {100-absorb_rate:.1f}% 타사로 유출")
        L.append(f"")
        if same_wd_records:
            L.append(f"[전주 동일요일({weekday_kr}) 시장 사이즈 비교 — 영업일수 보정]")
            for r in same_wd_records:
                rd = r['date']
                L.append(f"  {rd}({weekday_kr}, 영업일수{r['bw_fmt']}): 전체 {r['total_adj']:,}건")
            L.append(f"  4주 {weekday_kr}요일 평균: {wd_avg_total:,}건")
            L.append(f"  오늘: {today_total_adj:,}건")
        L.append(f"")
        L.append(f"[월 누적 시장 사이즈]")
        L.append(f"MVNO 전체 누적 영업일수 일평균: {int(avg_mvno_in):,}건")
        L.append(f"MNO Out 영업일수 일평균: {int(avg_mno_out):,}건")

        # ── 섹션 2: T Out ───────────────────────────────────────
        sec("2. T Out (SKT MNO→MVNO) ★목표지표 1순위")
        cum_t_out = cum_t_out_pre  # SUMMARY에서 계산한 값 재사용
        L.append(f"[당일]")
        L.append(f"실적: {today_t_out:,}건 / 영업일수 보정: {today_t_adj:,}건")
        if same_wd_records:
            L.append(f"")
            L.append(f"전주 동일요일({weekday_kr}) 비교 — 영업일수 보정:")
            for r in same_wd_records:
                diff_v = today_t_adj - r['t_out_adj']
                sign = '+' if diff_v >= 0 else ''
                L.append(f"  {r['date']}({weekday_kr}, 영업일수{r['bw_fmt']}): {r['t_out_adj']:,}건 → 오늘 대비 {sign}{diff_v:,}건")
            diff_wd = today_t_adj - wd_avg_t_out
            sign_wd = '+' if diff_wd >= 0 else ''
            pct_wd  = _pct(diff_wd, wd_avg_t_out)
            L.append(f"  4주 {weekday_kr}요일 평균: {wd_avg_t_out:,}건 → 오늘 {sign_wd}{diff_wd:,}건 ({sign_wd}{pct_wd:.1f}%)")
            mark = ' ← 이상치 ⚠️' if abs(pct_wd) >= 15 else ' ← 주목' if abs(pct_wd) >= 10 else ' ← 정상범위'
            L.append(f"  이상치 판단(±15%기준): {abs(pct_wd):.1f}%{mark}")
        L.append(f"")
        L.append(f"[월 누적]")
        L.append(f"누적: {cum_t_out:,}건 / 영업일수 일평균: {int(avg_t_out):,}건")
        L.append(f"목표: {_t_out_goal:,}건 이하")
        fc_s_str = _fc3(fc_mno_out, 'S') if fc_mno_out.get('S') else (
            f"Low {fc_low:,}건 / Mid {fc_mid:,}건 / High {fc_high:,}건"
            if fc_low else 'N/A')
        track_mark = '✅' if fc_on_track else '⚠️'
        L.append(f"마감예측(DB): {fc_s_str} → {'달성 가능' if fc_on_track else '목표 초과 위험'} {track_mark}")
        # 영업일수 기반 예측 제거 → DB fc값(마감예측(DB))으로 통일
        if prev_sync:
            prev_t_avg = round(prev_sync['t_out'] / cum_bw_man) if cum_bw_man else 0
            diff_t = int(avg_t_out) - prev_t_avg
            sign_t = '+' if diff_t >= 0 else ''
            L.append(f"")
            L.append(f"전월 동기 비교:")
            L.append(f"  전월 동기 T Out 누적: {prev_sync['t_out']:,}건 / 영업일수 일평균: {prev_t_avg:,}건")
            _prev_t_pct = f"({sign_t}{_pct(diff_t,prev_t_avg):.1f}%)" if prev_t_avg > 0 else "(전월 데이터 없음)"
            L.append(f"  {month}월 동기 영업일수 일평균: {int(avg_t_out):,}건 → 전월 대비 {sign_t}{diff_t:,}건 {_prev_t_pct}")

        # ── 섹션 3: SM 순증감 ────────────────────────────────────
        sec("3. SM 순증감 ★목표지표 2순위")
        cum_sm_net = cum_sm_net_pre      # SUMMARY에서 계산한 값 재사용
        sm_net_adj = round(today_sm_net / today_bw_man) if today_bw_man else today_sm_net
        remaining_goal = remaining_pre   # SUMMARY에서 계산한 값 재사용
        L.append(f"[당일]")
        L.append(f"실적: {_sign(today_sm_net)}건 / 영업일수 보정: {_sign(sm_net_adj)}건")
        if same_wd_records:
            L.append(f"")
            L.append(f"전주 동일요일({weekday_kr}) 비교 — 영업일수 보정:")
            for r in same_wd_records:
                diff_v = sm_net_adj - r['sm_net_adj']
                sign = '+' if diff_v >= 0 else ''
                L.append(f"  {r['date']}({weekday_kr}, 영업일수{r['bw_fmt']}): {_sign(r['sm_net_adj'])}건 → 오늘 대비 {sign}{diff_v:,}건")
            diff_wd = sm_net_adj - wd_avg_sm_net
            sign_wd = '+' if diff_wd >= 0 else ''
            pct_wd2 = _pct(abs(diff_wd), abs(wd_avg_sm_net)) if wd_avg_sm_net != 0 else 0
            mark2 = ' ← 이상치 ⚠️' if pct_wd2 >= 15 else ' ← 주목' if pct_wd2 >= 10 else ' ← 정상범위'
            L.append(f"  4주 {weekday_kr}요일 평균: {_sign(wd_avg_sm_net)}건 → 오늘 {sign_wd}{diff_wd:,}건 차이{mark2}")
        L.append(f"")
        L.append(f"[월 누적]")
        L.append(f"누적: {_sign(cum_sm_net)}건 / 영업일수 일평균: {_sign(int(avg_sm_net))}건")
        L.append(f"목표: {_sm_goal_label} / 잔여 여유: {_sign(remaining_goal)}건")
        fc_sm_net_str = _fc3(fc_net_db, 'SM')
        net_track = (fc_net_db.get('SM') or {}).get('mid', -99999)
        # [수정 20260924] -5000 하드코딩 - SM 순증감 목표를 -6000으로 바꿔도 이 판정만
        # 옛 -5000 기준으로 계속 판단하던 버그. _sm_goal_val(방금 조회한 최신 목표)로 교체.
        net_ok = net_track >= _sm_goal_val if net_track != -99999 else fc_on_track
        L.append(f"마감예측(DB): {fc_sm_net_str} → {'달성 가능 ✅' if net_ok else '목표 초과 위험 ⚠️'}")
        pred_net_man = int(cum_sm_net + avg_sm_net * rem_bw_man)
        # 영업일수 기반 예측 제거
        if prev_sync:
            prev_net_avg = round(prev_sync['sm_net'] / cum_bw_man) if cum_bw_man else 0
            diff_n = int(avg_sm_net) - prev_net_avg
            sign_n = '+' if diff_n >= 0 else ''
            L.append(f"")
            L.append(f"전월 동기 비교:")
            L.append(f"  전월 동기 누적: {_sign(prev_sync['sm_net'])}건 / 일평균: {_sign(prev_net_avg)}건")
            _prev_net_pct = f"({sign_n}{_pct(abs(diff_n),max(1,abs(prev_net_avg))):.1f}%)" if prev_net_avg != 0 else "(전월 데이터 없음)"
            L.append(f"  {month}월 동기 일평균: {_sign(int(avg_sm_net))}건 → 전월 대비 {sign_n}{diff_n:,}건 {_prev_net_pct}")

        # ── 섹션 4: MVNO IN ──────────────────────────────────────
        sec("4. MVNO IN (신규)")
        cum_sm_in = _n(cum_mi.get('SM'))
        cum_in_tot= _n(cum_mi.get('계'))
        L.append(f"[당일]")
        L.append(f"SM: {today_mi_sm:,}건({_pct(today_mi_sm,today_mi_tot):.1f}%) / "
                 f"KM: {_n(mvno_in.get('KM')):,}건({_pct(_n(mvno_in.get('KM')),today_mi_tot):.1f}%) / "
                 f"LM: {_n(mvno_in.get('LM')):,}건({_pct(_n(mvno_in.get('LM')),today_mi_tot):.1f}%) / "
                 f"계: {today_mi_tot:,}건")
        L.append(f"SM M/S 목표 {_sm_ms_goal:.0f}% 대비: {_pct(today_mi_sm,today_mi_tot):.1f}% ({_pct(today_mi_sm,today_mi_tot)-_sm_ms_goal:+.1f}%p)")
        if same_wd_records:
            wd_sm_ms_str = ' / '.join([f"{r['date']}: {r['sm_in_ms']:.1f}%" for r in same_wd_records])
            L.append(f"전주 동일요일 SM M/S: {wd_sm_ms_str}")
            L.append(f"4주 평균: {wd_avg_sm_ms:.1f}% → 오늘 {_pct(today_mi_sm,today_mi_tot):.1f}%")
        L.append(f"")
        L.append(f"[월 누적]")
        L.append(f"SM: {cum_sm_in:,}건({_pct(cum_sm_in,cum_in_tot):.1f}%) / "
                 f"KM: {_n(cum_mi.get('KM')):,}건({_pct(_n(cum_mi.get('KM')),cum_in_tot):.1f}%) / "
                 f"LM: {_n(cum_mi.get('LM')):,}건({_pct(_n(cum_mi.get('LM')),cum_in_tot):.1f}%) / "
                 f"계: {cum_in_tot:,}건")
        L.append(f"영업일수 일평균: SM {int(avg_sm_in):,}건 / 계 {int(avg_mvno_in):,}건")
        L.append(f"마감예측(DB) SM: {_fc3(fc_mvno_in,'SM')} / 계: {_fc3(fc_mvno_in,'계')}")
        if cum_in_tot > 0:
            # 목표 M/S 달성 위해 잔여기간 필요 SM신규 비중
            # = (목표M/S×전체예상신규 - 현재SM누적) / 잔여예상전체신규
            _avg_in_tot = avg_mvno_in  # 영업일수 기반 전체 일평균
            _expected_total = cum_in_tot + _avg_in_tot * rem_bw_man
            _needed_sm = (_sm_ms_goal/100) * _expected_total - cum_sm_in
            _remaining_total = _avg_in_tot * rem_bw_man
            needed_ms = _pct(_needed_sm, _remaining_total) if _remaining_total > 0 else 0
            L.append(f"SM M/S {_sm_ms_goal:.0f}% 달성 위해 잔여기간 필요 M/S: 약 {needed_ms:.1f}%")
        if prev_sync:
            prev_sm_in_ms = _pct(prev_sync['sm_in'], prev_sync['sm_in_tot']) if prev_sync.get('sm_in_tot') else 0
            L.append(f"전월 동기: SM {prev_sync['sm_in']:,}건({prev_sm_in_ms:.1f}%) → {month}월: {cum_sm_in:,}건({_pct(cum_sm_in,cum_in_tot):.1f}%)")

        # ── 섹션 5: MVNO OUT ─────────────────────────────────────
        sec("5. MVNO OUT (해지)")
        cum_sm_out  = _n(cum_mout.get('SM'))
        cum_out_tot = _n(cum_mout.get('계'))
        sm_out_ms_today = _pct(today_mout_sm, today_mout_tot)
        sm_out_ms_cum   = _pct(cum_sm_out, cum_out_tot)
        BASE_SM_OUT_MS  = 19.4  # 12월 기준선
        L.append(f"[당일]")
        L.append(f"SM: {today_mout_sm:,}건({sm_out_ms_today:.1f}%) / "
                 f"KM: {_n(mvno_out.get('KM')):,}건({_pct(_n(mvno_out.get('KM')),today_mout_tot):.1f}%) / "
                 f"LM: {_n(mvno_out.get('LM')):,}건({_pct(_n(mvno_out.get('LM')),today_mout_tot):.1f}%) / "
                 f"계: {today_mout_tot:,}건")
        L.append(f"SM 해지 M/S: {sm_out_ms_today:.1f}% ← 12월 기준선 {BASE_SM_OUT_MS}% "
                 f"({'동일' if abs(sm_out_ms_today-BASE_SM_OUT_MS)<0.5 else ('개선 ✅' if sm_out_ms_today<BASE_SM_OUT_MS else '악화 ⚠️')})")
        if same_wd_records:
            wd_sm_out_str = ' / '.join([f"{r['date']}: {r['sm_out_ms']:.1f}%" for r in same_wd_records])
            L.append(f"전주 동일요일 SM 해지 M/S: {wd_sm_out_str}")
        L.append(f"")
        L.append(f"[월 누적]")
        L.append(f"SM: {cum_sm_out:,}건({sm_out_ms_cum:.1f}%) / "
                 f"KM: {_n(cum_mout.get('KM')):,}건({_pct(_n(cum_mout.get('KM')),cum_out_tot):.1f}%) / "
                 f"LM: {_n(cum_mout.get('LM')):,}건({_pct(_n(cum_mout.get('LM')),cum_out_tot):.1f}%) / "
                 f"계: {cum_out_tot:,}건")
        L.append(f"SM 해지 M/S vs 12월 기준선({BASE_SM_OUT_MS}%): 현재 {sm_out_ms_cum:.1f}%, "
                 f"{sm_out_ms_cum-BASE_SM_OUT_MS:+.1f}%p {'악화 ⚠️' if sm_out_ms_cum>BASE_SM_OUT_MS else '개선 ✅'}")
        L.append(f"마감예측(DB) SM: {_fc3(fc_mvno_out,'SM')} / 계: {_fc3(fc_mvno_out,'계')}")

        # ── 섹션 6: MNO Out (시장 과열 지표) ────────────────────
        sec("6. MNO Out (MNO→MVNO 이탈) — 시장 과열 지표")
        cum_mno_s = _n(cum_mo.get('S'))
        cum_mno_k = _n(cum_mo.get('K'))
        cum_mno_l = _n(cum_mo.get('L'))
        cum_mno_계 = _n(cum_mo.get('계'))
        BASELINE = {'2월': 3159, '3월': 3123, '4월': 2400}  # 일평균 기준선
        L.append(f"[당일]")
        L.append(f"S: {today_t_out:,}건({_pct(today_t_out,today_mno_out_계):.1f}%) / "
                 f"K: {_n(mno_out.get('K')):,}건({_pct(_n(mno_out.get('K')),today_mno_out_계):.1f}%) / "
                 f"L: {_n(mno_out.get('L')):,}건({_pct(_n(mno_out.get('L')),today_mno_out_계):.1f}%) / "
                 f"계: {today_mno_out_계:,}건 / 영업일수 보정: {today_mno_adj:,}건")
        L.append(f"기준선: 2월 일평균 {BASELINE['2월']:,}건 / 3월 {BASELINE['3월']:,}건 / 4월 {BASELINE['4월']:,}건")
        b_diff = today_mno_adj - BASELINE['4월']
        b_sign = '+' if b_diff >= 0 else ''
        L.append(f"오늘 {today_mno_adj:,}건 → 4월 대비 {b_sign}{b_diff:,}건 ({b_sign}{_pct(b_diff,BASELINE['4월']):.1f}%)")
        L.append(f"T Out 비중: {_pct(today_t_out,today_mno_out_계):.1f}% ← 4월 마감 45~50% {'범위 내 ✅' if 45<=_pct(today_t_out,today_mno_out_계)<=50 else '범위 이탈 ⚠️'}")
        if same_wd_records:
            L.append(f"")
            L.append(f"전주 동일요일({weekday_kr}) 비교:")
            for r in same_wd_records:
                L.append(f"  {r['date']}: {r['mno_out_adj']:,}건")
            diff_mno = today_mno_adj - wd_avg_mno_out
            sign_mno = '+' if diff_mno >= 0 else ''
            L.append(f"  4주 평균: {wd_avg_mno_out:,}건 → 오늘 {sign_mno}{diff_mno:,}건 ({sign_mno}{_pct(diff_mno,wd_avg_mno_out):.1f}%)")
        L.append(f"")
        L.append(f"[월 누적]")
        L.append(f"S: {cum_mno_s:,}건({_pct(cum_mno_s,cum_mno_계):.1f}%) / "
                 f"K: {cum_mno_k:,}건({_pct(cum_mno_k,cum_mno_계):.1f}%) / "
                 f"L: {cum_mno_l:,}건({_pct(cum_mno_l,cum_mno_계):.1f}%) / "
                 f"계: {cum_mno_계:,}건")
        L.append(f"영업일수 일평균: {int(avg_mno_out):,}건 (4월 전체 {BASELINE['4월']:,}건 대비 {int(avg_mno_out)-BASELINE['4월']:+,}건)")
        L.append(f"마감예측(DB) S: {_fc3(fc_mno_out,'S')} / 계: {_fc3(fc_mno_out,'계')}")

        # ── 섹션 7: MNO IN / MNO Out 전체 ───────────────────────
        sec("7. MNO IN / MNO Out 전체")
        L.append(f"[당일]")
        _has_mno_detail = bool(_n(mno_in.get('S')) or _n(mno_in.get('계')))
        if _has_mno_detail:
            L.append(f"MNO IN     S: {_n(mno_in.get('S')):,}건 / K: {_n(mno_in.get('K')):,}건 / L: {_n(mno_in.get('L')):,}건 / 계: {_n(mno_in.get('계')):,}건")
            L.append(f"MNO OUT전체 S: {_n(mno_out_all.get('S')):,}건 / K: {_n(mno_out_all.get('K')):,}건 / L: {_n(mno_out_all.get('L')):,}건 / 계: {_n(mno_out_all.get('계')):,}건")
            L.append(f"(MNO OUT전체 = MNO→타MNO + MNO→MVNO 합산)")
        else:
            L.append("MNO IN/OUT전체: 데이터 없음 (2026-05-07 이전 미수집)")
        L.append(f"")
        L.append(f"[월 누적]")
        _has_cum_mno = bool(_n(cum_mno_in.get('S')) or _n(cum_mno_in.get('계')))
        if _has_cum_mno:
            L.append(f"MNO IN     S: {_n(cum_mno_in.get('S')):,}건 / K: {_n(cum_mno_in.get('K')):,}건 / L: {_n(cum_mno_in.get('L')):,}건 / 계: {_n(cum_mno_in.get('계')):,}건")
            L.append(f"MNO OUT전체 S: {_n(cum_mno_out_all.get('S')):,}건 / K: {_n(cum_mno_out_all.get('K')):,}건 / L: {_n(cum_mno_out_all.get('L')):,}건 / 계: {_n(cum_mno_out_all.get('계')):,}건")
        else:
            L.append("MNO IN/OUT전체 월누적: 데이터 없음 (2026-05-07 이전 미수집)")

        # ── 섹션 8: 순증감 전체 (제로섬) ────────────────────────
        sec("8. 순증감 전체 (제로섬 구조)")
        net_sm  = _n(net.get('SM'));  net_km  = _n(net.get('KM'));  net_lm  = _n(net.get('LM'))
        net_mvno= _n(net.get('계')); net_s   = _n(net.get('S'));   net_k   = _n(net.get('K'))
        net_l   = _n(net.get('L'));  net_mno = _n(net.get('MNO계'))
        zero_sum= net_mvno + net_mno
        _has_mno_net = bool(net_s or net_k or net_l or net_mno)
        zero_ok = ('✅' if abs(zero_sum) <= 5 else '확인필요 ⚠️') if _has_mno_net else 'MNO 데이터 없음(스킵)'
        L.append(f"[당일 MVNO]")
        L.append(f"SM: {_sign(net_sm)}건 / KM: {_sign(net_km)}건 / LM: {_sign(net_lm)}건 / MVNO계: {_sign(net_mvno)}건")
        L.append(f"[당일 MNO]")
        L.append(f"S: {_sign(net_s)}건 / K: {_sign(net_k)}건 / L: {_sign(net_l)}건 / MNO계: {_sign(net_mno)}건")
        L.append(f"제로섬 검증: MVNO계({_sign(net_mvno)}) + MNO계({_sign(net_mno)}) = {_sign(zero_sum)} {zero_ok}")
        L.append(f"")
        # 군별 포지션
        s_gun = net_s + net_sm; k_gun = net_k + net_km; l_gun = net_l + net_lm
        L.append(f"[군별 포지션 — 통신사별 MNO+MVNO 합산 득실]")
        L.append(f"S군(SKT MNO+SM): MNO {_sign(net_s)}, SM {_sign(net_sm)} → S군 전체 {_sign(s_gun)}건")
        L.append(f"K군(KT MNO+KM):  MNO {_sign(net_k)}, KM {_sign(net_km)} → K군 전체 {_sign(k_gun)}건")
        L.append(f"L군(LGU MNO+LM): MNO {_sign(net_l)}, LM {_sign(net_lm)} → L군 전체 {_sign(l_gun)}건")
        # 제로섬 이동 패턴
        L.append(f"")
        L.append(f"제로섬 관점 — 오늘 번호이동 흐름:")
        losers  = [(k,v) for k,v in [('SM',net_sm),('KM',net_km),('LM',net_lm)] if v < 0]
        winners = [(k,v) for k,v in [('SM',net_sm),('KM',net_km),('LM',net_lm)] if v >= 0]
        if losers:
            L.append(f"  순감: {', '.join([f'{k} {_sign(v)}건' for k,v in losers])}")
        if winners:
            L.append(f"  순증: {', '.join([f'{k} {_sign(v)}건' for k,v in winners])}")
        L.append(f"")
        # 누적
        c_net_sm  = _n(cum_net.get('SM'));  c_net_km = _n(cum_net.get('KM'))
        c_net_lm  = _n(cum_net.get('LM'));  c_net_mvno= _n(cum_net.get('계'))
        c_net_s   = _n(cum_net.get('S'));   c_net_k  = _n(cum_net.get('K'))
        c_net_l   = _n(cum_net.get('L'));   c_net_mno = _n(cum_net.get('MNO계'))
        c_zero    = c_net_mvno + c_net_mno
        _has_cum_mno_net = bool(c_net_s or c_net_k or c_net_l or c_net_mno)
        c_zero_ok = ('✅' if abs(c_zero) <= 10 else '확인필요 ⚠️') if _has_cum_mno_net else 'MNO 데이터 없음(스킵)'
        L.append(f"[월 누적 MVNO]")
        L.append(f"SM: {_sign(c_net_sm)}건 / KM: {_sign(c_net_km)}건 / LM: {_sign(c_net_lm)}건 / MVNO계: {_sign(c_net_mvno)}건")
        L.append(f"[월 누적 MNO]")
        L.append(f"S: {_sign(c_net_s)}건 / K: {_sign(c_net_k)}건 / L: {_sign(c_net_l)}건 / MNO계: {_sign(c_net_mno)}건")
        L.append(f"제로섬 검증: {c_net_mvno+c_net_mno:+,}건 {c_zero_ok}")
        L.append(f"")
        cs_gun = c_net_s + c_net_sm; ck_gun = c_net_k + c_net_km; cl_gun = c_net_l + c_net_lm
        L.append(f"[군별 누적 포지션]")
        L.append(f"S군: MNO {_sign(c_net_s)}, SM {_sign(c_net_sm)} → S군 전체 {_sign(cs_gun)}건")
        L.append(f"K군: MNO {_sign(c_net_k)}, KM {_sign(c_net_km)} → K군 전체 {_sign(ck_gun)}건")
        L.append(f"L군: MNO {_sign(c_net_l)}, LM {_sign(c_net_lm)} → L군 전체 {_sign(cl_gun)}건")

        # ── 섹션 9: 최근 5영업일 트렌드 ─────────────────────────
        sec("9. 최근 5영업일 트렌드")
        L.append(f"날짜        요일 영업일수 T-Out  보정   SM순증  SM신규  SM신규% SM해지% MNOOut")
        for r in trend_rows:
            L.append(
                f"{r['date']}({r['wd']}) "
                f"{r['bw']:>4} "
                f"{r['t_out']:>6,} {r['t_adj']:>6,} "
                f"{_sign(r['sm_net']):>7} "
                f"{r['sm_in']:>6,} "
                f"{r['sm_in_ms']:>6.1f}% "
                f"{r['sm_out_ms']:>6.1f}% "
                f"{r['mno_out']:>6,}"
            )
        if trend_rows:
            avg_tout_tr = round(sum(r['t_adj'] for r in trend_rows) / len(trend_rows))
            avg_net_tr  = round(sum(r['sm_net'] for r in trend_rows) / len(trend_rows))
            avg_ms_tr   = round(sum(r['sm_in_ms'] for r in trend_rows) / len(trend_rows), 1)
            avg_mno_tr  = round(sum(r['mno_out'] for r in trend_rows) / len(trend_rows))
            L.append(f"5일평균      —    —   {avg_tout_tr:>6,}  {avg_tout_tr:>6,} "
                     f"{_sign(avg_net_tr):>7}       —  {avg_ms_tr:>6.1f}%      —  {avg_mno_tr:>6,}")

        # ── 섹션 10: 월 목표 달성 현황 ──────────────────────────
        sec("10. 월 목표 달성 현황")
        L.append(f"T Out(SKT):")
        L.append(f"  누적 {cum_t_out:,}건 / 목표 {_t_out_goal:,}건 / 소진율 {_pct(cum_t_out,_t_out_goal):.1f}%")
        L.append(f"  마감예측(DB): {fc_s_str} → {'달성 가능 ✅' if fc_on_track else '목표 초과 위험 ⚠️'}")
        L.append(f"")
        L.append(f"SM 순증감:")
        L.append(f"  누적 {_sign(cum_sm_net)}건 / 목표 {_sm_goal_label} / 잔여 여유 {_sign(remaining_goal)}건")
        L.append(f"  마감예측(DB): {fc_sm_net_str} → {'달성 가능 ✅' if net_ok else '목표 초과 위험 ⚠️'}")
        # 영업일수 기반 예측 제거 (DB fc값으로 통일)
        L.append(f"")
        L.append(f"SM 신규 M/S:")
        L.append(f"  현재 {_pct(cum_sm_in,cum_in_tot):.1f}% / 목표 19% / {_pct(cum_sm_in,cum_in_tot)-19:+.1f}%p")

        # ── 섹션 11: AI 해석 가이드 ─────────────────────────────
        sec("11. AI 해석 가이드")
        L.append(f"오늘 특성: {weekday_kr}요일 / {day_type}")
        L.append(f"영업일수 {_bw_fmt(today_bw_man)} → {'보정 불필요' if today_bw_man==1.0 else f'원값×{1/today_bw_man:.2f} 보정 필요'}")
        L.append(f"")
        L.append(f"이상치 판단 (최근 4주 동일요일 대비 ±15% 기준):")
        L.append(f"  {_anomaly(today_t_adj,   wd_avg_t_out,  'T Out')}")
        L.append(f"  SM 신규 M/S: 오늘 {_pct(today_mi_sm,today_mi_tot):.1f}% vs 4주평균 {wd_avg_sm_ms:.1f}% ({_pct(today_mi_sm,today_mi_tot)-wd_avg_sm_ms:+.1f}%p)")
        L.append(f"  {_anomaly(today_mno_adj, wd_avg_mno_out,'MNO Out')}")
        L.append(f"  SM 순증감: 오늘 {_sign(sm_net_adj)}건 vs 4주평균 {_sign(wd_avg_sm_net)}건")
        L.append(f"")
        if prev_sync:
            L.append(f"전월 동기 요약:")
            t_diff = int(avg_t_out) - round(prev_sync['t_out']/cum_bw_man) if cum_bw_man else 0
            n_diff = int(avg_sm_net)- round(prev_sync['sm_net']/cum_bw_man) if cum_bw_man else 0
            L.append(f"  T Out: {month}월 동기 {t_diff:+,}건/일 {'개선 ✅' if t_diff<0 else '악화 ⚠️'}")
            L.append(f"  SM순증: {month}월 동기 {n_diff:+,}건/일 {'개선 ✅' if n_diff>0 else '악화 ⚠️'}")
            L.append(f"")
        L.append(f"핵심 시사점 (이 3가지 중심으로 해석):")
        # 자동 시사점 생성
        points = []
        if fc_on_track:
            points.append(f"T Out 목표 관리 양호 (DB예측 달성 가능)")
        else:
            points.append(f"T Out 목표 경계/초과 위험 — 잔여기간 관리 필요")
        if cum_sm_net < -4500:
            points.append(f"SM 순증감 목표 잔여 여유 {_sign(remaining_goal)}건 — 위험 수위")
        elif cum_sm_net < -3000:
            points.append(f"SM 순증감 누적 {_sign(cum_sm_net)}건 — 추이 모니터링")
        else:
            points.append(f"SM 순증감 목표 여유 충분")
        if _pct(today_mi_sm, today_mi_tot) < 17:
            points.append(f"SM 신규 M/S {_pct(today_mi_sm,today_mi_tot):.1f}% — 목표 19% 대비 낮은 수준")
        else:
            points.append(f"SM 신규 M/S {_pct(today_mi_sm,today_mi_tot):.1f}% — 목표 대비 관리 수준")
        for p in points:
            L.append(f"  - {p}")

        # ── Firestore 저장 ────────────────────────────────────────
        text = '\n'.join(L)
        if _result is not None:
            _result['text'] = text
            return
        from datetime import datetime as _dt2, timezone as _tz, timedelta as _td2
        KST = _tz(timedelta(hours=9))
        db.collection('ktoa_context').document(date_str).set({
            'date'    : date_str,
            'text'    : text,
            'saved_at': _dt2.now(KST),
            'version' : 'v1.0',
        })
        log.info(f"[_save_context_message] 저장 완료: {date_str} ({len(text):,}자)")

    except Exception as e:
        log.error(f"[_save_context_message] 실패: {e}")
        import traceback; traceback.print_exc()


# ============================================================
# Public API
# ============================================================

def build_context_message(date_str: str, daily: dict) -> str:
    """
    컨텍스트 메시지 텍스트만 생성 (저장 없음)
    테스트/미리보기용
    """
    # 내부 함수에서 text만 추출하기 위해 임시 저장 방식 활용
    import io
    lines_capture = []
    _original = log.info

    # daily 데이터로 텍스트 생성 (저장 스킵)
    # _save_context_message_internal의 text 생성 부분을 재활용
    # → 실제로는 save하되 반환값으로 text 노출하는 save 함수 활용
    result = {}
    _save_context_message_internal(date_str, daily, _result=result)
    return result.get('text', '')


def save_context_message(date_str: str, daily: dict) -> bool:
    """
    컨텍스트 메시지 생성 + ktoa_context/{date_str} 저장
    ktoa_scraper.py에서 호출하는 메인 함수

    반환: 성공 여부
    """
    try:
        _save_context_message_internal(date_str, daily)
        return True
    except Exception as e:
        log.error(f"[save_context_message] 실패: {e}")
        return False


def get_context_texts(date_str: str, days: int = 7) -> list:
    """
    ktoa_context에서 최근 N일치 텍스트 조회
    context_bundler.py에서 호출

    반환: [{"date": "2026-05-12", "text": "..."}, ...]  최신순
    """
    try:
        from datetime import datetime as _dt, timedelta as _td
        db = _get_db()
        results = []
        base = _dt.strptime(date_str, '%Y-%m-%d')
        for i in range(days):
            ds = (base - _td(days=i)).strftime('%Y-%m-%d')
            doc = db.collection('ktoa_context').document(ds).get()
            if doc.exists:
                d = doc.to_dict()
                if d.get('text'):
                    results.append({'date': ds, 'text': d['text']})
        log.info(f"[get_context_texts] {date_str} 기준 {len(results)}건 조회")
        return results
    except Exception as e:
        log.warning(f"[get_context_texts] 실패: {e}")
        return []


def backfill_context(start_date: str, end_date: str) -> int:
    """
    과거 날짜 ktoa_context 일괄 재생성
    사용법: python ktoa_context_builder.py backfill 2026-04-01 2026-05-12

    반환: 저장 성공 건수
    """
    from datetime import datetime as _dt, timedelta as _td
    db = _get_db()
    base  = _dt.strptime(start_date, '%Y-%m-%d')
    end   = _dt.strptime(end_date,   '%Y-%m-%d')
    saved = 0
    cur   = base
    while cur <= end:
        ds   = cur.strftime('%Y-%m-%d')
        doc  = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            daily = doc.to_dict()
            if daily.get('mvno_in'):  # 실적 있는 날만
                ok = save_context_message(ds, daily)
                if ok:
                    saved += 1
                    log.info(f"backfill 저장: {ds}")
            else:
                log.info(f"backfill 스킵 (실적없음): {ds}")
        else:
            log.info(f"backfill 스킵 (문서없음): {ds}")
        cur += _td(days=1)
    log.info(f"backfill 완료: {start_date}~{end_date}, {saved}건 저장")
    return saved


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    if len(sys.argv) >= 4 and sys.argv[1] == 'backfill':
        count = backfill_context(sys.argv[2], sys.argv[3])
        print(f"backfill 완료: {count}건")
    elif len(sys.argv) >= 2:
        # 단일 날짜 테스트: python ktoa_context_builder.py 2026-05-12
        ds = sys.argv[1]
        db = _get_db()
        doc = db.collection('ktoa_daily').document(ds).get()
        if doc.exists:
            text = build_context_message(ds, doc.to_dict())
            print(text)
        else:
            print(f"데이터 없음: {ds}")
    else:
        print("사용법:")
        print("  python ktoa_context_builder.py 2026-05-12          # 단일 테스트")
        print("  python ktoa_context_builder.py backfill 2026-04-01 2026-05-12  # 일괄")