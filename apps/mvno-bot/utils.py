#!/usr/bin/env python3
"""
utils.py — 공통 유틸리티

[수정 이력]
v1.0 | 2026-04-09 | 최초 작성
  - ktoa_daily_to_record(): main.py에서 분리
    context_bundler.py / data_aggregator.py가 main.py를 import하면
    순환참조(circular import)가 발생하므로 이 파일로 이동
  - main.py, context_bundler.py, data_aggregator.py 모두 여기서 import
"""

from datetime import datetime


def ktoa_daily_to_record(doc_id: str, d: dict) -> dict:
    """
    ktoa_daily Firestore 문서 → 분석용 record 포맷 변환 (어댑터)

    ktoa_daily 구조:
      mvno_in   : {SM, KM, LM, 계}   당일 MVNO IN
      mno_out   : {S, K, L, 계}      당일 MNO Out (T Out)
      net_change: {SM, KM, LM, 계}   당일 순증감
      mvno_out  : {SM, KM, LM, 계}   당일 MVNO Out
      cum_mvno_in, cum_mno_out, cum_net, cum_mvno_out  (월 누적)
      bw_final, bw_ai_prev, bw_performance             (영업일수)
    """
    mi   = d.get('mvno_in',    {})
    mno  = d.get('mno_out',    {})
    net  = d.get('net_change', {})
    mo   = d.get('mvno_out',   {})
    cmi  = d.get('cum_mvno_in',  {})
    cmno = d.get('cum_mno_out',  {})
    cnet = d.get('cum_net',      {})
    cmo  = d.get('cum_mvno_out', {})

    parsed_data = {
        # 당일
        '당일_마감': {
            'SM': mi.get('SM', 0), 'KM': mi.get('KM', 0),
            'LM': mi.get('LM', 0), '계': mi.get('계', 0),
            'S':  mno.get('S', 0), 'K':  mno.get('K', 0), 'L': mno.get('L', 0),
        },
        '당일_MNO_Out': {
            'S': mno.get('S', 0), 'K': mno.get('K', 0),
            'L': mno.get('L', 0), '계': mno.get('계', 0),
        },
        '당일_순증감': {
            'SM': net.get('SM', 0), 'KM': net.get('KM', 0), 'LM': net.get('LM', 0),
            'S':  net.get('SM', 0), 'K':  net.get('KM', 0), 'L':  net.get('LM', 0),
            '계': net.get('계', 0),
        },
        '당일_MVNO_MNP_해지': {
            'SM': mo.get('SM', 0), 'KM': mo.get('KM', 0), 'LM': mo.get('LM', 0),
            'S':  mo.get('SM', 0), 'K':  mo.get('KM', 0), 'L':  mo.get('LM', 0),
            '계': mo.get('계', 0),
        },
        # 누적 (레거시 S/K/L 키 호환 포함)
        '누적_MNO_Out': {
            'S': cmno.get('S', 0), 'K': cmno.get('K', 0),
            'L': cmno.get('L', 0), '계': cmno.get('계', 0),
        },
        '누적_순증감': {
            'SM': cnet.get('SM', 0), 'KM': cnet.get('KM', 0), 'LM': cnet.get('LM', 0),
            'S':  cnet.get('SM', 0), 'K':  cnet.get('KM', 0), 'L':  cnet.get('LM', 0),
            '계': cnet.get('계', 0),
        },
        '누적_신규': {
            'SM': cmi.get('SM', 0), 'KM': cmi.get('KM', 0), 'LM': cmi.get('LM', 0),
            'S':  cmi.get('SM', 0), 'K':  cmi.get('KM', 0), 'L':  cmi.get('LM', 0),
            '계': cmi.get('계', 0),
        },
        '누적_MVNO_MNP_해지': {
            'SM': cmo.get('SM', 0), 'KM': cmo.get('KM', 0), 'LM': cmo.get('LM', 0),
            'S':  cmo.get('SM', 0), 'K':  cmo.get('KM', 0), 'L':  cmo.get('LM', 0),
            '계': cmo.get('계', 0),
        },
        # 영업일수
        'bw_final':       d.get('bw_final'),
        'bw_performance': d.get('bw_performance'),
        'bw_ai_prev':     d.get('bw_ai_prev'),
    }

    # 날짜/요일/공휴일 계산
    try:
        import holidays as _hol
        dt2       = datetime.strptime(doc_id, '%Y-%m-%d')
        kr_hol    = _hol.KR()
        is_holiday = dt2.date() in kr_hol
        is_weekend = dt2.weekday() >= 5
        weekday_kr = ['월요일','화요일','수요일','목요일','금요일','토요일','일요일'][dt2.weekday()]
        day_type   = '공휴일' if is_holiday else ('주말' if is_weekend else '평일')
    except Exception:
        weekday_kr = ''
        day_type   = '평일'
        is_weekend = False
        is_holiday = False

    return {
        'date':        doc_id,
        'year':        int(doc_id[:4]),
        'month':       int(doc_id[5:7]),
        'day':         int(doc_id[8:10]),
        'weekday':     weekday_kr,
        'is_weekend':  is_weekend,
        'is_holiday':  is_holiday,
        'day_type':    day_type,
        'type':        'daily',
        'data':        parsed_data,
        # 자주 쓰이는 필드 최상위 노출
        'mvno_in':     mi,
        'mno_out':     mno,
        'net_change':  net,
        'mvno_out':    mo,
        'cum_mvno_in': cmi,
        'cum_mno_out': cmno,
        'cum_net':     cnet,
        'bw_final':    d.get('bw_final'),
    }