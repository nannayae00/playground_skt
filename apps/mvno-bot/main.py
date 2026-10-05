#!/usr/bin/env python3
"""
MVNO 실적 분석 텔레그램 봇 (Cloud Run)

[수정 이력]
v4.3 | 2026-09-07 | 세종이관 보정 메시지 개선 (Claude)
  - handle_sejong_migration(): 기존 마감 리포트 방(TELEGRAM_CHAT_ID)에도 동일 메시지 추가 발송
    (입력방과 다를 때만, 중복 발송 방지)
v4.2 | 2026-09-07 | 세종→고고 이관 보정 마감 메시지 기능 추가 (Claude)
  - SEJONG_MIG_CHAT_ID: 입력/출력 방 (-1004413130076, 입력방=출력방 동일)
  - classify_intent(): '세종이관' 시작 텍스트 → sejong_migration 액션 (Gemini 호출 전 사전 필터,
    기존 액션들과 키워드 겹치지 않아 충돌 없음)
  - parse_sejong_migration_text(): "세종이관 MM-DD\\nS n\\nK n\\nL 미확인" 형식 파싱
  - handle_sejong_migration(): 입력 저장 → 전일 마감 데이터 조회 → 보정 메시지 생성/발송
    · ktoa_firestore.save_sejong_migration() / get_sejong_migration()
    · ktoa_telegram.build_sejong_correction_message() 사용
  - webhook(): action == 'sejong_migration' 분기 추가 (chat_id가 SEJONG_MIG_CHAT_ID일 때만 동작)
v4.1 | 2026-06-12 | 토요일 주간 리포트 + 월말 월마감 처리 추가
  - trigger_daily_analysis(): 20:03 진입 시 분기
    · 월말(잔여bw=0): 월별 context(ktoa_context_month) 기반 분석 +
      generate_month_closing_report() 엑셀 전송 후 종료 (일간분석 스킵)
    · 토요일(월말 아닐 때): 주간 context(ktoa_context_week) 기반 분석 후
      종료 (일간분석 스킵)
    · 평일: 기존 일간분석 로직 그대로 유지
  - handle_report_excel(): 요청 연/월이 현재월이 아니면
    generate_month_report_for()로 해당월 마지막 영업일 기준 리포트 생성
  - [추가] build_analysis_prompt()에 period_label 파라미터 추가, analyze_period()
    신규: 주간/월간 마감 분석 시 "당일/금일" 프레이밍 대신 기간 전체 총평
    프레이밍 사용 (월마감/주간 분석이 일마감처럼 보이던 문제 수정)
v4.0 | 2026-05-20 | 텔레그램 전송 안정화
  - send_telegram_message: timeout 10→30초
  - 4000자 초과 시 자동 분할 전송
  - 전송 실패 시 로그 강화
v3.9 | 2026-05-13 | 일마감 분석 채팅방 단일화
  - trigger_daily_analysis: TELEGRAM_CHAT_ID 기본값 -5078644105로 변경
  - ANALYSIS_CHAT_ID 중복 전송 코드 제거
v3.8 | 2026-05-13 | ktoa_context 텍스트 프롬프트 주입
  - build_context_prompt(): context_texts 섹션 추가 (AI컨텍스트, 재계산 금지)
  - trigger_daily_analysis(): ktoa_context 없으면 사전 생성 후 분석
v3.7 | 2026-05-11 | 월 현황 bw 표시 강화
  - build_context_prompt(): 경과bw/잔여bw/전체bw 합계 직접 계산해서 표시
  - "자체계산 절대 금지" 섹션 헤더 강화
v3.6 | 2026-05-11 | fc/bw 컨텍스트 일마감 분석 주입 + 중복 함수 제거
  - build_daily_fc_context(): 일마감 분석용 fc/bw 컨텍스트 생성 함수 신규 추가
    · Firestore 직접 조회 (오늘~7일 역순) → fc_mno_out, fc_net, fc_mvno_in 포함
    · 영업일수 기반 일평균/월마감 예측값 계산 및 프롬프트 텍스트 생성
  - trigger_daily_analysis(): fc_context를 text_for_analysis에 삽입 후 분석
  - analyze_with_claude() 중복 정의 제거 (구버전 text+historical_data 버전 삭제)
v3.5 | 2026-05-10 | Claude API 우선 분석 도입
  - analyze_with_claude(): Claude 기반 분석 함수 추가
  - trigger_daily_analysis(): Claude 우선 → Gemini 폴백, 헤더에 API명 표시
  - handle_query(): 실적 질문 시 Claude 우선 → Gemini 폴백
  - "gemini분석"/"제미나이 분석" 키워드 포함 시 Gemini 강제 사용
  - 전일/전주 비교 데이터 포함 (v3.4)
  - 새 DB 필드 반영: mno_in, mno_out_all, net_change MNO, cum_net MNO
v3.4 | 2026-05-09 | 일마감 분석에 전일/전주 비교 데이터 추가
v3.3 | 2026-04-20 | 주말/공휴일 실적 0인 날 일마감 분석 스킵
  - trigger_daily_analysis(): mvno_in.계 == 0 이면 분석 없이 조용히 종료
v3.2 | 2026-04-13 | bw 영업일수 예측 + 답변 헤더 추가
  - handle_query(): 답변 앞에 해석/조회범위 헤더 표시
    (🔍 해석: ... / 📅 조회: ... 형태)
  - build_context_prompt(): 월 현황에 bw 데이터 섹션 추가
    (누적 bw_manual, bw_ai_prev, bw_final + 오늘 bw)
  - build_context_prompt(): 예측 지침 추가
    (실무자 bw 기반 / AI bw 기반 두 가지 예측값 제시 요구)
  - handle_message(): 예측/전망/알려줘/해줘 등 키워드 추가
v3.1 | 2026-04-09 | mvno_records 잔재 제거 + OCR 기능 제거 + ktoa_events 연동
  - save_to_firestore(): mvno_records 저장 제거 (ktoa_daily 자동 수집으로 대체)
  - save_hourly_to_firestore() 외 OCR 관련 함수 7개 전면 제거
    (parse_hourly_table_ocr, format_hourly_verification, analyze_hourly_with_gemini,
     save/get/clear_pending_hourly_verification)
  - webhook: 이미지 처리 블록, 시간대별 검증 대기 블록 제거
  - context_bundler.py: ktoa_events ±30일 조회 → bundle.events 추가
  - build_context_prompt(): events 섹션 추가 (Gemini 이벤트 맥락 참고)
  - save_to_firestore(): mvno_records 저장 제거
    → 텔레그램 실적 붙여넣기 시 저장 없이 분석만 수행 (ktoa_daily 자동 수집으로 대체)
  - save_hourly_to_firestore(): mvno_hourly_records → ktoa_hourly 변경
  - handle_message() data_input 흐름: save_to_firestore() 호출 제거
    → parse → analyze 직접 연결, "저장 완료" 메시지 제거
  - context_bundler.py: get_relevant_events() 추가
    → 분석 기준일 ±30일 ktoa_events 조회, bundle.events에 포함
  - build_context_prompt(): events 섹션 추가 → Gemini가 이벤트 맥락 참고
v3.0 | 2026-04-09 | AI-Mediated 아키텍처 전면 적용
  - ai_intent_parser.py (신규): 자연어 → QuerySpec 변환 (Gemini Flash, 실패시 룰베이스 fallback)
  - context_bundler.py (신규): QuerySpec → ContextBundle
    (핵심 데이터 + 같은 요일 이력 + 최근 흐름 + 공휴일 맥락 + 월 목표 번들링)
  - handle_query(): 3-Layer → 5-Step AI-Mediated 전면 교체
  - build_context_prompt(): 신규 — ContextBundle → Gemini 분석 프롬프트
  - get_all_data_cached(): 캐시 if False 버그 수정 → 5분 캐시 정상화
  - ai_intent_parser 전역변수 추가, initialize_parsers()에 초기화 추가
  - import: ai_intent_parser, context_bundler 추가 / prompt_builder 제거
v2.0 | 2026-04-06 | 엑셀 리포트 명령어 추가
  - classify_intent(): report_excel 액션 추가 ("엑셀 추출", "리포트", "실적 뽑아줘" 등)
  - handle_report_excel(): generate_query_report() → 6개 시트 전체 파일 전송
  - 텔레그램 라우팅: report_excel → handle_report_excel()
v1.9 | 2026-04-01 | 데이터 소스 ktoa_daily로 전환 (mvno_records 제거)
  - get_from_firestore(): mvno_records → ktoa_daily 조회
  - ktoa_daily_to_record(): ktoa_daily 구조를 기존 record 포맷으로 변환 (어댑터)
  - save_to_firestore(): 텔레그램 수동입력은 mvno_records 유지 (레거시 보존)
v1.8 | 2026-04-01 | Gemini intent 분류 → 자연어 라우팅
  - classify_intent(): Gemini로 action 분류
  - 액션: bw_excel / query / help / recent / data_input / ignore
v1.7 | 2026-04-01 | 영업일수 엑셀 명령어 추가
v1.6 | 2026-03-18 | 자동 분석 메시지 형식 수정 + 추가 채팅방 전송
v1.5 | 2026-03-17 | trigger-daily-analysis Firestore 필드 매핑 수정
v1.4 | 2026-03-17 | trigger-daily-analysis date 파라미터 추가
v1.3 | 2026-03-17 | 20:03 자동 일마감 해석 연동
v1.2 | 2026-03-17 | Firestore 전체 조회 성능 개선
v1.1 | 2026-03-17 | Timestamp 직렬화 오류 수정
v1.0 | ~2026-03-16 | 초기 버전
"""

import io
from datetime import datetime, date, timezone, timedelta
import holidays
import functools
import os
import re
import json

from config import DATA_STRUCTURE, MONTHLY_GOALS, KEY_FOCUS, DAILY_RESPONSE_FORMAT, GENERAL_RESPONSE_FORMAT, PERIOD_RESPONSE_FORMAT
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.cloud import firestore
import requests
from date_parser import parse_korean_date
from query_parser import QueryParser, QueryIntent
from data_aggregator import DataAggregator, AggregatedData
from ai_intent_parser import AIIntentParser, QuerySpec      # v3.0 신규
from context_bundler import ContextBundler, ContextBundle   # v3.0 신규
from utils import ktoa_daily_to_record                      # v3.0 신규 (utils.py로 분리)

# ── 환경 변수 ────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
# 세종→고고 이관 보정 메시지 입력/출력 방 (동일 방)
SEJONG_MIG_CHAT_ID = os.environ.get('SEJONG_MIG_CHAT_ID', '-1004413130076')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
WEBHOOK_URL    = os.environ.get('WEBHOOK_URL')

processed_today = set()

# ── Gemini 설정 ──────────────────────────────────────────────
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# ── Claude API 설정 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = 'claude-sonnet-4-20250514'

# ── Claude API 설정 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL = 'claude-sonnet-4-20250514'

# ── Firestore 초기화 ─────────────────────────────────────────
try:
    db = firestore.Client(project='mvno-484509', database='mvno-data')
    print("✅ Firestore 연결 성공")
except Exception as e:
    print(f"❌ Firestore 연결 실패: {e}")
    db = None

# ── Flask 앱 ─────────────────────────────────────────────────
app = Flask(__name__)

# ── 파서 전역변수 ────────────────────────────────────────────
query_parser     = None
ai_intent_parser = None   # v3.0 신규


def initialize_parsers():
    """파서 초기화 (앱 시작 시 1회)"""
    global query_parser, ai_intent_parser

    if query_parser is None:
        query_parser = QueryParser()
        print("✅ QueryParser 초기화 완료")

    if ai_intent_parser is None:                        # v3.0 신규
        ai_intent_parser = AIIntentParser(model)
        print("✅ AIIntentParser 초기화 완료")

initialize_parsers()


# ============================================================
# 유틸리티 함수
# ============================================================

def firestore_to_json(obj):
    """Firestore Timestamp → JSON 직렬화 가능 타입으로 변환"""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: firestore_to_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [firestore_to_json(i) for i in obj]
    else:
        return obj

def get_kst_now():
    """한국 시간(KST) 반환"""
    return datetime.now(timezone(timedelta(hours=9)))

def get_kst_str():
    """한국 시간 문자열 반환 (YYYY-MM-DD HH:MM:SS)"""
    return get_kst_now().strftime('%Y-%m-%d %H:%M:%S')

def send_telegram_message(chat_id, text):
    """텔레그램 메시지 전송 (동기식)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # 긴 메시지 분할 (텔레그램 4096자 제한)
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        results = []
        for chunk in chunks:
            data = {"chat_id": chat_id, "text": chunk}
            try:
                response = requests.post(url, json=data, timeout=30)
                results.append(response.json())
            except Exception as e:
                print(f"메시지 전송 실패 (분할): {e}")
        return results
    data = {"chat_id": chat_id, "text": text}
    try:
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        if not result.get('ok'):
            print(f"텔레그램 전송 실패: {result}")
        return result
    except Exception as e:
        print(f"메시지 전송 실패: {e}")
        return None


def parse_mvno_data(text):
    """MVNO 데이터 파싱 - 개선된 날짜 인식"""
    data = {}
    
    # 날짜 추출 - 다양한 형식 지원
    date_found = False
    year, month, day = None, None, None
    
    # 패턴 1: 2026년 01월 21일 (4자리 연도)
    match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        date_found = True
    
    # 패턴 2: 251229 (YYMMDD 6자리)
    if not date_found:
        match = re.search(r'(\d{6})', text)
        if match:
            date_str = match.group(1)
            yy, mm, dd = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
            # 1~12월, 1~31일 범위 확인
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                # 2자리 연도를 4자리로 변환
                year = 2000 + yy
                month, day = mm, dd
                date_found = True
    
    # 패턴 3: 실적 현황 보고_0121 (MMDD 4자리)
    if not date_found:
        match = re.search(r'_(\d{2})(\d{2})', text)
        if match:
            mm, dd = int(match.group(1)), int(match.group(2))
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                month, day = mm, dd
                today = datetime.now()
                
                # 🔧 수정: 2026년 초에 2025년 데이터 처리
                if today.year == 2026 and today.month <= 2 and mm >= 11:
                    year = 2025
                elif mm > today.month:
                    year = today.year - 1
                else:
                    year = today.year
                date_found = True
       
    # 패턴 4: 01월 21일 (연도 없음)
    if not date_found:
        match = re.search(r'(\d{1,2})월\s*(\d{1,2})일', text)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            # 현재 날짜 기준으로 연도 추정
            today = datetime.now()
            if month > today.month:
                year = today.year - 1
            else:
                year = today.year
            date_found = True
    
    # 날짜가 없으면 오늘 날짜
    if not date_found or not all([year, month, day]):
        today = datetime.now()
        year, month, day = today.year, today.month, today.day

    
    
    data['date'] = f"{year:04d}-{month:02d}-{day:02d}"
    data['year'] = year
    data['month'] = month
    data['day'] = day
    
    # 요일 및 공휴일 계산
    date_value = date(year, month, day)
    weekday_kr = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][date_value.weekday()]
    
    # 한국 공휴일 확인
    kr_holidays = holidays.KR()
    is_holiday = date_value in kr_holidays
    holiday_name = kr_holidays.get(date_value, '')
    
    # 주말 확인
    is_weekend = date_value.weekday() >= 5  # 토요일(5), 일요일(6)
    
    # 근무일 여부 (평일 + 공휴일 아님)
    is_working_day = not (is_weekend or is_holiday)
    
    data['weekday'] = weekday_kr
    data['weekday_eng'] = date_value.strftime('%A')
    data['is_weekend'] = is_weekend
    data['is_holiday'] = is_holiday
    data['holiday_name'] = holiday_name
    data['is_working_day'] = is_working_day
    data['day_type'] = '공휴일' if is_holiday else ('주말' if is_weekend else '평일')
    
   

    # 각 섹션 파싱
    def parse_num(s):
        """숫자 파싱 - 천/만 단위 정확한 처리"""
        s = s.replace(',', '').replace('△', '-').replace('▲', '-').replace('+', '').strip()
        if '만' in s:
            s = s.replace('만', '')
            return int(float(s) * 10000)
        elif '천' in s:
            s = s.replace('천', '')
            return int(float(s) * 1000)
        else:
            return int(float(s))

    parsed_data = {}

    # ===== 당일 섹션 (필터링 불필요) =====

    # 1. 당일 마감
    match = re.search(r'◎\s*당일\s*마감[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL)
    if match:
        try:
            parsed_data['당일_마감'] = {
                'S': parse_num(match.group(1)),
                'K': parse_num(match.group(2)),
                'L': parse_num(match.group(3)),
                '계': parse_num(match.group(4))
            }
        except: pass

    # 2. 당일 MNO Out
    match = re.search(r'◎\s*\d+월\s*당일\s*MNO\s*Out[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL)
    if match:
        try:
            parsed_data['당일_MNO_Out'] = {
                'S': parse_num(match.group(1)),
                'K': parse_num(match.group(2)),
                'L': parse_num(match.group(3)),
                '계': parse_num(match.group(4))
            }
        except: pass

    # 3. 당일 순증감
    match = re.search(r'◎\s*\d+월\s*당일\s*순증감[^◎]*?S\s*([+\-△▲]?[\d,.]+[천만]?).*?K\s*([+\-△▲]?[\d,.]+[천만]?).*?L\s*([+\-△▲]?[\d,.]+[천만]?).*?계\s*([+\-△▲]?[\d,.]+[천만]?)', text, re.DOTALL)
    if match:
        try:
            parsed_data['당일_순증감'] = {
                'S': parse_num(match.group(1)),
                'K': parse_num(match.group(2)),
                'L': parse_num(match.group(3)),
                '계': parse_num(match.group(4))
            }
        except: pass

    # 4. 당일 MVNO MNP 해지
    match = re.search(r'◎\s*\d+월\s*당일\s*MVNO\s*MNP\s*해지[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL)
    if match:
        try:
            parsed_data['당일_MVNO_MNP_해지'] = {
                'S': parse_num(match.group(1)),
                'K': parse_num(match.group(2)),
                'L': parse_num(match.group(3)),
                '계': parse_num(match.group(4))
            }
        except: pass

    # ===== 누적 섹션 (필터링 로직 적용) =====

    # 5. 누적 신규
    for match in re.finditer(r'◎\s*\d+월\s*누적[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL):
        matched_text = text[match.start():match.end()]
        if 'MNO' not in matched_text and '순증감' not in matched_text and 'MVNO' not in matched_text:
            try:
                parsed_data['누적_신규'] = {
                    'S': parse_num(match.group(1)),
                    'K': parse_num(match.group(2)),
                    'L': parse_num(match.group(3)),
                    '계': parse_num(match.group(4))
                }
                break
            except: pass

    # 6. 누적 MNO Out
    for match in re.finditer(r'◎\s*\d+월\s*누적\s*MNO\s*Out[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL):
        matched_text = text[match.start():match.end()]
        if 'MVNO' not in matched_text and '순증감' not in matched_text:
            try:
                parsed_data['누적_MNO_Out'] = {
                    'S': parse_num(match.group(1)),
                    'K': parse_num(match.group(2)),
                    'L': parse_num(match.group(3)),
                    '계': parse_num(match.group(4))
                }
                break
            except: pass

    # 7. 누적 순증감
    for match in re.finditer(r'◎\s*\d+월\s*누적\s*순증감[^◎]*?S\s*([+\-△▲]?[\d,.]+[천만]?).*?K\s*([+\-△▲]?[\d,.]+[천만]?).*?L\s*([+\-△▲]?[\d,.]+[천만]?).*?계\s*([+\-△▲]?[\d,.]+[천만]?)', text, re.DOTALL):
        matched_text = text[match.start():match.end()]
        if 'MNO' not in matched_text and 'MVNO' not in matched_text:
            try:
                parsed_data['누적_순증감'] = {
                    'S': parse_num(match.group(1)),
                    'K': parse_num(match.group(2)),
                    'L': parse_num(match.group(3)),
                    '계': parse_num(match.group(4))
                }
                break
            except: pass

    # 8. 누적 MVNO MNP 해지
    for match in re.finditer(r'◎\s*\d+월\s*누적\s*MVNO\s*MNP\s*해지[^◎]*?S\s*([\d,.]+[천만]?).*?K\s*([\d,.]+[천만]?).*?L\s*([\d,.]+[천만]?).*?계\s*([\d,.]+[천만]?)', text, re.DOTALL):
        matched_text = text[match.start():match.end()]
        if '순증감' not in matched_text:
            try:
                parsed_data['누적_MVNO_MNP_해지'] = {
                    'S': parse_num(match.group(1)),
                    'K': parse_num(match.group(2)),
                    'L': parse_num(match.group(3)),
                    '계': parse_num(match.group(4))
                }
                break
            except: pass

    data['data'] = parsed_data
    data['type'] = 'daily'
    data['raw_text'] = text
    data['updated_at'] = datetime.now().isoformat()


    # 디버깅 로그 추가
    print(f"🔍 파싱 결과:")
    print(f"  - 당일_순증감: {parsed_data.get('당일_순증감', 'None')}")
    print(f"  - 누적_순증감: {parsed_data.get('누적_순증감', 'None')}")

    return data if parsed_data else None


def save_to_firestore(data):
    """
    [v3.1] 텔레그램 수동 입력 실적 저장 — 제거됨
    ktoa_daily는 사이트 자동 수집으로 저장되므로 중복 저장 불필요.
    이 함수는 하위 호환성을 위해 유지하되 실제 저장은 수행하지 않음.
    """
    try:
        doc_id = data.get('date', '')
        date_obj = datetime.strptime(doc_id, '%Y-%m-%d')
        formatted_date = f"'{date_obj.strftime('%y.%m')}월{date_obj.day}일 ({data.get('weekday', '')},{data.get('day_type', '')})"
        return True, formatted_date
    except Exception as e:
        return False, f"날짜 파싱 실패: {e}"

    

def save_feedback(chat_id, feedback_text, analysis_date=None):
    """사용자 피드백 저장 - timestamp와 usage_count 추가"""
    if not db:
        return False, "Firestore 연결 안 됨"
    
    try:
        kst_now = get_kst_now()
        feedback_id = f"fb_{kst_now.strftime('%Y%m%d_%H%M%S')}"
        feedback_data = {
            "feedback_id": feedback_id,
            "timestamp": get_kst_str(),
            "chat_id": chat_id,
            "date": kst_now.strftime('%Y-%m-%d'),
            "analysis_date": analysis_date,
            "feedback_text": feedback_text,
            "usage_count": 0,
            "created_at": get_kst_str()
        }

      
        db.collection('feedbacks').document(feedback_id).set(feedback_data)
        return True, feedback_id
    except Exception as e:
        return False, str(e)



def save_query_log(chat_id, question, answer, response_time):
    """일반 질문 로그 저장"""
    if not db:
        return False
    
    try:
        kst_now = get_kst_now()
        query_id = f"q_{kst_now.strftime('%Y%m%d_%H%M%S')}"
        query_data = {
            "query_id": query_id,
            "timestamp": get_kst_str(),
            "chat_id": chat_id,
            "question": question,
            "answer": answer,
            "response_time": round(response_time, 2),
            "created_at": get_kst_str()
        }
                
        db.collection('queries').document(query_id).set(query_data)
        return True
    except Exception as e:
        print(f"질문 로그 저장 실패: {e}")
        return False



def save_analysis_log(chat_id, data_date, answer, response_time):
    """실적 입력 분석 로그 저장"""
    if not db:
        return False
    
    try:
        kst_now = get_kst_now()
        log_id = f"log_{kst_now.strftime('%Y%m%d_%H%M%S')}"
        log_data = {
            "log_id": log_id,
            "input_timestamp": get_kst_str(),
            "data_date": data_date,
            "chat_id": chat_id,
            "answer": answer,
            "response_time": round(response_time, 2),
            "created_at": get_kst_str()
        }
        
        db.collection('analysis_logs').document(log_id).set(log_data)
        return True
    except Exception as e:
        print(f"분석 로그 저장 실패: {e}")
        return False



def increment_feedback_usage(feedback_id):
    """피드백 활용 횟수 증가"""
    if not db:
        return
    
    try:
        doc_ref = db.collection('feedbacks').document(feedback_id)
        doc = doc_ref.get()
        if doc.exists:
            current_count = doc.to_dict().get('usage_count', 0)
            doc_ref.update({'usage_count': current_count + 1})
    except Exception as e:
        print(f"피드백 카운트 업데이트 실패: {e}")



def get_feedbacks(limit=10):
    """최근 피드백 조회 및 사용 횟수 증가"""
    if not db:
        return ""
    
    try:
        docs = db.collection('feedbacks')\
                 .order_by('created_at', direction=firestore.Query.DESCENDING)\
                 .limit(limit)\
                 .stream()
        
        feedbacks = []
        for doc in docs:
            data = doc.to_dict()
            feedback_id = data.get('feedback_id')
            date = data.get('date', 'N/A')
            text = data.get('feedback_text', '')
            feedbacks.append(f"- {date}: {text}")
            
            # 사용 횟수 증가
            if feedback_id:
                increment_feedback_usage(feedback_id)
        
        return "\n".join(feedbacks) if feedbacks else ""
    except Exception as e:
        print(f"피드백 조회 오류: {e}")
        return ""


# ktoa_daily_to_record 는 utils.py로 이동 (v3.0, 순환참조 방지)
# from utils import ktoa_daily_to_record  ← 상단 import에서 이미 로드됨


def get_from_firestore(date=None, limit=None):
    """
    Firestore에서 데이터 조회 — ktoa_daily 기반 (mvno_records 대체)
    반환 포맷은 기존 mvno_records와 동일하게 어댑터 변환.
    """
    if not db:
        print("❌ Firestore DB 없음")
        return []

    try:
        collection_ref = db.collection('ktoa_daily')

        if date:
            doc = collection_ref.document(date).get()
            if doc.exists:
                result = [ktoa_daily_to_record(doc.id, doc.to_dict())]
            else:
                result = []
            print(f"🔍 단일 조회 (ktoa_daily): {date} → {len(result)}건")
            return result

        print("🔍 ktoa_daily 전체 조회 (stream)")
        result = []
        docs = collection_ref.stream()
        for doc in docs:
            d = doc.to_dict()
            if not d:
                continue
            # 실적 없는 날(일요일/공휴일) 포함 — 영업일수만 있는 날도 포함
            result.append(ktoa_daily_to_record(doc.id, d))

        result.sort(key=lambda x: x.get('date', ''), reverse=True)

        if limit:
            result = result[:limit]

        print(f"✅ ktoa_daily 조회 완료: {len(result)}건")
        return result

    except Exception as e:
        print(f"❌ ktoa_daily 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        return []
        
# ============================================
# 캐싱 함수
# ============================================


# ============================================================
# 캐싱
# ============================================================

_cache_timestamp = None
_cached_data     = None
_qa_cache        = {}


def get_all_data_cached():
    """전체 데이터 조회 (5분 캐싱)
    ★ [BUG FIX v3.0] 기존 'if False:' → 'if age < 300:'으로 캐시 정상화
    """
    global _cache_timestamp, _cached_data
    now = datetime.now()

    if _cached_data and _cache_timestamp:
        age = (now - _cache_timestamp).total_seconds()
        if age < 300:
            print(f"📦 캐시 반환 (age: {age:.0f}초, {len(_cached_data)}건)")
            return _cached_data

    print("🔄 Firestore 새로 조회")
    _cached_data = get_from_firestore(limit=None)
    _cache_timestamp = now
    print(f"✅ 조회 완료: {len(_cached_data)}건")

    if _cached_data:
        for i, record in enumerate(_cached_data[:3]):
            print(f"  레코드 {i+1}: {record.get('date')}")
            if 'data' in record:
                print(f"    필드: {list(record['data'].keys())}")

    return _cached_data


def normalize_question(q):
    """질문 정규화"""
    q = q.lower().strip()
    q = re.sub(r'\s+', ' ', q)
    q = q.replace('?', '').replace('!', '').replace('.', '')
    q = re.sub(r'(\d{2})년', lambda m: f"20{m.group(1)}년", q)
    return q


# ============================================================
# 레거시 분석 함수 (trigger-daily-analysis 전용)
# ============================================================


@functools.lru_cache(maxsize=20)
def get_cached_statistics(earliest_date, latest_date, data_json):
    """통계 계산 결과를 캐싱 (5분 단위)"""
    import json
    historical_data = json.loads(data_json)
    
    # 통계 계산
    s_shares = []
    s_growth = []
    
    for record in historical_data:
        date = record.get('date', '')
        data = record.get('data', {})
        
        if '당일_마감' in data:
            daily = data['당일_마감']
            total = daily.get('계', 1)
            if total > 0:
                s_share = (daily.get('S', 0) / total * 100)
                s_shares.append({'date': date, 'share': s_share})
        
        if '당일_순증감' in data:
            growth = data['당일_순증감']
            s_growth.append({'date': date, 'value': growth.get('S', 0)})
    
    stats = {}
    
    if s_shares:
        avg_share = sum(x['share'] for x in s_shares) / len(s_shares)
        max_share = max(s_shares, key=lambda x: x['share'])
        min_share = min(s_shares, key=lambda x: x['share'])
        stats['share'] = {
            'avg': avg_share,
            'max': max_share,
            'min': min_share
        }
    
    if s_growth:
        avg_growth = sum(x['value'] for x in s_growth) / len(s_growth)
        max_growth = max(s_growth, key=lambda x: x['value'])
        min_growth = min(s_growth, key=lambda x: x['value'])
        stats['growth'] = {
            'avg': avg_growth,
            'max': max_growth,
            'min': min_growth
        }
    
    return stats



def build_analysis_prompt(current_data=None, historical_data=None, user_question=None, period_label=None):
    """통합 프롬프트 생성기 - 피드백 반영

    [v4.1] period_label 추가: 주간/월간 마감 분석 시 설정.
    설정 시 '금일 실적' 프레이밍 대신 기간 전체 마감 분석으로 안내하고,
    parse_mvno_data를 거치지 않고 current_data(period context 텍스트)를 그대로 사용.
    """
    prompt = f"""당신은 SK MVNO(SM) 실적 분석 전문가입니다.

{DATA_STRUCTURE}

{MONTHLY_GOALS}

{KEY_FOCUS}

"""
    
    # 사용자 질문 모드
    if user_question:
        prompt += f"""
**사용자 질문:**
{user_question}

**답변 요청:**
- 위 질문에 대해 아래 과거 데이터를 분석하여 답변
- 기간별 비교 시 정확한 날짜와 숫자 포함
- 예측 시 근거와 트렌드 명시
"""
    
    # 기간(주간/월간) 마감 분석 모드
    elif period_label:
        prompt += f"""
**{period_label} 마감 데이터:**
{current_data}

**분석 요청:**
- 위 데이터는 {period_label} 전체 기간의 합계/평균/목표 대비 수치입니다. 일별 데이터가 아닙니다.
- "당일", "금일" 같은 일별 표현을 사용하지 말고, 기간 전체에 대한 총평으로 작성하세요.
- 목표 대비 달성 여부, 전기(이전 주/월) 대비 변화, 다음 기간을 위한 시사점을 중심으로 작성하세요.
- 데이터에 이미 계산된 수치(목표, 전기 대비, 월마감 예측 등)는 그대로 인용하고 재계산하지 마세요.
"""

    # 실적 분석 모드
    else:
        current = (parse_mvno_data(current_data) if current_data else {}) or {}
        date_info = f"{current.get('date', 'N/A')} ({current.get('weekday', '')}, {current.get('day_type', '')})"
        
        prompt += f"""
**금일 실적 ({date_info}):**
{current_data}

**분석 요청:**
1. 목표 대비 달성도 평가
2. 전일/전주 대비 변화 분석
3. 특이사항 및 주안점 도출
"""
    
    # 과거 데이터 추가
    if historical_data and len(historical_data) > 0:
        # 전체 데이터 범위 계산
        dates = [record.get('date') for record in historical_data if record.get('date')]
        if dates:
            earliest_date = min(dates)
            latest_date = max(dates)
            prompt += f"\n**전체 데이터 범위: {earliest_date} ~ {latest_date} (총 {len(historical_data)}일치)**\n"
        else:
            prompt += f"\n**과거 데이터 (총 {len(historical_data)}일치):**\n"
        
        # 🔧 추가: 데이터 타입별 명시
        if user_question:
            # 순기별 데이터
            if len(historical_data) <= 5 and any('period_type' in d and d['period_type'] == '10day' for d in historical_data):
                prompt += """
**중요: 이것은 순기별 집계 데이터입니다.**
- 각 레코드 = 해당 순기의 실적 합계 (누적 차이값으로 계산)
- 1순기: 1~10일, 2순기: 11~20일, 3순기: 21~말일
- 예: 1순기 T Out 1,000건 = 1~10일 동안의 T Out 합계
- **반드시 "X순기" 형식으로 답변**
- 일별 데이터가 아니므로 "일별 실적" 언급 금지

"""
            # 주차별 데이터
            elif len(historical_data) <= 6 and any('period_type' in d and d['period_type'] == 'weekly' for d in historical_data):
                prompt += """
**중요: 이것은 주차별 집계 데이터입니다.**
- 각 레코드 = 해당 주차의 실적 합계 (누적 차이값으로 계산)
- 1주차: 1~7일, 2주차: 8~14일, 3주차: 15~21일, 4주차: 22~말일
- 예: 1주차 T Out 1,000건 = 1~7일 동안의 T Out 합계
- **반드시 "X주차" 형식으로 답변**
- 일별 데이터가 아니므로 "일별 실적" 언급 금지

"""
            # 월별 데이터
            elif len(historical_data) <= 20:
                prompt += """
**중요: 이것은 각 월 마지막 영업일의 '누적' 데이터입니다.**
- 각 레코드 = 해당 월 전체 실적
- 예: 2025-01-31의 누적 T Out = 2025년 1월 전체 T Out
- 월별 비교 시 각 레코드를 독립된 월 실적으로 취급
- 일별 데이터가 아니므로 "일별 실적 비교" 금지
- 반드시 "X월(X/XX 기준)" 형식으로 답변

"""
        
        # 캐싱을 위해 데이터를 JSON으로 변환 (Timestamp → ISO string 변환 포함)
        import json
        data_json = json.dumps(firestore_to_json(historical_data))
        
        # 캐시된 통계 가져오기 (5분마다 갱신)
        try:
            stats = get_cached_statistics(earliest_date, latest_date, data_json)
            
            # 통계 요약
            if 'share' in stats:
                share_stats = stats['share']
                prompt += f"\n**SM 점유율 통계:**\n"
                prompt += f"- 평균: {share_stats['avg']:.1f}%\n"
                prompt += f"- 최고: {share_stats['max']['share']:.1f}% ({share_stats['max']['date']})\n"
                prompt += f"- 최저: {share_stats['min']['share']:.1f}% ({share_stats['min']['date']})\n"
            
            if 'growth' in stats:
                growth_stats = stats['growth']
                prompt += f"\n**SM 순증감 통계:**\n"
                prompt += f"- 평균: {growth_stats['avg']:+.0f}\n"
                prompt += f"- 최고: {growth_stats['max']['value']:+,} ({growth_stats['max']['date']})\n"
                prompt += f"- 최저: {growth_stats['min']['value']:+,} ({growth_stats['min']['date']})\n"
        except Exception as e:
            print(f"캐시된 통계 조회 실패: {e}")
            # 실패 시 통계 생략

        # 🔧 수정: 데이터 타입별 상세 출력
        if len(historical_data) <= 20:
            # 순기별 데이터
            if any('period_type' in d and d['period_type'] == '10day' for d in historical_data):
                prompt += "\n**각 순기 실적 상세 (해당 기간 합계):**\n"
                for i, record in enumerate(historical_data[:10], 1):
                    period_name = record.get('period_name', 'N/A')
                    date = record.get('display_date', record.get('date', 'N/A'))
                    data = record.get('data', {})
                    
                    prompt += f"{i}. {period_name} ({date} 기준)\n"
                    
                    # 누적 데이터 출력
                    if '누적_순증감' in data:
                        growth = data['누적_순증감']
                        s_val = growth.get('S', 0)
                        k_val = growth.get('K', 0)
                        l_val = growth.get('L', 0)
                        
                        # 🔧 추가: 1순기는 누적 = 합계 명시
                        if '1순기' in period_name:
                            prompt += f"   **순증 (1순기 = 월초~{date.split('-')[-1]}일 합계): S {s_val:+,}, K {k_val:+,}, L {l_val:+,}**"
                        else:
                            prompt += f"   순증: S {s_val:+,}, K {k_val:+,}, L {l_val:+,}"
                    
                    if '누적_MNO_Out' in data:
                        mno_out = data['누적_MNO_Out']
                        s_val = mno_out.get('S', 0)
                        total_val = mno_out.get('계', 0)
                        
                        if '1순기' in period_name:
                            prompt += f" | **T Out (1순기 합계): S {s_val:,}, 계: {total_val:,}**"
                        else:
                            prompt += f" | T Out: S {s_val:,}, 계: {total_val:,}"
                    
                    if '누적_신규' in data:
                        new = data['누적_신규']
                        s_val = new.get('S', 0)
                        
                        if '1순기' in period_name:
                            prompt += f" | **신규 (1순기 합계): S {s_val:,}**"
                        else:
                            prompt += f" | 신규: S {s_val:,}"
                    
                    prompt += "\n"
            
            # 주차별 데이터
            elif any('period_type' in d and d['period_type'] == 'weekly' for d in historical_data):
                prompt += "\n**각 주차 실적 상세 (해당 주 합계):**\n"
                for i, record in enumerate(historical_data[:10], 1):
                    period_name = record.get('period_name', 'N/A')
                    date = record.get('display_date', record.get('date', 'N/A'))
                    data = record.get('data', {})
                    
                    prompt += f"{i}. {period_name} ({date} 기준)\n"
                    
                    if '누적_순증감' in data:
                        growth = data['누적_순증감']
                        prompt += f"   순증: S {growth.get('S', 0):+,}, K {growth.get('K', 0):+,}, L {growth.get('L', 0):+,}"
                    
                    if '누적_MNO_Out' in data:
                        mno_out = data['누적_MNO_Out']
                        prompt += f" | T Out: S {mno_out.get('S', 0):,}, 계: {mno_out.get('계', 0):,}"
                    
                    if '누적_신규' in data:
                        new = data['누적_신규']
                        prompt += f" | 신규: S {new.get('S', 0):,}"
                    
                    prompt += "\n"
            
            # 월별 데이터
            else:
                prompt += "\n**각 월 실적 상세 (마지막 영업일 누적 기준):**\n"
                for i, record in enumerate(historical_data[:10], 1):
                    date = record.get('date', 'N/A')
                    data = record.get('data', {})
                    
                    # 월 추출
                    year_month = date[:7]  # YYYY-MM
                    
                    prompt += f"{i}. {year_month} ({date} 기준 누적)\n"
                    
                    # 누적 데이터 출력
                    if '누적_순증감' in data:
                        growth = data['누적_순증감']
                        prompt += f"   순증: S {growth.get('S', 0):+,}, K {growth.get('K', 0):+,}, L {growth.get('L', 0):+,}"
                    
                    if '누적_MNO_Out' in data:
                        mno_out = data['누적_MNO_Out']
                        prompt += f" | T Out: S {mno_out.get('S', 0):,}, 계: {mno_out.get('계', 0):,}"
                    
                    if '누적_신규' in data:
                        new = data['누적_신규']
                        prompt += f" | 신규: S {new.get('S', 0):,}"
                    
                    prompt += "\n"
        else:
            # 일별 데이터 (많은 경우)
            prompt += "\n**최근 5일 상세:**\n"
            for i, record in enumerate(historical_data[:5], 1):
                date = record.get('date', 'N/A')
                data = record.get('data', {})
                weekday = record.get('weekday', '')
                day_type = record.get('day_type', '')
                
                prompt += f"{i}. {date} ({weekday}, {day_type})\n"
                
                if '당일_마감' in data:
                    daily = data['당일_마감']
                    total = daily.get('계', 1)
                    s_share = (daily.get('S', 0) / total * 100) if total > 0 else 0
                    prompt += f"   점유율: S {s_share:.1f}%"
                
                if '당일_순증감' in data:
                    growth = data['당일_순증감']
                    prompt += f" | 순증: S {growth.get('S', 0):+,}"
                
                if '당일_MVNO_MNP_해지' in data:
                    mnp = data['당일_MVNO_MNP_해지']
                    prompt += f" | MNP: S {mnp.get('S', 0):,}"
                
                if '당일_MNO_Out' in data:
                    mno_out = data['당일_MNO_Out']
                    prompt += f" | T Out: S {mno_out.get('S', 0):,}, 계: {mno_out.get('계', 0):,}"
                
                prompt += "\n"
    
    # ✅ 피드백 추가
    feedbacks = get_feedbacks(limit=10)
    if feedbacks:
        prompt += f"""

**🔄 과거 사용자 피드백 (최근 10건):**
{feedbacks}

⚠️ 위 피드백을 적극 반영하세요:
- 긍정 피드백 → 계속 유지
- 부정 피드백 → 개선
- 제안사항 → 최대한 반영
"""
    
    # 답변 형식 추가 - 일반질문 / 주간·월간 / 일별실적 3가지 구분
    # [수정 20260924] period_label 모드가 DAILY_RESPONSE_FORMAT을 그대로 재사용하고
    # 있었음 - "당일" 개념이 없는 주간/월간에 안 맞는 형식이라 전용 포맷 분리
    if user_question:
        prompt += f"\n{GENERAL_RESPONSE_FORMAT}"
    elif period_label:
        prompt += f"\n{PERIOD_RESPONSE_FORMAT}"
    else:
        prompt += f"\n{DAILY_RESPONSE_FORMAT}"
    
    return prompt
    
    

def analyze_with_claude(prompt):
    """Claude API 호출"""
    try:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY 없음")
        import urllib.request, json as _json
        payload = _json.dumps({
            "model": CLAUDE_MODEL,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = _json.loads(resp.read().decode('utf-8'))
            return result['content'][0]['text'], 'Claude'
    except Exception as e:
        print(f"Claude 실패, Gemini 폴백: {e}")
        return None, None


def analyze_auto_prompt(prompt, force_claude=False):
    """Gemini 우선 → Claude 강제 키워드 시 Claude 사용"""
    if force_claude and ANTHROPIC_API_KEY:
        result, api = analyze_with_claude(prompt)
        if result:
            return result, api
    # Gemini 기본
    try:
        resp = model.generate_content(prompt)
        return resp.text, 'Gemini'
    except Exception as e:
        print(f"Gemini 실패, Claude 폴백: {e}")
        if ANTHROPIC_API_KEY:
            result, api = analyze_with_claude(prompt)
            if result:
                return result, api
        return "분석 중 오류 발생", 'Error'


def analyze_with_gemini(text, historical_data=None):
    """Gemini로 데이터 분석 - 통합 프롬프트 + 피드백 반영"""
    try:
        prompt = build_analysis_prompt(
            current_data=text,
            historical_data=historical_data,
            user_question=None
        )
        response = model.generate_content(prompt)
        return response.text, 'Gemini'
    except Exception as e:
        return f"분석 중 오류 발생: {e}", 'Gemini'


# [수정 20260924] 사장님 피드백: "당일 얘기뿐 아니라 최근추세 대비 어떤지 해석이
# 있어야" - 처음엔 ktoa_daily 최근 7일 단순평균을 새로 계산해서 넣었는데, 알고보니
# ktoa_context_builder.py가 이미 훨씬 정교한 비교(4주 "동일요일" 평균 - 주말/평일이
# 안 섞임, ±15% 이상치 자동판정, 전월 동기 비교, 목표 잔여여유)를 SUMMARY 블록으로
# 매일 생성해서 ktoa_context/{date}에 저장해두고 있었음(trigger_daily_analysis()가
# 이 문서를 미리 만들어만 두고 실제 프롬프트에는 안 쓰고 있었던 게 원래 문제).
# 새로 계산하지 않고 이미 있는 더 정확한 데이터를 재사용하도록 교체 - SUMMARY(이상치/
# 목표위험 판정) + 시장사이즈 한 줄 + 핵심시사점만 뽑아써서 길이는 짧게 유지.
def build_ktoa_context_summary(today_str: str) -> str:
    """ktoa_context/{today_str}(ktoa_context_builder.py가 생성)에서 SUMMARY 블록 +
    시장 사이즈 한 줄 + 핵심 시사점만 발췌. 전체(섹션 0~11, 수천자)를 넣으면
    프롬프트가 길어져 "말이 많다" 문제가 재발하므로 핵심만 뽑음."""
    if not db:
        return ""
    try:
        doc = db.collection("ktoa_context").document(today_str).get()
        if not doc.exists:
            return ""
        text = (doc.to_dict() or {}).get("text", "")
        if not text:
            return ""

        lines = text.splitlines()
        out = ["\n## [최근추세/이상치] 4주 동일요일 평균 대비 오늘 (이미 계산된 확정값, 재계산 금지)"]

        # SUMMARY 블록: "■ SUMMARY" ~ "※ 상세 수치는" 직전까지
        in_summary = False
        for ln in lines:
            if "■ SUMMARY" in ln:
                in_summary = True
                continue
            if in_summary and ln.strip().startswith("※"):
                break
            if in_summary and ("MARKET:" in ln or "TOUT_RATIO:" in ln or "TREND5:" in ln
                                or "PREVMONTH:" in ln or "ALERT:" in ln or "NORMAL:" in ln):
                out.append("  " + ln.strip())

        # 핵심 시사점(섹션 11): "핵심 시사점" 다음 "  - " 로 시작하는 줄들
        in_points = False
        for ln in lines:
            if "핵심 시사점" in ln:
                in_points = True
                continue
            if in_points:
                if ln.strip().startswith("- "):
                    out.append("  " + ln.strip())
                elif ln.strip():
                    break

        if len(out) <= 1:
            return ""
        out.append("  ※ 위 비교값(4주 동일요일 평균 기준)을 최근추세 해석에 그대로 인용할 것")
        return "\n".join(out)
    except Exception as e:
        print(f"[build_ktoa_context_summary] 오류 (무시): {e}")
        return ""


# [추가 20260924] 사장님 피드백: "요금제 분석, 오프라인 분석 동향 분석과 실적을
# 연계하면 더 풍성해질듯" - dcinside/뽐뿌 커뮤니티 동향(community_context, 기존
# dcinside_job.py가 매일 저장)과 부성/비전 오프라인 정책 모니터링(cafe_collector.py가
# 저장) 결과를 일마감 실적 분석 프롬프트에 요약해서 넣어, "왜 신규/이탈이 이렇게
# 움직였는지"를 시장 동향과 엮어 해석할 수 있게 함.
def build_market_context(today_str: str, lookback_days: int = 3) -> str:
    """최근 N일치 커뮤니티 동향(SUMMARY만) + 오프라인 정책 변경 하이라이트.
    [수정 20260924] 사장님 피드백: "요금제 변경은 보통 1~3일 시차 있음 - 며칠전
    것도 참고해야 오늘 실적을 설명할 수 있음" - 기존엔 오늘자 커뮤니티 문서 1개,
    오프라인정책은 소스별 최신 1건만 봐서 "며칠 전 있었던 변경의 지연효과"를
    놓치고 있었음. 최근 N일 전체를 날짜(N일 전)와 함께 나열하도록 확장."""
    if not db:
        return ""
    from datetime import datetime as _dt, timedelta as _td
    today_date = _dt.strptime(today_str, "%Y-%m-%d")
    lines = []

    try:
        for offset in range(lookback_days):
            d = today_date - _td(days=offset)
            ds = d.strftime("%Y-%m-%d")
            day_label = "오늘" if offset == 0 else f"{offset}일 전({ds})"
            cdoc = db.collection("community_context").document(ds).get()
            if not cdoc.exists:
                continue
            cd = cdoc.to_dict()
            for label, field in [("디씨인사이드", "text_dcinside"), ("뽐뿌", "text_ppomppu")]:
                text = cd.get(field, "")
                if not text:
                    continue
                # SUMMARY 섹션(ALERT/NORMAL 라인)만 추출 - 전체 넣으면 너무 길어짐.
                # merge된 필드(text_dcinside/text_ppomppu)는 하루 여러 회차가 이어붙여져
                # 있어 중복 라인이 쌓이므로 순서를 유지하며 dedup, ALERT만(핫딜/이슈 있을
                # 때만 참고할 가치 있음 - NORMAL까지 다 넣으면 매일 반복돼 장문화됨)
                seen = set()
                alert_lines = []
                for ln in text.splitlines():
                    ln = ln.strip()
                    if ln.startswith("ALERT:") and ln not in seen:
                        seen.add(ln)
                        alert_lines.append(ln)
                if alert_lines:
                    lines.append(f"  [{day_label}/{label}] " + " / ".join(alert_lines))
    except Exception as e:
        print(f"[build_market_context] community_context 조회 실패 (무시): {e}")

    try:
        cutoff = today_date - _td(days=lookback_days - 1)
        for coll, label in [("offline_policy_busung", "부성"), ("offline_policy_vision", "비전")]:
            docs = list(db.collection(coll).order_by("article_id", direction=firestore.Query.DESCENDING).limit(5).stream())
            for doc in docs:
                dd = doc.to_dict()
                _wd = dd.get("write_date")
                if not hasattr(_wd, "strftime"):
                    continue
                _wd_naive = _wd.replace(tzinfo=None) if _wd.tzinfo else _wd
                if _wd_naive.date() < cutoff.date():
                    break  # article_id 내림차순이라 이 이후로는 더 오래된 글만 나옴
                days_ago = (today_date.date() - _wd_naive.date()).days
                day_label = "오늘" if days_ago == 0 else f"{days_ago}일 전"
                msg = dd.get("formatted_message", "")
                highlight_lines = [ln.strip() for ln in msg.splitlines() if ln.strip().startswith("★")]
                if highlight_lines:
                    lines.append(f"  [{day_label}({_wd_naive.strftime('%m/%d')})/오프라인정책-{label}] " + " / ".join(highlight_lines))
    except Exception as e:
        print(f"[build_market_context] offline_policy 조회 실패 (무시): {e}")

    # [추가 20260925] 사장님 피드백: "요금분석결과도 있잖아 - 요금제 수준비교, 실적과
    # 연계분석" - price_context(모요+알닷+허브 통합 RS 최저가, SKT/KT/LGU+ 구간별
    # 비교, 전일 대비 변동)가 이미 계산돼 있는데 지금까지 daily 분석에 전혀 연결
    # 안 되고 있었음. community_context/offline_policy와 동일하게 SUMMARY(ALERT)
    # 라인만 추출해서 포함 (price_context는 "⚠️ ALERT:" 이모지 포함 표기라 다른
    # 소스와 필터 방식이 다름에 주의).
    price_lines = []
    try:
        for offset in range(lookback_days):
            d = today_date - _td(days=offset)
            ds = d.strftime("%Y-%m-%d")
            day_label = "오늘" if offset == 0 else f"{offset}일 전({ds})"
            pdoc = db.collection("price_context").document(ds).get()
            if not pdoc.exists:
                continue
            text = (pdoc.to_dict() or {}).get("text", "")
            if not text:
                continue
            alert_lines = [ln.strip() for ln in text.splitlines() if "ALERT:" in ln]
            if alert_lines:
                price_lines.append(f"  [{day_label}/요금분석] " + " / ".join(alert_lines))
    except Exception as e:
        print(f"[build_market_context] price_context 조회 실패 (무시): {e}")

    if not lines and not price_lines:
        return ""
    header = [
        "\n## [시장동향] 최근 3일 요금제/오프라인 정책/요금분석 참고 "
        "(실적 해석의 배경으로만 활용, 동향 자체를 수치로 재인용 금지)",
        "  ※ 요금제/프로모션 변경은 보통 1~3일 시차를 두고 실적에 반영됨. "
        "오늘 일어난 변경보다 1~2일 전 변경이 오늘 실적과 더 관련 있을 수 있음 - "
        "날짜(N일 전)를 보고 시차를 고려해 해석할 것.",
        "  ※ [요금분석](최저가 변동)과 [디씨인사이드]/[뽐뿌]/[오프라인정책]에서 같은 "
        "사업자·요금제가 동시에 언급되면, 여러 소스에서 교차 확인된 것이므로 실적에 "
        "미치는 영향이 더 크다고 판단해도 됨.",
    ]
    return "\n".join(header + lines + price_lines)


def get_hot_community_link(today_str: str, lookback_days: int = 2):
    """[추가 20260924] 오늘/최근 N일 뽐뿌 고중요도(★3개, 중요도 7+) 게시글 중
    가장 중요도 높은 것 1개를 코드에서 직접 파싱해 반환.
    Gemini 프롬프트에 넣지 않고 별도 경로로 처리하는 이유: URL은 LLM이 프롬프트에서
    그대로 베끼지 못하고 재작성/변형(글자 하나만 틀려도 깨진 링크)할 위험이 있어,
    텔레그램 메시지에 실제로 붙이는 링크는 반드시 원본 데이터에서 코드로 직접
    추출해야 안전함 (Gemini 분석 텍스트와는 별개로 메시지 하단에 그대로 첨부)."""
    if not db:
        return None
    from datetime import datetime as _dt, timedelta as _td
    today_date = _dt.strptime(today_str, "%Y-%m-%d")
    best = None
    try:
        for offset in range(lookback_days):
            d = today_date - _td(days=offset)
            ds = d.strftime("%Y-%m-%d")
            cdoc = db.collection("community_context").document(ds).get()
            if not cdoc.exists:
                continue
            text = (cdoc.to_dict() or {}).get("text_ppomppu", "")
            if not text:
                continue
            cur = {}
            for ln in text.splitlines():
                s = ln.strip()
                if s.startswith("[") and "star 중요도" in s:
                    sm = re.search(r"중요도\s*(\d+)/10", s)
                    cur = {
                        "is_3star": "] 3star" in s,
                        "score": int(sm.group(1)) if sm else 0,
                    }
                elif s.startswith("제목:"):
                    cur["title"] = s[len("제목:"):].strip()
                elif s.startswith("조회"):
                    vm = re.search(r"조회\s*(\d+)", s)
                    if vm:
                        cur["views"] = int(vm.group(1))
                elif s.startswith("URL:"):
                    cur["url"] = s[len("URL:"):].strip()
                    if cur.get("is_3star") and cur.get("url") and cur.get("title"):
                        if not best or cur.get("score", 0) > best.get("score", 0):
                            best = dict(cur)
    except Exception as e:
        print(f"[get_hot_community_link] 조회 실패 (무시): {e}")
        return None
    return best


def build_daily_fc_context(today_str: str) -> str:
    """
    일마감 분석용 fc/bw 컨텍스트 문자열 생성
    trigger_daily_analysis()에서 build_analysis_prompt() 앞에 삽입
    Firestore에서 직접 최신 fc값 조회
    """
    if not db:
        return ""
    try:
        from datetime import datetime as _dt, timedelta as _td, date as _date
        from calendar import monthrange

        d = _dt.strptime(today_str, "%Y-%m-%d")
        year, month = d.year, d.month
        last_day = monthrange(year, month)[1]
        today_date = _date(year, d.month, d.day)

        # ── 이번달 레코드 수집 (bw 합산용)
        elapsed_bw_ai = 0.0
        remaining_bw_ai = 0.0
        remaining_bw_manual = 0.0
        cum_skt = 0
        cum_net_sm = 0
        cum_mvno_in_sm = 0
        bw_elapsed_days = 0

        for day in range(1, last_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            doc = db.collection("ktoa_daily").document(ds).get()
            if not doc.exists:
                continue
            dd = doc.to_dict()
            bw_ai = float(dd.get("bw_ai_prev") or 0)
            bw_man = float(dd.get("bw_manual") or bw_ai)
            skt = (dd.get("mno_out") or {}).get("S", 0) or 0
            if day <= d.day:
                if bw_ai > 0 and skt > 0:
                    elapsed_bw_ai += bw_ai
                    bw_elapsed_days += 1
                    cum_skt += int(skt)
                    cum_net_sm += int((dd.get("cum_net") or {}).get("SM", 0) or 0
                                     if day == d.day else
                                     (dd.get("net_change") or {}).get("SM", 0) or 0)
                    cum_mvno_in_sm += int((dd.get("mvno_in") or {}).get("SM", 0) or 0)
            else:
                if bw_ai > 0:
                    remaining_bw_ai += bw_ai
                    remaining_bw_manual += bw_man

        # 당일 누적값은 cum_net 직접 사용
        today_doc = db.collection("ktoa_daily").document(today_str).get()
        today_dd = today_doc.to_dict() if today_doc.exists else {}
        cum_skt    = int((today_dd.get("cum_mno_out") or {}).get("S", cum_skt) or cum_skt)
        cum_net_sm = int((today_dd.get("cum_net")     or {}).get("SM", 0) or 0)
        cum_mvno_in_sm = int((today_dd.get("cum_mvno_in") or {}).get("SM", 0) or 0)

        # 일평균
        avg_skt = round(cum_skt / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0
        avg_net = round(cum_net_sm / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0
        avg_in  = round(cum_mvno_in_sm / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0

        # bw 기반 월마감 예측
        pred_skt_ai  = int(cum_skt + remaining_bw_ai * avg_skt)
        pred_skt_man = int(cum_skt + remaining_bw_manual * avg_skt)
        pred_net_ai  = int(cum_net_sm + remaining_bw_ai * avg_net)

        # ── fc 예측값 직접 조회 (오늘~7일 역순)
        fc_low = fc_mid = fc_high = 0
        fc_mno_out = {}
        fc_net = {}
        fc_mvno_in = {}
        fc_on_track = False
        fc_date = ""

        for offset in range(0, 8):
            ds = (today_date - _td(days=offset)).strftime("%Y-%m-%d")
            if not ds.startswith(f"{year}-{month:02d}"):
                break
            fdoc = db.collection("ktoa_daily").document(ds).get()
            if not fdoc.exists:
                continue
            fdd = fdoc.to_dict()
            _has = (fdd.get("fc_mno_out") or {}).get("S") or fdd.get("fc_low")
            if _has:
                fc_low     = fdd.get("fc_low", 0) or 0
                fc_mid     = fdd.get("fc_mid", 0) or 0
                fc_high    = fdd.get("fc_high", 0) or 0
                fc_on_track = fdd.get("fc_on_track", False)
                fc_mno_out = fdd.get("fc_mno_out", {}) or {}
                fc_net     = fdd.get("fc_net", {}) or {}
                fc_mvno_in = fdd.get("fc_mvno_in", {}) or {}
                fc_date    = ds
                print(f"[fc컨텍스트] {ds}: fc_low={fc_low}, fc_mno_out.S={fc_mno_out.get('S')}")
                break

        # [수정 20260924] 문자열에 "5월"이 그대로 박혀있던 버그 - 5월에 작성된 이후
        # 어느 달에 돌려도 라벨만 "5월"로 잘못 나갔음(실제 발견은 9월). Gemini가 프롬프트의
        # "재계산 금지" 지시를 어기고 라벨을 자기 판단으로 "9월"로 고쳐 쓴 사례가 있었는데,
        # 라벨을 스스로 고쳤다는 건 값 자체도 재해석했을 위험 신호라 실제 월로 고정.
        _month_label = f"{month}월"

        # [수정 20260924] SM 순증감 목표(-5000건)가 이 함수 안에만 별도로 하드코딩돼
        # 있어서, 프롬프트 상단 MONTHLY_GOALS(DB 동적 조회)와 다른 달엔 서로 다른 기준이
        # 한 프롬프트에 섞여 들어가던 버그. target_goal_reader로 단일 소스화.
        try:
            from target_goal_reader import get_goals_tuple
            _t_out_goal, _sm_net_goal, _ = get_goals_tuple(year, month)
        except Exception:
            _t_out_goal, _sm_net_goal = 35000, -5000  # target_goal_reader 자체가 안 될 때만 쓰는 최후 폴백

        # ── 컨텍스트 문자열 생성
        lines = []
        lines.append("\n## [DB예측] 월 현황 및 마감 예측 (반드시 이 값 기준으로 해석할 것)")
        lines.append(f"  기준일: {today_str} / 경과 영업일: {bw_elapsed_days}일")
        lines.append(f"  잔여 영업일수: AI기준 {round(remaining_bw_ai,2)}일 / 실무자기준 {round(remaining_bw_manual,2)}일")
        lines.append(f"  영업일수 가중 일평균 — T Out: {avg_skt}건, SM순증감: {avg_net}건, SM신규: {avg_in}건")
        lines.append(f"  T Out 누적: {cum_skt:,}건 / SM순증감 누적: {cum_net_sm:+,}건")

        # [수정 20260924] T Out 목표 달성여부(_track)가 이 함수 밖(별도 배치 잡)에서
        # 미리 계산해 저장한 fc_on_track 필드를 그대로 신뢰하고 있었음 - 그 잡이 어떤
        # 목표치 기준으로 계산했는지 이 코드에서 검증 불가능하고, 목표(t_out_goal)가
        # DB에서 바뀌어도 fc_on_track은 재계산되지 않을 위험이 있음(SM순증감 목표 캐시
        # 문제와 동일 패턴). SM순증감처럼 여기서 target_goal_reader의 최신 목표값과
        # 직접 비교해 라이브로 재계산하도록 변경 - fc_on_track은 더 이상 사용 안 함.
        _fc_label = f"({fc_date} 기준)" if fc_date and fc_date != today_str else ""

        _s_fc = (fc_mno_out.get("S") or {})
        if isinstance(_s_fc, dict) and _s_fc:
            _s_low = _s_fc.get("low", 0)
            _s_mid = _s_fc.get("mid", 0)
            _track = "목표 달성 가능 ✅" if _s_mid and _s_mid <= _t_out_goal else "목표 초과 위험 ⚠️"
            lines.append(f"  {_month_label} T Out 마감 예측{_fc_label}: {_s_low:,}~{_s_mid:,}건 → {_track} (목표 {_t_out_goal:,}건 이하)")
        elif fc_low:
            _track = "목표 달성 가능 ✅" if fc_mid and fc_mid <= _t_out_goal else "목표 초과 위험 ⚠️"
            lines.append(f"  {_month_label} T Out 마감 예측{_fc_label}: {fc_low:,}~{fc_mid:,}건 → {_track} (목표 {_t_out_goal:,}건 이하)")

        lines.append(f"  영업일수 기반 T Out 예측: AI {pred_skt_ai:,}건 / 실무자 {pred_skt_man:,}건")

        _sm_fc = (fc_net.get("SM") or {})
        if isinstance(_sm_fc, dict) and _sm_fc:
            _net_mid = _sm_fc.get("mid", 0)
            _net_low = _sm_fc.get("low", 0)
            _net_track = "목표 달성 가능 ✅" if _net_mid and _net_mid >= _sm_net_goal else "목표 초과 위험 ⚠️"
            lines.append(f"  {_month_label} SM순증감 마감 예측{_fc_label}: {_net_low:,}~{_net_mid:,}건 → {_net_track} (목표 {_sm_net_goal:+,}건 이상)")

        lines.append(f"  영업일수 기반 SM순증감 예측: AI {pred_net_ai:+,}건")

        _sm_in_fc = (fc_mvno_in.get("SM") or {})
        if isinstance(_sm_in_fc, dict) and _sm_in_fc:
            _in_low = _sm_in_fc.get("low", 0)
            _in_mid = _sm_in_fc.get("mid", 0)
            lines.append(f"  {_month_label} SM신규 마감 예측{_fc_label}: {_in_low:,}~{_in_mid:,}건")

        lines.append("  ※ [DB예측] 값과 라벨(월)은 그대로 인용할 것. AI 재계산·재작성 금지.")
        return "\n".join(lines)

    except Exception as e:
        print(f"[build_daily_fc_context] 오류 (무시): {e}")
        import traceback; traceback.print_exc()
        return ""


def analyze_auto(text, historical_data=None, force_claude=False):
    """Gemini 우선, Claude 강제 키워드 시 Claude 사용 (일마감 분석용)"""
    prompt = build_analysis_prompt(
        current_data=text,
        historical_data=historical_data,
        user_question=None
    )
    return analyze_auto_prompt(prompt, force_claude=force_claude)


def _extract_period_summary(full_text: str) -> str:
    """[추가 20260924] ktoa_context_period_builder.py가 만드는 전체 텍스트(이번기간+
    전기간 2개 문서를 통째로 이어붙인 것, 수천자)는 그대로 프롬프트에 넣으면 일간과
    같은 "말이 너무 많다" 문제가 재발함. 문서별 SUMMARY 블록(이상치/목표위험 자동판정,
    시장규모 한 줄)만 뽑아 압축 - 상세 수치는 SUMMARY 안에 이미 반영돼 있어 원본 없이도
    해석 가능."""
    import re as _re
    # 문서 헤더("[MVNO ...]")를 기준으로 전체 텍스트를 문서 단위로 분리 - "\n\n" 기준
    # split은 헤더 블록과 SUMMARY 블록이 서로 다른 빈줄 구간에 있어 분리돼버려 헤더가
    # 항상 빈 문자열이 되는 버그가 있었음
    docs = _re.split(r"(?=\[MVNO )", full_text)
    out = []
    for doc in docs:
        header_m = _re.match(r"\[MVNO .*?\]", doc)
        header = header_m.group(0) if header_m else ""
        m = _re.search(r"■ SUMMARY.*?\n(.*?)\n※", doc, _re.DOTALL)
        if not m:
            continue
        lines = [ln.strip() for ln in m.group(1).splitlines()
                 if ln.strip() and (ln.strip().startswith(("⚠️", "✅", "ℹ️", "시장")))]
        if lines:
            out.append(header)
            out.extend(f"  {ln}" for ln in lines)
    return "\n".join(out) if out else full_text  # SUMMARY 없는 구버전 문서 대비 폴백


def analyze_period(text, period_label, historical_data=None, force_claude=False):
    """[v4.1] 주간/월간 마감 분석용. '당일 실적' 프레이밍 대신
    period_label(예: '2026년 5월 월마감') 기준 총평 프롬프트 사용."""
    summary_text = _extract_period_summary(text)
    prompt = build_analysis_prompt(
        current_data=summary_text,
        historical_data=historical_data,
        user_question=None,
        period_label=period_label,
    )
    return analyze_auto_prompt(prompt, force_claude=force_claude)
# ============================================================
# AI-Mediated Query 처리 (v3.0 전면 교체)
# ============================================================

def handle_query(chat_id, question):
    """
    5-Step AI-Mediated 아키텍처

    Step 1. AIIntentParser  : 자연어 → QuerySpec (Gemini Flash)
                              실패시 query_parser.py 룰베이스 자동 fallback
    Step 2. ContextBundler  : QuerySpec → ContextBundle
                              핵심 데이터 + 같은 요일 이력 + 최근 흐름
                              + 공휴일 맥락 + 월 목표
    Step 3. 빈 결과 처리    : 날짜 명시 → Gemini 혼동 방지
    Step 4. build_context_prompt : ContextBundle → Gemini 분석 프롬프트
    Step 5. Gemini Analyst  : 풍부한 컨텍스트 기반 분석 & 답변
    """
    try:
        normalized = normalize_question(question)
        q_hash = hash(normalized)

        now = datetime.now()
        if q_hash in _qa_cache:
            cached_answer, cached_time = _qa_cache[q_hash]
            if (now - cached_time).total_seconds() < 300:
                print("💾 캐시 hit")
                send_telegram_message(chat_id, f"💡 **답변**\n\n{cached_answer}")
                return

        send_telegram_message(chat_id, "🤔 분석 중...")
        start_time = datetime.now()

        # Step 1: AI Intent Parser
        spec = ai_intent_parser.parse(question)
        print(f"📋 QuerySpec: intent={spec.intent} agg={spec.aggregation} "
              f"dates={spec.target_dates} fallback={spec.used_fallback}")
        print(f"   desc: {spec.description}")

        # Step 2: Context Bundler
        all_data = get_all_data_cached()
        bundler  = ContextBundler(all_data, db=db, monthly_goals={})  # 월목표는 ktoa_config에서 별도 관리
        bundle   = bundler.build(spec)
        print(f"📦 Bundle: {bundle.summary()}")

        # Step 3: 빈 결과 처리
        if bundle.is_empty():
            dates = [d.get("date") for d in all_data if d.get("date")]
            msg  = "❌ **데이터 없음**\n\n"
            msg += f"**요청 내용:** {spec.description}\n"
            if spec.target_dates:
                msg += f"**요청 날짜:** {', '.join(spec.target_dates)}\n"
            if bundle.missing_dates:
                msg += f"**없는 날짜:** {', '.join(bundle.missing_dates)}\n"
            if dates:
                msg += f"\n**보유 범위:** {min(dates)} ~ {max(dates)} ({len(all_data)}일치)\n"
            msg += "\n💡 영업일이 아니거나 아직 수집 전일 수 있습니다."
            if spec.used_fallback:
                msg += "\n⚠️ AI 해석 실패로 룰베이스 처리됐습니다."
            send_telegram_message(chat_id, msg)
            return

        # Step 4: 프롬프트 생성
        prompt = build_context_prompt(question, spec, bundle)
        print(f"📝 프롬프트: {len(prompt)}자")

        # Step 5: Gemini 기본, claude/클로드 키워드 시 Claude 강제
        _q_lower = question.lower().replace(' ', '')
        _force_claude = any(kw in _q_lower for kw in
                           ['claude분석', '클로드분석', '클로드로', 'claude로', '클로드로분석'])
        answer, _api_name = analyze_auto_prompt(prompt, force_claude=_force_claude)

        _qa_cache[q_hash] = (answer, now)
        response_time = (datetime.now() - start_time).total_seconds()
        save_query_log(chat_id, question, answer, response_time)

        prefix = ""
        if spec.used_fallback:
            prefix = "⚠️ _AI 해석 실패 → 룰베이스 처리_\n\n"
        else:
            dates_all = (
                [r.get("date") for r in bundle.primary if r.get("date")] +
                [r.get("date") for r in bundle.recent_days if r.get("date")]
            )
            date_range = f"{min(dates_all)} ~ {max(dates_all)}" if dates_all else "N/A"
            events_note = f" | 이벤트 {len(bundle.events)}건" if bundle.events else ""
            prefix = (
                f"🔍 **이해한 내용:** {spec.description}\n"
                f"📅 **조회:** {date_range} ({len(bundle.primary)}건{events_note})\n"
                f"🤖 **분석:** {_api_name}\n\n"
            )

        send_telegram_message(chat_id, f"💡 **답변**\n\n{prefix}{answer}")

    except Exception as e:
        print(f"❌ handle_query 오류: {e}")
        import traceback
        traceback.print_exc()
        send_telegram_message(chat_id, f"❌ 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n`{e}`")


def build_context_prompt(question: str, spec, bundle) -> str:
    """
    ContextBundle → Gemini 분석 프롬프트 (v3.0 신규)
    핵심 데이터 + 참고 컨텍스트를 구조화해서 전달
    """
    def fmt_record(r: dict) -> dict:
        """Gemini에 넘길 레코드 정리 — data 하위 딕셔너리 제외, 최상위 필드만"""
        keep = {
            "date", "weekday", "day_type", "is_holiday", "is_weekend",
            "mvno_in", "mno_out", "net_change", "mvno_out",
            "cum_mvno_in", "cum_mno_out", "cum_net", "cum_mvno_out",
            "bw_final", "bw_performance", "bw_manual", "bw_ai_prev",
            "_rank_value", "_rank_field",
            # ★ 2026-05-07 추가
            "mno_in", "mno_out_all", "cum_mno_in", "cum_mno_out_all",
            "total", "total_mno", "total_mvno",
            "fc_daily", "fc_low", "fc_mid", "fc_high", "fc_on_track",
            "fc_mvno_in", "fc_mno_out", "fc_mvno_out", "fc_net",
        }
        return {k: v for k, v in r.items() if k in keep and v is not None}

    lines = []
    lines.append("당신은 SK MVNO(SM) 실적 분석 전문가입니다.")
    lines.append("")
    lines.append(DATA_STRUCTURE)
    lines.append(MONTHLY_GOALS)
    lines.append(KEY_FOCUS)
    lines.append("")
    lines.append(f"## 사용자 질문\n{question}")
    lines.append(f"## AI 해석\n{spec.description}")
    lines.append(f"## 분석 의도: {spec.intent}")
    lines.append("")

    if bundle.ranking_results:
        lines.append("## 랭킹 결과 (요청 조건 상위)")
        for i, r in enumerate(bundle.ranking_results, 1):
            val = r.get("_rank_value", 0)
            lines.append(
                f"  {i}위 | {r.get('date')} ({r.get('weekday','')},{r.get('day_type','')}) "
                f"| {r.get('_rank_field')}: {val:,.0f}"
            )
        lines.append("")

    if bundle.primary:
        lines.append("## 핵심 데이터 (요청 날짜/기간)")
        lines.append(json.dumps([fmt_record(r) for r in bundle.primary],
                                 ensure_ascii=False))
        lines.append("")

    if bundle.same_weekday_history:
        lines.append("## 참고: 같은 요일 최근 이력 (요일 패턴 비교)")
        lines.append(json.dumps([fmt_record(r) for r in bundle.same_weekday_history],
                                 ensure_ascii=False))
        lines.append("")

    if bundle.recent_days:
        label = "전체 스캔 데이터 (패턴 파악용)" if spec.intent == "ranking" else "참고: 최근 흐름"
        lines.append(f"## {label}")
        lines.append(json.dumps([fmt_record(r) for r in bundle.recent_days],
                                 ensure_ascii=False))
        lines.append("")

    if bundle.holiday_context:
        lines.append("## 공휴일/영업일 맥락 (요청일 전후 ±3일)")
        for hc in bundle.holiday_context:
            delta     = hc.get("delta", 0)
            marker    = "▶ 요청일" if delta == 0 else f"  {delta:+d}일"
            day_label = (f"휴일: {hc['holiday_name']}" if hc["is_holiday"]
                         else "주말" if hc["is_weekend"] else "영업일")
            lines.append(f"  {marker} | {hc['date']} ({hc['weekday']}) | {day_label}")
        lines.append("")

    if bundle.monthly_goal and bundle.monthly_goal.get("latest_record_date"):
        mg = bundle.monthly_goal
        lines.append("## 월 현황 [DB값 직접 인용 — 자체계산 절대 금지]")
        _elapsed_bw = mg.get('elapsed_bw', 'N/A')
        _rem_bw_man = mg.get('remaining_bw_manual', 'N/A')
        _rem_bw_ai  = mg.get('remaining_bw_ai', 'N/A')
        # 전체 bw = 경과 + 잔여 (AI가 계산하면 틀림 → 여기서 직접 표시)
        try:
            _total_bw_man = round(float(_elapsed_bw) + float(_rem_bw_man), 2)
            _total_bw_ai  = round(float(_elapsed_bw) + float(_rem_bw_ai), 2)
        except Exception:
            _total_bw_man = 'N/A'
            _total_bw_ai  = 'N/A'
        lines.append(f"  기준일: {mg.get('latest_record_date')} / 경과 영업일: {mg.get('bw_elapsed_days')}일 (경과bw합계: {_elapsed_bw})")
        lines.append(f"  잔여 영업일수: 수동기준 {_rem_bw_man}일 / AI기준 {_rem_bw_ai}일")

        # [수정 20260924] "5월" 하드코딩 + SM순증감 목표(-5000) 하드코딩 버그 -
        # build_daily_fc_context()와 동일한 문제라 같은 방식으로 수정
        _latest_date = mg.get('latest_record_date') or ''
        try:
            _mg_year, _mg_month = int(_latest_date[:4]), int(_latest_date[5:7])
            _month_label = f"{_mg_month}월"
        except Exception:
            _mg_year = _mg_month = None
            _month_label = "이번달"
        try:
            from target_goal_reader import get_goals_tuple
            _, _sm_net_goal, _ = get_goals_tuple(_mg_year, _mg_month) if _mg_year else (None, -5000, None)
        except Exception:
            _sm_net_goal = -5000

        lines.append(f"  {_month_label} 전체 영업일수(bw 합계): 수동기준 {_total_bw_man}일 / AI기준 {_total_bw_ai}일")
        lines.append(f"  영업일수 기반 일평균 — T Out: {mg.get('avg_skt_per_bw','N/A')}건, SM순증감: {mg.get('avg_net_sm_per_bw','N/A')}건")

        _fc_date_label = f"({mg.get('fc_date','')} 기준)" if mg.get('fc_date') and mg.get('fc_date') != mg.get('latest_record_date') else ""
        _avg_skt = mg.get('avg_skt_per_bw', 'N/A')
        _avg_net = mg.get('avg_net_sm_per_bw', 'N/A')
        _rbw_man = mg.get('remaining_bw_manual', 'N/A')
        _rbw_ai  = mg.get('remaining_bw_ai', 'N/A')

        if mg.get("fc_mno_out"):
            _s = (mg["fc_mno_out"].get("S") or {})
            _fc_s_low = _s.get('low', 0)
            _fc_s_mid = _s.get('mid', 0)
            _track = '목표 달성 가능 ✅' if mg.get('fc_on_track') else '목표 초과 위험 ⚠️'
            lines.append(f"  {_month_label} T Out 마감 예측{_fc_date_label}: {_fc_s_low:,}~{_fc_s_mid:,}건 → {_track}")
            lines.append(f"    (현재 일평균 {_avg_skt}건/영업일수 × 잔여 영업일수 {_rbw_man}일~AI {_rbw_ai}일 기준)")
        elif mg.get("fc_low"):
            _track = '목표 달성 가능 ✅' if mg.get('fc_on_track') else '목표 초과 위험 ⚠️'
            lines.append(f"  {_month_label} T Out 마감 예측{_fc_date_label}: {mg['fc_low']:,}~{mg['fc_mid']:,}건 → {_track}")

        if mg.get("fc_net"):
            _sm = (mg["fc_net"].get("SM") or {})
            _sm_low = _sm.get('low', 0)
            _sm_mid = _sm.get('mid', 0)
            if _sm_mid:
                _net_track = '목표 달성 가능 ✅' if _sm_mid >= _sm_net_goal else '목표 초과 위험 ⚠️'
                lines.append(f"  {_month_label} SM순증감 마감 예측{_fc_date_label}: {_sm_low:,}~{_sm_mid:,}건 → {_net_track} (목표 {_sm_net_goal:+,}건 이상)")
                lines.append(f"    (현재 일평균 {_avg_net}건/영업일수 × 잔여 영업일수 {_rbw_man}일~AI {_rbw_ai}일 기준)")

        if mg.get("fc_mvno_in"):
            _sm_in = (mg["fc_mvno_in"].get("SM") or {})
            _sm_in_low = _sm_in.get('low', 0)
            _sm_in_mid = _sm_in.get('mid', 0)
            if _sm_in_mid:
                lines.append(f"  {_month_label} SM신규 마감 예측{_fc_date_label}: {_sm_in_low:,}~{_sm_in_mid:,}건")

        lines.append("  ※ 위 예측값을 그대로 인용할 것. 별도 계산값으로 대체 금지.")
        lines.append("")

    if bundle.missing_dates:
        lines.append("## 데이터 없는 날짜")
        lines.append(f"  {', '.join(bundle.missing_dates)} — 영업일 아님 또는 미수집")
        lines.append("")

    # v3.1: ktoa_events 이벤트 맥락
    if bundle.events:
        lines.append("## 주요 이벤트 (분석 기준일 ±30일)")
        lines.append("  아래 이벤트가 실적에 영향을 미쳤을 수 있으니 분석 시 반드시 참고하세요.")
        for ev in bundle.events:
            period = ev['start_date']
            if ev['end_date'] and ev['end_date'] != ev['start_date']:
                period += f" ~ {ev['end_date']}"
            impact_label = {"positive": "긍정↑", "negative": "부정↓", "neutral": "중립"}.get(
                ev.get("impact", ""), ev.get("impact", ""))
            memo = f" | {ev['memo']}" if ev.get("memo") else ""
            lines.append(
                f"  [{period}] {ev['name']} ({ev['category']}, {ev['carrier']}) "
                f"영향:{impact_label}{memo}"
            )
        lines.append("")

    # v3.8: ktoa_context 텍스트 — 계산 완료된 수치, AI는 해석만
    if hasattr(bundle, 'context_texts') and bundle.context_texts:
        lines.append("## [AI컨텍스트] 사전 계산된 확정 수치 — 재계산 금지, 해석만 할 것")
        lines.append("  아래 수치는 Python에서 계산 완료된 값. 이 값을 그대로 인용하고 해석에 집중.")
        lines.append("")
        for ct in bundle.context_texts:
            lines.append(ct['text'])
            lines.append("")
        lines.append("")

    intent_guide = {
        "query":     "요청 날짜의 실적을 핵심 수치 중심으로 간결하게. 공휴일/연휴 영향 있으면 반드시 언급.",
        "compare":   "두 시점을 수치와 함께 비교. 차이 원인(영업일·공휴일·bw 등) 추정 포함.",
        "trend":     "방향성(상승/하락/보합)과 근거. 특이 구간 언급. 예측 요청 시 bw 기반 예측값 제시.",
        "ranking":   "상위 날짜들의 공통 패턴 분석. 단순 순위 나열 외에 패턴(요일·계절·이벤트) 해석.",
        "aggregate": "집계 구간별 수치 비교. 가장 높은/낮은 구간과 원인.",
    }
    lines.append("## 답변 지침")
    lines.append(f"  - {intent_guide.get(spec.intent, '수치 중심으로 간결하게.')}")
    lines.append("  - 데이터 없는 날짜는 '해당일 데이터 없음'으로 명시. 다른 날짜 데이터로 대체 답변 금지.")
    lines.append("  - 일요일/공휴일 영업 안 함 등 당연한 사실은 설명 생략. 실적 수치와 인사이트에 집중.")
    lines.append("  - 예측/전망 요청 시: 반드시 영업일수 기반으로 두 가지 예측값 제시")
    lines.append("    ① 영업일수 기반 예측: 누적실적 + (잔여 영업일수 × 일평균)")
    lines.append("    ② AI영업일수 기반 예측: 누적실적 + (잔여 AI영업일수 × 일평균)")
    lines.append("    ※ 시스템 예측값(낮은값/중간값/높은값)도 함께 활용할 것")
    lines.append("    ※ 'bw', 'fc', '실무자 영업일수', 'SM', 'KM', 'LM' 같은 기술 용어 답변에 사용 금지")
    lines.append("    ※ SM/KM/LM 약어 그대로 사용 가능. bw, fc, 실무자 영업일수 등 기술 용어만 금지")
    lines.append("  - 명사형 종결, 200~400자, 마크다운 사용 가능.")
    lines.append(GENERAL_RESPONSE_FORMAT)

    return "\n".join(lines)


# ============================================================
# 명령어 핸들러
# ============================================================


def handle_start(chat_id):
    """시작 명령어"""
    message = """🤖 MVNO 실적 분석 봇입니다!

📊 사용 방법:
1. 일일 실적 데이터를 그대로 복사해서 보내주세요
2. 자동으로 분석하고 Firestore에 저장합니다

💡 명령어:
/start - 도움말
/recent - 최근 10개 데이터 조회
/analyze - 트렌드 분석

데이터 형식 예시:
```
◎ 01월 누적 MVNO MNP 해지
S 32,690 (19.1%)
K 60,048 (35.1%)
L 78,176 (45.7%)
계 170,914
```"""
    send_telegram_message(chat_id, message)



def handle_recent(chat_id):
    """최근 데이터 조회"""
    records = get_from_firestore(limit=None)
    
    if not records:
        send_telegram_message(chat_id, "❌ 저장된 데이터가 없습니다.")
        return
    
    message = "📊 최근 10개 데이터:\n\n"
    for record in records:
        date = record.get('date', 'N/A')
        data = record.get('data', {})
        if '누적_MVNO_MNP_해지' in data:
            mnp = data['누적_MVNO_MNP_해지']
            message += f"📅 {date}\n"
            message += f"  S: {mnp.get('S', 0):,} | K: {mnp.get('K', 0):,} | L: {mnp.get('L', 0):,}\n"
            message += f"  합계: {mnp.get('계', 0):,}\n\n"
    
    send_telegram_message(chat_id, message)
        

def classify_intent(text: str, now_year: int, now_month: int) -> dict:
    """
    Gemini로 사용자 입력의 의도(intent)를 분류.

    Returns:
        {
          "action": str,       # bw_excel / query / help / recent / data_input / ignore
          "year":   int|None,  # 연도 (해당 시)
          "month":  int|None,  # 월 (해당 시)
          "original": str,     # 원본 텍스트
        }

    액션 정의:
      bw_excel   : 영업일수 엑셀 파일 요청 ("영업일수 뽑아줘", "bw 파일 줘", "4월 영업일수")
      query      : 실적/분석 질문 ("3월 T Out 어때?", "이번달 목표 달성률?")
      help       : 도움말/기능 문의 ("/start", "뭐 할 수 있어?")
      recent     : 최근 실적 조회 ("/recent", "최근 실적 보여줘")
      data_input : 실적 데이터 직접 입력 (실적현황 포맷 감지)
      ignore     : 무시할 메시지 (공지, 광고 등)
    """
    import json, re as _re

    # 빠른 사전 필터 (Gemini 호출 전)
    # [v4.2] 세종→고고 이관 입력 — 다른 키워드와 겹치지 않아 최상단에 배치
    if text.strip().startswith('세종이관'):
        return {'action': 'sejong_migration', 'year': None, 'month': None, 'original': text}
    if text.startswith('/start') or text.startswith('/help'):
        return {'action': 'help', 'year': None, 'month': None, 'original': text}
    if text.startswith('/recent'):
        return {'action': 'recent', 'year': None, 'month': None, 'original': text}
    if any(text.strip().startswith(p) for p in ['[공지]','[안내]','[참고]','[공유]',
                                                  '(공지)','(안내)','#공지']):
        return {'action': 'ignore', 'year': None, 'month': None, 'original': text}
    if re.search(r'◎.*?(당일|누적|MNO|MVNO)', text, re.IGNORECASE):
        return {'action': 'data_input', 'year': None, 'month': None, 'original': text}
    # [v2.0] 엑셀 리포트 키워드 → report_excel (영업일수보다 먼저 체크)
    if any(kw in text for kw in ['엑셀 추출', '엑셀추출', '리포트', '실적 추출', '실적추출',
                                   '월간 리포트', '월간리포트', '전체 엑셀', '전체엑셀']):
        _m2 = re.search(r'(\d{4})[-년]\s*(\d{1,2})|(\d{1,2})월', text)
        if _m2:
            if _m2.group(1):
                _yr2, _mo2 = int(_m2.group(1)), int(_m2.group(2))
            else:
                _yr2, _mo2 = now_year, int(_m2.group(3))
        else:
            _yr2, _mo2 = now_year, now_month
        return {'action': 'report_excel', 'year': _yr2, 'month': _mo2, 'original': text}
    # 영업일수 관련 키워드 → 엑셀/파일 요청 키워드 함께 있을 때만 bw_excel, 아니면 query
    if any(kw in text for kw in ['영업일수', 'bw', 'BW', '영업가중치', '일가중치']):
        is_file_request = any(kw in text for kw in ['엑셀', '추출', '뽑아', '파일', '다운'])
        if is_file_request:
            _m = re.search(r'(\d{4})[-년]\s*(\d{1,2})|(\d{1,2})월', text)
            if _m:
                if _m.group(1):
                    _yr2, _mo2 = int(_m.group(1)), int(_m.group(2))
                else:
                    _yr2, _mo2 = now_year, int(_m.group(3))
            else:
                _yr2, _mo2 = now_year, now_month
            return {'action': 'bw_excel', 'year': _yr2, 'month': _mo2, 'original': text}
        # 파일 요청 아니면 → query로 넘김 (잔여 영업일수 조회 등)

    # Gemini 분류
    prompt = f"""당신은 MVNO 알뜰폰 팀의 AI 봇입니다.
사용자 메시지를 분석해서 의도를 JSON으로 분류하세요.

현재 날짜: {now_year}년 {now_month}월

액션 종류:
- bw_excel  : 영업일수 데이터를 엑셀 파일로 요청
  예) "영업일수 뽑아줘", "4월 bw 파일", "영업일수 엑셀", "이번달 영업일수"
- report_excel : 전체 실적 리포트 엑셀 파일 요청 (6개 시트)
  예) "엑셀 추출", "리포트 줘", "실적 뽑아줘", "월간 리포트", "전체 엑셀"
- query     : 실적/분석/예측 질문
  예) "3월 T Out 어때", "이번달 목표 달성률", "SKT 점유율 트렌드", "월마감 예측"
- recent    : 최근 실적 데이터 조회
  예) "최근 실적", "어제 실적", "오늘 데이터"
- help      : 기능/사용법 문의
  예) "뭐 할 수 있어", "어떻게 써", "도움말"
- ignore    : 응답 불필요한 메시지
  예) 단순 인사만, 무관한 잡담, 외부 공지

사용자 메시지: "{text}"

JSON만 출력 (마크다운 없이):
{{"action": "<액션>", "year": <연도 또는 null>, "month": <월 또는 null>, "reason": "<판단 근거 10자 이내>"}}

연도/월: 메시지에 특정 월 언급 시 추출, 없으면 현재월({now_year}/{now_month}) 사용"""

    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1, max_output_tokens=100
            )
        )
        raw = resp.text.strip().strip('`').replace('json','').strip()
        result = json.loads(raw)
        action = result.get('action', 'query')
        year   = result.get('year')  or now_year
        month  = result.get('month') or now_month
        print(f"Intent 분류: action={action}, {year}-{month:02d}, reason={result.get('reason','')}")
        return {'action': action, 'year': int(year), 'month': int(month), 'original': text}
    except Exception as e:
        print(f"Intent 분류 실패 (query 폴백): {e}")
        return {'action': 'query', 'year': now_year, 'month': now_month, 'original': text}



def handle_bw_excel(chat_id: str, year: int, month: int) -> None:
    """
    영업일수 엑셀 파일 생성 후 텔레그램 전송
    트리거: '영업일수' 또는 '영업일수 2026-04'
    """
    try:
        send_telegram_message(chat_id, f"📊 {year}년 {month}월 영업일수 추출 중...")
        from forecast_excel import generate_bw_excel
        path = generate_bw_excel(year, month, output_dir='/tmp')
        if not path:
            send_telegram_message(chat_id, "❌ 영업일수 파일 생성 실패")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(path, 'rb') as f:
            resp = requests.post(
                url,
                data={'chat_id': chat_id,
                      'caption': f'📊 영업일수 현황 {year}년 {month}월\n'
                                 f'실적기반 / AI예측 / 수동입력 / 최종사용'},
                files={'document': f},
                timeout=30,
            )
        if resp.json().get('ok'):
            print(f"영업일수 엑셀 전송 완료: {year}-{month:02d}")
        else:
            send_telegram_message(chat_id, f"❌ 전송 실패: {resp.json()}")
    except Exception as e:
        print(f"handle_bw_excel 오류: {e}")
        send_telegram_message(chat_id, f"❌ 오류: {e}")



def handle_report_excel(chat_id: str, year: int, month: int) -> None:
    """
    [v2.0] 전체 실적 리포트 엑셀 생성 후 텔레그램 전송 (6개 시트)
    트리거: '엑셀 추출', '리포트', '실적 뽑아줘' 등
    S1: 일마감 요약 / S2: 시간별 예측 / S3: 월별 실적
    S4: 월마감 예측 추이 / S5: 영업일수 / S6: 예측 정확도
    """
    try:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        _now_kst = _dt.now(_tz(_td(hours=9)))
        send_telegram_message(chat_id,
            f"📊 {year}년 {month}월 실적 리포트 생성 중...\n"
            f"(S1:요약 / S2:시간별 / S3:월별실적 / S4:예측추이 / S5:영업일수 / S6:정확도)")

        _is_current_month = (year == _now_kst.year and month == _now_kst.month)

        if _is_current_month:
            from forecast_excel import generate_query_report
            path = generate_query_report(output_dir='/tmp')
        else:
            # [v4.1] 과거월 요청 → 해당월 마지막 영업일 기준 확정 리포트
            from forecast_excel import generate_month_report_for
            path = generate_month_report_for(year, month, output_dir='/tmp')
            if not path:
                send_telegram_message(chat_id, f"❌ {year}년 {month}월 실적 데이터 없음")
                return

        if not path:
            send_telegram_message(chat_id, "❌ 리포트 파일 생성 실패")
            return

        # 파일명에 날짜 포함
        date_label = _now_kst.strftime('%Y-%m-%d')
        caption_basis = (
            f'기준: {date_label} (일 실적 어제까지)' if _is_current_month
            else f'기준: {year}년 {month}월 마지막 영업일 (확정 실적)'
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(path, 'rb') as f:
            resp = requests.post(
                url,
                data={
                    'chat_id': chat_id,
                    'caption': (
                        f'📊 MVNO 실적 리포트 {year}년 {month}월\n'
                        f'{caption_basis}\n'
                        f'S1:일마감요약 S2:시간별예측 S3:월별실적\n'
                        f'S4:예측추이 S5:영업일수 S6:예측정확도'
                    ),
                },
                files={'document': f},
                timeout=60,
            )

        if resp.json().get('ok'):
            print(f"실적 리포트 전송 완료: {year}-{month:02d}")
        else:
            send_telegram_message(chat_id, f"❌ 전송 실패: {resp.json()}")

    except Exception as e:
        print(f"handle_report_excel 오류: {e}")
        send_telegram_message(chat_id, f"❌ 오류: {e}")



def parse_sejong_migration_text(text: str):
    """
    '세종이관 09-05\nS 0\nK 500\nL 미확인' 형식 파싱.
    날짜 생략 시 어제 날짜로 처리 (실무자가 아침에 전일자 이관건수 입력하는 흐름).
    반환: (date_str, sm:int, km:int, lm:int|None) 또는 파싱 실패 시 None.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None

    _now_kst = _dt.now(_tz(_td(hours=9)))

    # 날짜 파싱 (첫 줄에 MM-DD 있으면 사용, 없으면 어제)
    m = re.search(r'(\d{1,2})[-./](\d{1,2})', lines[0])
    if m:
        mo, da = int(m.group(1)), int(m.group(2))
        year = _now_kst.year
        # 12월 입력인데 현재 1월이면 작년으로 보정 (연말/연초 경계)
        if mo == 12 and _now_kst.month == 1:
            year -= 1
        date_str = f'{year:04d}-{mo:02d}-{da:02d}'
    else:
        yesterday = _now_kst - _td(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')

    vals = {'S': None, 'K': None, 'L': None}
    for line in lines[1:]:
        mm = re.match(r'^([SKL])\s*[:：]?\s*(.+)$', line, re.IGNORECASE)
        if not mm:
            continue
        key = mm.group(1).upper()
        raw = mm.group(2).strip()
        if raw in ('미확인', '-', 'x', 'X', ''):
            vals[key] = None
        else:
            num = re.sub(r'[^\d]', '', raw)
            vals[key] = int(num) if num else None

    # S/K는 미확인이어도 0으로 (합계 계산 필요), L만 None 허용 (미확인 표시 유지)
    sm = vals['S'] if vals['S'] is not None else 0
    km = vals['K'] if vals['K'] is not None else 0
    lm = vals['L']  # None 그대로 허용

    return date_str, sm, km, lm


def handle_sejong_migration(chat_id, text):
    """세종→고고 이관 입력 처리 → 보정 마감 메시지 생성/발송"""
    import ktoa_firestore
    import ktoa_telegram

    parsed = parse_sejong_migration_text(text)
    if not parsed:
        send_telegram_message(chat_id,
            "❌ 형식을 인식할 수 없습니다.\n\n사용법:\n세종이관 09-05\nS 0\nK 500\nL 미확인")
        return

    date_str, sm, km, lm = parsed

    daily = ktoa_firestore.get_daily(date_str)
    if not daily:
        send_telegram_message(chat_id, f"❌ {date_str} 마감 데이터가 아직 없습니다. 날짜를 확인해주세요.")
        return

    migration = ktoa_firestore.save_sejong_migration(date_str, sm, km, lm)
    prev_daily = ktoa_firestore.get_previous_daily_for_closing(date_str)

    msg = ktoa_telegram.build_sejong_correction_message(daily, migration, prev_daily)
    send_telegram_message(chat_id, msg)

    # [v4.3] 기존 마감 리포트 방에도 동일 메시지 추가 발송
    existing_report_chat_id = os.environ.get('TELEGRAM_CHAT_ID', '-5078644105')
    if str(existing_report_chat_id) != str(chat_id):
        send_telegram_message(existing_report_chat_id, msg)


def handle_message(chat_id, text):
    """일반 메시지 처리"""

    # ✅ 실적봇 메시지 자동 감지 (가장 먼저 체크!)
    if 'from_user' in globals() and hasattr(globals()['from_user'], 'username'):
        # Webhook에서 from_user 정보 추출 필요
        pass
    
    # 실적봇 메시지 확인 - username 체크
    # (이 부분은 webhook 함수에서 처리하는 게 더 정확함)

    
    # 🔕 무시할 메시지 키워드
    ignore_keywords = ['공지', '안내', '참고', '공유']
    
    # 자동으로 다양한 패턴 생성
    ignore_patterns = []
    for keyword in ignore_keywords:
        ignore_patterns.extend([
            f'[{keyword}]',
            f'[{keyword}',
            f'({keyword})',
            f'({keyword}',
            f'#{keyword}',
            f'##{keyword}',
            f'<{keyword}>',
        ])
    
    # 무시 패턴에 해당하면 응답 안함
    if any(text.strip().startswith(pattern) for pattern in ignore_patterns):
        return


    # MVNO 데이터인지 확인
    if re.search(r'◎.*?(당일|누적|MNO|MVNO)', text, re.IGNORECASE):
        # 1. 먼저 "분석 중" 메시지 전송
        send_telegram_message(chat_id, "📊 실적 분석 중...")
        
        # 시작 시간 기록
        start_time = datetime.now()
        
        # 2. 데이터 파싱
        parsed = parse_mvno_data(text)
        
        if parsed:
            # ⚠️ 일요일 체크
            if parsed.get('weekday') == '일요일':
                warning = "⚠️ **일요일 데이터입니다!**\n일요일은 영업을 하지 않으므로 데이터 확인이 필요합니다.\n\n"
            else:
                warning = ""

            # [v3.1] ktoa_daily 자동 수집으로 저장 대체 — 저장 없이 분석만 수행
            historical = get_from_firestore(limit=100)
            analysis = analyze_with_gemini(text, historical)

            response_time = (datetime.now() - start_time).total_seconds()
            save_analysis_log(chat_id, parsed.get('date'), analysis, response_time)

            date_obj = datetime.strptime(parsed.get('date', ''), '%Y-%m-%d')
            formatted_date = f"'{date_obj.strftime('%y.%m')}월{date_obj.day}일 ({parsed.get('weekday', '')},{parsed.get('day_type', '')})"
            response = f"{warning}✅ {formatted_date}\n\n{analysis}"
            send_telegram_message(chat_id, response)
            
        else:
            send_telegram_message(chat_id, "❌ 데이터 형식을 인식할 수 없습니다. /start로 형식을 확인하세요.")
    
    # ✅ 피드백 명령어 (질문보다 먼저 체크)
    elif text.startswith('/feedback') or text.startswith('/피드백'):
        feedback = text.replace('/feedback', '').replace('/피드백', '').strip()
        if feedback:
            success, msg = save_feedback(chat_id, feedback)
            if success:
                send_telegram_message(chat_id, "✅ 피드백이 저장되었습니다. 다음 분석에 반영하겠습니다!")
            else:
                send_telegram_message(chat_id, f"❌ 피드백 저장 실패: {msg}")
        else:
            send_telegram_message(chat_id, "💡 사용법: /feedback [의견]\n\n예시:\n- /feedback 경쟁사 비교를 더 자세히 해주세요\n- /feedback T Out 분석이 좋았어요")
    
    # ✅ 질문인지 확인 (피드백보다 우선)
    elif '?' in text or any(keyword in text for keyword in ['어때', '어떻게', '어땠', '어떰', '어떠냐', '어떤지', '비교', '예상', '분석', '언제', '얼마', '평균', '추이', '트렌드', '실적', '데이터', '예측', '전망', '몇건', '몇 건', '알려줘', '보여줘', '해줘', '많은', '적은', '높은', '낮은', '순위', '랭킹']):
        handle_query(chat_id, text)
    
    # ✅ 자연스러운 피드백 감지 (가장 마지막)
    elif any(word in text for word in ['좋았어', '너무 좋아', '부족해', '더 해줘', '추가해줘', '빼줘', '개선해줘', '아쉬워']):
        save_feedback(chat_id, text)
        send_telegram_message(chat_id, "✅ 피드백이 저장되었습니다. 다음 분석에 반영하겠습니다!")
    
    else:
        # 일반 대화
        send_telegram_message(chat_id, "안녕하세요! MVNO 실적 데이터를 보내주시거나 질문해주세요.\n\n💡 팁:\n- 질문: '지난주 실적은?'\n- 피드백: /feedback [의견]")

        
# ============================================
# Flask 라우트
# ============================================
@app.route('/webhook', methods=['POST'])
def webhook():
    """텔레그램 webhook"""
    try:
        update = request.get_json()
        
        # ✅ 채널 메시지 처리 (최우선!)
        if 'channel_post' in update:
            message = update['channel_post']
            chat_id = message['chat']['id']
            text = message.get('text', '')
            
            print(f"📢 채널 메시지 수신: {text[:50]}...")
            
            # "실적 현황 보고" 메시지 확인
            if "실적 현황 보고" in text:
                date_match = re.search(r'실적 현황 보고[_\s]*(\d{4})', text)
                if date_match:
                    report_date = date_match.group(1)
                    
                    if report_date in processed_today:
                        print(f"⏭️ {report_date} 이미 처리됨")
                        return jsonify({'ok': True})
                    
                    print(f"✅ 채널에서 실적 데이터 감지: {report_date}")
                    
                    send_telegram_message(chat_id, "📊 실적 분석 중...")
                    start_time = datetime.now()
                    
                    parsed = parse_mvno_data(text)
                    
                    if parsed:
                        warning = ""
                        if parsed.get('weekday') == '일요일':
                            warning = "⚠️ **일요일 데이터입니다!**\n일요일은 영업을 하지 않으므로 데이터 확인이 필요합니다.\n\n"
                        
                        success, msg = save_to_firestore(parsed)
                        historical = get_from_firestore(limit=100)
                        analysis = analyze_with_gemini(text, historical)
                        
                        response_time = (datetime.now() - start_time).total_seconds()
                        save_analysis_log(chat_id, parsed.get('date'), analysis, response_time)
                        
                        response = f"{warning}✅ {msg}\n\n{analysis}"
                        send_telegram_message(chat_id, response)
                        
                        processed_today.add(report_date)
                        print(f"✅ {report_date} 채널 분석 완료")
                    
                    return jsonify({'ok': True})
        
        # 기존 그룹 메시지 처리
        if 'message' not in update:
            return jsonify({'ok': True})
        
        message = update['message']
        chat_id = message['chat']['id']
        
        
        
        # 텍스트 처리
        if 'text' not in message:
            return jsonify({'ok': True})
        
        text = message['text']
        
        # ── Gemini intent 분류 → 자연어 라우팅
        from datetime import datetime as _dt2, timezone as _tz, timedelta as _td2
        _now_kst = _dt2.now(_tz(_td2(hours=9)))
        _now_yr, _now_mo = _now_kst.year, _now_kst.month

        intent = classify_intent(text, _now_yr, _now_mo)
        _action = intent['action']
        _yr     = intent['year']
        _mo     = intent['month']

        if _action == 'sejong_migration':
            # 지정된 방에서만 동작 (다른 방 오탐 방지)
            if str(chat_id) == str(SEJONG_MIG_CHAT_ID):
                handle_sejong_migration(chat_id, text)
            # 다른 방이면 무시 (기존 동작에 영향 없음)
        elif _action == 'help':
            handle_start(chat_id)
        elif _action == 'recent':
            handle_recent(chat_id)
        elif _action == 'bw_excel':
            handle_bw_excel(chat_id, _yr, _mo)
        elif _action == 'report_excel':
            handle_report_excel(chat_id, _yr, _mo)
        elif _action == 'ignore':
            pass  # 무시
        else:
            # query / data_input / 기타 → 기존 handle_message
            handle_message(chat_id, text)
        
        return jsonify({'ok': True})
    
    except Exception as e:
        print(f"Webhook 에러: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/setup', methods=['GET'])
def setup():
    """Webhook 설정"""
    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
        data = {"url": webhook_url}
        
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return f"✅ Webhook 설정 완료: {webhook_url}"
        else:
            return f"❌ Webhook 설정 실패: {result}", 500
    
    except Exception as e:
        return f"❌ 에러: {e}", 500



@app.route('/trigger-daily-analysis', methods=['POST'])
def trigger_daily_analysis():
    """Cloud Scheduler가 20:03에 호출 → ktoa_daily 읽어서 Gemini 분석 후 텔레그램 전송"""
    try:
        # 보안: TRIGGER_SECRET 검증
        trigger_secret = os.environ.get('TRIGGER_SECRET', '')
        if trigger_secret:
            auth_header = request.headers.get('Authorization', '')
            if auth_header != f'Bearer {trigger_secret}':
                print("❌ 인증 실패")
                return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

        # 텔레그램 채팅방 ID (ktoa-collector와 동일)
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '-5078644105')

        # 날짜 결정: body에 date 있으면 그걸 사용, 없으면 오늘 (KST)
        kst_now = get_kst_now()
        body = request.get_json(silent=True) or {}
        today_str = body.get('date', kst_now.strftime('%Y-%m-%d'))
        print(f"🕗 일마감 자동 분석 시작: {today_str}")

        # ktoa_daily에서 오늘 데이터 조회
        if not db:
            return jsonify({'ok': False, 'error': 'Firestore 연결 안 됨'}), 500

        doc = db.collection('ktoa_daily').document(today_str).get()
        if not doc.exists:
            msg = f"❌ {today_str} 일마감 데이터 없음 (ktoa_daily)"
            print(msg)
            send_telegram_message(chat_id, msg)
            return jsonify({'ok': False, 'error': msg}), 404

        ktoa_data = doc.to_dict()
        print(f"✅ ktoa_daily 데이터 조회 완료: {today_str}")
        print(f"  필드 목록: {list(ktoa_data.keys())}")

        # ── v3.3: 주말/공휴일 실적 0인 날 분석 스킵 ──────────────
        _total_in  = ktoa_data.get('mvno_in',  {}).get('계', 0)
        _total_mno = ktoa_data.get('mno_out',  {}).get('계', 0)
        if _total_in == 0 and _total_mno == 0:
            print(f"⏭ {today_str} 실적 0 (주말/공휴일) — 일마감 분석 스킵")
            return jsonify({'ok': True, 'skipped': True, 'reason': '실적 0 (주말/공휴일)'})
        # ────────────────────────────────────────────────────────────

        # ── [v3.15] 토요일/월말 분기: 주간/월간 리포트로 대체 ─────────
        try:
            _date_obj_branch = datetime.strptime(today_str, '%Y-%m-%d')
            _is_saturday = (_date_obj_branch.weekday() == 5)

            _is_month_end = False
            try:
                from bw_engine import is_zero_day
                from calendar import monthrange as _mr_branch
                _y, _m, _d = _date_obj_branch.year, _date_obj_branch.month, _date_obj_branch.day
                _last_day = _mr_branch(_y, _m)[1]
                _is_month_end = not any(
                    not is_zero_day(f"{_y:04d}-{_m:02d}-{dd:02d}")
                    for dd in range(_d + 1, _last_day + 1)
                )
            except Exception as _me_e:
                print(f"[월말판단] 실패 (무시, 평일 처리): {_me_e}")

            if _is_month_end:
                print(f"=== 월말 처리 모드: {today_str} ===")
                _y, _m = _date_obj_branch.year, _date_obj_branch.month

                # 월별 context 생성 보장 (ktoa_scraper 20:01에서 이미 생성 시도하지만 재확인)
                try:
                    from ktoa_context_period_builder import save_monthly_context, get_period_context
                    save_monthly_context(_y, _m)
                    _ctx_results = get_period_context('monthly', today_str)
                except Exception as _pc_e:
                    print(f"[월말] 월별 context 조회 실패: {_pc_e}")
                    _ctx_results = []

                if _ctx_results:
                    _month_text = "\n\n".join(c['text'] for c in _ctx_results)
                    send_telegram_message(chat_id, "📦 월마감 자동 분석 중...")
                    _start_m = datetime.now()
                    _force_claude_m = body.get('force_claude', False)
                    _historical_m = get_from_firestore()
                    _analysis_m, _api_name_m = analyze_period(_month_text, f"{_y}년 {_m}월 월마감", _historical_m, force_claude=_force_claude_m)
                    _rt_m = (datetime.now() - _start_m).total_seconds()
                    save_analysis_log(chat_id, today_str, _analysis_m, _rt_m)

                    _response_m = f"✅ {_y}년 {_m}월 월마감, {_api_name_m} 분석\n\n{_analysis_m}"
                    send_telegram_message(chat_id, _response_m)
                else:
                    send_telegram_message(chat_id, f"⚠️ {_y}년 {_m}월 월별 context 없음 — 월마감 분석 스킵")

                # 월마감 확정 엑셀 생성 + 전송
                try:
                    from forecast_excel import generate_month_closing_report, build_excel_caption
                    _excel_path_m = generate_month_closing_report(today_str, ktoa_data, output_dir='/tmp')
                    if _excel_path_m:
                        _caption_m = build_excel_caption(today_str, ktoa_data, is_month_closing=True)
                        _url_m = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
                        with open(_excel_path_m, 'rb') as _f_m:
                            _resp_m = requests.post(
                                _url_m,
                                data={'chat_id': chat_id, 'caption': _caption_m},
                                files={'document': _f_m},
                                timeout=60,
                            )
                        if not _resp_m.json().get('ok'):
                            send_telegram_message(chat_id, f"❌ 월마감 엑셀 전송 실패: {_resp_m.json()}")
                    else:
                        print("[월말] 월마감 엑셀 생성 실패 (경로 없음)")
                except Exception as _excel_e:
                    print(f"[월말] 월마감 엑셀 생성/전송 실패 (무시): {_excel_e}")

                print(f"✅ 월마감 자동 처리 완료: {today_str}")
                return jsonify({'ok': True, 'date': today_str, 'mode': 'month_end'})

            if _is_saturday:
                print(f"=== 주간 리포트 처리 모드: {today_str} ===")
                try:
                    from ktoa_context_period_builder import save_weekly_context, get_period_context
                    save_weekly_context(today_str)
                    _ctx_results_w = get_period_context('weekly', today_str)
                except Exception as _pc_we:
                    print(f"[주간] 주간 context 조회 실패: {_pc_we}")
                    _ctx_results_w = []

                if _ctx_results_w:
                    _week_text = "\n\n".join(c['text'] for c in _ctx_results_w)
                    send_telegram_message(chat_id, "📅 주간 자동 분석 중...")
                    _start_w = datetime.now()
                    _force_claude_w = body.get('force_claude', False)
                    _historical_w = get_from_firestore()
                    _analysis_w, _api_name_w = analyze_period(_week_text, f"{today_str} 기준 주간마감", _historical_w, force_claude=_force_claude_w)
                    _rt_w = (datetime.now() - _start_w).total_seconds()
                    save_analysis_log(chat_id, today_str, _analysis_w, _rt_w)

                    _response_w = f"✅ 주간 마감, {_api_name_w} 분석\n\n{_analysis_w}"
                    send_telegram_message(chat_id, _response_w)
                else:
                    send_telegram_message(chat_id, "⚠️ 주간 context 없음 — 주간 분석 스킵")

                print(f"✅ 주간 자동 처리 완료: {today_str}")
                return jsonify({'ok': True, 'date': today_str, 'mode': 'weekly'})
        except Exception as _branch_e:
            print(f"[토요일/월말 분기] 실패 (무시, 일간 분석으로 진행): {_branch_e}")
        # ────────────────────────────────────────────────────────────

        # ktoa_daily 구조: 중첩 없이 최상위 레벨에 바로 존재
        mvno_in  = ktoa_data.get('mvno_in',  {})
        mvno_out = ktoa_data.get('mvno_out', {})
        mno_out  = ktoa_data.get('mno_out',  {})
        net      = ktoa_data.get('net_change', {})

        cum_in   = ktoa_data.get('cum_mvno_in',  {})
        cum_out  = ktoa_data.get('cum_mvno_out', {})
        cum_mno  = ktoa_data.get('cum_mno_out',  {})
        cum_net  = ktoa_data.get('cum_net',      {})

        date_obj = kst_now
        mmdd = date_obj.strftime('%m%d')

        def fmt(v): return f"{int(v):,}" if v else "0"

        total_in  = mvno_in.get('계', 0)
        s_in_pct  = (mvno_in.get('SM', 0) / total_in * 100) if total_in else 0
        k_in_pct  = (mvno_in.get('KM', 0) / total_in * 100) if total_in else 0
        l_in_pct  = (mvno_in.get('LM', 0) / total_in * 100) if total_in else 0

        total_mno = mno_out.get('계', 0)
        s_mno_pct = (mno_out.get('S', 0) / total_mno * 100) if total_mno else 0
        k_mno_pct = (mno_out.get('K', 0) / total_mno * 100) if total_mno else 0
        l_mno_pct = (mno_out.get('L', 0) / total_mno * 100) if total_mno else 0

        total_out  = mvno_out.get('계', 0)
        s_out_pct  = (mvno_out.get('SM', 0) / total_out * 100) if total_out else 0
        k_out_pct  = (mvno_out.get('KM', 0) / total_out * 100) if total_out else 0
        l_out_pct  = (mvno_out.get('LM', 0) / total_out * 100) if total_out else 0

        cum_in_total = cum_in.get('계', 0)
        def cum_k(d, key): return int(d.get(key, 0) / 1000) if d.get(key, 0) >= 1000 else d.get(key, 0)

        month = date_obj.month

        text_for_analysis = f"""■ 실적 현황 보고_{mmdd}
◎ 당일 마감
S {fmt(mvno_in.get('SM',0))} ({s_in_pct:.1f}%)
K {fmt(mvno_in.get('KM',0))} ({k_in_pct:.1f}%)
L {fmt(mvno_in.get('LM',0))} ({l_in_pct:.1f}%)
계 {fmt(total_in)}
◎ {month:02d}월 누적
S {cum_in.get('SM',0)/1000:.1f}천({(cum_in.get('SM',0)/cum_in_total*100) if cum_in_total else 0:.1f}%)
K {cum_in.get('KM',0)/1000:.1f}천({(cum_in.get('KM',0)/cum_in_total*100) if cum_in_total else 0:.1f}%)
L {cum_in.get('LM',0)/1000:.1f}천({(cum_in.get('LM',0)/cum_in_total*100) if cum_in_total else 0:.1f}%)
계 {cum_in_total/1000:.1f}천
◎ {month:02d}월 당일 MNO Out
S {fmt(mno_out.get('S',0))} ({s_mno_pct:.1f}%)
K {fmt(mno_out.get('K',0))} ({k_mno_pct:.1f}%)
L {fmt(mno_out.get('L',0))} ({l_mno_pct:.1f}%)
계 {fmt(total_mno)}
◎ {month:02d}월 누적 MNO Out
S {cum_mno.get('S',0)/1000:.1f}천({(cum_mno.get('S',0)/cum_mno.get('계',1)*100) if cum_mno.get('계',0) else 0:.1f}%)
K {cum_mno.get('K',0)/1000:.1f}천({(cum_mno.get('K',0)/cum_mno.get('계',1)*100) if cum_mno.get('계',0) else 0:.1f}%)
L {cum_mno.get('L',0)/1000:.1f}천({(cum_mno.get('L',0)/cum_mno.get('계',1)*100) if cum_mno.get('계',0) else 0:.1f}%)
계 {cum_mno.get('계',0)/1000:.1f}천
◎ {month:02d}월 당일 순증감
S {net.get('SM',0):+,} 
K {net.get('KM',0):+,} 
L {net.get('LM',0):+,} 
계 {net.get('계',0):+,}
◎ {month:02d}월 누적 순증감
S {cum_net.get('SM',0):+,} 
K {cum_net.get('KM',0):+,} 
L {cum_net.get('LM',0):+,} 
계 {cum_net.get('계',0):+,}
◎ {month:02d}월 당일 MVNO MNP 해지
S {fmt(mvno_out.get('SM',0))} ({s_out_pct:.1f}%)
K {fmt(mvno_out.get('KM',0))} ({k_out_pct:.1f}%)
L {fmt(mvno_out.get('LM',0))} ({l_out_pct:.1f}%)
계 {fmt(total_out)}
◎ {month:02d}월 누적 MVNO MNP 해지
S {fmt(cum_out.get('SM',0))}
K {fmt(cum_out.get('KM',0))}
L {fmt(cum_out.get('LM',0))}
계 {fmt(cum_out.get('계',0))}"""

        # 분석 시작 메시지
        send_telegram_message(chat_id, "📊 일마감 자동 분석 중...")
        start_time = datetime.now()

        # 기존 parse → save → 분석 흐름 재사용
        parsed = parse_mvno_data(text_for_analysis)
        if parsed:
            save_to_firestore(parsed)

        historical = get_from_firestore()

        # "gemini분석"/"제미나이 분석" 키워드 확인 (body에 force_gemini 파라미터)
        force_claude = body.get('force_claude', False)

        # ★ ktoa_context 없으면 생성 (일마감 분석 전 보장)
        try:
            from ktoa_context_builder import save_context_message, get_context_texts
            _existing = get_context_texts(today_str, days=1)
            if not _existing:
                print(f"ktoa_context 없음 → 생성 시작: {today_str}")
                _daily_for_ctx = db.collection('ktoa_daily').document(today_str).get()
                if _daily_for_ctx.exists:
                    save_context_message(today_str, _daily_for_ctx.to_dict())
                    print(f"ktoa_context 생성 완료: {today_str}")
        except Exception as _ctx_pre_e:
            print(f"ktoa_context 사전 생성 실패 (무시): {_ctx_pre_e}")

        # ★ fc/bw 컨텍스트 + 최근추세 + 시장동향(요금제/오프라인정책) 컨텍스트를
        # text_for_analysis 뒤에 순서대로 삽입 (사장님 피드백: 당일값만이 아니라
        # 최근추세 대비 해석, 요금제/오프라인 동향과 실적 연계 필요)
        fc_context = build_daily_fc_context(today_str)
        trend_context = build_ktoa_context_summary(today_str)
        market_context = build_market_context(today_str)
        text_with_fc = text_for_analysis
        for extra in (fc_context, trend_context, market_context):
            if extra:
                text_with_fc += "\n" + extra

        analysis, api_name = analyze_auto(text_with_fc, historical, force_claude=force_claude)

        response_time = (datetime.now() - start_time).total_seconds()
        save_analysis_log(chat_id, today_str, analysis, response_time)

        # 날짜 포맷: '26.03월17일 (화요일,평일)
        import holidays as _holidays
        from datetime import date as _date
        date_obj2 = datetime.strptime(today_str, '%Y-%m-%d')
        weekday_kr = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][date_obj2.weekday()]
        kr_holidays = _holidays.KR()
        date_val = _date(date_obj2.year, date_obj2.month, date_obj2.day)
        is_holiday = date_val in kr_holidays
        is_weekend = date_val.weekday() >= 5
        day_type = '공휴일' if is_holiday else ('주말' if is_weekend else '평일')
        formatted_date = f"'{date_obj2.strftime('%y.%m')}월{date_obj2.day}일 ({weekday_kr},{day_type})"

        # 고중요도(★3개) 커뮤니티 게시글 링크 - Gemini 분석과 별개로 코드에서
        # 직접 추출해 첨부 (URL 재작성/변형 위험 없이 원본 그대로)
        link_footer = ""
        try:
            hot_link = get_hot_community_link(today_str)
            if hot_link:
                link_footer = f"\n\n🔗 동향확인: {hot_link['title']}"
                if hot_link.get("views"):
                    link_footer += f" (조회 {hot_link['views']:,})"
                link_footer += f"\n{hot_link['url']}"
        except Exception as _link_e:
            print(f"[trigger_daily_analysis] 동향 링크 첨부 실패 (무시): {_link_e}")

        # 기존 채팅방: 분석 결과 전송
        response = f"✅ {formatted_date}, {api_name} 분석\n\n{analysis}{link_footer}"
        send_telegram_message(chat_id, response)

        # ANALYSIS_CHAT_ID 중복 전송 제거 (v3.9: TELEGRAM_CHAT_ID를 -5078644105로 통합)

        print(f"✅ 일마감 자동 분석 완료 ({response_time:.1f}초)")
        return jsonify({'ok': True, 'date': today_str})

    except Exception as e:
        print(f"❌ trigger_daily_analysis 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """헬스 체크"""
    return jsonify({
        'status': 'healthy',
        'service': 'MVNO Analysis Bot',
        'firestore': 'connected' if db else 'disconnected',
        'timestamp': get_kst_str(),
        'timezone': 'Asia/Seoul (KST, UTC+9)'
    })



@app.route('/', methods=['GET'])
def index():
    """루트"""
    return '🤖 MVNO Bot is running on Cloud Run!'



# ============================================================


# main.py 맨 아래
if __name__ == '__main__':
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone='Asia/Seoul')

    scheduler.add_job(
        func=lambda: processed_today.clear(),
        trigger='cron',
        hour=0,
        minute=0
    )

    scheduler.start()

    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
@app.route('/debug-monthly', methods=['GET'])
def debug_monthly():
    from forecast_engine import predict_monthly
    result = predict_monthly('2026-05-07', 953, current_hour=15)
    return jsonify(result)