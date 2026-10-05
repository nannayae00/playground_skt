"""
firebase_ppomppu_extension.py
──────────────────────────────────────────────────────────────────────────────
FirebaseHandler에 추가할 뽐뿌 관련 메서드
기존 firebase_handler.py에 복사해서 추가하면 됨
──────────────────────────────────────────────────────────────────────────────
"""

# ══════════════════════════════════════════════════════════════════════════════
# 뽐뿌 관련 메서드 (FirebaseHandler 클래스에 추가)
# ══════════════════════════════════════════════════════════════════════════════

def save_ppomppu_post(self, post_data):
    """
    뽐뿌 게시글 저장
    
    Args:
        post_data: {
            'post_id': '680783',
            'title': '제목',
            'url': 'https://...',
            'views': 1234,
            'comments': 10,
            'posted_at': datetime,
            'content': '본문',
            'filter_result': {...},
            'summary': '요약',  # Claude 요약 (옵션)
        }
    
    Returns:
        bool: 성공 여부
    """
    if not self.db:
        print("⚠️ Firebase 미연결")
        return False
    
    try:
        post_id = post_data['post_id']
        
        # 문서 참조
        doc_ref = self.db.collection('ppomppu_monitor')\
            .document('posts').collection('all_posts').document(post_id)
        
        # 저장
        doc_ref.set({
            'post_id': post_id,
            'title': post_data.get('title', ''),
            'url': post_data.get('url', ''),
            'views': post_data.get('views', 0),
            'comments': post_data.get('comments', 0),
            'posted_at': post_data.get('posted_at'),
            'content': post_data.get('content', ''),
            'author': post_data.get('author', '익명'),
            'provider': post_data.get('filter_result', {}).get('provider'),
            'filter_method': post_data.get('filter_result', {}).get('method'),
            'confidence': post_data.get('filter_result', {}).get('confidence', 0.0),
            'summary': post_data.get('summary', ''),
            'scraped_at': post_data.get('scraped_at'),
            'notified': False,
        })
        
        return True
        
    except Exception as e:
        print(f"❌ 뽐뿌 게시글 저장 실패: {e}")
        return False


def get_existing_ppomppu_ids(self, limit=1000):
    """
    기존 수집된 뽐뿌 게시글 ID 목록 가져오기
    
    Args:
        limit: 최대 개수 (기본 1000개)
    
    Returns:
        set: post_id 집합
    """
    if not self.db:
        return set()
    
    try:
        docs = self.db.collection('ppomppu_monitor')\
            .document('posts').collection('all_posts')\
            .limit(limit).stream()
        
        post_ids = {doc.id for doc in docs}
        print(f"✅ 기존 뽐뿌 게시글: {len(post_ids)}개")
        return post_ids
        
    except Exception as e:
        print(f"❌ 기존 게시글 조회 실패: {e}")
        return set()


def mark_ppomppu_notified(self, post_id):
    """
    게시글 알림 발송 완료 표시
    
    Args:
        post_id: 게시글 ID
    
    Returns:
        bool: 성공 여부
    """
    if not self.db:
        return False
    
    try:
        from datetime import datetime
        import pytz
        
        doc_ref = self.db.collection('ppomppu_monitor')\
            .document('posts').collection('all_posts').document(post_id)
        
        doc_ref.update({
            'notified': True,
            'notified_at': datetime.now(pytz.timezone('Asia/Seoul'))
        })
        
        return True
        
    except Exception as e:
        print(f"❌ 알림 표시 실패: {e}")
        return False


def save_ppomppu_feedback(self, post_id, is_correct, feedback_type='manual'):
    """
    사용자 피드백 저장 (학습용)
    
    Args:
        post_id: 게시글 ID
        is_correct: True면 "MVNO 맞음", False면 "MVNO 아님"
        feedback_type: 'manual' | 'auto'
    
    Returns:
        bool: 성공 여부
    """
    if not self.db:
        return False
    
    try:
        from datetime import datetime
        import pytz
        
        doc_ref = self.db.collection('ppomppu_monitor')\
            .document('feedback').collection('all_feedback').document(post_id)
        
        # 원본 게시글 정보 가져오기
        post_ref = self.db.collection('ppomppu_monitor')\
            .document('posts').collection('all_posts').document(post_id)
        post_data = post_ref.get().to_dict()
        
        doc_ref.set({
            'post_id': post_id,
            'is_correct': is_correct,
            'feedback_type': feedback_type,
            'original_title': post_data.get('title', '') if post_data else '',
            'original_filter_method': post_data.get('filter_method', '') if post_data else '',
            'original_provider': post_data.get('provider', '') if post_data else '',
            'feedback_at': datetime.now(pytz.timezone('Asia/Seoul')),
        })
        
        print(f"✅ 피드백 저장: {post_id} - {'맞음' if is_correct else '틀림'}")
        return True
        
    except Exception as e:
        print(f"❌ 피드백 저장 실패: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 사용 예시
# ══════════════════════════════════════════════════════════════════════════════

"""
firebase_handler.py 파일에 위 메서드들을 추가하면 됩니다:

class FirebaseHandler:
    # ... 기존 코드 ...
    
    # 뽐뿌 관련 메서드 추가
    def save_ppomppu_post(self, post_data):
        ...
    
    def get_existing_ppomppu_ids(self, limit=1000):
        ...
    
    def mark_ppomppu_notified(self, post_id):
        ...
    
    def save_ppomppu_feedback(self, post_id, is_correct, feedback_type='manual'):
        ...
"""
