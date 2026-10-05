"""
firebase_handler.py  v1.12
수정일시: 2026-09-20

[v1.12 / 2026-09-20]
- 컨테이너 이미지에 service-account-key.json 그대로 baking하던 방식 제거,
  ApplicationDefault()로 전환 (Cloud Run 런타임 서비스 계정 자격증명 사용)
- save_ppomppu_post()의 network 추론이 존재하지 않는 scrapers.mvno_classifier.
  infer_network_from_provider를 import하려다 매번 조용히 실패하던 버그 수정
  (core.mvno_classifier에 실제로 구현하고 import 경로 수정)

[v1.11 / 2026-08-25]
- RS 스냅샷에 run_slot('morning'/'afternoon'/'evening') 태깅 추가
  · save_rs_snapshot()에 run_slot 파라미터 추가 (저장 시 함께 기록)
  · get_rs_snapshot_by_slot() 신규: 시각(hour) 매칭 대신 run_slot 필드로 정확한 회차 매칭
    (3사 통합 수집으로 저장 시각이 스케줄 시각보다 40분+ 밀리는 구조라 시각 기준 매칭은 부정확해짐)
  · 하루 3회(08/13/17시) 비교 로직 변경(scrape_job.py) 대응: 08시→전일08시, 13시→당일08시, 17시→당일13시
  · 기존 get_rs_snapshot(target_hour 기준)은 레거시로 유지 (하위호환, 신규 코드는 by_slot 사용 권장)

[v1.10 / 2026-08-24]
- save_rs_snapshot() / get_rs_snapshot() / get_latest_rs_snapshot()에 snap_type 파라미터 추가
  · 'general'(일반사업자, 기존 moyo_rs_snapshot 문서명 유지·하위호환) / 'sub'(자회사 신규) / 'mno'(MNO 신규)
  · 3사(모요+알닷+허브) 통합 발송 구조 변경(scrape_job.py) 대응 — 자회사/MNO도 현재/직전/Gap 비교 지원

[v1.9 / 2026-06-02]
- save_ppomppu_post(): Vision 분석 필드 추가
  · vision_analyzed, vision_price, vision_data (별3개 게시글 이미지 분석 결과)
  · contract_months (약정 개월)
  · is_affiliated (자회사 여부)


[v1.8 / 2026-04-21]
- save_dcinside_post(): post_id 정제 로직 추가
  · 슬래시/공백 제거, 빈 값이면 저장 스킵
  · "A document must have an even number of path elements" 오류 해결

[v1.6 / 2026-03-17]
- save_rs_snapshot() 추가: RS 구간별 망별 최저가 스냅샷 저장
  · 저장 경로: price_monitoring/moyo_rs_snapshot/history/{YYYY-MM-DD_HH:MM}
  · 전체 요금제 대신 최저가 숫자만 저장 → 빠른 조회 + Firestore 비용 절감
- get_rs_snapshot() 추가: 특정 시간대 RS 스냅샷 조회
  · days_ago, target_hour 파라미터로 시간대 지정
- get_latest_rs_snapshot() 추가: 가장 최근 스냅샷 조회

[v1.5 / 2026-03-10]
- save_dcinside_post() 추가: 디시인사이드 게시글 저장 (사업자/망/sentiment/topic 포함)

[v1.4 변경사항]
- save_guide_prices: guide_date 파라미터 누락 재확인 및 배포 반영

[v1.3]
- save_guide_prices(): guide_date 파라미터 추가 (기준 날짜 별도 저장)

[v1.2]
- save_guide_prices() 추가: 구간별 SKT 가이드 금액 Firebase 저장
- get_guide_prices() 추가: 저장된 가이드 금액 조회
- GUIDE_SEGMENTS 상수 추가: 구간 순서 고정

[v1.1 / 2026-03-06]
- get_data_by_hour() 추가
  · 특정 날짜/시간대(target_hour) auto 수집 데이터 조회
  · days_ago=0(오늘) / days_ago=1(어제) 선택

[v1.0 / 2026-03-05]
- save_ppomppu_post: 신규=전체저장, 기존=조회수/댓글만 업데이트
- relevance_score, content_summary 필드 추가 저장
"""
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
        # [v1.12] 컨테이너 이미지에 service-account-key.json을 그대로 baking하던 방식
        # 제거 (Cloud Build 업로드 때마다 키가 평문으로 올라가는 구조였음).
        # 이 job의 Cloud Run 런타임 서비스 계정이 기존 키 파일과 동일한
        # 668782164620-compute@developer.gserviceaccount.com 이라서, 키 파일 없이
        # ApplicationDefault()로 GCP가 자동 부여하는 런타임 자격증명을 쓰면 동일한
        # 권한으로 그대로 동작 — 별도 Secret Manager 설정이나 IAM 변경 불필요.
        # 로컬 개발 등 GOOGLE_APPLICATION_CREDENTIALS가 설정된 환경에서는 그 값을 우선 사용.
        try:
            cred = credentials.ApplicationDefault()
            try:
                firebase_admin.delete_app(firebase_admin.get_app())
            except ValueError:
                pass
            firebase_admin.initialize_app(cred, {'projectId': 'mvno-484509'})
            self.db = firestore.client(database_id='mvno-data')
            self._initialized = True
            print("✅ Firebase 연결 성공 (mvno-data, ApplicationDefault)")
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

    def get_data_by_hour(self, site_name, target_hour=8, days_ago=0):
        """
        특정 날짜의 target_hour 시간대에 수집된 auto 데이터 반환.

        days_ago=0 → 오늘
        days_ago=1 → 어제

        예) 13시/17시 수집 → get_data_by_hour(target_hour=8, days_ago=0)  → 금일 08시
            08시 수집     → get_data_by_hour(target_hour=8, days_ago=1)  → 전일 08시
        """
        if not self.db:
            return None
        try:
            korea_now  = datetime.now(KOREA_TZ)
            target_date = (korea_now - timedelta(days=days_ago)).date()

            # target_hour 시간대 범위 설정 (예: 08:00 ~ 08:59)
            tz         = KOREA_TZ
            range_start = tz.localize(datetime(target_date.year, target_date.month,
                                               target_date.day, target_hour, 0, 0))
            range_end   = tz.localize(datetime(target_date.year, target_date.month,
                                               target_date.day, target_hour, 59, 59))

            docs = list(
                self.db.collection('price_monitoring')
                .document(site_name).collection('history')
                .where('source_type', '==', 'auto')
                .where('checked_at', '>=', range_start)
                .where('checked_at', '<=', range_end)
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(1).stream()
            )
            if docs:
                print(f"✅ {target_date} {target_hour:02d}시 데이터 조회 성공")
                return self._read_doc(docs[0])
            else:
                print(f"⚠️ {target_date} {target_hour:02d}시 데이터 없음")
                return None
        except Exception as e:
            print(f"❌ get_data_by_hour 조회 실패: {e}")
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
            base = self.db.collection('price_monitoring').document(site_name).collection('history')

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
                for doc in base.order_by('checked_at', direction=firestore.Query.DESCENDING).limit(limit).stream():
                    for p in doc.reference.collection('all_plans').stream():
                        pid = p.to_dict().get('plan_id')
                        if pid: all_ids.add(str(pid))

            print(f"✅ 최근 plan_id 합집합: {len(all_ids)}개 (auto {len(auto_docs)}개 기준)")
            return all_ids
        except Exception as e:
            print(f"❌ recent plan_ids 조회 실패: {e}")
            return set()

    # ═══════════════════════════════════════════════════════════════════════
    # 가이드 금액 관련 메서드
    # ═══════════════════════════════════════════════════════════════════════

    # 구간 순서 고정 (표시/입력 순서)
    GUIDE_SEGMENTS = ['7G+', '10G+', '11G+', '15G+100', '15G+300', '100G+']

    # snap_type → Firestore 문서명 매핑
    # 'general'은 기존 moyo_rs_snapshot 문서명을 그대로 유지 (하위호환, 기존 이력 보존)
    _SNAPSHOT_DOC = {
        'general': 'moyo_rs_snapshot',
        'sub':     'sub_rs_snapshot',
        'mno':     'mno_rs_snapshot',
    }

    # ═══════════════════════════════════════════════════════════════════════
    # RS 최저가 스냅샷
    # ═══════════════════════════════════════════════════════════════════════

    def save_rs_snapshot(self, rs_min: dict, source_type: str = 'auto', snap_type: str = 'general', run_slot: str = None):
        """
        RS 구간별 망별 최저가 스냅샷 저장.

        rs_min 형식:
          {
            '7G+':     {'SKT': 8470, 'KT': 10000, 'LGU+': 8000},
            '10G+':    {'SKT': 14000, 'KT': 13000, 'LGU+': 12000},
            ...
          }

        snap_type: 'general'(일반사업자, 기존 moyo_rs_snapshot) / 'sub'(자회사) / 'mno'(MNO)
        run_slot:  'morning'(08시) / 'afternoon'(13시) / 'evening'(17시) — 실제 저장 시각이
                   집계 소요시간(3사 통합 후 저장이라 40분+ 소요)만큼 밀려도 정확한 회차 매칭을 위해 태깅
        저장 경로: price_monitoring/{doc}/history/{YYYY-MM-DD_HH:MM}
        """
        if not self.db:
            return False
        try:
            doc_name   = self._SNAPSHOT_DOC.get(snap_type, 'moyo_rs_snapshot')
            korea_time = datetime.now(KOREA_TZ)
            doc_id     = korea_time.strftime('%Y-%m-%d_%H:%M')
            self.db.collection('price_monitoring')                 .document(doc_name)                 .collection('history')                 .document(doc_id)                 .set({
                    'checked_at':  korea_time,
                    'source_type': source_type,
                    'run_slot':    run_slot,
                    'rs_min':      rs_min,
                })
            print(f"✅ RS 스냅샷 저장 완료 [{snap_type}/{run_slot}]: {doc_id}")
            return True
        except Exception as e:
            print(f"❌ RS 스냅샷 저장 실패 [{snap_type}]: {e}")
            return False

    def get_rs_snapshot_by_slot(self, run_slot: str, days_ago: int = 0, snap_type: str = 'general'):
        """
        특정 날짜의 run_slot(morning/afternoon/evening) 스냅샷 조회.
        시각(hour) 기준이 아니라 저장 시 태깅한 run_slot 필드로 매칭 — 집계 소요시간에 따른
        저장시각 드리프트(예: 07:30 시작 → 08:1x 저장)에 영향받지 않음.

        days_ago=0 → 오늘, days_ago=1 → 어제
        반환: {'checked_at': datetime, 'rs_min': {...}} 또는 None
        """
        if not self.db:
            return None
        try:
            doc_name    = self._SNAPSHOT_DOC.get(snap_type, 'moyo_rs_snapshot')
            korea_now   = datetime.now(KOREA_TZ)
            target_date = (korea_now - timedelta(days=days_ago)).date()
            range_start = KOREA_TZ.localize(datetime(
                target_date.year, target_date.month, target_date.day, 0, 0, 0))
            range_end   = KOREA_TZ.localize(datetime(
                target_date.year, target_date.month, target_date.day, 23, 59, 59))

            docs = list(
                self.db.collection('price_monitoring')
                .document(doc_name)
                .collection('history')
                .where('checked_at', '>=', range_start)
                .where('checked_at', '<=', range_end)
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(10).stream()
            )
            for doc in docs:
                d = doc.to_dict()
                if d.get('run_slot') == run_slot:
                    print(f"✅ RS 스냅샷 조회 성공 [{snap_type}/{run_slot}]: {target_date}")
                    return {'checked_at': d.get('checked_at'), 'rs_min': d.get('rs_min', {})}
            print(f"⚠️ RS 스냅샷 없음 [{snap_type}/{run_slot}]: {target_date}")
            return None
        except Exception as e:
            print(f"❌ RS 스냅샷 조회 실패 [{snap_type}/{run_slot}]: {e}")
            return None

    def get_rs_snapshot(self, target_hour: int = 8, days_ago: int = 0, snap_type: str = 'general'):
        """
        [레거시] 특정 날짜/시간대의 RS 스냅샷 조회 (시각 기준 매칭).
        신규 코드는 get_rs_snapshot_by_slot() 사용 권장 — 저장시각 드리프트에 취약함.

        days_ago=0 → 오늘, days_ago=1 → 어제
        target_hour=8 → 08:00~08:59 사이 수집분
        snap_type: 'general' / 'sub' / 'mno'

        반환: {'checked_at': datetime, 'rs_min': {...}} 또는 None
        """
        if not self.db:
            return None
        try:
            doc_name    = self._SNAPSHOT_DOC.get(snap_type, 'moyo_rs_snapshot')
            korea_now   = datetime.now(KOREA_TZ)
            target_date = (korea_now - timedelta(days=days_ago)).date()
            range_start = KOREA_TZ.localize(datetime(
                target_date.year, target_date.month, target_date.day, target_hour, 0, 0))
            range_end   = KOREA_TZ.localize(datetime(
                target_date.year, target_date.month, target_date.day, target_hour, 59, 59))

            docs = list(
                self.db.collection('price_monitoring')
                .document(doc_name)
                .collection('history')
                .where('checked_at', '>=', range_start)
                .where('checked_at', '<=', range_end)
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(1).stream()
            )
            if docs:
                d = docs[0].to_dict()
                print(f"✅ RS 스냅샷 조회 성공 [{snap_type}]: {target_date} {target_hour:02d}시")
                return {'checked_at': d.get('checked_at'), 'rs_min': d.get('rs_min', {})}
            print(f"⚠️ RS 스냅샷 없음 [{snap_type}]: {target_date} {target_hour:02d}시")
            return None
        except Exception as e:
            print(f"❌ RS 스냅샷 조회 실패 [{snap_type}]: {e}")
            return None

    def get_latest_rs_snapshot(self, exclude_current: bool = False, snap_type: str = 'general'):
        """
        가장 최근 RS 스냅샷 조회.
        exclude_current=True: 현재 시간대 제외 (직전 스냅샷)
        snap_type: 'general' / 'sub' / 'mno'
        """
        if not self.db:
            return None
        try:
            doc_name = self._SNAPSHOT_DOC.get(snap_type, 'moyo_rs_snapshot')
            limit    = 2 if exclude_current else 1
            docs     = list(
                self.db.collection('price_monitoring')
                .document(doc_name)
                .collection('history')
                .order_by('checked_at', direction=firestore.Query.DESCENDING)
                .limit(limit).stream()
            )
            if not docs:
                return None
            doc = docs[-1] if exclude_current and len(docs) > 1 else docs[0]
            d   = doc.to_dict()
            return {'checked_at': d.get('checked_at'), 'rs_min': d.get('rs_min', {})}
        except Exception as e:
            print(f"❌ 최근 RS 스냅샷 조회 실패 [{snap_type}]: {e}")
            return None

    def save_guide_prices(self, prices: dict, updated_by: str = 'manual', guide_date: str = ''):
        """
        가이드 금액 저장.
        prices:     {'7G+': 10000, '10G+': 14000, ...}
        guide_date: '03/01' 형식 기준 날짜 (사용자 입력)
        Firebase:   price_monitoring/moyo/config/guide_prices (단일 문서, 덮어쓰기)
        """
        if not self.db:
            return False
        try:
            korea_time = datetime.now(KOREA_TZ)
            if not guide_date:
                guide_date = korea_time.strftime('%m/%d')
            self.db.collection('price_monitoring').document('moyo')\
                .collection('config').document('guide_prices').set({
                    'prices':     prices,
                    'guide_date': guide_date,
                    'updated_at': korea_time,
                    'updated_by': updated_by,
                })
            print(f"✅ 가이드 금액 저장 완료 ({guide_date} 기준): {prices}")
            return True
        except Exception as e:
            print(f"❌ 가이드 금액 저장 실패: {e}")
            return False

    def get_guide_prices(self):
        """
        가이드 금액 조회.
        반환: {'prices': {...}, 'updated_at': datetime} 또는 None
        """
        if not self.db:
            return None
        try:
            doc = self.db.collection('price_monitoring').document('moyo')\
                .collection('config').document('guide_prices').get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"❌ 가이드 금액 조회 실패: {e}")
            return None

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

    # ═══════════════════════════════════════════════════════════════════════
    # 뽐뿌 관련 메서드
    # ═══════════════════════════════════════════════════════════════════════

    def save_ppomppu_post(self, post_data):
        """뽐뿌 게시글 저장
        - 신규 글: 전체 필드 저장 → True 반환
        - 기존 글: 조회수/댓글만 업데이트 → False 반환
        """
        if not self.db:
            print("⚠️ Firebase 미연결")
            return False

        try:
            post_id = post_data['post_id']
            doc_ref = self.db.collection('ppomppu_monitor')\
                .document('posts').collection('all_posts').document(post_id)

            doc = doc_ref.get()

            if doc.exists:
                # 기존 글: 조회수/댓글만 업데이트
                doc_ref.update({
                    'views':      post_data.get('views', 0),
                    'comments':   post_data.get('comments', 0),
                    'updated_at': datetime.now(KOREA_TZ),
                })
                return False  # 기존 글 업데이트
            else:
                # 신규 글: 전체 저장
                filter_result = post_data.get('filter_result', {})

                # network: Gemini 결과 우선, 없으면 사업자명으로 고정망 추론
                network = filter_result.get('network')
                if not network:
                    try:
                        from core.mvno_classifier import infer_network_from_provider
                        network = infer_network_from_provider(filter_result.get('provider'))
                    except Exception:
                        network = None

                doc_ref.set({
                    'post_id':         post_id,
                    'title':           post_data.get('title', ''),
                    'url':             post_data.get('url', ''),
                    'views':           post_data.get('views', 0),
                    'comments':        post_data.get('comments', 0),
                    'posted_at':       post_data.get('posted_at'),
                    'content':         post_data.get('content', ''),
                    'author':          post_data.get('author', '익명'),
                    'provider':        filter_result.get('provider'),
                    'network':         network,
                    'filter_method':   filter_result.get('method'),
                    'confidence':      filter_result.get('confidence', 0.0),
                    'relevance_score': filter_result.get('relevance_score', 0),
                    'content_summary': filter_result.get('content_summary', ''),
                    'is_affiliated':   filter_result.get('is_affiliated', False),
                    # Vision 분석 결과 (별3개 게시글)
                    'vision_analyzed':  filter_result.get('vision_analyzed', False),
                    'vision_price':     filter_result.get('vision_price'),
                    'vision_data':      filter_result.get('vision_data'),
                    'contract_months':  filter_result.get('contract_months', 0),
                    'summary':         post_data.get('summary', ''),
                    'scraped_at':      post_data.get('scraped_at'),
                    'saved_at':        datetime.now(KOREA_TZ),
                    'notified':        False,
                })
                return True  # 신규 저장

        except Exception as e:
            print(f"❌ 뽐뿌 게시글 저장 실패: {e}")
            return False

    def get_existing_ppomppu_ids(self, limit=5000):
        """기존 수집된 뽐뿌 게시글 ID 목록"""
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

    def get_existing_ppomppu_posts(self, limit=5000):
        """기존 수집된 뽐뿌 게시글 {id: {views, comments}} 반환 (급증 비교용)"""
        if not self.db:
            return {}
        try:
            docs = self.db.collection('ppomppu_monitor')                .document('posts').collection('all_posts')                .limit(limit).stream()
            result = {}
            for doc in docs:
                d = doc.to_dict()
                result[doc.id] = {
                    'views':    d.get('views', 0),
                    'comments': d.get('comments', 0),
                }
            print(f"✅ 기존 뽐뿌 게시글: {len(result)}개")
            return result
        except Exception as e:
            print(f"❌ 기존 게시글 조회 실패: {e}")
            return {}


    def save_dcinside_post(self, post_data):
        """디시인사이드 게시글 저장
        - 신규 글: 전체 필드 저장 → True 반환
        - 기존 글: 조회수/댓글만 업데이트 → False 반환
        """
        if not self.db:
            print("⚠️ Firebase 미연결")
            return False

        try:
            post_id = str(post_data.get('post_id', ''))

            # post_id 정제: 슬래시/공백 제거, 숫자+영문+언더스코어만 허용
            import re as _re
            post_id = _re.sub(r'[/\\\s]', '_', post_id).strip('_')

            if not post_id:
                print(f"⚠️ post_id 없음 - 저장 스킵: {post_data.get('title','')[:30]}")
                return False

            doc_ref = self.db.collection('dcinside_monitor')\
                .document('posts').collection('all_posts').document(post_id)

            doc = doc_ref.get()
            if doc.exists:
                doc_ref.update({
                    'views':      post_data.get('views', 0),
                    'comments':   post_data.get('comments', 0),
                    'updated_at': datetime.now(KOREA_TZ),
                })
                return False
            else:
                doc_ref.set({
                    'post_id':   post_id,
                    'gallery':   post_data.get('gallery', ''),
                    'title':     post_data.get('title', ''),
                    'url':       post_data.get('url', ''),
                    'views':     post_data.get('views', 0),
                    'comments':  post_data.get('comments', 0),
                    'posted_at': post_data.get('posted_at'),
                    'provider':  post_data.get('provider', ''),
                    'network':   post_data.get('network', ''),
                    'sentiment': post_data.get('sentiment', '중립'),
                    'topic':     post_data.get('topic', ''),
                    'saved_at':  datetime.now(KOREA_TZ),
                })
                return True

        except Exception as e:
            print(f"❌ 디시 게시글 저장 실패: {e}")
            return False
    def mark_ppomppu_notified(self, post_id):
        """게시글 알림 발송 완료 표시"""
        if not self.db:
            return False
        
        try:
            doc_ref = self.db.collection('ppomppu_monitor')\
                .document('posts').collection('all_posts').document(post_id)
            
            doc_ref.update({
                'notified': True,
                'notified_at': datetime.now(KOREA_TZ)
            })
            
            return True
            
        except Exception as e:
            print(f"❌ 알림 표시 실패: {e}")
            return False