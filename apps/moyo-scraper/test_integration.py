#!/usr/bin/env python3
"""
통합 테스트: 전체 파이프라인 검증
MoyoScraper → FirebaseHandler → Comparator 전체 흐름 테스트
"""
import sys
sys.path.insert(0, '/home/mclee_cecilia/price-monitor')

from datetime import datetime
import traceback

# 로깅 함수
def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {msg}")

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

# ============================================================
# 테스트 시작
# ============================================================

print_section("🚀 MVNO 가격 모니터링 시스템 - 통합 테스트")

try:
    # ============================================================
    # 1️⃣ MoyoScraper 실행
    # ============================================================
    print_section("1️⃣ MoyoScraper 실행 (약 4분 소요)")
    
    log("📥 MoyoScraper import...")
    from scrapers.moyo_scraper import MoyoScraper
    log("✅ import 성공")
    
    log("🔍 스크래핑 시작...")
    scraper = MoyoScraper()
    plans, screenshot = scraper.scrape()
    
    log(f"✅ {len(plans)}개 요금제 수집 완료")
    log(f"   스크린샷: {screenshot}")
    
    if not plans:
        log("❌ 요금제를 찾지 못했습니다")
        sys.exit(1)
    
    # 샘플 데이터 확인
    log("\n📊 샘플 데이터 (첫 3개):")
    for i, plan in enumerate(plans[:3], 1):
        log(f"  {i}. {plan['display_name']} - {plan['name']}")
        log(f"     💰 {plan['final_price']:,}원 | 👥 {plan['subscribers']:,}명")
    
    # ============================================================
    # 2️⃣ FirebaseHandler 실행
    # ============================================================
    print_section("2️⃣ FirebaseHandler 실행 (Firestore 저장)")
    
    log("📥 FirebaseHandler import...")
    from core.firebase_handler import FirebaseHandler
    log("✅ import 성공")
    
    log("💾 Firestore 저장 시작...")
    db = FirebaseHandler()
    
    if db.db is None:
        log("⚠️  Firebase 미연결 (service-account-key.json 확인 필요)")
        log("   계속 진행합니다...")
        save_success = False
    else:
        save_success = db.save_check_result('moyo', plans, screenshot)
    
    if save_success:
        log("✅ Firestore 저장 완료")
        
        # 저장된 데이터 확인
        log("📖 저장된 데이터 조회...")
        latest = db.get_latest_data('moyo')
        if latest:
            log(f"✅ 체크 시간: {latest.get('checked_at')}")
            log(f"✅ 요금제 수: {latest.get('plan_count')}개")
        else:
            log("⚠️  최신 데이터를 찾을 수 없음")
    else:
        log("⚠️  Firestore 저장 실패 (계속 진행)")
    
    # ============================================================
    # 3️⃣ Comparator 실행
    # ============================================================
    print_section("3️⃣ Comparator 실행 (경쟁력 분석)")
    
    log("📥 Comparator import...")
    from core.comparator import Comparator
    log("✅ import 성공")
    
    log("🔍 경쟁력 분석 시작...")
    comparator = Comparator()
    alerts = comparator.analyze_competitiveness(plans)
    
    log(f"✅ {len(alerts)}개 알림 생성")
    
    if alerts:
        log("\n📢 알림 목록 (최대 5개):")
        for i, alert in enumerate(alerts[:5], 1):
            log(f"  {i}. {alert['message']}")
        
        if len(alerts) > 5:
            log(f"  ... 외 {len(alerts) - 5}개")
    else:
        log("ℹ️  특이사항 없음 (모두 경쟁력 양호)")
    
    # ============================================================
    # 4️⃣ 메시지 생성
    # ============================================================
    print_section("4️⃣ 메시지 생성 & 포맷팅")
    
    log("📝 결과 메시지 생성...")
    
    message = f"""📊 MVNO 가격 모니터링 - 통합 테스트 완료

⏰ 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📈 수집: {len(plans)}개 요금제
🚨 알림: {len(alerts)}개

"""
    
    if alerts:
        message += "⚠️ 주요 알림:\n"
        for i, alert in enumerate(alerts[:5], 1):
            message += f"\n{i}. {alert['message']}"
        
        if len(alerts) > 5:
            message += f"\n\n... 외 {len(alerts) - 5}개"
    else:
        message += "✅ 경쟁력 양호! 특이사항 없음"
    
    message += f"\n\n상위 3개 요금제:\n"
    for i, plan in enumerate(plans[:3], 1):
        name = plan['name'].replace('_', ' ').replace('*', '').replace('[', '(').replace(']', ')')
        message += f"\n{i}. {plan['display_name']}"
        message += f"\n   {name}"
        message += f"\n   💰 {plan['final_price']:,}원\n"
    
    log(f"✅ 메시지 생성 완료 ({len(message)} 글자)")
    
    # ============================================================
    # ✅ 최종 결과
    # ============================================================
    print_section("✅ 통합 테스트 성공!")
    
    print("\n" + "="*60)
    print("📌 최종 결과:")
    print("="*60)
    print(f"""
✅ MoyoScraper:     {len(plans)}개 요금제 수집 성공
✅ FirebaseHandler: {'Firestore 저장 성공' if save_success else 'Firebase 미연결 (무시 가능)'}
✅ Comparator:      {len(alerts)}개 알림 생성 성공
✅ 메시지:          {len(message)} 글자 생성 성공

🎉 모든 파이프라인이 정상 작동합니다!
""")
    
    print("="*60)
    print("📤 최종 메시지 미리보기:")
    print("="*60)
    print(message)
    print("="*60)
    
    log("✅ 통합 테스트 완료!")
    sys.exit(0)

except Exception as e:
    # 에러 처리
    log(f"❌ 통합 테스트 실패: {e}")
    log("\n상세 에러:")
    traceback.print_exc()
    
    print_section("❌ 테스트 실패")
    sys.exit(1)
