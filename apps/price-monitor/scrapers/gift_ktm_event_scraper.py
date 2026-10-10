# -*- coding: utf-8 -*-
"""
gift_ktm_event_scraper.py - KT엠모바일 직영 이벤트 페이지 수집기
- gift_umobile_event_scraper.py와 동일 아키텍처 (스키마/캐싱/Vision 프롬프트 스타일 통일)
- 차이점: SSR(requests+BS4)이 아니라 SPA라서 Playwright 필요, 목록 카드 구조도 다름

[수정 이력]
- v0.1~v0.4 (2026-08-25): 초기 골격 + 리스트/상세 셀렉터 확정 + 필터 키워드 보강 (이전 버전)
- v0.5 (2026-08-25): networkidle → domcontentloaded (트래킹 스크립트로 인한 타임아웃 해결)
- v0.6 (2026-08-25): 실수집 24건 확인 후 필터 보강
- v0.7 (2026-08-25): gift_umobile_event_scraper.py 실물 확인 후 구조 전면 정합화
  * google.generativeai(deprecated) → google.genai 로 교체 (기존 코드가 잘못된 패키지 사용 중이었음)
  * 60만원 상한 로직을 수집 단계(_cap_amount)에서 제거 → 텔레그램 포맷 단계로 이동 (유모바일과 동일 위치)
  * Vision 출력 스키마를 유모바일과 통일: plan_name/total_gb/base_gb/random_gb/speed_mbps/benefits[]/total_won
  * 날짜 정규식을 KT 표기(YYYY.MM.DD)에 맞게 수정 + MAX_EVENT_DAYS(60일) 필터 추가
    → "2026.01.01~2026.12.31" 같은 상시 배너 페이지(M마켓/M쿠폰/셀프개통 등)가 이 필터 하나로 자동 제외됨
  * parse_images_with_vision, scrape_with_cache, format_telegram_message 함수명/시그니처를 유모바일과 통일
- v0.8 (2026-08-25): 실제 GCP 테스트로 Vision 파싱 End-to-End 확인 (1818번 "또드림" 이벤트, 32장 → 11건 파싱 성공,
  금액 실제 사이트와 일치 확인). "요금제 3종/5종" 같은 요약 배너가 유령 플랜으로 잡히는 문제 발견 →
  프롬프트 규칙 8번 추가 (구체적 요금제 1개를 지칭하지 않는 요약 이미지는 빈 배열 처리, "N종" 이름 금지)
- v0.9 (2026-08-25): scrape_with_cache 테스트 중 "인터넷+TV+모바일 최대 226만원..." 결합상품 이벤트가
  안 걸러지고 이미지 94장까지 Vision 호출되는 문제 발견. 제목에 "결합"이란 단어가 없어서 기존 키워드가
  매칭 안 됐던 것 → "인터넷+" 키워드 추가로 보강.
- v0.10 (2026-08-25): 캐시 재사용이 전혀 안 되는 문제 발견 (같은 이벤트가 재실행마다 "신규"로 잡힘).
  원인: html_hash를 image_urls 리스트 순서 그대로 join해서 계산 → Playwright 재방문마다 DOM에
  이미지가 잡히는 순서가 달라질 수 있어 해시가 매번 바뀜 → sorted(image_urls)로 정렬 후 해시 계산하도록 수정.
  → 재테스트로 캐시 재사용 정상 동작 확인 완료 (3건 모두 from_cache:True, Vision 0회 호출).
- v0.11 (2026-08-25): STEP 5 format_telegram_message() 추가 (유모바일과 동일 구조).
  60만원 상한(PLAN_VAL_CAP) 여기서 적용, 구간별 최고 이벤트 + 버튼 리스트 생성.
- v0.12 (2026-08-25): 비용/속도 최적화. 일부 오래된 이벤트(예: 937번)는 본문 이미지 파일명 자체가
  내용 태깅되어 있음 확인 ("11_갤럭시 자급제.png", "2_친구초대1(3).png" 등) → fetch_post_images에서
  EXCLUDE_KEYWORDS를 파일명에도 적용해 불필요한 Vision 호출을 사전 차단.
- v0.13 (2026-08-25): 22건 실제 돌려본 결과, 서로 다른 이벤트(937/938 등)에 동일한 공통 템플릿/배너
  이미지("M코드-초저가.png", "12_캐치콜플러스.png" 등)가 반복 등장하는데 이벤트 단위 캐시(html_hash)로는
  못 잡아서 매 이벤트마다 같은 이미지를 또 Vision 호출하는 비효율 발견.
  → parse_images_with_vision에 이미지 URL 단위 전역 캐시(ktm_image_cache, db 인자로 전달) 추가.
  빈 결과([])도 캐시해서 "이 이미지는 혜택카드 아님"이 확정되면 다시 안 물어봄.
"""

import os
import re
import json
import base64
import hashlib
import logging
import requests
from urllib.parse import quote
from datetime import datetime, timezone, date

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

LIST_URL = "https://www.ktmmobile.com/event/eventBoardList.do"
BASE_URL = "https://www.ktmmobile.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

# 제목에 포함되면 사은품 비교 대상에서 제외
EXCLUDE_KEYWORDS = [
    "휴대폰", "갤럭시", "아이폰", "스마트폰", "자급제", "eSIM",
    "친구",       # "친구초대", "친구 초대" 둘 다 커버
    "후기",       # "리뷰", "사용후기" 등
    "모아보기", "모음", "zip",
    "워치", "유심", "개통", "퀵배송",
    "M마켓", "M쿠폰", "바로카드", "안심보험",
    "결합", "인터넷+",   # 결합상품 ("인터넷+TV+모바일" 처럼 "결합"이란 단어가 없는 경우도 커버)
]

# 종료일 기준 최대 파싱 일수 (상시 배너 페이지 제외 - 유모바일과 동일 정책)
MAX_EVENT_DAYS = 60

# 리스트 페이지 셀렉터 (devtools 캡처로 확정)
SEL_EVENT_CARD = "li.event-list__item"
SEL_EVENT_ANCHOR = "a.event-list__anchor"
SEL_EVENT_TITLE = "span.event-list__title"
SEL_EVENT_SUB = "div.event-list__sub"

# 상세 페이지 셀렉터 (devtools 캡처로 확정)
SEL_DETAIL_CONTAINER = "article.c-editor"
SEL_DETAIL_IMAGES = "article.c-editor img"

_RE_KTM_DATE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})")

# 구간 정의 (gift_comparator와 동일해야 함)
DATA_BANDS = [
    ("5GB 이하",   0,   5),
    ("5~9GB",      5,   9),
    ("10~15GB",   10,  15),
    ("16~49GB",   16,  49),
    ("50~99GB",   50,  99),
    ("100GB 이상",100, 9999),
]

# ⚠️ KT엠모바일 카드 실제 레이아웃(screenshots 확인) 기준 프롬프트.
# 유모바일과 톤은 같지만 카드 구성요소가 달라서 별도 작성함
# (요금제명 + GB/통화 스펙 + 혜택박스[네이버페이 3.5만원X8개월 등] + 가격/월체감가)
GEMINI_VISION_PROMPT = """당신은 통신사 이벤트 이미지에서 사은품/혜택 정보를 추출하는 분석기입니다.
이미지에서 요금제별 혜택 정보를 추출해 아래 JSON 배열로만 답하세요.
설명, 마크다운, 코드펜스 없이 순수 JSON만 출력하세요.

이미지 구조 (KT엠모바일 요금제 카드 UI):
  ┌─────────────────────────────────┐
  │ [굵은 검정] 모두다 맘껏 안심 20GB+   ← plan_name
  │ [회색 아이콘] 20GB+최대400Kbps      ← total_gb / speed_mbps
  │ [전화 아이콘] 기본제공 +영상/부가통화 30분  ← 통화 관련 (무시)
  │ 🎁 네이버페이 3.5만원 X 8개월        ← benefit 1
  │ + 바로배송/바로유심/쿠팡유심 2만원    ← benefit 2 (1회성)
  │ 16,400원          월 체감가 0원      ← 요금제 정가 / 체감가 (무시, benefits와 무관)
  └─────────────────────────────────┘

스키마:
[
  {
    "plan_name": "모두다 맘껏 안심 20GB+",
    "total_gb": 20,
    "base_gb": 20,
    "random_gb": 0,
    "speed_mbps": 0.4,
    "benefits": [
      {
        "name": "혜택명 (예: 네이버페이, 쿠팡캐시, 밀리의서재)",
        "condition": "조건 (예: 요금제 가입 시)",
        "amount_won": 1회 금액(원, 숫자),
        "months": 개월수(1회성=1),
        "total_won": amount_won * months
      }
    ],
    "total_won": benefits total_won 합계
  }
]

규칙:
1. plan_name은 요금제 카드의 굵은 제목 텍스트 사용
2. total_gb = 기본 제공 GB (기본+보너스 합산 아닌 첫 숫자 우선)
3. "N천원X M개월" → amount_won=N*1000, months=M, total_won=amount_won*months
   "매달"/"매월" + 금액 → months만큼 반복 지급
4. "N천원"=N*1000, "N만원"=N*10000
5. 정가/체감가(월 X원) 는 요금제 요금 정보이지 사은품이 아니므로 benefits에 포함하지 말 것
6. 혜택 박스(🎁, + 아이콘 등)가 전혀 없는 키비주얼·배너·안내 이미지는 빈 배열 [] 출력
7. 금액 없는 혜택(추첨 등)은 amount_won=0
8. 특정 요금제 1개를 명확히 지칭하지 않는 "요약/전체 안내" 이미지
   (예: "3종 요금제 공통 혜택", "5종 요금제 대상" 처럼 여러 요금제를 뭉뚱그린 배너)는
   빈 배열 [] 출력. plan_name은 반드시 구체적인 요금제 1개의 실제 이름이어야 하며,
   "요금제 N종"처럼 개수만 표기된 이름은 절대 사용하지 말 것.
9. "대상 단말 자급제 등록 혜택"처럼 특정 자급제 단말 구매·등록이 조건인 혜택은
   요금제 가입 자체의 사은품이 아니라 단말 구매에 연동된 혜택이므로 benefits에
   포함하지 말 것 (total_won 계산에서도 제외).
"""


_DEVICE_LINKED_KEYWORDS = ['자급제']


def _strip_device_linked_benefits(plan: dict) -> dict:
    """
    [추가 20260925] "대상 단말 자급제 등록 혜택"처럼 특정 자급제 단말 구매·등록이
    전제조건인 혜택은 순수 요금제 가입 사은품이 아니라 단말 구매에 연동된 혜택이라
    K CUP 비교(모요 vs 직영) 대상에서 빼야 함(사장님 지적: "자급제혜택은
    프로모션계산에서 빼야함"). Vision 프롬프트에도 제외 지시를 추가했지만 LLM
    프롬프트 준수는 비결정적이라, 이미 Firestore에 캐시된 과거 파싱 결과에도
    일괄 적용되도록 캐시/신규 파싱 양쪽 병합 시점에서 다시 한번 필터링.
    """
    # [수정 20261010] 자급제뿐 아니라 친구추천·구독 이용권·할인쿠폰도 비교 금액에서 제외 (core.gift_rules - 모요와 같은 규칙)
    from core.gift_rules import is_compare_excluded, normalize_bbaek_benefit
    benefits = plan.get('benefits') or []
    kept = [normalize_bbaek_benefit(b) for b in benefits
            if not is_compare_excluded(f"{b.get('name', '')} {b.get('condition', '')}")]
    if kept == benefits:
        return plan
    plan = dict(plan)
    plan['benefits']   = kept
    plan['total_won']  = sum(int(b.get('total_won') or 0) for b in kept)
    return plan


def _looks_excluded(title: str) -> bool:
    lowered = title.lower()
    return any(kw.lower() in lowered for kw in EXCLUDE_KEYWORDS)


# ──────────────────────────────────────────
# STEP 1: 목록 수집 (Playwright, SPA라서 requests 불가)
# ──────────────────────────────────────────
def fetch_event_list(gift_only: bool = True) -> list:
    """
    진행중 이벤트 목록 수집
    Returns: [{post_id, url, title, date_start, date_end}]
    """
    events = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(SEL_EVENT_CARD, timeout=20000)

        cards = page.query_selector_all(SEL_EVENT_CARD)
        for card in cards:
            anchor = card.query_selector(SEL_EVENT_ANCHOR)
            if not anchor:
                continue
            ntcartseq = anchor.get_attribute("ntcartseq")
            if not ntcartseq:
                continue

            title_el = card.query_selector(SEL_EVENT_TITLE)
            title = title_el.inner_text().strip() if title_el else ""
            if not title:
                continue

            sub_el = card.query_selector(SEL_EVENT_SUB)
            sub_text = sub_el.inner_text().strip() if sub_el else ""

            date_match = _RE_KTM_DATE.search(sub_text)
            if date_match:
                y1, m1, d1, y2, m2, d2 = date_match.groups()
                date_start = f"{y1}-{m1}-{d1}"
                date_end = f"{y2}-{m2}-{d2}"
            else:
                date_start = date_end = ""

            events.append({
                "post_id": ntcartseq,
                "url": f"{BASE_URL}/event/eventDetail.do?ntcartSeq={ntcartseq}&sbstCtg=E&eventBranch=E",
                "title": title,
                "date_start": date_start,
                "date_end": date_end,
            })

        browser.close()

    print(f"[ktm] 목록 수집: {len(events)}건")

    if gift_only:
        today = date.today()
        filtered = []
        for ev in events:
            title = ev["title"]

            if _looks_excluded(title):
                print(f"[ktm] 제외 키워드 스킵: {title[:30]}")
                continue

            date_end = ev.get("date_end", "")
            if date_end:
                try:
                    end = date.fromisoformat(date_end)
                    days_left = (end - today).days
                    if days_left > MAX_EVENT_DAYS:
                        print(f"[ktm] 장기/상시 배너 스킵 (D+{days_left}): {title[:30]}")
                        continue
                except ValueError:
                    pass
            # 종료일 파싱 실패 시 상시 이벤트로 간주하고 포함 (유모바일과 동일 정책)

            filtered.append(ev)

        events = filtered
        print(f"[ktm] 필터 후: {len(events)}건")

    return events


# ──────────────────────────────────────────
# STEP 2: 상세 페이지 이미지 수집
# ──────────────────────────────────────────
def fetch_post_images(post_url: str) -> tuple:
    """
    상세 페이지 → (html_hash, image_urls)
    KT엠모바일은 페이지당 이미지가 여러 장(요금제 카드별 1장씩)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(SEL_DETAIL_CONTAINER, timeout=20000)

        image_urls = []
        seen = set()
        for img_el in page.query_selector_all(SEL_DETAIL_IMAGES):
            src = img_el.get_attribute("src")
            if not src:
                continue
            width = img_el.get_attribute("width")
            if width and width.isdigit() and int(width) < 200:
                continue  # 아이콘/로고성 이미지 배제
            # 파일명 자체에 컨텐츠가 태깅된 경우가 많음 (예: "11_갤럭시 자급제.png", "2_친구초대1(3).png")
            # → EXCLUDE_KEYWORDS로 1차 필터링해서 불필요한 Vision 호출 자체를 줄임
            fname = src.split("/")[-1]
            if _looks_excluded(fname):
                continue
            full = src if src.startswith("http") else f"{BASE_URL}{src}"
            if full not in seen:
                seen.add(full)
                image_urls.append(full)

        browser.close()

    html_hash = hashlib.md5("|".join(sorted(image_urls)).encode("utf-8")).hexdigest()
    return html_hash, image_urls


# ──────────────────────────────────────────
# STEP 3: Gemini Vision 파싱 (유모바일과 동일 구조)
# ──────────────────────────────────────────
def _download_image_b64(url: str):
    encoded_url = quote(url, safe=":/?=&%+#")
    r = requests.get(encoded_url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    mime = r.headers.get("Content-Type", "image/png").split(";")[0]
    if not mime.startswith("image/"):
        mime = "image/png"
    return base64.standard_b64encode(r.content).decode("utf-8"), mime


def parse_images_with_vision(image_urls: list, db=None) -> list:
    """
    이미지 URL 목록 → Gemini Vision → [{plan_name, total_gb, base_gb, ...}]

    db가 주어지면 이미지 URL 단위 전역 캐시(ktm_image_cache)를 사용한다.
    같은 공통 템플릿/배너 이미지가 여러 이벤트 상세페이지에 반복 등장하는 경우가 많아서
    (예: "M코드-초저가.png", "12_캐치콜플러스.png" 등) 이벤트 단위 캐시(html_hash)만으로는
    이런 반복 이미지에 대해 매 이벤트마다 Vision을 다시 호출하게 됨.
    이미지 URL 자체를 키로 한 번 파싱한 결과(빈 배열 포함)를 재사용해 중복 호출을 없앤다.
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 없음")
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")

    img_cache_col = db.collection("ktm_image_cache") if db is not None else None

    merged = {}
    img_total = len(image_urls)
    cache_hit = 0
    for idx, url in enumerate(image_urls, 1):
        fname = url.split("/")[-1]
        img_id = hashlib.md5(url.encode("utf-8")).hexdigest()

        if img_cache_col is not None:
            cached_doc = img_cache_col.document(img_id).get()
            if cached_doc.exists:
                cache_hit += 1
                plans = cached_doc.to_dict().get("plans", [])
                for plan in plans:
                    name = str(plan.get("plan_name", "")).strip()
                    if not name:
                        continue
                    plan = _strip_device_linked_benefits(plan)
                    total = int(plan.get("total_won") or 0)
                    if name not in merged or total > merged[name].get("total_won", 0):
                        merged[name] = plan
                continue

        print(f"[ktm-vision] 이미지 {idx}/{img_total}: {fname}")
        try:
            b64, mime = _download_image_b64(url)
        except Exception as e:
            print(f"[ktm-vision] 다운로드 실패: {fname} | {e}")
            continue
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime),
                    GEMINI_VISION_PROMPT,
                ]
            )
            raw = (resp.text or "[]").strip()
            raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            plans = json.loads(raw)
            plans = plans if isinstance(plans, list) else []
            hit = len([p for p in plans if p.get("total_won", 0) > 0])
            print(f"[ktm-vision] {fname} → {len(plans)}건 파싱 (유효 {hit}건)")
        except Exception as e:
            print(f"[ktm-vision] 파싱 실패: {fname} | {e}")
            continue

        if img_cache_col is not None:
            img_cache_col.document(img_id).set({
                "url": url,
                "plans": plans,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            })

        for plan in plans:
            name = str(plan.get("plan_name", "")).strip()
            if not name:
                continue
            plan = _strip_device_linked_benefits(plan)
            total = int(plan.get("total_won") or 0)
            if name not in merged or total > merged[name].get("total_won", 0):
                merged[name] = plan

    results = list(merged.values())
    if img_cache_col is not None:
        print(f"[ktm-vision] 요금제 {len(results)}건 파싱 완료 (이미지 캐시 재사용 {cache_hit}/{img_total}장)")
    else:
        print(f"[ktm-vision] 요금제 {len(results)}건 파싱 완료")
    return results


# ──────────────────────────────────────────
# STEP 4: Firestore 캐시 기반 수집
# ──────────────────────────────────────────
def scrape_with_cache(db, max_posts: int = 16, gift_only: bool = True) -> list:
    """
    변경감지 기반 수집 (유모바일 scrape_with_cache와 동일 패턴)
    Returns: [{post_id, url, title, date_start, date_end, plans, from_cache}]
    """
    posts = fetch_event_list(gift_only=gift_only)
    results = []
    cache_col = db.collection("ktm_event_cache")

    for post in posts[:max_posts]:
        post_id = post["post_id"]
        try:
            html_hash, image_urls = fetch_post_images(post["url"])
            post["image_urls"] = image_urls

            cached = cache_col.document(post_id).get()
            cached_data = cached.to_dict() if cached.exists else {}

            if cached_data.get("html_hash") == html_hash and cached_data.get("plans"):
                # 이벤트 단위 캐시는 parse_images_with_vision()을 거치지 않으므로
                # _strip_device_linked_benefits()를 여기서도 적용해야 과거 캐시된
                # 자급제 연동 혜택이 total_won에 남아있는 문제를 잡을 수 있음.
                post["plans"] = [_strip_device_linked_benefits(p) for p in cached_data["plans"]]
                post["from_cache"] = True
                print(f"[ktm] ⏭️  캐시 재사용: [{post_id}] {post['title'][:25]}")
            else:
                reason = "신규" if not cached_data else "변경감지"
                print(f"[ktm] 🔍 {reason} → Vision 파싱 시작: [{post_id}] {post['title'][:25]} (이미지 {len(image_urls)}장)")
                post["plans"] = parse_images_with_vision(image_urls, db=db) if image_urls else []
                post["from_cache"] = False
                valid = sum(1 for pl in post["plans"] if pl.get("total_won", 0) > 0)
                print(f"[ktm] ✅ 파싱 완료: [{post_id}] 요금제 {len(post['plans'])}건 (유효 {valid}건)")

                cache_col.document(post_id).set({
                    "post_id": post_id,
                    "url": post["url"],
                    "title": post["title"],
                    "date_start": post["date_start"],
                    "date_end": post["date_end"],
                    "html_hash": html_hash,
                    "plans": post["plans"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })

            results.append(post)
        except Exception as e:
            print(f"[ktm] 실패: {post_id} | {e}")

    cached_count = sum(1 for p in results if p.get("from_cache"))
    vision_count = len(results) - cached_count
    print(f"[ktm] 완료: 캐시 {cached_count}건 / Vision {vision_count}건")
    return results


# ──────────────────────────────────────────
# STEP 5: 텔레그램 메시지 포맷 (유모바일과 동일 구조)
# ──────────────────────────────────────────
def _get_band(total_gb) -> str:
    """GB → 구간명"""
    try:
        gb = float(total_gb)
    except (TypeError, ValueError):
        return "100GB 이상"
    for name, lo, hi in DATA_BANDS:
        if lo <= gb <= hi:
            return name
    return "100GB 이상"


def _get_data_key(total_gb) -> str:
    """[추가 20260925] "구간없애고 데이터제공량 별로" 요청 - gift_comparator의
    _data_key()와 동일한 문자열 형식('7gb' 등)으로 반환. [버그수정] 처음엔 (gb, label)
    튜플로 반환했는데, format_moyo_vs_direct가 기대하는 gift_comparator 쪽 키('7gb'
    문자열)와 형식이 달라 교집합 매칭이 항상 빈 결과로 나오던 문제 - 문자열로 통일.
    band_max 반환값은 다른 기능(7일 추이)이 의존하므로 그대로 둠."""
    try:
        gb = float(total_gb)
    except (TypeError, ValueError):
        return "unknown"
    return f"{int(gb) if gb == int(gb) else gb}gb"


def _dk_gb(dk: str) -> float:
    """'7gb' → 7.0, 정렬용. 'unknown'은 맨 뒤로 보냄."""
    try:
        return float(dk.replace("gb", ""))
    except (TypeError, ValueError):
        return float("inf")


def _dk_label(dk: str) -> str:
    """'7gb' → '7GB'."""
    if dk == "unknown":
        return "GB 미상"
    gb = _dk_gb(dk)
    return f"{int(gb)}GB" if gb == int(gb) else f"{gb}GB"


def _price_marker(won: int) -> str:
    """[추가 20260925] 항목 앞 고정 📌 대신 금액대별 색강조 이모지 (사장님 요청:
    "40이상 빨갓 / 30이상 노랑 / 나머지는 빈색")."""
    if won >= 400000:
        return "🔴"
    if won >= 300000:
        return "🟡"
    return "⚪"


def format_telegram_message(posts: list, now_str: str = None) -> tuple:
    """
    KT엠모바일 직영 이벤트 텔레그램 메시지 생성
    구간별 최고 이벤트 표기 + 이벤트별 버튼 생성 (유모바일 format_telegram_message와 동일 구조)

    Returns:
        (text, buttons, band_max)
    """
    if not now_str:
        from pytz import timezone as tz
        kst = tz("Asia/Seoul")
        now_str = datetime.now(kst).strftime("%Y-%m-%d  %H:%M")

    all_plans = []
    for post in posts:
        for plan in post.get("plans", []):
            if plan.get("total_won", 0) > 0:
                plan["_event_url"] = post["url"]
                plan["_event_title"] = post["title"]
                plan["_post_id"] = post["post_id"]
                plan["_date_start"] = post.get("date_start", "")
                plan["_date_end"] = post.get("date_end", "")
                all_plans.append(plan)

    # 과대계산 방지: 단일 플랜 총액 상한 60만원 (Vision 이중파싱 필터, 유모바일과 동일 위치)
    PLAN_VAL_CAP = 600000
    band_max = {}   # 다른 기능이 의존 - 그대로 유지
    band_best = {}
    dk_max  = {}    # [추가 20260925] 표시용, 구간 없이 GB 단위
    dk_best = {}
    for plan in all_plans:
        won = min(plan["total_won"], PLAN_VAL_CAP)
        gb_val = plan.get("base_gb", plan.get("total_gb", 0))
        band = _get_band(gb_val)
        if won > band_max.get(band, 0):
            band_max[band] = won
            band_best[band] = plan
        dk = _get_data_key(gb_val)
        if won > dk_max.get(dk, 0):
            dk_max[dk]  = won
            dk_best[dk] = plan

    def _short_date(d):
        m = re.match(r"\d{4}-(\d{2})-(\d{2})", d or "")
        return f"{int(m.group(1))}/{int(m.group(2))}" if m else d

    def _short_title(t: str) -> str:
        t = re.sub(r"^[✨🎁🏆\s]+", "", t).strip()
        return t[:18] + "…" if len(t) > 18 else t

    lines = [f"🏪 KT엠모바일 직영 이벤트 현황  📅 {now_str}", ""]

    top_won = max(band_max.values(), default=0)
    top_plans = [p for p in band_best.values() if p["total_won"] == top_won]
    if top_plans:
        lines.append(f"🏆 최고혜택: {_short_title(top_plans[0]['_event_title'])}  {top_won//10000}만원")
        lines.append("")

    # [수정 20260925] 구간(DATA_BANDS) 대신 데이터제공량(GB) 그대로 표시
    # GB<=0(파싱 실패로 0 처리된 값) 또는 GB 미상(unknown)은 구간 방식일 땐
    # 다른 구간에 묻혀서 안 보였는데, GB 그대로 쓰니 노이즈 항목으로 튀어나와 제외.
    for dk in sorted(dk_max, key=_dk_gb):
        if dk == "unknown" or _dk_gb(dk) <= 0:
            continue
        won = dk_max.get(dk)
        best = dk_best.get(dk)
        if won and best:
            event_label = _short_title(best["_event_title"])
            lines.append(f"{_price_marker(won)} {_dk_label(dk)}  {won//10000}만원")
            lines.append(f"  ↳ {event_label}")
            lines.append("")

    if not any(band_max.values()):
        lines.append("ℹ️ 현재 수집된 사은품 금액 없음")

    text = "\n".join(lines).strip()

    sorted_plans = sorted(band_best.values(), key=lambda p: -p["total_won"])
    seen_ids = set()
    buttons = []
    for plan in sorted_plans:
        pid = plan["_post_id"]
        if pid not in seen_ids:
            seen_ids.add(pid)
            label = _short_title(plan["_event_title"])
            ds = _short_date(plan["_date_start"])
            de = _short_date(plan["_date_end"])
            date_str = f" ({ds}~{de})" if ds and de else ""
            buttons.append({
                "text": f"🏪 {label}{date_str}",
                "url": plan["_event_url"],
            })

    # [수정 20260925] dk_max(GB 정확 매칭용) 추가 반환 - umobile 스크래퍼와 동일 패턴
    return text, buttons, band_max, dk_max


# ──────────────────────────────────────────
# 단독 실행 (테스트)
# ──────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("\n" + "=" * 60)
    print("STEP 1: 목록 수집")
    print("=" * 60)
    posts = fetch_event_list(gift_only=True)
    for p in posts:
        print(f"  [{p['post_id']}] {p['title']}  |  {p['date_start']} ~ {p['date_end']}")

    if posts:
        print("\n" + "=" * 60)
        print(f"STEP 2: 상세 이미지 확인 ({posts[0]['post_id']})")
        print("=" * 60)
        h, imgs = fetch_post_images(posts[0]["url"])
        print(f"  hash: {h}")
        print(f"  이미지: {len(imgs)}장")
        for img in imgs:
            print(f"    - {img}")

        if os.environ.get("GEMINI_API_KEY"):
            print("\n" + "=" * 60)
            print("STEP 3: Vision 파싱")
            print("=" * 60)
            plans = parse_images_with_vision(imgs)
            posts[0]["plans"] = plans
            print(json.dumps(plans, ensure_ascii=False, indent=2))

            print("\n" + "=" * 60)
            print("STEP 5: 텔레그램 메시지 포맷")
            print("=" * 60)
            text, buttons, band_max, dk_max = format_telegram_message([posts[0]])
            print(text)
            print("\n--- 버튼 ---")
            for b in buttons:
                print(f"  {b}")
        else:
            print("\n[GEMINI_API_KEY 없음] - Vision 파싱은 스킵")