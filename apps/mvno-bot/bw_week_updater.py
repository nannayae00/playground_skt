"""
bw_week_updater.py  v2.0
Cloud Run Job — 매주 월요일 + 매월 말일 자동 실행

[수정 이력]
v2.1 | 2026-04-15 | 경과일 bw_ai_w{N} 동시 저장
  - calc_and_save_bw_performance(): also_save_as 파라미터 추가
    경과일에 bw_performance와 동일값을 bw_ai_w{N}에도 저장
    → 엑셀 S5 시트에 1~14일 공백 없이 표시
v2.0 | 2026-04-15 | 전면 재작성 — 올바른 주차별 로직 구현
  - 경과일: bw_performance 역산 저장 (실제 실적 기반)
  - 미래일: calc_bw_ai() 재예측 → bw_ai_w{N} 저장
    (K-NN이 이미 쌓인 실적 자동 반영 → 정확도 향상)
  - w0(월초): 매월 말일 다음달 전체 사전 계산
  - 스케줄:
      매주 월요일 09:00 KST → 직전 주차 보정
      매월 말일  21:00 KST → 다음달 w0 사전 계산
v1.0 | 2026-04-15 | 최초 작성 (단순 복사 방식 — 폐기)

[주차별 처리 로직]
  bw_ai_w1 완료 시 (1주차 종료 후):
    1~ 7일: bw_performance 역산 (실적 확정)
    8~30일: calc_bw_ai() 재예측 (1주차 실적 K-NN 반영)

  bw_ai_w2 완료 시 (2주차 종료 후):
    1~14일: bw_performance 역산 (실적 확정)
   15~30일: calc_bw_ai() 재예측 (1~2주차 실적 K-NN 반영)

  bw_ai_w3 완료 시 (3주차 종료 후):
    1~21일: bw_performance 역산 (실적 확정)
   22~30일: calc_bw_ai() 재예측 (1~3주차 실적 K-NN 반영)

  bw_performance (월마감):
    1~30일: bw_performance 최종 역산
"""

import logging, os, sys
from datetime import datetime, timedelta
from calendar import monthrange

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)

PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'mvno-484509')
DATABASE   = os.environ.get('FIRESTORE_DATABASE',   'mvno-data')


# ── Firestore 연결
def get_db():
    from google.cloud import firestore
    return firestore.Client(project=PROJECT_ID, database=DATABASE)


def get_week_of_month(d: datetime) -> int:
    return (d.day - 1) // 7 + 1


def is_zero_day(d: datetime) -> bool:
    """영업 0일 — 일요일 또는 공휴일 (공휴일은 bw_engine 참조)"""
    if d.weekday() == 6:
        return True
    # 공휴일 체크는 bw_engine에 위임
    try:
        from bw_engine import _is_holiday
        return _is_holiday(d.strftime('%Y-%m-%d'))
    except Exception:
        return False


# ── bw_performance 역산 (실적 기반)
def calc_and_save_bw_performance(db, year: int, month: int,
                                  day_from: int, day_to: int,
                                  month_avg: float,
                                  also_save_as: str = None) -> int:
    """
    day_from ~ day_to 범위: bw_performance 역산 저장
    bw_performance = mvno_in_당일 / mvno_in_월평균
    also_save_as: 지정 시 해당 필드(bw_ai_w1 등)에도 동일 값 저장
    """
    saved = 0
    for day in range(day_from, day_to + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d  = datetime.strptime(ds, '%Y-%m-%d')
        if is_zero_day(d):
            continue

        doc = db.collection('ktoa_daily').document(ds).get()
        if not doc.exists:
            log.warning(f"  {ds} → 문서 없음, bw_performance 스킵")
            continue

        data     = doc.to_dict()
        mvno_in  = data.get('mvno_in', {})
        total_in = mvno_in.get('계', 0) if isinstance(mvno_in, dict) else 0

        if not total_in or month_avg <= 0:
            log.warning(f"  {ds} → mvno_in 없음 (total={total_in}, avg={month_avg})")
            continue

        bw_perf = round(total_in / month_avg, 3)
        update_data = {
            'bw_performance': bw_perf,
            'date': ds,
            'bw_performance_updated_at': datetime.now()
        }
        # ★ 경과일에도 bw_ai_w{N} 필드에 동일값 저장 (엑셀 S5 시트 표시용)
        if also_save_as:
            update_data[also_save_as] = bw_perf
            update_data[f'{also_save_as}_updated_at'] = datetime.now()

        db.collection('ktoa_daily').document(ds).set(update_data, merge=True)
        log.info(f"  {ds} → bw_performance={bw_perf}"
                 f"{f', {also_save_as}={bw_perf}' if also_save_as else ''}"
                 f" (mvno_in={total_in:,}, avg={month_avg:.1f})")
        saved += 1
    return saved


# ── 월 평균 MVNO IN 계산
def calc_month_avg_mvno_in(db, year: int, month: int, up_to_day: int) -> float:
    total, days = 0, 0
    for day in range(1, up_to_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d  = datetime.strptime(ds, '%Y-%m-%d')
        if is_zero_day(d):
            continue
        doc = db.collection('ktoa_daily').document(ds).get()
        if not doc.exists:
            continue
        data    = doc.to_dict()
        mvno_in = data.get('mvno_in', {})
        val     = mvno_in.get('계', 0) if isinstance(mvno_in, dict) else 0
        if val > 0:
            total += val
            days  += 1
    return round(total / days, 1) if days > 0 else 0.0


# ── 미래일 bw_ai 재예측 저장
def recalc_and_save_bw_ai(db, year: int, month: int,
                           day_from: int, day_to: int,
                           field_name: str) -> int:
    """
    day_from ~ day_to 범위: calc_bw_ai() 재예측 → field_name에 저장
    K-NN이 이미 쌓인 실적을 자동 반영하므로 정확도 향상
    """
    try:
        from bw_engine import calc_bw_ai
    except ImportError:
        log.error("bw_engine.py import 실패")
        return 0

    saved = 0
    last_day = monthrange(year, month)[1]
    day_to   = min(day_to, last_day)

    for day in range(day_from, day_to + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        d  = datetime.strptime(ds, '%Y-%m-%d')
        if is_zero_day(d):
            continue

        bw_val = calc_bw_ai(ds)
        db.collection('ktoa_daily').document(ds).set(
            {field_name: bw_val,
             'date': ds,
             f'{field_name}_updated_at': datetime.now()},
            merge=True
        )
        log.info(f"  {ds} → {field_name}={bw_val} (재예측)")
        saved += 1

    return saved


# ── 주차 보정 메인
def run_week_update(year: int, month: int, week: int) -> dict:
    """
    week 주차 종료 후 전체 월 재처리
    - 경과일(1 ~ week*7일): bw_performance 역산
    - 미래일(week*7+1 ~ 말일): calc_bw_ai() 재예측
    """
    db       = get_db()
    field    = f'bw_ai_w{week}'
    last_day = monthrange(year, month)[1]
    past_end = min(week * 7, last_day)   # 경과일 끝
    future_start = past_end + 1          # 미래일 시작

    log.info(f"=== {year}-{month:02d} {week}주차 보정 시작 ===")
    log.info(f"  경과일 역산: 1~{past_end}일 → bw_performance")
    log.info(f"  미래일 재예측: {future_start}~{last_day}일 → {field}")

    # 월 평균 계산 (경과일 기준)
    month_avg = calc_month_avg_mvno_in(db, year, month, past_end)
    log.info(f"  월평균 MVNO IN ({past_end}일까지): {month_avg:,.1f}")

    # 1. 경과일: bw_performance 역산 + bw_ai_w{N}에도 저장
    perf_saved = 0
    if month_avg > 0:
        perf_saved = calc_and_save_bw_performance(
            db, year, month, 1, past_end, month_avg,
            also_save_as=field)   # ★ bw_ai_w{N}에도 동일값 저장
    else:
        log.warning("  월평균 계산 실패 → bw_performance 스킵")

    # 2. 미래일: 재예측
    ai_saved = 0
    if future_start <= last_day:
        ai_saved = recalc_and_save_bw_ai(
            db, year, month, future_start, last_day, field)

    log.info(f"=== {week}주차 완료: "
             f"bw_performance {perf_saved}건, {field} {ai_saved}건 ===")
    return {'perf': perf_saved, 'ai': ai_saved}


# ── 월초(w0) 사전 계산
def run_w0_precalc(year: int, month: int) -> int:
    """
    월 시작 전 전체 월 bw_ai_w0 사전 계산
    매월 말일 21:00에 다음달 실행
    """
    db = get_db()
    log.info(f"=== {year}-{month:02d} w0 사전 계산 시작 ===")
    saved = recalc_and_save_bw_ai(
        db, year, month, 1, monthrange(year, month)[1], 'bw_ai_w0')
    log.info(f"=== w0 완료: {saved}건 ===")
    return saved


# ── 엔트리포인트
def main():
    now          = datetime.now()
    year, month  = now.year, now.month
    current_week = get_week_of_month(now)

    # 환경변수로 모드 제어 (Cloud Scheduler에서 설정)
    mode = os.environ.get('RUN_MODE', 'weekly')  # weekly | w0 | backfill_week

    log.info(f"실행: {now.strftime('%Y-%m-%d %H:%M')} | 모드: {mode}")

    if mode == 'w0':
        # 다음달 w0 사전 계산
        next_month = month % 12 + 1
        next_year  = year + (1 if month == 12 else 0)
        run_w0_precalc(next_year, next_month)

    elif mode == 'backfill_week':
        # [수정 20261007] 이 Job이 이미지에 아예 배포된 적이 없어 생긴 공백을 수동으로
        # 메울 때 쓰는 1회성 모드. TARGET_WEEK(기본 1) 주차를 즉시 보정.
        target_week = int(os.environ.get('TARGET_WEEK', '1'))
        run_week_update(year, month, target_week)

    else:  # weekly
        # 직전 완료 주차들 보정
        weeks_done = list(range(1, current_week))
        if not weeks_done:
            log.info("완료된 주차 없음")
            sys.exit(0)

        log.info(f"보정 대상: {weeks_done}주차")
        total_perf = total_ai = 0
        for w in weeks_done:
            result      = run_week_update(year, month, w)
            total_perf += result['perf']
            total_ai   += result['ai']

        log.info(f"✅ 전체 완료 — "
                 f"bw_performance {total_perf}건, bw_ai_w* {total_ai}건")


if __name__ == '__main__':
    main()