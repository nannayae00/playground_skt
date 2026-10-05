"""
[수정 이력]
v1.0 | 2026-06-01 | 6월 bw_manual 후불일별 값 Firestore 업데이트
                     (5월 스크립트 기반 - dry-run, KST, DB명 명시, 변경분만 업데이트)

실행:
  python update_bw_manual_june.py           # 실제 업데이트
  python update_bw_manual_june.py --dry-run # 비교만 (저장 안함)
"""

import sys
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

# ── 2026년 6월 bw_manual 후불일별 확정값 ─────────────────
BW_MANUAL = {
    "2026-06-01": 1.4,   # 월
    "2026-06-02": 1.1,   # 화
    "2026-06-03": 0.6,   # 수
    "2026-06-04": 1.3,   # 목
    "2026-06-05": 1.0,   # 금
    "2026-06-06": 0.6,   # 토 (현충일)
    "2026-06-07": 0.0,   # 일
    "2026-06-08": 1.2,   # 월
    "2026-06-09": 1.0,   # 화
    "2026-06-10": 1.1,   # 수
    "2026-06-11": 1.0,   # 목
    "2026-06-12": 1.0,   # 금
    "2026-06-13": 0.6,   # 토
    "2026-06-14": 0.0,   # 일
    "2026-06-15": 1.2,   # 월
    "2026-06-16": 1.0,   # 화
    "2026-06-17": 1.1,   # 수
    "2026-06-18": 1.0,   # 목
    "2026-06-19": 1.0,   # 금
    "2026-06-20": 0.6,   # 토
    "2026-06-21": 0.0,   # 일
    "2026-06-22": 1.2,   # 월
    "2026-06-23": 1.0,   # 화
    "2026-06-24": 1.1,   # 수
    "2026-06-25": 1.0,   # 목
    "2026-06-26": 1.0,   # 금
    "2026-06-27": 0.6,   # 토
    "2026-06-28": 0.0,   # 일
    "2026-06-29": 1.3,   # 월
    "2026-06-30": 1.3,   # 화
}

DRY_RUN = "--dry-run" in sys.argv


def get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project="mvno-484509", database="mvno-data")


def main():
    mode = "DRY-RUN (저장 안함)" if DRY_RUN else "실제 업데이트"
    print(f"=== 2026년 6월 bw_manual 업데이트 ({mode}) ===\n")

    total = sum(v for v in BW_MANUAL.values())
    non_zero = sum(1 for v in BW_MANUAL.values() if v > 0)
    print(f"신규값 합계: {total:.1f} / 영업일 {non_zero}일 / 휴일 {30-non_zero}일\n")

    db = get_db()

    # DB 기존값 전체 조회
    print("DB 기존값 조회 중...")
    existing = {}
    for date_str in sorted(BW_MANUAL.keys()):
        doc = db.collection("ktoa_daily").document(date_str).get()
        existing[date_str] = doc.to_dict().get("bw_manual") if doc.exists else None

    # 비교 출력
    print(f"\n{'날짜':<12} {'요일':<4} {'기존값':<8} {'신규값':<8} {'상태'}")
    print("-" * 58)

    to_update = []
    for date_str in sorted(BW_MANUAL.keys()):
        new_val = BW_MANUAL[date_str]
        old_val = existing[date_str]
        weekday = ["월","화","수","목","금","토","일"][
            datetime.strptime(date_str, "%Y-%m-%d").weekday()]
        old_str = f"{float(old_val):.1f}" if old_val is not None else "없음"

        if old_val is None:
            status = "⬜ 신규"
            to_update.append(date_str)
        elif abs(float(old_val) - float(new_val)) < 0.001:
            status = "✅ 동일"
        else:
            status = f"🔄 변경 ({old_str}→{new_val:.1f})"
            to_update.append(date_str)

        print(f"{date_str}  {weekday:<4} {old_str:<8} {new_val:<8.1f} {status}")

    print(f"\n변경/신규: {len(to_update)}건 / 동일: {30-len(to_update)}건")

    if not to_update:
        print("변경사항 없음. 종료.")
        return

    if DRY_RUN:
        print("\n※ DRY-RUN: 저장 안됨. 실제 저장하려면 --dry-run 없이 실행")
        return

    # 실제 업데이트
    print(f"\n변경분 {len(to_update)}건 업데이트 중...")
    ok = fail = 0
    for date_str in to_update:
        bw = BW_MANUAL[date_str]
        try:
            db.collection("ktoa_daily").document(date_str).set(
                {"bw_manual": bw, "date": date_str,
                 "bw_manual_updated_at": datetime.now(KST)},
                merge=True,
            )
            print(f"  ✅ {date_str} ({weekday_of(date_str)}) → {bw}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {date_str} 실패: {e}")
            fail += 1

    print(f"\n=== 완료: 성공 {ok}건 / 실패 {fail}건 ===")


def weekday_of(date_str):
    return ["월","화","수","목","금","토","일"][
        datetime.strptime(date_str, "%Y-%m-%d").weekday()]


if __name__ == "__main__":
    main()