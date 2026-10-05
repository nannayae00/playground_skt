"""
ktoa_mvno_period_aggregator.py  v1.3
작성일: 2026-08-03

[수정 이력]
v1.3 (2026-08-07): aggregate_period()에 "그 달 전체 실측 bw 없음" 판별 로직
  추가 - months_without_bw 계산 후 get_bw_for_date()에 use_formula_fallback
  전달(mvno_period_utils.py v1.2/bw_lite.py v1.1과 연동). 2016~2023 등 과거
  확장 구간 백필용(사용자 확정 공식).
v1.2 (2026-08-07): backfill_weekly()/backfill_monthly()에 구간별 실패
  허용 로직 추가. 실사용 백필 중 Firestore 503(ping timeout) 순간 끊김이
  google-cloud-firestore 라이브러리 자체의 재시도 버그(_retry 속성 없음)와
  겹쳐 전체 백필이 중단되는 문제 발견. 이제 한 구간(주/월) 실패 시 3초
  대기 후 1회 재시도, 그래도 실패하면 그 구간만 건너뛰고 나머지는 계속
  진행하도록 변경 - 끝나고 실패 구간 목록을 로그로 남김(있으면 그 구간만
  나중에 다시 실행).
v1.1 (2026-08-07): import 대상을 bw_engine.py 대신 경량판 bw_lite.py로 변경
  (brand-report/ 배포에 bw_engine.py가 없어서 발생한 ModuleNotFoundError 대응 -
  이유는 bw_lite.py 파일 헤더 참고. bw_engine.py 전체를 중복 배치하지 않기로 함).
v1.0 (2026-08-03): 최초 작성. 설계문서(주간월간_리포트_설계_20260803.md)
  4/5번 그대로 구현.
  - aggregate_period(): 지정 기간(start~end)의 ktoa_mvno_brand_in/out을
    사업자별로 합산 + bw_performance 기반 가중평균 계산 (sum(값)/sum(bw) 방식)
  - save_weekly_summary()/save_monthly_summary(): 이미 계산된 agg를 받아
    ktoa_mvno_weekly_summary/ktoa_mvno_monthly_summary에 저장(문서 스키마는
    설계문서 4번 그대로). aggregate_period()를 먼저 호출해서 만든 agg를
    넘기는 구조 - 리포트 빌드(ktoa_mvno_period_report.py)와 집계를 한 번만
    수행하고 재사용하기 위함(중복 조회 방지).
  - backfill_weekly()/backfill_monthly(): 특정 기간을 지정해서 반복
    실행할 수 있는 구조(ktoa_mvno_scraper.py의 TARGET_YM 패턴과 동일한
    설계 의도) - 기존 백필 데이터(2024-12~2026-07) 소급 집계용.

실행 환경: 로컬(이 환경)에서는 Firestore 접근 불가(egress 미허용).
  Cloud Shell에 복사해서 실행할 것 (ktoa_mvno_report.py와 동일).

사용법:
    # 특정 주 하나만 집계 (월요일 날짜 기준)
    python3 ktoa_mvno_period_aggregator.py weekly 2026-07-27

    # 특정 월 하나만 집계
    python3 ktoa_mvno_period_aggregator.py monthly 2026 7

    # 과거 구간 소급 백필 (여러 주/월을 한 번에)
    python3 ktoa_mvno_period_aggregator.py backfill-weekly 2024-12-01 2026-07-31
    python3 ktoa_mvno_period_aggregator.py backfill-monthly 2024 12 2026 7
"""

import logging
import time
from datetime import date, timedelta
from calendar import monthrange

from google.cloud import firestore

from bw_lite import is_zero_day
from mvno_period_utils import week_of_month, weighted_avg, get_bw_for_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
NETWORK_DB_TO_LABEL = {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}
# ktoa_mvno_report.py의 MNO_BRAND_NAMES와 동일(원조 3사 자체 데이터 제외용)
MNO_BRAND_NAMES = {"SKT", "KT", "LGU", "LGU+", "LG", "LG U+", "KTF", "LGT"}


def _get_db():
    return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)


def _date_range(start: date, end: date) -> list:
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _fetch_daily_docs(db, dates: list) -> dict:
    """ktoa_daily/{date} 문서를 날짜별로 미리 조회 (bw 조회용, N+1 방지)."""
    result = {}
    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        doc = db.collection("ktoa_daily").document(ds).get()
        result[ds] = doc.to_dict() if doc.exists else {}
    return result


def _fetch_brand_docs_for_date(db, collection: str, d: date) -> dict:
    date_str = d.strftime("%Y-%m-%d")
    docs = db.collection(collection).where("date", "==", date_str).stream()
    return {doc_data.get("brand"): doc_data for doc_data in (doc.to_dict() for doc in docs)}


def aggregate_period(db, start: date, end: date) -> dict:
    """
    기간(start~end) 내 brand_in/out을 사업자별로 합산 + bw 가중평균 계산.
    반환: {
        "brands": {brand: {"network", "sum_in", "sum_out", "avg_in", "avg_out"}},
        "business_days": int,   # 영업 0일(일요일/설추석 당일) 제외한 실제 데이터 있는 날 수
        "bw_sum": float,        # 가중평균 분모
    }
    brand_out 문서에는 network 필드가 없으므로(기존 일일 리포트에서 확인된
    이슈) brand_in에서 채워진 매핑을 그대로 재사용 - 기간 내 하루라도 IN이
    있었던 사업자면 network를 알 수 있음. 기간 내 OUT만 있고 IN이 전혀
    없던 사업자는 network를 "UNKNOWN"으로 남김(드문 엣지케이스).
    """
    dates = _date_range(start, end)
    daily_docs = _fetch_daily_docs(db, dates)

    # 그 달(YYYY-MM) 전체에 실측 bw 필드가 하나도 없는지 미리 판별 -
    # 있으면(최근 달처럼 대부분 있고 공휴일 하루 정도만 빠진 경우) 기존처럼
    # 그 날만 제외, 전혀 없으면(2016~2023 등 과거 확장 구간) estimate_bw_formula()
    # 사용(bw_lite.py v1.1, 사용자 확정: "bw없는 달만 이 로직을 사용").
    REAL_BW_FIELDS = ["bw_performance", "bw_ai_prev", "bw_manual", "bw_ai_w3", "bw_ai_w2", "bw_ai_w1"]
    months_seen: dict[str, bool] = {}
    for d in dates:
        ym = d.strftime("%Y-%m")
        doc = daily_docs.get(d.strftime("%Y-%m-%d")) or {}
        has_real = any(doc.get(f) not in (None, 0, 0.0) for f in REAL_BW_FIELDS)
        months_seen[ym] = months_seen.get(ym, False) or has_real
    months_without_bw = {ym for ym, has_real in months_seen.items() if not has_real}

    brand_sum_in: dict = {}
    brand_sum_out: dict = {}
    brand_network: dict = {}
    bw_sum = 0.0

    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        use_formula = d.strftime("%Y-%m") in months_without_bw
        bw = get_bw_for_date(ds, daily_docs.get(ds), use_formula_fallback=use_formula)
        if bw <= 0:
            continue  # 영업 0일(일요일/설·추석 당일)은 가중치 0 - 집계 자체에서 제외
        bw_sum += bw

        in_docs = _fetch_brand_docs_for_date(db, "ktoa_mvno_brand_in", d)
        out_docs = _fetch_brand_docs_for_date(db, "ktoa_mvno_brand_out", d)

        for brand, doc in in_docs.items():
            if brand in MNO_BRAND_NAMES:
                continue
            network = NETWORK_DB_TO_LABEL.get(doc.get("network"))
            if network is None:
                continue
            brand_network[brand] = network
            brand_sum_in[brand] = brand_sum_in.get(brand, 0) + (doc.get("total_in") or 0)

        for brand, doc in out_docs.items():
            if brand in MNO_BRAND_NAMES:
                continue
            brand_sum_out[brand] = brand_sum_out.get(brand, 0) + (doc.get("total_out") or 0)

    business_days = sum(1 for d in dates if not is_zero_day(d.strftime("%Y-%m-%d")))

    all_brands = set(brand_sum_in) | set(brand_sum_out)
    brands = {}
    for brand in all_brands:
        network = brand_network.get(brand, "UNKNOWN")
        sum_in = brand_sum_in.get(brand, 0)
        sum_out = brand_sum_out.get(brand, 0)
        brands[brand] = {
            "network": network,
            "sum_in": sum_in,
            "sum_out": sum_out,
            "avg_in": weighted_avg(sum_in, bw_sum),
            "avg_out": weighted_avg(sum_out, bw_sum),
        }

    return {"brands": brands, "business_days": business_days, "bw_sum": round(bw_sum, 3)}


def _write_batch(db, collection: str, doc_id_fn, base_payload: dict, agg: dict) -> int:
    batch = db.batch()
    count = 0
    written = 0

    for brand, data in agg["brands"].items():
        doc_id = doc_id_fn(brand)
        ref = db.collection(collection).document(doc_id)
        payload = dict(base_payload)
        payload.update({
            "brand": brand,
            "network": data["network"],
            "sum_in": data["sum_in"],
            "sum_out": data["sum_out"],
            "avg_in": data["avg_in"],
            "avg_out": data["avg_out"],
            "collected_at": firestore.SERVER_TIMESTAMP,
        })
        batch.set(ref, payload, merge=True)
        count += 1
        written += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    return written


def save_weekly_summary(db, agg: dict, year: int, month: int, week: int,
                         period_start: date, period_end: date) -> int:
    """ktoa_mvno_weekly_summary/{year}-{month}W{week}_{brand} 문서로 저장."""
    base = {
        "year": year, "month": month, "week": week,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "business_days": agg["business_days"],
    }
    written = _write_batch(
        db, "ktoa_mvno_weekly_summary",
        lambda brand: f"{year}-{month:02d}W{week}_{brand}",
        base, agg,
    )
    log.info(f"ktoa_mvno_weekly_summary 저장 완료: {year}-{month:02d}W{week} ({written}개 사업자)")
    return written


def save_monthly_summary(db, agg: dict, year: int, month: int,
                          period_start: date, period_end: date) -> int:
    """ktoa_mvno_monthly_summary/{year}-{month}_{brand} 문서로 저장."""
    base = {
        "year": year, "month": month,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "business_days": agg["business_days"],
    }
    written = _write_batch(
        db, "ktoa_mvno_monthly_summary",
        lambda brand: f"{year}-{month:02d}_{brand}",
        base, agg,
    )
    log.info(f"ktoa_mvno_monthly_summary 저장 완료: {year}-{month:02d} ({written}개 사업자)")
    return written


# ============================================================
# 백필 (과거 구간 소급 집계)
# ============================================================

def backfill_weekly(start_date: date, end_date: date) -> int:
    """
    start~end 범위에 걸치는 모든 주(월~토)에 대해 순차적으로 집계+저장.
    한 구간에서 예외(네트워크 순간 끊김 등)가 나도 전체를 중단하지 않고,
    1회 재시도 후에도 실패하면 그 구간만 건너뛰고 계속 진행함(실측 중
    503 ping timeout으로 전체가 죽는 문제 발견 - 2026-08-07).
    """
    db = _get_db()
    saved = 0
    failed = []
    cur = start_date - timedelta(days=start_date.weekday())  # 그 주의 월요일로 정렬
    seen = set()
    while cur <= end_date:
        year, month, week, mon, sat = week_of_month(cur)
        key = (year, month, week)
        if key not in seen:
            label = f"{year}-{month:02d}W{week}"
            for attempt in range(2):
                try:
                    agg = aggregate_period(db, mon, sat)
                    save_weekly_summary(db, agg, year, month, week, mon, sat)
                    saved += 1
                    break
                except Exception as e:
                    if attempt == 0:
                        log.warning(f"{label} 집계 실패, 3초 후 재시도: {e}")
                        time.sleep(3)
                    else:
                        log.warning(f"{label} 집계 최종 실패(건너뜀 - 나중에 이 구간만 다시 실행 필요): {e}")
                        failed.append(label)
            seen.add(key)
        cur += timedelta(days=7)
    if failed:
        log.warning(f"backfill_weekly 실패 구간 {len(failed)}건: {failed}")
    log.info(f"backfill_weekly 완료: {start_date}~{end_date}, 성공 {saved}건, 실패 {len(failed)}건")
    return saved


def backfill_monthly(start_year: int, start_month: int, end_year: int, end_month: int) -> int:
    """
    start_year-start_month ~ end_year-end_month까지 월별 순차 집계+저장.
    backfill_weekly와 동일하게 구간별 1회 재시도 후 실패 시 건너뛰는 방식 적용.
    """
    db = _get_db()
    saved = 0
    failed = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        period_start = date(y, m, 1)
        last_day = monthrange(y, m)[1]
        period_end = date(y, m, last_day)
        label = f"{y}-{m:02d}"
        for attempt in range(2):
            try:
                agg = aggregate_period(db, period_start, period_end)
                save_monthly_summary(db, agg, y, m, period_start, period_end)
                saved += 1
                break
            except Exception as e:
                if attempt == 0:
                    log.warning(f"{label} 집계 실패, 3초 후 재시도: {e}")
                    time.sleep(3)
                else:
                    log.warning(f"{label} 집계 최종 실패(건너뜀 - 나중에 이 구간만 다시 실행 필요): {e}")
                    failed.append(label)
        m += 1
        if m > 12:
            m = 1
            y += 1
    if failed:
        log.warning(f"backfill_monthly 실패 구간 {len(failed)}건: {failed}")
    log.info(f"backfill_monthly 완료: 성공 {saved}건, 실패 {len(failed)}건")
    return saved


# ============================================================
# CLI 실행
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법:")
        print("  python ktoa_mvno_period_aggregator.py weekly 2026-07-27")
        print("  python ktoa_mvno_period_aggregator.py monthly 2026 7")
        print("  python ktoa_mvno_period_aggregator.py backfill-weekly 2024-12-01 2026-07-31")
        print("  python ktoa_mvno_period_aggregator.py backfill-monthly 2024 12 2026 7")
        sys.exit(0)

    cmd = sys.argv[1]
    db = _get_db()

    if cmd == "weekly":
        any_day = date.fromisoformat(sys.argv[2])
        year, month, week, mon, sat = week_of_month(any_day)
        agg = aggregate_period(db, mon, sat)
        n = save_weekly_summary(db, agg, year, month, week, mon, sat)
        print(f"주간 집계 완료: {year}-{month:02d}W{week} ({mon}~{sat}), {n}개 사업자")

    elif cmd == "monthly":
        year, month = int(sys.argv[2]), int(sys.argv[3])
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
        agg = aggregate_period(db, period_start, period_end)
        n = save_monthly_summary(db, agg, year, month, period_start, period_end)
        print(f"월간 집계 완료: {year}-{month:02d}, {n}개 사업자")

    elif cmd == "backfill-weekly":
        n = backfill_weekly(date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]))
        print(f"주간 백필 완료: {n}건")

    elif cmd == "backfill-monthly":
        n = backfill_monthly(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
        print(f"월간 백필 완료: {n}건")

    else:
        print(f"알 수 없는 명령: {cmd}")
