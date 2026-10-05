#!/bin/bash
# deploy.sh  v1.2
# 작성일: 2026-06-30
#
# [수정 이력]
# [v1.0 / 2026-06-30] 신규 생성
# [v1.1 / 2026-07-02] GEMINI_API_KEY 환경변수 직접 주입 방식으로 변경
# [v1.2 / 2026-07-02] --allow-unauthenticated 변경 (텔레그램 webhook 403 오류 수정)

set -e

PROJECT_ID="mvno-484509"
REGION="asia-northeast3"
SERVICE_NAME="mvno-issue-collector"
IMAGE="asia-northeast3-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}"

echo "🚀 ${SERVICE_NAME} 배포 시작..."

# 이미지 빌드 & 푸시
gcloud builds submit --tag ${IMAGE} .

# Cloud Run 배포
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --set-secrets="TELEGRAM_TOKEN=mvno-issue-bot-token:latest" \
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},GEMINI_API_KEY=${GEMINI_API_KEY},TELEGRAM_CHAT_ID=-1003970573811,GOOGLE_GENAI_USE_VERTEXAI=false" \
  --memory 512Mi \
  --timeout 120

echo "✅ 배포 완료!"

# webhook URL 자동 등록
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
WEBHOOK_URL="${SERVICE_URL}/webhook"

echo "📡 Webhook 등록 중: ${WEBHOOK_URL}"
TOKEN=$(gcloud secrets versions access latest --secret=mvno-issue-bot-token)
curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${WEBHOOK_URL}" | python3 -m json.tool

echo "🎉 완료! 봇 URL: ${SERVICE_URL}"