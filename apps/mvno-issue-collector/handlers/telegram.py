"""
handlers/telegram.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: 텔레그램 API 래퍼
  · send_message, send_message_with_buttons, answer_callback, download_file
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    resp = requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })
    return resp.json()


def send_message_with_buttons(chat_id: str, text: str, buttons: list, parse_mode: str = "HTML") -> dict:
    """
    buttons 예시:
    [
        [{"text": "✅ 등록", "callback_data": "confirm:mvno_issues"},
         {"text": "🔄 분류변경", "callback_data": "reclassify"},
         {"text": "✏️ 수정", "callback_data": "edit"},
         {"text": "❌ 취소", "callback_data": "cancel"}]
    ]
    callback_data 최대 64바이트 주의
    """
    resp = requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": {"inline_keyboard": buttons},
    })
    return resp.json()


def edit_message_with_buttons(chat_id: str, message_id: int, text: str, buttons: list) -> dict:
    resp = requests.post(f"{BASE_URL}/editMessageText", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": buttons},
    })
    return resp.json()


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    resp = requests.post(f"{BASE_URL}/answerCallbackQuery", json={
        "callback_query_id": callback_query_id,
        "text": text,
    })
    return resp.json()


def download_file(file_id: str) -> bytes:
    """텔레그램 file_id로 파일 바이트 다운로드"""
    # 파일 경로 조회
    r = requests.get(f"{BASE_URL}/getFile", params={"file_id": file_id})
    file_path = r.json()["result"]["file_path"]
    # 실제 파일 다운로드
    r2 = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}")
    return r2.content
