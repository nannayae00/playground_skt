"""
merge_performance_into_profiles.py  v1.1
작성일: 2026-08-17

[수정 이력]
v1.1 (2026-08-18): networks 요약에 yoy_growth(연도별 합계) 필드 누락돼있던
  버그 수정 - 컨플루언스 문서에 "월평균 IN(24/25/26년)"을 추가하려 했는데
  이 필드가 애초에 안 뽑혀있어서 항상 비어있었음(사용자 발견). DB에서
  다시 뽑아오는 것뿐이라 build_brand_insights_v2.py 재실행은 필요 없음.
v1.0 (2026-08-17): 최초 작성. brand_profiles_merged.json(웹조사 프로필)의
  각 사업자 항목 안에 ktoa_mvno_brand_insights(DB 실적분석)에서 뽑은
  가벼운 요약을 "performance_summary" 필드로 병합 - 사용자 요청(2026-08-17):
  "실적기반 요약도 같은 json에 들어가면 좋겠다".

  넣는 내용(가벼운 것만 - 유입/유출top5 같은 무거운 건 제외):
    - networks: {망: {first_active_month, all_time_high, all_time_low}}
    - recent_events: 최근 5건 특이사항(급성장/급감소/휴면/재개)

  import_brand_profiles.py(반대 방향 - JSON→DB 병합)와는 반대 흐름.
  이 스크립트는 DB→JSON 방향. match_keywords로 브랜드 매칭하는 로직은
  import_brand_profiles.py와 동일하게 재사용.

사용법:
    python3 merge_performance_into_profiles.py brand_profiles_merged.json

  결과: brand_profiles_merged.json을 그 자리에서 덮어씀(각 브랜드 항목에
  performance_summary 필드 추가). 원본을 보존하고 싶으면 실행 전에 따로
  백업해둘 것.
"""

import json
import logging
import sys

from ktoa_mvno_period_aggregator import _get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def find_best_match(existing_ids: list, keywords: list):
    for kw in keywords:
        if kw in existing_ids:
            return kw
    for doc_id in existing_ids:
        for kw in keywords:
            if kw and (kw in doc_id or doc_id in kw):
                return doc_id
    return None


def build_summary(insight_doc: dict) -> dict:
    networks = insight_doc.get("networks", {})
    summary_networks = {}
    all_events = []

    for net, nd in networks.items():
        summary_networks[net] = {
            "first_active_month": nd.get("first_active_month"),
            "all_time_high": nd.get("all_time_high"),
            "all_time_low": nd.get("all_time_low"),
            "significant_low": nd.get("significant_low"),
            # 24/25/26년 월평균 IN 계산에 필요 - v1.0에서 빠뜨렸던 필드
            # (사용자 발견, 2026-08-18: "월평균 IN 추가 안 된 것 같다")
            "yoy_growth": nd.get("yoy_growth", {}),
        }

    for ev in insight_doc.get("events", []):
        all_events.append(ev)

    recent_events = sorted(all_events, key=lambda e: e.get("period", ""), reverse=True)[:5]
    recent_events_summary = [
        f"{e.get('period')} [{e.get('network')}] {e.get('type')} - {e.get('detail')}"
        for e in recent_events
    ]

    return {"networks": summary_networks, "recent_events": recent_events_summary}


def run(json_path: str) -> None:
    db = _get_db()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    insight_docs = {d.id: d.to_dict() for d in db.collection("ktoa_mvno_brand_insights").stream()}
    existing_ids = list(insight_docs.keys())
    log.info(f"ktoa_mvno_brand_insights 문서: {len(existing_ids)}개")

    matched, unmatched = 0, []

    for profile in data.get("brands", []):
        keywords = profile["match_keywords"]
        doc_id = find_best_match(existing_ids, keywords)

        if not doc_id:
            unmatched.append(keywords[0])
            continue

        profile["performance_summary"] = build_summary(insight_docs[doc_id])
        matched += 1

    log.info(f"완료: 매칭 {matched}개 / 미매칭 {len(unmatched)}개")
    if unmatched:
        log.warning(f"미매칭(실적 데이터 없거나 DB에 아직 없음): {unmatched}")

    data["note"] = data.get("note", "") + f" | performance_summary 병합됨 ({matched}개 사업자)"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"저장 완료: {json_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "brand_profiles_merged.json"
    run(path)