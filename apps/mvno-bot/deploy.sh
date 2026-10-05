#!/bin/bash
# MVNO AX Agent - mvno-bot 배포 스크립트
# 사용법: ./deploy.sh
#
# [수정 이력]
# v1.1 | 2026-06-12 | mvno-bot 서비스(Cloud Run Service) 배포 단계 추가
#   - 기존: ktoa-collector(Job)만 업데이트 → mvno-bot(Service, main.py)이
#     같은 이미지를 쓰는데도 갱신 안 되는 문제 발견
#   - 추가: 3. mvno-bot 서비스 업데이트 (트리거 엔드포인트/텔레그램 봇)
set -e
cd "$(dirname "$0")"

echo "=== 1. 빌드 + 푸시 ==="
gcloud builds submit --tag gcr.io/mvno-484509/mvno-bot

echo ""
echo "=== 2. ktoa-collector 업데이트 ==="
gcloud run jobs update ktoa-collector \
  --image gcr.io/mvno-484509/mvno-bot \
  --region asia-northeast3

echo ""
echo "=== 3. mvno-bot 서비스 업데이트 ==="
gcloud run services update mvno-bot \
  --image gcr.io/mvno-484509/mvno-bot \
  --region asia-northeast3

echo ""
echo "✅ 배포 완료"
