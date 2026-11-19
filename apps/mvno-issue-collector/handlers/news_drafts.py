"""
handlers/news_drafts.py  v1.0
작성일: 2026-10-05

[개요]
news_scraper가 생성한 "이슈 등록 대기" draft를 기사 단위로 저장.

session.py와 분리하는 이유: session.py는 chat_id당 세션 슬롯이 1개뿐이라,
뉴스 다이제스트처럼 기사 여러 건을 동시에 버튼으로 보내면 나중 메시지의
세션이 이전 메시지의 세션을 덮어써서 먼저 온 메시지의 버튼을 누르면
엉뚱한(가장 최근) 기사를 등록해버리는 충돌이 생김. 기사별 고유
draft_id(해시)를 콜백데이터에 직접 심어, 세션 없이도 어떤 기사의
버튼인지 식별 가능하게 함.
"""

import os
import logging
from datetime import datetime, timezone

from google.cloud import firestore

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"
COLLECTION = "news_drafts"

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


def save_draft(draft_id: str, record: dict, duplicate: dict | None = None):
    get_db().collection(COLLECTION).document(draft_id).set({
        "record": record,
        "duplicate": duplicate,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def get_draft(draft_id: str) -> dict | None:
    snap = get_db().collection(COLLECTION).document(draft_id).get()
    return snap.to_dict() if snap.exists else None


def delete_draft(draft_id: str):
    get_db().collection(COLLECTION).document(draft_id).delete()
