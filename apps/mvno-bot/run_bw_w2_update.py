"""
run_bw_w2_update.py
2주차(bw_ai_w2) 실적 피드백 보정 수동 실행 스크립트
- 1주차(bw_ai_w1)도 같이 점검
- 실적 기반 bw_performance로 w1/w2 재계산 → ktoa_daily에 저장

실행: python3 run_bw_w2_update.py
"""

import os, sys, logging
from datetime import datetime, timedelta
from calendar import monthrange

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

# ── Firestore 연결
def get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault())
    return fs.Client(project='mvno-484509', database='mvno-data')

def get_week_of_month(d: datetime) -> int:
    return (d.day - 1) // 7 + 1

def run_bw_week_update(year: int, month: int, week: int):
    """
    특정 주차의 bw_ai_w{N} 필드를 실적(bw_performance) 기반으로 업데이트
    week: 1, 2, 3, 4
    """
    db = get_db()
    field_name = f'bw_ai_w{week}'
    last_day = monthrange(year, month)[1]
    
    updated = 0
    skipped = 0
    no_perf = 0
    
    log.info(f"=== {year}-{month:02d} {week}주차 bw 보정 시작 ({field_name}) ===")
    
    for day in range(1, last_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d = datetime.strptime(ds, '%Y-%m-%d')
        
        # 해당 주차만 처리
        if get_week_of_month(d) != week:
            continue
        
        # 일요일 제외
        if d.weekday() == 6:
            log.info(f"  {ds} (일요일) → 건너뜀")
            continue
        
        # 미래 날짜 제외
        if d.date() > datetime.now().date():
            log.info(f"  {ds} (미래) → 건너뜀")
            continue
        
        # Firestore에서 해당 날짜 데이터 조회
        doc = db.collection('ktoa_daily').document(ds).get()
        if not doc.exists:
            log.warning(f"  {ds} → 문서 없음")
            skipped += 1
            continue
        
        data = doc.to_dict()
        bw_perf = data.get('bw_performance')
        
        if bw_perf is None or float(bw_perf) <= 0:
            # bw_performance 없으면 bw_ai_prev 사용
            bw_perf = data.get('bw_ai_prev')
            if bw_perf is None:
                log.warning(f"  {ds} → bw_performance, bw_ai_prev 모두 없음")
                no_perf += 1
                continue
            log.info(f"  {ds} → bw_performance 없음, bw_ai_prev({bw_perf}) 사용")
        
        bw_val = round(float(bw_perf), 3)
        
        # 기존 값 확인
        existing = data.get(field_name)
        
        # 저장
        db.collection('ktoa_daily').document(ds).set(
            {field_name: bw_val,
             'date': ds,
             f'{field_name}_updated_at': datetime.utcnow()},
            merge=True
        )
        log.info(f"  {ds} → {field_name}={bw_val} "
                 f"(기존: {existing}, bw_perf: {bw_perf})")
        updated += 1
    
    log.info(f"=== 완료: 업데이트 {updated}건, 스킵 {skipped}건, 실적없음 {no_perf}건 ===")
    return updated

if __name__ == '__main__':
    now = datetime.now()
    year, month = now.year, now.month
    
    print(f"\n{'='*50}")
    print(f"bw 주차별 보정 실행: {year}년 {month}월")
    print(f"현재 날짜: {now.strftime('%Y-%m-%d')} ({now.day}일)")
    print(f"{'='*50}\n")
    
    # 현재 주차 확인
    current_week = get_week_of_month(now)
    print(f"현재 {current_week}주차")
    
    # 지난 주차들 모두 보정 (1주차부터 현재 이전 주차까지)
    weeks_to_update = list(range(1, current_week))  # 완료된 주차만
    
    if not weeks_to_update:
        print("보정할 완료 주차 없음 (1주차 진행 중)")
        sys.exit(0)
    
    print(f"보정 대상 주차: {weeks_to_update}")
    print()
    
    total = 0
    for week in weeks_to_update:
        count = run_bw_week_update(year, month, week)
        total += count
        print()
    
    print(f"\n✅ 전체 완료: {total}건 업데이트")