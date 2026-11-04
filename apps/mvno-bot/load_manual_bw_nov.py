"""
load_manual_bw_nov.py
2026년 11월 실무자 영업일수(bw_manual) Firestore 저장

출처: 팀 엑셀 "11월 MVNO 실적 Simulation" 영업일수 행 (일요일은 0)
검증: 주간누적 8.7 / 6.3 / 6.0 / 6.3 / 1.7, 기경과 15.0 / 21.0 / 27.3 / 29.0 과 일치

- bw_manual 필드만 저장합니다. bw_ai_prev는 건드리지 않습니다
  (10월 성장계수 스케일은 2026-10-20에 해제됨).
- 텔레그램 "잔여 영업일수: 실무자기준"(main.py)이 bw_manual을 읽으므로
  저장 즉시 다음 실행부터 반영됩니다(재배포 불필요).

사용:
  GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa.json python3 load_manual_bw_nov.py --dry-run
  GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa.json python3 load_manual_bw_nov.py
"""
import sys
import json
import datetime as dt
from google.cloud import firestore

YEAR, MONTH = 2026, 11
EXPECTED_TOTAL = 29.0

MANUAL_BW = {
    1: 0.0,
    2: 2.0, 3: 1.6, 4: 1.5, 5: 1.4, 6: 1.3, 7: 0.9, 8: 0.0,
    9: 1.3, 10: 1.1, 11: 1.2, 12: 1.0, 13: 1.0, 14: 0.7, 15: 0.0,
    16: 1.2, 17: 1.0, 18: 1.1, 19: 1.0, 20: 1.0, 21: 0.7, 22: 0.0,
    23: 1.2, 24: 1.0, 25: 1.1, 26: 1.0, 27: 1.1, 28: 0.9, 29: 0.0,
    30: 1.7,
}

# 엑셀 주간누적 대조 (시작일, 종료일, 기대값)
WEEK_CHECK = [(1, 7, 8.7), (8, 14, 6.3), (15, 21, 6.0), (22, 28, 6.3), (29, 30, 1.7)]


def main():
    dry = "--dry-run" in sys.argv

    for s, e, exp in WEEK_CHECK:
        got = round(sum(MANUAL_BW[d] for d in range(s, e + 1)), 1)
        assert got == exp, f"{MONTH}/{s}~{MONTH}/{e} 주간누적 {got} != 엑셀 {exp}"
    total = round(sum(MANUAL_BW.values()), 1)
    assert total == EXPECTED_TOTAL, f"월합계 {total} != {EXPECTED_TOTAL}"

    db = firestore.Client(project="mvno-484509", database="mvno-data")
    col = db.collection("ktoa_daily")

    rows, backup = [], {}
    for day, val in sorted(MANUAL_BW.items()):
        ds = f"{YEAR}-{MONTH:02d}-{day:02d}"
        snap = col.document(ds).get()
        d = snap.to_dict() if snap.exists else {}
        backup[ds] = d.get("bw_manual")
        rows.append((ds, val, d.get("bw_ai_prev")))

    bk_path = f"bw_manual_backup_{YEAR}{MONTH:02d}_{dt.datetime.now():%Y%m%d%H%M%S}.json"
    with open(bk_path, "w") as f:
        json.dump(backup, f, ensure_ascii=False, indent=1)
    print(f"기존 bw_manual 백업: {bk_path}")

    print(f"{'날짜':>10} {'요일':>2} {'기존':>6} {'실무자':>6} {'AI':>7}")
    ai_sum = 0.0
    for ds, val, ai in rows:
        wd = "월화수목금토일"[dt.date.fromisoformat(ds).weekday()]
        ai_sum += ai or 0
        old = backup[ds]
        print(f"{ds:>10} {wd:>2} {str(old):>6} {val:>6.1f} {('' if ai is None else f'{ai:.3f}'):>7}")
    print(f"합계: 실무자 {total} / AI {ai_sum:.2f}")

    if dry:
        print("[dry-run] 저장하지 않음")
        return

    batch = db.batch()
    now = dt.datetime.now(dt.timezone.utc)
    for ds, val, _ in rows:
        batch.set(col.document(ds),
                  {"bw_manual": val, "date": ds, "bw_manual_updated_at": now},
                  merge=True)
    batch.commit()
    print(f"bw_manual 저장 완료: {len(rows)}일")


if __name__ == "__main__":
    main()
