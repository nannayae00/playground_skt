# -*- coding: utf-8 -*-
import re, json, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.uplusumobile.com"
LIST_URL = f"{BASE_URL}/event-benefit/event/ongoing"
TEST_POST_IDS = ["12590", "10314"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    print(f"  → {r.status_code} | {len(r.text):,}자 | {url}")
    return r

print("\n" + "="*60)
print("STEP 1: 목록 페이지 게시글 링크 수집")
print("="*60)
r = fetch(LIST_URL)
soup = BeautifulSoup(r.text, "html.parser")

links = soup.find_all("a", href=re.compile(r"/event-benefit/event/ongoing/\d+"))
print(f"\n패턴1 (<a href=/ongoing/숫자>): {len(links)}건")
for a in links[:5]:
    print(f"  {a['href']}  |  {a.get_text(strip=True)[:40]}")

scripts = soup.find_all("script", id="__NEXT_DATA__")
if scripts:
    nd = json.loads(scripts[0].string)
    print(f"\n__NEXT_DATA__ 있음 — 키: {list(nd.keys())[:5]}")
else:
    print("\n__NEXT_DATA__: 없음")

body = soup.find("body")
if body:
    print(f"\n[body 텍스트 앞 300자]\n{body.get_text()[:300]}")

print("\n" + "="*60)
print("STEP 2: 게시글 이미지 URL 수집")
print("="*60)
for post_id in TEST_POST_IDS:
    url = f"{BASE_URL}/event-benefit/event/ongoing/{post_id}"
    print(f"\n--- 게시글 {post_id} ---")
    r2 = fetch(url)
    soup2 = BeautifulSoup(r2.text, "html.parser")
    imgs = soup2.find_all("img")
    print(f"전체 img: {len(imgs)}개")
    for img in imgs[:15]:
        src = img.get("src") or img.get("data-src") or ""
        if src:
            print(f"  {urljoin(BASE_URL, src)[:100]}")
    print("  [컨테이너 후보]")
    for sel in ["article","main","div.event-detail","div.event_content","div.content","section"]:
        found = soup2.select(sel)
        if found:
            print(f"  '{sel}': {len(found)}개, img {len(found[0].find_all('img'))}개")
