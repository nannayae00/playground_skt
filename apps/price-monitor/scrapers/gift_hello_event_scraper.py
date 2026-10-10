"""
gift_hello_event_scraper.py  v0.1
LG헬로모바일 직영몰 알뜰요금제 이벤트 수집 (모요 vs 헬로직영 비교용)

[v0.1 / 2026-10-10] 신규
- 목록: https://direct.lghellovision.net/m/event/viewEventList.do
  이벤트 목록과 상세 본문 모두 자바스크립트(ajax)로 그려지고, 목록 API는 세션 없이
  호출하면 빈 결과라 Playwright로 렌더링해서 수집. 카테고리가 "알뜰요금제"인 이벤트만 대상.
- 상세: viewEventDetailGuest.do?idxOfEvent=N → 본문 이미지(directcdn .../upload/atcfile/board/*)
  세로로 매우 긴 이미지(최대 1만px+)가 많아 겹치게 잘라서(2,400px, 300px 겹침) Gemini에 전달.
- 혜택이 요금제 카드마다 "친구추천 13.6만 / 코드입력 12만 / 자급제 10만 / 기본 10만 / 쿠폰팩 12만"
  처럼 나열되는 구조라, 항목마다 category를 붙여 저장하고 비교값은 category로 고름.
  · 비교값 포함 (DIRECT_CATEGORIES): 기본 혜택, 프로모션 코드(누구나 입력 가능),
    요금제 자체 혜택(쿠폰팩·Npay 요금제·제휴 요금제 등)
  · 제외: 친구추천 링크 가입, 단말(자급제) 구매, 결합, 기타 대상 제한 혜택 - 메시지에만 표시
- 요금제 카드 밖에 "15,900원 이상 요금제 가입 시 코드 입력 12만원"처럼 공통으로 안내된 혜택은
  common으로 받아, 월 요금 조건이 맞고 같은 category가 카드에 없을 때만 더함.
- 캐시: 이벤트별(hello_event_cache/{idx}) 이미지 주소 목록 해시가 같으면 Vision 재파싱 없음.
"""
import os
import re
import io
import json
import hashlib
import html
import requests
from datetime import date, datetime, timezone

BASE_URL = "https://direct.lghellovision.net"
LIST_URL = f"{BASE_URL}/m/event/viewEventList.do?returnTab=allli"
DETAIL_URL = f"{BASE_URL}/m/event/viewEventDetailGuest.do?idxOfEvent={{idx}}"
CACHE_COLLECTION = "hello_event_cache"
PARSE_VERSION = "2"   # 파싱 규칙이 바뀌면 올려서 캐시 무효화

MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"}

TARGET_CATEGORY = "알뜰요금제"
MIN_IMG_WIDTH = 600
MIN_IMG_HEIGHT = 400      # 하단 공통 배너(340~374px) 등 혜택 없는 띠 이미지 제외
CHUNK_H, CHUNK_OVERLAP = 2400, 300
MAX_CHUNKS_PER_EVENT = 40

CATEGORIES = ("기본", "코드", "요금제", "친구추천", "단말", "결합", "기타")
DIRECT_CATEGORIES = ("기본", "코드", "요금제")
# 제휴 서비스 이용권(전자책·구독 등)은 현금성이 아니라 비교값에서 제외 (스카이라이프 규칙과 동일)
SERVICE_KEYWORDS = ("교보", "sam", "구독", "이용권", "멤버십")
CATEGORY_LABEL = {"기본": "기본혜택", "코드": "프로모션코드", "요금제": "요금제혜택",
                  "친구추천": "친구추천", "단말": "자급제/단말", "결합": "결합", "기타": "기타"}

_RE_LIST_ANCHOR = re.compile(r"fncEventDetail\(this,\s*(\d+)")
_RE_PERIOD = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})")

GEMINI_PROMPT = """당신은 LG헬로모바일(알뜰폰) 이벤트 안내 이미지에서 요금제별 금전성 혜택을 추출하는 분석기입니다.
이미지는 긴 페이지를 잘라낸 일부일 수 있습니다. 순수 JSON만 출력합니다.

스키마:
{
  "plans": [
    {"plan_name": "요금제명 (예: DATA 걱정없는 유심 7GB)",
     "base_gb": 월 기본 데이터(GB, 숫자. "11+20GB+일2GB"면 11, "95GB+10GB"면 95, 없으면 0),
     "monthly_fee": 월 기본요금(원, 정수. 할인 전 정가),
     "benefits": [{"name": "혜택명", "category": "분류", "amount_won": 1회 금액, "months": 개월수, "total_won": 총액}]}
  ],
  "common": [
    {"name": "혜택명", "category": "분류", "min_fee": 대상 월 요금 하한(원, 없으면 0),
     "amount_won": 1회 금액, "months": 개월수, "total_won": 총액}
  ]
}

category 분류 (반드시 아래 중 하나):
- "기본": 무조건/기본으로 받는 가입 혜택
- "코드": 프로모션 코드 입력 시 혜택
- "요금제": 쿠폰팩 요금제, Npay 혜택형 요금제, 제휴 요금제처럼 그 요금제에 가입하면 매월 주는 혜택
- "친구추천": 친구추천 링크 가입 혜택
- "단말": 갤럭시/아이폰 자급제·휴대폰 구매 조건 혜택
- "결합": 결합 시 혜택
- "기타": 그 외 대상·조건이 제한된 혜택

규칙:
1. 숫자는 쉼표 없이 정수. "N천원"=N*1000, "N만원"=N*10000, "1.5만원"=15000
2. "1.5만원 x 8개월"이면 amount_won=15000, months=8, total_won=120000. 1회성은 months=1
3. plans: 요금제 카드(요금제명/데이터/월 요금이 함께 보이는 박스)마다 1개. 카드 안에 혜택 목록이
   있으면 benefits에 넣고, "매월 Npay 15,000원"처럼 카드에 붙은 매월 혜택은 category "요금제", months는 안내된 개월수(없으면 24)
4. common: 카드 밖에서 안내된 "프로모션 코드 입력 시" 혜택만 넣는다 (예: "15,900원 이상 요금제 가입 시 코드 입력 12만원").
   그 외 카드 밖 안내(매월 N만원 x N개월 요약, 쿠폰팩/친구추천/자급제 안내 등)는 common에 넣지 않는다
5. 지급되는 혜택(Npay·상품권·포인트·캐시·쿠폰)만 넣는다. 요금 할인, 데이터 추가, 월별 지급 일정표는 넣지 않는다
6. 여러 혜택을 합친 금액(예: "총 혜택 47.6만원", "최대 57.6만원", "헬로모바일 혜택 25.6만원"처럼 구성 항목의 합계)은 넣지 않는다.
   구성 항목이 보이면 항목별로 넣고, 안 보이면 넣지 않는다
7. 요금제명/월 요금만 나열되고 혜택이 적혀 있지 않은 요금제 목록은 benefits를 빈 배열로 둔다
8. 해당 내용이 없으면 {"plans": [], "common": []}
"""


# ──────────────────────────────────────────
# 브라우저
# ──────────────────────────────────────────
def _launch(p):
    kwargs = {"headless": True}
    if os.environ.get("PW_CHROMIUM_PATH"):          # 로컬 테스트용 (Cloud Run 이미지는 기본 경로)
        kwargs["executable_path"] = os.environ["PW_CHROMIUM_PATH"]
    if os.environ.get("PW_PROXY"):
        kwargs["proxy"] = {"server": os.environ["PW_PROXY"]}
    return p.chromium.launch(**kwargs)


def _new_page(browser):
    return browser.new_page(user_agent=MOBILE_UA, viewport={"width": 412, "height": 900})


def _scroll(page, n=5):
    for _ in range(n):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(600)


def fetch_event_list(browser) -> list:
    """진행중 이벤트 목록 → [{idx, title, category, date_start, date_end, url}] (알뜰요금제만)"""
    page = _new_page(browser)
    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
    _scroll(page, 4)
    anchors = page.eval_on_selector_all(
        "a[onclick*='fncEventDetail']",
        "els=>els.map(e=>[e.getAttribute('onclick')||'', (e.innerText||'').replace(/\\s+/g,' ').trim()])")
    page.close()

    events, seen = [], set()
    for onclick, text in anchors:
        m = _RE_LIST_ANCHOR.search(onclick)
        if not m or m.group(1) in seen:
            continue
        idx = m.group(1)
        seen.add(idx)
        pm = _RE_PERIOD.search(text)
        head = text[:pm.start()].strip() if pm else text
        category = head.rsplit(" ", 1)[-1] if " " in head else ""
        title = head[: -len(category)].strip() if category else head
        events.append({
            "idx": idx, "title": title, "category": category,
            "date_start": f"{pm.group(1)}-{pm.group(2)}-{pm.group(3)}" if pm else "",
            "date_end": f"{pm.group(4)}-{pm.group(5)}-{pm.group(6)}" if pm else "",
            "url": DETAIL_URL.format(idx=idx),
        })
    print(f"[hello] 목록 수집: {len(events)}건")

    today = date.today().isoformat()
    out = []
    for ev in events:
        if ev["category"] != TARGET_CATEGORY:
            print(f"[hello] 대상 아님({ev['category'] or '?'}) 스킵: {ev['title'][:30]}")
            continue
        if ev["date_end"] and ev["date_end"] < today:
            continue
        out.append(ev)
    print(f"[hello] 필터 후: {len(out)}건")
    return out


def fetch_event_images(browser, url: str) -> list:
    """상세 페이지 → 본문 혜택 이미지 URL 목록 (표시 순서)"""
    page = _new_page(browser)
    page.goto(url, wait_until="networkidle", timeout=60000)
    _scroll(page, 5)
    imgs = page.eval_on_selector_all(
        "img", "els=>els.map(e=>[e.currentSrc||e.src, e.naturalWidth, e.naturalHeight])")
    page.close()
    urls = []
    for src, w, h in imgs:
        if ("/upload/atcfile/board/" not in src or "event_pop" in src
                or w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT or src in urls):
            continue
        urls.append(src)
    return urls


# ──────────────────────────────────────────
# Gemini Vision
# ──────────────────────────────────────────
def _image_chunks(content: bytes) -> list:
    """긴 이미지를 겹치게 잘라 JPEG bytes 목록으로 (Pillow 없으면 원본 1장)"""
    try:
        from PIL import Image
    except ImportError:
        return [(content, "image/png")]
    im = Image.open(io.BytesIO(content)).convert("RGB")
    w, h = im.size
    if h <= CHUNK_H:
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        return [(buf.getvalue(), "image/jpeg")]
    out, top = [], 0
    while top < h:
        buf = io.BytesIO()
        im.crop((0, top, w, min(h, top + CHUNK_H))).save(buf, "JPEG", quality=85)
        out.append((buf.getvalue(), "image/jpeg"))
        if top + CHUNK_H >= h:
            break
        top += CHUNK_H - CHUNK_OVERLAP
    return out


def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _norm_benefit(b: dict) -> dict:
    amount = _to_int(b.get("amount_won"))
    months = max(_to_int(b.get("months")) or 1, 1)
    total = amount * months if amount else _to_int(b.get("total_won"))
    cat = b.get("category") if b.get("category") in CATEGORIES else "기타"
    return {"name": str(b.get("name", "")).strip(), "category": cat,
            "amount_won": amount or total, "months": months if amount else 1, "total_won": total}


def parse_event_images(image_urls: list) -> tuple:
    """이미지들 → (plans, common, failures)"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 없음")
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")

    raw_plans, raw_common, failures, calls = [], [], 0, 0
    for url in image_urls:
        fname = url.rsplit("/", 1)[-1]
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            chunks = _image_chunks(r.content)
        except Exception as e:
            print(f"[hello] 이미지 다운로드 실패: {fname} | {e}")
            failures += 1
            continue
        for ci, (data, mime) in enumerate(chunks):
            if calls >= MAX_CHUNKS_PER_EVENT:
                break
            calls += 1
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_bytes(data=data, mime_type=mime), GEMINI_PROMPT],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                obj = json.loads((resp.text or "{}").strip())
            except Exception as e:
                print(f"[hello] Vision 실패: {fname}#{ci} | {e}")
                failures += 1
                continue
            if isinstance(obj, list):
                obj = {"plans": obj}
            ps = [p for p in (obj.get("plans") or []) if isinstance(p, dict)]
            cs = [c for c in (obj.get("common") or []) if isinstance(c, dict)]
            raw_plans += ps
            raw_common += cs
            print(f"[vision] {fname}#{ci} → 요금제 {len(ps)} / 공통 {len(cs)}")

    # 같은 요금제(데이터, 월 요금)가 여러 이미지에 반복 안내되면 1건으로 합치고, category별 최대값 1건만 유지
    merged = {}
    for p in raw_plans:
        gb = float(p.get("base_gb") or 0)
        fee = _to_int(p.get("monthly_fee"))
        if not gb or not fee:
            continue
        key = (gb, fee)
        slot = merged.setdefault(key, {"plan_name": str(p.get("plan_name", "")).strip(),
                                       "base_gb": gb, "monthly_fee": fee, "benefits": {}})
        for b in (p.get("benefits") or []):
            if not isinstance(b, dict):
                continue
            nb = _norm_benefit(b)
            if nb["total_won"] <= 0 or "할인" in nb["name"]:
                continue
            cur = slot["benefits"].get(nb["category"])
            if not cur or nb["total_won"] > cur["total_won"]:
                slot["benefits"][nb["category"]] = nb
    plans = []
    for slot in merged.values():
        bens = list(slot["benefits"].values())
        # 합계 문구가 '기본'으로 잡힌 경우(다른 항목 합과 같으면) 제외
        others = sum(b["total_won"] for b in bens if b["category"] != "기본")
        bens = [b for b in bens if not (b["category"] == "기본" and others and b["total_won"] == others)]
        if not bens:
            continue    # 혜택이 적히지 않은 요금제 목록(더 많은 요금제 보기 등)은 비교 대상 아님
        slot["benefits"] = sorted(bens, key=lambda b: CATEGORIES.index(b["category"]))
        plans.append(slot)
    plans.sort(key=lambda p: (p["base_gb"], p["monthly_fee"]))

    common, seen = [], set()
    for c in raw_common:
        nb = _norm_benefit(c)
        nb["min_fee"] = _to_int(c.get("min_fee"))
        # 공통 혜택은 프로모션 코드만 인정 (요약 문구·쿠폰팩·교체지원금 등이 전 요금제에 붙는 것 방지)
        if nb["total_won"] <= 0 or nb["category"] != "코드" or "코드" not in nb["name"] or "할인" in nb["name"]:
            continue
        key = (nb["category"], nb["min_fee"], nb["total_won"])
        if key not in seen:
            seen.add(key)
            common.append(nb)
    return plans, common, failures


# ──────────────────────────────────────────
# 비교값
# ──────────────────────────────────────────
def _is_service(b: dict) -> bool:
    name = b.get("name", "").lower()
    return any(k.lower() in name for k in SERVICE_KEYWORDS)


def direct_benefits(plan: dict, common: list) -> list:
    """비교값에 넣는 혜택 = 카드의 기본/코드/요금제 혜택 + 카드에 없는 category의 공통 혜택(월 요금 조건 충족 시).
    카드 자체에 비교 대상 혜택이 없으면(제휴 이용권만 있는 요금제 등) 빈 리스트 - 공통 코드만으로는 비교하지 않음."""
    own = [b for b in plan.get("benefits", []) if b["category"] in DIRECT_CATEGORIES and not _is_service(b)]
    if not own:
        return []
    have = {b["category"] for b in own}
    fee = plan.get("monthly_fee") or 0
    extra = {}
    for c in common or []:
        if c["category"] in DIRECT_CATEGORIES and c["category"] not in have and fee >= (c.get("min_fee") or 0):
            if c["total_won"] > extra.get(c["category"], {}).get("total_won", 0):
                extra[c["category"]] = c
    return own + list(extra.values())


def excluded_benefits(plan: dict) -> list:
    return [b for b in plan.get("benefits", []) if b["category"] not in DIRECT_CATEGORIES or _is_service(b)]


def _attach_values(post: dict) -> None:
    for p in post.get("plans", []):
        bens = direct_benefits(p, post.get("common", []))
        p["direct_benefits"] = bens
        p["total_won"] = sum(b["total_won"] for b in bens)


# ──────────────────────────────────────────
# 수집 (캐시)
# ──────────────────────────────────────────
def scrape_with_cache(db) -> list:
    """→ [{idx, title, url, date_start, date_end, plans, common, from_cache}]"""
    from playwright.sync_api import sync_playwright

    posts = []
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            events = fetch_event_list(browser)
            for ev in events:
                try:
                    urls = fetch_event_images(browser, ev["url"])
                except Exception as e:
                    print(f"[hello] 상세 수집 실패 [{ev['idx']}]: {e}")
                    continue
                img_hash = hashlib.md5(("|".join(urls) + "|v" + PARSE_VERSION).encode("utf-8")).hexdigest()
                ref = db.collection(CACHE_COLLECTION).document(ev["idx"])
                snap = ref.get()
                cached = snap.to_dict() if snap.exists else {}
                post = dict(ev)
                if cached.get("img_hash") == img_hash and cached.get("parse_ok"):
                    post.update(plans=cached.get("plans", []), common=cached.get("common", []), from_cache=True)
                    print(f"[hello] ⏭️  캐시 재사용: [{ev['idx']}] {ev['title'][:30]}")
                else:
                    print(f"[hello] 🔍 {'신규' if not cached else '변경감지'} → Vision: [{ev['idx']}] {ev['title'][:30]} (이미지 {len(urls)}장)")
                    plans, common, failures = parse_event_images(urls) if urls else ([], [], 0)
                    post.update(plans=plans, common=common, from_cache=False)
                    ref.set({
                        "title": ev["title"], "url": ev["url"],
                        "date_start": ev["date_start"], "date_end": ev["date_end"],
                        "img_hash": img_hash, "image_urls": urls,
                        "plans": plans, "common": common,
                        "parse_ok": bool(urls) and failures == 0,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
                    print(f"[hello] ✅ 파싱 완료: [{ev['idx']}] 요금제 {len(plans)}건 / 공통 {len(common)}건 (실패 {failures})")
                _attach_values(post)
                posts.append(post)
        finally:
            browser.close()
    print(f"[hello] 완료: {len(posts)}건 (캐시 {sum(1 for x in posts if x.get('from_cache'))})")
    return posts


# ──────────────────────────────────────────
# 비교 / 메시지
# ──────────────────────────────────────────
def _plan_dk(plan: dict) -> str:
    gb = float(plan.get("base_gb") or 0)
    return f"{int(gb) if gb == int(gb) else gb}gb" if gb else ""


def compute_direct_dk_max(posts: list) -> dict:
    """{data_key: 직영 비교값 최대}"""
    dk_max = {}
    for post in posts:
        for p in post.get("plans", []):
            dk = _plan_dk(p)
            if dk and p.get("total_won", 0) > dk_max.get(dk, 0):
                dk_max[dk] = p["total_won"]
    return dk_max


def build_kcup_direct_posts(posts: list) -> list:
    """build_kcup_records()용 - 요금제명 앞에 기본 GB를 붙여 GB 매칭이 어긋나지 않게 함
    (예: '11+20GB+일2GB' 카드는 요금제명만으로는 20GB로 읽힐 수 있음)."""
    out = []
    for post in posts:
        plans = []
        for p in post.get("plans", []):
            if not p.get("total_won"):
                continue
            gb = p["base_gb"]
            gb_s = str(int(gb)) if gb == int(gb) else str(gb)
            plans.append({
                "plan_name": f"{gb_s}GB {p.get('plan_name', '')} (월 {p['monthly_fee']:,}원)",
                "base_gb": gb,
                "total_won": p["total_won"],
                "benefits": p.get("direct_benefits", []),
            })
        out.append({"title": post.get("title", ""), "url": post.get("url", ""),
                    "date_start": post.get("date_start", ""), "date_end": post.get("date_end", ""),
                    "plans": plans})
    return out


def _won(v: int) -> str:
    if v % 10000 == 0:
        return f"{v // 10000}만"
    if v % 1000 == 0:
        return f"{v / 10000:g}만"
    return f"{v:,}원"


def _short_date(d: str) -> str:
    m = re.match(r"\d{4}-(\d{2})-(\d{2})", d or "")
    return f"{int(m.group(1))}/{int(m.group(2))}" if m else ""


def format_telegram_message(posts: list, now_str: str = None) -> tuple:
    """→ (text, buttons)"""
    now_str = now_str or datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📺 LG헬로모바일 직영 이벤트  📅 {now_str}", ""]
    buttons = []
    any_plan = False
    for post in posts:
        plans = [p for p in post.get("plans", []) if p.get("total_won") or excluded_benefits(p)]
        period = f"{_short_date(post.get('date_start'))}~{_short_date(post.get('date_end'))}"
        lines.append(f"■ {html.escape(post.get('title', '')[:40])} ({period})")  # 발송은 HTML 모드
        if not plans:
            common = [c for c in post.get("common", []) if c["category"] in DIRECT_CATEGORIES]
            if common:
                for c in common:
                    cond = f"{c['min_fee']:,}원 이상 " if c.get("min_fee") else ""
                    lines.append(f"  • 공통: {cond}{html.escape(c['name'])} {_won(c['total_won'])}")
            else:
                lines.append("  • 요금제별 금액 혜택 없음")
            lines.append("")
            buttons.append({"text": f"🌐 {post.get('title', '')[:20]}", "url": post.get("url", "")})
            continue
        any_plan = True
        for p in plans:
            gb = p["base_gb"]
            gb_s = str(int(gb)) if gb == int(gb) else str(gb)
            parts = "+".join(f"{CATEGORY_LABEL[b['category']]}{_won(b['total_won'])}" for b in p.get("direct_benefits", []))
            line = f"  • {gb_s}GB 월{p['monthly_fee']:,}원: {_won(p['total_won']) if p['total_won'] else '0'}"
            if parts:
                line += f" ({parts})"
            ex = excluded_benefits(p)
            if ex:
                line += " / 조건부 " + ", ".join(
                f"{'제휴이용권' if _is_service(b) else CATEGORY_LABEL[b['category']]}{_won(b['total_won'])}" for b in ex)
            lines.append(line)
        lines.append("")
        buttons.append({"text": f"🌐 {post.get('title', '')[:20]}", "url": post.get("url", "")})
    if not posts:
        lines.append("ℹ️ 진행중 알뜰요금제 이벤트 없음")
    elif any_plan:
        lines.append("※ 금액 = 기본혜택 + 프로모션코드 + 요금제혜택(쿠폰팩·Npay 등). 친구추천·자급제·제휴이용권은 조건부로 별도 표시")
    return "\n".join(lines).strip(), buttons[:4]
