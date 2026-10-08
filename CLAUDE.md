# CLAUDE.md

MVNO팀 업무 자동화 앱(GCP `mvno-484509`, Cloud Run)과 그 데이터(Firestore)를 다루는 저장소입니다.
앱별 구조·배포는 `README.md`를 보고, 이 파일은 **데이터 분석**에 필요한 것을 정리합니다.

## 접속과 권한

- 세션 시작 시 `.claude/settings.json` 훅이 환경변수 `GCP_SA_KEY_B64`로 gcloud에 로그인합니다.
  Python에서 Firestore를 읽으려면 환경변수 `GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa.json`도 필요합니다.
- 팀원 분석용 계정은 `team-readonly@mvno-484509.iam.gserviceaccount.com`(Firestore·로그·Cloud Run 읽기 전용)입니다.
  이 계정으로는 쓰기·배포가 안 되는 것이 정상입니다.
- **운영 데이터는 기본적으로 읽기만 합니다.** DB 수정·배포는 사용자가 명시적으로 요청한 경우에만 하고,
  덮어쓰기 전에는 기존 값을 백업합니다. 키·토큰은 출력하지 않습니다.

Firestore 읽기 예시 (DB 이름은 `mvno-data`):

```python
from google.cloud import firestore
db = firestore.Client(project="mvno-484509", database="mvno-data")
d = db.collection("ktoa_daily").document("2026-10-07").get().to_dict()
```

`apps/mvno-bot/forecast_engine.py`의 `_get_db()`를 써도 됩니다(그 경우 `pip install -r apps/mvno-bot/requirements.txt`).
범위 조회는 `where('date','>=',...)`로 하고, 많은 문서를 반복 조회할 때는 한 번 받아 로컬(JSON)에 저장해서 쓰세요.

## 핵심 데이터 (Firestore `mvno-data`)

용어: S/K/L = SKT/KT/LGU+ (MNO), SM/KM/LM = SKT망/KT망/LGU망 알뜰폰(MVNO).
**T Out** = SKT → 알뜰폰 번호이동(`mno_out.S`). SKT망 알뜰폰으로 가는 것도 T Out에 포함됩니다.

### `ktoa_daily/{YYYY-MM-DD}` — KTOA 번호이동 일별 실적 (+ 월마감 예측)

| 필드 | 의미 |
|---|---|
| `mno_out` {S,K,L,계} | MNO → 알뜰폰 이탈 (S = T Out) |
| `mno_out_all` {S,K,L,계} | MNO 전체 이탈 (타 MNO + 알뜰폰) |
| `mno_in` {S,K,L,계} | MNO 유입 |
| `mvno_in` / `mvno_out` {SM,KM,LM,계} | 알뜰폰 유입 / 이탈 |
| `net_change` {SM,KM,LM,계,S,K,L,MNO계} | 순증. MNO 순증 = `mno_in - mno_out_all`, MNO계 = -(MVNO 계) |
| `cum_*` | 위 항목들의 월 누적 (일별 합과 일치) |
| `matrix[도착지][출발지]` | 이동 경로. 키: SKT, KT, LGU, MVNO_SKT, MVNO_KT, MVNO_LGU. **행이 도착지**입니다. 예: SKT→LGU망 알뜰폰 = `matrix['MVNO_LGU']['SKT']` |
| `bw_ai_prev` | AI 영업일수 (예측에 우선 사용) |
| `bw_manual` | 팀 영업일수 (MNP Simulation 엑셀 마감 시트 값, 2023-12~) |
| `fc_*` | 월마감 예측 (아래 '예측 필드') |

영업일수 규칙:
- 예측·분석은 `bw_ai_prev`가 있으면(0.0 포함) 그 값을, 필드가 없을 때만 `bw_manual`을 씁니다. `or`로 폴백하면 0.0이 무시되니 주의.
- 엑셀(bw_manual)은 AI보다 매달 약 1.2~4일 크고, 월초·월말을 크게 잡습니다. 2026-10월은 AI 값이 엑셀(29.0)에 맞춰져 있습니다.
- 달끼리 하루 속도를 비교할 때는 달력 가중(평일 1.0, 토요일·공휴일 0.66, bw=0인 날 0)을 쓰면 bw 입력 방식 차이에 흔들리지 않습니다.
- 2025-04·05·07은 유심 사태로 실적이 비정상이라 백테스트·추세 비교에서 제외합니다.

### `ktoa_hourly/{YYYY-MM-DD}_{HHMM}` — 10분 단위 누적 스냅샷
`mno_out`, `mvno_in` 등 당일 누적값. 정시(:01) 문서에만 그날 일마감 예측 `forecast_*`가 있습니다.

### `ktoa_mvno_brand_in` — 알뜰폰 사업자(브랜드)별 유입
문서 = (date, brand). `inflows`는 출발지별 건수 dict, `network`는 망(`SKT`/`KT`/`LGU`).
**사업자별 T Out** = 브랜드별 `inflows['SKT']` 합계(MNO 브랜드 `SKT`/`KT`/`LGU+` 제외). 일별 합이 `mno_out.S`와 정확히 일치합니다.
사업자 이탈은 `ktoa_mvno_brand_out`, 사업자 목록·망은 `ktoa_mvno_operator_registry`.

### 시장·경쟁 동향
| 컬렉션 | 내용 |
|---|---|
| `gift_snapshots/{date}` | 모요 사은품 금액. `moyo[사업자][요금제키]` (KT엠모바일, U+유모바일, LG헬로모바일, KT스카이라이프) |
| `price_context/{date}` | 요금제 최저가(RS) 망·구간별 요약 텍스트 (모요·알닷·허브) |
| `offline_policy_busung`, `offline_policy_vision` | 오프라인 유통 MNP 수수료 정책. `prices_by_provider[사업자].plans[].domestic_mnp` |
| `ppomppu_monitor/posts/all_posts`, `dcinside_monitor/posts/all_posts` | 커뮤니티 게시글 (title, views, comments, posted_at, url) |
| `community_context/{date}` | 커뮤니티 요약 텍스트 |
| `mvno_issues`, `promotion`, `ktoa_events` | 수동·자동 등록 이슈, 프로모션, 이벤트 |

### 설정
- `ktoa_config/target_goal/monthly/{YYYY-MM}`: 월 목표 `goals.t_out/sm_net/sm_ms`(+ 호환용 `goal`). 텔레그램 메시지가 매 실행마다 읽습니다.

## 예측 필드 (2026-10-07 이후 저장분부터 현재 로직)

| 필드 | 내용 |
|---|---|
| `ktoa_daily.fc_mid/fc_low/fc_high` | SKT OUT 월마감 공식 예측 (텔레그램과 같은 계산). 일마감 20:01·20:25에 저장 |
| `ktoa_daily.fc_mno_out.S` | `fc_mid` 등과 같은 값 |
| `ktoa_daily.fc_mvno_in/fc_mvno_out/fc_mno_in/fc_mno_out_all/fc_net` | 전 항목 월마감 예측 (low/mid/high). '계'는 세부 합 |
| `ktoa_daily.fc_daily` | 그날 일마감 예측치 (확정 실적은 `mno_out.S`) |
| `ktoa_hourly.forecast_*` | 그날 일마감 예측 (정시 문서) |

- 월마감 로직: 직전 2개월의 "같은 날짜 이후 남은 영업일당 속도"를 전월 그대로(50%)와 이번 달 수준 반영(50%)으로 섞어 남은 영업일수에 곱함 (`forecast_engine._get_prev_month_analog_pred`).
- 예외: SM의 `fc_mvno_in/fc_mvno_out/fc_net`(2026-10-08~)은 월말정렬 잔여예측 - 남은 영업일을 월말부터 직전 2개월의 같은 위치 영업일에 맞춰 달력가중으로 적용(`forecast_engine.get_end_aligned_mvno_pred`). IN 예측 - OUT 예측 = 순증감 예측이 정확히 성립하고, low/high는 진행시점별 과거 오차 70% 구간.
- 2026-10-06 이전 `fc_*`는 옛 로직이라 기간 비교 시 주의.
- 상세와 백테스트 결과: 팀 공유 문서 "월마감·일마감 예측 로직 개선 (2026-10-07)".

## 자주 하는 분석

- **T Out 어디로 가나**: `matrix[MVNO_KT|MVNO_LGU|MVNO_SKT]['SKT']`를 월·기간별로 합산, 달력일당으로 비교.
- **사업자별 T Out 변화**: `ktoa_mvno_brand_in`의 `inflows['SKT']`를 같은 기간(예: 매월 1~7일)끼리 비교. 월초 몰림이 있으니 평일끼리도 한 번 더 비교.
- **원인 확인**: 늘어난 사업자에 대해 `gift_snapshots`(사은품), `offline_policy_*`(수수료), 커뮤니티 게시글 제목(특가 출시·마감)을 같은 날짜 범위로 확인.
- **월마감 vs 목표**: `fc_mid`와 `ktoa_config/target_goal`의 `goals.t_out`. 목표까지 필요한 속도 = (목표 - 누적) / 남은 영업일수.

## 결과 공유
- 분석 결과는 숫자와 근거(어느 컬렉션, 어떤 기간)를 함께 제시합니다.
- 공식 실적과 합계가 맞는지(예: 브랜드 합 = `mno_out.S`) 먼저 검증한 뒤 해석합니다.
