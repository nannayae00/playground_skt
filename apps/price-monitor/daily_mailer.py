"""
daily_mailer.py  v1.1
작성일: 2026-05-20

[수정 이력]
v1.1 | 2026-05-20 | pytz 의존성 제거 (datetime.timezone으로 교체)
v1.0 | 2026-05-20 | 최초 작성
"""

import os
import sys
import smtplib
import logging
import requests
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

GMAIL_ADDRESS      = os.getenv('GMAIL_ADDRESS',      'mclee.cecilia@gmail.com')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
MAIL_TO            = os.getenv('MAIL_TO',            'chris.mclee@sk.com')
TELEGRAM_TOKEN     = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID',  '')


def _get_db():
    from google.cloud import firestore as _fs
    import firebase_admin
    from firebase_admin import credentials as _cred
    if not firebase_admin._apps:
        firebase_admin.initialize_app(_cred.ApplicationDefault())
    return _fs.Client(project='mvno-484509', database='mvno-data')


def _fetch_context(db, collection, date_str):
    try:
        doc = db.collection(collection).document(date_str).get()
        if doc.exists:
            return doc.to_dict().get('text') or None
        return None
    except Exception as e:
        log.warning(f"{collection}/{date_str} 조회 실패: {e}")
        return None


def build_mail_body(date_str, contexts):
    SEP  = '━' * 40
    L    = []
    L.append(f"MVNO Daily Intelligence | {date_str}")
    L.append(f"발송: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST")
    L.append(SEP)
    L.append("")
    L.append("※ 이 메일은 MVNO AX Agent가 자동 생성한 일일 통합 리포트입니다.")
    L.append("※ 모든 수치는 확정값. AI 해석 참고용.")
    L.append("")

    sections = [
        ('ktoa',      '📊 실적 현황 (KTOA MNP 데이터)'),
        ('price',     '💰 요금제 현황 (RS 최저가 모니터링)'),
        ('community', '📢 커뮤니티 동향 (뽐뿌 + 디씨인사이드)'),
        ('youtube',   '📺 YouTube MVNO 동향'),
    ]
    for key, title in sections:
        L.append(SEP)
        L.append(f"■ {title}")
        L.append(SEP)
        text = contexts.get(key)
        if text:
            L.append(text)
        else:
            L.append(f"⚠️ {date_str} 데이터 미수집")
        L.append("")

    L.append(SEP)
    L.append("MVNO AX Agent | SKT MVNO Strategy")
    L.append(SEP)
    return '\n'.join(L)


def send_mail(date_str, body):
    if not GMAIL_APP_PASSWORD:
        log.error("GMAIL_APP_PASSWORD 환경변수 없음")
        return False
    subject = f"[MVNO Daily] {date_str} 실적/요금제/커뮤니티/YouTube 통합 리포트"
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_ADDRESS
    msg['To']      = MAIL_TO
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, MAIL_TO, msg.as_string())
        log.info(f"메일 발송 완료 → {MAIL_TO}")
        return True
    except Exception as e:
        log.error(f"메일 발송 실패: {e}")
        return False


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10
        )
    except Exception as e:
        log.warning(f"텔레그램 알림 실패: {e}")


def main(date_str=None):
    _now     = datetime.now(KST)
    date_str = date_str or _now.strftime('%Y-%m-%d')
    log.info(f"daily_mailer 시작: {date_str}")

    db = _get_db()
    contexts = {
        'ktoa'     : _fetch_context(db, 'ktoa_context',      date_str),
        'price'    : _fetch_context(db, 'price_context',     date_str),
        'community': _fetch_context(db, 'community_context', date_str),
        'youtube'  : _fetch_context(db, 'youtube_context',   date_str),
    }

    found   = [k for k, v in contexts.items() if v]
    missing = [k for k, v in contexts.items() if not v]
    log.info(f"context 확보: {found} / 미확보: {missing}")

    if not any(contexts.values()):
        msg = f"⚠️ daily_mailer: {date_str} context 전체 미수집 — 메일 발송 중단"
        log.error(msg)
        send_telegram(msg)
        return False

    body = build_mail_body(date_str, contexts)
    ok   = send_mail(date_str, body)

    label = {'ktoa':'실적','price':'요금제','community':'커뮤니티','youtube':'YouTube'}
    if ok:
        send_telegram(
            f"📧 MVNO Daily 메일 발송 완료\n"
            f"날짜: {date_str}\n"
            f"수신: {MAIL_TO}\n"
            f"포함: {' / '.join(label[k] for k in found)}\n"
            f"미포함: {' / '.join(label[k] for k in missing) or '없음'}"
        )
    else:
        send_telegram(f"❌ daily_mailer 메일 발송 실패: {date_str}")

    return ok


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if main(date_arg) else 1)