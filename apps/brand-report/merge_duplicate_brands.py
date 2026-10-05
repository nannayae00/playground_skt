"""
merge_duplicate_brands.py  v1.0
작성일: 2026-08-17

[수정 이력]
v1.0 (2026-08-17): 최초 작성. find_duplicate_brand_names.py로 찾은 중복
  사업자 문서 병합. clean_brand_name()이 원본 브랜드명 표기차이("한패스SKT"
  vs "한패스모바일LG", "세종텔레콤(KT)" vs "세종텔레콤KT")를 다르게
  처리해서 같은 회사가 여러 문서로 쪼개진 걸 하나로 합침(KCT 때와 동일한
  근본원인).

  MERGE_MAP = {병합될 문서(삭제됨): 대상 문서(남음)}
    - "한패스" -> "한패스모바일" (프로필 정보가 이미 한패스모바일 쪽에
      매칭돼 있었음 - import_brand_profiles.py 실행 이력 기준)
    - "세종텔레콤(KT)" -> "세종텔레콤"
    - "세종텔레콤KT" -> "세종텔레콤"

  병합 방식: networks(망별 데이터)는 대상 문서에 없는 망만 원본에서 채워
  넣고(겹치는 망 있으면 경고만 남기고 대상 쪽 유지 - 수동 확인 필요),
  events는 합쳐서 중복 제거, profile류 필드(legal_name 등)는 대상 문서에
  비어있는 것만 원본에서 채움. 병합 끝나면 원본 문서는 삭제.

사용법:
    python3 merge_duplicate_brands.py            # 실제 병합 실행
    python3 merge_duplicate_brands.py --dry-run   # 미리보기만(삭제/쓰기 안 함)
"""

import argparse
import logging

from google.cloud import firestore as fs

from ktoa_mvno_period_aggregator import _get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MERGE_MAP = {
    "한패스": "한패스모바일",
    "세종텔레콤(KT)": "세종텔레콤",
    "세종텔레콤KT": "세종텔레콤",
}


def merge_one(db, source_id: str, target_id: str, dry_run: bool) -> None:
    source_ref = db.collection("ktoa_mvno_brand_insights").document(source_id)
    target_ref = db.collection("ktoa_mvno_brand_insights").document(target_id)

    source_doc = source_ref.get()
    target_doc = target_ref.get()

    if not source_doc.exists:
        log.warning(f"'{source_id}' 문서 없음 - 건너뜀")
        return
    if not target_doc.exists:
        log.warning(f"대상 문서 '{target_id}' 없음 - 건너뜀 (source만 있고 target이 없는 이상 케이스)")
        return

    source = source_doc.to_dict()
    target = target_doc.to_dict()

    # 1) networks 병합 - 대상에 없는 망만 원본에서 채움
    source_nets = source.get("networks", {})
    target_nets = target.get("networks", {})
    for net, data in source_nets.items():
        if net == "UNKNOWN":
            continue  # UNKNOWN은 애초에 의미없는 카테고리라 병합 안 함
        if net in target_nets:
            log.warning(f"[{source_id}->{target_id}] 망 '{net}'이 양쪽에 다 있음 - 대상 값 유지(수동확인 필요)")
        else:
            target_nets[net] = data
            log.info(f"[{source_id}->{target_id}] 망 '{net}' 데이터 이관")

    # 2) events 병합 + 중복 제거
    source_events = source.get("events", [])
    target_events = target.get("events", [])
    seen = {(e.get("period"), e.get("network"), e.get("type"), e.get("detail")) for e in target_events}
    for e in source_events:
        key = (e.get("period"), e.get("network"), e.get("type"), e.get("detail"))
        if key not in seen:
            target_events.append(e)
            seen.add(key)

    # 3) 프로필류 필드 - 대상이 비어있는 것만 원본에서 채움
    for field in ["legal_name", "biz_reg_no", "address", "homepage_url", "ceo", "profile_notes", "category"]:
        if not target.get(field) and source.get(field):
            target[field] = source[field]

    if dry_run:
        log.info(f"[DRY-RUN] '{source_id}' -> '{target_id}' 병합 예정 (실제 반영 안 함)")
        return

    target_ref.set({
        "networks": target_nets,
        "events": sorted(target_events, key=lambda e: e.get("period", "")),
        "legal_name": target.get("legal_name"),
        "biz_reg_no": target.get("biz_reg_no"),
        "address": target.get("address"),
        "homepage_url": target.get("homepage_url"),
        "ceo": target.get("ceo"),
        "profile_notes": target.get("profile_notes"),
        "category": target.get("category"),
        "merged_from": fs.ArrayUnion([source_id]),
        "merge_updated_at": fs.SERVER_TIMESTAMP,
    }, merge=True)

    source_ref.delete()
    log.info(f"완료: '{source_id}' -> '{target_id}' 병합 후 원본 삭제")


def run(dry_run: bool) -> None:
    db = _get_db()
    for source_id, target_id in MERGE_MAP.items():
        merge_one(db, source_id, target_id, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
    print("완료")
