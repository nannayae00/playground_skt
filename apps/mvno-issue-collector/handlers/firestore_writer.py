"""
handlers/firestore_writer.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: Firestore mvno-data DB 저장
  · 문서ID: YYMMDD_요약 형식
  · _collection 필드 제거 후 저장
  · append_to_existing: 기존 문서 detail에 추가 내용 병합
"""

import os
import re
import logging
from datetime import datetime, timezone

from google.cloud import firestore

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


def make_doc_id(record: dict, collection: str, max_len: int = 30) -> str:
    raw_date = (record.get("event_date") or record.get("snapshot_date") or
                record.get("input_date") or "")
    date_part = raw_date.replace("-", "")[2:] if raw_date else "000000"

    summary = record.get("summary") or ""
    first_chunk = re.split(r"[.,]", summary)[0].strip()
    slug = first_chunk[:max_len].strip().replace("/", "-")

    if not slug:
        if "providers" in record:
            slug = "_".join(list(record["providers"].keys())[:3]) + " 프로모션현황"
        else:
            slug = "기타"

    base_id = f"{date_part}_{slug}"
    db = get_db()
    doc_id = base_id
    suffix = 2
    while db.collection(collection).document(doc_id).get().exists:
        doc_id = f"{base_id}_{suffix}"
        suffix += 1
    return doc_id


def save_issue(record: dict, collection: str) -> str | None:
    try:
        db = get_db()
        clean = {k: v for k, v in record.items() if k != "_collection"}
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_id = make_doc_id(clean, collection)
        db.collection(collection).document(doc_id).set(clean)
        logger.info(f"저장 완료: {collection}/{doc_id}")
        return doc_id
    except Exception as e:
        logger.error(f"Firestore 저장 오류: {e}", exc_info=True)
        return None


def append_to_existing(doc_id: str, collection: str, new_record: dict) -> bool:
    """기존 문서에 새 내용을 detail/follow_up에 병합"""
    try:
        db = get_db()
        ref = db.collection(collection).document(doc_id)
        existing = ref.get().to_dict() or {}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_text = f"\n\n[{now} 추가]\n{new_record.get('detail', new_record.get('summary', ''))}"

        existing_detail = existing.get("detail", "")
        ref.update({
            "detail": existing_detail + append_text,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "확인중",
        })
        return True
    except Exception as e:
        logger.error(f"append 오류: {e}", exc_info=True)
        return False
