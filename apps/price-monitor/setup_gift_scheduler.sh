#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# setup_gift_scheduler.sh - gift-sensing-job 스케줄러 등록 (최초 1회만 실행)
# 사용법: bash setup_gift_scheduler.sh
# 스케줄: 매일 08:00 / 13:00 / 19:00 KST
# ══════════════════════════════════════════════════════════════════════════════

PROJECT="mvno-484509"
REGION="asia-northeast3"
GIFT_JOB_NAME="gift-sensing-job"

# 기존 moyo-scrape-job SA 재사용
SA=$(gcloud run jobs describe moyo-scrape-job \
  --region ${REGION} --project ${PROJECT} \
  --format="value(spec.template.spec.serviceAccountName)")

URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${GIFT_JOB_NAME}:run"

echo "📅 gift-sensing 스케줄러 등록 (08:00 / 13:00 / 19:00 KST)"
echo "   SA: ${SA}"
echo ""

for HOUR in 8 13 19; do
  NAME="gift-sensing-${HOUR}h"
  echo "⏳ ${NAME} 등록 중..."
  gcloud scheduler jobs create http ${NAME} \
    --location ${REGION} \
    --schedule="0 ${HOUR} * * *" \
    --time-zone="Asia/Seoul" \
    --uri="${URI}" \
    --oauth-service-account-email="${SA}" \
    --message-body="{}" \
    --project ${PROJECT} 2>/dev/null && echo "  ✅ 완료" || \
  gcloud scheduler jobs update http ${NAME} \
    --location ${REGION} \
    --schedule="0 ${HOUR} * * *" \
    --time-zone="Asia/Seoul" \
    --uri="${URI}" \
    --oauth-service-account-email="${SA}" \
    --message-body="{}" \
    --project ${PROJECT} && echo "  ✅ 업데이트 완료"
done

echo ""
echo "✅ 스케줄러 등록 완료!"
echo "   매일 08:00 / 13:00 / 19:00 KST 자동 실행"
echo ""
echo "📌 확인:"
echo "   gcloud scheduler jobs list --location ${REGION} | grep gift"
