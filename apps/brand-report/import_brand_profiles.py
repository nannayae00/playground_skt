"""
import_brand_profiles.py  v1.2
작성일: 2026-08-07

[수정 이력]
v1.2 (2026-08-07): discontinued(사업 종료/매각 이력) 리스트 처리 추가 -
  brands와 별개 배열로 받아서 같은 매칭 로직으로 discontinued/
  discontinued_period/discontinued_detail 필드만 추가(다른 프로필 필드는
  안 건드림). 우리 DB의 휴면/영구중단 감지 이벤트와 대조하는 용도.
v1.1 (2026-08-07): market_events 처리 추가 - JSON에 market_events 키가
  있으면 ktoa_mvno_market_events 컬렉션에 별도 저장(특정 사업자가 아닌
  시장 전체 이벤트 - 예: KT 위약금 면제 사태로 인한 업계 전반 초저가
  경쟁). 브랜드별 events와 구분해서 "개별 이슈 vs 시장 전체 이벤트" 해석에
  참고자료로 사용.
v1.0 (2026-08-07): 최초 작성. 웹 조사로 모은 사업자 프로필(홈페이지/주소/
  대표/특이사항 - brand_profiles_batch1.json)을 ktoa_mvno_brand_insights
  컬렉션에 병합. clean_name(문서ID) 정확한 표기를 미리 알 수 없어서
  match_keywords(후보 여러 개)로 기존 문서 중 가장 가까운 걸 자동 매칭:
    1) 문서ID(clean_name) 자체가 키워드와 완전히 같으면 최우선
    2) 문서ID가 키워드를 포함하거나(부분일치) 키워드가 문서ID를 포함하면 후보
  매칭된 문서에 homepage_url/address/ceo/notes 필드를 merge=True로 추가
  (기존 events/networks 등은 그대로 유지 - build_brand_insights.py가 만든
  구조를 덮어쓰지 않음).
  매칭 안 된 항목은 목록으로 출력만 하고 건드리지 않음(수동 확인 필요).

실행 환경: Cloud Shell. 전제조건: build_brand_insights.py를 먼저 실행해서
ktoa_mvno_brand_insights 문서들이 이미 생성돼 있어야 함(매칭 대상 필요).
"""

import json
import logging

from google.cloud import firestore as fs

from ktoa_mvno_period_aggregator import _get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def find_best_match(existing_ids: list, keywords: list) -> str | None:
    for kw in keywords:
        if kw in existing_ids:
            return kw
    for doc_id in existing_ids:
        for kw in keywords:
            if kw and (kw in doc_id or doc_id in kw):
                return doc_id
    return None


def import_market_events(data: dict) -> int:
    """
    JSON의 market_events(있으면)를 ktoa_mvno_market_events 컬렉션에 저장.
    특정 사업자가 아니라 시장 전체에 영향을 준 사건(예: 특정 통신사 위약금
    면제 사태로 인한 업계 전반 초저가 경쟁) - 여러 사업자에서 동시다발적
    이상 이벤트가 감지될 때 "개별 이슈 vs 시장 전체 이벤트" 구분용 참고자료.
    """
    events = data.get("market_events")
    if not events:
        return 0

    db = _get_db()
    count = 0
    for ev in events:
        doc_id = ev["period"].split(" ")[0]  # 기간 앞부분을 문서ID로 (겹치면 덮어씀 - 의도된 동작)
        ref = db.collection("ktoa_mvno_market_events").document(doc_id)
        ref.set({**ev, "updated_at": fs.SERVER_TIMESTAMP}, merge=True)
        count += 1
        log.info(f"market_event 저장: {ev['period']}")
    return count


def run(json_path: str) -> None:
    db = _get_db()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_ids = [d.id for d in db.collection("ktoa_mvno_brand_insights").stream()]
    log.info(f"기존 ktoa_mvno_brand_insights 문서: {len(existing_ids)}개")

    matched, unmatched = 0, []

    for profile in data["brands"]:
        keywords = profile["match_keywords"]
        doc_id = find_best_match(existing_ids, keywords)

        if not doc_id:
            unmatched.append(keywords[0])
            continue

        ref = db.collection("ktoa_mvno_brand_insights").document(doc_id)
        ref.set({
            "legal_name": profile.get("legal_name"),
            "biz_reg_no": profile.get("biz_reg_no"),
            "address": profile.get("address"),
            "homepage_url": profile.get("homepage"),
            "ceo": profile.get("ceo"),
            "profile_notes": profile.get("notes"),
            "profile_updated_at": fs.SERVER_TIMESTAMP,
        }, merge=True)
        matched += 1
        log.info(f"매칭: {keywords[0]} -> 문서ID '{doc_id}'")

    # discontinued(사업 종료/매각 이력) - 별도 리스트, 있으면 같은 방식으로 매칭 후
    # discontinued 관련 필드만 추가(다른 profile 필드는 건드리지 않음)
    for item in data.get("discontinued", []):
        keywords = item["match_keywords"]
        doc_id = find_best_match(existing_ids, keywords)

        if not doc_id:
            unmatched.append(f"[종료이력] {keywords[0]}")
            continue

        ref = db.collection("ktoa_mvno_brand_insights").document(doc_id)
        ref.set({
            "discontinued": True,
            "discontinued_period": item.get("period"),
            "discontinued_detail": item.get("detail"),
            "profile_updated_at": fs.SERVER_TIMESTAMP,
        }, merge=True)
        matched += 1
        log.info(f"종료이력 매칭: {keywords[0]} -> 문서ID '{doc_id}'")

    log.info(f"완료: 매칭 {matched}개 / 미매칭 {len(unmatched)}개")
    if unmatched:
        log.warning(f"미매칭 목록(수동 확인 필요): {unmatched}")

    n_events = import_market_events(data)
    if n_events:
        log.info(f"시장 전체 이벤트 저장: {n_events}건")


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "brand_profiles_batch1.json"
    run(path)
