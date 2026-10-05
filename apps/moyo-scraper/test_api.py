from playwright.sync_api import sync_playwright
import json

print("🔍 API 호출 찾기...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # API 호출 캐치
    api_calls = []
    
    def handle_response(response):
        # JSON 응답만 캐치
        if 'json' in response.headers.get('content-type', ''):
            api_calls.append({
                'url': response.url,
                'status': response.status
            })
    
    page.on('response', handle_response)
    
    print("📡 페이지 로딩...")
    page.goto("https://www.moyoplan.com/plans", timeout=90000)
    page.wait_for_load_state('domcontentloaded')
    
    print(f"\n📋 발견된 API 호출 {len(api_calls)}개:\n")
    for call in api_calls:
        print(f"  {call['status']} - {call['url']}")
    
    browser.close()