# mvno-issue-collector 봇 배포 가이드

## 1. Secret Manager에 토큰 등록

```bash
# 텔레그램 봇 토큰 (BotFather에서 재발급받은 새 토큰으로)
echo -n "YOUR_NEW_BOT_TOKEN" | \
  gcloud secrets create mvno-issue-bot-token \
  --data-file=- --project=mvno-484509

# Gemini API 키 (이 서비스 전용 시크릿, deploy.sh v1.5부터 필수)
# 지금 Cloud Run에 평문 env로 들어있는 키를 화면 출력 없이 그대로 옮기는 방법:
gcloud run services describe mvno-issue-collector --region asia-northeast3 --format=json \
  | python3 -c "import json,sys;e=json.load(sys.stdin)['spec']['template']['spec']['containers'][0]['env'];print(next(x['value'] for x in e if x['name']=='GEMINI_API_KEY'),end='')" \
  | gcloud secrets create mvno-issue-gemini-key --replication-policy=automatic --data-file=- --project=mvno-484509
# (런타임 계정 668782164620-compute@ 는 프로젝트 단위 secretAccessor가 있어 추가 권한 불필요)
# 시크릿 생성 후 ./deploy.sh 로 재배포하면 env의 평문 키가 사라지고 시크릿 참조로 바뀜
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

## 4. 스케줄러 (현재 등록된 것)

| 잡 | 시각(KST) | 호출 |
|---|---|---|
| mvno-news-digest-morning | 07:45 | POST /daily-news |
| mvno-news-digest-noon | 12:45 | POST /daily-news (2026-11-04 추가) |
| mvno-news-digest-evening | 18:45 | POST /daily-news (2026-11-04 추가) |

이미 보낸 기사는 `scraped_news_seen`으로 걸러져 회차마다 새 기사만 전송됨.
수동 실행: `gcloud scheduler jobs run mvno-news-digest-morning --location asia-northeast3`
전송 없이 확인: `curl -X POST "$SERVICE_URL/daily-news?dry_run=true"`

## 5. daily 리포트 Cloud Scheduler 등록

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
