# firestore_client.py
# ============================================================
# [수정 이력]
# v1.0 | 2026-05-27 | 최초 작성
#   - ktoa_hourly / ktoa_daily 최신 문서 조회
#   - 전일·전주 동시간 문서 조회
#   - 최근 N영업일 ktoa_daily 목록 조회
#   - ktoa_context / ktoa_context_week / ktoa_context_month 조회
# ============================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from google.cloud import firestore

# ── 프로젝트 설정 ──────────────────────────────────────────
PROJECT_ID = "mvno-484509"
DATABASE   = "mvno-data"
KST        = timezone(timedelta(hours=9))

# ── 클라이언트 싱글톤 ──────────────────────────────────────
_db: Optional[firestore.Client] = None

def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


# ══════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════

def now_kst() -> datetime:
    return datetime.now(KST)

def is_close_time() -> bool:
    """20:00 KST 이후면 마감 모드"""
    return now_kst().hour >= 20

def today_str() -> str:
    return now_kst().strftime("%Y-%m-%d")

def _doc_id_hourly(dt: datetime) -> str:
    """YYYY-MM-DD_HHmm 형식 (10분 단위)"""
    minute = (dt.minute // 10) * 10
    return dt.strftime("%Y-%m-%d_") + f"{dt.hour:02d}{minute:02d}"


# ══════════════════════════════════════════════════════════
# ktoa_hourly 조회
# ══════════════════════════════════════════════════════════

def get_latest_hourly() -> Optional[dict]:
    """오늘 가장 최신 ktoa_hourly 문서 반환"""
    db   = get_db()
    now  = now_kst()

    # 현재 시간부터 거슬러 올라가며 존재하는 문서 탐색 (최대 12시간)
    for delta in range(0, 180, 10):
        dt = now - timedelta(minutes=delta)
        dt = dt.replace(second=0, microsecond=0)
        dt = dt.replace(minute=(dt.minute // 10) * 10)
        doc_id = _doc_id_hourly(dt)
        doc = db.collection("ktoa_hourly").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["_doc_id"]   = doc_id
            data["_snapshot_hour"] = dt.hour
            return data
    return None


def get_hourly_comparison(today_hour: int) -> dict:
    """
    전일·전주 동시간 문서 반환
    Returns: {"yesterday": dict|None, "last_week": dict|None}
    """
    db  = get_db()
    now = now_kst()

    def fetch(dt: datetime) -> Optional[dict]:
        doc_id = _doc_id_hourly(dt)
        doc = db.collection("ktoa_hourly").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["_doc_id"] = doc_id
            return data
        return None

    yesterday   = now - timedelta(days=1)
    last_week   = now - timedelta(days=7)
    yd_dt       = yesterday.replace(hour=today_hour, minute=0, second=0, microsecond=0)
    lw_dt       = last_week.replace(hour=today_hour, minute=0, second=0, microsecond=0)

    return {
        "yesterday": fetch(yd_dt),
        "last_week": fetch(lw_dt),
    }


# ══════════════════════════════════════════════════════════
# ktoa_daily 조회
# ══════════════════════════════════════════════════════════

def get_daily(date_str: Optional[str] = None) -> Optional[dict]:
    """
    특정 날짜(YYYY-MM-DD) 또는 가장 최근 마감 ktoa_daily 문서 반환
    오늘 문서에 실적(mvno_in)이 없으면 어제 문서로 fallback
    """
    db = get_db()
    if date_str:
        doc = db.collection("ktoa_daily").document(date_str).get()
        if doc.exists:
            data = doc.to_dict()
            data["_doc_id"] = date_str
            return data
        return None
    # 날짜 미지정: 오늘부터 역순으로 실적 있는 문서 탐색
    cursor = now_kst().date()
    for _ in range(7):
        key = cursor.strftime("%Y-%m-%d")
        doc = db.collection("ktoa_daily").document(key).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("mvno_in"):  # 실적 있는 문서만
                data["_doc_id"] = key
                return data
        cursor -= timedelta(days=1)
    return None


def get_recent_daily(n: int = 5) -> list[dict]:
    """
    최근 N영업일(확정값 있는 ktoa_daily) 목록 반환
    """
    db    = get_db()
    today = now_kst().date()
    rows  = []
    cursor = today - timedelta(days=1)   # 어제부터 역순 탐색

    attempts = 0
    while len(rows) < n and attempts < 60:
        doc_id = cursor.strftime("%Y-%m-%d")
        doc = db.collection("ktoa_daily").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            # 확정 실적이 있는 문서만 포함 (mvno_in 필드 존재 여부로 판단)
            if data.get("mvno_in"):
                data["_doc_id"] = doc_id
                rows.append(data)
        cursor -= timedelta(days=1)
        attempts += 1

    return rows


# ══════════════════════════════════════════════════════════
# ktoa_context 조회
# ══════════════════════════════════════════════════════════

def get_context_daily(date_str: Optional[str] = None) -> Optional[dict]:
    db  = get_db()
    key = date_str or today_str()
    doc = db.collection("ktoa_context").document(key).get()
    return doc.to_dict() if doc.exists else None


def get_context_week(year_week: Optional[str] = None) -> Optional[dict]:
    """year_week: 'YYYY-WW' 형식 (None이면 이번 주)"""
    db = get_db()
    if year_week is None:
        now = now_kst()
        year_week = f"{now.year}-{now.strftime('%W')}"
    doc = db.collection("ktoa_context_week").document(year_week).get()
    return doc.to_dict() if doc.exists else None


def get_context_month(year_month: Optional[str] = None) -> Optional[dict]:
    """year_month: 'YYYY-MM' 형식 (None이면 이번 달)"""
    db = get_db()
    if year_month is None:
        year_month = now_kst().strftime("%Y-%m")
    doc = db.collection("ktoa_context_month").document(year_month).get()
    return doc.to_dict() if doc.exists else None


# ══════════════════════════════════════════════════════════
# 아카이브 목록
# ══════════════════════════════════════════════════════════

def get_archive_list(limit: int = 30) -> list[dict]:
    """
    최근 30일 ktoa_daily 문서 목록 반환 (아카이브 사이드바용)
    Returns list of {doc_id, status_tag, ms_pct} sorted desc
    """
    db    = get_db()
    today = now_kst().date()
    items = []

    for i in range(1, limit + 1):
        d      = today - timedelta(days=i)
        doc_id = d.strftime("%Y-%m-%d")
        doc    = db.collection("ktoa_daily").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            # SM 신규 MS% 계산
            mvno_in = data.get("mvno_in", {})
            sm_in   = mvno_in.get("SM", 0) or 0
            total_in = mvno_in.get("계", 1) or 1
            ms_pct  = round(sm_in / total_in * 100, 1) if total_in else 0

            # 판정 태그 (fc_on_track + MS% 기준)
            on_track = data.get("fc_on_track", None)
            if on_track is False or ms_pct < 18:
                tag = "d"   # danger → 조치필요
            elif ms_pct < 20:
                tag = "w"   # warn → 관리필요
            else:
                tag = "g"   # good → 양호

            items.append({
                "doc_id":  doc_id,
                "date_label": d.strftime("%-m/%-d"),
                "day_ko":  ["월","화","수","목","금","토","일"][d.weekday()],
                "tag":     tag,
                "ms_pct":  ms_pct,
            })

    return items
