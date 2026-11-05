#!/bin/bash
# MVNO AX Agent - mvno-bot 배포 스크립트
# 사용법: ./deploy.sh            (git 저장소의 최신 main 기준 소스에서만 배포)
#        FORCE_DEPLOY=1 ./deploy.sh   (아래 사전 검사를 건너뜀 - 긴급 시에만)
#
# [수정 이력]
# v1.1 | 2026-06-12 | mvno-bot 서비스(Cloud Run Service) 배포 단계 추가
#   - 기존: ktoa-collector(Job)만 업데이트 → mvno-bot(Service, main.py)이
#     같은 이미지를 쓰는데도 갱신 안 되는 문제 발견
#   - 추가: 3. mvno-bot 서비스 업데이트 (트리거 엔드포인트/텔레그램 봇)
# v1.2 | 2026-10-19 | 배포 전 소스 검사 추가
#   - 10/08(Cloud Shell)과 10/15(다른 세션) 두 번, 옛 폴더 소스로 :latest를 덮어써
#     월마감 예측이 옛 로직으로 돌아감(10/15~19 fc_mid 400~500건 과대).
#   - 검사: ① git 저장소 안 ② 커밋 안 된 변경 없음 ③ origin/main을 포함
#     ④ 현행 예측 함수 존재. 하나라도 실패하면 빌드하지 않음.
#   - 이미지를 커밋 해시 태그로 빌드하고 Job/Service를 그 태그로 고정
#     (:latest를 누가 다시 덮어써도 운영은 바뀌지 않음, :latest도 같이 갱신).
set -e
cd "$(dirname "$0")"

IMAGE=gcr.io/mvno-484509/mvno-bot
REGION=asia-northeast3

# 현행 로직에 반드시 있어야 하는 함수 (파일:패턴)
REQUIRED_MARKERS=(
  "forecast_engine.py:def _get_prev_month_analog_pred"
  "forecast_engine.py:def get_end_aligned_tout_pred"
  "forecast_engine.py:def get_tout_mid_parts"
  "forecast_engine.py:def get_end_aligned_mvno_pred"
  "ktoa_scraper.py:def _save_all_fc_to_daily"
)

fail() { echo "❌ 배포 중단: $1"; echo "   (검사를 건너뛰려면 FORCE_DEPLOY=1 - 원인을 확인한 뒤에만)"; exit 1; }

echo "=== 0. 배포 전 검사 ==="
if [ "${FORCE_DEPLOY:-0}" != "1" ]; then
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "git 저장소가 아닙니다. playground_skt 저장소의 apps/mvno-bot에서 실행하세요."
  [ -z "$(git status --porcelain -- .)" ] \
    || fail "커밋 안 된 변경이 있습니다. 커밋(또는 정리) 후 배포하세요."
  git fetch -q origin main || fail "origin/main을 가져오지 못했습니다."
  git merge-base --is-ancestor origin/main HEAD \
    || fail "현재 소스가 최신 origin/main을 포함하지 않습니다. main을 merge/rebase 하세요."
  for m in "${REQUIRED_MARKERS[@]}"; do
    f="${m%%:*}"; p="${m#*:}"
    grep -q "$p" "$f" 2>/dev/null || fail "$f 에 '$p' 가 없습니다 (옛 소스로 보임)."
  done
  echo "검사 통과"
else
  echo "⚠️ FORCE_DEPLOY=1 - 검사 생략"
fi

TAG=$(git rev-parse --short=12 HEAD 2>/dev/null || date +%Y%m%d%H%M)
echo "이미지 태그: $TAG"

echo ""
echo "=== 1. 빌드 + 푸시 ==="
gcloud builds submit --tag "$IMAGE:$TAG"
gcloud container images add-tag -q "$IMAGE:$TAG" "$IMAGE:latest"

echo ""
echo "=== 2. ktoa-collector 업데이트 ==="
gcloud run jobs update ktoa-collector \
  --image "$IMAGE:$TAG" \
  --update-labels "git-sha=$TAG" \
  --region "$REGION"

echo ""
echo "=== 3. mvno-bot 서비스 업데이트 ==="
gcloud run services update mvno-bot \
  --image "$IMAGE:$TAG" \
  --update-labels "git-sha=$TAG" \
  --region "$REGION"

echo ""
echo "✅ 배포 완료 ($IMAGE:$TAG)"
