# -*- coding: utf-8 -*-
"""
gift_callback_handler.py - 사은품 버튼 클릭 처리 모듈

[수정 이력]
- v0.3 (2026-07-15) 7일 추이 버튼 추가
    * gift_trend_{provider_key} 콜백 처리
    * Firestore gift_daily_tier/{date}/{provider} → 7일 테이블 생성
- v0.2 (2026-07-09) 유모바일 직영 상세보기 추가
- v0.1 (2026-07-09) 최초 작성
"""

import os
import requests
from datetime import datetime, timezone, timedelta, date

TELEGRAM_TOKEN  = os.environ.get('TELEGRAM_BOT_TOKEN', '')
KST = timezone(timedelta(hours=9))

try:
    from core.firebase_handler import FirebaseHandler as _FH
    def get_db():
        return _FH().db
except ImportError:
    get_db = None

PROV_LABEL = {
    'umobile':        'U+유모바일 (모요)',
    'hello':          'LG헬로모바일',
    'skylife':        'KT스카이라이프',
    'ktm':            'KT엠모바일(모요)',
    'umobile_direct': 'U+유모바일 직영',
    'ktm_direct':     'KT엠모바일 직영',
}

DATAKEY_MIN_VAL = 200000  # core.gift_comparator.SUMMARY_MIN_VAL과 동일 기준(20만원)


def _man_short(v: int) -> str:
    if not v: return '-'
    m = v / 10000
    return f'{m:.0f}만' if m == int(m) else f'{m:.1f}만'


def _data_key_gb(dk: str) -> float:
    try:
        return float(dk.replace('gb', ''))
    except ValueError:
        return float('inf')


def _data_key_label(dk: str) -> str:
    gb = _data_key_gb(dk)
    if gb == float('inf'):
        return dk
    gb_str = str(int(gb)) if gb == int(gb) else str(gb)
    return f'{gb_str}GB'


def _answer_callback(callback_query_id: str, text: str = ''):
    requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery',
        json={'callback_query_id': callback_query_id, 'text': text},
        timeout=10)


def _send_message(chat_id, text: str):
    requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
        json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
        timeout=15)


def _get_trend_text(prov_key: str) -> str:
    """
    Firestore gift_daily_datakey에서 최근 7일 데이터 → 데이터제공량(GB) 단위 추이 테이블.

    [수정 20260925] 기존엔 gift_daily_tier(TIER_ORDER 6구간 - 5GB이하/5~9GB/...)를
    읽어서, 요약 메시지·K CUP 비교는 이미 실제 GB 단위로 바뀌었는데 "📈 추이" 버튼만
    누르면 옛날 구간별 표가 나오는 문제가 있었음(사장님 지적: "아래버튼 누름 여전히
    구간별로 나옴"). format_summary_report와 동일하게 gift_daily_datakey(GB 단위)로
    교체. 컬럼이 너무 많아지는 걸 막기 위해 요약 표와 같은 기준
    (DATAKEY_MIN_VAL=20만원 이상)으로 GB 컬럼도 추려냄.
    """
    if not get_db:
        return '⚠️ DB 연결 없음'

    db    = get_db()
    today = datetime.now(KST).date()
    days  = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    label = PROV_LABEL.get(prov_key, prov_key)
    rows  = []
    for d in days:
        date_str = d.isoformat()
        try:
            doc = db.collection('gift_daily_datakey').document(date_str).get()
            data = doc.to_dict() if doc.exists else {}
            dk_data = data.get(prov_key, {})
        except Exception:
            dk_data = {}
        rows.append((date_str, dk_data))

    # 20만원 이상 찍힌 적 있는 GB만 (요약 표와 동일 기준)
    active_dks = sorted(
        {dk for _, dk_data in rows for dk, v in dk_data.items() if v >= DATAKEY_MIN_VAL},
        key=_data_key_gb
    )
    if not active_dks:
        return f'⚠️ {label} 추이 데이터 없음 (7일, {_man_short(DATAKEY_MIN_VAL)} 이상 기준)'

    lines = [f'📈 <b>{label} 7일 추이</b> ({_man_short(DATAKEY_MIN_VAL)} 이상)', '']

    for date_str, dk_data in rows:
        d = date.fromisoformat(date_str)
        date_label = f'{d.month}/{d.day}'
        is_today   = (d == today)

        vals = []
        for dk in active_dks:
            v = dk_data.get(dk, 0)
            vals.append(f'{v//10000}만' if v else '-')

        row = f'  {date_label}  ' + '  '.join(vals)
        if is_today:
            row += '  ← 오늘'
        lines.append(row)

    dk_header = '  '.join(_data_key_label(dk) for dk in active_dks)
    lines.insert(2, f'       {dk_header}')

    return '\n'.join(lines)


def handle_gift_callback(callback_query: dict) -> bool:
    data = callback_query.get('data', '')
    if not data.startswith('gift_'):
        return False

    cq_id   = callback_query['id']
    chat_id = callback_query['message']['chat']['id']

    # 추이 버튼: gift_trend_{provider_key}
    if data.startswith('gift_trend_'):
        prov_key = data[len('gift_trend_'):]
        label    = PROV_LABEL.get(prov_key, prov_key)
        _answer_callback(cq_id, f'{label} 7일 추이 조회 중...')
        text = _get_trend_text(prov_key)
        _send_message(chat_id, text)
        return True

    # K CUP 상세보기 버튼: gift_kcup_{date}_{seq}
    # (요약 메시지 + 건별 버튼 구조 - gift_job.py의 _save_kcup_details()가 미리
    #  gift_reports/{date}/kcup_details/{seq}에 저장해둔 전체 상세를 조회해서 보여줌)
    if data.startswith('gift_kcup_'):
        rest = data[len('gift_kcup_'):]
        try:
            date_str, seq = rest.rsplit('_', 1)
        except ValueError:
            _answer_callback(cq_id, '잘못된 요청')
            return True

        _answer_callback(cq_id, '상세 조회 중...')

        if not get_db:
            _send_message(chat_id, '⚠️ DB 연결 없음')
            return True

        try:
            db  = get_db()
            doc = (db.collection('gift_reports')
                     .document(date_str)
                     .collection('kcup_details')
                     .document(seq)
                     .get())
            text = doc.to_dict().get('text', '데이터 없음') if doc.exists else '⚠️ 상세 데이터 없음'
        except Exception as e:
            text = f'⚠️ 조회 오류: {e}'

        _send_message(chat_id, text)
        return True

    # 상세 버튼: gift_{date}_{provider_key}
    parts = data.split('_', 2)
    if len(parts) < 3:
        _answer_callback(cq_id, '잘못된 요청')
        return True

    date_str = parts[1]
    prov_key = parts[2]
    label    = PROV_LABEL.get(prov_key, prov_key)

    _answer_callback(cq_id, f'{label} 상세 조회 중...')

    if not get_db:
        _send_message(chat_id, '⚠️ DB 연결 없음')
        return True

    try:
        db  = get_db()
        doc = (db.collection('gift_reports')
                 .document(date_str)
                 .collection('providers')
                 .document(prov_key)
                 .get())

        if doc.exists:
            text = doc.to_dict().get('text', '데이터 없음')
        else:
            today = datetime.now(KST).strftime('%Y-%m-%d')
            doc2  = (db.collection('gift_reports')
                       .document(today)
                       .collection('providers')
                       .document(prov_key)
                       .get())
            text = (doc2.to_dict().get('text', '데이터 없음')
                    if doc2.exists else f'⚠️ {label} 데이터 없음')

    except Exception as e:
        text = f'⚠️ 조회 오류: {e}'

    _send_message(chat_id, text)
    return True