"""
list_zero_performance_operators.py  v1.0
작성일: 2026-08-17

[수정 이력]
v1.0 (2026-08-17): 최초 작성. ktoa_mvno_operator_registry에서 first_in_date가
  None인(=한 번도 실적 IN>0이 없었던) 사업자만 뽑음. 조사한 56개(정성조사
  완료)/종료이력 13개(실제 폐업·매각 확인)와는 다른 세 번째 그룹 - "코드는
  있는데 실적 자체가 한 번도 안 잡힌" 사업자.

사용법:
    python3 list_zero_performance_operators.py
"""

from ktoa_mvno_period_aggregator import _get_db


def run():
    db = _get_db()
    docs = list(db.collection("ktoa_mvno_operator_registry").stream())

    zero_perf = [d.to_dict() for d in docs if not d.to_dict().get("first_in_date")]
    zero_perf.sort(key=lambda x: (x.get("network") or "", x.get("code") or ""))

    print(f"=== 전체 {len(docs)}개 코드 중 실적 0(첫실적 없음) {len(zero_perf)}개 ===\n")
    for op in zero_perf:
        print(f"{op.get('code')}\t{op.get('name')}\t{op.get('network')}\t등록일:{op.get('first_seen_at')}")


if __name__ == "__main__":
    run()