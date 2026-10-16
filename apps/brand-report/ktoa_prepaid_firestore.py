"""
ktoa_prepaid_firestore.py  v1.0
작성일: 2026-10-16

[수정 이력]
v1.0 | 2026-10-16 | 최초 작성
  - 선불 등록현황(일별) 저장: ktoa_prepaid_daily/{YYYY-MM-DD}
    {
      "date": "2026-10-15",
      "blocks": {
        "TOTAL": {"name": "총 계", "code": None, "subtotal": -923, "new_reg": 6360, ...},
        "SKT": {...}, "KT": {...}, "LGU+": {...},
        "전체_MVNO합계": {...},           # 사이트 표에 있는 합계 블록은 이름 키로 저장
        "L57": {"name": "우들모바일LG(L57)", "code": "L57", ...},
      },
      "block_order": ["TOTAL", "SKT", ...],   # 사이트 표의 열 순서
      "collected_at": SERVER_TIMESTAMP,
    }
  - 지표 키는 ktoa_prepaid_parser.METRICS 참고
  - 같은 날짜를 다시 수집하면 문서를 통째로 덮어씀(set, merge 아님) - KTOA가 과거
    일자를 정정했을 때 사라진 블록이 남지 않도록
"""

import logging

from google.cloud import firestore as fs

from ktoa_mvno_firestore import _get_db

log = logging.getLogger(__name__)

COLLECTION = "ktoa_prepaid_daily"


def save_prepaid_days(parsed: dict) -> int:
    """parse_grid() 결과를 날짜별 문서로 저장. 저장한 문서 수를 반환."""
    db = _get_db()
    batch = db.batch()
    pending = 0
    written = 0
    meta = {b["key"]: b for b in parsed["blocks"]}
    order = [b["key"] for b in parsed["blocks"]]

    for date_str, day in sorted(parsed["days"].items()):
        blocks = {}
        for key, metrics in day.items():
            blocks[key] = {"name": meta[key]["name"], "code": meta[key]["code"], **metrics}
        ref = db.collection(COLLECTION).document(date_str)
        batch.set(ref, {
            "date": date_str,
            "blocks": blocks,
            "block_order": order,
            "collected_at": fs.SERVER_TIMESTAMP,
        })
        pending += 1
        written += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0

    if pending:
        batch.commit()
    log.info(f"{COLLECTION} 저장 완료: {written}건")
    return written


def load_prepaid_days(start: str, end: str) -> dict:
    """[start, end] 범위 문서를 {date: {block_key: metrics}} 형태로 읽는다 (검증용)."""
    db = _get_db()
    q = (db.collection(COLLECTION)
         .where("date", ">=", start).where("date", "<=", end))
    out = {}
    for doc in q.stream():
        d = doc.to_dict()
        out[d["date"]] = {
            k: {m: v for m, v in blk.items() if m not in ("name", "code")}
            for k, blk in d.get("blocks", {}).items()
        }
    return out
