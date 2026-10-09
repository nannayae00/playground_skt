"""
[수정 이력]
2026-10-06 v3.2 - 10월 확정 타겟 반영 (36000/-4000/18), DB 동시 수정 (Claude)
2026-06-18 v3.1 - 파일명/경로 tout_goal → target_goal 변경
2026-06-18 v3.0 - 1~5월 포함 1~12월 전체 일괄 생성 (Claude)
  - 1~5월도 DB에 넣어 코드 하드코딩(_HISTORICAL_OVERRIDES) 완전 제거
  - 확정 타겟 반영: 1월(42000/+9000/20), 2월(41000/+1000/20),
    3월(43000/-4000/19), 4월(36000/-6000/18), 5월(33000/-7000/18)
    1월 t_out=42000은 일1,450건 환산 추정 — 정확값 확인되면 DB에서 직접 수정
2026-06-18 v2.0 - 키명 t_out/sm_net/sm_ms로 통일, direction 정정
2026-06-18 v1.0 - 최초 작성 (6~12월만)

★ 특정 달만 수정하고 싶을 때:
   MONTHS_GOALS 딕셔너리에서 해당 달 값만 고치고 TARGET 설정 후 재실행.
   또는 Firestore 콘솔에서 goals 필드를 직접 수정해도 동일 효과 (코드 배포 불필요).
"""

from google.cloud import firestore
from datetime import datetime, timezone

PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"


def _make_goals(t_out: int, sm_net, sm_ms: float) -> dict:
    d = {
        "t_out": {"label": "SKT Out", "value": t_out, "unit": "건", "direction": "lte"},
        "sm_ms": {"label": "MVNO in M/S(SM)", "value": sm_ms, "unit": "%", "direction": "gte"},
    }
    if sm_net is not None:
        d["sm_net"] = {"label": "SM 순증감", "value": sm_net, "unit": "건", "direction": "gte"}
    return d


# 월별 목표 변경 시 이 딕셔너리만 수정 후 재실행
# (YYYY-MM): (t_out_goal, sm_net_goal_or_None, sm_ms_goal)
MONTHS_GOALS = {
    "2026-01": (42000, 9000,  20.0),   # t_out: 일1,450건 환산 추정 — 정확값 확인 필요
    "2026-02": (41000, 1000,  20.0),
    "2026-03": (43000, -4000, 19.0),
    "2026-04": (36000, -6000, 18.0),
    "2026-05": (33000, -7000, 18.0),
    "2026-06": (34000, -5000, 20.0),
    "2026-07": (34000, -5000, 20.0),   # 확정되면 수정
    "2026-08": (34000, -5000, 20.0),
    "2026-09": (34000, -5000, 20.0),
    "2026-10": (36000, -4000, 18.0),   # 2026-10-06 확정
    "2026-11": (34000, -5000, 20.0),
    "2026-12": (34000, -5000, 20.0),
}


def main():
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    col_ref = (
        db.collection("ktoa_config")
        .document("target_goal")
        .collection("monthly")
    )

    for month, (t_out, sm_net, sm_ms) in MONTHS_GOALS.items():
        col_ref.document(month).set(
            {
                "goals": _make_goals(t_out, sm_net, sm_ms),
                "goal": t_out,   # 기존 ktoa_telegram/forecast_engine 호환용
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )
        sm_str = f"{sm_net:+,}" if sm_net is not None else "None"
        print(f"[OK] {month}  t_out={t_out:,}  sm_net={sm_str}  sm_ms={sm_ms}%")

    print(f"\n총 {len(MONTHS_GOALS)}개월 갱신 완료")
    print("→ 이후 목표 수정: Firestore 콘솔에서 직접 (코드 배포 불필요)")


if __name__ == "__main__":
    main()