import sys
sys.path.insert(0, '/home/mclee_cecilia/price-monitor')

# 시뮬레이션
post = {
    'title': '[찬스모바일] U+망 알뜰 100GB+5Mbps 평생요금제(26,900원/무배)',
    'views': 16421,
    'comments': 54,
    'filter_result': {
        'relevance_score': 60  # AI가 준 점수
    }
}

print("=" * 80)
print("🧪 실제 로직 시뮬레이션")
print("=" * 80)

views = post.get('views', 0)
comments = post.get('comments', 0)
current_score = post['filter_result'].get('relevance_score', 5)

print(f"조회수: {views:,}")
print(f"댓글: {comments}")
print(f"AI 초기 점수: {current_score}")
print()

# 조회수 보정
if views >= 10000:
    boosted_score = max(current_score, 70)
    print(f"✅ 조건: views >= 10000 → boosted_score = max({current_score}, 70) = {boosted_score}")
    
    if boosted_score > current_score:
        print(f"   ✅ {boosted_score} > {current_score} → 업데이트!")
        post['filter_result']['relevance_score'] = boosted_score
        current_score = boosted_score
    else:
        print(f"   ❌ {boosted_score} <= {current_score} → 업데이트 안 함")
        
print()

# 댓글 보정
if comments >= 50:
    current_score = post['filter_result'].get('relevance_score', 5)
    new_score = min(current_score + 5, 100)
    print(f"✅ 조건: comments >= 50 → {current_score} + 5 = {new_score}")
    post['filter_result']['relevance_score'] = new_score
    current_score = new_score

print()
print(f"🎯 최종 점수: {current_score}")

# 실제 Firebase 데이터는?
print()
print("=" * 80)
print("💾 Firebase 저장 데이터 확인 필요")
print("=" * 80)
print("Firebase에서 실제 저장된 점수를 확인해야 합니다:")
print("post_id: ppomppu_704616")

