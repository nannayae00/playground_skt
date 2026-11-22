"""
handlers/news_backfill.py  v1.0
작성일: 2026-11-19

[개요]
과거 1년치 알뜰폰 뉴스를 일일 브리핑과 같은 기준으로 수집·판정·정제해서 결과를 검토용
컬렉션에만 저장한다 (mvno_issues / 텔레그램 / scraped_news_seen 은 건드리지 않음).
팀이 결과를 보고 트리아지 기준·요약 프롬프트를 고치기 위한 "평가용 데이터셋".

[소스]
Google News RSS는 과거 기사가 주당 5~12건밖에 안 나와서(실측) 네이버 뉴스 검색(일반 검색
페이지, 하루 단위 기간 지정 + 관련도순 첫 페이지)을 키워드 여러 개로 돌려 날짜별 상위 기사를 모음.

[실행 방식]
Cloud Run 요청 타임아웃(540s) 안에서 끝나도록 "시간 예산(BUDGET_SEC)만큼만 일하고 상태 저장 후 반환"을
반복하는 재개형 구조. Cloud Scheduler가 새벽에 10분 간격으로 /news-backfill 을 호출한다.
  phase "collect": 7일 단위로 네이버 검색 → 제목 트리아지(flash, 일일 브리핑과 같은 프롬프트)
                   → 날짜별 결과를 news_backfill_days/{YYYY-MM-DD} 에 저장, 통과 기사는
                   news_backfill/{id} 에 status=pending 으로 저장
  phase "refine":  pending 기사 본문 크롤링 → 본문 포함 확인(flash) → 기사 전용 정제(pro)
                   → status=done(record 포함) / rejected_confirm / failed
  phase "done":    아무것도 안 함 (스케줄러는 나중에 정리)
상태: news_backfill_runs/{run_id}
"""

import json
import logging
import re
import time
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore

from handlers.input_handler import _fetch_article
from handlers.gemini_refiner import refine_news_article
from handlers import news_scraper as ns

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
BUDGET_SEC = 470
SEARCH_INTERVAL_SEC = 1.5
WINDOW_DAYS = 7
RUNS = "news_backfill_runs"
DAYS = "news_backfill_days"
ARTICLES = "news_backfill"

DEFAULT_KEYWORDS = [
    "알뜰폰", "MVNO", "알뜰폰 요금제", "알뜰폰 정책",
    "알뜰폰 도매대가", "알뜰폰 번호이동", "알뜰폰 점유율", "알뜰폰 자회사",
]
DEFAULT_MAX_REFINE = 800


def _db():
    return ns.get_db()


# ───────────────────────── 네이버 일자별 검색 ─────────────────────────

def _naver_day_search(query: str, day: str) -> list[dict]:
    """day = YYYY-MM-DD. 관련도순 첫 페이지의 기사들 (언론사 원문 링크 기준)."""
    d = day.replace("-", "")
    dots = day.replace("-", ".")
    params = {"where": "news", "query": query, "sort": "0", "ds": dots, "de": dots,
              "nso": f"so:r,p:from{d}to{d}"}
    try:
        resp = requests.get(ns.NAVER_SEARCH_URL, params=params, headers={"User-Agent": ns.UA}, timeout=10)
    except Exception as e:
        logger.warning(f"네이버 검색 오류 ({query} {day}): {e}")
        return []
    if resp.status_code != 200:
        logger.warning(f"네이버 검색 실패 {resp.status_code} ({query} {day})")
        return []

    by_href: dict[str, str] = {}
    for a in BeautifulSoup(resp.text, "html.parser").find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if not href.startswith("http") or "naver.com" in href or not text.endswith("새 창 열림"):
            continue
        text = text.replace("새 창 열림", "").strip()
        u = urlparse(href)
        # 언론사 홈 링크(경로 없음)·네이버 하단 링크·짧은 텍스트 제외
        if len(text) < 12 or len((u.path or "").strip("/")) < 3 and not u.query or "navercorp" in (u.hostname or ""):
            continue
        if href not in by_href:  # 같은 링크의 첫 앵커 = 제목 (다음 앵커는 본문 미리보기)
            by_href[href] = text
    out = []
    for href, title in by_href.items():
        host = (urlparse(href).hostname or "").removeprefix("www.")
        out.append({"title": title, "url": href, "source": host, "pub_day": day, "keyword": query})
    return out


def _collect_window(days: list[str], keywords: list[str]) -> dict[str, list[dict]]:
    per_day: dict[str, list[dict]] = {}
    for day in days:
        seen, items = set(), []
        for kw in keywords:
            for it in _naver_day_search(kw, day):
                key = ns._norm_title(it["title"])
                if key in seen:
                    continue
                seen.add(key)
                items.append(it)
            time.sleep(SEARCH_INTERVAL_SEC)
        per_day[day] = items
    return per_day


def _triage(items: list[dict]) -> list[dict]:
    """일일 브리핑과 같은 트리아지 프롬프트. 반환: 아이템별 verdict(dict) (대표로 안 뽑히면 clustered)."""
    for it in items:
        it["verdict"] = {"stage": "clustered"}
    for start in range(0, len(items), 150):
        chunk = items[start:start + 150]
        lines = [f"{i}. {c['title']} | 출처: {c['source']} | 날짜: {c['pub_day']}" for i, c in enumerate(chunk)]
        result = ns._gemini_json(ns._TRIAGE_PROMPT.format(items="\n".join(lines)))
        if not isinstance(result, list):
            for c in chunk:
                c["verdict"] = {"stage": "triage_error"}
            continue
        for v in result:
            try:
                idx = int(v.get("index"))
            except (TypeError, ValueError):
                continue
            if not 0 <= idx < len(chunk):
                continue
            passed = v.get("relevant") and not v.get("advertorial") and v.get("impact_level") in ("상", "중")
            chunk[idx]["verdict"] = {
                "stage": "triage_pass" if passed else "triage_reject",
                "relevant": v.get("relevant"), "advertorial": v.get("advertorial"),
                "impact_level": v.get("impact_level"),
            }
    return items


def _article_id(it: dict) -> str:
    return "b" + hashlib.sha1((it["url"] + it["title"]).encode("utf-8")).hexdigest()[:15]


# ───────────────────────── phase 실행 ─────────────────────────

def _do_collect(state: dict, deadline: float) -> None:
    db = _db()
    start = datetime.strptime(state["start"], "%Y-%m-%d").date()
    end = datetime.strptime(state["end"], "%Y-%m-%d").date()
    cur = datetime.strptime(state["next_day"], "%Y-%m-%d").date()
    while cur <= end and time.time() < deadline - 120:  # 7일 수집+트리아지 ≈ 90~110초
        days = [(cur + timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS)
                if cur + timedelta(days=i) <= end]
        per_day = _collect_window(days, state["keywords"])
        window_items = [it for d in days for it in per_day[d]]
        _triage(window_items)

        batch = db.batch()
        for d in days:
            batch.set(db.collection(DAYS).document(d), {
                "date": d, "run_id": state["run_id"], "count": len(per_day[d]),
                "items": [{k: it[k] for k in ("title", "url", "source", "keyword", "verdict")} for it in per_day[d]],
            })
        passed = [it for it in window_items if it["verdict"]["stage"] == "triage_pass"]
        for it in passed:
            batch.set(db.collection(ARTICLES).document(_article_id(it)), {
                "run_id": state["run_id"], "status": "pending", "title": it["title"], "url": it["url"],
                "source": it["source"], "pub_day": it["pub_day"], "keyword": it["keyword"],
                "triage": it["verdict"], "created_at": datetime.now(KST).isoformat(),
            })
        batch.commit()
        state["collected_days"] = state.get("collected_days", 0) + len(days)
        state["candidates"] = state.get("candidates", 0) + len(window_items)
        state["triage_pass"] = state.get("triage_pass", 0) + len(passed)
        cur = cur + timedelta(days=WINDOW_DAYS)
        state["next_day"] = cur.isoformat()
        logger.info(f"[backfill] 수집 {days[0]}~{days[-1]}: 후보 {len(window_items)}, 통과 {len(passed)}")
        _save_state(state)
    if cur > end:
        state["phase"] = "refine"


def _do_refine(state: dict, deadline: float) -> None:
    db = _db()
    while time.time() < deadline - 60:  # 1건 ≈ 20~40초
        if state.get("refined", 0) >= state["max_refine"]:
            state["phase"] = "done"
            state["stop_reason"] = f"max_refine {state['max_refine']} 도달"
            return
        docs = list(db.collection(ARTICLES).where("run_id", "==", state["run_id"])
                    .where("status", "==", "pending").limit(1).stream())
        if not docs:
            state["phase"] = "done"
            state["stop_reason"] = "pending 없음"
            return
        ref, a = docs[0].reference, docs[0].to_dict()
        try:
            content = _fetch_article(a["url"]) or ""
            body_src = a["url"]
            if len(content) < 300:
                for alt in ns._naver_candidates(a["title"], "", a["url"])[:4]:
                    if alt == a["url"]:
                        continue
                    alt_c = _fetch_article(alt)
                    if alt_c and len(alt_c) >= 300:
                        content, body_src = alt_c, alt
                        break
            item = {"title": a["title"], "source": a["source"], "content": content}
            verdict = ns._confirm_with_content(item) or {}
            rejected = (not verdict.get("relevant") or verdict.get("advertorial")
                        or verdict.get("impact_level") not in ("상", "중"))
            update = {"confirm": verdict, "body_len": len(content), "body_src": body_src,
                      "updated_at": datetime.now(KST).isoformat()}
            if rejected and content:
                update["status"] = "rejected_confirm"
            else:
                record = refine_news_article(a["title"], a["source"], a["url"], a["pub_day"], content)
                update["status"] = "done" if record else "failed"
                if record:
                    record["source"] = {"type": "기사URL", "origin": a["source"], "ref": a["url"],
                                        "title": a["title"], "raw_input": content[:4000]}
                    update["record"] = record
                state["refined"] = state.get("refined", 0) + 1
            ref.update(update)
            state[update["status"]] = state.get(update["status"], 0) + 1
        except Exception as e:
            logger.error(f"[backfill] 정제 오류 {a.get('title')}: {e}", exc_info=True)
            ref.update({"status": "failed", "error": str(e)[:300]})
            state["failed"] = state.get("failed", 0) + 1
        _save_state(state)


def _save_state(state: dict) -> None:
    state["updated_at"] = datetime.now(KST).isoformat()
    _db().collection(RUNS).document(state["run_id"]).set(state)


def run_backfill_step(run_id: str, start: str | None = None, end: str | None = None,
                      max_refine: int | None = None) -> dict:
    """시간 예산만큼 진행하고 현재 상태를 반환. 처음 호출 시 run 생성."""
    deadline = time.time() + BUDGET_SEC
    ref = _db().collection(RUNS).document(run_id)
    snap = ref.get()
    if snap.exists:
        state = snap.to_dict()
    else:
        today = datetime.now(KST).date()
        state = {
            "run_id": run_id,
            "start": start or (today - timedelta(days=365)).isoformat(),
            "end": end or (today - timedelta(days=1)).isoformat(),
            "keywords": DEFAULT_KEYWORDS,
            "max_refine": max_refine or DEFAULT_MAX_REFINE,
            "phase": "collect",
            "created_at": datetime.now(KST).isoformat(),
        }
        state["next_day"] = state["start"]

    # 동시 실행 방지 (이전 호출이 아직 도는 중이면 건너뜀)
    lock = state.get("lock_until")
    if lock and datetime.fromisoformat(lock) > datetime.now(KST):
        return {"skipped": "running", **{k: state.get(k) for k in ("phase", "next_day", "refined")}}
    state["lock_until"] = (datetime.now(KST) + timedelta(seconds=BUDGET_SEC + 30)).isoformat()
    _save_state(state)

    try:
        if state["phase"] == "collect":
            _do_collect(state, deadline)
        if state["phase"] == "refine":
            _do_refine(state, deadline)
    finally:
        state["lock_until"] = None
        _save_state(state)
    return {k: v for k, v in state.items() if k != "keywords"}
