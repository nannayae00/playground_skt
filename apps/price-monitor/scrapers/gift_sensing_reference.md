# MVNO 사은품 센싱 프로그램 - 개발 참고 문서
> 작성일: 2026-07-09 | 용도: 신규 대화창 컨텍스트 복원용

---

## 1. 프로그램 개요

### 목적
KT·LG 자회사 MVNO의 사은품(프로모션) 총액을 사이트별로 수집·비교하여
**이용자 차별** 소지 감지 및 경쟁사 프로모션 모니터링

### GCP 인프라
| 항목 | 값 |
|------|-----|
| 프로젝트 | mvno-484509 |
| 리전 | asia-northeast3 |
| Cloud Run Job | gift-sensing-job ✅ 운영 중 |
| Cloud Run Service | price-monitor ✅ 운영 중 (버튼 콜백 처리) |
| Firestore 컬렉션 | gift_reports/{date}/providers/{key}, gift_snapshots/{date} |
| 텔레그램 봇 | mvno_AI_monitor (기존 price-monitor 봇 공유) |
| 텔레그램 채널 | -1004446911605 (gift 전용) |

### 스케줄러 ✅ 등록 완료
| 잡명 | 시간 (KST) |
|------|-----------|
| gift-sensing-8h | 매일 08:00 |
| gift-sensing-13h | 매일 13:00 |
| gift-sensing-19h | 매일 19:00 |

---

## 2. 파일 구조

```
~/price-monitor/
├── gift_job.py                    ← v0.7  메인 잡 (모요 수집 + Firestore 저장 + 버튼)
├── gift_callback_handler.py       ← v0.1  버튼 클릭 처리 (price-monitor 서비스에 포함)
├── main.py                        ← v4.19 telegram_webhook에 callback_query 핸들러 추가
├── scrapers/
│   └── gift_moyo_scraper.py       ← v0.8  모요 API 수집
├── core/
│   ├── gift_parser.py             ← v0.3  사은품 금액 환산
│   └── gift_comparator.py         ← v0.4  비교·리포트 포맷
└── deploy.sh                      ← gift-sensing-job 포함 (4단계)
```

---

## 3. 핵심 로직

### 모요 수집 (gift_moyo_scraper.py v0.8)
- **엔드포인트**: `POST https://api.moyoplan.com/core/api/v2/moyo/plan-search/ranking`
- **페이지네이션**: `?page=N&size=100` (쿼리스트링)
- **사은품 필드**: `giftGroupList[].title` + `subTitle`
- **자회사 필터**: `mobilePlanOperatorBrandName` 기준
  - KT엠모바일 → brand명이 정확히 `'KT'` (exact match, 'KT스카이라이프'와 구분)
  - 조기종료: 4개 브랜드 모두 발견 후 3페이지 연속 추가 없으면 종료
- **보너스GB 처리**: 플랜명 첫 번째 GB 우선 사용 (API total은 보너스 포함)

### Firebase 연결 방식 (중요)
```python
# price-monitor 레포에서는 get_db 없음 → FirebaseHandler 사용
from core.firebase_handler import FirebaseHandler as _FH
def get_db():
    return _FH().db
```

### 텔레그램 환경변수
- `gift_job.py` (Job): `TELEGRAM_TOKEN`, `GIFT_CHANNEL_ID`
- `gift_callback_handler.py` (Service): `TELEGRAM_BOT_TOKEN` (main.py와 동일)

### 텔레그램 리포트 구조
**1번 메시지**: LG/KT 자회사 요약 + 사업자별 버튼 4개
```
📊 자회사 사은품 현황 요약 (모요 기준)  📅 2026-07-09  09:00

📌 5GB 이하
  LG (U+유모바일): 42만원
  KT (KT스카이라이프): 8만원
...
[📱 U+유모바일] [📱 LG헬로모바일]
[📱 KT스카이라이프] [📱 KT엠모바일]
```

**버튼 클릭 시**: Firestore `gift_reports/{date}/providers/{key}`에서 상세 조회 후 발송

### 데이터 구간 분류
| 구간 | GB 범위 |
|------|---------|
| 5GB 이하 | 0~5GB |
| 5~9GB | 5.1~9GB |
| 10~15GB | 10~15GB |
| 16~49GB | 16~49GB |
| 50~99GB | 50~99GB |
| 100GB 이상 | 100GB+ (무제한 포함) |

### Firestore 스키마
```
gift_reports/{YYYY-MM-DD}/providers/{provider_key}
  - text: 포맷된 상세 리포트 텍스트
  - provider: 사업자명
  - updated_at: ISO timestamp

gift_snapshots/{YYYY-MM-DD}
  - moyo: {사업자명: {data_key_voice_key: max_value}}
  - updated_at: ISO timestamp
```

---

## 4. 알려진 이슈

| 항목 | 내용 | 우선순위 |
|------|------|---------|
| 중복 버튼 클릭 | 여러 번 누르면 여러 번 발송됨 (방지 로직 미구현) | 낮음 |
| `9GB/기타` | 3Mbps 속도가 통화분으로 오파싱 | 낮음 |
| KT엠모바일 사은품 0건 | 모요개통 전용 요금제는 ranking API giftGroupList 비어있음 | 중간 |
| 유모바일 직영 수집 | 개선 필요 (현재 비활성화) | 중간 |

---

## 5. 다음 작업: 유모바일 이벤트 페이지 센싱

### 대상 URL
- 목록: `https://www.uplusumobile.com/event-benefit/event/ongoing`
- 게시글: `https://www.uplusumobile.com/event-benefit/event/ongoing/10314`

### 특징
- 게시글 내용이 **전부 이미지**로 구성
- Playwright로 이미지 URL 수집 → **Gemini Vision**으로 텍스트 파싱

### 이미지 구조 (2026-07-08 실측)
```
요금제명 (기본GB)
├── 요금제 가입 시: 이마트24 5천원×24개월 (12만원)
├── 이벤트코드 입력시: LG라이프케어몰P 3만원×10개월 (30만원)
└── 최종혜택가: 0원
```

### 개발 계획
1. Playwright로 이벤트 목록 URL 수집
2. 각 게시글 이미지 URL 추출
3. Gemini Vision으로 이미지 → 구조화 텍스트
4. 요금제명/혜택금액/기간 파싱
5. 기존 모요 데이터와 비교 → 차이 리포트

### 참고: 기존 Gemini Vision 활용 코드
`mvno_issue_collector_bot`에 이미 Gemini Vision 구현 되어 있음 → 재활용 가능
