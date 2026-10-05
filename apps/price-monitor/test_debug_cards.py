"""
test_debug_cards.py
목적: 26613, 30954 누락 원인 디버깅
- 3페이지만 수집
- 모든 카드 raw text 출력
- 특히 26613, 30954 상세 출력
"""

import asyncio
import re
from playwright.async_api import async_playwright

BASE_URL  = "https://www.moyoplan.com/plans"
TARGET_IDS = {'26613', '30954'}
MAX_PAGES = 3

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-dev-shm-usage', '--disable-gpu']
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        )
        page = await context.new_page()
        seen_ids = set()
        all_ids  = []

        for page_num in range(1, MAX_PAGES + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
            print(f"\n{'='*60}")
            print(f"📄 {page_num}페이지: {url}")
            print('='*60)

            await page.goto(url, timeout=60_000, wait_until='domcontentloaded')
            await page.wait_for_timeout(1500)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)

            # 전체 카드 수집
            card_data = await page.evaluate("""
                () => {
                    const cards = document.querySelectorAll('a[href^="/plans/"]');
                    return Array.from(cards).map(card => {
                        const href = card.getAttribute('href') || '';
                        const id   = href.replace('/plans/', '');
                        const img  = card.querySelector('img');
                        const alt  = img ? (img.alt || '') : '';
                        const text = card.innerText
                            .split('\\n')
                            .map(s => s.trim())
                            .filter(s => s.length > 0)
                            .join('|');
                        return { id, alt, text };
                    });
                }
            """)

            page_ids = []
            for item in card_data:
                pid = item.get('id', '')
                if not re.match(r'^\d+$', pid):
                    continue
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                page_ids.append(pid)
                all_ids.append(pid)

                # 타겟 ID면 상세 출력
                if pid in TARGET_IDS:
                    print(f"\n🎯 TARGET 발견: {pid}")
                    print(f"   alt(사업자): {item.get('alt', '')}")
                    print(f"   raw text: {item.get('text', '')}")
                    parts = [p for p in item.get('text','').split('|') if p.strip()]
                    print(f"   parts({len(parts)}개): {parts}")

            print(f"\n✅ {page_num}페이지 카드: {len(page_ids)}개 → {page_ids}")
            print(f"   타겟 포함 여부: 26613={'26613' in page_ids} / 30954={'30954' in page_ids}")

        print(f"\n{'='*60}")
        print(f"📊 전체 수집: {len(all_ids)}개")
        print(f"26613 수집됨: {'26613' in all_ids}")
        print(f"30954 수집됨: {'30954' in all_ids}")

        await browser.close()

asyncio.run(main())
