from playwright.sync_api import sync_playwright
import json

print("🔍 Playwright로 API 응답 캐치...\n")

api_data = None

def handle_response(response):
    global api_data
    
    if 'plan-search/ranking' in response.url:
        print(f"✅ API 발견: {response.url}")
        print(f"   상태: {response.status}")
        
        try:
            api_data = response.json()
            print(f"   데이터 수신 성공!")
        except:
            print(f"   JSON 파싱 실패")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    page.on('response', handle_response)
    
    print("📡 페이지 로딩...")
    page.goto("https://www.moyoplan.com/plans", timeout=90000)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(3000)  # 3초 대기
    
    browser.close()

if api_data:
    print("\n📊 API 데이터 저장 중...")
    
    with open('moyo_api_response.json', 'w', encoding='utf-8') as f:
        json.dump(api_data, f, indent=2, ensure_ascii=False)
    
    print("✅ JSON 저장: moyo_api_response.json")
    print(f"\nJSON 키 목록: {list(api_data.keys())}")
    print("\n처음 1000자:")
    print(json.dumps(api_data, indent=2, ensure_ascii=False)[:1000])
else:
    print("\n❌ API 데이터를 받지 못했습니다")