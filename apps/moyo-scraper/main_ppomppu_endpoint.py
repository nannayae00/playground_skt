"""
main_ppomppu_endpoint.py
──────────────────────────────────────────────────────────────────────────────
main.py에 추가할 뽐뿌 모니터링 엔드포인트
기존 코드는 건드리지 않고 맨 아래에 추가만 하면 됨
──────────────────────────────────────────────────────────────────────────────
"""

# ══════════════════════════════════════════════════════════════════════════════
# 뽐뿌 모니터링 엔드포인트 (main.py 맨 아래에 추가)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/webhook_ppomppu', methods=['POST'])
def webhook_ppomppu():
    """
    뽐뿌 모니터링 웹훅 (Cloud Scheduler용)
    
    동작:
    1. 뽐뿌 크롤링 (최근 7일)
    2. MVNO 필터링
    3. 신규 글만 선별
    4. Firebase 저장
    5. Telegram 알림 발송
    
    Returns:
        JSON: {"status": "ok", "new_posts": N}
    """
    try:
        from scrapers.ppomppu_scraper import PpomppuScraper, filter_mvno_posts, filter_new_posts
        from core.firebase_handler import FirebaseHandler
        import os
        
        print("🔍 뽐뿌 모니터링 시작")
        
        # Step 1: 뽐뿌 크롤링 (7일)
        scraper = PpomppuScraper()
        all_posts = scraper.scrape(days=7, max_pages=10)
        
        if not all_posts:
            return {"status": "ok", "message": "수집된 게시글 없음", "new_posts": 0}
        
        # Step 2: Firebase에서 기존 게시글 ID 가져오기
        firebase = FirebaseHandler()
        existing_ids = firebase.get_existing_ppomppu_ids(limit=2000)
        
        # Step 3: 신규 글만 필터링
        new_posts = filter_new_posts(all_posts, existing_ids)
        
        if not new_posts:
            return {"status": "ok", "message": "신규 게시글 없음", "new_posts": 0}
        
        # Step 4: MVNO 필터링
        mvno_posts = filter_mvno_posts(
            new_posts, 
            fetch_content=True,  # 본문도 가져옴
            use_ai=False  # AI는 비용 때문에 일단 꺼둠
        )
        
        if not mvno_posts:
            return {"status": "ok", "message": "MVNO 관련 게시글 없음", "new_posts": 0}
        
        # Step 5: Firebase 저장 + Telegram 알림
        saved_count = 0
        for post in mvno_posts:
            # Firebase 저장
            if firebase.save_ppomppu_post(post):
                saved_count += 1
                
                # Telegram 알림 발송
                send_ppomppu_alert(post)
        
        return {
            "status": "ok",
            "total_scraped": len(all_posts),
            "new_posts": len(new_posts),
            "mvno_posts": len(mvno_posts),
            "saved": saved_count
        }
        
    except Exception as e:
        print(f"❌ 뽐뿌 모니터링 에러: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}, 500


# ══════════════════════════════════════════════════════════════════════════════
# Telegram 알림 발송 함수
# ══════════════════════════════════════════════════════════════════════════════

def send_ppomppu_alert(post):
    """
    뽐뿌 게시글 Telegram 알림 발송
    
    Args:
        post: 게시글 데이터 dict
    """
    import os
    import requests
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram 설정 없음")
        return
    
    try:
        filter_result = post.get('filter_result', {})
        provider = filter_result.get('provider', '알뜰폰')
        confidence = filter_result.get('confidence', 0.0)
        method = filter_result.get('method', 'unknown')
        
        # URL 단축 (뽐뿌는 기본적으로 짧음)
        # 예: https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=680783
        # → https://m.ppomppu.co.kr/new/bbs_view.php?no=680783 (id 파라미터 제거)
        original_url = post['url']
        post_id = post['post_id']
        short_url = f"https://m.ppomppu.co.kr/new/bbs_view.php?no={post_id}"
        
        # 메시지 포맷팅
        message = f"""🔔 <b>뽐뿌 알뜰폰 신규 글</b>

📱 <b>{provider}</b> ({confidence:.1%} 신뢰도)
📝 {post['title']}

👁 조회 {post['views']:,} | 💬 댓글 {post['comments']}
📅 {post['posted_at'].strftime('%Y-%m-%d')}

🔗 {short_url}

<i>필터: {method}</i>"""
        
        # Telegram API 호출
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False  # 링크 프리뷰 활성화
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Telegram 알림 발송: {post['post_id']}")
            
            # 알림 발송 완료 표시
            from core.firebase_handler import FirebaseHandler
            firebase = FirebaseHandler()
            firebase.mark_ppomppu_notified(post['post_id'])
        else:
            print(f"⚠️ Telegram 발송 실패: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Telegram 알림 에러: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Telegram 명령어: 수동 트리거
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """
    기존 Telegram 웹훅에 명령어 추가
    """
    # ... 기존 코드 ...
    
    # 뽐뿌 수동 트리거 명령어 추가
    if text == '뽐뿌 체크해줘' or text == '/ppomppu':
        # webhook_ppomppu() 호출
        result = webhook_ppomppu()
        
        reply = f"""✅ 뽐뿌 체크 완료
        
총 {result.get('total_scraped', 0)}개 수집
신규 {result.get('new_posts', 0)}개
MVNO {result.get('mvno_posts', 0)}개 감지"""
        
        send_telegram_message(chat_id, reply)
        return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# 사용법
# ══════════════════════════════════════════════════════════════════════════════

"""
1. main.py 맨 아래에 위 코드 복사
2. Cloud Scheduler 설정:
   - URL: https://your-service.run.app/webhook_ppomppu
   - 스케줄: 0 */2 * * *  (2시간마다)
   - 방법: POST

3. Telegram 명령어로 수동 실행:
   - "뽐뿌 체크해줘" 또는 "/ppomppu"
"""
