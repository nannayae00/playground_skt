from core.firebase_handler import FirebaseHandler
from core.comparator import Comparator

print("🔍 디버깅 시작\n")

# 1. Firestore 데이터 확인
db = FirebaseHandler()
latest = db.get_latest_data('moyo')

if latest and latest.get('plans'):
    plans = latest['plans']
    print(f"📦 수집된 요금제: {len(plans)}개\n")
    
    # 경쟁사만 필터링
    competitors = [p for p in plans if p.get('is_competitor', False)]
    print(f"🎯 경쟁사(KT/LG): {len(competitors)}개\n")
    
    # 데이터량별 분포
    from collections import Counter
    data_counts = Counter([p.get('data_gb', 0) for p in competitors])
    print("📊 데이터량별 분포:")
    for gb, count in sorted(data_counts.items()):
        print(f"   {gb}GB: {count}개")
    
    # 우리 요금제 확인
    comparator = Comparator()
    print(f"\n💼 우리 요금제: {len(comparator.our_plans)}개")
    for plan in comparator.our_plans:
        print(f"   {plan['name']}: {plan['data_gb']}GB - {plan['final_price']:,}원")
    
    # 5GB 경쟁사 찾기
    print("\n🔍 5GB 경쟁사 요금제:")
    gb5_competitors = [p for p in competitors if p.get('data_gb') == 5]
    if gb5_competitors:
        for p in gb5_competitors[:3]:
            print(f"   {p['display_name']}: {p['final_price']:,}원")
    else:
        print("   없음!")
    
    # 10GB 경쟁사 찾기
    print("\n🔍 10GB 경쟁사 요금제:")
    gb10_competitors = [p for p in competitors if p.get('data_gb') == 10]
    if gb10_competitors:
        for p in gb10_competitors[:3]:
            print(f"   {p['display_name']}: {p['final_price']:,}원")
    else:
        print("   없음!")
    
    # 실제 수집된 데이터 샘플
    print("\n📋 수집된 요금제 샘플 (처음 3개):")
    for i, p in enumerate(plans[:3], 1):
        print(f"\n{i}. {p.get('display_name', '?')}")
        print(f"   데이터: {p.get('data', '?')} ({p.get('data_gb', '?')}GB)")
        print(f"   가격: {p.get('final_price', '?'):,}원")
        print(f"   경쟁사: {p.get('is_competitor', '?')}")
        print(f"   통신망: {p.get('network', '?')}")

else:
    print("❌ 데이터 없음")
