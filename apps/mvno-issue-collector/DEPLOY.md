# mvno-issue-collector 봇 배포 가이드

## 1. Secret Manager에 토큰 등록

```bash
# 텔레그램 봇 토큰 (BotFather에서 재발급받은 새 토큰으로)
echo -n "YOUR_NEW_BOT_TOKEN" | \
  gcloud secrets create mvno-issue-bot-token \
  --data-file=- --project=mvno-484509

# Gemini API 키 (기존에 있으면 건너뜀)
# 이미 gemini-api-key secret 있으면:
# gcloud secrets versions add gemini-api-key --data-file=<(echo -n "KEY")
```

## 2. TELEGRAM_CHAT_ID 확인

봇에게 텔레그램에서 아무 메시지 보낸 뒤:
```bash
TOKEN="YOUR_BOT_TOKEN"
curl "https://api.telegram.org/bot${TOKEN}/getUpdates" | python3 -m json.tool
# result[0].message.chat.id 값이 CHAT_ID
```

## 3. deploy.sh에서 YOUR_CHAT_ID 교체 후 배포

```bash
cd ~/mvno-issue-collector/bot
# deploy.sh 안의 YOUR_CHAT_ID를 실제 값으로 교체
nano deploy.sh

chmod +x deploy.sh
./deploy.sh
```

## 4. daily 리포트 Cloud Scheduler 등록

```bash
SERVICE_URL=$(gcloud run services describe mvno-issue-collector \
  --region asia-northeast3 --format 'value(status.url)')

gcloud scheduler jobs create http mvno-issue-daily-report \
  --location=asia-northeast3 \
  --schedule="0 8 * * *" \
  --uri="${SERVICE_URL}/daily-report" \
  --oidc-service-account-email="YOUR_SERVICE_ACCOUNT@mvno-484509.iam.gserviceaccount.com" \
  --time-zone="Asia/Seoul"
```

## 파일 구조

```
mvno-issue-collector/
├── bot/                        ← 이 폴더를 Cloud Shell에 업로드
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── deploy.sh
│   └── handlers/
│       ├── __init__.py
│       ├── telegram.py
│       ├── input_handler.py
│       ├── callback_handler.py
│       ├── edit_handler.py
│       ├── firestore_writer.py
│       ├── session.py
│       ├── duplicate_checker.py
│       └── summary.py
├── data/                       ← 기존 seed 데이터
├── upload_seed_data.py
├── cleanup_default_db.py
├── provider_map.py
└── SCHEMA.md
```
