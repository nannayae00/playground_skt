import requests

# 분석 봇에 직접 데이터 전송
url = "https://mvno-bot-668782164620.asia-northeast3.run.app/webhook"

# 사람이 보낸 것처럼 구성
data = {
    "message": {
        "message_id": 999,
        "from": {
            "id": 123456789,
            "is_bot": False,  # 사람으로 가장
            "first_name": "AutoBot"
        },
        "chat": {
            "id": -4997611682,
            "type": "group",
            "title": "260122테스트봇"
        },
        "text": """◎ 01월 당일 마감
S 2,626 (20.3%)
K 4,700 (36.3%)
L 5,613 (43.4%)
계 12,939

◎ 01월 누적 MVNO MNP 해지
S 37,402 (19.2%)
K 68,345 (35.1%)
L 89,242 (45.8%)
계 194,989"""
    }
}

response = requests.post(url, json=data)
print("응답:", response.status_code, response.text)
