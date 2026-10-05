"""
find_uncovered_operators.py  v1.0
작성일: 2026-08-07

[수정 이력]
v1.0 (2026-08-07): 최초 작성. ktoa_mvno_operator_registry(실제 129개 코드)와
  brand_profiles_merged.json(조사 완료된 56개 사업자의 match_keywords)를
  대조해서 "진짜 조사 안 된 코드"만 정확히 뽑아냄. 회사 대 코드 단위
  혼동(한 회사가 여러 망 코드를 가짐) 문제를 해결하기 위해 만듦.
"""

import json

from ktoa_mvno_period_aggregator import _get_db


def run(profiles_path: str = "brand_profiles_merged.json"):
    db = _get_db()

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    all_keywords = set()
    for b in profiles["brands"]:
        for kw in b["match_keywords"]:
            all_keywords.add(kw.lower())

    covered = []
    uncovered = []

    for doc in db.collection("ktoa_mvno_operator_registry").stream():
        d = doc.to_dict()
        code = d.get("code") or doc.id
        name = d.get("name") or ""

        # name이 조사된 키워드 중 하나를 포함하거나(부분일치) 반대로 포함되면 커버된 것으로 판단
        is_covered = any(kw in name.lower() or name.lower() in kw for kw in all_keywords if kw)

        if is_covered:
            covered.append((code, name))
        else:
            uncovered.append((code, name, d.get("first_in_date"), d.get("network")))

    print(f"전체 registry 코드: {len(covered) + len(uncovered)}개")
    print(f"조사 완료로 매칭됨: {len(covered)}개")
    print(f"미조사(진짜 잔여): {len(uncovered)}개\n")

    print("=== 미조사 코드 목록 (코드 / 이름 / 실적시작일 / 망) ===")
    for code, name, first_in, network in sorted(uncovered, key=lambda x: (x[3] or "", x[0])):
        print(f"{code}\t{name}\t{first_in or '(실적없음)'}\t{network}")


if __name__ == "__main__":
    run()
