#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# deploy.sh - price-monitor 배포 스크립트
# 사용법: cd ~/price-monitor && bash deploy.sh
#
# [수정 이력]
# 2026-08-25: gift-sensing-job GIFT_CHANNEL_ID 값을 세미콜론(;) 구분 멀티 채널로 변경
#   (gift_job.py v1.3 - 여러 방에 동시 발송, 콤마는 gcloud 환경변수 구분자와 충돌해서 세미콜론 사용)
# 2026-07-13: price-monitor 서비스 배포 단계 추가 (5/5)
# 2026-07-09: gift-sensing-job 환경변수에 GEMINI_API_KEY 추가 (유모바일 Vision 파싱)
# 2026-07-08: gift-sensing-job 배포 단계 추가 (사은품 센싱 프로그램)
# 2026-07-03: moyo_scraper.py v6.3 배포 반영 (페이백 배지 파싱 버그 수정)
# 2026-06-30: moyo-scrape-job 배포 단계 추가 (별도 이미지지만 같은 소스 폴더 사용)
#   - scrapers/moyo_scraper.py v6.2 (RS 뱃지 클래스 오탐 제거) 배포 반영
# ══════════════════════════════════════════════════════════════════════════════

set -e  # 에러 시 즉시 중단

PROJECT="mvno-484509"
REGION="asia-northeast3"
IMAGE="asia-northeast3-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/price-monitor:latest"
JOB_NAME="ppomppu-monitor-job"
SERVICE_NAME="price-monitor"
MOYO_JOB_NAME="moyo-scrape-job"
GIFT_JOB_NAME="gift-sensing-job"

# .env에서 GEMINI_API_KEY 읽기
GEMINI_API_KEY=$(grep '^GEMINI_API_KEY=' .env | cut -d'=' -f2)

echo "🚀 price-monitor 배포 시작"
echo "📦 이미지: ${IMAGE}"
echo ""

# 1. 빌드 + 푸시
echo "⏳ [1/4] 이미지 빌드 중..."
gcloud builds submit \
  --tag "${IMAGE}" \
  --project "${PROJECT}"

echo ""
echo "⏳ [2/4] ppomppu-monitor-job 업데이트 중..."
gcloud run jobs update "${JOB_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --project "${PROJECT}"

echo ""
echo "⏳ [3/4] moyo-scrape-job 배포 중..."
gcloud run jobs deploy "${MOYO_JOB_NAME}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT}"

echo ""
echo "⏳ [4/5] gift-sensing-job 배포 중..."
gcloud run jobs deploy "${GIFT_JOB_NAME}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT}" \
  --set-env-vars "TELEGRAM_TOKEN=${TELEGRAM_TOKEN},GIFT_CHANNEL_ID=-1004446911605;-1004469107624,GEMINI_API_KEY=${GEMINI_API_KEY}"

echo ""
echo "⏳ [5/5] price-monitor 서비스 배포 중..."
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT}"

echo ""
echo "✅ 배포 완료!"
echo "   Jobs: ${JOB_NAME}, ${MOYO_JOB_NAME}, ${GIFT_JOB_NAME}"
echo "   Service: ${SERVICE_NAME}"
echo ""
echo "📌 수동 실행:"
echo "   gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo "   gcloud run jobs execute ${MOYO_JOB_NAME} --region=${REGION}"
echo "   gcloud run jobs execute ${GIFT_JOB_NAME} --region=${REGION}"