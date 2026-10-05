import sys
sys.path.insert(0, '/home/mclee_cecilia/price-monitor')

from google.cloud import firestore

db = firestore.Client(project='mvno-484509')

# 찬스모바일 게시글 확인
post_id = 'ppomppu_704616'

doc = db.collection('ppomppu_monitor').document('posts').collection('all_posts').document(post_id).get()

if doc.exists:
    data = doc.to_dict()
    
    print("=" * 80)
    print("💾 Firebase 저장 데이터")
    print("=" * 80)
    print(f"post_id: {post_id}")
    print(f"제목: {data.get('title', 'N/A')[:60]}...")
    print(f"조회수: {data.get('views', 0):,}")
    print(f"댓글: {data.get('comments', 0)}")
    print()
    
    filter_result = data.get('filter_result', {})
    print("─" * 80)
    print("filter_result:")
    print("─" * 80)
    print(f"  relevance_score: {filter_result.get('relevance_score', 'N/A')}")
    print(f"  high_traffic_boost: {filter_result.get('high_traffic_boost', False)}")
    print(f"  high_engagement_boost: {filter_result.get('high_engagement_boost', False)}")
    print(f"  provider: {filter_result.get('provider', 'N/A')}")
    print(f"  category: {filter_result.get('category', 'N/A')}")
    print()
    
    # 별점 계산
    score = filter_result.get('relevance_score', 0)
    stars = '★' * (score // 20) + '☆' * (5 - score // 20)
    print(f"🎯 점수: {score}/10 → {stars}")
    
    print()
    print("=" * 80)
    print("🔍 문제 진단")
    print("=" * 80)
    
    if not filter_result.get('high_traffic_boost'):
        print("❌ high_traffic_boost = False")
        print("   → 조회수 보정이 실행 안 됨!")
        print()
        print("📌 가능한 원인:")
        print("   1. 배포 후 아직 재수집 안 함")
        print("   2. 코드 실행 중 에러 발생")
        print("   3. 이미 70점 이상이었음")
    else:
        print("✅ high_traffic_boost = True")
        print("   → 조회수 보정 실행됨")
        
    if not filter_result.get('high_engagement_boost'):
        print("❌ high_engagement_boost = False")
        print("   → 댓글 보정이 실행 안 됨!")
    else:
        print("✅ high_engagement_boost = True")
        print("   → 댓글 보정 실행됨")
        
else:
    print(f"❌ {post_id} 문서가 Firebase에 없습니다.")

