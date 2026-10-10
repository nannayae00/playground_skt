"""
gift_skylife_event_scraper.py  v0.1
KT스카이라이프 직영몰 "이달의 가입혜택" 수집 (모요 vs 스카이직영 비교용)

[v0.1 / 2026-10-10] 신규
- 대상: https://www.skylife.co.kr/event/MonthlyBenefits (모바일 N월 가입혜택 모음)
  Next.js 페이지라 혜택 본문은 자바스크립트로 그려지지만, 원본 HTML의 RSC 데이터
  (self.__next_f.push)에 혜택 이미지 주소가 그대로 들어 있어 브라우저 없이 수집 가능.
- 혜택이 유모바일/KT엠처럼 "요금제 카드(데이터량)별"이 아니라 "요금제 가격대별"
  (예: 3만원 이상 S-머니 6만원, 5천원~3만원 미만 3만원) + 조건부 추가혜택
  (바로유심 개통, 골드 요금제, 아이폰 자급제 등)이라 별도 스키마로 저장.
- 모요 비교: 모요의 KT스카이라이프 요금제마다 월 요금(base_price)으로 직영 정기혜택을
  계산해 데이터량별 최대값(direct_dk_max)을 만들고 기존 format_moyo_vs_direct()에 넘김.
  조건부 추가혜택은 비교값에 넣지 않고 메시지에만 표시.
- 캐시: 이미지 주소 목록 해시가 같으면 Vision 재파싱 없이 Firestore 캐시 재사용.
"""
import os
import re
import json
import base64
import hashlib
import requests
from datetime import datetime, timezone

BASE_URL = "https://www.skylife.co.kr"
EVENT_URL = f"{BASE_URL}/event/MonthlyBenefits"
CACHE_COLLECTION = "skylife_event_cache"
CACHE_DOC = "monthly_benefits"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

GEMINI_PROMPT = """당신은 통신사(KT스카이라이프 알뜰폰) 가입혜택 안내 이미지에서 금전성 혜택을 추출하는 분석기입니다.
이미지의 혜택 박스마다 아래 JSON 배열의 항목 하나로 답하세요. 순수 JSON만 출력합니다.

스키마:
[
  {"name": "혜택명 (예: S-머니 정기혜택)",
   "condition": "받는 조건 원문 요약 (예: 3만원 이상 요금제 가입 시)",
   "kind": "regular 또는 extra",
   "min_fee": 대상 요금제 월정액 하한(원, 정수, 없으면 0),
   "max_fee": 대상 요금제 월정액 상한(원, 정수, '미만' 기준, 없으면 0),
   "amount_won": 1회 지급 금액(원, 정수),
   "months": 지급 개월수(1회성=1),
   "total_won": amount_won*months}
]

규칙:
1. 숫자는 쉼표 없이 정수로만 쓴다. "N천원"=N*1000, "N만원"=N*10000
2. kind: 요금제 가격 조건만 맞으면 누구나 받는 혜택은 "regular",
   선착순/연령/특정 요금제명/단말 구매/개통 경로(바로유심, 편의점 등) 같은 추가 조건이 있으면 "extra"
3. "6개월*1만원 → 6만원"처럼 표기된 경우 amount_won=10000, months=6, total_won=60000
4. 지급되는 혜택(S-머니, 상품권, 네이버페이 등 페이, 포인트, 캐시)만 넣는다.
   요금 할인, 결합 할인(통신비 반값 등), 제휴카드 할인, 구독/제휴 서비스 할인, 데이터 추가는 넣지 않는다
5. 안내/유의사항/교환처 소개, 같은 혜택을 다시 요약한 문구는 넣지 않는다
6. 혜택 박스가 없는 이미지는 빈 배열 []
"""


def _decode_rsc(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    blob = "".join(chunks).encode().decode("unicode_escape", errors="ignore")
    return blob.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")


def fetch_monthly_benefits() -> dict:
    """이달의 가입혜택 페이지 → {title, image_urls, img_hash, url}"""
    r = requests.get(EVENT_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    blob = _decode_rsc(r.text)
    title_m = re.search(r'"og:title","content":"([^"]+)"', blob) or re.search(r"<title>([^<]+)</title>", r.text)
    title = (title_m.group(1).split("|")[0].strip() if title_m else "스카이라이프 가입혜택")
    # 반응형 이미지 블록의 PC용(고해상도) 이미지만 사용 - 모바일용은 같은 내용의 축소판
    urls = []
    for u in re.findall(r'<source media="\(min-width: 768px\)" srcset="(https://homeapp\.skylife\.co\.kr/[^"]+)"', blob):
        if u not in urls:
            urls.append(u)
    img_hash = hashlib.md5("|".join(sorted(urls)).encode("utf-8")).hexdigest()
    return {"title": title, "image_urls": urls, "img_hash": img_hash, "url": EVENT_URL}


def parse_images_with_gemini(image_urls: list) -> tuple:
    """이미지들 → (benefits, failures)"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 없음")
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")

    benefits, failures = [], 0
    for idx, url in enumerate(image_urls, 1):
        fname = url.split("/")[-1][:20]
        try:
            img = requests.get(url, headers=HEADERS, timeout=30)
            img.raise_for_status()
            mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
            resp = client.models.generate_content(
                model=model_name,
                contents=[types.Part.from_bytes(data=img.content, mime_type=mime), GEMINI_PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            items = json.loads((resp.text or "[]").strip())
        except Exception as e:
            print(f"[skylife] 이미지 {idx}/{len(image_urls)} 파싱 실패: {fname} | {e}")
            failures += 1
            continue
        n = 0
        for b in (items if isinstance(items, list) else []):
            try:
                amount = int(b.get("amount_won") or 0)
                months = max(int(b.get("months") or 1), 1)
                item = {
                    "name": str(b.get("name", "")).strip(),
                    "condition": str(b.get("condition", "")).strip(),
                    "kind": "regular" if b.get("kind") == "regular" else "extra",
                    "min_fee": int(b.get("min_fee") or 0),
                    "max_fee": int(b.get("max_fee") or 0),
                    "amount_won": amount,
                    "months": months,
                    "total_won": amount * months,
                }
            except (TypeError, ValueError):
                continue
            if item["total_won"] > 0:
                benefits.append(item)
                n += 1
        print(f"[skylife] 이미지 {idx}/{len(image_urls)}: {fname} → 혜택 {n}건")

    # 할인성 항목 제외 (프롬프트 규칙의 안전장치)
    benefits = [b for b in benefits if "할인" not in (b["name"] + b["condition"])]
    # 가격대 조건이 없는 regular는 비교값을 부풀리므로 extra로 강등
    for b in benefits:
        if b["kind"] == "regular" and not (b["min_fee"] or b["max_fee"]):
            b["kind"] = "extra"
    # regular: 같은 가격대(min_fee, max_fee)는 1건만 - 이미지마다 이름만 다르게 반복 안내되는 경우
    # (예: "S-머니 정기혜택"과 "정기혜택 (3만원 미만 요금제)")가 합산되지 않도록 금액 큰 것 1건
    uniq, seen = [], {}
    for b in sorted(benefits, key=lambda x: -x["total_won"]):
        key = ("regular", b["min_fee"], b["max_fee"]) if b["kind"] == "regular" else ("extra", b["name"], b["condition"], b["total_won"])
        if key not in seen:
            seen[key] = True
            uniq.append(b)
    return uniq, failures


def scrape_with_cache(db) -> dict:
    """캐시 기반 수집 → {title, url, image_urls, benefits, from_cache}"""
    page = fetch_monthly_benefits()
    ref = db.collection(CACHE_COLLECTION).document(CACHE_DOC)
    cached = ref.get()
    cached = cached.to_dict() if cached.exists else {}
    if cached.get("img_hash") == page["img_hash"] and cached.get("parse_ok"):
        page["benefits"] = cached.get("benefits", [])
        page["from_cache"] = True
        print(f"[skylife] ⏭️  캐시 재사용: {page['title']} (혜택 {len(page['benefits'])}건)")
        return page

    print(f"[skylife] 🔍 {'신규' if not cached else '변경감지'} → Gemini 파싱: {page['title']} (이미지 {len(page['image_urls'])}장)")
    benefits, failures = parse_images_with_gemini(page["image_urls"]) if page["image_urls"] else ([], 0)
    page["benefits"] = benefits
    page["from_cache"] = False
    ref.set({
        "title": page["title"],
        "url": page["url"],
        "img_hash": page["img_hash"],
        "image_urls": page["image_urls"],
        "benefits": benefits,
        "parse_ok": bool(page["image_urls"]) and failures == 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[skylife] ✅ 파싱 완료: 혜택 {len(benefits)}건 (실패 이미지 {failures}장)")
    return page


def regular_value_for_fee(benefits: list, fee: int) -> int:
    """월 요금 fee인 요금제가 조건 없이 받는 정기혜택 합계 (가격대 조건만 확인)."""
    total = 0
    for b in benefits:
        if b.get("kind") != "regular":
            continue
        lo, hi = b.get("min_fee") or 0, b.get("max_fee") or 0
        if fee >= lo and (not hi or fee < hi):
            total += b["total_won"]
    return total


# [추가 20261010] 직영 비교값에 포함하는 개통경로 혜택 - 바로유심(편의점)/바로배송은 누구나 받을 수 있어
# 사용자 결정(2번안)으로 정기혜택에 더해서 비교 (골드·아이폰 등 대상 제한 혜택은 제외)
CHANNEL_KEYWORDS = ("바로유심", "바로배송")


def channel_benefits(benefits: list) -> list:
    return [b for b in benefits
            if b.get("kind") == "extra" and any(k in (b.get("name", "") + b.get("condition", "")) for k in CHANNEL_KEYWORDS)]


def direct_benefits_for_fee(benefits: list, fee: int) -> list:
    """월 요금 fee 요금제의 직영 비교 대상 혜택 = 해당 가격대 정기혜택 + 바로유심/바로배송 혜택(1건, 최대값).
    정기혜택 대상이 아닌 요금제(예: 월 5천원 미만)는 공통 제외 대상이라 빈 리스트."""
    regular = [b for b in benefits if b.get("kind") == "regular"
               and fee >= (b.get("min_fee") or 0) and (not b.get("max_fee") or fee < b["max_fee"])]
    if not regular:
        return []
    ch = sorted(channel_benefits(benefits), key=lambda b: -b["total_won"])[:1]
    return regular + ch


def direct_value_for_fee(benefits: list, fee: int) -> int:
    return sum(b["total_won"] for b in direct_benefits_for_fee(benefits, fee))


def build_kcup_direct_posts(moyo_plans: list, page: dict) -> list:
    """K CUP 비교(build_kcup_records)용 직영 post 형식 - 모요의 스카이라이프 요금제마다
    직영 비교값(정기+바로유심)을 붙인 가상 plan 목록."""
    plans = []
    for p in moyo_plans:
        if p.get("provider") != "KT스카이라이프":
            continue
        fee = int(p.get("base_price") or 0)
        bens = direct_benefits_for_fee(page.get("benefits") or [], fee)
        if not bens:
            continue
        plans.append({
            "plan_name": p.get("name", ""),
            "base_gb": float(p.get("data_gb") or 0),
            "total_won": sum(b["total_won"] for b in bens),
            "benefits": bens,
        })
    return [{"title": page.get("title", ""), "url": page.get("url", EVENT_URL),
             "date_start": "", "date_end": "", "plans": plans}]


def compute_direct_dk_max(moyo_plans: list, benefits: list) -> dict:
    """모요의 KT스카이라이프 요금제별로 직영 정기혜택을 계산 → {data_key: max_won}"""
    from core.gift_comparator import _data_key
    dk_max = {}
    for p in moyo_plans:
        if p.get("provider") != "KT스카이라이프":
            continue
        fee = int(p.get("base_price") or 0)
        if fee <= 0:
            continue
        dk = _data_key(p)
        if dk == "unknown":
            continue
        val = direct_value_for_fee(benefits, fee)
        if val > dk_max.get(dk, 0):
            dk_max[dk] = val
    return dk_max


def _won(v: int) -> str:
    return f"{v // 10000}만원" if v % 10000 == 0 else f"{v:,}원"


def format_telegram_message(page: dict, now_str: str = None) -> tuple:
    """→ (text, buttons)"""
    now_str = now_str or datetime.now().strftime("%Y-%m-%d %H:%M")
    benefits = page.get("benefits") or []
    lines = [f"📡 KT스카이라이프 직영 가입혜택  📅 {now_str}", f"({page.get('title', '')})", ""]
    regular = sorted([b for b in benefits if b["kind"] == "regular"], key=lambda b: -b["min_fee"])
    extra = sorted([b for b in benefits if b["kind"] == "extra"], key=lambda b: -b["total_won"])
    if regular:
        lines.append("■ 정기혜택 (요금제 가격대별)")
        for b in regular:
            lines.append(f"• {b['condition'] or b['name']}: {b['name']} {_won(b['total_won'])}")
        lines.append("")
    if extra:
        lines.append("■ 추가 조건 혜택")
        for b in extra:
            lines.append(f"• {b['name']} {_won(b['total_won'])} ({b['condition']})")
        lines.append("")
    if not benefits:
        lines.append("ℹ️ 현재 수집된 가입혜택 금액 없음")
    buttons = [{"text": "🌐 스카이라이프 이달의 가입혜택", "url": page.get("url", EVENT_URL)}]
    return "\n".join(lines).strip(), buttons
