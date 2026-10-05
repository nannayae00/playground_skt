import requests
import os

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = "5296554147"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    print(f"📤 전송 시도: {url}")
    print(f"   Chat ID: {CHAT_ID}")
    
    try:
        response = requests.post(url, json=data, timeout=10)
        print(f"   응답 코드: {response.status_code}")
        print(f"   응답 내용: {response.text}")
        
        if response.status_code == 200:
            print("✅ 전송 성공!")
        else:
            print("❌ 전송 실패!")
        
        return response
    except Exception as e:
        print(f"❌ 에러: {e}")
        return None

# 테스트
print("=" * 50)
print("텔레그램 전송 테스트")
print("=" * 50)

send_telegram("🧪 테스트 메시지입니다!")
