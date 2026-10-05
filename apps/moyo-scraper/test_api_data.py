import requests
import json

print("🔍 모요 API 테스트...\n")

url = "https://api.moyoplan.com/core/api/v2/moyo/plan-search/ranking?sorting=recommend_v2"

# 브라우저처럼 헤더 추가
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Referer': 'https://www.moyoplan.com/',
    'Origin': 'https://www.moyoplan.com'
}

response = requests.get(url, headers=headers)
print(f"응답 상태: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    
    print(f"\nJSON 키 목록: {list(data.keys())}")
    
    print("\n전체 JSON (처음 1000자):")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
    
    with open('moyo_api_response.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("\n✅ JSON 저장: moyo_api_response.json")
    
elif response.status_code == 405:
    print("\n❌ 405 에러 - POST 방식 시도...")
    
    # POST로 시도
    response = requests.post(url, headers=headers, json={})
    print(f"POST 응답 상태: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nJSON 키 목록: {list(data.keys())}")
        
        with open('moyo_api_response.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print("✅ JSON 저장: moyo_api_response.json")
    else:
        print(f"POST도 실패: {response.status_code}")
        print(response.text[:500])
else:
    print(f"❌ 에러: {response.status_code}")
    print(response.text[:500])