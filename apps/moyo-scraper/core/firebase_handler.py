import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import os
import pytz

KOREA_TZ = pytz.timezone('Asia/Seoul')

class FirebaseHandler:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        key_path = 'service-account-key.json'
        if not os.path.exists(key_path):
            print(f"⚠️ 서비스 계정 키 없음: {key_path}")
            self._initialized = True
            self.db = None
            return
        try:
            cred = credentials.Certificate(key_path)
            try:
                firebase_admin.delete_app(firebase_admin.get_app())
            except ValueError:
                pass
            firebase_admin.initialize_app(cred)
            self.db = firestore.client(database_id='mvno-data')
            self._initialized = True
            print("✅ Firebase 연결 성공 (mvno-data)")
        except Exception as e:
            print(f"❌ Firebase 연결 실패: {e}")
            self.db = None
            self._initialized = True

    def save_check_result(self, site_name, plans, screenshot_path, source_type='manual'):
        """
        요금제 데이터 저장.
        source_type: 'auto' (스케줄 자동) | 'manual' (텔레그램 수동)
        """
        if not self.db:
            print("⚠️ Firebase 미연결")
            return False
        try:
            korea_time = datetime.now(KOREA_TZ)
            timestamp  = korea_time.strftime('%Y-%m-%d_%H:%M:%S')
            history_ref = self.db.collection('price_monitoring')\
                .document(site_name).collection('history').document(timestamp)
            history_ref.set({
                'checked_at':      korea_time,
                'source':          site_name,
                'source_type':     source_type,
                'screenshot_path': screenshot_path,
                'plan_count':      len(plans),
            })
            batch = self.db.batch()
            count = 0
            for plan in plans:
                plan_id = str(plan.get('plan_id', f"plan_{count}"))
                batch.set(history_ref.collection('all_plans').document(plan_id), plan)
                count += 1
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
            batch.commit()
            print(f"✅ Firestore 저장 완료: {count}개 ({source_type})")
            return True
        except Exception as e:
            print(f"❌ Firestore 저장 실패: {e}")
            return False

    def _read_doc(self, doc):
        """history 문서 → plans 포함 dict"""
        data  = doc.to_dict()
        plans = [p.to_dict() for p in doc.reference.collection('all_plans').stream()]
        return {
            'checked_at':  data.get('checked_at'),
            'source_type': data.get('source_type', 'manual'),
            'plan_count':  data.get('plan_count'),
            'plans':       plans,
        }

    def get_latest_data(self, site_name):
        """가장 최근 수집 데이터 (타입 무관)"""
        if not self.db:
            return None
        try:
            docs = list(
                self.db.collection('price_monitoring')
                .document(site_name).collection('history')
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(1).stream()
            )
            return self._read_doc(docs[0]) if docs else None
        except Exception as e:
            print(f"❌ 데이터 조회 실패: {e}")
            return None

    def get_previous_data(self, site_name, compare_type=None):
        """
        비교용 직전 데이터.
        compare_type=None  → 타입 무관 2번째
        compare_type='auto'→ auto 중 2번째
        """
        if not self.db:
            return None
        try:
            q = self.db.collection('price_monitoring')\
                .document(site_name).collection('history')\
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
            if compare_type:
                q = q.where('source_type', '==', compare_type)
            docs = list(q.limit(2).stream())
            return self._read_doc(docs[1]) if len(docs) >= 2 else None
        except Exception as e:
            print(f"❌ 이전 데이터 조회 실패: {e}")
            return None

    def get_latest_auto_data(self, site_name):
        """가장 최근 auto 수집 데이터"""
        if not self.db:
            return None
        try:
            docs = list(
                self.db.collection('price_monitoring')
                .document(site_name).collection('history')
                .where('source_type', '==', 'auto')
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(1).stream()
            )
            return self._read_doc(docs[0]) if docs else None
        except Exception as e:
            print(f"❌ auto 데이터 조회 실패: {e}")
            return None

    def get_recent_plan_ids(self, site_name, limit=5, source_type='auto'):
        """
        최근 N개 수집의 plan_id 합집합.
        auto가 부족하면 manual 포함해서 보충.
        """
        if not self.db:
            return set()
        try:
            all_ids = set()
            base = self.db.collection('price_monitoring')                .document(site_name).collection('history')

            # 1. auto 우선
            auto_docs = []
            if source_type:
                auto_docs = list(
                    base.where('source_type', '==', source_type)
                    .order_by('checked_at', direction=firestore.Query.DESCENDING)
                    .limit(limit).stream()
                )
                for doc in auto_docs:
                    for p in doc.reference.collection('all_plans').stream():
                        pid = p.to_dict().get('plan_id')
                        if pid: all_ids.add(str(pid))

            # 2. auto 부족 시 전체(manual 포함)로 보충
            if len(auto_docs) < limit:
                for doc in base.order_by('checked_at', direction=firestore.Query.DESCENDING)                               .limit(limit).stream():
                    for p in doc.reference.collection('all_plans').stream():
                        pid = p.to_dict().get('plan_id')
                        if pid: all_ids.add(str(pid))

            print(f"✅ 최근 plan_id 합집합: {len(all_ids)}개 (auto {len(auto_docs)}개 기준)")
            return all_ids
        except Exception as e:
            print(f"❌ recent plan_ids 조회 실패: {e}")
            return set()

    def save_daily_summary(self, site_name, summary_data):
        if not self.db: return False
        try:
            korea_time = datetime.now(KOREA_TZ)
            date_str   = korea_time.strftime('%Y-%m-%d')
            self.db.collection('daily_analysis').document(date_str).set({
                'site': site_name, 'analyzed_at': korea_time, 'summary': summary_data
            })
            print(f"✅ {date_str} 일별 요약 저장 완료")
            return True
        except Exception as e:
            print(f"❌ 일별 요약 저장 실패: {e}")
            return False


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
