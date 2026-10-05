from flask import Flask, request, jsonify
from datetime import datetime
import requests
import os
import sys
import traceback
import pytz
import threading  # 이 한 줄만 추가


from scrapers.moyo_scraper import MoyoScraper
from core.firebase_handler import FirebaseHandler
from core.comparator import Comparator

app = Flask(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
KOREA_TZ = pytz.timezone('Asia/Seoul')

def log(message):
    timestamp = datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def get_korea_time():
    return datetime.now(KOREA_TZ)

def send_telegram(text):
    log("📤 텔레그램 전송 시도...")
    
    if not BOT_TOKEN or not CHAT_ID:
        log("⚠️ 텔레그램 설정 없음")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            log("✅ 텔레그램 전송 성공!")
            return True
        else:
            log(f"❌ 텔레그램 전송 실패: {response.status_code}")
            return False
    except Exception as e:
        log(f"❌ 텔레그램 에러: {e}")
        return False

def get_latest_plans_analysis():
    db = FirebaseHandler()
    latest = db.get_latest_data('moyo')
    
    if not latest:
        return None
    
    plans = latest.get('plans', [])
    checked_at = latest.get('checked_at')
    
    if hasattr(checked_at, 'astimezone'):
        korea_time = checked_at.astimezone(KOREA_TZ)
    else:
        korea_time = get_korea_time()
    
    return {
        'checked_at': korea_time,
        'total_plans': len(plans),
        'plans': plans
    }

def get_best_value_plans(plans, limit=3):
    scored = []
    for p in plans:
        if p.get('data_gb', 0) > 0 and p.get('final_price', 0) > 0:
            value = p['data_gb'] / p['final_price']
            scored.append({
                'plan': p,
                'value': value,
                'price_per_gb': p['final_price'] / p['data_gb']
            })
    
    top = sorted(scored, key=lambda x: x['value'], reverse=True)[:limit]
    return top

def get_popular_plans(plans, limit=3):
    with_subs = [p for p in plans if p.get('subscribers', 0) > 0]
    top = sorted(with_subs, key=lambda x: x['subscribers'], reverse=True)[:limit]
    return top

def get_cheapest_plans(plans, limit=3):
    top = sorted(plans, key=lambda x: x.get('final_price', float('inf')))[:limit]
    return top

@app.route('/')
def index():
    return jsonify({
        "status": "ok",
        "service": "Price Monitor",
        "version": "2.0",
        "timestamp": datetime.now(KOREA_TZ).isoformat()
    })

@app.route('/check-moyo', methods=['POST'])
def check_moyo():
    try:
        log("🚀 모요 체크 시작")
        
        log("1️⃣ MoyoScraper 시작...")
        scraper = MoyoScraper(progress_callback=lambda msg: send_telegram(msg))
        plans, screenshot = scraper.scrape()
        log(f"   ✅ {len(plans)}개 요금제 수집 완료")
        
        if not plans:
            error_msg = "❌ 모요 스크래핑 실패"
            log(error_msg)
            send_telegram(error_msg)
            return jsonify({"status": "error"}), 500
        
        log("2️⃣ Firebase 저장...")
        db = FirebaseHandler()
        save_success = db.save_check_result('moyo', plans, screenshot)
        
        if save_success:
            log("   ✅ Firestore 저장 완료")
        else:
            log("   ⚠️ Firebase 저장 실패")
        
        log("3️⃣ 경쟁력 분석...")
        try:
            comparator = Comparator()
            alerts = comparator.analyze_competitiveness(plans)
            log(f"   ✅ {len(alerts)}개 알림 생성")
        except Exception as e:
            log(f"   ⚠️ 경쟁력 분석 실패: {e}")
            alerts = []
        
        log("4️⃣ 메시지 생성...")
        korea_time = get_korea_time()
        message = f"""📊 MVNO 요금제 모니터링 완료

⏰ 수집 시간 (한국): {korea_time.strftime('%Y-%m-%d %H:%M:%S')}
📈 수집: {len(plans)}개 요금제
🚨 알림: {len(alerts)}개
"""
        
        if alerts:
            message += "\n⚠️ 주요 알림:\n"
            for i, alert in enumerate(alerts[:5], 1):
                message += f"{i}. {alert['message']}\n"
            if len(alerts) > 5:
                message += f"\n... 외 {len(alerts) - 5}개 알림"
        else:
            message += "\n✅ 경쟁력 양호!"
        
        log("5️⃣ Telegram 전송...")
        send_telegram(message)
        
        log(f"✅ 모요 체크 완료")
        
        return jsonify({
            "status": "success",
            "plans_count": len(plans),
            "alerts_count": len(alerts),
            "timestamp": datetime.now(KOREA_TZ).isoformat()
        })
    
    except Exception as e:
        log(f"❌ 모요 체크 실패: {str(e)}")
        error_msg = f"""❌ 모요 체크 실패

⏰ 시간: {get_korea_time().strftime('%Y-%m-%d %H:%M:%S')}
에러: {str(e)}"""
        send_telegram(error_msg)
        return jsonify({"status": "error"}), 500

@app.route('/latest-analysis', methods=['GET'])
def latest_analysis():
    try:
        log("📊 최신 분석 요청")
        
        analysis = get_latest_plans_analysis()
        if not analysis:
            return jsonify({"status": "no_data"}), 404
        
        plans = analysis['plans']
        checked_at = analysis['checked_at']
        
        best_value = get_best_value_plans(plans, 3)
        popular = get_popular_plans(plans, 3)
        cheapest = get_cheapest_plans(plans, 3)
        
        response = {
            "status": "ok",
            "timestamp": datetime.now(KOREA_TZ).isoformat(),
            "checked_at_korea": checked_at.strftime('%Y-%m-%d %H:%M:%S %Z'),
            "total_plans": analysis['total_plans'],
            "best_value_plans": [
                {
                    "name": p['plan']['display_name'],
                    "data_gb": p['plan']['data_gb'],
                    "price": p['plan']['final_price'],
                    "subscribers": p['plan']['subscribers'],
                    "value_score": round(p['value'], 2),
                    "price_per_gb": round(p['price_per_gb'], 0)
                }
                for p in best_value
            ],
            "popular_plans": [
                {
                    "name": p['display_name'],
                    "data": p['data'],
                    "price": p['final_price'],
                    "subscribers": p['subscribers']
                }
                for p in popular
            ],
            "cheapest_plans": [
                {
                    "name": p['display_name'],
                    "data": p['data'],
                    "price": p['final_price'],
                    "subscribers": p['subscribers']
                }
                for p in cheapest
            ]
        }
        
        log("✅ 최신 분석 완료")
        return jsonify(response)
    
    except Exception as e:
        log(f"❌ 최신 분석 실패: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/status')
def status():
    try:
        db = FirebaseHandler()
        latest = db.get_latest_data('moyo')
        
        if latest:
            checked_at = latest.get('checked_at')
            if hasattr(checked_at, 'astimezone'):
                korea_time = checked_at.astimezone(KOREA_TZ)
            else:
                korea_time = get_korea_time()
            
            return jsonify({
                "status": "ok",
                "service": "Price Monitor",
                "last_check_korea": korea_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                "last_plan_count": latest.get('plan_count'),
                "timestamp": datetime.now(KOREA_TZ).isoformat()
            })
        else:
            return jsonify({
                "status": "no_data",
                "message": "No check result yet",
                "timestamp": datetime.now(KOREA_TZ).isoformat()
            })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(KOREA_TZ).isoformat()
        }), 500

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json()
        
        if 'message' not in data:
            return jsonify({"status": "ok"})
        
        message = data['message']
        text = message.get('text', '').strip()
        
        log(f"📨 Telegram: {text}")
        
        text_lower = text.lower()
        
        # 최신분석
        if '최신분석' in text_lower or '최신' in text_lower:
            log("📊 최신 분석")
            analysis = get_latest_plans_analysis()
            if not analysis:
                send_telegram("⚠️ 데이터 없음")
                return jsonify({"status": "ok"})
            
            plans = analysis['plans']
            checked_at = analysis['checked_at']
            best_value = get_best_value_plans(plans, 3)
            popular = get_popular_plans(plans, 3)
            cheapest = get_cheapest_plans(plans, 3)
            
            msg = f"""📊 MVNO 요금제 최신 분석

⏰ 수집: {checked_at.strftime('%Y-%m-%d %H:%M:%S %Z')}
📈 요금제: {len(plans):,}개

🏆 가성비 최고:
"""
            for i, item in enumerate(best_value, 1):
                p = item['plan']
                msg += f"{i}. {p['display_name']}\n   {p['data']} | {p['final_price']:,}원\n\n"
            
            msg += """🔥 인기:
"""
            for i, p in enumerate(popular, 1):
                msg += f"{i}. {p['display_name']}\n   {p['data']} | {p['final_price']:,}원\n   👥 {p['subscribers']:,}명\n\n"
            
            msg += """💵 최저가:
"""
            for i, p in enumerate(cheapest, 1):
                msg += f"{i}. {p['display_name']}\n   {p['final_price']:,}원\n\n"
            
            send_telegram(msg)
        
        # 가성비
        elif '가성비' in text_lower:
            log("💎 가성비")
            analysis = get_latest_plans_analysis()
            if not analysis:
                send_telegram("⚠️ 데이터 없음")
                return jsonify({"status": "ok"})
            
            best = get_best_value_plans(analysis['plans'], 5)
            msg = "💎 가성비 최고 (TOP 5)\n\n"
            for i, item in enumerate(best, 1):
                p = item['plan']
                msg += f"{i}. {p['display_name']}\n   {p['data_gb']}GB | {p['final_price']:,}원\n\n"
            
            send_telegram(msg)
        
        # 인기
        elif '인기' in text_lower:
            log("🔥 인기")
            analysis = get_latest_plans_analysis()
            if not analysis:
                send_telegram("⚠️ 데이터 없음")
                return jsonify({"status": "ok"})
            
            popular = get_popular_plans(analysis['plans'], 5)
            msg = "🔥 인기 요금제 (TOP 5)\n\n"
            for i, p in enumerate(popular, 1):
                msg += f"{i}. {p['display_name']}\n   {p['data']} | {p['final_price']:,}원\n   👥 {p['subscribers']:,}명\n\n"
            
            send_telegram(msg)
        
        # 최저가
        elif '최저가' in text_lower:
            log("💵 최저가")
            analysis = get_latest_plans_analysis()
            if not analysis:
                send_telegram("⚠️ 데이터 없음")
                return jsonify({"status": "ok"})
            
            cheap = get_cheapest_plans(analysis['plans'], 5)
            msg = "💵 최저가 요금제 (TOP 5)\n\n"
            for i, p in enumerate(cheap, 1):
                msg += f"{i}. {p['display_name']}\n   {p['final_price']:,}원\n\n"
            
            send_telegram(msg)
        elif '수집' in text_lower or '체크' in text_lower or '확인' in text_lower:
            log("🔍 수집 명령 수신 - Job 트리거")
            
            try:
                import google.auth
                import google.auth.transport.requests
                
                # 인증 토큰 가져오기
                credentials, project = google.auth.default()
                auth_req = google.auth.transport.requests.Request()
                credentials.refresh(auth_req)
                token = credentials.token
                
                # Cloud Run Job API 호출
                url = "https://asia-northeast3-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/mvno-484509/jobs/moyo-scrape-job:run"
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json={}
                )
                
                if response.status_code in [200, 201]:
                    send_telegram("🔍 수집 시작! 완료되면 알려드릴게요 (약 15분 소요)")
                    log("✅ Job 트리거 성공")
                else:
                    log(f"❌ Job 트리거 실패: {response.status_code} {response.text}")
                    send_telegram(f"❌ 수집 시작 실패\n\n{response.text[:200]}")
                    
            except Exception as e:
                log(f"❌ Job 트리거 실패: {e}")
                send_telegram(f"❌ 수집 시작 실패\n\n{str(e)}")
            
            return jsonify({"status": "ok"})

       
        # 도움말
        elif '도움' in text_lower or 'help' in text_lower:
            log("ℹ️ 도움말")
            help_msg = """📋 명령어:

⚡ 즉시:
최신분석 / 가성비 / 인기 / 최저가

🔄 수집 (4분):
수집해줘 / 체크해줘

💡 도움말 / help"""
            send_telegram(help_msg)
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        log(f"❌ 웹훅 에러: {e}")
        traceback.print_exc()
        return jsonify({"status": "error"}), 500

@app.route('/test-network', methods=['GET'])
def test_network():
    try:
        resp = requests.get('https://www.moyoplan.com', timeout=10)
        return jsonify({
            "status_code": resp.status_code,
            "reachable": True,
            "message": "moyoplan.com 접속 성공!"
        })
    except Exception as e:
        return jsonify({
            "reachable": False,
            "error": str(e)
        })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    log(f"🚀 Flask 앱 시작 (포트: {port})")
    app.run(host='0.0.0.0', port=port, debug=False)
