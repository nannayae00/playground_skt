"""
[수정 이력]
v1.0 | 2026-03-20 | 최초 작성 - 아침 일정 알림 스케줄러
v1.1 | 2026-03-21 | KST 시간대 명시, 날짜 포맷 한국어 요일로 변경
v1.2 | 2026-09-20 | 중복 등록된 일정이 브리핑에 두 줄씩 보이던 문제 - dedupe_events 적용
"""

import os
import logging
from datetime import datetime, timedelta, timezone
import requests

from calendar_handler import CalendarHandler, dedupe_events

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

ALERT_CHAT_IDS = [
    int(x.strip())
    for x in os.environ.get("ALERT_CHAT_IDS", "").split(",")
    if x.strip()
]

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def send_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    })


def format_date_header(dt: datetime) -> str:
    yy = str(dt.year)[2:]
    dow = WEEKDAY_KO[dt.weekday()]
    return f"'{yy}-{dt.strftime('%m-%d')} ({dow})"


def format_event_line(ev: dict) -> str:
    time_start = ev.get("time_start", "")
    time_end = ev.get("time_end", "")
    title = ev.get("title", "")
    time_str = ""
    if time_start and time_end:
        time_str = f" {time_start}~{time_end}"
    elif time_start:
        time_str = f" {time_start}"
    return f"• {title}{time_str}"


def send_daily_briefing():
    if not ALERT_CHAT_IDS:
        logger.warning("ALERT_CHAT_IDS 환경변수가 설정되지 않았습니다.")
        return

    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    cal = CalendarHandler()
    try:
        today_events = dedupe_events(cal.list_events(today, today))
        tomorrow_events = dedupe_events(cal.list_events(tomorrow, tomorrow))
    except Exception as e:
        logger.error(f"Calendar fetch error: {e}")
        return

    msg = "🌅 <b>오늘의 일정 브리핑</b>\n\n"
    msg += f"<b>📅 오늘 {format_date_header(now)}</b>\n"
    if today_events:
        for ev in today_events:
            msg += format_event_line(ev) + "\n"
    else:
        msg += "• 일정 없음\n"

    msg += f"\n<b>📅 내일 {format_date_header(now + timedelta(days=1))}</b>\n"
    if tomorrow_events:
        for ev in tomorrow_events:
            msg += format_event_line(ev) + "\n"
    else:
        msg += "• 일정 없음\n"

    for chat_id in ALERT_CHAT_IDS:
        try:
            send_message(chat_id, msg)
            logger.info(f"Daily briefing sent to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send to {chat_id}: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    send_daily_briefing()