"""
[수정 이력]
- v1.0 (2026-07-31): 최초 작성. 텔레그램 리포트(ktoa_mvno_report.py)와는
  별개로, Cloud Shell에서 즉석 조회용으로 만든 CLI 도구.
  S/K/L-MVNO 3망을 모두 운영하는 사업자를 자동으로 찾아, 각 사업자의
  오늘(또는 지정한 날짜) 실적을 "계 / SM / KM / LM" 순서로 출력한다.
  (텔레그램 리포트의 메시지3은 기존 포맷 "SM/KM/LM/계" 그대로 유지 -
  이 스크립트는 셸 조회 전용이며 리포트 발송 로직에는 영향 없음)
- v1.1 (2026-07-31): 프리텔레콤(L망=프리티) 같은 별칭 사업자도 3망 통합
  대상에 포함하도록 ALIAS_TO_CANONICAL 매핑 추가. ktoa_mvno_report.py의
  FIXED_BRAND_NETWORK_ALIASES와 동일한 사실관계를 반대 방향(실제표기 ->
  대표명)으로 반영.

사용법:
    python3 shell_brand_check.py                  # 오늘(KST) 기준
    python3 shell_brand_check.py 2026-07-30        # 특정 날짜 지정
"""

import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from google.cloud import firestore

PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
KST = timezone(timedelta(hours=9))

# ktoa_mvno_report.py와 동일한 매핑 재사용 (import 대신 직접 정의 - 독립 실행 스크립트로 유지)
NETWORK_DB_TO_LABEL = {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}
MNO_BRAND_NAMES = {"SKT", "KT", "LGU", "LGU+", "LG", "LG U+", "KTF", "LGT"}

import re
NAME_SUFFIX_PATTERN = re.compile(r"(SKT|KT|LGU\+|LG|\(재판매\)|\(미사용\))$")


def clean_brand_name(name: str) -> str:
    return NAME_SUFFIX_PATTERN.sub("", name).strip()


def is_mno_brand(name: str) -> bool:
    return name in MNO_BRAND_NAMES


# network별로 실제 brand명이 다르게 표기되는 경우의 별칭 매핑.
# ktoa_mvno_report.py의 FIXED_BRAND_NETWORK_ALIASES와 동일한 사실관계를
# 반대 방향(실제표기 -> 대표명)으로 정의: 프리텔레콤은 L-MVNO에서
# "프리티"라는 별도 브랜드명(L01)으로 등록되어 있음(프리텔레콤 자체는
# L망 미운영, 프리티가 그 실적을 가짐 - 실측 확인).
ALIAS_TO_CANONICAL = {
    ("L-MVNO", "프리티"): "프리텔레콤",
}


def get_target_date(arg: str | None) -> str:
    if arg:
        return arg
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch_day_docs(db, date_str: str) -> dict:
    """해당 날짜의 ktoa_mvno_brand_in 문서 전체. {brand: doc_dict}."""
    docs = db.collection("ktoa_mvno_brand_in").where("date", "==", date_str).stream()
    return {d.get("brand"): d for d in (doc.to_dict() for doc in docs)}


def find_full_network_brands(day_docs: dict) -> dict:
    """
    3망(S/K/L) 모두 존재하는 사업자만 골라 반환.
    {대표 사업자명: {"S-MVNO": (brand, total_in), "K-MVNO": ..., "L-MVNO": ...}}
    ALIAS_TO_CANONICAL에 등록된 별칭(예: L망의 "프리티" -> "프리텔레콤")은
    대표명으로 통합해서 그룹핑한다.
    """
    grouped = defaultdict(dict)
    for brand, doc in day_docs.items():
        if is_mno_brand(brand):
            continue
        network = NETWORK_DB_TO_LABEL.get(doc.get("network"))
        total_in = doc.get("total_in")
        if network is None or total_in is None:
            continue
        clean_name = clean_brand_name(brand)
        canonical_name = ALIAS_TO_CANONICAL.get((network, clean_name), clean_name)
        grouped[canonical_name][network] = (brand, total_in)

    return {
        name: nets for name, nets in grouped.items()
        if len(nets) == 3  # S/K/L 모두 존재
    }


def main():
    target_date = get_target_date(sys.argv[1] if len(sys.argv) > 1 else None)

    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    day_docs = fetch_day_docs(db, target_date)

    if not day_docs:
        print(f"{target_date}: 데이터 없음")
        return

    full_brands = find_full_network_brands(day_docs)

    if not full_brands:
        print(f"{target_date}: 3망(S/K/L) 모두 운영하는 사업자 없음")
        return

    # 계(3사 합) 기준 내림차순 정렬
    ranked = sorted(
        full_brands.items(),
        key=lambda item: sum(v[1] for v in item[1].values()),
        reverse=True,
    )

    print(f"=== 사업자 실적 (계/SM/KM/LM) - {target_date} ===")
    print(f"(3망 모두 운영하는 사업자 {len(ranked)}개, IN 합계 기준 내림차순)\n")

    for name, nets in ranked:
        s_in = nets["S-MVNO"][1]
        k_in = nets["K-MVNO"][1]
        l_in = nets["L-MVNO"][1]
        total = s_in + k_in + l_in
        print(f"◎ {name}")
        print(f"  계 : {total:,}건 (100%)")
        print(f"  SM : {s_in:,}건 ({s_in/total*100:.0f}%)")
        print(f"  KM : {k_in:,}건 ({k_in/total*100:.0f}%)")
        print(f"  LM : {l_in:,}건 ({l_in/total*100:.0f}%)")
        print()


if __name__ == "__main__":
    main()