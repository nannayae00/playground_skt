"""
handlers/session.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: 텔레그램 대화 세션 관리
  · Firestore bot_sessions 컬렉션 사용
  · 30분 TTL 자동 만료 처리
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"
COLLECTION = "bot_sessions"
SESSION_TTL_MINUTES = 30

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


def save_session(chat_id: str, data: dict | None):
    db = get_db()
    ref = db.collection(COLLECTION).document(f"issue_bot_{chat_id}")
    if data is None:
        ref.delete()
        return
    data["_created_at"] = datetime.now(timezone.utc).isoformat()
    ref.set(data)


def get_session(chat_id: str) -> dict | None:
    db = get_db()
    ref = db.collection(COLLECTION).document(f"issue_bot_{chat_id}")
    doc = ref.get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    created_at_str = data.get("_created_at")
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str)
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=SESSION_TTL_MINUTES):
            ref.delete()
            return None

    return data
