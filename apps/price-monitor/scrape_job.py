"""
scrape_job.py  v3.32
수정일시: 2026-10-01

[v3.32 / 2026-10-01]
- 메일 수신자 변경: 김호창(haochang@sk.com) 제외, 박범준(herothen@sktelecom.com) 추가

[v3.31 / 2026-08-25]
- 직전 최저가(Gap) 비교 로직을 하루 3회(08/13/17시) 롤링 방식으로 변경
  · 08시 실행 → 전일 08시와 비교 / 13시 실행 → 당일 08시와 비교 / 17시 실행 → 당일 13시와 비교
  · 기존엔 08시만 전일과 비교하고 13시·17시는 둘 다 "당일 08시"와만 비교(13시 대비 17시 변동을 못 봄) — 버그성 누락 수정
  · _get_run_slot()/PREV_SLOT_MAP 신규 추가, firebase_handler.py v1.11의 get_rs_snapshot_by_slot() 사용
  · 시각(hour) 매칭 대신 저장 시 run_slot 태깅 방식으로 변경 — v3.29부터 3사 통합 후 저장이라 실제 저장시각이
    스케줄 시각보다 40분+ 밀리는데, 기존 hour 매칭 방식은 이 드리프트에 취약했음

[v3.30 / 2026-08-24]
- 메시지1(통합 수집현황) 가독성 개선: 텍스트 나열 → 코드블록 표(구분/총계/RS/RM)로 변경
  · 한글 라벨(일반/자회사/MNO) 폭 문제 대응 위해 _dw()/_wpad() 표시폭 기준 패딩 헬퍼 추가
  · S/K/L망 카운트는 표 하단 요약 한 줄로 유지 (4×3 매트릭스로 확장하면 표가 과도하게 커짐)
- 메시지5 "🆕 단독 요금제" 섹션도 코드블록으로 감싸서 박스 처리 (기존엔 이 섹션만 박스 밖에 있었음)
  · "[알닷]/[허브]" 접두 표기 → "ㅇ 알닷 .../ㅇ 허브 ..." 불릿 형식으로 통일 ("📋 모요 대비 저렴한" 섹션과 톤 맞춤)
- _clean_provider_display() 추가: 사업자명에 부가정보가 괄호로 섞여 들어오는 경우
  (예: 'A모바일(에넥스�텔레콤)', '프리티 (SKT, KT망)') 표시 시 괄호 안 제거 — 망 정보는 별도 network 필드로 이미 표시됨
  · 메시지5 단독요금제 + 모요대비저렴 상세 양쪽에 적용
- (별도 확인 필요/미반영) 알닷 일부 요금제명이 URL인코딩된 이미지 파일명으로 잘못 들어오는 문제
  (예: %ec%97%90%ec%8a%a4%ec%9b%90...) — aldot_scraper.py 파싱 버그로 추정, 해당 파일 확인 후 별도 수정 예정

[v3.29 / 2026-08-24]
- 텔레그램 발송 구조 전면 개편: 소스별 개별 발송 → 3사(모요+알닷+허브) 모두 수집 완료 후 통합 5개 메시지 일괄 발송
  · scrape_type='all' 경로만 해당. scrape_type='aldot'('알닷 확인' 수동 명령)은 기존 레거시 단일메시지 플로우 그대로 유지
  · 메시지1: 통합 수집현황 (3사 각각 총량/RS·RM, S·K·L망별 카운트, 일반/자회사/MNO 분류) — build_source_status_block()
  · 메시지2: 일반사업자 RS 최저가 — 3사 병합 최저값(소스 라벨 없음), 현재/직전/Gap 구조 유지
  · 메시지3: 자회사 RS 최저가 — 3사 병합 (기존엔 모요 단독 + 스냅샷 비교 없음 → 이번에 직전/Gap 신규 추가)
  · 메시지4: MNO 최저가 — 3사 병합 (기존엔 모요 단독 + 현재값만 → 이번에 직전/Gap 신규 추가)
  · 메시지5: 알닷+허브 단독요금제 + 모요 대비 저렴한 요금제 상세 통합 (전일 대비 변동 섹션은 제거 결정)
- get_provider_type() 기반 분류를 모요뿐 아니라 알닷/허브 plans에도 동일 적용 → split_by_provider_type() 헬퍼 추가
- build_rs_comparison()에 segments 파라미터 추가 (기본 GUIDE_SEGMENTS) → MNO 전용 구간도 동일 함수로 재사용
- MNO 전용 구간 로직(_mno_segment_a, MNO_SEGMENTS)을 main() 내부 → 모듈 최상단으로 이동 (get_mno_segment_min_prices())
- firebase_handler.py v1.10 연동: RS 스냅샷 함수에 snap_type('general'/'sub'/'mno') 파라미터 추가
  · 자회사/MNO도 병합값 기준 스냅샷 저장·조회 가능해짐
- send_merged() 추가: 메시지1~5 공용 발송 함수 (clean_for_markdown 적용)
- send_excel_mail() 라벨/구성 변경: [수집현황/일반사업자/자회사/MNO/단독·저렴상세] 5개로 대응
- save_price_context() 라벨 텍스트 "(모요 기준)" → "(3사 통합 기준)" (curr_rs가 병합값으로 바뀜에 따른 표기 수정)
- 기존 build_aldot_comparison() / build_mvnohub_comparison() / send_aldot() / send_mvnohub()는 'aldot' 단독수집
  경로 하위호환용으로 유지 (삭제하지 않음)

[v3.28 / 2026-08-06]
- MIN_PRICE 3,000원 조건 제거 (comparator v2.2 연동)
  · 1,000원 이하 이벤트 요금제도 RS 최저가 집계 포함
- 사업자구분 필드 추가 (엑셀 컬럼)
  · 일반 / 자회사S(텔링크) / 자회사K(엠모바일,스카이라이프) / 자회사L(유모바일,헬로)
  · MNO_SKT(SKT,AIR) / MNO_KT(KT,요고) / MNO_LG(LGU+,너겟)
- 모요 메시지 3분리: 일반사업자 / 자회사 / MNO 별도 발송
- 메일 본문에 자회사/MNO 메시지도 포함 (send_excel_mail body_parts 5개로 확장)
- 메인 RS 최저가 비교를 일반사업자 기준으로 변경
  · 제목: "📶 RS 최저가 비교" → "📶 RS 최저가 비교(일반사업자)"
  · curr_rs 계산을 general_plans 기준으로 산출 (스냅샷 저장도 일반사업자 기준)
- 자회사/MNO 메시지에 RS/RM 개수 분리 및 대상 사업자명 라인 추가
- MNO 메시지: RS 단독 → RS+RM 통합 최저가로 변경
  · MNO는 리베이트 구조가 아니라 RS/RM 구분 의미가 약함
  · MNO 전용 구간 도입 (~10GB/10~20GB/20~50GB/50~100GB/100GB+/무제한)
    기존 RS 구간(7G+~100G+)과 별개 — 일반/자회사 메시지에는 영향 없음
  · 대상 표시명 축약: air by SK telecom → AIR

[v3.27 / 2026-07-20]

[v3.27 / 2026-07-20]
- 메일 수신자 도메인 변경: jangga@sktelecom.com → jangga@sk.com
  · 550 Mailbox does not exist 오류 해결
- 메일 수신자 추가: haochang@sk.com

[v3.26 / 2026-07-14]
- send_excel_mail() 텔레그램 로그 알림 추가
  · 메일 발송 성공/실패 여부를 CHAT_LOG 방에 send_log()로 알림

[v3.25 / 2026-07-09]
- 엑셀 파일 메일 자동 발송 추가
  · 텔레그램 엑셀 발송과 동시에 Gmail → chris.mclee@sk.com 발송
  · send_excel_mail() 함수 추가 (daily_mailer.py SMTP 로직 재활용)
  · 환경변수: GMAIL_ADDRESS, GMAIL_APP_PASSWORD, MAIL_TO
  · 메일 발송 실패 시 텔레그램 알림만 발송하고 계속 진행

[v3.24 / 2026-06-07]
- provider_map.py 연동: 텔레그램 메시지 사업자명 약칭 적용
  · build_aldot_comparison / build_mvnohub_comparison 6곳 shorten() 적용
  · save_price_context(AI 컨텍스트)는 원문 유지

[v3.23 / 2026-05-20]
- price_context 빌더 추가: save_price_context()
  · auto 수집 완료 후 Firestore price_context/{YYYY-MM-DD} 저장
  · SUMMARY(ALERT/NORMAL) + RS최저가 현황 + 전일 대비 변동 + 단독RS 요약 포함
  · 다른 AI 시스템이 읽기 좋은 구조화 텍스트 형식

[v3.22 / 2026-04-23]
- 알뜰폰허브(MvnohubScraper) 수집 통합
  · 모요 → 알닷 → 알뜰폰허브 순차 수집
  · build_mvnohub_comparison(): 모요 vs 알뜰폰허브 RS 3사 비교 + 단독RS + 변동
  · send_mvnohub(): clean_for_markdown 적용 Markdown 발송
  · build_excel(): mvnohub_plans 파라미터 추가 + Sheet6 알뜰폰허브 시트
  · Firebase 저장: 'mvnohub' source_type으로 저장
  · 엑셀 파일명: moyo_aldot_mvnohub_{시간}.xlsx
  · SCRAPE_TYPE='aldot' 시 알뜰폰허브 수집 생략

[v3.21 / 2026-04-09]
- 알닷 상세 블록 헤더 추가 (📋 모요 대비 저렴한 알닷 상세)
- manual 수집 시 prev_aldot 조회 개선: 당일 07:30 → 최근 auto → 이전 데이터 순

[v3.20 / 2026-04-09]
- 알닷 메시지 parse_mode=None → Markdown 복원 (코드블록 렌더링 정상화)
- clean_for_markdown() 추가: 코드블록 밖 텍스트 특수문자 자동 제거
  어떤 요금제명/사업자명이 들어와도 Markdown 파싱 에러 방지 보장
- send_aldot() 개선: clean_for_markdown 적용 후 단일 메시지 발송
- 변동/삭제 섹션 요금제명 특수문자(_,*,[,]) 제거
- SCRAPE_TYPE 환경변수 추가: 'all'(모요+알닷) | 'aldot'(알닷만)
  · aldot 전용 수집 시 모요는 Firebase 최신 데이터 로드
  · aldot 전용 수집 시 모요 메시지/엑셀 발송 생략
  · main.py '알닷 확인' 명령어와 연동

[v3.0 / 2026-03-14]
- AldotScraper 통합: 모요 수집 후 알닷 순차 수집
- 발송 순서 변경: 모요 메시지 → 알닷 메시지 → 엑셀 파일
- build_aldot_comparison() 신규 추가
  · 💰 모요보다 저렴한 RS 요금제 (동일 data+network 기준, 차액 표시)
  · 🆕 알닷 단독 RS 요금제 (모요 미등록)
  · 🔄 전일 대비 알닷 변동 (신규/단종/가격변동)
- _write_sheet() 헬퍼 추가: 모요/알닷 개별 시트 공통 작성 로직
- build_excel() 시그니처 변경: (plans) → (moyo_plans, aldot_plans, path)
- 엑셀 시트 구성 변경:
  · Sheet1: 요금제 전체 (모요+알닷 합산)
  · Sheet2: 모요
  · Sheet3: 알닷
  · Sheet4: RS 망별 최저가(모요)  ← 시트명 변경
  · Sheet5: RM Top5(모요)         ← 시트명 변경
- 알닷 수집 실패 시 모요 결과는 정상 발송, 엑셀은 알닷 빈 리스트로 생성
- 시작 메시지 소요시간 안내 업데이트 (약 30분)

[v3.1 / 2026-03-14]
- 메시지 발송 순서 변경: 모요+알닷 수집 완료 후 일괄 발송
  모요 수집 → 알닷 수집 → 모요 메시지 → 알닷 메시지 → 엑셀
- 중복 # ── 메인 헤더 제거
- aldot_plans 초기값 [] 명시 (알닷 실패 시 엑셀 정상 생성 보장)

[v3.2 / 2026-03-14]
- 알닷 메시지 미발송 버그 수정: if aldot_msg → 항상 발송
- build_aldot_comparison 예외 시 기본 메시지 발송
- 알닷 수집 실패 시에도 실패 메시지 결과방 발송

[v3.3 / 2026-03-14]
- send_to() 빈 문자열 가드 추가 (텔레그램 400 에러 방지)
- aldot_msg 빈 문자열 fallback 추가 (최소 수집 완료 메시지 보장)

[v3.4 / 2026-03-14]
- build_aldot_comparison 상세 디버그 로그 추가 (원인 추적용)
- 예외 발생 시 전체 traceback 로그방 발송

[v3.5 / 2026-03-15]
- 알닷 메시지 parse_mode=None으로 변경 (Markdown 특수문자 파싱 에러 방지)
  요금제명/사업자명에 _, *, [ 등 포함 시 텔레그램 400 에러로 묵살되는 문제 수정

[v3.6 / 2026-03-15]
- build_aldot_comparison 메시지 포맷 개편
  · 개별 나열 제거 → 구간별 테이블로 압축
  · 3,000원 미만 이상 데이터 필터 추가
  · 단독 RS 요금제 5개로 축소

[v3.7 / 2026-03-15]
- build_aldot_comparison: 구간별 테이블 하단에 상세 요금제 목록 추가
  구간당 최대 3개, 모요 최저가 미만 요금제만 표시

[v3.8 / 2026-03-15]
- 구간별 테이블 차액 열 제거 (정렬 개선)

[v3.9 / 2026-03-15]
- 알닷 plans에 tag_plans_with_lowest() 적용 → segment 필드 생성
  (미적용 시 구간별 테이블 비교 불가)

[v3.10 / 2026-03-15]
- 알닷 메시지 표: 전체 구간 표시 (알닷 저렴 여부와 무관)
- * 표시: 알닷이 모요보다 저렴한 구간
- 상세 요금제 나열: 알닷이 더 싼 구간만, 구간당 최저가 3개

[v3.11 / 2026-03-15]
- 알닷 엑셀 시트 전용 컬럼 2개 추가
  · 모요대비저렴: 동일 구간+망 모요 최저가보다 싸면 ★
  · 알닷최저가: 해당 구간+망 알닷 내 최저가면 ★

[v3.12 / 2026-03-17]
- 모요/전체 시트 컬럼 순서 변경: RS여부/RS최저가/RM최저가 → 맨 뒤로 이동
- 통화 값 앞에 "통화 " 접두어 추가 (예: 무제한 → 통화 무제한)
- 문자 값 앞에 "문자 " 접두어 추가 (예: 무제한 → 문자 무제한)
- 사용망 값 뒤에 "망" 추가 (예: KT → KT망, 공백 없음)

[v3.13 / 2026-03-17]
- RS 최저가 산출 시 프리티 하나은행 요금제 제외 (계좌 가입 조건)
  filter_for_rs() 함수 추가

[v3.14 / 2026-03-17]
- RS최저가 태깅(is_lowest_rs)도 프리티 하나은행 제외 후 산출
  제외 요금제는 is_lowest_rs=False 강제

[v3.15 / 2026-03-17]
- build_rs_comparison() 신규: 현재/직전/Gap 3단 비교 메시지 (📶 RS 최저가 비교)
- save_rs_snapshot() 호출: RS 최저가 스냅샷 Firebase 저장
- 가이드이하 섹션 제거, build_summary_table → build_rs_comparison 대체

[v3.16 / 2026-03-17]
- RS 스냅샷 저장: auto 수집일 때만 저장 (manual은 저장 생략)
- manual 수집: 가장 최근 auto 스냅샷과 비교

[v3.17 / 2026-03-17]
- 할인개월 빈칸 → 0으로 표기

[v3.18 / 2026-03-17]
- 알닷 RS 분류 정확도 개선 (base_scraper.py v1.2 data+voice 기준 연동)
- 망 표기 공백 제거: KT 망 → KT망

[v3.19 / 2026-03-24]
- 알닷 표 포맷 개선: 사업자명 제거, 숫자만 코드블록 정렬 (모요 표와 동일)
- 상세 목록 코드블록으로 정렬
- comparator.py v2.1 연동: 15G+300 오분류 수정 (31GB/50GB → 100G+)

[v3.2 / 2026-03-14]
- aldot_msg 디버그 로그 추가 (메시지 미발송 원인 파악용)

[v2.15 변경사항]
- 코드블록 내 * 이스케이프 제거 (\* 출력 문제 해결)
- 엑셀 Sheet1 이름 → "요금제 전체"

[v2.14]
- Markdown 모드에서 * 이스케이프 처리 (볼드 처리 방지)

[v2.13]
- send_to: parse_mode="Markdown" 기본값 추가 → 코드블록 정상 렌더링

[v2.12]
- build_rs_analysis Top5: ◎ 요금제명 / 가격, 가입자수 형식으로 통일

[v2.11]
- build_popularity_table: RS/RM 태그, 가격, ◎ 형식, 헤더 → 가입수 Top5(모요)
- build_summary_table: 구간명 정렬 개선 (│ 제거, 9칸 폭)
- EXCEL_COLS: 가이드이하 필드 추가
- build_excel: 가이드이하 계산 + RS 망별 최저가 시트 + RM Top5 시트 추가
- send_result/send_telegram_file: 수동 수집 시 항상 CHAT_LOG 전송 보장

[v2.10]
- build_rm_analysis() 추가: RM 가격대별 최대 데이터 + 가입수 Top 5 + 전주 대비 증감

[v2.9]
- build_guide_comparison: ㅇ→📊, * →◎, 요금제 들여쓰기 (   - 형식)
- build_guide_comparison: guide_date 필드 우선 사용

[v2.8]
- build_rs_analysis: data_gb float 타입 처리 (7.0 → 7 변환 오류 수정)

[v2.7]
- build_popularity_table() 추가: 3사별 가입자수 Top 5
- build_rs_analysis() 추가: RS 가격대별 최대 데이터 + 가입수 Top 5

[v2.6]
- build_summary_table: 🔥 → * 변경 (줄바꿈 문제 해결), 3사 동일 최저가면 미표기
- 직전 수집 대비 변경 사항 블록 삭제
- 엑셀 전송: 수동/자동 동일하게 (기존 auto만 → 항상)

[v2.5]
- 가이드 이하 조건 수정: 이하(≤) → 미만(<), 없는 구간 생략

[v2.4]
- 가이드 이하 요금제 표시 기능 추가 (build_guide_comparison)

[v2.3]
- 비교 로직 시간대별 분리

[v2.2]
- 채팅방별 발송 분리

[v2.1]
- source_type: auto / manual
"""

import os
import re
import sys
from datetime import datetime
import pytz
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from scrapers.moyo_scraper import MoyoScraper
from scrapers.aldot_scraper import AldotScraper
from scrapers.mvnohub_scraper import MvnohubScraper
from core.firebase_handler import FirebaseHandler
from core.comparator import Comparator
from provider_map import shorten


# ── 사업자 구분 매핑 ─────────────────────────────────────────────────────────
PROVIDER_TYPE_MAP = {
    # ── 자회사 S (SKT 계열) ──
    '에스케이텔링크':    '자회사S',
    'SK7모바일':         '자회사S',
    # ── 자회사 K (KT 계열) ──
    'KT엠모바일':        '자회사K',
    'KT스카이라이프':    '자회사K',
    '케이티스카이라이프': '자회사K',
    # ── 자회사 L (LG 계열) ──
    'U+유모바일':        '자회사L',
    'LG헬로모바일':      '자회사L',
    # ── MNO SKT ──
    'SKT':               'MNO_SKT',
    'air by SK telecom': 'MNO_SKT',
    # ── MNO KT ──
    'KT':                'MNO_KT',
    '요고':              'MNO_KT',
    # ── MNO LG ──
    'LG U+':             'MNO_LG',
    '너겟':              'MNO_LG',
}

def get_provider_type(provider: str) -> str:
    return PROVIDER_TYPE_MAP.get(provider, '일반')


def split_by_provider_type(plans):
    """plans 리스트를 일반/자회사/MNO로 분류. 소스(모요/알닷/허브) 무관하게 동일 로직 사용."""
    general = [p for p in plans if get_provider_type(p.get('provider', '')) == '일반']
    sub     = [p for p in plans if get_provider_type(p.get('provider', '')).startswith('자회사')]
    mno     = [p for p in plans if get_provider_type(p.get('provider', '')).startswith('MNO')]
    return general, sub, mno


# ── 하루 3회 수집 스케줄(08/13/17시) — 롤링 비교 슬롯 ────────────────────────
# 08시→전일 08시 비교, 13시→당일 08시 비교, 17시→당일 13시 비교
PREV_SLOT_MAP = {
    'morning':   ('morning',   1),  # 08시 실행 → 전일 08시와 비교
    'afternoon': ('morning',   0),  # 13시 실행 → 당일 08시와 비교
    'evening':   ('afternoon', 0),  # 17시 실행 → 당일 13시와 비교
}

def _get_run_slot(hour):
    """현재 시각을 08/13/17시 중 어느 회차 실행인지로 분류. (임계값: <10→08시대, <15→13시대, 그 외→17시대)"""
    if hour < 10:
        return 'morning'
    elif hour < 15:
        return 'afternoon'
    else:
        return 'evening'


# ── MNO 전용 구간(A안) ────────────────────────────────────────────────────────
MNO_SEGMENTS = ['~10GB', '10~20GB', '20~50GB', '50~100GB', '100GB+', '무제한']

def _mno_segment_a(data_gb):
    """MNO 전용 구간 분류 (A안): ~10GB / 10~20GB / 20~50GB / 50~100GB / 100GB+ / 무제한"""
    if data_gb >= 9999: return '무제한'
    if data_gb < 10:    return '~10GB'
    if data_gb < 20:    return '10~20GB'
    if data_gb < 50:    return '20~50GB'
    if data_gb < 100:   return '50~100GB'
    return '100GB+'

def get_mno_segment_min_prices(plans):
    """MNO 전용 구간 기준 망별 최저가. RS+RM 통합(필터 없음) — MNO는 리베이트 구조가 아님."""
    NETS  = ['SKT', 'KT', 'LGU+']
    table = {seg: {n: 0 for n in NETS} for seg in MNO_SEGMENTS}
    for p in plans:
        seg = _mno_segment_a(p.get('data_gb', 0))
        net = p.get('network', '')
        fp  = p.get('final_price', 0)
        if net not in NETS or fp <= 0:
            continue
        cur = table[seg][net]
        if cur == 0 or fp < cur:
            table[seg][net] = fp
    return table


# ── 요약 테이블 ───────────────────────────────────────────────────────────────


# RS 최저가 산출 시 제외 요금제 (계좌 가입 조건 있음)
RS_EXCLUDE = [
    {'provider': '프리티', 'name_keyword': '하나은행'},
]

def filter_for_rs(plans):
    """RS 최저가 산출용 - 특정 요금제 제외"""
    result = []
    for p in plans:
        exclude = False
        for ex in RS_EXCLUDE:
            if (p.get('provider','') == ex['provider'] and
                ex['name_keyword'] in p.get('name','')):
                exclude = True
                break
        if not exclude:
            result.append(p)
    return result

def save_price_context(curr_rs, prev_snapshot, plans, aldot_plans, mvnohub_plans):
    """
    요금제 price_context 생성 → Firestore price_context/{YYYY-MM-DD} 저장
    auto 수집 완료 후 호출. 다른 AI 시스템이 읽기 좋은 구조화 텍스트 형식.

    저장 구조:
      price_context/{YYYY-MM-DD} → {date, text, saved_at, version}
    """
    try:
        from google.cloud import firestore as _fs
        import firebase_admin
        from firebase_admin import credentials as _cred

        if not firebase_admin._apps:
            firebase_admin.initialize_app(_cred.ApplicationDefault())
        _db = _fs.Client(project='mvno-484509', database='mvno-data')

        KST       = pytz.timezone('Asia/Seoul')
        now_kst   = datetime.now(KST)
        date_str  = now_kst.strftime('%Y-%m-%d')
        checked_at= now_kst.strftime('%m/%d %H:%M')

        NETS     = ['SKT', 'KT', 'LGU+']
        SEGMENTS = FirebaseHandler.GUIDE_SEGMENTS  # ['7G+','10G+','11G+','15G+100','15G+300','100G+']

        # ── 전일 대비 변동 계산 ─────────────────────────────────
        prev_rs = prev_snapshot.get('rs_min', {}) if prev_snapshot else {}

        changes = []  # [(seg, net, curr_price, prev_price, diff)]
        for seg in SEGMENTS:
            for net in NETS:
                cp = (curr_rs.get(seg) or {}).get(net, 0)
                pp = (prev_rs.get(seg)  or {}).get(net, 0)
                if cp and pp and cp != pp:
                    changes.append((seg, net, cp, pp, cp - pp))

        # ── SUMMARY 판별 ────────────────────────────────────────
        alerts  = []
        normals = []

        if changes:
            downs = [(s, n, c, p, d) for s, n, c, p, d in changes if d < 0]
            ups   = [(s, n, c, p, d) for s, n, c, p, d in changes if d > 0]
            if downs:
                alerts.append(
                    f"RS 최저가 인하 {len(downs)}건 — "
                    + ', '.join(f"{s} {n} {abs(d):,}원↓" for s, n, c, p, d in downs[:3])
                )
            if ups:
                alerts.append(
                    f"RS 최저가 인상 {len(ups)}건 — "
                    + ', '.join(f"{s} {n} {abs(d):,}원↑" for s, n, c, p, d in ups[:3])
                )
        else:
            normals.append("전일 대비 RS 최저가 변동 없음")

        # 단독 RS (모요에만 있거나 알닷에만 있는 구간·망)
        moyo_rs_segs  = set()
        aldot_rs_segs = set()
        for p in plans:
            if p.get('is_rs') and p.get('is_lowest_rs'):
                moyo_rs_segs.add((p.get('segment',''), p.get('network','')))
        for p in aldot_plans:
            if p.get('is_rs') and p.get('is_lowest_rs'):
                aldot_rs_segs.add((p.get('segment',''), p.get('network','')))
        moyo_only = moyo_rs_segs - aldot_rs_segs
        aldot_only = aldot_rs_segs - moyo_rs_segs
        if moyo_only:
            normals.append(f"모요 단독 RS 구간·망: {len(moyo_only)}개")
        if aldot_only:
            alerts.append(f"알닷 단독 RS (모요 미등록): {len(aldot_only)}개")

        # ── 텍스트 조립 ─────────────────────────────────────────
        L = []
        SEP = '━' * 28

        L.append(f"[MVNO 요금제 AI컨텍스트 | {date_str} | {checked_at} 기준]")
        L.append("※ 모든 수치는 수집 확정값. 재계산 금지. 해석만 할 것.")
        L.append("")
        L.append(SEP)
        L.append("■ SUMMARY (AI 해석 우선순위)")
        L.append(SEP)
        for a in alerts:
            L.append(f"  ⚠️ ALERT: {a}")
        for n in normals:
            L.append(f"  ✅ NORMAL: {n}")
        L.append("※ 상세 수치는 하단 각 섹션 참조")

        # ── 섹션 1: RS 최저가 현황 ──────────────────────────────
        L.append(f"\n{SEP}")
        L.append("■ 1. RS 최저가 현황 (모요+알닷+허브 3사 통합 기준)")
        L.append(SEP)
        L.append(f"{'구간':<10} {'SKT':>8} {'KT':>8} {'LGU+':>8}")
        L.append("─" * 38)
        for seg in SEGMENTS:
            nets = curr_rs.get(seg, {})
            row  = [nets.get(n, 0) for n in NETS]
            min_v = min((v for v in row if v > 0), default=0)
            cells = []
            for v in row:
                if v == 0:
                    cells.append("     -")
                elif v == min_v:
                    cells.append(f"{v:>7,}*")  # * = 구간 최저
                else:
                    cells.append(f"{v:>8,}")
            L.append(f"{seg:<10} {cells[0]} {cells[1]} {cells[2]}")
        L.append("* 구간 최저가")

        # ── 섹션 2: 전일 대비 변동 ──────────────────────────────
        L.append(f"\n{SEP}")
        L.append("■ 2. 전일 대비 RS 최저가 변동")
        L.append(SEP)
        if changes:
            L.append(f"{'구간':<10} {'망':<6} {'현재':>8} {'전일':>8} {'변동':>8}")
            L.append("─" * 44)
            for seg, net, cp, pp, diff in changes:
                arrow = f"↓{abs(diff):,}" if diff < 0 else f"↑{diff:,}"
                L.append(f"{seg:<10} {net:<6} {cp:>8,} {pp:>8,} {arrow:>8}")
        else:
            L.append("변동 없음")

        # ── 섹션 3: 수집 현황 ───────────────────────────────────
        L.append(f"\n{SEP}")
        L.append("■ 3. 수집 현황")
        L.append(SEP)
        moyo_rs  = sum(1 for p in plans         if p.get('is_rs'))
        aldot_rs = sum(1 for p in aldot_plans   if p.get('is_rs'))
        hub_rs   = sum(1 for p in mvnohub_plans if p.get('is_rs'))
        L.append(f"모요:       총 {len(plans):,}개 (RS {moyo_rs}개 / RM {len(plans)-moyo_rs}개)")
        L.append(f"알닷:       총 {len(aldot_plans):,}개 (RS {aldot_rs}개 / RM {len(aldot_plans)-aldot_rs}개)")
        L.append(f"알뜰폰허브: 총 {len(mvnohub_plans):,}개 (RS {hub_rs}개 / RM {len(mvnohub_plans)-hub_rs}개)")

        # ── 섹션 4: 알닷 단독 RS (모요 미등록) ─────────────────
        if aldot_only:
            L.append(f"\n{SEP}")
            L.append("■ 4. 알닷 단독 RS (모요 미등록 구간·망)")
            L.append(SEP)
            for p in aldot_plans:
                if p.get('is_rs') and p.get('is_lowest_rs'):
                    seg = p.get('segment', '')
                    net = p.get('network', '')
                    if (seg, net) in aldot_only:
                        L.append(
                            f"  {p.get('provider','')} {p.get('name','')} "
                            f"| {net} | {p.get('data','')} | {p.get('final_price',0):,}원"
                        )

        text = '\n'.join(L)

        # ── Firestore 저장 ────────────────────────────────────────
        _db.collection('price_context').document(date_str).set({
            'date'    : date_str,
            'text'    : text,
            'saved_at': now_kst,
            'version' : 'v1.0',
        })
        print(f"✅ price_context 저장 완료: {date_str} ({len(text):,}자)")

    except Exception as e:
        import traceback
        print(f"⚠️ price_context 저장 실패: {e}\n{traceback.format_exc()[-300:]}")


def build_rs_comparison(curr_rs, prev_snapshot, title="📶 RS 최저가 비교", segments=None):
    """
    RS 최저가 비교 메시지 생성.

    curr_rs:       {seg: {net: price}} - 현재 최저가
    prev_snapshot: {'checked_at': datetime, 'rs_min': {...}} - 직전 스냅샷
    title:         메시지 상단 제목 (기본: "📶 RS 최저가 비교")
    segments:      구간 리스트 (기본: GUIDE_SEGMENTS). MNO 등 전용 구간 사용 시 지정
    """
    NETS     = ['SKT', 'KT', 'LGU+']
    SEGMENTS = segments or FirebaseHandler.GUIDE_SEGMENTS  # ['7G+', '10G+', '11G+', '15G+100', '15G+300', '100G+']
    korea_now = datetime.now(KOREA_TZ)

    def fmt_price(v, is_min):
        if not v: return '      -'
        s = f'{v:,}'
        return (s + '*').rjust(8) if is_min else s.rjust(7)

    def make_table(rs_data, label):
        msg  = f"📊 {label}\n```\n"
        msg += f"{'구간':<9}{'SKT':>8} {'KT':>8} {'LGU+':>8}\n"
        msg += "─" * 38 + "\n"
        for seg in SEGMENTS:
            nets = rs_data.get(seg, {})
            prices = {n: nets.get(n, 0) for n in NETS}
            min_val   = min((v for v in prices.values() if v > 0), default=0)
            min_count = sum(1 for v in prices.values() if v == min_val and v > 0)
            cells = [fmt_price(prices[n], prices[n] == min_val and min_val > 0 and min_count < 3)
                     for n in NETS]
            msg += f"{seg:<9}{cells[0]} {cells[1]} {cells[2]}\n"
        msg += "* 구간최저(2사이하)\n```"
        return msg

    def make_gap_table(curr, prev_rs):
        """변동분만 표시, 없으면 '변경 사항 없음'"""
        changes = []
        for seg in SEGMENTS:
            curr_nets = curr.get(seg, {})
            prev_nets = prev_rs.get(seg, {})
            for net in NETS:
                cp = curr_nets.get(net, 0)
                pp = prev_nets.get(net, 0)
                if cp and pp and cp != pp:
                    changes.append((seg, net, cp, pp, cp - pp))

        if not changes:
            return "📊 Gap (현재 vs 직전)\n변경 사항 없음"

        msg  = "📊 Gap (현재 vs 직전)\n```\n"
        msg += f"{'구간':<9}{'망':<6} {'현재':>8} {'직전':>8} {'변동':>8}\n"
        msg += "─" * 44 + "\n"
        for seg, net, cp, pp, diff in changes:
            arrow = f"↓{abs(diff):,}" if diff < 0 else f"↑{diff:,}"
            msg += f"{seg:<9}{net:<6} {cp:>8,} {pp:>8,} {arrow:>8}\n"
        msg += "```"
        return msg

    # 현재 수집 시각 레이블
    curr_label = f"현재 최저가 ({korea_now.strftime('%m/%d %H:%M')})"

    # 직전 스냅샷 레이블
    if prev_snapshot:
        prev_at  = prev_snapshot.get('checked_at')
        prev_rs  = prev_snapshot.get('rs_min', {})
        if prev_at and hasattr(prev_at, 'astimezone'):
            prev_at_kst = prev_at.astimezone(KOREA_TZ)
            prev_label  = f"직전 최저가 ({prev_at_kst.strftime('%m/%d %H:%M')})"
        else:
            prev_label = "직전 최저가"
    else:
        prev_rs    = {}
        prev_label = "직전 최저가 (데이터 없음)"

    lines = [
        title,
        "",
        make_table(curr_rs, curr_label),
        "",
        make_table(prev_rs, prev_label) if prev_rs else f"📊 {prev_label}",
        "",
        make_gap_table(curr_rs, prev_rs),
    ]
    return "\n".join(lines)


# ── [v3.29] 3사 통합 발송용 헬퍼 ──────────────────────────────────────────────

def _dw(s):
    """표시 폭 계산 (한글/이모지 등 wide 문자는 2칸, 나머지는 1칸) — 코드블록 표 정렬용"""
    return sum(2 if ord(ch) >= 0x1100 else 1 for ch in str(s))

def _wpad(s, width, align='left'):
    """표시 폭 기준 패딩 (str.ljust/rjust는 한글 폭을 못 맞춰서 별도 구현)"""
    s = str(s)
    pad = max(0, width - _dw(s))
    return (s + ' ' * pad) if align == 'left' else (' ' * pad + s)


def _clean_provider_display(name):
    """
    단독/저렴상세 표시용 사업자명 정리.
    스크래퍼가 사업자명에 부가정보(사업자 원문명, 사용망 등)를 괄호로 같이 넣어오는 경우가 있어
    (예: 'A모바일(에넥스텔레콤)', '프리티 (SKT, KT망)') — 망 정보는 별도 network 필드로 이미 표시되므로 괄호 안은 제거.
    """
    return re.sub(r'\s*\([^)]*\)', '', str(name)).strip()


def build_source_status_block(title_emoji_label, plans, checked_at):
    """
    메시지1(통합 수집현황)의 소스 1개 블록.
    총량/RS·RM, S/K/L망별 카운트, 일반/자회사/MNO 분류를 코드블록 표로 표시.
    """
    general, sub, mno = split_by_provider_type(plans)

    def _row(label, plist):
        r = sum(1 for p in plist if p.get('is_rs'))
        return label, len(plist), r, len(plist) - r

    rows = [
        _row('전체', plans),
        _row('일반', general),
        _row('자회사', sub),
        _row('MNO', mno),
    ]

    s_cnt = sum(1 for p in plans if p.get('network') == 'SKT')
    k_cnt = sum(1 for p in plans if p.get('network') == 'KT')
    l_cnt = sum(1 for p in plans if p.get('network') == 'LGU+')

    lines = [f"{title_emoji_label} ({checked_at})", "```"]
    lines.append(f"{_wpad('구분', 8)}{_wpad('총계', 7, 'right')}{_wpad('RS', 6, 'right')}{_wpad('RM', 6, 'right')}")
    lines.append("─" * 27)
    for label, tot, rs, rm in rows:
        lines.append(f"{_wpad(label, 8)}{tot:>7,}{rs:>6,}{rm:>6,}")
    lines.append("─" * 27)
    lines.append(f"S망 {s_cnt} · K망 {k_cnt} · L망 {l_cnt}")
    lines.append("```")
    return "\n".join(lines)


def _only_source_plans(source_plans, moyo_plans, limit=5):
    """moyo_plans에 없는 (data, network) 조합을 가진 source_plans의 단독 RS 요금제."""
    moyo_keys = {(p.get('data', ''), p.get('network', '')) for p in moyo_plans}
    only, seen = [], set()
    for p in source_plans:
        if not p.get('is_rs'): continue
        if p.get('final_price', 0) <= 0: continue
        key = (p.get('data', ''), p.get('network', ''))
        if key not in moyo_keys and key not in seen:
            only.append(p)
            seen.add(key)
    only.sort(key=lambda x: x.get('final_price', 0))
    return only


def _cheaper_detail_vs_moyo(source_plans, moyo_plans, network_filter=None):
    """
    source_plans 중 동일 구간·망에서 모요보다 저렴한 요금제 상세 (구간당 최저 3개).
    network_filter 지정 시 해당 망만 검사 (예: 알닷은 LGU+ 전용).
    """
    NETS     = ['SKT', 'KT', 'LGU+']
    segments = FirebaseHandler.GUIDE_SEGMENTS

    moyo_min = {}
    for p in moyo_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp <= 0: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in moyo_min or fp < moyo_min[key]:
            moyo_min[key] = fp

    src_min = {}
    for p in source_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp <= 0: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in src_min or fp < src_min[key]:
            src_min[key] = fp

    nets_to_check = [network_filter] if network_filter else NETS
    lines = []
    for seg in segments:
        for net in nets_to_check:
            key = (seg, net)
            mv  = moyo_min.get(key, 0)
            sv  = src_min.get(key, 0)
            if mv and sv and sv < mv:
                seg_plans = [
                    p for p in source_plans
                    if p.get('is_rs') and p.get('segment', '') == seg
                    and p.get('network', '') == net
                    and 0 < p.get('final_price', 0) < mv
                ]
                seg_plans.sort(key=lambda x: x.get('final_price', 0))
                if seg_plans:
                    lines.append(f"ㅇ {seg}({net}) (모요 {mv:,}원)")
                    for p in seg_plans[:3]:
                        fp   = p.get('final_price', 0)
                        diff = mv - fp
                        nm   = _clean_provider_display(shorten(p.get('provider', '')))
                        lines.append(
                            f"  {nm:<8s} {p.get('name','')[:15]} | {fp:,}원 (↓{diff:,})"
                        )
    return lines


def build_source_highlights(aldot_plans, mvnohub_plans, moyo_plans):
    """
    메시지5: 알닷/허브 단독 요금제 + 모요 대비 저렴한 요금제.
    (전일 대비 변동 섹션은 제외 — 3사 통합 발송 구조 변경 시 삭제 결정)
    """
    lines = []

    only_aldot = _only_source_plans(aldot_plans, moyo_plans)
    only_hub   = _only_source_plans(mvnohub_plans, moyo_plans)

    if only_aldot or only_hub:
        lines.append(f"🆕 단독 요금제 (모요 미등록, 알닷 {len(only_aldot)}개 / 허브 {len(only_hub)}개)")
        lines.append("```")
        for p in only_aldot[:5]:
            disc = f" ({p['discount_months']}개월후 {p['base_price']:,}원)" if p.get('discount_months') else ""
            nm   = _clean_provider_display(shorten(p.get('provider', '')))
            lines.append(f"ㅇ 알닷 {nm}({p.get('network','')}), {p.get('data','')} | {p.get('final_price',0):,}원{disc}")
        if len(only_aldot) > 5:
            lines.append(f"  ... 외 {len(only_aldot)-5}개")
        for p in only_hub[:5]:
            disc = f" ({p['discount_months']}개월후 {p['base_price']:,}원)" if p.get('discount_months') else ""
            nm   = _clean_provider_display(shorten(p.get('provider', '')))
            lines.append(f"ㅇ 허브 {nm}({p.get('network','')}), {p.get('data','')} | {p.get('final_price',0):,}원{disc}")
        if len(only_hub) > 5:
            lines.append(f"  ... 외 {len(only_hub)-5}개")
        lines.append("```")
        lines.append("")

    aldot_detail = _cheaper_detail_vs_moyo(aldot_plans, moyo_plans, network_filter='LGU+')  # 알닷은 LGU+ 전용
    hub_detail   = _cheaper_detail_vs_moyo(mvnohub_plans, moyo_plans)                        # 허브는 3망 전체

    if aldot_detail or hub_detail:
        lines.append("📋 모요 대비 저렴한 요금제")
        lines.append("```")
        if aldot_detail:
            lines.append("[알닷]")
            lines.extend(aldot_detail)
        if hub_detail:
            lines.append("[허브]")
            lines.extend(hub_detail)
        lines.append("```")

    if not lines:
        return "📋 단독/저렴 요금제 없음"

    return "\n".join(lines).strip()


def build_summary_table(curr_plans, prev_plans):
    comp       = Comparator()
    prev_rs    = comp.get_segment_min_prices(filter_for_rs(prev_plans), rs_only=True) if prev_plans else {}
    curr_rs    = comp.get_segment_min_prices(filter_for_rs(curr_plans), rs_only=True)
    changes_rs = comp.analyze_changes(curr_rs, prev_rs)

    NETS = ['SKT', 'KT', 'LGU+']

    def fmt(v, is_min):
        if not v: return '     - '
        num = f'{v:,}'
        return (num + '*').rjust(8) if is_min else (num + ' ').rjust(8)

    def arrow(d):
        if d < 0: return f"({abs(d):,}↓)".rjust(8)
        if d > 0: return f"({d:,}↑)".rjust(8)
        return ' ' * 8

    def tbl(label, summary, changes):
        msg  = f"📊 {label} 망별 최저가\n```\n"
        msg += f"{'구간':<9}{'SKT':>9} {'KT':>9} {'LGU+':>9}\n"
        msg += "─" * 38 + "\n"
        for seg, nets in summary.items():
            prices    = {n: nets.get(n, 0) for n in NETS}
            min_val   = min((v for v in prices.values() if v > 0), default=0)
            min_count = sum(1 for v in prices.values() if v == min_val and v > 0)
            cells = [fmt(prices[n], prices[n] == min_val and min_val > 0 and min_count < 3)
                     for n in NETS]
            msg += f"{seg:<9}{cells[0]} {cells[1]} {cells[2]}\n"
            ds  = changes.get(seg, {})
            row = [arrow(ds.get(n, 0)) for n in NETS]
            if any(x.strip() for x in row):
                msg += f"{'':9}{row[0]} {row[1]} {row[2]}\n"
        msg += "* 구간최저(2사이하) / ↓하락 / ↑상승\n```"
        return msg

    return tbl("RS", curr_rs, changes_rs)


try:
    import pandas as pd
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

KOREA_TZ      = pytz.timezone('Asia/Seoul')
BOT_TOKEN     = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_LOG      = os.getenv('TELEGRAM_CHAT_ID', '')
CHAT_MOYO     = '-1003843687198'
REQUESTER_ID  = os.getenv('REQUESTER_CHAT_ID', '')


# ── 텔레그램 ──────────────────────────────────────────────────────────────────

def clean_for_markdown(text):
    """코드블록(```) 밖의 텍스트에서만 Markdown 특수문자 제거"""
    parts = text.split('```')
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 0:  # 코드블록 밖
            for ch in ['_', '*', '[', ']']:
                part = part.replace(ch, '')
        result.append(part)
    return '```'.join(result)


def send_to(chat_id, text, parse_mode="Markdown"):
    if not BOT_TOKEN or not chat_id: return
    if not text or not str(text).strip(): return  # 빈 문자열 발송 방지
    try:
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload, timeout=10
        )
    except: pass

def send_log(text):
    send_to(CHAT_LOG, text)


def send_aldot(text, source_type='auto'):
    """
    알닷 메시지 발송: clean_for_markdown으로 특수문자 제거 후 Markdown 단일 발송.
    코드블록(```) 안은 그대로 유지, 밖의 텍스트만 특수문자 제거.
    """
    if not text or not text.strip():
        return
    cleaned = clean_for_markdown(text)
    send_result(cleaned, source_type=source_type)


def send_result(text, source_type='auto'):
    send_to(CHAT_LOG, text)
    if source_type == 'auto':
        send_to(CHAT_MOYO, text)
    if REQUESTER_ID and REQUESTER_ID != CHAT_LOG:
        send_to(REQUESTER_ID, text)

def send_telegram(text):
    send_to(CHAT_LOG, text)

def send_telegram_file(file_path, caption, source_type='auto'):
    if not BOT_TOKEN: return
    targets = [CHAT_LOG]
    if source_type == 'auto':
        targets.append(CHAT_MOYO)
    if REQUESTER_ID and REQUESTER_ID != CHAT_LOG:
        if REQUESTER_ID not in targets:
            targets.append(REQUESTER_ID)
    for chat_id in targets:
        if not chat_id: continue
        try:
            with open(file_path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                    data={'chat_id': chat_id, 'caption': caption},
                    files={'document': f}, timeout=60
                )
        except Exception as e:
            print(f"⚠️ 파일 전송 실패 ({chat_id}): {e}")


def send_excel_mail(file_path, caption, body_parts=None):
    """엑셀 파일을 Gmail로 발송 (chris.mclee@sk.com, jangga@sk.com, herothen@sktelecom.com)
    body_parts: [msg1, msg2, msg3, msg4, msg5] 텔레그램 메시지 리스트
      msg1=통합 수집현황 / msg2=일반사업자(3사통합) / msg3=자회사(3사통합) / msg4=MNO(3사통합) / msg5=단독·저렴상세
    """
    gmail_address  = os.getenv('GMAIL_ADDRESS',      'mclee.cecilia@gmail.com')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD', '')
    mail_to_list   = [
        os.getenv('MAIL_TO', 'chris.mclee@sk.com'),
        'jangga@sk.com',
        'herothen@sktelecom.com',
    ]

    if not gmail_password:
        print("⚠️ GMAIL_APP_PASSWORD 없음 → 메일 발송 생략")
        return False

    try:
        filename = os.path.basename(file_path)
        subject  = f"[MVNO 요금제] {caption}"

        # 본문 구성
        SEP = '━' * 40
        body_lines = [
            f"MVNO 요금제 현황 | {caption}",
            "",
        ]
        if body_parts:
            labels = ['✅ 수집현황', '📶 일반사업자(3사통합)', '🏢 자회사(3사통합)', '📡 MNO(3사통합)', '📋 단독·저렴상세']
            for label, part in zip(labels, body_parts):
                if part:
                    body_lines.append(SEP)
                    body_lines.append(f"■ {label}")
                    body_lines.append(SEP)
                    body_lines.append(part)
                    body_lines.append("")
        body_text = '\n'.join(body_lines)

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From']    = gmail_address
        msg['To']      = ', '.join(mail_to_list)
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, mail_to_list, msg.as_string())

        print(f"✅ 엑셀 메일 발송 완료 → {', '.join(mail_to_list)}")
        send_log(
            f"📧 MVNO 요금제 메일 발송 완료\n"
            f"수신: {', '.join(mail_to_list)}\n"
            f"제목: {subject}"
        )
        return True

    except Exception as e:
        print(f"⚠️ 엑셀 메일 발송 실패: {e}")
        send_log(f"❌ 엑셀 메일 발송 실패: {e}")
        return False


def send_mvnohub(text, source_type='auto'):
    """알뜰폰허브 메시지 발송: clean_for_markdown 적용 후 Markdown 단일 발송."""
    if not text or not text.strip():
        return
    cleaned = clean_for_markdown(text)
    send_result(cleaned, source_type=source_type)


def send_merged(text, source_type='auto'):
    """[v3.29] 3사 통합 메시지(1~5) 공용 발송: clean_for_markdown 적용 후 Markdown 발송."""
    if not text or not text.strip():
        return
    cleaned = clean_for_markdown(text)
    send_result(cleaned, source_type=source_type)


# ── 알닷 vs 모요 비교 메시지 ─────────────────────────────────────────────────

def build_aldot_comparison(aldot_plans, moyo_plans, prev_aldot_plans, recent_aldot_ids=None):
    """
    알닷 수집 결과를 모요와 비교해 텔레그램 메시지 생성.

    1) RS 구간별 모요 최저가 vs 알닷 최저가 테이블
    2) 알닷 단독 RS 요금제 (모요에 없는 data+network 조합)
    3) 전일 대비 알닷 변동
    """
    MIN_PRICE  = 0   # MIN_PRICE 조건 제거 (v3.28)
    NETS       = ['SKT', 'KT', 'LGU+']
    checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')
    rs_count   = sum(1 for p in aldot_plans if p.get('is_rs'))
    lines = [
        f"📡 알닷 수집 완료 ({checked_at})",
        f"총 {len(aldot_plans)}개 (RS {rs_count} / RM {len(aldot_plans)-rs_count})",
        ""
    ]

    # ── 1) RS 구간별 모요 vs 알닷 최저가 테이블 ─────────────────────────────
    # 모요 RS: segment+network → 최저가
    moyo_seg_min = {}
    for p in moyo_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in moyo_seg_min or fp < moyo_seg_min[key]['price']:
            moyo_seg_min[key] = {'price': fp, 'provider': p.get('provider', '')}

    # 알닷 RS: segment+network → 최저가+사업자
    aldot_seg_min = {}
    for p in aldot_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in aldot_seg_min or fp < aldot_seg_min[key]['price']:
            aldot_seg_min[key] = {'price': fp, 'provider': p.get('provider', ''), 'name': p.get('name', '')}

    # 알닷이 모요보다 저렴한 구간 찾기
    cheaper_segs = []
    from core.firebase_handler import FirebaseHandler as _FH
    segments = _FH.GUIDE_SEGMENTS  # ['7G+', '10G+', '11G+', '15G+100', '15G+300', '100G+']
    for seg in segments:
        for net in NETS:
            key   = (seg, net)
            moyo  = moyo_seg_min.get(key)
            aldot = aldot_seg_min.get(key)
            if moyo and aldot and aldot['price'] < moyo['price']:
                cheaper_segs.append({
                    'seg':          seg,
                    'network':      net,
                    'moyo_price':   moyo['price'],
                    'aldot_price':  aldot['price'],
                    'diff':         moyo['price'] - aldot['price'],
                    'provider':     aldot['provider'],
                    'name':         aldot['name'],
                })

    # ── 전체 구간 표 (모요 vs 알닷 최저가 비교) ────────────────────────────
    # 모요/알닷 segment+network 최저가
    moyo_seg_net_min  = {}
    aldot_seg_net_min = {}
    for p in moyo_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment',''), p.get('network',''))
        if key not in moyo_seg_net_min or fp < moyo_seg_net_min[key]['price']:
            moyo_seg_net_min[key] = {'price': fp, 'provider': p.get('provider','')}
    for p in aldot_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment',''), p.get('network',''))
        if key not in aldot_seg_net_min or fp < aldot_seg_net_min[key]['price']:
            aldot_seg_net_min[key] = {'price': fp, 'provider': p.get('provider','')}

    # 전체 구간 표 생성 (알닷 LGU+ 기준, 모든 구간 표시)
    table_rows = []
    cheaper_detail_segs = []  # 알닷이 더 싼 구간만 상세 나열
    for seg in segments:
        net = 'LGU+'  # 알닷은 LGU+ 전용
        moyo  = moyo_seg_net_min.get((seg, net))
        aldot = aldot_seg_net_min.get((seg, net))
        if not moyo and not aldot:
            continue
        moyo_price  = moyo['price']  if moyo  else 0
        aldot_price = aldot['price'] if aldot else 0
        cheaper_mark = '*' if (aldot_price > 0 and moyo_price > 0 and aldot_price < moyo_price) else ''
        moyo_str  = f"{moyo_price:,}"  if moyo_price  else '  -'
        aldot_str = f"{aldot_price:,}{cheaper_mark}" if aldot_price else '  -'
        provider  = aldot['provider'][:6] if aldot else ''
        table_rows.append(f"{seg:<9}{moyo_str:>8} {aldot_str:>8}")
        if cheaper_mark:
            cheaper_detail_segs.append((seg, net, moyo_price))

    if table_rows:
        cheaper_count = len(cheaper_detail_segs)
        lines.append(f"💰 모요 vs 알닷 RS 최저가 비교 (LGU+, 저렴:{cheaper_count}개*)")
        lines.append("```")
        lines.append(f"{'구간':<9}{'모요':>8} {'알닷':>8}")
        lines.append("─" * 28)
        for seg in segments:
            net = 'LGU+'
            moyo  = moyo_seg_net_min.get((seg, net))
            aldot = aldot_seg_net_min.get((seg, net))
            if not moyo and not aldot:
                continue
            moyo_price  = moyo['price']  if moyo  else 0
            aldot_price = aldot['price'] if aldot else 0
            cheaper_mark = '*' if (aldot_price > 0 and moyo_price > 0 and aldot_price < moyo_price) else ' '
            moyo_str  = f"{moyo_price:,}"  if moyo_price  else '     -'
            aldot_str = f"{aldot_price:,}{cheaper_mark}" if aldot_price else '     -'
            lines.append(f"{seg:<9}{moyo_str:>8} {aldot_str:>8}")
        lines.append("* 알닷이 더 저렴")
        lines.append("```")
        lines.append("")

    # ── 구간별 상세 요금제 목록 (알닷이 더 싼 구간만, 최저가 3개) ──────────
    if cheaper_detail_segs:
        detail_lines = []
        for seg, net, moyo_min in cheaper_detail_segs:
            seg_plans = [
                p for p in aldot_plans
                if p.get('is_rs')
                and p.get('segment','') == seg
                and p.get('network','') == net
                and p.get('final_price',0) > MIN_PRICE
                and p.get('final_price',0) < moyo_min
            ]
            seg_plans.sort(key=lambda x: x.get('final_price',0))
            if seg_plans:
                detail_lines.append(f"ㅇ {seg} (모요 {moyo_min:,}원)")
                for p in seg_plans[:3]:
                    fp   = p.get('final_price',0)
                    diff = moyo_min - fp
                    detail_lines.append(
                        f"  {shorten(p.get('provider','')):<8s} {p.get('name','')[:15]} | {fp:,}원 (↓{diff:,})"
                    )
        if detail_lines:
            lines.append("📋 모요 대비 저렴한 알닷 상세")
            lines.append("```")
            lines.extend(detail_lines)
            lines.append("```")
            lines.append("")

    # ── 2) 알닷 단독 RS 요금제 (모요 미등록) ────────────────────────────────
    moyo_keys = set()
    for p in moyo_plans:
        moyo_keys.add((p.get('data', ''), p.get('network', '')))

    only_aldot = []
    seen_keys  = set()
    for p in aldot_plans:
        if not p.get('is_rs'): continue
        if p.get('final_price', 0) < MIN_PRICE: continue
        key = (p.get('data', ''), p.get('network', ''))
        if key not in moyo_keys and key not in seen_keys:
            only_aldot.append(p)
            seen_keys.add(key)

    if only_aldot:
        only_aldot.sort(key=lambda x: x.get('final_price', 0))
        lines.append(f"🆕 알닷 단독 RS ({len(only_aldot)}개, 모요 미등록)")
        for p in only_aldot[:5]:
            disc = f" ({p['discount_months']}개월후 {p['base_price']:,}원)" if p.get('discount_months') else ""
            lines.append(f"[{p['network']}] {shorten(p['provider'])}, {p['data']} | {p['final_price']:,}원{disc}")
        if len(only_aldot) > 5:
            lines.append(f"  ... 외 {len(only_aldot)-5}개")
        lines.append("")

    # ── 3) 전주 대비 알닷 변동 ──────────────────────────────────────────────
    if prev_aldot_plans:
        prev_by_id   = {p['plan_id']: p for p in prev_aldot_plans if p.get('plan_id')}
        curr_by_id   = {p['plan_id']: p for p in aldot_plans if p.get('plan_id')}
        prev_ids     = set(prev_by_id.keys())
        curr_ids     = set(curr_by_id.keys())

        down, up, new_plans, removed = [], [], [], []

        for p in aldot_plans:
            pid  = p.get('plan_id')
            prev = prev_by_id.get(pid)
            if not prev: continue
            cp, pp = p.get('final_price', 0), prev.get('final_price', 0)
            if cp > 0 and pp > 0 and cp != pp:
                entry = {
                    'provider': p.get('provider', '?'),
                    'network':  p.get('network', '?'),
                    'name':     p.get('name', '?'),
                    'price':    cp, 'diff': cp - pp,
                    'is_rs':    p.get('is_rs', False)
                }
                (down if cp < pp else up).append(entry)

        for pid in (curr_ids - prev_ids):
            if recent_aldot_ids and pid in recent_aldot_ids: continue
            p = curr_by_id[pid]
            new_plans.append({
                'provider': p.get('provider', '?'),
                'network':  p.get('network', '?'),
                'name':     p.get('name', '?'),
                'price':    p.get('final_price', 0),
                'is_rs':    p.get('is_rs', False)
            })

        for pid in (prev_ids - curr_ids):
            if recent_aldot_ids and pid in recent_aldot_ids: continue
            p = prev_by_id[pid]
            removed.append({'provider': p.get('provider', '?'), 'name': p.get('name', '?')})

        if any([down, up, new_plans, removed]):
            lines.append(
                f"🔄 전일 대비 변동 | 가격↓{len(down)} ↑{len(up)} | 신규 {len(new_plans)} | 삭제 {len(removed)}"
            )
            rs1 = lambda e: (0 if e.get('is_rs') else 1)
            for title, items in [("■ 하향", down), ("■ 상향", up), ("■ 신규", new_plans)]:
                if not items: continue
                items.sort(key=lambda e: (rs1(e), e.get('diff', 0)))
                lines.append(title)
                for e in items[:5]:
                    tag  = 'RS' if e.get('is_rs') else 'RM'
                    diff = f"(↓{abs(e['diff']):,})" if e.get('diff', 0) < 0 else \
                           f"(↑{e['diff']:,})" if e.get('diff', 0) > 0 else ""
                    lines.append(f"[{tag}] {shorten(e['provider'])}({e['network']}), {e['name'][:20]}, {e['price']:,}원{diff}")
                if len(items) > 5:
                    lines.append(f"  ... 외 {len(items)-5}개")
            if removed:
                lines.append(f"■ 삭제: {len(removed)}개")
                for e in removed[:3]:
                    lines.append(f"  {shorten(e['provider'])}, {e['name'][:20]}")

    return "\n".join(lines)


# ── 알뜰폰허브 vs 모요 비교 메시지 ───────────────────────────────────────────

def build_mvnohub_comparison(mvnohub_plans, moyo_plans, prev_mvnohub_plans, recent_mvnohub_ids=None):
    """
    알뜰폰허브 수집 결과를 모요와 비교해 텔레그램 메시지 생성.

    1) RS 구간별 모요 vs 알뜰폰허브 최저가 테이블 (SKT/KT/LGU+ 3사)
    2) 알뜰폰허브 단독 RS 요금제 (모요에 없는 data+network 조합)
    3) 전일 대비 알뜰폰허브 변동
    """
    MIN_PRICE  = 0
    NETS       = ['SKT', 'KT', 'LGU+']
    checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')
    rs_count   = sum(1 for p in mvnohub_plans if p.get('is_rs'))
    lines = [
        f"🏪 알뜰폰허브 수집 완료 ({checked_at})",
        f"총 {len(mvnohub_plans)}개 (RS {rs_count} / RM {len(mvnohub_plans)-rs_count})",
        ""
    ]

    from core.firebase_handler import FirebaseHandler as _FH
    segments = _FH.GUIDE_SEGMENTS  # ['7G+', '10G+', '11G+', '15G+100', '15G+300', '100G+']

    # ── 1) RS 구간별 모요 vs 알뜰폰허브 최저가 테이블 (3사) ──────────────────
    moyo_seg_min  = {}
    hub_seg_min   = {}

    for p in moyo_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in moyo_seg_min or fp < moyo_seg_min[key]['price']:
            moyo_seg_min[key] = {'price': fp, 'provider': p.get('provider', '')}

    for p in mvnohub_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE: continue
        key = (p.get('segment', ''), p.get('network', ''))
        if key not in hub_seg_min or fp < hub_seg_min[key]['price']:
            hub_seg_min[key] = {'price': fp, 'provider': p.get('provider', ''), 'name': p.get('name', '')}

    # 3사별로 테이블 생성
    for net in NETS:
        table_rows = []
        cheaper_detail_segs = []
        for seg in segments:
            key   = (seg, net)
            moyo  = moyo_seg_min.get(key)
            hub   = hub_seg_min.get(key)
            if not moyo and not hub:
                continue
            moyo_price = moyo['price'] if moyo else 0
            hub_price  = hub['price']  if hub  else 0
            cheaper_mark = '*' if (hub_price > 0 and moyo_price > 0 and hub_price < moyo_price) else ' '
            moyo_str = f"{moyo_price:,}" if moyo_price else '     -'
            hub_str  = f"{hub_price:,}{cheaper_mark}" if hub_price else '     -'
            table_rows.append(f"{seg:<9}{moyo_str:>8} {hub_str:>8}")
            if cheaper_mark == '*':
                cheaper_detail_segs.append((seg, net, moyo_price))

        if table_rows:
            cheaper_count = len(cheaper_detail_segs)
            lines.append(f"💰 모요 vs 허브 RS 최저가 ({net}, 저렴:{cheaper_count}개*)")
            lines.append("```")
            lines.append(f"{'구간':<9}{'모요':>8} {'허브':>8}")
            lines.append("─" * 28)
            lines.extend(table_rows)
            lines.append("* 허브가 더 저렴")
            lines.append("```")
            lines.append("")

        # 구간별 상세 (허브가 더 싼 구간만)
        if cheaper_detail_segs:
            detail_lines = []
            for seg, net2, moyo_min in cheaper_detail_segs:
                seg_plans = [
                    p for p in mvnohub_plans
                    if p.get('is_rs')
                    and p.get('segment', '') == seg
                    and p.get('network', '') == net2
                    and p.get('final_price', 0) > MIN_PRICE
                    and p.get('final_price', 0) < moyo_min
                ]
                seg_plans.sort(key=lambda x: x.get('final_price', 0))
                if seg_plans:
                    detail_lines.append(f"ㅇ {seg} (모요 {moyo_min:,}원)")
                    for p in seg_plans[:3]:
                        fp   = p.get('final_price', 0)
                        diff = moyo_min - fp
                        detail_lines.append(
                            f"  {shorten(p.get('provider','')):<8s} {p.get('name','')[:15]} | {fp:,}원 (↓{diff:,})"
                        )
            if detail_lines:
                lines.append(f"📋 모요 대비 저렴한 허브 상세 ({net})")
                lines.append("```")
                lines.extend(detail_lines)
                lines.append("```")
                lines.append("")

    # ── 2) 허브 단독 RS 요금제 (모요 미등록) ─────────────────────────────────
    moyo_keys = {(p.get('data', ''), p.get('network', '')) for p in moyo_plans}
    only_hub  = []
    seen_keys = set()
    for p in mvnohub_plans:
        if not p.get('is_rs'): continue
        if p.get('final_price', 0) < MIN_PRICE: continue
        key = (p.get('data', ''), p.get('network', ''))
        if key not in moyo_keys and key not in seen_keys:
            only_hub.append(p)
            seen_keys.add(key)

    if only_hub:
        only_hub.sort(key=lambda x: x.get('final_price', 0))
        lines.append(f"🆕 허브 단독 RS ({len(only_hub)}개, 모요 미등록)")
        for p in only_hub[:5]:
            disc = f" ({p['discount_months']}개월후 {p['base_price']:,}원)" if p.get('discount_months') else ""
            lines.append(f"[{p['network']}] {shorten(p['provider'])}, {p['data']} | {p['final_price']:,}원{disc}")
        if len(only_hub) > 5:
            lines.append(f"  ... 외 {len(only_hub)-5}개")
        lines.append("")

    # ── 3) 전일 대비 알뜰폰허브 변동 ─────────────────────────────────────────
    if prev_mvnohub_plans:
        prev_by_id = {p['plan_id']: p for p in prev_mvnohub_plans if p.get('plan_id')}
        curr_by_id = {p['plan_id']: p for p in mvnohub_plans if p.get('plan_id')}
        prev_ids   = set(prev_by_id.keys())
        curr_ids   = set(curr_by_id.keys())

        down, up, new_plans, removed = [], [], [], []

        for p in mvnohub_plans:
            pid  = p.get('plan_id')
            prev = prev_by_id.get(pid)
            if not prev: continue
            cp, pp = p.get('final_price', 0), prev.get('final_price', 0)
            if cp > 0 and pp > 0 and cp != pp:
                entry = {
                    'provider': p.get('provider', '?'),
                    'network':  p.get('network', '?'),
                    'name':     p.get('name', '?'),
                    'price':    cp, 'diff': cp - pp,
                    'is_rs':    p.get('is_rs', False)
                }
                (down if cp < pp else up).append(entry)

        for pid in (curr_ids - prev_ids):
            if recent_mvnohub_ids and pid in recent_mvnohub_ids: continue
            p = curr_by_id[pid]
            new_plans.append({
                'provider': p.get('provider', '?'),
                'network':  p.get('network', '?'),
                'name':     p.get('name', '?'),
                'price':    p.get('final_price', 0),
                'is_rs':    p.get('is_rs', False)
            })

        for pid in (prev_ids - curr_ids):
            if recent_mvnohub_ids and pid in recent_mvnohub_ids: continue
            p = prev_by_id[pid]
            removed.append({'provider': p.get('provider', '?'), 'name': p.get('name', '?')})

        if any([down, up, new_plans, removed]):
            lines.append(
                f"🔄 전일 대비 변동 | 가격↓{len(down)} ↑{len(up)} | 신규 {len(new_plans)} | 삭제 {len(removed)}"
            )
            rs1 = lambda e: (0 if e.get('is_rs') else 1)
            for title, items in [("■ 하향", down), ("■ 상향", up), ("■ 신규", new_plans)]:
                if not items: continue
                items.sort(key=lambda e: (rs1(e), e.get('diff', 0)))
                lines.append(title)
                for e in items[:5]:
                    tag  = 'RS' if e.get('is_rs') else 'RM'
                    diff = f"(↓{abs(e['diff']):,})" if e.get('diff', 0) < 0 else \
                           f"(↑{e['diff']:,})" if e.get('diff', 0) > 0 else ""
                    lines.append(f"[{tag}] {shorten(e['provider'])}({e['network']}), {e['name'][:20]}, {e['price']:,}원{diff}")
                if len(items) > 5:
                    lines.append(f"  ... 외 {len(items)-5}개")
            if removed:
                lines.append(f"■ 삭제: {len(removed)}개")
                for e in removed[:3]:
                    lines.append(f"  {shorten(e['provider'])}, {e['name'][:20]}")

    return "\n".join(lines)

EXCEL_COLS = [
    ('_no',               'No',          5),
    ('_source_label',     '출처',         8),
    ('provider',          '알뜰폰사업자', 14),
    ('provider_type',     '사업자구분',  10),
    ('name',              '요금제명',    24),
    ('data',              '데이터',       9),
    ('segment',           '구간',         9),
    ('voice',             '통화',        12),
    ('sms',               '문자',        12),
    ('network',           '사용망',      10),
    ('network_generation','네트워크',     9),
    ('final_price',       '할인후금액',  12),
    ('discount_months',   '할인개월',    10),
    ('base_price',        '할인전금액',  12),
    ('subscribers',       '가입자수',    10),
    ('guide_below',       '가이드이하',  10),
    ('is_rs',             'RS여부',       8),
    ('rs_source',         'RS판정출처',  10),
    ('is_lowest_rs',      'RS최저가',     9),
    ('is_lowest_rm',      'RM최저가',     9),
]

# 알닷 시트 전용 추가 컬럼
EXCEL_COLS_ALDOT_EXTRA = [
    ('cheaper_than_moyo', '모요대비저렴', 12),
    ('aldot_lowest',      '알닷최저가',  10),
]



# ── 가이드 이하 요금제 표시 ───────────────────────────────────────────────────

def build_guide_comparison(plans, guide_data):
    """
    SKT망 RS 요금제 중 가이드 금액 이하인 요금제 목록 반환.
    가이드 금액과 동일한 금액도 포함 (이하 =).
    guide_data: {'prices': {'7G+': 10000, ...}, 'updated_at': datetime}
    """
    if not guide_data:
        return ""

    prices     = guide_data.get('prices', {})
    date_str = guide_data.get('guide_date', '')
    if not date_str:
        updated_at = guide_data.get('updated_at')
        date_str   = (updated_at.astimezone(pytz.timezone('Asia/Seoul')).strftime('%m/%d')
                      if updated_at and hasattr(updated_at, 'astimezone') else '날짜미상')

    from core.firebase_handler import FirebaseHandler
    segments = FirebaseHandler.GUIDE_SEGMENTS

    # SKT망 RS 요금제만 필터
    skt_rs = [p for p in plans
              if p.get('is_rs') and p.get('network') == 'SKT' and p.get('final_price', 0) >= 3000]

    lines = [f"📊 가이드 이하 요금제 [{date_str} 기준]"]
    has_any = False

    for seg in segments:
        guide_price = prices.get(seg, 0)
        if not guide_price:
            continue

        # 해당 구간 요금제 중 가이드 미만 (동일 금액 제외)
        seg_plans = [
            p for p in skt_rs
            if p.get('segment') == seg and p.get('final_price', 0) < guide_price
        ]

        # 없는 구간은 생략
        if not seg_plans:
            continue

        # 가격 오름차순 정렬
        seg_plans.sort(key=lambda x: x['final_price'])
        has_any = True
        lines.append(f"◎ {seg}({guide_price:,}원)")
        for p in seg_plans:
            lines.append(f"   - {p.get('provider','?')} {p.get('name','?')[:20]}, {p.get('final_price',0):,}원")

    if not has_any:
        return ""

    return "\n".join(lines)



# ── 모요 인기 (가입자 Top5) ───────────────────────────────────────────────────

def build_popularity_table(plans):
    """
    3사별 가입자수 Top 5 요금제 표시 (RS/RM 구분, 가격 포함).
    subscribers 필드 기준, 0이면 제외.
    """
    NETS = ['SKT', 'KT', 'LGU+']
    lines = ["📊 가입수 Top5 (모요)"]

    for net in NETS:
        net_plans = [p for p in plans if p.get('network') == net and p.get('subscribers', 0) > 0]
        top5 = sorted(net_plans, key=lambda x: x.get('subscribers', 0), reverse=True)[:5]
        lines.append(f"\n({net})")
        if top5:
            for p in top5:
                subs  = p.get('subscribers', 0)
                tag   = '(RS)' if p.get('is_rs') else '(RM)'
                price = p.get('final_price', 0)
                lines.append(f"  ◎ {tag} {p.get('provider','?')} {p.get('name','?')[:18]}")
                lines.append(f"     {price:,}원  {subs:,}명")
        else:
            lines.append("  데이터 없음")

    return "\n".join(lines)




# ── RM 요금제 분석 ────────────────────────────────────────────────────────────

def build_rm_analysis(plans, prev_plans=None):
    """
    RM 요금제 분석:
    1. 가격대별 최대 데이터 제공량 (3사)
    2. 가입수 Top 5 (3사) + 전주 대비 증감
    """
    NETS    = ['SKT', 'KT', 'LGU+']
    BUCKETS = [
        ('100원 이하',   0,      100),
        ('1천원 이하',   100,    1000),
        ('3천원 이하',   1000,   3000),
        ('1만원 이하',   3000,   10000),
        ('1만원 초과',   10000,  99999999),
    ]

    rm_plans = [p for p in plans if not p.get('is_rs') and p.get('final_price', 0) > 0]

    # 전주 데이터 구독자수 맵 {plan_id: subscribers}
    prev_subs = {}
    if prev_plans:
        for p in prev_plans:
            pid = p.get('plan_id') or p.get('id')
            if pid and p.get('subscribers', 0):
                prev_subs[pid] = p.get('subscribers', 0)

    # ── 1. 가격대별 최대 데이터 ──────────────────────────────────────────────
    def max_data_label(net_plans):
        if not net_plans:
            return '  -  '
        best = max(net_plans, key=lambda x: x.get('data_gb', 0))
        gb   = best.get('data_gb', 0)
        if gb == 0:    return '  -  '
        if gb == 9999: return '무제한'
        return f"{int(gb)}GB"

    tbl  = "📊 금액별 최대 데이터 제공량 (RM)\n```\n"
    tbl += f"{'구간':<10}│{'SKT':>6} │{'KT':>6} │{'LGU+':>6}\n"
    tbl += "─" * 34 + "\n"

    for label, lo, hi in BUCKETS:
        row = {}
        for net in NETS:
            bucket = [p for p in rm_plans
                      if p.get('network') == net
                      and lo < p.get('final_price', 0) <= hi]
            row[net] = max_data_label(bucket)

        max_gb = 0
        for net in NETS:
            v = row[net]
            if v == '무제한': gb = 9999
            elif 'GB' in v:
                try:    gb = int(float(v.replace('GB', '')))
                except: gb = 0
            else: gb = 0
            if gb > max_gb: max_gb = gb

        def mark(v):
            if max_gb == 0: return v.rjust(6)
            if v == '무제한' and max_gb == 9999: return (v + '*').rjust(7)
            if 'GB' in v:
                try:
                    if int(float(v.replace('GB', ''))) == max_gb: return (v + '*').rjust(7)
                except: pass
            return v.rjust(6)

        cells = [mark(row[n]) for n in NETS]
        tbl  += f"{label:<10}│{cells[0]} │{cells[1]} │{cells[2]}\n"

    tbl += "* 구간 최대\n```\n\n"

    # ── 2. 가입수 Top 5 ──────────────────────────────────────────────────────
    def change_label(curr_subs, pid):
        if not pid or pid not in prev_subs or not curr_subs:
            return ""
        prev = prev_subs[pid]
        if prev == 0:
            return ""
        rate = (curr_subs - prev) / prev * 100
        if rate <= -5:
            return f" (전주 대비 ▲{abs(int(rate))}%)"
        elif rate >= 5:
            return f" (전주 대비 +{int(rate)}%↑)"
        return ""

    tbl += "📊 가입수 Top 5 (RM)\n"
    for net in NETS:
        net_rm = [p for p in rm_plans
                  if p.get('network') == net and p.get('subscribers', 0) > 0]
        top5   = sorted(net_rm, key=lambda x: x.get('subscribers', 0), reverse=True)[:5]
        tbl   += f"\n({net})\n"
        for p in top5:
            subs  = p.get('subscribers', 0)
            pid   = p.get('plan_id') or p.get('id')
            price = p.get('final_price', 0)
            chg   = change_label(subs, pid)
            tbl  += f"  ◎ {p.get('provider','?')} {p.get('name','?')[:20]}\n"
            tbl  += f"     {price:,}원  {subs:,}명{chg}\n"

    return tbl.rstrip()

# ── RS 요금제 분석 ────────────────────────────────────────────────────────────

def build_rs_analysis(plans):
    """
    RS 요금제 분석:
    1. 가격대별 최대 데이터 제공량 (3사)
    2. 가입수 Top 5 (3사)
    """
    NETS    = ['SKT', 'KT', 'LGU+']
    BUCKETS = [
        ('100원 이하',   0,      100),
        ('1천원 이하',   100,    1000),
        ('3천원 이하',   1000,   3000),
        ('1만원 이하',   3000,   10000),
        ('1만원 초과',   10000,  99999999),
    ]

    rs_plans = [p for p in plans if p.get('is_rs') and p.get('final_price', 0) > 0]

    # ── 1. 가격대별 최대 데이터 ──────────────────────────────────────────────
    def max_data_label(net_plans):
        """data_gb 최대값 → 표시용 문자열"""
        if not net_plans:
            return '  -  '
        best = max(net_plans, key=lambda x: x.get('data_gb', 0))
        gb   = best.get('data_gb', 0)
        if gb == 0:    return '  -  '
        if gb == 9999: return '무제한'
        return f"{int(gb)}GB"

    tbl  = "📊 금액별 최대 데이터 제공량 (RS)\n```\n"
    tbl += f"{'구간':<10}│{'SKT':>6} │{'KT':>6} │{'LGU+':>6}\n"
    tbl += "─" * 34 + "\n"

    for label, lo, hi in BUCKETS:
        row = {}
        for net in NETS:
            bucket_plans = [p for p in rs_plans
                            if p.get('network') == net
                            and lo < p.get('final_price', 0) <= hi]
            row[net] = max_data_label(bucket_plans)
        # 3사 중 최대값 표시 (* 마킹)
        max_gb = 0
        for net in NETS:
            v = row[net]
            if v == '무제한': gb = 9999
            elif 'GB' in v:
                try:    gb = int(float(v.replace('GB','')))
                except: gb = 0
            else: gb = 0
            if gb > max_gb: max_gb = gb

        def mark(v):
            if max_gb == 0: return v.rjust(6)
            if v == '무제한' and max_gb == 9999: return (v + '*').rjust(7)
            if 'GB' in v:
                try:
                    if int(float(v.replace('GB',''))) == max_gb: return (v + '*').rjust(7)
                except: pass
            return v.rjust(6)

        cells = [mark(row[n]) for n in NETS]
        tbl  += f"{label:<10}│{cells[0]} │{cells[1]} │{cells[2]}\n"

    tbl += "* 구간 최대\n```\n\n"

    # ── 2. 가입수 Top 5 ──────────────────────────────────────────────────────
    tbl += "📊 가입수 Top 5 (RS)\n"
    for net in NETS:
        net_rs = [p for p in rs_plans if p.get('network') == net and p.get('subscribers', 0) > 0]
        top5   = sorted(net_rs, key=lambda x: x.get('subscribers', 0), reverse=True)[:5]
        tbl   += f"\n({net}) {len(top5)}개\n"
        for p in top5:
            price = p.get('final_price', 0)
            subs  = p.get('subscribers', 0)
            tbl  += f"  ◎ {p.get('provider','?')} {p.get('name','?')[:20]}\n"
            tbl  += f"     {price:,}원  {subs:,}명\n"

    return tbl.rstrip()


def _write_sheet(wb, ws, rows, hdr_fill, hdr_font, thin, odd_fill, even_fill, price_cols, extra_cols=None):
    """모요/알닷 개별 시트 작성 헬퍼. extra_cols: 추가 컬럼 리스트 [(field, kor, width), ...]"""
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    all_cols = list(EXCEL_COLS) + (list(extra_cols) if extra_cols else [])
    for ci, (_, kor, width) in enumerate(all_cols, 1):
        c           = ws.cell(row=1, column=ci)
        c.value     = kor
        c.fill      = hdr_fill
        c.font      = hdr_font
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border    = thin
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[1].height = 22
    for ri, row in enumerate(rows, 2):
        fill = odd_fill if ri % 2 == 0 else even_fill
        for ci, (field, _, _) in enumerate(all_cols, 1):
            val  = row.get(field, '')
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.border    = thin
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.fill      = fill
            if cell.column in price_cols and isinstance(val, (int, float)):
                cell.number_format = '#,##0'
    ws.freeze_panes = 'A2'


def build_excel(moyo_plans, aldot_plans, path, mvnohub_plans=None):
    # 가이드 금액 로드
    try:
        from core.firebase_handler import FirebaseHandler as _FH
        _db = _FH()
        _gd = _db.get_guide_prices()
        _gprices = _gd.get('prices', {}) if _gd else {}
    except Exception:
        _gprices = {}

    def make_rows(plan_list, extra_cols=None):
        rows = []
        for i, p in enumerate(plan_list, 1):
            row = {'_no': i}
            for field, _, _ in EXCEL_COLS[1:]:
                val = p.get(field, '')
                if field == 'discount_months' and val == 0: val = 0
                if field == 'is_rs':                        val = 'RS' if val else 'RM'
                if field == 'rs_source':
                    val = {'rules': '룰매칭', 'badge': '⚠뱃지', 'none': ''}.get(val, val)
                if field in ('is_lowest_rs', 'is_lowest_rm'): val = '★' if val else ''
                if field == 'subscribers' and val == 0:     val = ''
                if field == 'voice' and val:                val = f'통화 {val}'
                if field == 'sms'   and val:                val = f'문자 {val}'
                if field == 'network' and val:              val = f'{val}망'
                if field == 'guide_below':
                    seg  = p.get('segment', '')
                    gp   = _gprices.get(seg, 0)
                    fp   = p.get('final_price', 0)
                    val  = '◎' if (p.get('is_rs') and p.get('network') == 'SKT' and gp and fp and fp < gp) else ''
                row[field] = val
            # 추가 컬럼 (알닷 전용 등)
            if extra_cols:
                for field, _, _ in extra_cols:
                    row[field] = p.get(field, '')
            rows.append(row)
        return rows

    mvnohub_plans = mvnohub_plans or []

    # 알닷 전용 태깅: 모요대비저렴, 알닷최저가
    MIN_PRICE_EXCEL = 0
    # 모요 RS segment+network 최저가
    _moyo_seg_min = {}
    for p in moyo_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE_EXCEL: continue
        key = (p.get('segment',''), p.get('network',''))
        if key not in _moyo_seg_min or fp < _moyo_seg_min[key]:
            _moyo_seg_min[key] = fp
    # 알닷 RS segment+network 최저가
    _aldot_seg_min = {}
    for p in aldot_plans:
        if not p.get('is_rs'): continue
        fp = p.get('final_price', 0)
        if fp < MIN_PRICE_EXCEL: continue
        key = (p.get('segment',''), p.get('network',''))
        if key not in _aldot_seg_min or fp < _aldot_seg_min[key]:
            _aldot_seg_min[key] = fp
    # 알닷 plan에 태깅
    for p in aldot_plans:
        key   = (p.get('segment',''), p.get('network',''))
        fp    = p.get('final_price', 0)
        moyo_min  = _moyo_seg_min.get(key, 0)
        aldot_min = _aldot_seg_min.get(key, 0)
        p['cheaper_than_moyo'] = '★' if (fp > MIN_PRICE_EXCEL and moyo_min > 0 and fp < moyo_min) else ''
        p['aldot_lowest']      = '★' if (fp > MIN_PRICE_EXCEL and aldot_min > 0 and fp == aldot_min) else ''

    # 출처 라벨 태깅 (리스트 출처 기준 — moyo_scraper.py 쪽엔 'source' 필드가
    # 아예 없어서 plan.get('source')에 의존하지 않고, 어느 리스트에서 왔는지로 직접 부여)
    for p in moyo_plans:
        p['_source_label'] = '모요'
    for p in aldot_plans:
        p['_source_label'] = '알닷'
    for p in mvnohub_plans:
        p['_source_label'] = '허브'

    # 사업자구분 태깅
    for p in moyo_plans + aldot_plans + mvnohub_plans:
        p['provider_type'] = get_provider_type(p.get('provider', ''))

    all_plans     = moyo_plans + aldot_plans + mvnohub_plans
    all_rows      = make_rows(all_plans)
    moyo_rows     = make_rows(moyo_plans)
    aldot_rows    = make_rows(aldot_plans, extra_cols=EXCEL_COLS_ALDOT_EXTRA)
    mvnohub_rows  = make_rows(mvnohub_plans)

    cols = [f for f, _, _ in EXCEL_COLS]
    df   = pd.DataFrame(all_rows, columns=cols)
    df.to_excel(path, index=False, engine='openpyxl')

    try:
        wb       = load_workbook(path)
        ws       = wb.active
        # ── Sheet1: 요금제 전체 (모요+알닷 합산) ────────────────────────────
        ws.title = "요금제 전체"
        hdr_fill = PatternFill("solid", fgColor="1F4E79")
        hdr_font = Font(bold=True, color="FFFFFF", size=10)
        thin     = Border(left=Side(style='thin'), right=Side(style='thin'),
                          top=Side(style='thin'),  bottom=Side(style='thin'))
        odd_fill  = PatternFill("solid", fgColor="EBF3FB")
        even_fill = PatternFill("solid", fgColor="FFFFFF")

        for ci, (_, kor, width) in enumerate(EXCEL_COLS, 1):
            c           = ws.cell(row=1, column=ci)
            c.value     = kor
            c.fill      = hdr_fill
            c.font      = hdr_font
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border    = thin
            ws.column_dimensions[get_column_letter(ci)].width = width
        ws.row_dimensions[1].height = 22

        price_cols = {10, 12}
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            fill = odd_fill if row[0].row % 2 == 0 else even_fill
            for cell in row:
                cell.border    = thin
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.fill      = fill
                if cell.column in price_cols and isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0'
        ws.freeze_panes = 'A2'

        # ── Sheet2: 모요 ────────────────────────────────────────────────────
        ws_moyo = wb.create_sheet(title="모요")
        _write_sheet(wb, ws_moyo, moyo_rows, hdr_fill, hdr_font, thin, odd_fill, even_fill, price_cols)

        # ── Sheet3: 알닷 ────────────────────────────────────────────────────
        ws_aldot = wb.create_sheet(title="알닷")
        _write_sheet(wb, ws_aldot, aldot_rows, hdr_fill, hdr_font, thin, odd_fill, even_fill, price_cols,
                     extra_cols=EXCEL_COLS_ALDOT_EXTRA)

        # ── Sheet4: RS 망별 최저가 (모요) ───────────────────────────────────
        from core.comparator import Comparator as _Comp
        _comp   = _Comp()
        _rs_min = _comp.get_segment_min_prices(moyo_plans, rs_only=True)
        NETS    = ['SKT', 'KT', 'LGU+']

        ws2 = wb.create_sheet(title="RS 망별 최저가(모요)")
        for ci, h in enumerate(['구간', 'SKT', 'KT', 'LGU+'], 1):
            c = ws2.cell(row=1, column=ci, value=h)
            c.fill = PatternFill("solid", fgColor="1F4E79")
            c.font = Font(bold=True, color="FFFFFF", size=10)
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = thin
        for ci, w in enumerate([12, 14, 14, 14], 1):
            ws2.column_dimensions[get_column_letter(ci)].width = w
        ws2.row_dimensions[1].height = 22

        for ri, (seg, nets_data) in enumerate(_rs_min.items(), 2):
            min_val   = min((v for v in nets_data.values() if v > 0), default=0)
            min_count = sum(1 for v in nets_data.values() if v == min_val and v > 0)
            rf = PatternFill("solid", fgColor="EBF3FB" if ri%2==0 else "FFFFFF")
            c = ws2.cell(row=ri, column=1, value=seg)
            c.border=thin; c.alignment=Alignment(horizontal='center',vertical='center'); c.fill=rf
            for ci, net in enumerate(NETS, 2):
                v = nets_data.get(net, 0)
                cell = ws2.cell(row=ri, column=ci, value=v if v else None)
                cell.border=thin; cell.alignment=Alignment(horizontal='center',vertical='center')
                cell.fill=rf; cell.number_format='#,##0'
                if v and v==min_val and min_count<3:
                    cell.font = Font(bold=True, color="C00000")

        # ── Sheet5: RM Top5 (모요) ──────────────────────────────────────────
        ws3 = wb.create_sheet(title="RM Top5(모요)")
        rm_plans_ex = [p for p in moyo_plans if not p.get('is_rs') and p.get('subscribers', 0) > 0]
        row_idx = 1
        for net in NETS:
            net_rm = [p for p in rm_plans_ex if p.get('network') == net]
            top5   = sorted(net_rm, key=lambda x: x.get('subscribers', 0), reverse=True)[:5]
            # 망 헤더
            c = ws3.cell(row=row_idx, column=1, value=f"({net})")
            c.font=Font(bold=True,color="FFFFFF",size=10)
            c.fill=PatternFill("solid",fgColor="1F4E79")
            c.alignment=Alignment(horizontal='center',vertical='center'); c.border=thin
            ws3.merge_cells(start_row=row_idx,start_column=1,end_row=row_idx,end_column=4)
            row_idx += 1
            for ci, h in enumerate(['사업자','요금제명','금액','가입자수'], 1):
                c = ws3.cell(row=row_idx, column=ci, value=h)
                c.font=Font(bold=True,color="FFFFFF",size=9)
                c.fill=PatternFill("solid",fgColor="2E75B6")
                c.alignment=Alignment(horizontal='center',vertical='center'); c.border=thin
            row_idx += 1
            for rank_i, p in enumerate(top5):
                rf2 = PatternFill("solid", fgColor="EBF3FB" if rank_i%2==0 else "FFFFFF")
                for ci, v in enumerate([p.get('provider',''), p.get('name',''),
                                         p.get('final_price',0), p.get('subscribers',0)], 1):
                    c = ws3.cell(row=row_idx, column=ci, value=v)
                    c.border=thin; c.alignment=Alignment(horizontal='center',vertical='center')
                    c.fill=rf2
                    if ci in (3,4) and isinstance(v,(int,float)): c.number_format='#,##0'
                row_idx += 1
            row_idx += 1
        for ci, w in enumerate([14, 24, 10, 10], 1):
            ws3.column_dimensions[get_column_letter(ci)].width = w

        # ── Sheet6: 알뜰폰허브 ──────────────────────────────────────────────
        if mvnohub_rows:
            ws_hub = wb.create_sheet(title="알뜰폰허브")
            _write_sheet(wb, ws_hub, mvnohub_rows, hdr_fill, hdr_font, thin, odd_fill, even_fill, price_cols)

        wb.save(path)
    except Exception as e:
        print(f"⚠️ 스타일 실패: {e}")
    return path


# ── 변경 내역 메시지 ──────────────────────────────────────────────────────────

def build_plan_changes(curr_plans, prev_plans, recent_ids=None):
    """
    recent_ids: 최근 5개 수집 plan_id 합집합.
                여기 이미 있으면 이번 수집에서 누락된 것 → 신규 아님.
    """
    if not prev_plans:
        return ""

    prev_by_id   = {p.get('plan_id'): p for p in prev_plans if p.get('plan_id')}
    curr_by_id   = {p.get('plan_id'): p for p in curr_plans if p.get('plan_id')}
    prev_by_name = {(p.get('provider','')+'|'+p.get('name','')): p for p in prev_plans}

    prev_ids = set(prev_by_id.keys())
    curr_ids = set(curr_by_id.keys())

    down, up, new_plans, removed, surged = [], [], [], [], []

    SURGE_RATE = 0.20
    SURGE_MIN  = 500

    for p in curr_plans:
        pid  = p.get('plan_id')
        key  = p.get('provider','')+'|'+p.get('name','')
        prev = prev_by_id.get(pid) or prev_by_name.get(key)
        if not prev:
            continue
        # 가격 변경
        cp, pp = p.get('final_price',0), prev.get('final_price',0)
        if cp > 0 and pp > 0 and cp != pp:
            entry = {'provider': p.get('provider','?'), 'network': p.get('network','?'),
                     'name': p.get('name','?'), 'price': cp, 'diff': cp-pp,
                     'is_rs': p.get('is_rs', False)}
            (down if cp < pp else up).append(entry)
        # 선택수 급등
        cs, ps = p.get('subscribers',0), prev.get('subscribers',0)
        if ps > 0 and cs > ps:
            ds, rate = cs-ps, (cs-ps)/ps
            if rate >= SURGE_RATE and ds >= SURGE_MIN:
                surged.append({'provider': p.get('provider','?'), 'network': p.get('network','?'),
                               'name': p.get('name','?'), 'price': p.get('final_price',0),
                               'curr_subs': cs, 'diff_subs': ds, 'rate': rate,
                               'is_rs': p.get('is_rs', False)})

    # 신규: recent_ids에 없는 것만 진짜 신규
    for pid in (curr_ids - prev_ids):
        if recent_ids and pid in recent_ids:
            continue  # 이전에 있던 요금제가 한번 누락된 것 → 무시
        p = curr_by_id[pid]
        new_plans.append({'provider': p.get('provider','?'), 'network': p.get('network','?'),
                          'name': p.get('name','?'), 'price': p.get('final_price',0),
                          'is_rs': p.get('is_rs', False)})

    # 삭제: recent_ids 기준으로 최근 5개 모두에서 없어진 것만
    for pid in (prev_ids - curr_ids):
        if recent_ids and pid in recent_ids:
            continue  # 아직 최근 기록에 있음 → 일시 누락일 수 있음
        p = prev_by_id[pid]
        removed.append({'provider': p.get('provider','?'), 'name': p.get('name','?'),
                        'is_rs': p.get('is_rs', False)})

    if not any([down, up, new_plans, removed, surged]):
        return ""

    rs1 = lambda e: (0 if e['is_rs'] else 1)
    down.sort(key=lambda e: (rs1(e), e['diff']))
    up.sort(key=lambda e: (rs1(e), e['diff']))
    new_plans.sort(key=lambda e: (rs1(e), -e.get('price',0)))
    surged.sort(key=lambda e: (rs1(e), -e['diff_subs']))

    MAX = 20
    def _s(t): return str(t).replace('_','').replace('*','').replace('[','').replace(']','')
    def fc(e):
        a = f"↓{abs(e['diff']):,}" if e['diff']<0 else f"↑{e['diff']:,}"
        return f"[{'RS' if e['is_rs'] else 'RM'}] {_s(e['provider'])}({e['network']}), {_s(e['name'])[:25]}, {e['price']:,}원({a})"
    def fn(e):
        return f"[{'RS' if e['is_rs'] else 'RM'}] {_s(e['provider'])}({e['network']}), {_s(e['name'])[:25]}, {e['price']:,}원"
    def fs(e):
        return (f"[{'RS' if e['is_rs'] else 'RM'}] {_s(e['provider'])}({e['network']}), {_s(e['name'])[:25]}, "
                f"{e['price']:,}원 | {e['curr_subs']:,}명(+{e['diff_subs']:,}, +{e['rate']*100:.0f}%)")

    lines = [f"🔄 변경 내역 | 가격↓{len(down)} ↑{len(up)} | 신규 {len(new_plans)} | 삭제 {len(removed)} | 급등 {len(surged)}", ""]
    for title, items, fmt_fn in [("■ 하향 요금제", down, fc), ("■ 상향 요금제", up, fc),
                                   ("■ 신규 요금제", new_plans, fn), ("■ 선택수 급등", surged, fs)]:
        if items:
            lines.append(title)
            lines += [fmt_fn(e) for e in items[:MAX]]
            if len(items) > MAX: lines.append(f"  ... 외 {len(items)-MAX}개")
            lines.append("")
    if removed:
        lines.append(f"■ 삭제된 요금제: {len(removed)}개")
        for e in removed[:10]:
            lines.append(f"[{'RS' if e['is_rs'] else 'RM'}] {_s(e['provider'])}, {_s(e['name'])[:25]}")
        if len(removed) > 10: lines.append(f"  ... 외 {len(removed)-10}개")

    return "\n".join(lines)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    source_type = os.getenv('SCRAPE_SOURCE_TYPE', 'auto')
    scrape_type = os.getenv('SCRAPE_TYPE', 'all')  # 'all'(모요+알닷+허브, 3사 통합 발송) | 'aldot'(알닷만, 레거시 단일메시지)
    label       = '자동' if source_type == 'auto' else '수동'
    korea_time  = datetime.now(KOREA_TZ)
    print(f"🚀 스크래핑 시작: {korea_time.strftime('%Y-%m-%d %H:%M:%S')} ({source_type}, {scrape_type})")

    if scrape_type == 'aldot':
        send_log(f"📡 [{label}] 알닷 수집을 시작합니다! (약 30분 소요)")
    else:
        send_log(f"🔍 [{label}] 수집 작업을 시작합니다! (모요+알닷+허브, 3사 모두 수집 후 통합 발송 · 약 45분 소요)")

    try:
        def progress(msg):
            print(msg)
            send_log(msg)

        db         = FirebaseHandler()
        comparator = Comparator()

        # ── 모요 수집 (scrape_type='all'일 때만) ────────────────────────────
        if scrape_type == 'aldot':
            # 알닷 전용: 모요는 Firebase 최신 데이터 사용
            moyo_data  = db.get_latest_data('moyo')
            plans      = moyo_data.get('plans', []) if moyo_data else []
            screenshot = None
            print(f"ℹ️ 알닷 전용 - 모요 Firebase 로드: {len(plans)}개")
            if not plans:
                send_result("⚠️ 모요 데이터 없음. '모요 확인' 먼저 실행해주세요.", source_type)
                return
        else:
            scraper = MoyoScraper(progress_callback=progress)
            plans, screenshot = scraper.scrape()
            print(f"✅ 모요 {len(plans)}개 수집 완료")
        moyo_checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')

        # 모요 비교 대상 결정
        current_hour = datetime.now(KOREA_TZ).hour
        if source_type == 'auto':
            if current_hour < 10:
                previous = db.get_data_by_hour('moyo', target_hour=8, days_ago=1)
            else:
                previous = db.get_data_by_hour('moyo', target_hour=8, days_ago=0)
            if not previous:
                previous = db.get_previous_data('moyo', compare_type='auto')
        else:
            previous = db.get_latest_auto_data('moyo')
            if not previous:
                previous = db.get_previous_data('moyo')

        prev_plans  = previous.get('plans', []) if previous else []
        recent_ids  = db.get_recent_plan_ids('moyo', limit=5)

        # RS 최저가 태깅: 전체 plans로 segment 먼저 부여 후
        # 제외 요금제 빼고 최저가 재산출하여 is_lowest_rs 덮어쓰기
        plans = comparator.tag_plans_with_lowest(plans)  # segment, is_lowest_rs, is_lowest_rm 부여
        plans_for_rs = filter_for_rs(plans)
        plans_tagged = comparator.tag_plans_with_lowest(plans_for_rs)  # 제외 후 최저가 재산출
        tagged_ids = {p['plan_id']: p for p in plans_tagged}
        for p in plans:
            if p['plan_id'] in tagged_ids:
                # 제외 안 된 요금제: 필터링된 기준의 최저가 태깅 적용
                p['is_lowest_rs'] = tagged_ids[p['plan_id']].get('is_lowest_rs', False)
                p['is_lowest_rm'] = tagged_ids[p['plan_id']].get('is_lowest_rm', False)
            else:
                # 제외된 요금제(프리티 하나은행 등): is_lowest_rs=False 강제
                p['is_lowest_rs'] = False
        db.save_check_result('moyo', plans, screenshot, source_type=source_type)
        print("✅ 모요 Firebase 저장 완료")

        # 사업자구분별 분류 (모요)
        general_plans, sub_plans, mno_plans_list = split_by_provider_type(plans)

        # ═══════════════════════════════════════════════════════════════════
        # scrape_type == 'aldot' : 레거시 단일 소스 플로우 (기존과 동일, 변경 없음)
        # '알닷 확인' 수동 명령 전용 — 모요/허브 관여 없이 알닷 메시지 1건만 발송
        # ═══════════════════════════════════════════════════════════════════
        if scrape_type == 'aldot':
            aldot_plans = []
            aldot_msg   = ""
            try:
                aldot_scraper = AldotScraper(progress_callback=progress)
                aldot_plans, _ = aldot_scraper.scrape()
                print(f"✅ 알닷 {len(aldot_plans)}개 수집 완료")

                prev_aldot = db.get_data_by_hour('aldot', target_hour=8, days_ago=0)
                if not prev_aldot:
                    prev_aldot = db.get_latest_auto_data('aldot')
                if not prev_aldot:
                    prev_aldot = db.get_previous_data('aldot')
                prev_aldot_plans = prev_aldot.get('plans', []) if prev_aldot else []
                recent_aldot_ids = db.get_recent_plan_ids('aldot', limit=5)

                aldot_plans = comparator.tag_plans_with_lowest(aldot_plans)
                db.save_check_result('aldot', aldot_plans, None, source_type=source_type)
                print("✅ 알닷 Firebase 저장 완료")

                aldot_msg = build_aldot_comparison(aldot_plans, plans, prev_aldot_plans, recent_aldot_ids)
            except Exception as e:
                import traceback
                err = f"⚠️ 알닷 수집 실패\n{str(e)}\n{traceback.format_exc()[-300:]}"
                print(err)
                send_log(err)
                aldot_msg = f"⚠️ 알닷 수집 실패\n{str(e)}"

            if not aldot_msg:
                checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')
                aldot_msg  = f"📡 알닷 수집 완료 ({checked_at})\n총 {len(aldot_plans)}개"
            send_aldot(aldot_msg, source_type=source_type)
            return

        # ═══════════════════════════════════════════════════════════════════
        # scrape_type == 'all' : 3사(모요+알닷+허브) 모두 수집 완료 후 통합 발송 [v3.29]
        # ═══════════════════════════════════════════════════════════════════

        # ── 알닷 수집 ────────────────────────────────────────────────────────
        aldot_plans = []
        try:
            aldot_scraper = AldotScraper(progress_callback=progress)
            aldot_plans, _ = aldot_scraper.scrape()
            aldot_plans = comparator.tag_plans_with_lowest(aldot_plans)
            db.save_check_result('aldot', aldot_plans, None, source_type=source_type)
            print(f"✅ 알닷 {len(aldot_plans)}개 수집 완료")
        except Exception as e:
            import traceback
            err = f"⚠️ 알닷 수집 실패 (모요는 정상)\n{str(e)}\n{traceback.format_exc()[-300:]}"
            print(err)
            send_log(err)
            aldot_plans = []
        aldot_checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')

        # ── 알뜰폰허브 수집 ──────────────────────────────────────────────────
        mvnohub_plans = []
        try:
            hub_scraper = MvnohubScraper(progress_callback=progress)
            mvnohub_plans, _ = hub_scraper.scrape()
            mvnohub_plans = comparator.tag_plans_with_lowest(mvnohub_plans)
            db.save_check_result('mvnohub', mvnohub_plans, None, source_type=source_type)
            print(f"✅ 알뜰폰허브 {len(mvnohub_plans)}개 수집 완료")
        except Exception as e:
            import traceback
            err = f"⚠️ 알뜰폰허브 수집 실패\n{str(e)}\n{traceback.format_exc()[-300:]}"
            print(err)
            send_log(err)
            mvnohub_plans = []
        hub_checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')

        # ── 3사 모두 수집 완료 → 사업자구분별 병합 ──────────────────────────
        aldot_general, aldot_sub, aldot_mno = split_by_provider_type(aldot_plans)
        hub_general,   hub_sub,   hub_mno   = split_by_provider_type(mvnohub_plans)

        merged_general_all = general_plans + aldot_general + hub_general
        merged_sub_all      = sub_plans + aldot_sub + hub_sub
        merged_mno_all      = mno_plans_list + aldot_mno + hub_mno

        # 3사 병합 최저가 (구간·망별 최소값 — 소스 구분 없이 산출)
        curr_rs  = comparator.get_segment_min_prices(filter_for_rs(merged_general_all), rs_only=True)
        curr_sub = comparator.get_segment_min_prices(filter_for_rs(merged_sub_all), rs_only=True)
        curr_mno = get_mno_segment_min_prices(merged_mno_all)  # RS+RM 통합, 필터 없음(기존과 동일)

        # ── 직전 스냅샷 조회 (일반/자회사/MNO 각각, 병합값 기준) ────────────
        # 하루 3회(08/13/17시) 롤링 비교: 08시→전일 08시 / 13시→당일 08시 / 17시→당일 13시
        run_slot = _get_run_slot(current_hour)
        prev_slot, prev_days_ago = PREV_SLOT_MAP[run_slot]

        def _load_prev_snapshot(snap_type):
            if source_type == 'auto':
                snap = db.get_rs_snapshot_by_slot(prev_slot, days_ago=prev_days_ago, snap_type=snap_type)
                if not snap:
                    snap = db.get_latest_rs_snapshot(exclude_current=True, snap_type=snap_type)
            else:
                # 수동 수집: 가장 최근 auto 스냅샷과 비교
                snap = db.get_latest_rs_snapshot(snap_type=snap_type)
            return snap

        prev_general = _load_prev_snapshot('general')
        prev_sub     = _load_prev_snapshot('sub')
        prev_mno     = _load_prev_snapshot('mno')

        # 스냅샷 저장: auto 수집일 때만 (3종 모두 병합값 기준, run_slot 태깅하여 저장)
        if source_type == 'auto':
            db.save_rs_snapshot(curr_rs,  source_type=source_type, snap_type='general', run_slot=run_slot)
            db.save_rs_snapshot(curr_sub, source_type=source_type, snap_type='sub',     run_slot=run_slot)
            db.save_rs_snapshot(curr_mno, source_type=source_type, snap_type='mno',     run_slot=run_slot)
        else:
            print("ℹ️ 수동 수집 - RS 스냅샷 저장 생략")

        # ── 메시지1: 통합 수집현황 (모요+알닷+허브) ─────────────────────────
        msg1 = "\n\n".join([
            build_source_status_block(f"✅ 모요 수집 완료 [{label}]", plans, moyo_checked_at),
            build_source_status_block("📡 알닷 수집 완료", aldot_plans, aldot_checked_at),
            build_source_status_block("🏪 알뜰폰허브 수집 완료", mvnohub_plans, hub_checked_at),
        ])

        # ── 메시지2: 일반사업자 RS 최저가 (3사 통합) ────────────────────────
        msg2 = build_rs_comparison(
            curr_rs, prev_general,
            title="📶 RS 최저가 비교(일반사업자, 모요+알닷+허브 통합)"
        )

        # ── 메시지3: 자회사 RS 최저가 (3사 통합) ────────────────────────────
        SUB_PROVIDERS  = ['SK7모바일', 'KT엠모바일/스카이라이프', '유모바일/헬로비전']
        sub_rs_cnt_all = sum(1 for p in merged_sub_all if p.get('is_rs'))
        msg3 = (
            f"🏢 자회사 RS 최저가 (모요+알닷+허브 통합)\n"
            f"총 {len(merged_sub_all)}개 (RS {sub_rs_cnt_all} / RM {len(merged_sub_all)-sub_rs_cnt_all})\n"
            f"대상 : {', '.join(SUB_PROVIDERS)}\n\n"
            + build_rs_comparison(curr_sub, prev_sub)
        ) if merged_sub_all else ""

        # ── 메시지4: MNO 최저가 (3사 통합, RS+RM 통합) ──────────────────────
        MNO_PROVIDERS  = ['SKT', 'AIR', 'KT', '요고', 'LG U+', '너겟']
        mno_rs_cnt_all = sum(1 for p in merged_mno_all if p.get('is_rs'))
        msg4 = (
            f"📡 MNO 최저가 비교 (모요+알닷+허브 통합, RS+RM 통합)\n"
            f"총 {len(merged_mno_all)}개 (RS {mno_rs_cnt_all} / RM {len(merged_mno_all)-mno_rs_cnt_all})\n"
            f"대상 : {', '.join(MNO_PROVIDERS)}\n\n"
            + build_rs_comparison(curr_mno, prev_mno, title="📶 MNO 최저가 비교", segments=MNO_SEGMENTS)
        ) if merged_mno_all else ""

        # ── 메시지5: 단독 요금제 + 모요 대비 저렴한 요금제 (알닷+허브) ──────
        # 전일 대비 변동(가격↑↓/신규/삭제) 섹션은 제거 결정 (3사 통합 구조 변경)
        msg5 = build_source_highlights(aldot_plans, mvnohub_plans, plans)

        # ── 발송: 3사 모두 수집 완료 후 일괄 (메시지1~5 순서) ───────────────
        send_merged(msg1, source_type=source_type)
        send_merged(msg2, source_type=source_type)
        if msg3:
            send_merged(msg3, source_type=source_type)
        if msg4:
            send_merged(msg4, source_type=source_type)
        send_merged(msg5, source_type=source_type)

        # ── 엑셀 전송 ────────────────────────────────────────────────────────
        if HAS_PANDAS:
            try:
                excel_path = f"/tmp/moyo_aldot_mvnohub_{datetime.now(KOREA_TZ).strftime('%m%d_%H%M')}.xlsx"
                build_excel(plans, aldot_plans, excel_path, mvnohub_plans=mvnohub_plans)
                send_telegram_file(
                    excel_path,
                    f"📊 모요+알닷+허브 ({len(plans)}+{len(aldot_plans)}+{len(mvnohub_plans)}건) | {datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')}",
                    source_type=source_type
                )
                print("✅ 엑셀 전송 완료")
                # 메일 발송 (텔레그램과 동시)
                send_excel_mail(
                    excel_path,
                    f"모요+알닷+허브 ({len(plans)}+{len(aldot_plans)}+{len(mvnohub_plans)}건) | {datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')}",
                    body_parts=[msg1, msg2, msg3, msg4, msg5]
                )
            except Exception as e:
                import traceback
                send_result(f"⚠️ 엑셀 실패\n{traceback.format_exc()[-300:]}", source_type)

        # ── price_context 저장 (auto 수집일 때만) ───────────────────────────
        if source_type == 'auto':
            save_price_context(
                curr_rs       = curr_rs,
                prev_snapshot = prev_general,
                plans         = plans,
                aldot_plans   = aldot_plans,
                mvnohub_plans = mvnohub_plans,
            )

    except Exception as e:
        import traceback
        print(f"❌ 에러: {e}\n{traceback.format_exc()}")
        send_result(f"❌ 수집 실패\n\n{str(e)}", source_type=source_type)
        sys.exit(1)


if __name__ == '__main__':
    main()