#!/usr/bin/env python3
"""
MVNO 실적 분석 텔레그램 봇 (Cloud Run) - 안정적인 버전
"""

from google.cloud import vision
import io
from PIL import Image
from datetime import timedelta

from datetime import datetime, date, timezone, timedelta
import holidays
import functools

import os
import re
import json

from config import DATA_STRUCTURE, MONTHLY_GOALS, KEY_FOCUS, DAILY_RESPONSE_FORMAT, GENERAL_RESPONSE_FORMAT
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.cloud import firestore
import requests

# 환경 변수
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# Gemini 설정
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')


# Firestore 초기화
try:
    db = firestore.Client(project='mvno-484509', database='mvno-data')
    print("✅ Firestore 연결 성공")
except Exception as e:
    print(f"❌ Firestore 연결 실패: {e}")
    db = None

# Flask 앱
app = Flask(__name__)


# ============================================
# 유틸리티 함수
# ============================================
def get_kst_now():
    """한국 시간(KST) 반환"""
    return datetime.now(timezone(timedelta(hours=9)))

def get_kst_str():
    """한국 시간 문자열 반환 (YYYY-MM-DD HH:MM:SS)"""
    return get_kst_now().strftime('%Y-%m-%d %H:%M:%S')
    
def send_telegram_message(chat_id, text):
    """텔레그램 메시지 전송 (동기식)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
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
    """Firestore에 데이터 저장 - 기존 데이터 업데이트 지원"""
    if not db:
        return False, "Firestore 연결 안 됨"
    
    try:
        doc_id = data['date']
        collection_ref = db.collection('mvno_records')
        doc_ref = collection_ref.document(doc_id)
        
        # 기존 문서 확인
        existing_doc = doc_ref.get()
        
        if existing_doc.exists:
            # 기존 데이터와 병합
            existing_data = existing_doc.to_dict()
            
            # 기존 데이터의 항목과 새 데이터 병합
            if 'data' in existing_data:
                existing_data['data'].update(data['data'])
                data['data'] = existing_data['data']
            
            # 업데이트
            doc_ref.set(data, merge=True)
            
            # 날짜 포맷팅 - '26.12월29일 (수요일,평일) 형식
            date_obj = datetime.strptime(doc_id, '%Y-%m-%d')
            formatted_date = f"'{date_obj.strftime('%y.%m')}월{date_obj.day}일 ({data.get('weekday', '')},{data.get('day_type', '')})"
            
            return True, formatted_date
        else:
            # 새 문서 생성
            doc_ref.set(data)
            
            # 날짜 포맷팅
            date_obj = datetime.strptime(doc_id, '%Y-%m-%d')
            formatted_date = f"'{date_obj.strftime('%y.%m')}월{date_obj.day}일 ({data.get('weekday', '')},{data.get('day_type', '')})"
            
            return True, formatted_date
    
    except Exception as e:
        return False, f"❌ 저장 실패: {e}"

    
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

def get_from_firestore(date=None, limit=None):
    """Firestore에서 데이터 조회"""
    if not db:
        print("❌ Firestore DB 없음")
        return []
    
    try:
        collection_ref = db.collection('mvno_records')
        
        if date:
            doc = collection_ref.document(date).get()
            result = [doc.to_dict()] if doc.exists else []
            print(f"🔍 단일 조회: {date} → {len(result)}건")
            return result
        else:
            # 🔧 수정: limit이 None이면 전체 조회
            query = collection_ref.order_by('date', direction=firestore.Query.DESCENDING)
            
            if limit is not None and limit > 0:
                query = query.limit(limit)
                print(f"🔍 Firestore 조회 (limit={limit})")
            else:
                print(f"🔍 Firestore 조회 (전체)")
            
            docs = query.stream()
            result = [doc.to_dict() for doc in docs]
            
            print(f"✅ 조회 완료: {len(result)}건")
            
            # 🔧 디버깅: 첫 2개 레코드의 필드명 출력
            if result:
                for i, record in enumerate(result[:2]):
                    date_str = record.get('date', 'N/A')
                    print(f"  [{i+1}] {date_str}")
                    if 'data' in record:
                        mno_keys = [k for k in record['data'].keys() if 'MNO' in k]
                        if mno_keys:
                            print(f"      MNO 필드: {mno_keys}")
            
            return result
    except Exception as e:
        print(f"❌ 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        return []
        
# ============================================
# 캐싱 함수
# ============================================

_cache_timestamp = None
_cached_data = None
_qa_cache = {}

def get_all_data_cached():
    """전체 데이터 조회 (5분 캐싱)"""
    global _cache_timestamp, _cached_data
    now = datetime.now()
    
    # 캐시 확인
    if _cached_data and _cache_timestamp:
        age = (now - _cache_timestamp).seconds
        if age < 300:
            print(f"📦 캐시 반환 (age: {age}초, {len(_cached_data)}건)")
            return _cached_data
    
    print("🔄 Firestore 새로 조회")
    _cached_data = get_from_firestore(limit=None)
    _cache_timestamp = now
    
    print(f"✅ 조회 완료: {len(_cached_data)}건")
    
    # 🔧 디버깅: 첫 3개 데이터의 필드명 확인
    if _cached_data:
        for i, record in enumerate(_cached_data[:3]):
            print(f"  레코드 {i+1}: {record.get('date')}")
            if 'data' in record:
                keys = list(record['data'].keys())
                print(f"    필드: {keys}")
    
    return _cached_data

def get_monthly_summary_data(all_data):
    """각 월 마지막 날 누적 데이터 추출"""
    monthly = {}
    for record in all_data:
        year = record.get('year')
        month = record.get('month')
        day = record.get('day')
        if not all([year, month, day]):
            continue
        key = f"{year}-{month:02d}"
        if key not in monthly or day > monthly[key]['day']:
            monthly[key] = record
    sorted_monthly = sorted(monthly.values(), key=lambda x: x.get('date'))
    print(f"📅 월별 요약: {len(sorted_monthly)}개월")
    return sorted_monthly

def get_10day_summary_data(all_data, year, month):
    """순기별 데이터 추출 (1~10일, 11~20일, 21~말일)"""
    import calendar
    
    # 해당 월 데이터만 필터링
    monthly_data = [d for d in all_data 
                   if d.get('year') == year and d.get('month') == month]
    
    if not monthly_data:
        print(f"❌ {year}년 {month}월 데이터 없음")
        return []
    
    # 날짜순 정렬
    monthly_data.sort(key=lambda x: x.get('day', 0))
    
    print(f"📊 {year}년 {month}월 데이터: {len(monthly_data)}일치")
    
    # 각 순기 마지막 날 찾기 (가장 가까운 날)
    day10 = None
    day20 = None
    day_last = None
    
    # 1~10일 중 가장 마지막 날
    for record in monthly_data:
        day = record.get('day')
        if 1 <= day <= 10:
            if not day10 or day > day10.get('day'):
                day10 = record
    
    # 11~20일 중 가장 마지막 날
    for record in monthly_data:
        day = record.get('day')
        if 11 <= day <= 20:
            if not day20 or day > day20.get('day'):
                day20 = record
    
    # 21일~말일 중 가장 마지막 날
    last_day_of_month = calendar.monthrange(year, month)[1]
    for record in monthly_data:
        day = record.get('day')
        if 21 <= day <= last_day_of_month:
            if not day_last or day > day_last.get('day'):
                day_last = record
    
    print(f"  1순기 마지막: {day10.get('day') if day10 else 'None'}일")
    print(f"  2순기 마지막: {day20.get('day') if day20 else 'None'}일")
    print(f"  3순기 마지막: {day_last.get('day') if day_last else 'None'}일")
    
    result = []
    
    # 1순기 (1~10일)
    if day10:
        period1 = day10.copy()
        period1['period_name'] = f'1순기 (1~{day10.get("day")}일)'
        period1['period_type'] = '10day'
        period1['display_date'] = f"{year}-{month:02d}-{day10.get('day'):02d}"
        result.append(period1)
    
    # 2순기 (11~20일) = 20일 누적 - 10일 누적
    if day20 and day10:
        period2 = day20.copy()
        period2['period_name'] = f'2순기 ({day10.get("day")+1}~{day20.get("day")}일)'
        period2['period_type'] = '10day'
        period2['display_date'] = f"{year}-{month:02d}-{day20.get('day'):02d}"
        
        # 데이터 차이 계산
        if 'data' in period2 and 'data' in day10:
            new_data = {}
            for key, value in period2['data'].items():
                if key.startswith('누적_'):
                    # 누적 데이터만 차이 계산
                    if key in day10['data']:
                        if isinstance(value, dict):
                            new_data[key] = {}
                            for k, v in value.items():
                                base = day10['data'][key].get(k, 0)
                                new_data[key][k] = v - base
                        else:
                            new_data[key] = value - day10['data'][key]
                    else:
                        new_data[key] = value
                # 당일 데이터는 그대로 (의미 없음)
            period2['data'] = new_data
        
        result.append(period2)
    
    # 3순기 (21~말일) = 말일 누적 - 20일 누적
    if day_last:
        if day20:
            period3 = day_last.copy()
            period3['period_name'] = f'3순기 ({day20.get("day")+1}~{day_last.get("day")}일)'
            period3['period_type'] = '10day'
            period3['display_date'] = f"{year}-{month:02d}-{day_last.get('day'):02d}"
            
            # 데이터 차이 계산
            if 'data' in period3 and 'data' in day20:
                new_data = {}
                for key, value in period3['data'].items():
                    if key.startswith('누적_'):
                        if key in day20['data']:
                            if isinstance(value, dict):
                                new_data[key] = {}
                                for k, v in value.items():
                                    base = day20['data'][key].get(k, 0)
                                    new_data[key][k] = v - base
                            else:
                                new_data[key] = value - day20['data'][key]
                        else:
                            new_data[key] = value
                period3['data'] = new_data
            
            result.append(period3)
        else:
            # 2순기 데이터가 없으면 1순기 다음부터
            if day10:
                period3 = day_last.copy()
                period3['period_name'] = f'2+3순기 ({day10.get("day")+1}~{day_last.get("day")}일)'
                period3['period_type'] = '10day'
                period3['display_date'] = f"{year}-{month:02d}-{day_last.get('day'):02d}"
                
                if 'data' in period3 and 'data' in day10:
                    new_data = {}
                    for key, value in period3['data'].items():
                        if key.startswith('누적_'):
                            if key in day10['data']:
                                if isinstance(value, dict):
                                    new_data[key] = {}
                                    for k, v in value.items():
                                        base = day10['data'][key].get(k, 0)
                                        new_data[key][k] = v - base
                                else:
                                    new_data[key] = value - day10['data'][key]
                            else:
                                new_data[key] = value
                    period3['data'] = new_data
                
                result.append(period3)
    
    print(f"📅 순기별 요약: {len(result)}개 순기")
    return result

def get_weekly_summary_data(all_data, year, month):
    """주차별 데이터 추출"""
    from datetime import date
    import calendar
    
    # 해당 월 데이터만 필터링
    monthly_data = [d for d in all_data 
                   if d.get('year') == year and d.get('month') == month]
    
    if not monthly_data:
        print(f"❌ {year}년 {month}월 데이터 없음")
        return []
    
    # 날짜순 정렬
    monthly_data.sort(key=lambda x: x.get('day', 0))
    
    print(f"📊 {year}년 {month}월 데이터: {len(monthly_data)}일치")
    
    # 월의 첫날과 마지막날
    first_day = date(year, month, 1)
    last_day_num = calendar.monthrange(year, month)[1]
    
    # 주차 구분: 7일씩
    week_ranges = []
    current_start = 1
    week_num = 1
    
    while current_start <= last_day_num:
        week_end = min(current_start + 6, last_day_num)
        week_ranges.append({
            'week': week_num,
            'start': current_start,
            'end': week_end
        })
        current_start = week_end + 1
        week_num += 1
    
    print(f"  주차 구분: {len(week_ranges)}주")
    for wr in week_ranges:
        print(f"    {wr['week']}주차: {wr['start']}~{wr['end']}일")
    
    # 각 주차의 마지막 날 데이터 찾기
    week_data = []
    for wr in week_ranges:
        # 해당 범위에서 가장 마지막 날 찾기
        week_last = None
        for record in monthly_data:
            day = record.get('day')
            if wr['start'] <= day <= wr['end']:
                if not week_last or day > week_last.get('day'):
                    week_last = record
        
        if week_last:
            week_data.append({
                'week_num': wr['week'],
                'range': f"{wr['start']}~{wr['end']}일",
                'record': week_last
            })
            print(f"  {wr['week']}주차 마지막: {week_last.get('day')}일")
    
    # 차이 계산
    result = []
    for i, wd in enumerate(week_data):
        record = wd['record'].copy()
        record['period_name'] = f"{wd['week_num']}주차 ({wd['range']})"
        record['period_type'] = 'weekly'
        record['display_date'] = record.get('date')
        
        if i > 0:
            prev = week_data[i-1]['record']
            # 누적 데이터 차이 계산
            if 'data' in record and 'data' in prev:
                new_data = {}
                for key, value in record['data'].items():
                    if key.startswith('누적_'):
                        if key in prev['data']:
                            if isinstance(value, dict):
                                new_data[key] = {}
                                for k, v in value.items():
                                    base = prev['data'][key].get(k, 0)
                                    new_data[key][k] = v - base
                            else:
                                new_data[key] = value - prev['data'][key]
                        else:
                            new_data[key] = value
                record['data'] = new_data
        
        result.append(record)
    
    print(f"📅 주차별 요약: {len(result)}개 주차")
    return result


def normalize_question(q):
    """질문 정규화"""
    q = q.lower().strip()
    q = re.sub(r'\s+', ' ', q)
    q = q.replace('?', '').replace('!', '').replace('.', '')
    q = re.sub(r'(\d{2})년', lambda m: f"20{m.group(1)}년", q)
    return q

def get_data_for_question(question):
    """질문 유형별 데이터 로딩"""

    # 순기별 패턴
    if any(word in question for word in ['순기', '1순기', '2순기', '3순기']):
        year_match = re.search(r'(\d{2,4})년', question)
        month_match = re.search(r'(\d{1,2})월', question)
        
        # 🔧 추가: 월이 없으면 현재 월 사용
        if not month_match:
            today = datetime.now()
            month = today.month
            year = today.year
            print(f"📅 {year}년 {month}월 순기별 (월 자동 추정)")
            all_data = get_all_data_cached()
            return get_10day_summary_data(all_data, year, month), '10day'
        
        if month_match:
            if year_match:
                year = int(year_match.group(1))
                if year < 100:
                    year = 2000 + year
            else:
                today = datetime.now()
                month_val = int(month_match.group(1))
                if month_val > today.month:
                    year = today.year - 1
                else:
                    year = today.year
                print(f"📅 {year}년 {month_val}월 순기별 (연도 자동 추정)")
            
            month = int(month_match.group(1))
            
            print(f"📅 {year}년 {month}월 순기별")
            all_data = get_all_data_cached()
            return get_10day_summary_data(all_data, year, month), '10day'
    
    # 주차별 패턴
    if any(word in question for word in ['주차', '1주차', '2주차', '3주차', '4주차', '주별']):
        year_match = re.search(r'(\d{2,4})년', question)
        month_match = re.search(r'(\d{1,2})월', question)
        
        # 🔧 수정: 연도가 없으면 현재 연도 사용
        if month_match:
            if year_match:
                year = int(year_match.group(1))
                if year < 100:
                    year = 2000 + year
            else:
                # 연도 없으면 현재 연도 추정
                today = datetime.now()
                month = int(month_match.group(1))
                if month > today.month:
                    year = today.year - 1
                else:
                    year = today.year
            
            month = int(month_match.group(1))
            
            print(f"📅 {year}년 {month}월 주차별")
            all_data = get_all_data_cached()
            return get_weekly_summary_data(all_data, year, month), 'weekly'
    
    # 월별 패턴
    monthly_patterns = [
        r'월별|각\s*월',
        r'제일.*달|가장.*달|최고.*달|최저.*달',
        r'어느.*월|몇.*월.*좋|몇.*월.*나쁨',
        r'월.*비교|달.*비교',
    ]

    # ... (나머지 코드 동일)
    
    if any(re.search(pattern, question) for pattern in monthly_patterns):
        print("📆 월별 요약")
        all_data = get_all_data_cached()
        print(f"  전체 데이터: {len(all_data)}건")
        monthly = get_monthly_summary_data(all_data)
        print(f"  월별 요약: {len(monthly)}개월")
        return monthly, 'monthly'

    needs_all_patterns = [
        r'일별.*평균|평균.*일별',
        r'요일.*패턴|패턴.*요일',
        r'전체.*추이|추이.*전체',
    ]
    if any(re.search(pattern, question) for pattern in needs_all_patterns):
        print("📚 전체 데이터")
        return get_all_data_cached(), 'all'
    
    year_match = re.search(r'(\d{2,4})년', question)
    month_match = re.search(r'(\d{1,2})월', question)
    
    if year_match and month_match:
        year = int(year_match.group(1))
        if year < 100:
            year = 2000 + year
        month = int(month_match.group(1))
        print(f"📅 {year}년 {month}월")
        all_data = get_all_data_cached()
        filtered = [d for d in all_data 
                   if d.get('year') == year and d.get('month') == month]
        return filtered, 'month'
    
    if month_match and not year_match:
        month = int(month_match.group(1))
        print(f"📅 {month}월")
        all_data = get_all_data_cached()
        filtered = [d for d in all_data if d.get('month') == month]
        return filtered, 'month'
    
    # 🔧 수정: "지난주"는 30일 데이터 필요
    if any(word in question for word in ['지난주', '전주']):
        print("📊 최근 30일 (지난주 포함)")
        return get_all_data_cached()[:30], 'recent'
    
    if any(word in question for word in ['최근', '요즘']):
        print("📊 최근 14일")
        return get_all_data_cached()[:14], 'recent'
    
    print("📊 기본 30일")
    return get_all_data_cached()[:30], 'default'

# ============================================
# 시간대별 분석 함수
# ============================================

def parse_hourly_table_ocr(image_bytes):
    """시간대별 표 OCR 파싱"""
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.document_text_detection(image=image)
        text = response.full_text_annotation.text
        
        print(f"📸 OCR 텍스트:\n{text[:200]}...")
        
        hour_match = re.search(r'(\d{2})시', text)
        if not hour_match:
            return None
        hour = int(hour_match.group(1))
        
        week_data = []
        lines = text.split('\n')
        
        for line in lines:
            date_match = re.search(r'(\d{2})/(\d{2})', line)
            if date_match:
                mm, dd = int(date_match.group(1)), int(date_match.group(2))
                numbers = re.findall(r'[+\-△▲]?\d+[,\d]*', line)
                numbers = [n.replace(',', '').replace('△', '-').replace('▲', '-') for n in numbers]
                
                if len(numbers) >= 2:
                    hour_value = int(numbers[0].replace('+', ''))
                    closing = int(numbers[1].replace('+', '')) if len(numbers) > 1 else None
                    
                    week_data.append({
                        'date': f"2026-{mm:02d}-{dd:02d}",
                        'hour_value': hour_value,
                        'closing': closing
                    })
        
        return {'hour': hour, 'week_data': week_data}
    except Exception as e:
        print(f"❌ OCR 오류: {e}")
        return None

def format_hourly_verification(parsed):
    """OCR 검증 메시지"""
    if not parsed:
        return None
    hour = parsed['hour']
    msg = f"📊 **{hour}시 데이터 OCR 결과**\n\n아래 내용이 맞는지 확인해주세요:\n\n"
    for item in parsed['week_data']:
        date = item['date']
        h_val = item['hour_value']
        closing = item['closing']
        closing_str = f"{closing:+,}건" if closing else "-"
        msg += f"• {date}: {hour}시 {h_val:+,}건, 마감 {closing_str}\n"
    msg += "\n✅ **맞으면:** '확인'\n❌ **틀리면:** 수정 내용 입력\n"
    return msg

def save_hourly_to_firestore(data):
    """시간대별 데이터 저장"""
    if not db:
        return False, "Firestore 연결 안 됨"
    try:
        target_date = data['week_data'][-1]['date'] if data['week_data'] else None
        if not target_date:
            return False, "날짜 없음"
        hour = data['hour']
        doc_id = f"{target_date}_{hour:02d}"
        hourly_data = {
            'date': target_date,
            'hour': hour,
            'week_data': data['week_data'],
            'updated_at': get_kst_str()
        }
        db.collection('mvno_hourly_records').document(doc_id).set(hourly_data)
        return True, f"{target_date} {hour}시"
    except Exception as e:
        return False, f"저장 실패: {e}"

def analyze_hourly_with_gemini(hourly_data):
    """시간대별 AI 분석"""
    try:
        hour = hourly_data['hour']
        week_data = hourly_data['week_data']
        if not week_data:
            return "데이터 없음"
        
        target = week_data[-1]
        target_date = target['date']
        target_hour_val = target['hour_value']
        
        prompt = f"""SK MVNO(SM) {hour}시 시간대별 실적 분석:

**일주일 데이터:**
"""
        for item in week_data:
            closing_str = f"{item.get('closing'):+,}건" if item.get('closing') else "미정"
            prompt += f"- {item['date']}: {hour}시 {item['hour_value']:+,}건, 마감 {closing_str}\n"
        
        prompt += f"\n**분석 대상:** {target_date} ({hour}시)\n"
        
        if hour <= 19:
            prompt += """
**분석:**
1. 현재시간 실적 평가 (전일/지난주/평균 비교)
2. 마감 예상 (과거 패턴 분석)

**형식:**
■ (19시 실적) ...
■ (마감 예상) ...
■ (특이사항) ...

명사형 종결, 150-250자
"""
        else:
            prompt += """
**분석:**
마감 확정 실적 평가

**형식:**
■ (마감 실적) ...
■ (특이사항) ...

명사형 종결, 100-200자, 예측 없음
"""
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"분석 오류: {e}"

def save_pending_hourly_verification(chat_id, data):
    """검증 대기 저장"""
    if not db:
        return
    db.collection('pending_hourly_verifications').document(str(chat_id)).set({
        'timestamp': get_kst_str(),
        'parsed_data': data,
        'expires_at': (get_kst_now() + timedelta(minutes=5)).isoformat()
    })

def get_pending_hourly_verification(chat_id):
    """검증 대기 조회"""
    if not db:
        return None
    doc = db.collection('pending_hourly_verifications').document(str(chat_id)).get()
    if doc.exists:
        data = doc.to_dict()
        expires = datetime.fromisoformat(data['expires_at'])
        if get_kst_now() < expires:
            return data['parsed_data']
    return None

def clear_pending_hourly_verification(chat_id):
    """검증 대기 삭제"""
    if not db:
        return
    db.collection('pending_hourly_verifications').document(str(chat_id)).delete()




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


def build_analysis_prompt(current_data=None, historical_data=None, user_question=None):
    """통합 프롬프트 생성기 - 피드백 반영"""
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
    
    # 실적 분석 모드
    else:
        current = parse_mvno_data(current_data) if current_data else {}
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
        
        # 캐싱을 위해 데이터를 JSON으로 변환
        import json
        data_json = json.dumps(historical_data)
        
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
    
    # 답변 형식 추가 - 일별 실적 vs 일반 질문 구분
    if user_question:
        prompt += f"\n{GENERAL_RESPONSE_FORMAT}"
    else:
        prompt += f"\n{DAILY_RESPONSE_FORMAT}"
    
    return prompt
    
    
def analyze_with_gemini(text, historical_data=None):
    """Gemini로 데이터 분석 - 통합 프롬프트 + 피드백 반영"""
    try:
        prompt = build_analysis_prompt(
            current_data=text,
            historical_data=historical_data,
            user_question=None
        )
        
        response = model.generate_content(prompt)
        return response.text
    
    except Exception as e:
        return f"분석 중 오류 발생: {e}"




# ============================================
# 명령어 핸들러
# ============================================

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

def handle_query(chat_id, question):
    """질문 처리 - 캐싱 + 스마트 로딩"""
    try:
        # 질문 정규화
        normalized = normalize_question(question)
        q_hash = hash(normalized)
        
        # 캐시 확인 (5분)
        now = datetime.now()
        if q_hash in _qa_cache:
            cached_answer, cached_time = _qa_cache[q_hash]
            age = (now - cached_time).seconds
            if age < 300:
                print(f"💾 캐시 hit ({age}초)")
                send_telegram_message(chat_id, f"💡 **답변**\n\n{cached_answer}")
                return
        
        send_telegram_message(chat_id, "🤔 분석 중...")
        start_time = datetime.now()
        
        # 스마트 데이터 로딩
        data, data_type = get_data_for_question(question)
        
        if not data:
            send_telegram_message(chat_id, "❌ 해당 기간 데이터 없음")
            return
        
        # 프롬프트 생성
        prompt = build_analysis_prompt(
            current_data=None,
            historical_data=data,
            user_question=question
        )
        
        # 데이터 범위 명시
        if data:
            dates = [d.get('date') for d in data if d.get('date')]
            if dates:
                earliest = min(dates)
                latest = max(dates)
                prompt += f"\n\n**데이터: {earliest} ~ {latest} ({len(data)}일치)**"
                if data_type == 'monthly':
                    prompt += "\n**월별 질문 - 각 월 마지막 날 누적 데이터**"
        
        # Gemini 분석
        response = model.generate_content(prompt)
        answer = response.text
        
        # 캐시 저장
        _qa_cache[q_hash] = (answer, now)
        
        # 로그 저장
        response_time = (datetime.now() - start_time).total_seconds()
        save_query_log(chat_id, question, answer, response_time)
        
        send_telegram_message(chat_id, f"💡 **답변**\n\n{answer}")
        
    except Exception as e:
        send_telegram_message(chat_id, f"❌ 오류: {e}")

        


def handle_message(chat_id, text):
    """일반 메시지 처리"""
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
            # 3. Firestore에 저장
            success, msg = save_to_firestore(parsed)
            
            # 4. 과거 데이터 가져오기
            historical = get_from_firestore(limit=100)
            
            # 5. Gemini로 분석
            analysis = analyze_with_gemini(text, historical)
            
            # 응답 시간 계산
            response_time = (datetime.now() - start_time).total_seconds()
            
            # 로그 저장
            save_analysis_log(chat_id, parsed.get('date'), analysis, response_time)
            
            # 6. 최종 결과 전송
            # 6. 최종 결과 전송 (경고 포함)
            response = f"{warning}✅ {msg}\n\n{analysis}"
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
    elif '?' in text or any(keyword in text for keyword in ['어때', '어떻게', '어땠', '비교', '예상', '분석', '언제', '얼마', '평균', '추이', '트렌드', '실적', '데이터']):    
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
        
        if 'message' not in update:
            return jsonify({'ok': True})
        
        message = update['message']
        chat_id = message['chat']['id']
        
        # 📸 이미지 처리
        if 'photo' in message:
            photo = message['photo'][-1]
            file_id = photo['file_id']
            
            send_telegram_message(chat_id, "📸 이미지 분석 중...")
            
            file_info = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
            ).json()
            
            if file_info.get('ok'):
                file_path = file_info['result']['file_path']
                file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                image_response = requests.get(file_url)
                image_bytes = image_response.content
                
                parsed = parse_hourly_table_ocr(image_bytes)
                
                if parsed:
                    verification_msg = format_hourly_verification(parsed)
                    if verification_msg:
                        save_pending_hourly_verification(chat_id, parsed)
                        send_telegram_message(chat_id, verification_msg)
                    else:
                        send_telegram_message(chat_id, "❌ 표 형식 인식 실패")
                else:
                    send_telegram_message(chat_id, "❌ OCR 실패. 명확한 이미지를 다시 보내주세요.")
            else:
                send_telegram_message(chat_id, "❌ 이미지 다운로드 실패")
            
            return jsonify({'ok': True})
        
        # 텍스트 처리
        if 'text' not in message:
            return jsonify({'ok': True})
        
        text = message['text']
        
        # 시간대별 검증 대기 중?
        pending = get_pending_hourly_verification(chat_id)
        if pending:
            if text == '확인':
                success, msg = save_hourly_to_firestore(pending)
                
                if success:
                    send_telegram_message(chat_id, f"✅ {msg} 저장!\n\n📊 분석 중...")
                    
                    start_time = datetime.now()
                    analysis = analyze_hourly_with_gemini(pending)
                    
                    hour = pending['hour']
                    result = f"🕐 **{msg} 시간대별 분석**\n\n{analysis}"
                    send_telegram_message(chat_id, result)
                else:
                    send_telegram_message(chat_id, f"❌ 저장 실패: {msg}")
                
                clear_pending_hourly_verification(chat_id)
            else:
                send_telegram_message(chat_id, "수정 기능은 다음 버전에서 지원. 이미지 재업로드 해주세요.")
                clear_pending_hourly_verification(chat_id)
            
            return jsonify({'ok': True})
        
        # 명령어 처리
        if text == '/start' or text == '/help':
            handle_start(chat_id)
        elif text == '/recent':
            handle_recent(chat_id)
        else:
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)