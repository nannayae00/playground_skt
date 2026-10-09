# -*- coding: utf-8 -*-
"""
gift_umobile_event_scraper.py - U+유모바일 이벤트 페이지 수집기

[수정 이력]
- v0.1 (2026-07-09): 최초 작성
  * requests + BeautifulSoup 기반 (SSR 확인)
  * 목록 34건 수집, 사은품성 필터 16건 확인
  * 본문 이미지: /upload/direct/img/evnt/ 경로 + main 컨테이너
- v0.2 (2026-07-09): 배너 이미지 제외 필터 추가
  * 이벤트 목록 배너 이미지 제외 (이벤트목록배너, PC, MO 이벤트 목록배너 패턴)
  * Gemini Vision 파싱 연결 / 한글 URL 인코딩 처리
- v0.3 (2026-07-09): Gemini 패키지 및 모델명 교체
  * google.generativeai(deprecated) → google.genai
  * gemini-2.0-flash(지원종료) → gemini-2.5-flash
- v0.4 (2026-07-09): Vision 프롬프트 개선
  * plan_name → 회색 소분류 텍스트 기준 (굵은 GB숫자 사용 금지)
  * total_gb / base_gb / random_gb / speed_mbps 필드 추가
  * 키비주얼·배너 이미지(혜택조건 박스 없는 것) 빈배열 반환 규칙 추가
- v0.5 (2026-07-09): 날짜·링크·HTML해시 추가 + 변경감지 + 텔레그램 메시지 포맷
  * fetch_event_list: 시작일/종료일 파싱, url 필드 유지
  * fetch_post_html_hash: main 영역 HTML → MD5 (변경감지용)
  * scrape_with_cache: Firestore 캐시 비교 → 변경 시만 Vision 파싱
  * format_telegram_message: 구간별 요약 + 이벤트 링크 버튼용 텍스트
- v0.6 (2026-07-09): 진행상황 로그 강화
  * Vision 파싱 이미지별 N/M 진행 로그
  * 게시글별 캐시재사용/신규/변경감지 이모지 로그
- v0.7 (2026-07-09): 파싱 정확도 개선
  * 상한선 필터 제거 (불필요)
  * 빽다방 쿠폰 1잔=2,000원 계산 규칙 프롬프트 추가
- v0.8 (2026-07-09): 버그 수정
  * 이미지 진행 로그 변수명 충돌 수정 (total → img_total)
  * top_event 선정 로직 수정 (게시글 내 최대 total_won 기준)
"""

import os
import re
import json
import base64
import hashlib
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uplusumobile.com"
LIST_URL = f"{BASE_URL}/event-benefit/event/ongoing"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

EVNT_IMG_PATH = "/upload/direct/img/evnt/"
# [추가 20261010] 2026-10 신규 이벤트 템플릿은 본문 이미지를 /upload/event/images/event{번호}-*.jpg에 올림
# (예: 12567 전설의 요금제) - 기존 경로만 인정해서 이미지 0장 → 요금제 0건으로 누락되던 문제
EVNT_IMG_PATHS = (EVNT_IMG_PATH, "/upload/event/images/")
BANNER_EXCLUDE_PATTERNS = ["이벤트목록배너", "이벤트 목록배너", "PC, MO", "목록배너"]
GIFT_KEYWORDS = [
    "혜택", "사은품", "지급", "Npay", "N페이", "페이백",
    "상품권", "쿠폰", "포인트", "증정",
    "요금제", "야쿠르트", "다이소", "빽다방", "쿠팡", "K-패스",
    "교통비", "올리브영", "GS25", "이마트", "교보문고",
]

# 제목에 포함 시 제외 (요금할인/수수료면제 등 사은품 아닌 것)
EXCLUDE_KEYWORDS = [
    "무료", "eSIM", "추천하고", "알림 신청", "갤럭시", "아이폰", "버디", "휴대폰",
    "라이프케어몰에서", "다운로드비", "증정",
]

# 종료일 기준 최대 파싱 일수 (상시 이벤트 제외)
MAX_EVENT_DAYS = 60

# 구간 정의 (gift_comparator와 동일)
DATA_BANDS = [
    ("5GB 이하",   0,   5),
    ("5~9GB",      5,   9),
    ("10~15GB",   10,  15),
    ("16~49GB",   16,  49),
    ("50~99GB",   50,  99),
    ("100GB 이상",100, 9999),
]

GEMINI_VISION_PROMPT = """당신은 통신사 이벤트 이미지에서 사은품/혜택 정보를 추출하는 분석기입니다.
이미지에서 요금제별 혜택 정보를 추출해 아래 JSON 배열로만 답하세요.
설명, 마크다운, 코드펜스 없이 순수 JSON만 출력하세요.

이미지 구조 (요금제 카드 UI):
  ┌─────────────────────────────────┐
  │ [회색 소문자] LTE (10GB+/통화기본)   ← plan_name (이것만 사용)
  │ [굵은 검정] 20GB+1Mbps             ← total_gb / speed_mbps
  │ [회색 소문자] 기본제공 10GB + 랜덤결합 10GB + 1Mbps  ← base_gb / random_gb
  │
  │ ✓ 요금제 가입 시    이마트24 5천원X24개월  ← benefit
  │ ✓ 이벤트코드 입력시  LG라이프케어몰 3만원X10개월  ← benefit
  └─────────────────────────────────┘

스키마:
[
  {
    "plan_name": "LTE (10GB+/통화기본)",
    "total_gb": 20,
    "base_gb": 10,
    "random_gb": 10,
    "speed_mbps": 1,
    "benefits": [
      {
        "name": "혜택명 (예: 이마트24 편의점)",
        "condition": "조건 (예: 요금제 가입 시 / 이벤트코드 입력 시)",
        "amount_won": 1회 금액(원, 숫자),
        "months": 개월수(1회성=1),
        "total_won": amount_won * months
      }
    ],
    "total_won": benefits total_won 합계
  }
]

규칙:
1. plan_name은 반드시 회색 소문자 소분류 텍스트 사용 (예: "LTE 스페셜", "데이터플러스 (7GB+/통화기본)")
   굵은 GB 숫자(예: "91GB+3Mbps")를 plan_name으로 쓰지 말 것
2. total_gb = 굵은 숫자의 GB / base_gb = 기본제공 GB / random_gb = 랜덤결합 GB (없으면 0)
3. "N천원X M개월" → amount_won=N*1000, months=M, total_won=amount_won*months
   "매달"/"매월" + 금액 → months만큼 반복 지급
4. "N천원"=N*1000, "N만원"=N*10000
5. 금액 없는 혜택(추첨 등)은 amount_won=0
6. 혜택 조건 박스(✓ 가입 시 / ✓ 이벤트코드)가 없는 키비주얼·배너·안내 이미지는 빈 배열 [] 출력
7. 빽다방 쿠폰은 1잔 = 2,000원으로 계산
   예: "빽다방 4잔 X 25개월" → amount_won=8000(4×2000), months=25, total_won=200000
8. "대상 단말 자급제 등록 혜택"처럼 특정 자급제 단말 구매·등록이 조건인 혜택은
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
    프롬프트 준수는 비결정적이라, 신규 파싱 병합 시점에서 다시 한번 필터링.
    """
    benefits = plan.get('benefits') or []
    kept = [b for b in benefits
            if not any(kw in f"{b.get('name', '')} {b.get('condition', '')}"
                       for kw in _DEVICE_LINKED_KEYWORDS)]
    if len(kept) == len(benefits):
        return plan
    plan = dict(plan)
    plan['benefits']  = kept
    plan['total_won'] = sum(int(b.get('total_won') or 0) for b in kept)
    return plan


# ──────────────────────────────────────────
# STEP 1: 목록 수집 (날짜 포함)
# ──────────────────────────────────────────
def fetch_event_list(gift_only: bool = True) -> list:
    """
    진행중 이벤트 목록 수집
    Returns: [{post_id, url, title, date_start, date_end}]
    """
    r = requests.get(LIST_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    seen = set()
    posts = []
    for a in soup.find_all("a", href=re.compile(r"/event-benefit/event/ongoing/\d+")):
        href = a["href"]
        post_id = re.search(r"/(\d+)$", href).group(1)
        if post_id in seen:
            continue
        seen.add(post_id)

        raw_text = a.get_text(separator=" ", strip=True)

        # 날짜 추출: "2026-07-01~2026-07-10" 또는 "2026-07-01 ~ 2026-07-10"
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", raw_text)
        date_start = date_match.group(1) if date_match else ""
        date_end   = date_match.group(2) if date_match else ""

        # 제목: 날짜 이전까지
        title = re.sub(r"\d{4}-\d{2}-\d{2}.*", "", raw_text).strip()

        posts.append({
            "post_id":    post_id,
            "url":        urljoin(BASE_URL, href),
            "title":      title,
            "date_start": date_start,
            "date_end":   date_end,
        })

    print(f"[umobile] 목록 수집: {len(posts)}건")

    if gift_only:
        from datetime import date
        today = date.today()

        filtered = []
        for p in posts:
            title = p["title"]

            # 1) GIFT_KEYWORDS 포함 여부
            if not any(k in title for k in GIFT_KEYWORDS):
                print(f"[umobile] 키워드 미해당 스킵: {title[:30]}")
                continue

            # 2) EXCLUDE_KEYWORDS 제외
            if any(k in title for k in EXCLUDE_KEYWORDS):
                print(f"[umobile] 제외 키워드 스킵: {title[:30]}")
                continue

            # 3) 종료일 60일 이내 필터
            date_end = p.get("date_end", "")
            if date_end:
                try:
                    end = date.fromisoformat(date_end)
                    days_left = (end - today).days
                    if days_left > MAX_EVENT_DAYS:
                        print(f"[umobile] 장기 이벤트 스킵 (D+{days_left}): {title[:30]}")
                        continue
                except ValueError:
                    pass
            else:
                # 종료일 없음 (응모 마감까지) → 상시 이벤트로 포함
                pass

            filtered.append(p)

        posts = filtered
        print(f"[umobile] 필터 후: {len(posts)}건")

    return posts


# ──────────────────────────────────────────
# STEP 2: HTML 해시 (변경감지)
# ──────────────────────────────────────────
def fetch_post_html_hash(post_url: str) -> tuple:
    """
    게시글 main 영역 HTML → (html_hash, image_urls)
    변경감지: 저장된 hash와 비교 후 다르면 Vision 재파싱
    """
    r = requests.get(post_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    main = soup.find("main") or soup
    main_html = str(main)
    html_hash = hashlib.md5(main_html.encode("utf-8")).hexdigest()

    # 이미지 URL도 같이 추출
    image_urls = []
    seen = set()
    for img in main.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or not any(p in src for p in EVNT_IMG_PATHS):
            continue
        if any(pat in src for pat in BANNER_EXCLUDE_PATTERNS):
            continue
        full = urljoin(BASE_URL, src)
        if full not in seen:
            seen.add(full)
            image_urls.append(full)

    return html_hash, image_urls


# ──────────────────────────────────────────
# STEP 3: Gemini Vision 파싱
# ──────────────────────────────────────────
def _download_image_b64(url: str):
    encoded_url = quote(url, safe=":/?=&%+#")
    r = requests.get(encoded_url, headers={
        "User-Agent": HEADERS["User-Agent"],
        "Referer": BASE_URL,
    }, timeout=20)
    r.raise_for_status()
    mime = r.headers.get("Content-Type", "image/png").split(";")[0]
    if not mime.startswith("image/"):
        mime = "image/png"
    return base64.standard_b64encode(r.content).decode("utf-8"), mime


# 직전 parse_images_with_vision() 호출의 이미지 다운로드/파싱 실패 수 (0이면 전부 정상 처리)
LAST_VISION_FAILURES = 0


def parse_images_with_vision(image_urls: list) -> list:
    """이미지 URL → Gemini Vision → [{plan_name, total_gb, base_gb, ...}]"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 없음")
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")

    global LAST_VISION_FAILURES
    LAST_VISION_FAILURES = 0
    merged = {}
    img_total = len(image_urls)
    for idx, url in enumerate(image_urls, 1):
        fname = url.split("/")[-1]
        print(f"[vision] 이미지 {idx}/{img_total}: {fname}")
        try:
            b64, mime = _download_image_b64(url)
        except Exception as e:
            print(f"[vision] 다운로드 실패: {fname} | {e}")
            LAST_VISION_FAILURES += 1
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
            hit = len([p for p in plans if isinstance(plans, list) and p.get("total_won", 0) > 0])
            print(f"[vision] {fname} → {len(plans) if isinstance(plans, list) else 0}건 파싱 (유효 {hit}건)")
        except Exception as e:
            print(f"[vision] 파싱 실패: {fname} | {e}")
            LAST_VISION_FAILURES += 1
            continue

        for plan in (plans if isinstance(plans, list) else []):
            name = str(plan.get("plan_name", "")).strip()
            if not name:
                continue
            total = int(plan.get("total_won") or 0)
            if name not in merged or total > merged[name].get("total_won", 0):
                merged[name] = plan

    results = list(merged.values())
    print(f"[vision] 요금제 {len(results)}건 파싱 완료")
    return results


# ──────────────────────────────────────────
# STEP 4: Firestore 캐시 기반 수집
# ──────────────────────────────────────────
def scrape_with_cache(db, max_posts: int = 16, gift_only: bool = True) -> list:
    """
    변경감지 기반 수집
    - HTML 해시 동일 → Firestore 캐시 재사용 (Vision 호출 없음)
    - 해시 변경 or 신규 → Vision 파싱 후 Firestore 저장
    Returns: [{post_id, url, title, date_start, date_end, plans, from_cache}]
    """
    posts = fetch_event_list(gift_only=gift_only)
    results = []
    cache_col = db.collection("umobile_event_cache")

    for post in posts[:max_posts]:
        post_id = post["post_id"]
        try:
            html_hash, image_urls = fetch_post_html_hash(post["url"])
            post["image_urls"] = image_urls

            # Firestore 캐시 조회
            cached = cache_col.document(post_id).get()
            cached_data = cached.to_dict() if cached.exists else {}

            # [수정 20261010] 요금제 0건이어도 파싱이 오류 없이 끝난 게시글(parse_ok)은 재사용 -
            # 기존엔 plans가 비면 매 실행마다 "변경감지"로 재파싱했음
            if cached_data.get("html_hash") == html_hash and (cached_data.get("plans") or cached_data.get("parse_ok")):
                # 변경 없음 → 캐시 재사용
                # (이벤트 단위 캐시는 parse_images_with_vision()을 거치지 않으므로
                #  _strip_device_linked_benefits()를 여기서도 적용)
                post["plans"] = [_strip_device_linked_benefits(p) for p in cached_data["plans"]]
                post["from_cache"] = True
                print(f"[umobile] ⏭️  캐시 재사용: [{post_id}] {post['title'][:25]}")
            else:
                # 신규 or 변경 → Vision 파싱
                reason = "신규" if not cached_data else "변경감지"
                print(f"[umobile] 🔍 {reason} → Vision 파싱 시작: [{post_id}] {post['title'][:25]} (이미지 {len(image_urls)}장)")
                post["plans"] = parse_images_with_vision(image_urls) if image_urls else []
                parse_ok = bool(image_urls) and LAST_VISION_FAILURES == 0
                post["from_cache"] = False
                valid = sum(1 for p in post["plans"] if p.get("total_won", 0) > 0)
                print(f"[umobile] ✅ 파싱 완료: [{post_id}] 요금제 {len(post['plans'])}건 (유효 {valid}건)")

                # Firestore 저장
                cache_col.document(post_id).set({
                    "post_id":    post_id,
                    "url":        post["url"],
                    "title":      post["title"],
                    "date_start": post["date_start"],
                    "date_end":   post["date_end"],
                    "html_hash":  html_hash,
                    "plans":      post["plans"],
                    "parse_ok":   parse_ok,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })

            results.append(post)
        except Exception as e:
            print(f"[umobile] 실패: {post_id} | {e}")

    cached_count = sum(1 for p in results if p.get("from_cache"))
    vision_count = len(results) - cached_count
    print(f"[umobile] 완료: 캐시 {cached_count}건 / Vision {vision_count}건")
    return results


# ──────────────────────────────────────────
# STEP 5: 텔레그램 메시지 포맷
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
    유모바일 직영 이벤트 텔레그램 메시지 생성
    구간별 최고 이벤트 표기 + 이벤트별 버튼 생성

    Returns:
        (text, buttons, band_max)
        buttons: [{"text": "...", "url": "..."}]  → InlineKeyboard URL 버튼용
    """
    if not now_str:
        from pytz import timezone as tz
        kst = tz("Asia/Seoul")
        now_str = datetime.now(kst).strftime("%Y-%m-%d  %H:%M")

    # 유효 플랜 수집 + 이벤트 정보 태깅
    all_plans = []
    for post in posts:
        for plan in post.get("plans", []):
            if plan.get("total_won", 0) > 0:
                plan["_event_url"]   = post["url"]
                plan["_event_title"] = post["title"]
                plan["_post_id"]     = post["post_id"]
                plan["_date_start"]  = post.get("date_start", "")
                plan["_date_end"]    = post.get("date_end", "")
                all_plans.append(plan)

    # 구간별 최고 플랜 (금액 + 이벤트 정보)
    # 과대계산 방지: 단일 플랜 총액 상한 60만원 (Vision 이중파싱 필터)
    PLAN_VAL_CAP = 600000
    band_max  = {}   # band → max_won (다른 기능이 의존 - 그대로 유지)
    band_best = {}   # band → best plan dict
    dk_max    = {}   # (gb, label) → max_won - [추가 20260925] 표시용, 구간 없이 GB 단위
    dk_best   = {}   # (gb, label) → best plan dict
    for plan in all_plans:
        won  = min(plan["total_won"], PLAN_VAL_CAP)
        gb_val = plan.get("base_gb", plan.get("total_gb", 0))
        band = _get_band(gb_val)
        if won > band_max.get(band, 0):
            band_max[band]  = won
            band_best[band] = plan
        dk = _get_data_key(gb_val)
        if won > dk_max.get(dk, 0):
            dk_max[dk]  = won
            dk_best[dk] = plan

    def _short_date(d):
        m = re.match(r"\d{4}-(\d{2})-(\d{2})", d or "")
        return f"{int(m.group(1))}/{int(m.group(2))}" if m else d

    def _short_title(t: str) -> str:
        """이벤트 제목 축약 (20자 이내)"""
        t = re.sub(r"^[✨🎁🏆\s]+", "", t).strip()
        return t[:18] + "…" if len(t) > 18 else t

    # 메시지 본문
    lines = [f"🌐 U+유모바일 직영 이벤트 현황  📅 {now_str}", ""]

    top_won   = max(band_max.values(), default=0)
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
        won  = dk_max.get(dk)
        best = dk_best.get(dk)
        if won and best:
            event_label = _short_title(best["_event_title"])
            lines.append(f"{_price_marker(won)} {_dk_label(dk)}  {won//10000}만원")
            lines.append(f"  ↳ {event_label}")
            lines.append("")

    if not any(band_max.values()):
        lines.append("ℹ️ 현재 수집된 사은품 금액 없음")

    text = "\n".join(lines).strip()

    # 버튼: 구간별 최고 이벤트 중 중복 제거 → 이벤트별 버튼
    seen_ids = set()
    buttons  = []
    for _, _, _ in DATA_BANDS:
        pass  # 아래에서 band_best 순서대로 처리

    # 금액 높은 순으로 유니크 이벤트 버튼
    sorted_plans = sorted(band_best.values(), key=lambda p: -p["total_won"])
    for plan in sorted_plans:
        pid = plan["_post_id"]
        if pid not in seen_ids:
            seen_ids.add(pid)
            label = _short_title(plan["_event_title"])
            ds = _short_date(plan["_date_start"])
            de = _short_date(plan["_date_end"])
            date_str = f" ({ds}~{de})" if ds and de else ""
            buttons.append({
                "text": f"🌐 {label}{date_str}",
                "url":  plan["_event_url"],
            })

    # [수정 20260925] dk_max(GB 정확 매칭용, "서로 비교값 있는 것만" 요청 반영해
    # format_moyo_vs_direct/K CUP 특이사항에서 씀) 추가 반환. band_max는 7일 추이
    # 기능이 그대로 의존하므로 기존 위치·순서 유지.
    return text, buttons, band_max, dk_max


# ──────────────────────────────────────────
# 단독 실행 (테스트)
# ──────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("\n" + "="*60)
    print("STEP 1: 목록 수집 (날짜 포함)")
    print("="*60)
    posts = fetch_event_list(gift_only=True)
    for p in posts:
        print(f"  [{p['post_id']}] {p['title']}  |  {p['date_start']} ~ {p['date_end']}")

    print("\n" + "="*60)
    print("STEP 2: HTML 해시 확인 (10314)")
    print("="*60)
    target = next((p for p in posts if p["post_id"] == "10314"), posts[0])
    h, imgs = fetch_post_html_hash(target["url"])
    print(f"  hash: {h}")
    print(f"  이미지: {len(imgs)}장")

    if os.environ.get("GEMINI_API_KEY"):
        print("\n" + "="*60)
        print("STEP 3: Vision 파싱 (10314)")
        print("="*60)
        plans = parse_images_with_vision(imgs)
        target["plans"] = plans
        target["date_start"] = target.get("date_start", "")
        target["date_end"]   = target.get("date_end", "")
        text, buttons, band_max, dk_max = format_telegram_message([target])
        print("\n--- 텔레그램 메시지 ---")
        print(text)
        print("\n--- 버튼 ---")
        for b in buttons:
            print(f"  {b}")
        print("\n--- 구간별 최대 ---")
        print(json.dumps(band_max, ensure_ascii=False, indent=2))
    else:
        print("\n[GEMINI_API_KEY 없음]")
        print("export $(grep -v '^#' .env | xargs)")