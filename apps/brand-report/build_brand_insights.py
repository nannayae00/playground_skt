"""
build_brand_insights.py  v1.0
작성일: 2026-08-07

[수정 이력]
v1.0 (2026-08-07): 최초 작성. 사업자별 특이사항 DB(`ktoa_mvno_brand_insights`)
  생성 스크립트 - `ktoa_mvno_monthly_summary`(10년치 백필 완료 후) 전체를
  사업자(clean_name) + 망별로 시계열 정렬해서 아래 이벤트를 자동 추출:
    - 최초시작: 그 망에서 처음 IN>0 찍힌 월 (operator_registry의
      first_in_date와 같은 값이지만, 이 컬렉션은 사업자 단위로 S/K/L을
      통합해서 보여주는 게 목적이라 여기 다시 저장)
    - 급성장: 전월 대비 IN 2배 이상 증가 (전월 실적 50건 이상일 때만 -
      작은 숫자에서 나오는 허수 급증 방지)
    - 급감소: 전월 대비 50% 이상 감소 (전월 100건 이상일 때만)
    - 휴면 추정: 실적 있던 사업자가 2개월 이상 연속 IN=0
    - 재개: 휴면 이후 다시 IN>0
  임계값(2배/50%/50건/100건/2개월)은 1차 확정치 - 실제 돌려보고 이벤트가
  너무 많거나 적으면 조정 예정.
  homepage_url 필드는 이 스크립트에서 채우지 않음(별도 조사 필요 - 스크립트
  실행 후 기존 값 있으면 보존, 없으면 null로 초기화).

실행 환경: Cloud Shell에서 실행 (로컬 샌드박스는 Firestore 접근 불가).
전제조건: ktoa_mvno_monthly_summary가 분석하려는 전체 기간(예: 2016-01~
2026-07)에 대해 이미 채워져 있어야 함 - backfill-monthly를 그 범위로
먼저 돌려둘 것.
"""

import logging
from datetime import date

from google.cloud import firestore as fs

from ktoa_mvno_period_aggregator import _get_db
from ktoa_mvno_report import clean_brand_name, is_mno_brand

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GROWTH_RATIO = 2.0        # 전월 대비 이 배수 이상이면 "급성장"
GROWTH_MIN_PREV = 50      # 급성장 판정에 필요한 전월 최소 실적
DECLINE_RATIO = 0.5       # 전월 대비 이 비율 이하로 떨어지면 "급감소"
DECLINE_MIN_PREV = 100    # 급감소 판정에 필요한 전월 최소 실적
DORMANT_MONTHS = 2        # 연속 이 개월 이상 IN=0이면 "휴면 추정"


def _fetch_all_monthly(db) -> dict:
    """
    ktoa_mvno_monthly_summary 전체를 (clean_name, network) -> [(period, sum_in), ...]
    시계열로 정리해서 반환. brand_code -> clean_name/network 매핑도 같이 만듦.
    """
    docs = db.collection("ktoa_mvno_monthly_summary").stream()

    series: dict = {}
    brand_meta: dict = {}  # (clean_name, network) -> {"brand_codes": set()}

    for doc in docs:
        d = doc.to_dict()
        brand = d.get("brand")
        network = d.get("network")
        if not brand or not network or is_mno_brand(brand):
            continue

        clean_name = clean_brand_name(brand)
        key = (clean_name, network)
        period = f"{d['year']:04d}-{d['month']:02d}"
        sum_in = d.get("sum_in") or 0

        series.setdefault(key, {})[period] = series.get(key, {}).get(period, 0) + sum_in
        brand_meta.setdefault(key, {"brand_codes": set()})["brand_codes"].add(brand)

    # dict(period->sum) -> 정렬된 리스트로 변환
    series_sorted = {
        key: sorted(month_map.items(), key=lambda kv: kv[0])
        for key, month_map in series.items()
    }
    return series_sorted, brand_meta


def _extract_events(period_series: list) -> list:
    """
    [(period, sum_in), ...] (기간순 정렬됨)에서 급성장/급감소/휴면/재개 이벤트 추출.
    """
    events = []
    dormant_start = None
    prev_active_period = None
    prev_sum = None

    for i, (period, sum_in) in enumerate(period_series):
        if prev_sum is not None and prev_sum > 0:
            if sum_in >= prev_sum * GROWTH_RATIO and prev_sum >= GROWTH_MIN_PREV:
                events.append({
                    "period": period, "type": "급성장",
                    "detail": f"전월대비 {(sum_in / prev_sum - 1) * 100:.0f}% ({prev_sum:,}건→{sum_in:,}건)",
                })
            elif sum_in <= prev_sum * DECLINE_RATIO and prev_sum >= DECLINE_MIN_PREV:
                events.append({
                    "period": period, "type": "급감소",
                    "detail": f"전월대비 {(sum_in / prev_sum - 1) * 100:.0f}% ({prev_sum:,}건→{sum_in:,}건)",
                })

        if sum_in <= 0:
            if dormant_start is None and prev_active_period is not None:
                dormant_start = period
        else:
            if dormant_start is not None:
                # 휴면 종료 - 몇 개월 연속이었는지 계산
                start_idx = [p for p, _ in period_series].index(dormant_start)
                dormant_len = i - start_idx
                if dormant_len >= DORMANT_MONTHS:
                    end_period = period_series[i - 1][0]
                    events.append({
                        "period": f"{dormant_start}~{end_period}", "type": "휴면 추정",
                        "detail": f"{dormant_len}개월 연속 실적 0",
                    })
                    events.append({"period": period, "type": "재개", "detail": f"{sum_in:,}건으로 재개"})
                dormant_start = None
            prev_active_period = period

        prev_sum = sum_in

    return events


def build(db) -> int:
    series, brand_meta = _fetch_all_monthly(db)
    log.info(f"분석 대상: {len(series)}개 (사업자,망) 조합")

    # clean_name 단위로 취합
    by_brand: dict = {}
    for (clean_name, network), period_series in series.items():
        first_active = next((p for p, v in period_series if v > 0), None)
        events = _extract_events(period_series)
        for ev in events:
            ev["network"] = network

        by_brand.setdefault(clean_name, {"networks": {}, "events": []})
        by_brand[clean_name]["networks"][network] = {
            "brand_codes": sorted(brand_meta[(clean_name, network)]["brand_codes"]),
            "first_active_month": first_active,
        }
        by_brand[clean_name]["events"].extend(events)

    written = 0
    for clean_name, data in by_brand.items():
        data["events"].sort(key=lambda e: e["period"])

        ref = db.collection("ktoa_mvno_brand_insights").document(clean_name)
        existing = ref.get()
        homepage_url = existing.to_dict().get("homepage_url") if existing.exists else None

        payload = {
            "clean_name": clean_name,
            "networks": data["networks"],
            "events": data["events"],
            "homepage_url": homepage_url,
            "updated_at": fs.SERVER_TIMESTAMP,
        }
        ref.set(payload, merge=False)
        written += 1

    log.info(f"ktoa_mvno_brand_insights 저장 완료: {written}개 사업자")
    return written


if __name__ == "__main__":
    db = _get_db()
    n = build(db)
    print(f"완료: {n}개 사업자 특이사항 분석/저장")
