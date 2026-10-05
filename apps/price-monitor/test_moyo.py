from playwright.sync_api import sync_playwright

print("🔍 모요 사이트 테스트...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print("📡 접속 중...")
    # 타임아웃을 90초로 늘림
    page.goto("https://www.moyoplan.com/plans", timeout=90000)
    
    # networkidle 대신 domcontentloaded 사용 (더 빠름)
    page.wait_for_load_state('domcontentloaded', timeout=60000)
    
    print("📸 스크린샷 저장...")
    page.screenshot(path='moyo_test.png', full_page=True)
    
    print("📄 HTML 저장...")
    html = page.content()
    with open('moyo_page.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("\n✅ 완료!")
    print("  - moyo_test.png")
    print("  - moyo_page.html")
    
    browser.close()