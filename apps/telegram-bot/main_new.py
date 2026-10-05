#!/usr/bin/env python3
"""
MVNO 실적 분석 텔레그램 봇 (Cloud Run) - 안정적인 버전
"""

import os
import re
import json
from datetime import datetime
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
model = genai.GenerativeModel('gemini-2.0-flash-exp')

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
    """MVNO 데이터 파싱"""
    data = {}
    
    # 날짜 추출
    date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일|(\d{2})\.(\d{2})\.(\d{2})', text)
    if date_match:
        if date_match.group(1):
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
        else:
            year = 2000 + int(date_match.group(4))
            month = int(date_match.group(5))
            day = int(date_match.group(6))
        data['date'] = f"{year:04d}-{month:02d}-{day:02d}"
        data['year'] = year
        data['month'] = month
        data['day'] = day
    else:
        # 날짜가 없으면 오늘 날짜
        today = datetime.now()
        data['date'] = today.strftime('%Y-%m-%d')
        data['year'] = today.year
        data['month'] = today.month
        data['day'] = today.day
    
    # 각 섹션 파싱
    sections = {
        '당일_마감': r'◎\s*당일\s*마감[^◎]*?S\s*([\d,]+).*?K\s*([\d,]+).*?L\s*([\d,]+).*?계\s*([\d,]+)',
        '누적_신규': r'◎\s*\d+월\s*누적[^◎]*?S\s*([\d,.]+천?).*?K\s*([\d,.]+천?).*?L\s*([\d,.]+천?).*?계\s*([\d,.]+천?)',
        '당일_MNO_Out': r'◎.*?당일.*?MNO.*?Out[^◎]*?S\s*([\d,]+).*?K\s*([\d,]+).*?L\s*([\d,]+).*?계\s*([\d,]+)',
        '누적_MNO_Out': r'◎.*?누적.*?MNO.*?Out[^◎]*?S\s*([\d,.]+천?).*?K\s*([\d,.]+천?).*?L\s*([\d,.]+천?).*?계\s*([\d,.]+천?)',
        '당일_순증감': r'◎.*?당일.*?순증감[^◎]*?S\s*([+\-△▲]?[\d,]+).*?K\s*([+\-△▲]?[\d,]+).*?L\s*([+\-△▲]?[\d,]+).*?계\s*([+\-△▲]?[\d,]+)',
        '누적_순증감': r'◎.*?누적.*?순증감[^◎]*?S\s*([+\-△▲]?[\d,]+).*?K\s*([+\-△▲]?[\d,]+).*?L\s*([+\-△▲]?[\d,]+).*?계\s*([+\-△▲]?[\d,]+)',
        '당일_MVNO_MNP_해지': r'◎.*?당일.*?MVNO.*?MNP.*?해지[^◎]*?S\s*([\d,]+).*?K\s*([\d,]+).*?L\s*([\d,]+).*?계\s*([\d,]+)',
        '누적_MVNO_MNP_해지': r'◎.*?누적.*?MVNO.*?MNP.*?해지[^◎]*?S\s*([\d,]+).*?K\s*([\d,]+).*?L\s*([\d,]+).*?계\s*([\d,]+)'
    }
    
    parsed_data = {}
    for section_name, pattern in sections.items():
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                def parse_num(s):
                    s = s.replace(',', '').replace('천', '00').replace('△', '-').replace('▲', '-').replace('+', '')
                    return int(float(s))
                
                parsed_data[section_name] = {
                    'S': parse_num(match.group(1)),
                    'K': parse_num(match.group(2)),
                    'L': parse_num(match.group(3)),
                    '계': parse_num(match.group(4))
                }
            except:
                pass
    
    data['data'] = parsed_data
    data['type'] = 'daily'
    data['raw_text'] = text
    
    return data if parsed_data else None


def save_to_firestore(data):
    """Firestore에 데이터 저장"""
    if not db:
        return False, "Firestore 연결 안 됨"
    
    try:
        doc_id = data['date']
        collection_ref = db.collection('mvno_records')
        collection_ref.document(doc_id).set(data, merge=True)
        return True, f"✅ {doc_id} 저장 완료"
    except Exception as e:
        return False, f"❌ 저장 실패: {e}"


def get_from_firestore(date=None, limit=10):
    """Firestore에서 데이터 조회"""
    if not db:
        return []
    
    try:
        collection_ref = db.collection('mvno_records')
        
        if date:
            doc = collection_ref.document(date).get()
            return [doc.to_dict()] if doc.exists else []
        else:
            docs = collection_ref.order_by('date', direction=firestore.Query.DESCENDING).limit(limit).stream()
            return [doc.to_dict() for doc in docs]
    except Exception as e:
        print(f"조회 실패: {e}")
        return []


def analyze_with_gemini(text, historical_data=None):
    """Gemini로 데이터 분석"""
    try:
        prompt = f"""당신은 MVNO 실적 분석 전문가입니다.

현재 데이터:
{text}

"""
        if historical_data and len(historical_data) > 0:
            prompt += "\n과거 데이터:\n"
            for record in historical_data[:5]:
                prompt += f"- {record.get('date', 'N/A')}: {json.dumps(record.get('data', {}), ensure_ascii=False)}\n"
        
        prompt += """

위 데이터를 분석하여 다음을 포함한 간결한 분석 리포트를 작성해주세요:
1. 주요 수치 요약
2. 통신사별 점유율 변화
3. 전월 대비 증감 트렌드 (과거 데이터가 있는 경우)
4. 핵심 인사이트


한국 통신시장 구조:
- MNO 3사: SKT, KT, LGU+
- MVNO 3사: SM(SKT MVNO), KM(KT MVNO), LM(LGU+ MVNO)
  (데이터에서 S, K, L로 표기됨)

당신의 역할은 일일 실적 데이터를 SM(S) 관점에서 시계열 비교 분석하고 핵심 인사이트를 제공하는 것입니다.

분석 시 다음 사항에 집중하세요:
1. SM의 시장 점유율 변화 (신규, MNP 해지 기준)
2. SM의 순증감 성과 (경쟁사 대비)
3. MNO로의 Out 비율 (이탈 현황)
4. 시계열 비교 (전일, 전주, 동일 요일, 평일/주말 패턴, 전년 동기)
5. 트렌드 및 패턴 분석
6. 주의해야 할 위험 신호나 긍정적 신호

답변은 아래 양식처럼 작성해주고, 
각 O마다 분석, 추가 내용은 - 으로 표시 
■ 랑 -는 줄만 바꾸고
다음 ■이 나올땐 그전에 한줄씩 띄어서 구분 
■ 제목 1
- 세부내용 

■ 제목2 
- 세부내용 

■ 제목은 bold하게 
- 세부내용은 bold 하지말고, 
특이 사항은 밑줄까지 작성 해줘 


불렛 포인트나 과도한 포맷팅 없이 자연스러운 문장으로 작성하세요
"~입니다" 등 서술어, 마침표는 안써도됨 
 접두어는 최대한  제외하고, 간결하게 작성 
Input 통계 대비해서는 결과값이 짧은게 좋음 

"■"는 통계치 하나를 분석 
"-"은 위 "■" 내용을 뒷받침할  내용 으로 기입 


(결과 포맷)
■ 금일 시장 size는 기존 평일 대비 유사한 SIZE
 - S는 20.7%로 타겟인 21%대비 소폭 낮은 수준 
 -k or L의 증가 원인 

■ 당일 순증감은 +100건으로 평일 평균 수준임
- 당일 MNO out은 60건으로 기존 당일 대비 낮은 수준임
- 당일 순증감 중 대비 많은 수준임
-
■  MVNP MNP 해지는 당일 마감 대비 많은 수준으로 순증에 기여함
- 누적 순증감은 3사 중 5차 가장 나은 상황
- 누적 MNO out 비율은 SM out% 00%로 기존 당일 대비 낮은 수준임 최근 같은 수준임
- 당일 MNO out 건 수는 범위 대비 증가 or 21를 위해서는 앞날 설정이 24는 나와야함

■ 당일 MNO out은00%로 기존 평일 대비 낮은 수준 
K나 L이 증감한 사유
MNO out 전체 사이즈는 평시 대비 증가 한 상태 

■ 당일 순증감은 +100건으로 평일 평균 수준임
K, L 대비 양호 , 부진 실적 

■ 누적 순증감은  3사 중 S가 가장 나은 상황

■ MVNP MNP 해지는  당일 마감 비율 대비 양호 수준으로 순증에 기여함 
 비율이 당일 마감 대비 높다/적다
K, L은 높다 적다. 

답변은 150-200자 정도로 줄여서 핵심만 전달.
불렛 포인트나 과도한 포맷팅 없이 자연스러운 문장으로 작성하세요


200자 이내로 핵심만 간결하게 작성하세요."""

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
    records = get_from_firestore(limit=10)
    
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


def handle_message(chat_id, text):
    """일반 메시지 처리"""
    # MVNO 데이터인지 확인
    if re.search(r'◎.*?(당일|누적|MNO|MVNO)', text, re.IGNORECASE):
        # 데이터 파싱
        parsed = parse_mvno_data(text)
        
        if parsed:
            # Firestore에 저장
            success, msg = save_to_firestore(parsed)
            
            # 과거 데이터 가져오기
            historical = get_from_firestore(limit=5)
            
            # Gemini로 분석
            analysis = analyze_with_gemini(text, historical)
            
            response = f"{msg}\n\n📊 **분석 결과:**\n{analysis}"
            send_telegram_message(chat_id, response)
        else:
            send_telegram_message(chat_id, "❌ 데이터 형식을 인식할 수 없습니다. /start로 형식을 확인하세요.")
    else:
        # 일반 대화
        send_telegram_message(chat_id, "안녕하세요! MVNO 실적 데이터를 보내주시면 분석해드립니다. /start로 사용법을 확인하세요.")


# ============================================
# Flask 라우트
# ============================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """텔레그램 webhook"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            
            if 'text' in message:
                text = message['text']
                
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
        'timestamp': datetime.now().isoformat()
    })


@app.route('/', methods=['GET'])
def index():
    """루트"""
    return '🤖 MVNO Bot is running on Cloud Run!'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)