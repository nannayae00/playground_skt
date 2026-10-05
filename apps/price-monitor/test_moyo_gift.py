# -*- coding: utf-8 -*-
"""
test_moyo.py - 모요 LG 자회사 테마 페이지 수집 테스트 (주인님 환경에서 실행)

[수정 이력]
- v0.1 (2026-07-07) 최초 작성

[실행 방법 - Cloud Shell 또는 로컬]
    pip install playwright && playwright install chromium
    python test_moyo.py

[확인 포인트]
1. 카드가 몇 건 잡히는지 (0건이면 셀렉터 문제)
2. dump_moyo_gift.txt 에서 카드 innerText 구조 확인
3. '사은품 최대 N개' 펼침 후 사은품 텍스트가 잡히는지
→ 결과를 Claude에게 붙여넣으면 셀렉터 확정해서 v0.3 반영
"""

import asyncio
from playwright.async_api import async_playwright

THEME_URL = 'https://www.moyoplan.com/plans/themes/lg-subsidiary'

# 후보 카드 셀렉터 (위에서부터 순차 시도)
CARD_SELECTORS = [
    'a[href*="/plans/"]',            # 요금제 상세 링크 카드
    '[class*="planCard"]',
    '[class*="PlanCard"]',
    'li[class*="plan"]',
    'div[class*="card"]',
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/126.0 Safari/537.36'),
            locale='ko-KR')
        page = await context.new_page()

        print(f'접속: {THEME_URL}')
        await page.goto(THEME_URL, wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(2000)
        print(f'타이틀: {await page.title()}')

        # 1) 셀렉터별 카드 수 확인
        best_selector, best_cards = None, []
        for sel in CARD_SELECTORS:
            cards = await page.query_selector_all(sel)
            print(f'  {sel:<28} → {len(cards)}건')
            if len(cards) > len(best_cards):
                best_selector, best_cards = sel, cards

        if not best_cards:
            print('\n⚠️ 카드 미검출. 페이지 전체 텍스트 앞부분:')
            body = await page.inner_text('body')
            print(body[:2000])
            with open('dump_moyo_body.txt', 'w', encoding='utf-8') as f:
                f.write(body)
            print('→ dump_moyo_body.txt 저장됨. Claude에게 공유해주세요.')
            await browser.close()
            return

        print(f'\n✅ 최다 검출 셀렉터: {best_selector} ({len(best_cards)}건)')

        # 2) 상위 5개 카드 innerText 덤프
        dump = []
        for i, card in enumerate(best_cards[:5]):
            text = await card.inner_text()
            dump.append(f'{"="*60}\n[카드 {i+1}]\n{text}')

        # 3) '사은품' 토글 클릭 테스트 (첫 카드)
        try:
            toggle = await page.query_selector('text=/사은품 최대/')
            if toggle:
                await toggle.click()
                await page.wait_for_timeout(500)
                text_after = await best_cards[0].inner_text()
                dump.append(f'{"="*60}\n[사은품 펼침 후 카드1]\n{text_after}')
                print('사은품 토글 클릭 성공')
            else:
                print('⚠️ 사은품 토글 미발견 - 덤프에서 구조 확인 필요')
        except Exception as e:
            print(f'⚠️ 토글 클릭 실패: {e}')

        with open('dump_moyo_gift.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(dump))
        print('\n→ dump_moyo_gift.txt 저장 완료. 내용을 Claude에게 붙여넣어 주세요.')
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
