"""
[수정 이력]
- v1.0 (2026-07-29): 최초 작성(ktoa_mvno_top10.py). S/K/L-MVNO 각각
  IN/OUT/순증감 top10 산출. 같은요일(휴일은 휴일끼리) 최근 4주 평균 대비
  ±30% 특이점 표시.
- v1.1 (2026-07-29): 텔레그램 포맷을 단순 한줄형으로 변경. 특이점을
  순증감 섹션에도 확장.
- v2.0 (2026-07-29): 3개 메시지 구조로 전면 재작성 (ktoa_mvno_report.py로
  파일명 변경, 기존 top10.py는 폐기 예정).
  - 메시지1: S-MVNO는 IN>0 전체, K/L-MVNO는 IN top10(+전체/IN≥100 사업자수
    표기). 특이점 기준 30%→20%로 변경. 사업자명 접미사(SKT/KT/LG/재판매/
    미사용 등) 제거해서 표시. 신규 사업자(비교 baseline 데이터 자체가
    없는 경우)는 🆕신규 태그로 별도 표시(20% 증감 판정과는 별개).
  - 메시지2: 메시지1과 동일 데이터에서 특이점(20% 이상 또는 신규)에
    해당하는 사업자만 IN/OUT/순증감별로 재구성해 모아서 표시.
  - 메시지3(신규): 고정 사업자 4개(프리텔레콤/유니컴즈/아이즈비전/스마텔)
    × S/K/L 망별 M/S. M/S는 최근 7일 가중평균(7일 건수합 기준 비율)
    대비 오늘 M/S의 %p 차이. 증가 ▲, 감소 ▼ 표시.
- v2.1 (2026-07-29): Cloud Shell 실제 실행 결과 기반 버그 3건 수정.
  (1) brand명이 "SKT"/"KT"/"LGU" 자체인 원조 3사 데이터가 brand_in에
      존재해 clean_brand_name()이 통째로 지워 빈 이름으로 표시되던 문제
      -> is_mno_brand()로 판별해 리포트에서 완전 제외.
  (2) ktoa_mvno_brand_out 문서에는 network 필드가 저장되어 있지 않아
      (실측 결과 None) OUT 집계가 전부 0으로 나오던 문제 -> brand_in의
      {brand: network} 매핑으로 out_docs를 보정하는 fill_missing_network()
      추가.
  (3) 순증감(IN-OUT) 특이점 판정 시 baseline이 0 근처라 변동률이
      -5600%, +8709% 등으로 발산하던 문제 -> classify_net_change()를
      신설해 순증감만 비율이 아닌 baseline 대비 절대값 차이(100건 이상)로
      판정/표시.
- v2.2 (2026-07-29): 실사용 피드백 반영 2건.
  (1) IN 값이 50건 미만인 소액 사업자는 %가 사소한 변동에도 과민 반응하므로
      classify_change()에 min_value 기준(기본 50) 추가 - 신규 판정은 값
      크기와 무관하게 그대로 유지, 특이점(%) 판정만 생략.
  (2) 메시지2 순증감 섹션 표현을 "평소 대비 N건"에서 "평소 X건 → 오늘 Y건"
      형태로 변경해 부호 해석 혼동을 줄임(spike_records에 diff 대신
      baseline 원값을 저장하도록 build_message1도 함께 수정).
- v2.3 (2026-07-29): 포맷 재정비(사용자 제공 목업 반영).
  (1) 공통: 증감 부호를 증가 '+', 감소 '▲'(시각 강조 목적)로 통일
      -> format_signed() 헬퍼 신설, 메시지1/2/3에 일괄 적용.
  (2) 메시지1: network 헤더에 (전체IN/전체OUT/전체순증) 요약 추가.
      IN 최소기준 100→50으로 하향(IN_FLOOR_FOR_COUNT). IN 특이점 표시에
      baseline값 병기: "⚡ IN+120% (5 → 11)".
  (3) 메시지2: 타이틀에 ⚡ 추가. "N% 증가/감소 (baseline건 → 오늘건)"
      문장형으로 변경(기존 "+N건 (change%)"에서 전환). IN/OUT spike_records
      튜플에 baseline 추가(4요소로 확장).
  (4) 메시지3: 구분자 '—'를 ':'로, 부호 표시 통일.
  주의: 메시지3에서 특정 사업자·망 조합이 "데이터 없음"으로 나오는 경우는
  fixed_name 매칭 실패 원인 확인 필요(예: 프리텔레콤 L망) - Cloud Shell에서
  해당 브랜드의 실제 network/기간별 데이터 존재 여부 확인 중, 원인 파악되면
  로직 보강 예정.
- v2.4 (2026-07-29): 메시지3 "프리텔레콤 L: 데이터 없음" 원인 확인 및 수정.
  실측 결과 프리텔레콤은 L-MVNO에서 "프리티"라는 별도 브랜드명(L01)으로
  등록되어 있음(프리텔레콤 자체는 L망 미운영, 프리티가 그 실적을 가짐).
  FIXED_BRAND_NETWORK_ALIASES 딕셔너리 신설 - 메시지3 표시명은 "프리텔레콤"
  유지하되 L-MVNO 매칭 시에는 "프리티"로 검색하도록 처리.
- v2.5 (2026-07-29): 세부 포맷 튜닝 3건.
  (1) 메시지1: K/L-MVNO 헤더의 "전체N개 중 IN≥50 M개" 문구를 요약 라인과
      분리해 다음 줄로 이동. 사업자별 ⚡특이점도 같은 줄이 아닌 다음 줄로
      줄바꿈하고 표현을 "IN N% 증가/감소 (baseline → 오늘)" 문장형으로
      통일(기존 "IN+29%" 방식에서 전환, 메시지2와 표현 통일).
  (2) 메시지3: 비율(%) 산출 기준을 "해당 망 내 비율"에서 "S+K+L 3사 합산
      대비 비율"로 변경(사용자 확정). 7일 가중평균 대비 %p 차이도 동일하게
      합산 기준으로 재계산(권장안 채택 - 비율표시와 %p가 같은 모수를
      가리켜야 혼동이 없음). 사업자별 "계" 줄(3망 합계 건수+비율) 추가.
- v2.6 (2026-07-29): v2.5의 메시지3 "3사 합산" 해석 오류 수정. v2.5에서는
  분모를 "4개 고정사업자 전체의 3망 합계"로 잘못 계산해 프리텔레콤 등이
  1~4%처럼 비정상적으로 작게 나왔음. 올바른 분모는 "그 사업자 자신의
  오늘 S+K+L 합계"(사업자 안에서 S+K+L 비율 합=100%가 되어야 함) - 실측
  결과로 확인(프리텔레콤 S/K/L=495/240/276 -> 49%/24%/27%, 계 100%).
  today_grand_total/recent_grand_total(4사업자 전체 합산) 계산 제거,
  build_message3 내부를 "S/K/L 값 먼저 수집 -> 사업자 자신의 합계로 나눔"
  2단계 구조로 재작성. 데이터가 전혀 없는 사업자는 "계 0건 (0%)"로 표시
  (100%로 잘못 표시되던 것 수정).
- v2.7 (2026-07-29): 문구/줄바꿈 세부 조정.
  (1) 메시지1: "[ IN/OUT/순증 ]" -> "[ IN/OUT/순증감 ]", K/L 헤더
      "전체N개 중 IN≥50 M개" -> "...M개 사업자".
  (2) 메시지2: [IN]/[OUT]/[순증감] 섹션 사이 한 줄 띄기, ◎ network 블록
      사이 두 줄 띄기로 간격 규칙 정리(기존엔 섹션 간 간격이 없었고
      network 간은 한 줄뿐이었음).

사업자별(브랜드) 텔레그램 리포트 생성 스크립트
- 대상 컬렉션: ktoa_mvno_brand_in, ktoa_mvno_brand_out
  (KTOA_사업자별_작업요약_20260728.md 스키마 기준)
- network 필드 값으로 S-MVNO / K-MVNO / L-MVNO 그룹핑

실행 환경: 로컬(이 환경)에서는 Firestore 접근 불가(egress 미허용).
  Cloud Shell(~/mvno-bot-cloudrun/mvno-bot-cloudrun)에 복사해
  `source ~/.ktoa_env` 후 실행할 것.

사용법:
    python3 ktoa_mvno_report.py 2026-07-28
    python3 ktoa_mvno_report.py 2026-07-28 --telegram   # 텔레그램 발송(개인방)
"""

import re
import argparse
from datetime import date, timedelta
from collections import defaultdict

from google.cloud import firestore

# ── 설정 ──────────────────────────────────────────────────────────────
PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
NETWORKS = ["S-MVNO", "K-MVNO", "L-MVNO"]
# Firestore의 network 필드 실제 값(SKT/KT/LGU, Cloud Shell에서 실측 확인) -> 표시용 그룹명 매핑.
# DB 필드값은 그대로 두고, 스크립트에서만 표시용으로 변환.
NETWORK_DB_TO_LABEL = {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}
LOOKBACK_WEEKS = 4              # 메시지1/2 특이점: 같은요일/휴일 비교 주 수
SPIKE_THRESHOLD = 0.20          # 메시지1/2 특이점 기준 (±20%)
MS_LOOKBACK_DAYS = 7            # 메시지3: M/S 가중평균 기간
TOP_N = 10
IN_FLOOR_FOR_COUNT = 50         # "IN 50건 이상 사업자 수" 집계 기준
FIXED_BRANDS_FOR_MS = ["프리텔레콤", "유니컴즈", "아이즈비전", "스마텔"]  # 메시지3 고정 리스트
# 표시 사업자명(FIXED_BRANDS_FOR_MS)과 실제 brand명(clean_brand_name 결과 기준)이
# network별로 다르게 표기되는 경우의 예외 매핑. {표시명: {network: 실제 정규화명}}.
# 실측 확인: 프리텔레콤은 L-MVNO에서 "프리티"라는 별도 브랜드명으로 등록되어 있음(문서상 L01, brand="프리티LG").
FIXED_BRAND_NETWORK_ALIASES = {
    "프리텔레콤": {"L-MVNO": "프리티"},
}

# 한국 공휴일 (2026년 기준, 필요시 갱신)
KR_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 1), date(2026, 3, 2),
    date(2026, 5, 5),
    date(2026, 5, 24), date(2026, 5, 25),
    date(2026, 6, 6),
    date(2026, 8, 15), date(2026, 8, 17),
    date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26),
    date(2026, 10, 3),
    date(2026, 10, 9),
    date(2026, 12, 25),
}

# 사업자명 뒤에 붙는 network/재판매 접미사 제거용 패턴.
# 같은 network(S/K/L) 그룹 안에서는 접미사를 떼도 사업자명이 겹치지 않음 (사용자 확인 완료).
# 주의: "세종텔레콤(KT)"처럼 괄호 안 문구가 브랜드 고유 표기의 일부인 경우는
# 이 패턴(SKT/KT/LGU+/LG/(재판매)/(미사용) 끝문자열 매칭)에 걸리지 않아 원본 유지됨 - 의도된 동작.
NAME_SUFFIX_PATTERN = re.compile(r"(SKT|KT|LGU\+|LG|\(재판매\)|\(미사용\))$")

# brand명이 이 값과 완전히 일치하면 MVNO가 아니라 원조 통신 3사(MNO) 자체 데이터이므로
# 리포트에서 제외한다. Cloud Shell 실측: brand_in에 "SKT"(total_in=5513, S-MVNO),
# "LGU+"(total_in=4918, L-MVNO) 브랜드명 자체로 존재 확인. K-MVNO측 원조 표기("KT"/"KTF" 등)는
# 미실측이나 md 파일(MNO_CODES={"SKT":"SKT","KTF":"KT","LGT":"LGU"})의 코드 체계를 참고해
# 가능한 표기를 모두 포함해둠 - 리포트에 원조 브랜드가 다시 보이면 이 세트에 실제 값 추가 필요.
MNO_BRAND_NAMES = {"SKT", "KT", "LGU", "LGU+", "LG", "LG U+", "KTF", "LGT"}


def is_mno_brand(name: str) -> bool:
    """brand명이 원조 3사(SKT/KT/LGU 등) 코드값 자체인지 판별."""
    return name in MNO_BRAND_NAMES


def format_signed(value: float, unit: str = "") -> str:
    """
    증감값 표시 공통 포맷. 사용자 확정 규칙: 증가는 '+', 감소는 '▲'(시각적 강조 목적).
    예: format_signed(23) -> '+23', format_signed(-100) -> '▲100'
    """
    if value >= 0:
        return f"+{value:,.0f}{unit}"
    return f"▲{abs(value):,.0f}{unit}"


def clean_brand_name(name: str) -> str:
    """사업자명 뒤 접미사(SKT/KT/LG/재판매/미사용) 제거. 매칭 안 되면 원본 그대로."""
    return NAME_SUFFIX_PATTERN.sub("", name).strip()


def is_holiday(d: date) -> bool:
    return d in KR_HOLIDAYS_2026 or d.weekday() >= 5


def get_comparison_dates(target_date: date, weeks: int = LOOKBACK_WEEKS) -> list[date]:
    """target_date와 같은 유형(휴일/같은요일)의 과거 날짜를 최근순 weeks개 반환."""
    results = []
    target_is_holiday = is_holiday(target_date)
    cursor = target_date - timedelta(days=1)
    for _ in range(200):
        if len(results) >= weeks:
            break
        if target_is_holiday:
            if is_holiday(cursor):
                results.append(cursor)
        else:
            if cursor.weekday() == target_date.weekday() and not is_holiday(cursor):
                results.append(cursor)
        cursor -= timedelta(days=1)
    return results


def get_recent_n_days(target_date: date, n: int = MS_LOOKBACK_DAYS) -> list[date]:
    """target_date 이전 n일(요일 구분 없이 달력일 기준)."""
    return [target_date - timedelta(days=i) for i in range(1, n + 1)]


_doc_cache: dict[tuple[str, str], dict] = {}


def fetch_brand_docs(db, collection_name: str, target_date: date) -> dict:
    """지정 날짜의 brand_in/out 문서 전체. {brand: doc_dict}. 같은 (collection, date) 재조회 방지 캐싱."""
    key = (collection_name, target_date.isoformat())
    if key in _doc_cache:
        return _doc_cache[key]
    date_str = target_date.strftime("%Y-%m-%d")
    docs = db.collection(collection_name).where("date", "==", date_str).stream()
    result = {d.get("brand"): d for d in (doc.to_dict() for doc in docs)}
    _doc_cache[key] = result
    return result


def build_network_totals(brand_docs: dict, value_field: str) -> dict:
    """{brand: doc} -> {network(표시용 라벨): {brand: value}}. DB의 network(SKT/KT/LGU)를 S/K/L-MVNO로 변환.
    brand명이 원조 3사 자체(SKT/KT/LGU 등)인 경우는 MVNO가 아니므로 제외."""
    result = defaultdict(dict)
    for brand, doc in brand_docs.items():
        if is_mno_brand(brand):
            continue
        db_network = doc.get("network")
        network = NETWORK_DB_TO_LABEL.get(db_network)
        value = doc.get(value_field)
        if network is None or value is None:
            continue
        result[network][brand] = value
    return result


def compute_baseline(db, collection_name: str, value_field: str,
                      target_date: date, brand: str) -> float | None:
    """해당 브랜드의 최근 N개 비교일(같은요일/휴일) 평균. 데이터가 하나도 없으면 None(=신규 후보)."""
    comp_dates = get_comparison_dates(target_date)
    values = []
    for d in comp_dates:
        docs = fetch_brand_docs(db, collection_name, d)
        doc = docs.get(brand)
        if doc and doc.get(value_field) is not None:
            values.append(doc[value_field])
    if not values:
        return None
    return sum(values) / len(values)


def compute_net_baseline(db, target_date: date, brand: str) -> float | None:
    """순증감(IN-OUT)의 최근 N개 비교일 평균. 데이터가 하나도 없으면 None."""
    comp_dates = get_comparison_dates(target_date)
    values = []
    for d in comp_dates:
        in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", d)
        out_docs = fetch_brand_docs(db, "ktoa_mvno_brand_out", d)
        in_doc = in_docs.get(brand)
        out_doc = out_docs.get(brand)
        if in_doc is None and out_doc is None:
            continue
        in_v = in_doc.get("total_in", 0) if in_doc else 0
        out_v = out_doc.get("total_out", 0) if out_doc else 0
        values.append(in_v - out_v)
    if not values:
        return None
    return sum(values) / len(values)


MIN_VALUE_FOR_SPIKE = 50  # 이 값 미만인 경우 특이점(%) 판정 생략 (소액 사업자의 % 과민반응 방지)


def classify_change(current: float, baseline: float | None,
                     min_value: float = MIN_VALUE_FOR_SPIKE) -> tuple[str, float | None]:
    """
    (태그, 변동률) 반환. IN/OUT 특이점 판정용(비율 기반).
    - baseline이 None -> ("신규", None)  # 신규 여부는 값 크기와 무관하게 항상 판정
    - current < min_value -> ("", 변동률 or None)  # 소액이면 특이점 판정 생략(신규 제외)
    - |변동률| >= SPIKE_THRESHOLD -> ("특이", 변동률)
    - 그 외 -> ("", 변동률)
    """
    if baseline is None:
        return "신규", None
    if current < min_value:
        change = None if baseline == 0 else (current - baseline) / baseline
        return "", change
    if baseline == 0:
        return ("특이", None) if current > 0 else ("", 0.0)
    change = (current - baseline) / baseline
    if abs(change) >= SPIKE_THRESHOLD:
        return "특이", change
    return "", change


NET_SPIKE_ABS_THRESHOLD = 100  # 순증감(IN-OUT) 특이점 판정: baseline 대비 절대값 100건 이상 차이


def classify_net_change(current: float, baseline: float | None) -> tuple[str, float | None]:
    """
    순증감(IN-OUT) 전용 판정. IN/OUT과 달리 baseline이 0 근처에서 %가 발산하므로
    비율이 아닌 절대값 차이(건수)로 특이점을 판정한다.
    (태그, 절대값차이) 반환.
    - baseline이 None -> ("신규", None)
    - |current - baseline| >= NET_SPIKE_ABS_THRESHOLD -> ("특이", 차이값)
    - 그 외 -> ("", 차이값)
    """
    if baseline is None:
        return "신규", None
    diff = current - baseline
    if abs(diff) >= NET_SPIKE_ABS_THRESHOLD:
        return "특이", diff
    return "", diff


# ── 메시지1: 사업자별 실적 (S 전체 / K·L top10) ─────────────────────────

def build_message1(db, target_date: date, in_totals: dict, out_totals: dict) -> tuple[str, dict]:
    """
    반환: (메시지 텍스트, spike_records)
    spike_records: {network: {"in": [(name, value, change)], "out": [...], "net": [...], "new": {"in":[...],"out":[...],"net":[...]}}}
    메시지2에서 재사용하기 위해 특이점/신규 기록을 함께 반환.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [f"📊 MNP 주요 사업자별 실적 ({date_str})", "[ IN/OUT/순증감 ]"]
    spike_records = {}

    for network in NETWORKS:
        in_by_brand = in_totals.get(network, {})
        out_by_brand = out_totals.get(network, {})
        all_brands = set(in_by_brand) | set(out_by_brand)

        spike_records[network] = {"in": [], "out": [], "net": [], "new": {"in": [], "out": [], "net": []}}

        if not all_brands:
            lines.append(f"\n◎ {network}: 데이터 없음")
            continue

        # 정렬은 IN 기준, S는 IN>0 전체, K/L은 top10
        ranked = sorted(all_brands, key=lambda b: in_by_brand.get(b, 0), reverse=True)
        ranked = [b for b in ranked if in_by_brand.get(b, 0) > 0]

        total_count = len(all_brands)
        in_floor_count = sum(1 for b in all_brands if in_by_brand.get(b, 0) >= IN_FLOOR_FOR_COUNT)

        network_in_sum = sum(in_by_brand.values())
        network_out_sum = sum(out_by_brand.values())
        network_net_sum = network_in_sum - network_out_sum
        summary = f"{network_in_sum:,}/{network_out_sum:,}/{format_signed(network_net_sum)}"

        if network == "S-MVNO":
            header = f"\n◎ {network} ({summary})"
            display_list = ranked
        else:
            header = f"\n◎ {network} ({summary})\n전체 {total_count}개 중 IN≥{IN_FLOOR_FOR_COUNT} {in_floor_count}개 사업자"
            display_list = ranked[:TOP_N]

        lines.append(header)
        for i, brand in enumerate(display_list, 1):
            in_v = in_by_brand.get(brand, 0)
            out_v = out_by_brand.get(brand, 0)
            net_v = in_v - out_v
            display_name = clean_brand_name(brand)

            in_baseline = compute_baseline(db, "ktoa_mvno_brand_in", "total_in", target_date, brand)
            in_tag, in_change = classify_change(in_v, in_baseline)

            tag_str = ""
            if in_tag == "신규":
                tag_str = " 🆕신규"
                spike_records[network]["new"]["in"].append((display_name, in_v))
            elif in_tag == "특이":
                baseline_str = f"{in_baseline:,.0f}" if in_baseline is not None else "0"
                direction = "증가" if in_change >= 0 else "감소"
                tag_str = f"\n   ⚡ IN {abs(in_change):.0%} {direction} ({baseline_str} → {in_v:,})"
                spike_records[network]["in"].append((display_name, in_v, in_change, in_baseline))

            lines.append(f"{i}) {display_name} : {in_v:,} / {out_v:,} / {format_signed(net_v)}{tag_str}")

        # OUT/순증 특이점도 별도 계산해서 메시지2용으로 기록(메시지1 본문에는 IN 특이점만 표기)
        for brand in display_list:
            out_v = out_by_brand.get(brand, 0)
            out_baseline = compute_baseline(db, "ktoa_mvno_brand_out", "total_out", target_date, brand)
            out_tag, out_change = classify_change(out_v, out_baseline)
            display_name = clean_brand_name(brand)
            if out_tag == "신규":
                spike_records[network]["new"]["out"].append((display_name, out_v))
            elif out_tag == "특이":
                spike_records[network]["out"].append((display_name, out_v, out_change, out_baseline))

            net_v = in_by_brand.get(brand, 0) - out_v
            net_baseline = compute_net_baseline(db, target_date, brand)
            net_tag, net_diff = classify_net_change(net_v, net_baseline)
            if net_tag == "신규":
                spike_records[network]["new"]["net"].append((display_name, net_v))
            elif net_tag == "특이":
                spike_records[network]["net"].append((display_name, net_v, net_baseline))

    return "\n".join(lines), spike_records


# ── 메시지2: 특이사항 모음 ────────────────────────────────────────────

def build_message2(target_date: date, spike_records: dict) -> str:
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [
        f"📊 MNP 사업자별 증감 특이사항⚡ ({date_str})",
        f"(4주간 같은 요일/휴일 평균 대비 ±{SPIKE_THRESHOLD:.0%})",
    ]

    for network in NETWORKS:
        rec = spike_records.get(network, {"in": [], "out": [], "net": [], "new": {"in": [], "out": [], "net": []}})
        lines.append(f"\n\n◎ {network}")

        for label, key in [("IN", "in"), ("OUT", "out"), ("순증감", "net")]:
            items = rec[key]
            new_items = rec["new"][key]
            if not items and not new_items:
                lines.append(f"[{label}] 해당 없음")
                lines.append("")
                continue
            lines.append(f"[{label}]")
            if key == "net":
                # 순증감은 baseline(평소 순증감) -> 오늘 순증감 형태로 명시 표시
                for name, value, baseline in items:
                    lines.append(f"  {name} : 평소 {format_signed(baseline)}건 → 오늘 {format_signed(value)}건")
            else:
                for name, value, change, baseline in items:
                    direction = "증가" if change >= 0 else "감소"
                    baseline_str = f"{baseline:,.0f}" if baseline is not None else "0"
                    lines.append(f"  {name} : {abs(change):.0%} {direction} ({baseline_str}건 → {value:,}건)")
            for name, value in new_items:
                lines.append(f"  {name} : {value:,}건 🆕신규")
            lines.append("")  # 섹션([IN]/[OUT]/[순증감]) 사이 한 줄 띄기

        if lines[-1] == "":
            lines.pop()  # 마지막 섹션(순증감) 뒤 빈 줄은 다음 ◎ 헤더의 두줄 띄기(\n\n)와 합쳐지므로 제거

    return "\n".join(lines)


# ── 메시지3: 사업자·망별 M/S (7일 가중평균 대비) ─────────────────────

def build_message3(db, target_date: date) -> str:
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [
        f"📊 MNP 사업자/망별 M/S ({date_str})",
        "(비교 값은 M/S 기준 최근 7일 평균 대비 %p 차이)",
    ]

    recent_days = get_recent_n_days(target_date, MS_LOOKBACK_DAYS)

    # 오늘자 in_docs
    today_in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", target_date)

    # 최근 7일 network별 사업자별 IN 합 (가중평균 분자용)
    recent_brand_totals = defaultdict(lambda: defaultdict(int))  # {network: {brand: sum}}
    for d in recent_days:
        docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", d)
        for brand, doc in docs.items():
            net = NETWORK_DB_TO_LABEL.get(doc.get("network"))
            val = doc.get("total_in")
            if net and val is not None:
                recent_brand_totals[net][brand] += val

    for fixed_name in FIXED_BRANDS_FOR_MS:
        lines.append(f"\n◎ {fixed_name}")

        # 1단계: S/K/L 값을 먼저 전부 수집 (비율 분모=해당 사업자 자신의 S+K+L 합계이므로 먼저 합계 확정 필요)
        per_network_data = {}  # {net_label: (today_v, recent_brand_sum) or None(데이터없음)}
        for net_label, network in [("S", "S-MVNO"), ("K", "K-MVNO"), ("L", "L-MVNO")]:
            # network별로 실제 brand명이 다르게 표기되는 경우(예: 프리텔레콤의 L망="프리티") 적용
            search_name = FIXED_BRAND_NETWORK_ALIASES.get(fixed_name, {}).get(network, fixed_name)

            matched_brand = None
            for brand in today_in_docs:
                if NETWORK_DB_TO_LABEL.get(today_in_docs[brand].get("network")) == network and clean_brand_name(brand) == search_name:
                    matched_brand = brand
                    break
            if matched_brand is None:
                for net_brands in recent_brand_totals.get(network, {}):
                    if clean_brand_name(net_brands) == search_name:
                        matched_brand = net_brands
                        break
            if matched_brand is None:
                per_network_data[net_label] = None
                continue

            today_v = today_in_docs.get(matched_brand, {}).get("total_in", 0)
            recent_brand_sum = recent_brand_totals[network].get(matched_brand, 0)
            per_network_data[net_label] = (today_v, recent_brand_sum)

        # 2단계: 해당 사업자 자신의 S+K+L 합계를 분모로 비율 산출 (사업자 안에서 3사 합=100%)
        brand_today_sum = sum(v[0] for v in per_network_data.values() if v is not None)
        brand_recent_sum = sum(v[1] for v in per_network_data.values() if v is not None)

        for net_label in ["S", "K", "L"]:
            data = per_network_data[net_label]
            if data is None:
                lines.append(f"  {net_label}: 데이터 없음")
                continue
            today_v, recent_brand_sum = data
            today_pct = (today_v / brand_today_sum * 100) if brand_today_sum else 0.0
            weighted_avg_pct = (recent_brand_sum / brand_recent_sum * 100) if brand_recent_sum else None

            if weighted_avg_pct is None:
                diff_str = "비교불가(최근 데이터 없음)"
            else:
                diff = today_pct - weighted_avg_pct
                diff_str = f"+{diff:.1f}%p" if diff >= 0 else f"▲{abs(diff):.1f}%p"

            lines.append(f"  {net_label}: {today_v:,}건 ({today_pct:.0f}%) : {diff_str}")

        total_label = "100%" if brand_today_sum else "0%"
        lines.append(f" 계 : {brand_today_sum:,}건 ({total_label})")

    return "\n".join(lines)


# ── 실행 ──────────────────────────────────────────────────────────────

def fill_missing_network(target_docs: dict, reference_docs: dict) -> dict:
    """
    target_docs(예: brand_out)의 문서에 network 필드가 비어있으면
    reference_docs(예: brand_in, 같은 brand명 기준)의 network 값으로 보정.
    (Cloud Shell 실측: ktoa_mvno_brand_out 문서는 network 필드가 저장되지 않음 - None)
    원본 dict는 변경하지 않고 새 dict를 반환.
    """
    result = {}
    for brand, doc in target_docs.items():
        doc = dict(doc)  # 원본 보호를 위한 얕은 복사
        if not doc.get("network"):
            ref_doc = reference_docs.get(brand)
            if ref_doc and ref_doc.get("network"):
                doc["network"] = ref_doc["network"]
        result[brand] = doc
    return result


def build_all_reports(target_date: date) -> tuple[str, str, str]:
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

    in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", target_date)
    out_docs = fetch_brand_docs(db, "ktoa_mvno_brand_out", target_date)
    out_docs = fill_missing_network(out_docs, in_docs)  # brand_out에 network 필드 없음 -> brand_in 기준 보정

    in_totals = build_network_totals(in_docs, "total_in")
    out_totals = build_network_totals(out_docs, "total_out")

    msg1, spike_records = build_message1(db, target_date, in_totals, out_totals)
    msg2 = build_message2(target_date, spike_records)
    msg3 = build_message3(db, target_date)

    return msg1, msg2, msg3


def send_telegram(messages: list[str]):
    """개인 텔레그램 방으로 메시지별 개별 발송."""
    import os
    import requests

    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = "-1003761301521"  # 개인 방 (테스트/검증 전용)
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for msg in messages:
        # 4096자 제한 대응: 필요시 섹션(◎) 단위로 분할
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


def main():
    parser = argparse.ArgumentParser(description="KTOA 사업자별 텔레그램 리포트 (3종)")
    parser.add_argument("target_date", help="조회 날짜 (YYYY-MM-DD)")
    parser.add_argument("--telegram", action="store_true", help="개인 텔레그램 방으로 발송")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.target_date)
    msg1, msg2, msg3 = build_all_reports(target_date)

    print(msg1)
    print("\n" + "=" * 50 + "\n")
    print(msg2)
    print("\n" + "=" * 50 + "\n")
    print(msg3)

    if args.telegram:
        send_telegram([msg1, msg2, msg3])
        print("\n[텔레그램 발송 완료 - 개인방, 3건]")


if __name__ == "__main__":
    main()