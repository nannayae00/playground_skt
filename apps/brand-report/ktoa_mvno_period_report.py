"""
ktoa_mvno_period_report.py  v1.10
작성일: 2026-08-03

[수정 이력]
v1.10 (2026-09-20, Claude): build_ms_message() FIXED_BRAND_NETWORK_ALIASES
  누락 버그 수정. daily(ktoa_mvno_report.py build_message3)는 "프리텔레콤"의
  L-MVNO(LGU+) 원본 데이터가 "프리티"라는 다른 이름으로 저장되는 걸
  alias_lookup으로 합쳐서 인식하는데, 여기(주간/월간)엔 그 로직이 없어서
  "프리텔레콤"(S/K)과 "프리티"(L)가 서로 다른 브랜드로 취급되어 둘 다 3망 중
  1~2개만 있는 걸로 보여 M/S 리포트에서 통째로 빠지던 문제 (실사용 확인:
  일별 M/S엔 "프리텔"이 나오는데 같은 기간 포함 주간 M/S엔 안 나옴).
  ktoa_mvno_report에서 FIXED_BRAND_NETWORK_ALIASES import 추가, daily와
  동일한 alias_lookup 적용.
v1.9 (2026-08-27): weekly context 문서에 iso_year_week("2026-W34" 형식) 필드
  추가(사용자 요청 - 사내 다른 대시보드가 ISO 주차로 표기하는 것과 맞추기
  위함). save_period_context()에 extra_fields 파라미터 신설, monthly에는
  year/month도 같이 추가. 기존 "월N주차"(월 1일마다 1주차로 리셋되는 사내
  자체 체계) 필드는 그대로 유지 - ISO 주차와는 다른 체계라 병기.
v1.8 (2026-08-27): Context DB 연동(사용자 확정, 최종 설계 - daily와 동일하게
  기존 ktoa_context 패턴으로 단순화: 문서 1개=기간 1개, text 필드에 메시지
  원문을 구분선으로 이어붙여 그대로 저장). save_period_context() 신규 추가,
  build_weekly_report()/build_monthly_report()에서 메시지 3개 생성 직후
  호출해서 ktoa_brand_context_weekly/monthly에 저장. 영업일수(bw_sum/
  business_days)는 Context DB에 저장하지 않기로 함(사용자 확정).
v1.7 (2026-08-26): 메시지2를 일일 리포트(ktoa_mvno_report.py v3.16~v3.19)와
  동일한 구조로 재구성(사용자 요청) - 통신3사 자회사(SK텔링크/KT엠모바일/
  KT스카이라이프/LG헬로비전/미디어로그)를 망 구분 없이 맨 위 "◎ 자회사"로
  모으고(순번 없이 신호등만), 그 아래 "◎ {network} 일반"은 자회사 제외
  하고 1부터 연속 번호. 자회사 판별은 "망 단위"로(ktoa_mvno_report의
  SUBSIDIARY_BY_NETWORK import) - 다른 망에서 예전에 소량 운영하다 접은
  동명이인 데이터가 자회사로 잘못 묶이는 것 방지(daily에서 헬로비전으로
  실측 확인된 문제). 같은 표시명으로 원본 브랜드가 쪼개진 경우도 daily와
  동일하게 합산(_merge_period_by_display 신설). "일반" 헤더의 (IN/OUT/
  순증감)은 "메시지1과 동일한 망 전체 합계 - 자회사 raw 브랜드 전체"로
  직접 계산해서 항상 메시지1 총계와 정확히 맞아떨어지게 함(daily v3.18과
  동일 이유). _display_list_for_network()는 더 이상 안 씀(제거).
v1.6 (2026-08-26): 일일 리포트(ktoa_mvno_report.py v3.11~v3.15)와 동일한
  느낌으로 메시지1/2 재구성(사용자 요청).
  - 메시지1(build_summary_message/_rank_and_format): K/L-MVNO 표시 기준을
    기존 "IN≥50 카운트만 표기 + top10 고정 표시"에서 "기간합계 IN≥100인
    사업자 전부 표시"로 변경(PERIOD_IN_FLOOR=100, 일일리포트의
    DAILY_IN_FLOOR=30과 같은 역할이지만 기간 합계라 스케일이 커서
    100으로 별도 설정 - 사용자 확정).
  - 메시지2: build_spike_message() 폐기, build_change_message()로 전면
    교체 - "특이사항만 나열" 방식 대신 메시지1과 동일 대상(S 전체/K,L은
    기간합계 IN≥100)을 실적순으로 다 보여주면서 🟢/🔴/🟡 신호등
    부착(ktoa_mvno_report의 _spike_light/_pct_change 재사용, import 추가).
    baseline도 avg_in(일 평균) 대신 sum_in(기간합계) 평균으로 통일해서
    표시값(실적=sum_in)과 비교기준의 단위를 맞춤. 신호등은 기간합계
    IN≥100인 사업자에만 적용(소액 사업자 % 착시 방지, 일일리포트와
    동일 취지). build_weekly_report/build_monthly_report의 호출부도
    build_change_message로 변경.
  - classify_change/classify_net_change/SPIKE_THRESHOLD/spike_color/
    net_change_color/net_change_ratio_str import 및 관련 함수(구
    build_spike_message)는 더 이상 이 파일에서 안 씀 - import 정리.
v1.5 (2026-08-18): 일일 리포트(ktoa_mvno_report.py v3.2)와 색상 체계 일관성
  맞춤. build_spike_message()의 IN 특이점/순증감 특이점 줄에 ⚡ 대신
  5단계 신호등(spike_color/net_change_color) 적용, 순증감 줄에 배수 문구
  (net_change_ratio_str)도 병기.
v1.4 (2026-08-07): 표시 문구 "가중평균" → "평균"으로 변경.
v1.3 (2026-08-07): build_ms_message() KCT 5분할 버그 수정(합산 방식으로 전환).
v1.2 (2026-08-07): build_ms_message() KeyError('K-MVNO') 버그 수정
  (UNKNOWN network 사업자가 3망으로 오판정되던 문제).
v1.1 (2026-08-03): 메시지2(특이사항⚡) 추가.
v1.0 (2026-08-03): 최초 작성.

실행 환경: 로컬(이 환경)에서는 Firestore 접근 불가. Cloud Shell에서 실행할 것.
"""

import logging
from datetime import date

from google.cloud import firestore as fs

from ktoa_mvno_report import (
    clean_brand_name, shorten_brand_name, is_mno_brand, format_signed,
    _pct_change, _spike_light, SUBSIDIARY_BY_NETWORK, FIXED_BRAND_NETWORK_ALIASES,
)
from save_brand_context import build_full_text, save_context_text

log = logging.getLogger(__name__)

PERIOD_IN_FLOOR = 100  # 메시지1/2 공통 기준(사용자 확정, 2026-08-26) - 기간합계 IN이 이 값 이상인 K/L 사업자만 표시
MS_MIN_SM = 10  # S-MVNO(SM) 기간 합계 IN이 이 값 미만인 사업자는 M/S 리포트에서 제외

# 특이점 판정용 lookback 기간 수 (사용자 확정: 주간=최근4주, 월간=최근3개월)
LOOKBACK_N = {"weekly": 4, "monthly": 3}


# ── 메시지1: 총괄 실적 ──────────────────────────────────────────────

def _rank_and_format(network: str, brands: dict, floor: int) -> list:
    """agg['brands']에서 특정 network만 뽑아 IN 합계 내림차순 랭킹 텍스트 라인 생성.
    S-MVNO는 전체, K/L-MVNO는 기간합계 IN≥floor인 사업자 전부 표시(v1.6)."""
    lines = []
    net_brands = {b: d for b, d in brands.items() if d["network"] == network}
    if not net_brands:
        lines.append(f"\n◎ {network}: 데이터 없음")
        return lines

    ranked = sorted(net_brands.items(), key=lambda kv: kv[1]["sum_in"], reverse=True)
    ranked = [(b, d) for b, d in ranked if d["sum_in"] > 0]

    total_count = len(net_brands)

    network_in_sum = sum(d["sum_in"] for d in net_brands.values())
    network_out_sum = sum(d["sum_out"] for d in net_brands.values())
    network_net_sum = network_in_sum - network_out_sum
    summary = f"{network_in_sum:,}/{network_out_sum:,}/{format_signed(network_net_sum)}"

    if network == "S-MVNO":
        lines.append(f"\n◎ {network} ({summary})")
        display_list = ranked
    else:
        display_list = [(b, d) for b, d in ranked if d["sum_in"] >= floor]
        lines.append(f"\n◎ {network} ({summary})")
        lines.append(f"전체 {total_count}개 중 기간합계 IN≥{floor} {len(display_list)}개 사업자")

    for i, (brand, d) in enumerate(display_list, 1):
        display_name = shorten_brand_name(clean_brand_name(brand))
        net_v = d["sum_in"] - d["sum_out"]
        lines.append(f"{i}) {display_name} : {d['sum_in']:,} / {d['sum_out']:,} / {format_signed(net_v)}")

    return lines


def build_summary_message(agg: dict, title: str, period_start: date, period_end: date) -> str:
    """메시지1 스타일: 기간 합계 IN/OUT/순증감 (S 전체, K/L은 기간합계 IN≥100 전부)."""
    lines = [
        f"📊 {title} ({period_start.isoformat()}~{period_end.isoformat()})",
        f"영업일수(가중): {agg['bw_sum']} / 실데이터일수: {agg['business_days']}",
        "[ IN/OUT/순증감 ]",
    ]
    for network in ["S-MVNO", "K-MVNO", "L-MVNO"]:
        lines.extend(_rank_and_format(network, agg["brands"], PERIOD_IN_FLOOR))
    return "\n".join(lines)


# ── 메시지2: IN 증감 현황 (메시지1과 동일한 자회사 분리 + 신호등) ──────

def _brand_period_history(db, collection: str, brand: str, period_start_str: str, limit: int) -> list:
    """
    해당 사업자의 과거 요약 문서를 period_start 내림차순으로 최근 limit개 조회.
    ⚠️ brand==, period_start< , order_by(period_start) 조합 - Firestore 복합
    인덱스 필요(최초 실행 시 에러 메시지의 링크로 1회 생성).
    """
    docs = (
        db.collection(collection)
        .where("brand", "==", brand)
        .where("period_start", "<", period_start_str)
        .order_by("period_start", direction=fs.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [d.to_dict() for d in docs]


def _avg_of(history: list, field: str):
    values = [h[field] for h in history if h.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _merge_period_by_display(net_brands: dict) -> dict:
    """망 하나의 raw brand -> {sum_in, sum_out} 딕셔너리를 표시명
    (shorten_brand_name(clean_brand_name)) 기준으로 합산. 일일 리포트의
    _merge_network_by_display와 동일한 목적(같은 표시명인데 원본 브랜드가
    여러 개로 쪼개진 경우 - KCT/헬로비전 패턴 - 하나로 합침). 반환:
    {표시명: {"raw_brands": [...], "in": 합계, "out": 합계}}."""
    merged: dict = {}
    for brand, d in net_brands.items():
        name = shorten_brand_name(clean_brand_name(brand))
        slot = merged.setdefault(name, {"raw_brands": [], "in": 0, "out": 0})
        slot["raw_brands"].append(brand)
        slot["in"] += d["sum_in"]
        slot["out"] += d["sum_out"]
    return merged


def build_change_message(db, collection: str, agg: dict, period_start: date, period_end: date,
                          lookback_n: int, title: str, prev_label: str) -> str:
    """
    메시지2 v1.7(사용자 요청, 2026-08-26): 일일 리포트(ktoa_mvno_report.py
    v3.16~v3.19)와 동일하게 통신3사 자회사(SK텔링크/KT엠모바일/KT스카이라이프/
    LG헬로비전/미디어로그)를 망 구분 없이 맨 위 "◎ 자회사"로 모으고(순번
    없이 신호등만), 그 아래 "◎ {network} 일반"은 자회사 제외하고 1부터
    연속 번호. 자회사 판별은 daily와 동일하게 "망 단위"로(SUBSIDIARY_BY_NETWORK
    재사용 - 예전에 다른 망에서 소량 운영하다 접은 동명이인 데이터가 자회사로
    잘못 묶이는 것 방지). 같은 표시명으로 원본 브랜드가 쪼개진 경우
    (_merge_period_by_display)도 daily와 동일하게 합산.
    "◎ {network} 일반" 헤더의 (IN/OUT/순증감)은 "메시지1과 동일한 망 전체
    합계 - 자회사 raw 브랜드 전체"로 직접 계산(daily v3.18과 동일한 이유 -
    산수가 항상 메시지1 총계와 정확히 맞아떨어지게 하기 위함).
    - "최근{lookback_n}기간 평균 대비": 최근 N기간(주간=4주/월간=3개월)의
      기간합계(sum_in) 평균 대비. 표시명이 합쳐진 경우 raw_brands 전체의
      history를 각각 조회해서 합산.
    - "{prev_label}"(전주비/전월비): 직전 1기간 합계 대비.
    - 신호등은 기간합계 IN≥100(PERIOD_IN_FLOOR)인 사업자에만 적용.
    """
    period_start_str = period_start.isoformat()
    lines = [
        f"📊 {title} IN 증감 현황",
        f"[ 실적 / 최근{lookback_n}기간 평균 대비 / {prev_label} ]",
    ]

    per_network = {}
    for network in ["S-MVNO", "K-MVNO", "L-MVNO"]:
        net_brands = {b: d for b, d in agg["brands"].items() if d["network"] == network and not is_mno_brand(b)}
        merged = _merge_period_by_display(net_brands)
        ranked = sorted(merged.items(), key=lambda kv: kv[1]["in"], reverse=True)
        ranked = [(name, info) for name, info in ranked if info["in"] > 0]

        subsidiary_names = SUBSIDIARY_BY_NETWORK.get(network, set())
        general_all = [(name, info) for name, info in ranked if name not in subsidiary_names]
        subsidiary_all = [(name, info) for name, info in ranked if name in subsidiary_names]

        subsidiary_raw_brands = {b for _, info in subsidiary_all for b in info["raw_brands"]}
        network_total_in = sum(d["sum_in"] for d in net_brands.values())
        network_total_out = sum(d["sum_out"] for d in net_brands.values())
        subsidiary_in_sum = sum(net_brands[b]["sum_in"] for b in subsidiary_raw_brands)
        subsidiary_out_sum = sum(net_brands[b]["sum_out"] for b in subsidiary_raw_brands)
        general_in_sum = network_total_in - subsidiary_in_sum
        general_out_sum = network_total_out - subsidiary_out_sum
        summary = f"{general_in_sum:,}/{general_out_sum:,}/{format_signed(general_in_sum - general_out_sum)}"

        general_floor = None if network == "S-MVNO" else PERIOD_IN_FLOOR
        per_network[network] = {
            "general_all": general_all, "subsidiary_all": subsidiary_all,
            "summary": summary, "general_floor": general_floor,
        }

    def _row(raw_brands: list, in_v: int) -> str:
        baseline_sum, has_baseline = 0.0, False
        prev_sum, has_prev = 0.0, False
        for b in raw_brands:
            history = _brand_period_history(db, collection, b, period_start_str, lookback_n)
            avg_b = _avg_of(history, "sum_in")
            if avg_b is not None:
                baseline_sum += avg_b
                has_baseline = True
            if history:
                prev_b = history[0].get("sum_in")
                if prev_b is not None:
                    prev_sum += prev_b
                    has_prev = True

        baseline_pct = _pct_change(in_v, baseline_sum if has_baseline else None)
        baseline_str = f"{format_signed(baseline_pct * 100)}%" if baseline_pct is not None else "-"
        prev_pct = _pct_change(in_v, prev_sum if has_prev else None)
        prev_str = f"{format_signed(prev_pct * 100)}%" if prev_pct is not None else "-"
        color = _spike_light(baseline_pct, prev_pct) if in_v >= PERIOD_IN_FLOOR else ""
        return color, baseline_str, prev_str

    # ── ◎ 자회사(망 구분 없이, 순번 없음) ──
    lines.append("\n◎ 자회사")
    subsidiary_lines = []
    for network in ["S-MVNO", "K-MVNO", "L-MVNO"]:
        for name, info in per_network[network]["subsidiary_all"]:
            in_v = info["in"]
            color, baseline_str, prev_str = _row(info["raw_brands"], in_v)
            subsidiary_lines.append(f"{color}{name} {in_v:,} / {baseline_str} / {prev_str}")
    lines.extend(subsidiary_lines if subsidiary_lines else ["데이터 없음"])

    # ── ◎ {network} 일반(자회사 제외, 1부터 연속 번호) ──
    for network in ["S-MVNO", "K-MVNO", "L-MVNO"]:
        pn = per_network[network]
        general_all, summary, floor = pn["general_all"], pn["summary"], pn["general_floor"]

        display_list = general_all if floor is None else [(n, i) for n, i in general_all if i["in"] >= floor]

        lines.append(f"\n◎ {network} 일반 ({summary})")
        if floor is not None:
            lines.append(f"전체 {len(general_all)}개 중 기간합계 IN≥{floor} {len(display_list)}개 사업자")

        if not display_list:
            lines.append("데이터 없음")
            continue

        for i, (name, info) in enumerate(display_list, 1):
            in_v = info["in"]
            color, baseline_str, prev_str = _row(info["raw_brands"], in_v)
            lines.append(f"{i}) {color}{name} {in_v:,} / {baseline_str} / {prev_str}")

    return "\n".join(lines)


# ── 메시지3: M/S ──────────────────────────────────────────────────

def save_period_context(db, collection: str, period_start: date, period_end: date, messages: list,
                         extra_fields: dict = None) -> None:
    """messages(build_weekly_report/build_monthly_report가 만든 메시지 리스트)를
    구분선으로 이어붙여 text 필드 하나로 저장(v1.8/v1.10). doc_id는 period_start
    문자열 - 재실행해도 같은 기간이면 덮어씀. extra_fields로 year/month/week/
    iso_year_week 같은 조회용 필드를 추가로 얹을 수 있음."""
    text = build_full_text(messages)
    period_start_str = period_start.isoformat()
    fields = {
        "period_start": period_start_str,
        "period_end": period_end.isoformat(),
        "text": text,
    }
    if extra_fields:
        fields.update(extra_fields)
    save_context_text(db, collection, period_start_str, fields)


def build_ms_message(agg: dict, title: str, period_start: date, period_end: date) -> str:
    """메시지3 스타일: S/K/L 3망을 모두 운영하는 사업자의 기간 합계 M/S."""
    lines = [f"📊 {title} 사업자/망별 M/S ({period_start.isoformat()}~{period_end.isoformat()})"]

    REQUIRED_NETWORKS = {"S-MVNO", "K-MVNO", "L-MVNO"}

    # clean_name -> {network: sum_in 합계}
    # 같은 회사가 원본 브랜드명이 여러 개로 쪼개져 있는 경우(예: "KCT(미사용)"와
    # "KCT(재판매)"가 둘 다 S-MVNO인 것처럼 같은 clean_name+같은 network로 겹치는
    # 케이스가 실제로 있음 - 실측 확인됨) 덮어쓰지 않고 합산함. brand_key 하나만
    # 저장해서 나중에 agg["brands"][key]로 되찾는 방식이면 나중 것이 앞의 것을
    # 덮어써서 데이터가 조용히 사라지는 버그가 생김(2026-08-07 실측 중 KCT로 발견).
    # [버그수정, Claude] FIXED_BRAND_NETWORK_ALIASES 누락 - daily(ktoa_mvno_report.py
    # build_message3)는 "프리텔레콤"의 L-MVNO(LGU+) 원본 데이터가 "프리티"라는
    # 다른 이름으로 저장되는 걸 alias_lookup으로 합쳐서 인식하는데, 여기(주간/월간)엔
    # 그 로직이 없어서 "프리텔레콤"(S/K)과 "프리티"(L)가 서로 다른 브랜드로 취급되고
    # 둘 다 3망 중 1~2개만 있는 걸로 보여 M/S 리포트에서 통째로 빠지던 문제.
    alias_lookup = {}
    for canonical, net_aliases in FIXED_BRAND_NETWORK_ALIASES.items():
        for network, alias_name in net_aliases.items():
            alias_lookup[(network, alias_name)] = canonical

    grouped: dict = {}
    for brand, d in agg["brands"].items():
        if is_mno_brand(brand):
            continue
        if d["network"] not in REQUIRED_NETWORKS:
            continue  # network 미상(UNKNOWN, 기간 내 OUT만 있고 IN이 한번도 없던 사업자)은 M/S 대상에서 제외
        clean_name = clean_brand_name(brand)
        canonical_name = alias_lookup.get((d["network"], clean_name), clean_name)
        slot = grouped.setdefault(canonical_name, {})
        slot[d["network"]] = slot.get(d["network"], 0) + d["sum_in"]

    full = {name: nets for name, nets in grouped.items() if set(nets.keys()) == REQUIRED_NETWORKS}

    rows = []
    for name, nets in full.items():
        per_net = {"S": nets["S-MVNO"], "K": nets["K-MVNO"], "L": nets["L-MVNO"]}

        if per_net["S"] < MS_MIN_SM:
            continue

        total = sum(per_net.values())
        rows.append((name, total, per_net))

    rows.sort(key=lambda r: r[1], reverse=True)

    for name, total, per_net in rows:
        lines.append(f"\n◎ {shorten_brand_name(name)} : 총 {total:,}건 (100%)")
        for label in ["S", "K", "L"]:
            v = per_net[label]
            pct = (v / total * 100) if total else 0.0
            lines.append(f"  {label}: {v:,}건 ({pct:.0f}%)")

    if not rows:
        lines.append("\n(조건을 만족하는 사업자 없음)")

    return "\n".join(lines)


# ── 리포트 조립 ───────────────────────────────────────────────────

def build_weekly_report(db, agg: dict, year: int, month: int, week: int,
                         period_start: date, period_end: date) -> list:
    title1 = f"MNP 주간 실적 ({year}년 {month}월 {week}주차)"
    title3 = f"{year}년 {month}월 {week}주차"
    messages = [
        build_summary_message(agg, title1, period_start, period_end),
        build_change_message(db, "ktoa_mvno_weekly_summary", agg, period_start, period_end,
                              LOOKBACK_N["weekly"], title1, "전주비"),
        build_ms_message(agg, title3, period_start, period_end),
    ]
    # period_start는 항상 월요일이라 isocalendar()가 이 주의 ISO 주차를 그대로 줌
    # (사내 다른 대시보드가 쓰는 "2026-W34" 표기와 맞추기 위해 추가, 사용자 요청,
    # 2026-08-27) - 기존 "월N주차"(month-relative, 매월 1일마다 1주차로 리셋)와는
    # 다른 체계라 둘 다 남겨둠.
    iso_year, iso_week, _ = period_start.isocalendar()
    save_period_context(db, "ktoa_brand_context_weekly", period_start, period_end, messages, extra_fields={
        "year": year, "month": month, "week": week,
        "iso_year_week": f"{iso_year}-W{iso_week:02d}",
    })
    return messages


def build_monthly_report(db, agg: dict, year: int, month: int,
                          period_start: date, period_end: date) -> list:
    title1 = f"MNP 월간 실적 ({year}년 {month}월)"
    title3 = f"{year}년 {month}월"
    messages = [
        build_summary_message(agg, title1, period_start, period_end),
        build_change_message(db, "ktoa_mvno_monthly_summary", agg, period_start, period_end,
                              LOOKBACK_N["monthly"], title1, "전월비"),
        build_ms_message(agg, title3, period_start, period_end),
    ]
    save_period_context(db, "ktoa_brand_context_monthly", period_start, period_end, messages, extra_fields={
        "year": year, "month": month,
    })
    return messages


def send_telegram_report(messages: list) -> None:
    """개인 텔레그램 방으로 메시지별 개별 발송. ktoa_mvno_report.send_telegram과 동일 방식/청크 규칙."""
    import os
    import requests

    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = "-1003761301521"
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for msg in messages:
        if len(msg) <= 3800:
            resp = requests.post(url, json={"chat_id": chat_id, "text": msg})
            resp.raise_for_status()
        else:
            chunks, current = [], ""
            for section in msg.split("\n\n"):
                if len(current) + len(section) + 2 > 3800:
                    chunks.append(current)
                    current = section
                else:
                    current = f"{current}\n\n{section}" if current else section
            if current:
                chunks.append(current)
            for chunk in chunks:
                resp = requests.post(url, json={"chat_id": chat_id, "text": chunk})
                resp.raise_for_status()