import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = "-4997611682"

message = """◎ 01월 당일 마감
S 2,626 (20.3%)
K 4,700 (36.3%)
L 5,613 (43.4%)
계 12,939

◎ 01월 누적 순증감
S +8,798 (42.5%)
K +8,686 (41.9%)
L +3,226 (15.6%)
계 +20,710

◎ 01월 누적 MVNO MNP 해지
S 37,402 (19.2%)
K 68,345 (35.1%)
L 89,242 (45.8%)
계 194,989"""

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": message}

response = requests.post(url, json=data)
print("발송 결과:", response.json())
