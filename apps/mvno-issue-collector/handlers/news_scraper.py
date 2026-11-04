"""
handlers/news_scraper.py  v1.1
작성일: 2026-10-05

[수정 이력]
[v1.1 / 2026-11-04] Google News 429 재시도·간격 추가, 브리핑 날짜 KST 표시

[개요]
하루 1회, 알뜰폰/MVNO 관련 뉴스를 Google News RSS에서 수집해
- 중복/동일 토픽 묶음(Gemini 클러스터링)
- 광고성/보도자료성 기사 제외
- 영향도(상/중) 높은 기사만
선별하여 이슈방(TELEGRAM_CHAT_ID)에 다이제스트로 전송한다.

검색 키워드는 기존 price-monitor(ppomppu/dcinside 통합 수집기)의
core/mvno_classifier.py에 쓰이는 MVNO_KEYWORDS/_TELECOM_KW/MVNO_PROVIDERS
분류체계를 참고해 구성 (알뜰폰/MVNO 핵심어 + 정책/요금제 축 포함).

[동작 단계]
1. RSS 수집: 키워드별 Google News RSS 검색 → (title, source, pubDate, google_link)
2. 1차 필터: 최근 48시간 이내 + 이미 보낸(Firestore scraped_news_seen) 기사 제외
3. 2차 Gemini 트리아지 (제목만, 배치 1회): 동일 토픽 클러스터링 → 대표기사 1건 선정
   + 광고성 여부 + 예비 영향도 판단
4. 생존 기사만 Google News 리다이렉트 디코딩 → 원문 URL → 본문 크롤링
   (input_handler._fetch_article 재사용)
5. 3차 Gemini 확인 (본문 포함, 배치 1회): 최종 영향도/광고성 재확인 + 1~2줄 시사점
6. 영향도 상/중 & 비광고성만 채택 → Firestore에 seen 기록 → 다이제스트 전송
"""

import os
import re
import json
import logging
import hashlib
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore
import google.generativeai as genai

from handlers.input_handler import _fetch_article
from handlers.gemini_refiner import refine_input
from handlers.duplicate_checker import check_duplicate
from handlers.news_drafts import save_draft

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SEEN_COLLECTION = "scraped_news_seen"
SEEN_TTL_DAYS = 14
KST = timezone(timedelta(hours=9))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# [키워드 - 20261005] price-monitor/core/mvno_classifier.py의
# MVNO_KEYWORDS(\b알뜰폰\b, \bMVNO\b 등) + _TELECOM_KW(요금제/도매대가류 정책어) 체계를
# "검색어" 용도로 압축. 분류기처럼 수십개 사업자명까지 쓰지 않는 이유는 Google News가
# "알뜰폰"/"MVNO" 두 핵심어만으로도 사업자 개별 뉴스를 충분히 끌어오기 때문(실측 확인:
# "알뜰폰" 검색 결과에 KT Japan 'tt mobile' 등 사업자발 뉴스도 자연히 포함됨).
NEWS_SEARCH_KEYWORDS = [
    "알뜰폰",
    "MVNO",
    "알뜰폰 요금제",
    "알뜰폰 정책",
]

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


# ───────────────────────── RSS 수집 ─────────────────────────

def _fetch_rss(keyword: str) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote(keyword)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"RSS 수집 실패 ({keyword}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "xml")
    items = []
    for it in soup.find_all("item"):
        title_el = it.find("title")
        link_el = it.find("link")
        pub_el = it.find("pubDate")
        src_el = it.find("source")
        if not (title_el and link_el):
            continue
        items.append({
            "title": title_el.text.strip(),
            "google_link": link_el.text.strip(),
            "source": src_el.text.strip() if src_el else "",
            "pub_date": pub_el.text.strip() if pub_el else "",
            "keyword": keyword,
        })
    return items


def _parse_pubdate(pub_date: str) -> datetime | None:
    # RFC822 포맷: "Mon, 05 Oct 2026 03:00:00 GMT"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _collect_candidates(hours: int = 48) -> list[dict]:
    seen_titles = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    candidates = []

    for kw in NEWS_SEARCH_KEYWORDS:
        for item in _fetch_rss(kw):
            title = item["title"]
            if title in seen_titles:
                continue
            pub_dt = _parse_pubdate(item["pub_date"])
            if pub_dt and pub_dt < cutoff:
                continue
            seen_titles.add(title)
            candidates.append(item)

    return candidates


# ───────────────────────── seen 체크 (Firestore) ─────────────────────────

def _title_hash(title: str) -> str:
    normalized = re.sub(r"\s+", "", title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _filter_unseen(candidates: list[dict]) -> list[dict]:
    db = get_db()
    unseen = []
    for c in candidates:
        doc_id = _title_hash(c["title"])
        if db.collection(SEEN_COLLECTION).document(doc_id).get().exists:
            continue
        c["_seen_doc_id"] = doc_id
        unseen.append(c)
    return unseen


def _mark_seen(items: list[dict]):
    db = get_db()
    now = datetime.now(timezone.utc)
    batch = db.batch()
    for item in items:
        ref = db.collection(SEEN_COLLECTION).document(item["_seen_doc_id"])
        batch.set(ref, {
            "title": item["title"],
            "source": item.get("source", ""),
            "seen_at": now.isoformat(),
        })
    batch.commit()


# ───────────────────────── Google News 리다이렉트 디코딩 ─────────────────────────

_SG = re.compile(r'data-n-a-sg="([^"]+)"')
_TS = re.compile(r'data-n-a-ts="([^"]+)"')
_BATCHEXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_GARTURLREQ_CTX = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "KR:ko", None, 1, None, None, None, None, None, 0, 1],
    "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
]


def _article_id(google_link: str) -> str | None:
    try:
        url = urlparse(google_link)
        path = url.path.split("/")
        if url.hostname == "news.google.com" and len(path) > 1 and path[-2] in ("articles", "read"):
            return path[-1] or None
    except Exception:
        return None
    return None


# [수정 20261104] 운영(Cloud Run)에서 batchexecute가 간헐적으로 429(Too Many Requests,
# google.com/sorry)를 받아 원문 URL 디코딩이 실패 → 본문 없이 제목만으로 판정되고 브리핑
# 링크도 news.google.com 리다이렉트로 남았음 (실측: 2026-11-04 07:45 실행 2건 모두 429).
# 429/503은 잠깐 쉬었다가 재시도하고, 기사 사이에도 간격을 둬서 연속 호출을 줄임.
_RETRY_STATUS = (429, 503)
_RETRY_WAITS = (3, 8, 15)  # 초. 최악 26초/건, 생존 기사는 보통 몇 건이라 540s 타임아웃 안쪽
DECODE_INTERVAL_SEC = 2


def _request_with_backoff(method: str, url: str, **kwargs) -> requests.Response | None:
    for attempt in range(len(_RETRY_WAITS) + 1):
        try:
            resp = requests.request(method, url, timeout=10, **kwargs)
        except Exception as e:
            logger.warning(f"요청 실패 ({method} {url[:60]}): {e}")
            resp = None
        if resp is not None and resp.status_code not in _RETRY_STATUS:
            return resp
        if attempt < len(_RETRY_WAITS):
            wait = _RETRY_WAITS[attempt]
            code = resp.status_code if resp is not None else "error"
            logger.warning(f"Google News {code} → {wait}초 후 재시도 ({attempt + 1}/{len(_RETRY_WAITS)})")
            time.sleep(wait)
    return resp


def _decode_google_news_url(google_link: str) -> str | None:
    """Google News RSS의 리다이렉트 링크를 실제 기사 URL로 디코딩."""
    art_id = _article_id(google_link)
    if not art_id:
        return None

    page_url = f"https://news.google.com/rss/articles/{art_id}?hl=ko&gl=KR&ceid=KR:ko"
    resp = _request_with_backoff("GET", page_url, headers={"User-Agent": UA})
    if resp is None or resp.status_code != 200:
        logger.warning(f"Google News 페이지 조회 실패: {getattr(resp, 'status_code', 'error')}")
        return None

    sg_m = _SG.search(resp.text)
    ts_m = _TS.search(resp.text)
    if not (sg_m and ts_m):
        return None

    inner = ["garturlreq", _GARTURLREQ_CTX, art_id,
             int(ts_m.group(1)) if ts_m.group(1).isdigit() else ts_m.group(1), sg_m.group(1)]
    envelope = [["Fbv4je", json.dumps(inner, separators=(",", ":")), None, "0"]]
    body = f"f.req={quote(json.dumps([envelope], separators=(',', ':')))}"

    try:
        r2 = _request_with_backoff(
            "POST", _BATCHEXECUTE_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": UA},
            data=body,
        )
        if r2 is None:
            raise RuntimeError("응답 없음")
        r2.raise_for_status()
    except Exception as e:
        logger.warning(f"batchexecute 요청 실패: {e}")
        return None

    text = r2.text
    if "\n\n" in text:
        text = text.split("\n\n", 1)[1]
    try:
        rows = json.loads(text.lstrip())
    except Exception as e:
        logger.warning(f"batchexecute 응답 파싱 실패: {e}")
        return None

    for row in rows:
        if not (isinstance(row, list) and len(row) >= 3):
            continue
        if row[0] == "wrb.fr" or (len(row) > 1 and row[1] == "Fbv4je"):
            payload = row[2]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    continue
            if isinstance(payload, list) and payload and payload[0] == "garturlres":
                return payload[1]
    return None


# ───────────────────────── Gemini 트리아지 ─────────────────────────

_TRIAGE_PROMPT = """당신은 SKT MVNO(알뜰폰) 팀의 뉴스 모니터링 담당자입니다.
아래는 오늘 수집된 알뜰폰/MVNO 관련 뉴스 제목 목록입니다 (번호, 제목, 출처, 키워드).

[작업]
1. 같은 사건/이슈를 다루는 기사들을 하나의 클러스터로 묶으세요 (여러 언론사가 동일 사건을
   보도하는 경우가 많습니다. 예: 여러 매체가 같은 신제품 출시를 각자 보도).
2. 각 클러스터마다 대표 기사 1건만 선택하세요 (가능하면 통신/IT 전문지나 주요 언론사:
   연합뉴스, 뉴시스, 전자신문(etnews), 지디넷코리아, 디지털데일리 등을 우선. 없으면 가장
   상세해 보이는 제목을 선택).
3. 각 대표 기사에 대해 판단하세요:
   - relevant: SKT MVNO 팀 업무와 실제로 관련있는 알뜰폰/MVNO 산업 뉴스인가?
     (단순 통신 일반 뉴스, 알뜰폰과 무관한 내용은 false)
   - advertorial: 특정 사업자의 단순 홍보/판매 유도성 보도자료 기사인가?
     (예: "~요금제 출시, 지금 가입하면 혜택" 식의 광고성 기사는 true.
      반대로 정책/규제/시장동향/경쟁구도/실적 등 분석 가치가 있는 기사는 false)
   - impact_level: 제목만으로 예비 판단한 영향도 (상/중/하).
     SKT MVNO의 가입자·매출·정책대응에 영향을 줄 수 있는 규제/정책/대형 경쟁사 동향은 상,
     개별 사업자 소식/통계는 중, 단순 홍보·사소한 소식은 하.

[출력]
JSON 배열만 출력 (마크다운 코드블록 금지). 각 원소:
{{"index": 대표기사의 원래 번호, "relevant": true/false, "advertorial": true/false, "impact_level": "상|중|하"}}
relevant=false 이거나 advertorial=true 이거나 impact_level="하" 인 클러스터도 모두 포함해서 반환하세요
(이후 단계에서 필터링합니다). 클러스터에 속하지 않고 대표로 뽑히지 않은 번호는 출력하지 마세요.

[뉴스 목록]
{items}
"""


def _gemini_json(prompt: str) -> list | dict | None:
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Gemini 트리아지 오류: {e}", exc_info=True)
        return None


def _triage_titles(candidates: list[dict]) -> list[dict]:
    lines = []
    for i, c in enumerate(candidates):
        lines.append(f"{i}. {c['title']} | 출처: {c.get('source','')} | 검색어: {c.get('keyword','')}")
    prompt = _TRIAGE_PROMPT.format(items="\n".join(lines))

    result = _gemini_json(prompt)
    if not isinstance(result, list):
        logger.warning("Gemini 트리아지 응답이 리스트가 아님, 전체 스킵")
        return []

    survivors = []
    for verdict in result:
        try:
            idx = int(verdict.get("index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(candidates):
            continue
        if not verdict.get("relevant"):
            continue
        if verdict.get("advertorial"):
            continue
        if verdict.get("impact_level") not in ("상", "중"):
            continue
        item = dict(candidates[idx])
        item["_prelim_impact"] = verdict.get("impact_level")
        survivors.append(item)
    return survivors


_CONFIRM_PROMPT = """당신은 SKT MVNO(알뜰폰) 팀의 뉴스 모니터링 담당자입니다.
아래 기사의 제목과 본문 일부를 보고 최종 판단해주세요.

[팀 포지션]
당사: SKT MVNO 운영사. 경쟁사: KT계열(KTM), LG계열(유모바일/헬로모바일) MVNO.

[기사]
제목: {title}
출처: {source}
본문:
{content}

[출력] JSON만 (마크다운 코드블록 금지):
{{
  "relevant": true/false,
  "advertorial": true/false,
  "impact_level": "상|중|하",
  "one_line": "SKT MVNO 관점에서 이 기사가 왜 중요한지 1문장 (막연한 '모니터링 필요' 금지, 구체적으로)"
}}
"""


def _confirm_with_content(item: dict) -> dict | None:
    content = item.get("content", "")[:2500]
    prompt = _CONFIRM_PROMPT.format(
        title=item["title"], source=item.get("source", ""), content=content or "(본문 추출 실패, 제목만으로 판단)"
    )
    return _gemini_json(prompt)


# ───────────────────────── 등록 draft 생성 ─────────────────────────

def _make_draft_id(item: dict) -> str:
    raw = (item.get("url") or item["google_link"]) + item["title"]
    return "n" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:11]


def _build_issue_draft(item: dict) -> dict | None:
    """기사 내용을 gemini_refiner.refine_input()에 통과시켜, 수동으로 링크를 붙여넣었을 때와
    동일한 형식의 mvno_issues 구조화 draft를 생성. source는 자동수집 정보로 덮어씀."""
    raw_input = (
        f"[기사 제목: {item['title']}]\n[출처: {item.get('source','')}]\n[URL: {item.get('url','')}]\n\n"
        f"{item.get('content') or '(본문 추출 실패)'}"
    )
    result = refine_input(raw_input)
    if not result:
        return None
    record = result[0] if isinstance(result, list) else result
    record["source"] = {
        "type": "기사URL",
        "origin": item.get("source", ""),
        "ref": item.get("url", ""),
        "raw_input": item.get("content", "")[:2000],
    }
    record["tags"] = list(set((record.get("tags") or []) + ["자동수집"]))
    return record


def _format_pub_date(pub_date: str) -> str:
    dt = _parse_pubdate(pub_date)
    if not dt:
        return "-"
    kst = dt.astimezone(KST)
    return kst.strftime("%m/%d %H:%M")


def _build_compact_entry(index: int, item: dict, record: dict, dup: dict | None) -> str:
    mark = "🔴" if item["impact_level"] == "상" else "🟡"
    title_link = f'<a href="{item["url"]}">{item["title"]}</a>'
    lines = [
        f"{index}. {mark} <b>{title_link}</b>",
        f"   🏷 {record.get('category','-')} | 📡 {record.get('network','-')} | 출처: {item.get('source','')} | 📅 {_format_pub_date(item.get('pub_date',''))}",
        f"   💬 {item['one_line']}",
    ]
    if dup:
        lines.append(f"   ⚠️ 유사 이슈 있음: {dup['id']}")
    return "\n".join(lines)


# ───────────────────────── 메인 파이프라인 ─────────────────────────

def run_daily_news_scrape(dry_run: bool = False) -> str:
    """일일 뉴스 스크랩 파이프라인 실행. 반환값은 전송(또는 미전송)한 다이제스트 텍스트."""
    candidates = _collect_candidates()
    logger.info(f"수집된 후보: {len(candidates)}건")
    if not candidates:
        return "📭 수집된 알뜰폰 관련 뉴스가 없습니다."

    candidates = _filter_unseen(candidates)
    logger.info(f"미전송 후보: {len(candidates)}건")
    if not candidates:
        return "📭 신규(미전송) 알뜰폰 관련 뉴스가 없습니다."

    survivors = _triage_titles(candidates)
    logger.info(f"1차 트리아지 생존: {len(survivors)}건")
    if not survivors:
        if not dry_run:
            _mark_seen(candidates)
        return "📭 영향도 높은 신규 알뜰폰 뉴스가 없습니다 (광고성/저영향 기사 제외됨)."

    # 1차 트리아지에서 제목만으로 걸러진 건들은 그대로 seen 처리 (제목은 안 바뀌므로
    # 재평가해도 같은 결과). survivors는 _triage_titles에서 dict(...)로 복사된 새
    # 객체라 title로만 원본 candidates와 매칭 가능 (title은 _collect_candidates에서
    # 이미 중복 제거되어 유일함).
    survivor_titles = {s["title"] for s in survivors}
    seen_candidates = [c for c in candidates if c["title"] not in survivor_titles]

    final_items = []
    for n, item in enumerate(survivors):
        if n:
            time.sleep(DECODE_INTERVAL_SEC)
        real_url = _decode_google_news_url(item["google_link"])
        if not real_url:
            logger.warning(f"원문 URL 디코딩 실패 → 제목만으로 판정: {item['title']}")
        item["url"] = real_url or item["google_link"]
        content = _fetch_article(real_url) if real_url else None
        item["content"] = content or ""
        content_fetch_failed = not content

        verdict = _confirm_with_content(item)
        if not verdict:
            # Gemini 확인 실패 시 1차 트리아지 결과로 대체 (보수적으로 포함)
            item["impact_level"] = item.get("_prelim_impact", "중")
            item["one_line"] = item["title"]
            final_items.append(item)
            seen_candidates.append(item)
            continue

        rejected = (not verdict.get("relevant") or verdict.get("advertorial")
                    or verdict.get("impact_level") not in ("상", "중"))
        if rejected:
            # [수정 20261006] 본문 크롤링이 (타임아웃 등 일시적 오류로) 실패해서
            # 제목만 보고 탈락한 경우는 seen 처리하지 않음 - 다음 실행에서 사이트가
            # 복구되면 본문까지 포함해 다시 평가받을 기회를 줌. 실측: metroseoul.co.kr
            # 접속 타임아웃으로 탈락한 기사가 영구 seen 처리되어 다시 뜨지 않았음.
            # 본문을 실제로 읽고 탈락시킨 경우는 근거가 있는 판단이므로 그대로 seen.
            if not content_fetch_failed:
                seen_candidates.append(item)
            continue

        item["impact_level"] = verdict["impact_level"]
        item["one_line"] = verdict.get("one_line", item["title"])
        final_items.append(item)
        seen_candidates.append(item)

    if not dry_run:
        _mark_seen(seen_candidates)

    if not final_items:
        return "📭 영향도 높은 신규 알뜰폰 뉴스가 없습니다 (최종 확인 단계에서 제외됨)."

    final_items.sort(key=lambda x: 0 if x["impact_level"] == "상" else 1)

    # [수정 20261104] UTC 날짜를 쓰면 07:45 KST 실행 시 전날 날짜가 찍혀 KST로 변경
    today = datetime.now(KST).strftime("%Y-%m-%d")
    header = f"📰 <b>알뜰폰 뉴스 브리핑</b> ({today}) - 영향도 높은 신규 기사 {len(final_items)}건"

    entries = []
    for it in final_items:
        record = _build_issue_draft(it)
        if not record:
            continue
        entries.append({
            "item": it,
            "record": record,
            "duplicate": check_duplicate(record),
            "draft_id": _make_draft_id(it),
        })

    if not entries:
        return "📭 영향도 높은 신규 알뜰폰 뉴스가 없습니다 (draft 생성 실패)."

    # [수정 20261005] 기사 여러 건을 메시지 1개로 모아서 보여주고, 번호 버튼으로 선택.
    # session.py(chat당 세션 슬롯 1개)를 바로 쓰면 여러 draft가 동시에 떠 있는 상태에서
    # 세션이 덮어써지는 충돌이 생기므로, 기사별로 news_drafts에 독립 저장해두고 버튼의
    # 콜백데이터에 draft_id를 직접 심음.
    # [수정 20261006] 번호 버튼 클릭 시 바로 저장하지 않고, 먼저 등록될 내용(카테고리/
    # 요약/시사점 등)을 수동입력 때와 동일한 _build_preview로 보여준 뒤 ✅등록/✏️수정/
    # ❌취소를 고르게 함 ("맘에 안들면 수정" 요구). 이 미리보기 단계부터는 기사 1건만
    # 다루므로 session.py로 넘겨서 기존 수정/등록 플로우(edit_handler 등)를 그대로 재사용.
    MAX_ENTRIES_PER_MESSAGE = 8  # Telegram 메시지 4096자 제한 안에서 안전하게
    shown = entries[:MAX_ENTRIES_PER_MESSAGE]
    omitted = len(entries) - len(shown)

    body = "\n\n".join(
        _build_compact_entry(i, e["item"], e["record"], e["duplicate"])
        for i, e in enumerate(shown, start=1)
    )
    text = f"{header}\n\n{body}"
    if omitted > 0:
        text += f"\n\n(영향도 낮은 {omitted}건 생략됨)"
    text += "\n\n👇 등록 전 내용을 확인할 기사 번호를 선택하세요"

    buttons, row = [], []
    for i, e in enumerate(shown, start=1):
        row.append({"text": f"{i}번 확인", "callback_data": f"newsreg:preview:{e['draft_id']}"})
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if not dry_run:
        from handlers.telegram import send_message_with_buttons
        if CHAT_ID:
            for e in shown:
                save_draft(e["draft_id"], e["record"], e["duplicate"])
            send_message_with_buttons(CHAT_ID, text, buttons)
            logger.info(f"뉴스 다이제스트 전송 완료: {len(shown)}건 (전체 {len(entries)}건 중)")
        else:
            logger.error("TELEGRAM_CHAT_ID 환경변수 없음")

    return text
