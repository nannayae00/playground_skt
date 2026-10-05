"""
5/13 게시글 테스트 - 실제 배포 코드 사용
"""
import sys
sys.path.insert(0, '/home/mclee_cecilia/price-monitor')

from core.mvno_classifier import check_keywords, normalize_provider, classify_post

# 테스트 게시글 (5/13)
post = {
    'title': '알닷에서 LG U+ 알뜰폰 무료 유심교체 택배로 받은걸로 번이 가능할까요?',
    'body': '''형님들 안녕하세요!
 
기존에 에이모바일(LG U+망)에서 A 스페셜 4.5GB+ 요금제를 사용 중이었어요 (월 8800원)
최근에 슈가모바일(LG U+망)에서 같은 구성인데 금액이 더 저렴한걸 발견해서 번호이동할 계획입니다. (월 5910원)
그런데요!!
알닷에 들어가보니 마침 제가 LG U+ 유심 무료교체 대상인걸 알게 되었어요. 
일단 택배로 신청해뒀는데요. 
 
유심 무료교체 신청해서 받은 유심을, 
기존 통신사가 아닌 새로운 통신사 번호이동시에 개통해도 될까요???
 
무료교체 신청해서 받은 유심은
그냥 일반적인 "모두의 유심 원칩"이랑 같은건지 궁금합니다.''',
    'post_id': 'phone_3916064',
    'link': 'https://www.ppomppu.co.kr/zboard/view.php?id=phone&no=3916064',
    'views': 867,
    'comments': 3,
    'author': '티끌모아라랄라',
}

print("=" * 100)
print("🧪 실제 배포 코드 테스트 - 5/13 게시글")
print("=" * 100)
print(f"제목: {post['title']}")
print(f"링크: {post['link']}")
print(f"조회: {post['views']} | 댓글: {post['comments']}")
print()

# Step 1: 키워드 체크
print("─" * 100)
print("1️⃣ check_keywords() - 키워드 패턴 매칭")
print("─" * 100)
keyword_result = check_keywords(post['title'], post['body'])
print(f"결과: {keyword_result}")
if keyword_result:
    print("✅ 키워드 필터 통과!")
else:
    print("❌ 키워드 필터 탈락")
print()

# Step 2: 사업자 정규화
print("─" * 100)
print("2️⃣ normalize_provider() - 사업자명 감지")
print("─" * 100)
provider = normalize_provider(post['title'] + ' ' + post['body'])
print(f"감지된 사업자: {provider}")
print()

# Step 3: classify_post (룰베이스)
print("─" * 100)
print("3️⃣ classify_post() - 전체 분류 (AI 없이)")
print("─" * 100)
result = classify_post(post['title'], post['body'], use_ai=False)

if result:
    print("✅ MVNO 관련 게시글로 판정!")
    print(f"   분류 방식: {result.get('method')}")
    print(f"   사업자: {result.get('provider', 'N/A')}")
    print(f"   점수: {result.get('score', 0)}")
    print(f"   카테고리: {result.get('category', 'N/A')}")
    print()
    
    # Firebase 저장 여부
    print("─" * 100)
    print("4️⃣ 실제 수집 시 처리")
    print("─" * 100)
    print("✅ Firebase에 저장됨")
    print("✅ 텔레그램 알림 발송됨")
    print()
    print("📱 예상 알림:")
    print(f"   제목: {post['title'][:50]}...")
    print(f"   사업자: {result.get('provider', 'N/A')}")
    print(f"   점수: {result.get('score')}점")
    
else:
    print("❌ MVNO 관련 아님 (수집 안 됨)")
    print("   사유: 키워드 필터링 통과 못 함")

print()
print("=" * 100)

