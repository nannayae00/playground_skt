"""
[수정 이력]
2026-06-18 v5.2 - DB 미존재 시 전월 값으로 신규 문서 자동 생성 (Claude)
  - 기존 v5.1: 전월 값을 읽어서 반환만 하고 DB엔 쓰지 않음
  - 변경: 전월 값을 찾으면 해당 월 문서를 DB에 자동 생성(copied_from 필드 포함)
          → 다음 조회 때 바로 찾을 수 있고, Firestore 콘솔에서 직접 수정도 가능
2026-06-18 v5.1 - DB 미존재 시 전월 자동 복사 로직 추가 (읽기만, 쓰기 없음)
2026-06-18 v5.0 - 파일명/Firestore 경로 tout_goal → target_goal 변경 (Claude)
  - 파일명: tout_goal_reader.py → target_goal_reader.py
  - Firestore 경로: ktoa_config/tout_goal → ktoa_config/target_goal
  - tout은 SKT이탈(T-Out) 하나의 지표일 뿐, 파일/DB는 전체 목표 관리용이라 target_goal이 적합
2026-06-18 v4.0 - _HISTORICAL_OVERRIDES 상수 완전 제거, DB 단일 소스 완성 (Claude)
  - update_target_goal.py v3.0이 1~12월 전체를 DB에 생성하므로
    코드 안에 박혀있던 _HISTORICAL_OVERRIDES 딕셔너리 자체가 불필요해짐
  - 조회: Firestore → _FALLBACK(최후 안전망) 2단계로 단순화
  - "목표 수정 = DB만 수정" 완성. 코드 배포 없이 Firestore 콘솔에서 바로 반영.
2026-06-18 v3.x - 1~5월 보관용 _HISTORICAL_OVERRIDES + Firestore + 폴백 3단계 (폐기)
2026-06-18 v2.0 - 키명/방향성 수정
2026-06-18 v1.0 - 최초 작성

목적:
  ktoa_config/target_goal/monthly/{YYYY-MM} 의 다중 지표(goals)를
  ktoa_telegram / ktoa_context_builder / ktoa_context_period_builder /
  forecast_excel / config.py 등이 각자 따로 Firestore 조회하거나 하드코딩하지 않고,
  이 모듈 하나를 통해서만 읽도록 통일하기 위한 공용 헬퍼.

  ★ 월별 목표 변경 방법:
     Firestore 콘솔 → ktoa_config/target_goal/monthly/{YYYY-MM} → goals 필드 수정
     또는 update_target_goal.py 해당 달만 수정 후 재실행. 코드 배포 불필요.
"""

from datetime import datetime
from google.cloud import firestore

PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"

# DB에 문서가 전혀 없는 경우에만 동작하는 최후 안전망
# (update_target_goal.py를 한 번 실행하면 사실상 쓰일 일 없음)
_FALLBACK = {
    "t_out":  {"label": "SKT Out",          "value": 34000, "unit": "건", "direction": "lte"},
    "sm_net": {"label": "SM 순증감",        "value": -5000, "unit": "건", "direction": "gte"},
    "sm_ms":  {"label": "MVNO in M/S(SM)",  "value": 20.0,  "unit": "%",  "direction": "gte"},
}

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    return _db


def _fetch_goals_from_db(yyyymm: str) -> dict | None:
    """DB에서 해당 월 goals dict를 조회. 없으면 None 반환."""
    try:
        doc = (
            _get_db()
            .collection("ktoa_config")
            .document("target_goal")
            .collection("monthly")
            .document(yyyymm)
            .get()
        )
        if doc.exists:
            goals = (doc.to_dict() or {}).get("goals")
            if goals:
                return goals
    except Exception:
        pass
    return None


def get_monthly_goals(yyyymm: str = None) -> dict:
    """
    지정한 월(없으면 이번 달)의 goals dict를 반환.
    조회 순서:
      1) 해당 월 DB 문서
      2) 없으면 전월 → 전전월 (최대 3개월 거슬러 올라감)
         → 찾은 전월 값을 해당 월 DB 문서로 자동 생성 (copied_from 필드 포함)
         → 이후 Firestore 콘솔에서 해당 월 문서 직접 수정 가능
      3) 그래도 없으면 _FALLBACK
    """
    if yyyymm is None:
        yyyymm = datetime.now().strftime("%Y-%m")

    # 1) 해당 월 직접 조회
    goals = _fetch_goals_from_db(yyyymm)
    if goals:
        return goals

    # 2) 전월부터 최대 3개월 거슬러 올라가며 탐색
    year, month = int(yyyymm[:4]), int(yyyymm[5:7])
    for _ in range(3):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        prev_yyyymm = f"{year:04d}-{month:02d}"
        goals = _fetch_goals_from_db(prev_yyyymm)
        if goals:
            # 찾은 전월 값으로 해당 월 문서 자동 생성
            try:
                _get_db().collection("ktoa_config").document("target_goal") \
                    .collection("monthly").document(yyyymm).set(
                        {
                            "goals": goals,
                            "goal": goals.get("t_out", {}).get("value", 34000),
                            "copied_from": prev_yyyymm,
                            "updated_at": datetime.now(),
                        },
                        merge=True,
                    )
                print(f"[target_goal] {yyyymm} 문서 없음 → {prev_yyyymm} 값으로 자동 생성")
            except Exception as e:
                print(f"[target_goal] {yyyymm} 자동 생성 실패 (무시): {e}")
            return goals

    return _FALLBACK


def get_goals_tuple(year: int, month: int) -> tuple:
    """
    (t_out_goal, sm_net_goal, sm_ms_goal) 반환.
    sm_net이 DB에 없는 달은 None 반환.
    기존 GOALS_BY_MONTH.get((year, month), ...) 호출부를 그대로 대체 가능.
    """
    goals = get_monthly_goals(f"{year:04d}-{month:02d}")
    sm_net = goals.get("sm_net")
    return (
        goals.get("t_out", _FALLBACK["t_out"])["value"],
        sm_net["value"] if sm_net else None,
        goals.get("sm_ms", _FALLBACK["sm_ms"])["value"],
    )


def check_goal_status(metric_key: str, actual_value: float, goals: dict) -> str:
    """특정 지표의 실제값과 목표를 비교해 '달성'/'미달성'/'확인불가' 반환."""
    g = goals.get(metric_key)
    if g is None:
        return "확인불가"
    target, direction = g["value"], g["direction"]
    if direction == "gte":
        return "달성" if actual_value >= target else "미달성"
    elif direction == "lte":
        return "달성" if actual_value <= target else "미달성"
    return "확인불가"


def format_goal_line(metric_key: str, actual_value: float, goals: dict) -> str:
    """텔레그램/리포트용 한 줄 포맷. 예: 'SKT Out: 33,500건 (목표 34,000건 이하) → 달성'"""
    g = goals.get(metric_key)
    if g is None:
        return f"{metric_key}: 목표 정보 없음"
    status = check_goal_status(metric_key, actual_value, goals)
    direction_kr = "이상" if g["direction"] == "gte" else "이하"
    return (
        f"{g['label']}: {actual_value:,.0f}{g['unit']} "
        f"(목표 {g['value']:,.0f}{g['unit']} {direction_kr}) → {status}"
    )


def get_monthly_goal_text_block(year: int, month: int) -> str:
    """config.py MONTHLY_GOALS 프롬프트용 한 달치 텍스트 블록 생성."""
    t_out, sm_net, sm_ms = get_goals_tuple(year, month)
    lines = [f"**{year}년 {month}월 목표:**", "Priority"]
    lines.append(f"1) SKT OUT 월누적 {t_out:,}건 이하")
    if sm_net is not None:
        # [수정 20260925, 버그] 기존엔 목표값의 부호로 "이상/이하"를 판단했음
        # (sm_net > 0 → 이상, else 이하). 하지만 sm_net의 실제 direction은 스키마상
        # 항상 'gte'(이상)이고, 목표가 음수(예: -6,000)일 때도 의미는 "-6,000보다
        # 나빠지면 안 됨(이상)"인데 부호만 보고 "이하"로 잘못 표시하고 있었음 -
        # "-6,000건 이하"는 수학적으로 더 나쁜 값(-8,000 등)도 허용한다는 뜻이라
        # 실제 의도와 정반대. format_goal_line()처럼 실제 direction('gte')을
        # 그대로 반영해 항상 "이상"으로 표기.
        lines.append(f"2) MVNO MNP 순증감(SM) {sm_net:+,}건 이상")
    lines.append(f"3) MVNO in M/S {sm_ms:.0f}% 이상")
    return "\n".join(lines) + "\n"


def build_dynamic_goals_text(start_year: int, start_month: int,
                              end_year: int, end_month: int) -> str:
    """start~end 범위의 월별 목표 텍스트를 이어붙여서 반환."""
    blocks = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        blocks.append(get_monthly_goal_text_block(y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return "\n".join(blocks)


def save_monthly_actual(yyyymm: str, t_out: float, sm_net: float, sm_ms: float) -> bool:
    """
    월마감 시점(잔여영업일=0)에 그 달의 최종 실제 누적값을 같은 문서에 기록.
    main.py의 _is_month_end 분기(월마감 엑셀 생성 시점)에서 같이 호출.
    예: save_monthly_actual("2026-06", t_out=33820, sm_net=-4712, sm_ms=20.3)
    """
    try:
        doc_ref = (
            _get_db()
            .collection("ktoa_config")
            .document("target_goal")
            .collection("monthly")
            .document(yyyymm)
        )
        doc_ref.set(
            {
                "actual": {"t_out": t_out, "sm_net": sm_net, "sm_ms": sm_ms},
                "actual_saved_at": datetime.now(),
            },
            merge=True,
        )
        return True
    except Exception:
        return False