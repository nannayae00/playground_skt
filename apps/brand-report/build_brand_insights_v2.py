"""
build_brand_insights_v2.py  v1.3
작성일: 2026-08-07

[수정 이력]
v1.3 (2026-08-18): v1.2에서 significant_low 추가할 때 compute_records()의
  "실적 데이터 없음(active 비어있음)" 조기 리턴 분기를 6개 값으로 안 고치고
  5개인 채로 남겨둬서 ValueError(not enough values to unpack)로 죽던 버그
  수정. 실적이 아예 없는 (사업자,망) 조합을 만나면 무조건 터지는 상태였음 -
  실행 검증 시 조기발견 못 하고 실제 10년치 돌릴 때 걸림(제 실수, 죄송).
v1.2 (2026-08-17): significant_low(100건 이상인 달 중 최저치) 필드 추가 -
  기존 all_time_low(절대 최솟값, 런칭 초기 소량 실적 등 노이즈성 값 포함
  가능)와 별개로, "망 시작 이후 어느 정도 자리잡은 뒤의 진짜 저점"을 보기
  위한 지표(사용자 요청, 2026-08-17: "역대 최저도 100개 이상 기준으로").
  compute_records()가 5개 튜플(high, low, significant_low, yoy, cv,
  seasonality) 반환하도록 시그니처 변경 - 호출부(build() 함수)도 함께 수정.
v1.1 (2026-08-07): SKT 전용 흡수율(skt_inflow_ratio_by_year, S-MVNO만)을
  사용자 요청으로 전체 사업자 대상 확장 - 각 사업자(모든 망)마다 연도별로
  "어디서 가장 많이 흡수했는지 top5(inflow)" / "어디로 가장 많이 나갔는지
  top5(outflow)"로 일반화. brand_in.inflows/brand_out.outflows를 raw
  brand명 기준으로 연 단위 집계(월 단위는 쿼리량이 12배라 일단 연 단위만 -
  특정 연도를 더 세밀히 보고 싶으면 그 해만 월별로 별도 조회 권장).
  ⚠️ 이 스크립트를 돌리기 전에 ktoa_mvno_monthly_summary가 분석하려는
  전체 기간(예: 2016~2026)에 대해 채워져 있어야 함 - 2016~2023년 원본
  일별 데이터(brand_in/out) 백필이 끝났어도 월간 요약 집계 자체는 별도
  실행이 필요함(ktoa_mvno_period_aggregator.py backfill-monthly로).
v1.0 (2026-08-07): 최초 작성. build_brand_insights.py(v1 - 급성장/급감소/
  휴면/재개만 감지)를 10년 데이터 기준으로 대폭 확장. 한 번 실행으로 아래
  전부를 `ktoa_mvno_brand_insights` 문서에 채움(merge=True, v1이 만든
  networks/events/profile 필드는 그대로 유지하고 추가 필드만 덧붙임):

  [기존 유지]
  - events: 급성장(전월대비2배+)/급감소(전월대비50%-)/휴면(2개월+연속0)/재개

  [신규 - 일반]
  - all_time_high / all_time_low: 망별 역대 최고·최저 실적 월
  - yoy_growth: 연도별 합계 + 전년대비 성장률
  - volatility_cv: 월별 실적의 변동계수(표준편차/평균) - 낮을수록 안정형
  - ramp_speed_months: 최초실적월부터 그 망 top10 최초진입까지 걸린 개월수
  - seasonality: 캘린더월(1~12)별 평균 실적, 평균 대비 1.5배 넘는 성수기 월 표시
  - network_share_trend: 2망 이상 겸용 사업자의 연도별 망별 비중 변화(첫해→최근해)
  - discontinued_check: profile_notes의 종료/매각 시점과 실제 데이터 마지막
    활동월이 얼마나 가까운지 자동 대조(있는 경우만)
  - market_event_tags: events 중 ktoa_mvno_market_events 기간과 겹치는 것에
    "시장전체이벤트 가능성" 태그 부착

  [신규 - 유입/유출 분석 (전체 사업자 대상, v1.1에서 확장)]
  - top5_inflow_sources_by_year: 연도별로 "어디서 가장 많이 흡수했는지" top5
    (브랜드명/건수/비중%). SKT MVNO팀 관점에서는 특히 S-MVNO 사업자들의
    inflow top5 안에 "SKT"(원조 MNO)가 몇 위·몇 %인지가 "이 사업자가 SKT
    이탈고객을 얼마나 흡수해가는지"를 보여주는 핵심 지표가 됨.
  - top5_outflow_destinations_by_year: 연도별로 "어디로 가장 많이 나갔는지"
    top5. 원본 daily 문서(brand_in/out)를 읽어야 해서 이 스크립트에서
    제일 무거운 부분(연도별 date range 쿼리).

실행 환경: Cloud Shell. 전제조건: ktoa_mvno_monthly_summary가 분석 대상
전체 기간(예: 2016-01~2026-07)에 채워져 있어야 함. build_brand_insights.py
(v1)와 import_brand_profiles.py를 먼저 실행해서 기본 문서/프로필이 있으면
더 좋음(discontinued_check가 그 데이터를 참고함).
"""

import logging
import statistics
from datetime import date
from calendar import monthrange

from google.cloud import firestore as fs

from ktoa_mvno_period_aggregator import _get_db
from ktoa_mvno_report import clean_brand_name, is_mno_brand

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GROWTH_RATIO = 2.0
GROWTH_MIN_PREV = 50
DECLINE_RATIO = 0.5
DECLINE_MIN_PREV = 100
DORMANT_MONTHS = 2
SEASONALITY_THRESHOLD = 1.5  # 캘린더월 평균이 전체평균의 이 배수를 넘으면 성수기로 표시


# ── 1) 월간 요약 전체를 (clean_name, network) 별 시계열로 정리 ──────

def fetch_all_monthly(db):
    docs = db.collection("ktoa_mvno_monthly_summary").stream()
    series = {}       # (clean_name, network) -> {period: {"sum_in":, "avg_in":, "avg_out":}}
    brand_meta = {}    # (clean_name, network) -> {"brand_codes": set()}

    for doc in docs:
        d = doc.to_dict()
        brand = d.get("brand")
        network = d.get("network")
        if not brand or not network or is_mno_brand(brand):
            continue
        clean_name = clean_brand_name(brand)
        key = (clean_name, network)
        period = f"{d['year']:04d}-{d['month']:02d}"

        slot = series.setdefault(key, {})
        prev = slot.get(period, {"sum_in": 0, "avg_in": 0.0, "avg_out": 0.0})
        slot[period] = {
            "sum_in": prev["sum_in"] + (d.get("sum_in") or 0),
            "avg_in": prev["avg_in"] + (d.get("avg_in") or 0.0),
            "avg_out": prev["avg_out"] + (d.get("avg_out") or 0.0),
        }
        brand_meta.setdefault(key, {"brand_codes": set()})["brand_codes"].add(brand)

    series_sorted = {key: sorted(m.items(), key=lambda kv: kv[0]) for key, m in series.items()}
    return series_sorted, brand_meta


# ── 2) 급성장/급감소/휴면/재개 이벤트 (v1과 동일 로직) ──────────────

def extract_events(period_series):
    events = []
    dormant_start = None
    prev_active_period = None
    prev_sum = None

    for i, (period, vals) in enumerate(period_series):
        sum_in = vals["sum_in"]
        if prev_sum is not None and prev_sum > 0:
            if sum_in >= prev_sum * GROWTH_RATIO and prev_sum >= GROWTH_MIN_PREV:
                events.append({"period": period, "type": "급성장",
                                "detail": f"전월대비 {(sum_in / prev_sum - 1) * 100:.0f}% ({prev_sum:,}건→{sum_in:,}건)"})
            elif sum_in <= prev_sum * DECLINE_RATIO and prev_sum >= DECLINE_MIN_PREV:
                events.append({"period": period, "type": "급감소",
                                "detail": f"전월대비 {(sum_in / prev_sum - 1) * 100:.0f}% ({prev_sum:,}건→{sum_in:,}건)"})

        if sum_in <= 0:
            if dormant_start is None and prev_active_period is not None:
                dormant_start = period
        else:
            if dormant_start is not None:
                start_idx = [p for p, _ in period_series].index(dormant_start)
                dormant_len = i - start_idx
                if dormant_len >= DORMANT_MONTHS:
                    end_period = period_series[i - 1][0]
                    events.append({"period": f"{dormant_start}~{end_period}", "type": "휴면 추정",
                                    "detail": f"{dormant_len}개월 연속 실적 0"})
                    events.append({"period": period, "type": "재개", "detail": f"{sum_in:,}건으로 재개"})
                dormant_start = None
            prev_active_period = period
        prev_sum = sum_in

    return events


# ── 3) 역대 최고/최저, YoY, 변동성, 계절성 ──────────────────────────

def compute_records(period_series):
    active = [(p, v["sum_in"]) for p, v in period_series if v["sum_in"] > 0]
    if not active:
        return None, None, None, {}, None, {}

    high = max(active, key=lambda x: x[1])
    low = min(active, key=lambda x: x[1])

    # 100건 이상인 달 중 최저 - 런칭 첫 달처럼 극단적으로 작은 값(노이즈성)을
    # 제외한 "의미있는 최저치". 사용자 요청(2026-08-17): "역대 최저도
    # (망 시작했을때 이후, 100개 이상)" - 100건 미만인 달을 걸러내면
    # 자연스럽게 런칭 직후 워밍업 구간도 대부분 같이 걸러짐.
    SIGNIFICANT_LOW_THRESHOLD = 100
    significant_active = [(p, v) for p, v in active if v >= SIGNIFICANT_LOW_THRESHOLD]
    significant_low = min(significant_active, key=lambda x: x[1]) if significant_active else None

    # 연도별 합계 + YoY
    by_year = {}
    for p, v in period_series:
        y = p[:4]
        by_year[y] = by_year.get(y, 0) + v["sum_in"]
    years_sorted = sorted(by_year.keys())
    yoy = {}
    for i, y in enumerate(years_sorted):
        if i == 0:
            yoy[y] = {"sum": by_year[y], "yoy_pct": None}
        else:
            prev_y = years_sorted[i - 1]
            prev_val = by_year[prev_y]
            pct = ((by_year[y] / prev_val) - 1) * 100 if prev_val > 0 else None
            yoy[y] = {"sum": by_year[y], "yoy_pct": round(pct, 1) if pct is not None else None}

    # 변동계수(CV) - 활동한 달만 기준
    values = [v for _, v in active]
    cv = None
    if len(values) >= 2 and statistics.mean(values) > 0:
        cv = round(statistics.stdev(values) / statistics.mean(values), 2)

    # 계절성 - 캘린더월별 평균
    month_totals = {}
    for p, val in active:
        m = p[5:7]
        month_totals.setdefault(m, []).append(val)
    month_avg = {m: sum(vs) / len(vs) for m, vs in month_totals.items()}
    overall_avg = sum(month_avg.values()) / len(month_avg) if month_avg else 0
    peak_months = [m for m, avg in month_avg.items() if overall_avg > 0 and avg >= overall_avg * SEASONALITY_THRESHOLD]

    return (
        {"period": high[0], "value": high[1]},
        {"period": low[0], "value": low[1]},
        {"period": significant_low[0], "value": significant_low[1]} if significant_low else None,
        yoy,
        cv,
        {"peak_months": sorted(peak_months), "month_avg": {k: round(v, 1) for k, v in month_avg.items()}},
    )


# ── 4) 신규진입 후 top10 도달 속도 ──────────────────────────────────

def compute_ramp_speed(clean_name, network, period_series, monthly_rank_cache, db):
    first_active = next((p for p, v in period_series if v["sum_in"] > 0), None)
    if not first_active:
        return None

    key = f"{network}:{first_active}"
    if key not in monthly_rank_cache:
        y, m = int(first_active[:4]), int(first_active[5:7])
        docs = db.collection("ktoa_mvno_monthly_summary") \
            .where("year", "==", y).where("month", "==", m).where("network", "==", network).stream()
        ranked = sorted(
            [(clean_brand_name(d.to_dict().get("brand", "")), d.to_dict().get("sum_in", 0)) for d in docs],
            key=lambda x: -x[1],
        )
        monthly_rank_cache[key] = {name: i + 1 for i, (name, _) in enumerate(ranked)}

    for i, (period, vals) in enumerate(period_series):
        if vals["sum_in"] <= 0:
            continue
        cache_key = f"{network}:{period}"
        if cache_key not in monthly_rank_cache:
            y, m = int(period[:4]), int(period[5:7])
            docs = db.collection("ktoa_mvno_monthly_summary") \
                .where("year", "==", y).where("month", "==", m).where("network", "==", network).stream()
            ranked = sorted(
                [(clean_brand_name(d.to_dict().get("brand", "")), d.to_dict().get("sum_in", 0)) for d in docs],
                key=lambda x: -x[1],
            )
            monthly_rank_cache[cache_key] = {name: j + 1 for j, (name, _) in enumerate(ranked)}

        rank = monthly_rank_cache[cache_key].get(clean_name)
        if rank and rank <= 10:
            fy, fm = int(first_active[:4]), int(first_active[5:7])
            py, pm = int(period[:4]), int(period[5:7])
            months = (py - fy) * 12 + (pm - fm)
            return {"first_active_month": first_active, "top10_reached_month": period, "months_taken": months}

    return None


# ── 5) 유입/유출 top5 분석 (전체 망 대상, 연도별) ───────────────────

def compute_flow_analysis(db, start_year=2016):
    """
    모든 사업자(brand_code)에 대해 연도별로 (a) 어디서 가장 많이 흡수했는지
    top5, (b) 어디로 가장 많이 빠져나갔는지 top5를 계산.
    brand_in.inflows(유입출처별 건수)/brand_out.outflows(유출목적지별 건수)를
    연 단위 date range 쿼리로 통째로 읽어서 합산 - S-MVNO 한정이 아니라
    전체 사업자 대상(사용자 요청, 2026-08-07 - 원래 SKT 흡수율만 보려던 것을
    "어디서 오고 어디로 가는지" 전체로 확장).
    """
    inflow_result = {}   # brand_code -> {year: {from_brand: count}}
    outflow_result = {}  # brand_code -> {year: {to_brand: count}}
    current_year = date.today().year

    for year in range(start_year, current_year + 1):
        start, end = f"{year}-01-01", f"{year}-12-31"

        try:
            in_docs = db.collection("ktoa_mvno_brand_in") \
                .where("date", ">=", start).where("date", "<=", end).stream()
        except Exception as e:
            log.warning(f"{year}년 brand_in 유입분석 쿼리 실패(건너뜀): {e}")
            in_docs = []

        for doc in in_docs:
            d = doc.to_dict()
            brand = d.get("brand")
            if not brand:
                continue
            slot = inflow_result.setdefault(brand, {}).setdefault(str(year), {})
            for from_brand, cnt in (d.get("inflows") or {}).items():
                slot[from_brand] = slot.get(from_brand, 0) + cnt

        try:
            out_docs = db.collection("ktoa_mvno_brand_out") \
                .where("date", ">=", start).where("date", "<=", end).stream()
        except Exception as e:
            log.warning(f"{year}년 brand_out 유출분석 쿼리 실패(건너뜀): {e}")
            out_docs = []

        for doc in out_docs:
            d = doc.to_dict()
            brand = d.get("brand")
            if not brand:
                continue
            slot = outflow_result.setdefault(brand, {}).setdefault(str(year), {})
            for to_brand, cnt in (d.get("outflows") or {}).items():
                slot[to_brand] = slot.get(to_brand, 0) + cnt

        log.info(f"{year}년 유입/유출 분석 완료")

    return inflow_result, outflow_result


def top5(flow_dict: dict) -> list:
    """{from/to_brand: count} -> [(brand, count, pct), ...] top5, 비중(%) 포함."""
    total = sum(flow_dict.values())
    if total == 0:
        return []
    ranked = sorted(flow_dict.items(), key=lambda kv: -kv[1])[:5]
    return [{"brand": b, "count": c, "pct": round(c / total * 100, 1)} for b, c in ranked]


# ── 6) 시장 이벤트와 겹치는지 태깅 ──────────────────────────────────

def load_market_events(db):
    events = []
    try:
        for doc in db.collection("ktoa_mvno_market_events").stream():
            d = doc.to_dict()
            period = d.get("period", "")
            start = period.split("~")[0].strip().split(" ")[0]
            events.append({"id": doc.id, "start": start, "detail": d.get("detail", "")[:80]})
    except Exception as e:
        log.warning(f"시장이벤트 로드 실패(건너뜀): {e}")
    return events


def tag_market_events(events, market_events):
    for ev in events:
        ev_period = ev["period"][:7]  # YYYY-MM
        for me in market_events:
            if me["start"][:7] == ev_period:
                ev["market_event_note"] = f"시장전체이벤트({me['id']})와 같은 시기 - 개별사업자 이슈 아닐 수 있음"
                break
    return events


# ── 메인 ────────────────────────────────────────────────────────

def build(db):
    series, brand_meta = fetch_all_monthly(db)
    market_events = load_market_events(db)
    log.info(f"분석 대상: {len(series)}개 (사업자,망) 조합, 시장이벤트 {len(market_events)}건")

    by_brand = {}
    monthly_rank_cache = {}

    for (clean_name, network), period_series in series.items():
        events = extract_events(period_series)
        events = tag_market_events(events, market_events)
        for ev in events:
            ev["network"] = network

        high, low, significant_low, yoy, cv, seasonality = compute_records(period_series)
        ramp = compute_ramp_speed(clean_name, network, period_series, monthly_rank_cache, db)
        first_active = next((p for p, v in period_series if v["sum_in"] > 0), None)

        by_brand.setdefault(clean_name, {"networks": {}, "events": []})
        by_brand[clean_name]["networks"][network] = {
            "brand_codes": sorted(brand_meta[(clean_name, network)]["brand_codes"]),
            "first_active_month": first_active,
            "all_time_high": high,
            "all_time_low": low,
            "significant_low": significant_low,
            "yoy_growth": yoy,
            "volatility_cv": cv,
            "seasonality": seasonality,
            "ramp_speed": ramp,
        }
        by_brand[clean_name]["events"].extend(events)

    # 망 비중 추이 (2망 이상 겸용 사업자만)
    for clean_name, data in by_brand.items():
        nets = data["networks"]
        if len(nets) < 2:
            continue
        all_years = set()
        for net_data in nets.values():
            all_years.update(net_data["yoy_growth"].keys())
        years_sorted = sorted(all_years)
        if len(years_sorted) < 2:
            continue
        first_y, last_y = years_sorted[0], years_sorted[-1]

        def share_snapshot(year):
            totals = {n: nets[n]["yoy_growth"].get(year, {}).get("sum", 0) for n in nets}
            grand = sum(totals.values())
            if grand == 0:
                return {}
            return {n: round(v / grand * 100, 1) for n, v in totals.items()}

        data["network_share_trend"] = {
            "first_year": first_y, "first_year_share": share_snapshot(first_y),
            "last_year": last_y, "last_year_share": share_snapshot(last_y),
        }

    # 유입/유출 top5 분석 (전체 사업자 대상, 연도별)
    log.info("유입/유출 분석 시작 (전체 사업자, 연도별 - 시간 좀 걸립니다)")
    inflow_by_brandname, outflow_by_brandname = compute_flow_analysis(db)

    for clean_name, data in by_brand.items():
        for network, net_data in data["networks"].items():
            raw_brands = brand_meta[(clean_name, network)]["brand_codes"]  # 실제로는 원본 brand 문자열 집합

            inflow_by_year = {}
            outflow_by_year = {}
            for raw in raw_brands:
                for year, flow in inflow_by_brandname.get(raw, {}).items():
                    merged = inflow_by_year.setdefault(year, {})
                    for src, cnt in flow.items():
                        merged[src] = merged.get(src, 0) + cnt
                for year, flow in outflow_by_brandname.get(raw, {}).items():
                    merged = outflow_by_year.setdefault(year, {})
                    for dst, cnt in flow.items():
                        merged[dst] = merged.get(dst, 0) + cnt

            net_data["top5_inflow_sources_by_year"] = {y: top5(f) for y, f in inflow_by_year.items()}
            net_data["top5_outflow_destinations_by_year"] = {y: top5(f) for y, f in outflow_by_year.items()}

    # 저장 (기존 문서 있으면 merge - v1/프로필 필드 보존)
    written = 0
    for clean_name, data in by_brand.items():
        data["events"].sort(key=lambda e: e["period"])
        ref = db.collection("ktoa_mvno_brand_insights").document(clean_name)
        ref.set({
            "networks": data["networks"],
            "events": data["events"],
            "network_share_trend": data.get("network_share_trend"),
            "insights_v2_updated_at": fs.SERVER_TIMESTAMP,
        }, merge=True)
        written += 1

    log.info(f"ktoa_mvno_brand_insights v2 저장 완료: {written}개 사업자")
    return written


if __name__ == "__main__":
    db = _get_db()
    n = build(db)
    print(f"완료: {n}개 사업자 종합분석(v2) 저장")