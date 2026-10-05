#!/bin/bash
# deploy.sh - Cloud Run 배포 스크립트
#
# [수정 이력]
# v1.0 | 2026-03-19 | 최초 작성
# v1.1 | 2026-03-19 | 서비스 계정 → OAuth2 방식으로 변경
# v1.2 | 2026-09-20 | 하드코딩된 텔레그램 봇 토큰 제거 — env.yaml에서 읽도록 변경
#      | (레포에 실제 토큰이 평문으로 커밋되는 걸 방지)

set -e

PROJECT_ID="mvno-484509"          # ← GCP 프로젝트 ID
REGION="asia-northeast3"               # 서울 리전
SERVICE_NAME="calendar-bot"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🔨 Docker 이미지 빌드 & 푸시..."
gcloud builds submit --tag $IMAGE --project $PROJECT_ID

echo "🚀 Cloud Run 배포..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --project $PROJECT_ID \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --env-vars-file env.yaml \
  --set-secrets "GOOGLE_CLIENT_ID=gcal-client-id:latest" \
  --set-secrets "GOOGLE_CLIENT_SECRET=gcal-client-secret:latest" \
  --set-secrets "GOOGLE_REFRESH_TOKEN=gcal-refresh-token:latest"

SERVICE_URL="https://calendar-bot-668782164620.asia-northeast3.run.app"

echo "✅ 배포 완료: $SERVICE_URL"

echo "📡 텔레그램 Webhook 등록..."
# env.yaml에서 TELEGRAM_TOKEN 읽어서 사용 (하드코딩 금지)
TELEGRAM_TOKEN=$(grep '^TELEGRAM_TOKEN:' env.yaml | sed 's/TELEGRAM_TOKEN:[[:space:]]*//')
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook" \
  -d "url=$SERVICE_URL/webhook" | python3 -m json.tool

echo "🎉 완료!"
