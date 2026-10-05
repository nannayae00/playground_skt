# MVNO GCP 앱 모음

GCP 프로젝트 `mvno-484509`에서 돌아가는 MVNO 업무 자동화 프로그램(Cloud Run 서비스와 작업)의 소스입니다.
2026-10-05에 GCP 빌드 버킷에 남아 있던 배포 소스를 모아 만들었고, 이제 이 저장소가 원본입니다.
Cloud Shell에서 직접 수정하지 말고, 이 저장소를 고친 뒤 여기서 배포합니다.

## 세션 준비 (자동)

`.claude/settings.json`의 SessionStart 훅이 세션 시작 시 아래를 처리합니다.

- 환경변수 `GCP_SA_KEY_B64`를 디코딩해 `/tmp/gcp-sa.json` 생성 (`GOOGLE_APPLICATION_CREDENTIALS`가 이 파일을 가리킴)
- `gcloud`를 서비스 계정 `claude-code-agent@mvno-484509.iam.gserviceaccount.com`으로 로그인하고 기본 프로젝트를 `mvno-484509`로 설정

## 앱과 GCP 리소스 대응표

리전은 별도 표기가 없으면 `asia-northeast3`(서울)입니다.

| 폴더 | Cloud Run 서비스 | Cloud Run 작업 (실행 파일) | 이미지 |
|---|---|---|---|
| `apps/mvno-bot` | `mvno-bot` | `ktoa-collector` (`ktoa_scraper.py`), `cafe-collector` (`cafe_collector_runner.py`), `backfill-pattern` (`backfill_hourly_pattern.py`), `bw-week-updater` | `gcr.io/mvno-484509/mvno-bot` |
| `apps/price-monitor` | `price-monitor` (서울), `price-monitor` (도쿄 `asia-northeast1`) | `moyo-scrape-job` (`scrape_job.py`), `gift-sensing-job` (`gift_job.py`), `dcinside-monitor-job` (`dcinside_job.py`), `ppomppu-monitor-job` (`ppomppu_job.py`), `community-excel-job` (`community_excel_job.py`) | `gcr.io/mvno-484509/price-monitor`, 작업은 `cloud-run-source-deploy/<작업명>` |
| `apps/brand-report` | - | `mvno-brand-report-job` (`run_mvno_brand_job.py`), `mvno-new-data-check-job` (`check_new_data.py`) | `cloud-run-source-deploy/<작업명>` |
| `apps/youtube-analyzer-bot` | `youtube-analyzer-bot` | `youtube-monitor` (`youtube_monitor.py`) | `cloud-run-source-deploy/youtube-analyzer-bot` |
| `apps/calendar-bot` | `calendar-bot` | `test-cal` | `gcr.io/mvno-484509/calendar-bot` |
| `apps/mvno-issue-collector` | `mvno-issue-collector` | - | `cloud-run-source-deploy/mvno-issue-collector` |
| `apps/mvno-dashboard` | `mvno-dashboard` | - | `gcr.io/mvno-484509/mvno-dashboard` |
| `apps/telegram-bot` | `telegram-bot` | - | `cloud-run-source-deploy/telegram-bot` |
| `apps/tg-mail-bridge` | `tg-mail-bridge` | - | `cloud-run-source-deploy/tg-mail-bridge` |
| `apps/moyo-scraper` | `moyo-scraper` | - | `gcr.io/mvno-484509/moyo-scraper` |

`cloud-run-source-deploy/...`는 `asia-northeast3-docker.pkg.dev/mvno-484509/cloud-run-source-deploy/...`의 줄임입니다.

## 배포

폴더에 `deploy.sh`가 있으면 그것을 씁니다 (`mvno-bot`, `price-monitor`, `mvno-dashboard`, `mvno-issue-collector`).
없으면 기본 흐름은 다음과 같습니다.

```bash
cd apps/<폴더>
gcloud builds submit --tag <이미지>:<태그> .
gcloud run jobs update <작업명> --region asia-northeast3 --image <이미지>@<다이제스트>
# 서비스는: gcloud run services update <서비스명> --region asia-northeast3 --image <이미지>@<다이제스트>
```

- 같은 이미지를 여러 서비스·작업이 공유합니다 (위 표 참고). 한 곳만 바꾸려면 별도 태그로 빌드하고 다이제스트로 지정하세요.
- 배포 전에 이전 이미지 다이제스트를 기록해 두면 `--image`로 바로 되돌릴 수 있습니다.

## 비밀값

- 토큰, API 키, 비밀번호는 저장소에 넣지 않습니다. Secret Manager 또는 Cloud Run 환경변수에만 둡니다.
- 가져오면서 코드에 직접 적혀 있던 텔레그램 토큰과 Gemini 키를 환경변수(`TELEGRAM_TOKEN`, `GEMINI_API_KEY`) 참조로 바꿨습니다.
- `price-monitor/deploy.sh`와 `mvno-issue-collector/deploy.sh`는 실행할 때 셸 환경변수 `GEMINI_API_KEY`(필요 시 `TELEGRAM_TOKEN`)가 있어야 합니다.

## 가져올 때 확인된 차이 (2026-10-05)

대응표의 코드는 각 계열에서 가장 최근 빌드 기준입니다. 아래는 지금 운영 중인 버전과 다릅니다.

- `mvno-bot` 서비스: 10/05 03:26 빌드로 실행 중. 저장소에는 그 뒤 `ktoa_scraper.py` 수정(페이지 로드 60초 제한, 장애·복구 알림)이 들어 있고, 이 수정은 `ktoa-collector` 작업에만 배포됨.
- `brand-report`: 운영 작업은 `ktoa_mvno_scraper.py` v1.9. 저장소는 v1.10(자정 무렵 `pageBeforeDay is not defined` 오류 수정)이며 아직 배포 안 됨.
- `price-monitor` 도쿄 서비스는 2026-02 빌드, `ppomppu-monitor-job`은 09/28 빌드로 실행 중 (저장소는 10/01 빌드 기준).
- `youtube-analyzer-bot` 서비스는 2026-05 빌드로 실행 중 (저장소와 `youtube-monitor` 작업은 09/24 빌드 기준).
