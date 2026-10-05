#!/bin/bash
# deploy.sh
# ============================================================
# [수정 이력]
# v1.0 | 2026-05-27 | 최초 작성 - Cloud Run 배포 스크립트
# ============================================================

set -e

PROJECT="mvno-484509"
SERVICE="mvno-dashboard"
REGION="asia-northeast3"
IMAGE="gcr.io/${PROJECT}/${SERVICE}"

echo "🚀 MVNO Dashboard 배포 시작..."
echo "   프로젝트: ${PROJECT}"
echo "   서비스:   ${SERVICE}"
echo "   리전:     ${REGION}"
echo ""

# 1. 이미지 빌드 & 푸시
echo "📦 [1/3] Cloud Build 이미지 빌드..."
gcloud builds submit \
  --project="${PROJECT}" \
  --tag="${IMAGE}" \
  .

# 2. Cloud Run 배포
echo "☁️  [2/3] Cloud Run 배포..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="DASHBOARD_ID=mvno,DASHBOARD_PW=skt2026!" \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=30s

# 3. URL 확인
echo ""
echo "✅ [3/3] 배포 완료!"
echo ""
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format="value(status.url)"

echo ""
echo "🔐 접속 정보:"
echo "   ID: mvno"
echo "   PW: (배포 시 설정한 값)"
echo ""
echo "💡 팁: 비밀번호를 Secret Manager로 관리하려면"
echo "   gcloud secrets create dashboard-pw --data-file=- <<< '비밀번호'"
echo "   그 후 --set-secrets='DASHBOARD_PW=dashboard-pw:latest' 옵션 사용"
