# 프로모션 사은품 센싱 프로그램 (gift-sensing)

> v0.1 | 2026-07-07 | price-monitor 확장 모듈

사이트별 동일 요금제의 사은품 총액 차이(이용자 차별 소지)를 자동 감지.
대상: KT엠모바일 / LG헬로모바일 / U+유모바일 (KT·LG 자회사)

## 파일 구조 (기존 price-monitor 레포에 병합)

```
~/price-monitor/
├── gift_job.py                    ← v0.1  메인 잡 (신규)
├── scrapers/
│   ├── gift_moyo_scraper.py       ← v0.1  모요 사은품 (신규)
│   └── umobile_scraper.py         ← v0.1  유모바일 직영 (신규)
└── core/
    ├── gift_parser.py             ← v0.1  금액 환산 파서 (신규)
    └── gift_comparator.py         ← v0.1  cross-match 비교 (신규)
```

## 핵심 확인 사항 (2026-07-07 페이지 분석 결과)

- **유모바일 직영몰**: 서버 렌더링 → 사은품이 카드 텍스트에 그대로 노출.
  🎁 라인(요금제 내장혜택)과 '사은품 혜택' 리스트(이벤트코드 사은품) 분리 수집.
- **모요**: 일반 HTTP 요청 400 차단 → 기존 Playwright 방식 필수.
  사은품 섹션 펼침 셀렉터는 **첫 실행 전 확인 필요** (아래 1단계).

## 파서 검증 완료 (14개 실전 문구)

| 문구 | 환산 결과 |
|------|----------|
| 네이버페이 매달 1.6만원 페이백 (10개월) | 160,000원 exact |
| 매달 hy 금액권 1만원(6만) | 60,000원 exact (괄호 총액 우선) |
| 라이프케어몰 포인트 20만P | 200,000원 point |
| 라이프케어몰포인트 15만원 (1만원X15개월) | 150,000원 exact (X개월 패턴) |
| 기본료의 10% 적립 (24개월) | base_price 기반 exact |
| 매월 빽다방 커피 4잔 (25개월) | 250,000원 estimated (단가표) |
| 데이터 5GB 추가 증정 | unknown → 수동 확인 리포트 |

- 비금전 단가표: `gift_parser.py` 상단 `GIFT_UNIT_PRICES` 수정
- 알림 임계값: `gift_comparator.py` 의 `DIFF_THRESHOLD` (기본 1만원)

## 배포 전 작업 순서

1. **모요 셀렉터 확정** (필수)
   ```bash
   DEBUG_DUMP=1 python gift_job.py
   # → /tmp/dump_moyo_gift.txt 에서 카드 원문 확인 후
   #   gift_moyo_scraper.py 의 TODO 셀렉터 2곳 교체
   #   (카드 컨테이너 + 사은품 펼침 토글)
   ```
2. **유모바일 카드 셀렉터 확인**
   `umobile_scraper.py` 의 후보 셀렉터 4개 중 매칭 실패 시
   body 텍스트 fallback 이 동작하지만, 정확도 위해 확정 권장.
3. **환경변수**: `TELEGRAM_TOKEN` (기존 공유), `GIFT_CHANNEL_ID` (신규 채널)
4. **배포**
   ```bash
   gcloud run jobs deploy gift-sensing-job --source . \
       --region asia-northeast3 --project mvno-484509
   gcloud scheduler jobs create http gift-sensing-daily \
       --schedule="30 8 * * *" --time-zone="Asia/Seoul" \
       --uri="https://asia-northeast3-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/mvno-484509/jobs/gift-sensing-job:run" \
       --oauth-service-account-email=<기존 SA>
   ```

## Firestore 스키마

- `gift_snapshots/{YYYY-MM-DD}`: 일자별 전체 수집 결과 (moyo / umobile_direct)
- `gift_issues/{auto}`: 임계값 초과 이슈 로그 (provider, plan_name, diff, 양쪽 사은품 원문)

## 다음 단계 (v0.2 후보)

- KT엠모바일 / LG헬로모바일 직영몰 스크래퍼 추가 (모요 vs 각 직영 비교 확장)
- 요금제명 fuzzy match (직영몰 표기 ≠ 모요 표기 케이스 대응)
- 이슈 발생 시 스크린샷 첨부 (증빙용)
