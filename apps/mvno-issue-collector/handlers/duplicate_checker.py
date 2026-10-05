"""
handlers/duplicate_checker.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: 중복 이슈 감지
  · event_date ±1일 + category 기준 1차 필터
  · Gemini로 summary 유사도 2차 판단
"""

import os
import logging
from datetime import datetime, timedelta
from google.cloud import firestore
import google.generativeai as genai

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


def check_duplicate(record: dict) -> dict | None:
    """유사 이슈 찾기. 있으면 {"id": doc_id, "summary": ..., "collection": ...} 반환"""
    collection = record.get("_collection", "mvno_issues")
    if collection != "mvno_issues":
        return None

    event_date_str = record.get("event_date", "")
    category = record.get("category", "")
    new_summary = record.get("summary", "")

    if not event_date_str or not new_summary:
        return None

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
        date_from = (event_date - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to = (event_date + timedelta(days=1)).strftime("%Y-%m-%d")

        db = get_db()
        candidates = (
            db.collection("mvno_issues")
            .where("category", "==", category)
            .where("event_date", ">=", date_from)
            .where("event_date", "<=", date_to)
            .limit(5)
            .stream()
        )

        for doc in candidates:
            data = doc.to_dict()
            existing_summary = data.get("summary", "")
            if _is_similar(new_summary, existing_summary):
                return {
                    "id": doc.id,
                    "summary": existing_summary,
                    "collection": "mvno_issues",
                }
    except Exception as e:
        logger.warning(f"중복 체크 오류: {e}")

    return None


def _is_similar(summary_a: str, summary_b: str) -> bool:
    """Gemini로 두 요약문이 동일 이슈인지 판단"""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""다음 두 MVNO 이슈 요약이 동일한 사건/이슈를 다루고 있으면 "YES", 아니면 "NO"만 답하세요.

A: {summary_a}
B: {summary_b}"""
        response = model.generate_content(prompt)
        return "YES" in response.text.upper()
    except Exception as e:
        logger.warning(f"유사도 판단 오류: {e}")
        return False
