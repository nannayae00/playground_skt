"""
bw_compare_and_fix.py
[수정 이력]
v1.0 | 2026-06-01 | bw_manual vs bw_ai 비교 + 6/3 지방선거 공휴일 반영

기능:
  1. bw_manual vs bw_ai_prev 비교 (차이 큰 날 강조)
  2. bw_engine.py _HOLIDAYS에 2026-06-03 추가 안내
  3. 6월 bw_ai_prev 재계산 (선거일 반영)

실행:
  python bw_compare_and_fix.py           # 비교 출력만
  python bw_compare_and_fix.py --fix     # 비교 + 6월 bw_ai_prev 재계산
"""

import sys
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DRY_RUN = '--fix' not in sys.argv

YEAR, MONTH = 2026, 6
THRESHOLD = 0.2   # 차이 강조 기준


def get_db():
    import firebase_admin
    from firebase_admin import credentials
    from google.cloud import firestore as fs
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return fs.Client(project='mvno-484509', database='mvno-data')


def main():
    mode = "재계산 실행" if not DRY_RUN else "비교 출력만 (--fix 없음)"
    print(f"=== bw_manual vs bw_ai 비교 ({mode}) ===\n")

    db = get_db()

    # ── 6월 전체 문서 조회
    rows = []
    for day in range(1, 31):
        ds = f"{YEAR:04d}-{MONTH:02d}-{day:02d}"
        doc = db.collection('ktoa_daily').document(ds).get()
        data = doc.to_dict() if doc.exists else {}

        bw_manual = data.get('bw_manual')
        bw_ai     = data.get('bw_ai_prev')
        bw_perf   = data.get('bw_performance')  # 실적 확정값 (경과일만 존재)

        wd = ["월","화","수","목","금","토","일"][
            datetime.strptime(ds, '%Y-%m-%d').weekday()]

        rows.append({
            'date': ds, 'day': day, 'wd': wd,
            'manual': bw_manual,
            'ai':     bw_ai,
            'perf':   bw_perf,
        })

    # ── 비교 출력
    print(f"{'날짜':<12} {'요':<2} {'manual':<8} {'ai_prev':<8} {'실적':<8} {'차이':<8} {'비고'}")
    print("-" * 72)

    big_diff = []
    for r in rows:
        m = r['manual']
        a = r['ai']
        p = r['perf']

        m_str = f"{m:.2f}" if m is not None else "  - "
        a_str = f"{a:.2f}" if a is not None else "  - "
        p_str = f"{p:.2f}" if p is not None else "  - "

        diff_str = ""
        flag = ""
        if m is not None and a is not None:
            diff = m - a
            diff_str = f"{diff:+.2f}"
            if abs(diff) >= THRESHOLD:
                flag = "⚠️ 차이 큼"
                big_diff.append(r)

        # 선거일 표시
        if r['day'] == 3:
            flag += " 🗳️ 지방선거"

        print(f"{r['date']}  {r['wd']:<2} {m_str:<8} {a_str:<8} {p_str:<8} {diff_str:<8} {flag}")

    # ── 요약
    print(f"\n차이 ≥ {THRESHOLD} 날짜: {len(big_diff)}건")
    if big_diff:
        print("\n[ 차이 큰 날 상세 ]")
        for r in big_diff:
            m, a = r['manual'], r['ai']
            diff = m - a if (m and a) else 0
            direction = "manual이 높음 (AI 과소예측)" if diff > 0 else "AI가 높음 (AI 과대예측)"
            print(f"  {r['date']} ({r['wd']}) manual={m:.2f} ai={a:.2f} 차이={diff:+.2f} → {direction}")

    # ── 6/3 선거일 안내
    print("""
=== 6/3 지방선거 공휴일 반영 방법 ===

[ 현재 상태 ]
  bw_engine.py _HOLIDAYS에 '2026-06-03' 없음
  → AI가 6/3을 일반 평일(월요일)로 예측

[ bw_manual ]
  이미 0.6으로 입력됨 ✅ (운영에는 문제 없음)
  실제 예측은 bw_manual 우선 사용

[ bw_engine.py 수정 필요 내용 ]
  _HOLIDAYS 셋에 '2026-06-03' 추가:

  _HOLIDAYS = {{
      ...기존...
      '2026-06-03',   # ★ 지방선거
      '2026-06-06',   # 현충일 (이미 있음)
      ...
  }}

  → 추가 시 K-NN이 6/3을 '영업 공휴일'로 분류
  → 과거 토요일/영업공휴일 데이터 참고해 ~0.6 예측
  → bw_ai_prev도 정상 예측됨
""")

    if DRY_RUN:
        print("※ bw_ai_prev 재계산은 --fix 옵션으로 실행하세요")
        print("  먼저 bw_engine.py에 2026-06-03 추가 후 실행 권장")
        return

    # ── --fix: 6월 bw_ai_prev 재계산
    print("=== 6월 bw_ai_prev 재계산 시작 ===\n")
    try:
        from bw_engine import calc_bw_ai
    except ImportError:
        print("❌ bw_engine.py import 실패. 같은 디렉토리에 있는지 확인하세요.")
        return

    ok = fail = skip = 0
    for r in rows:
        ds = r['date']
        try:
            new_ai = calc_bw_ai(ds)

            old_ai = r['ai']
            if old_ai is not None and abs(float(old_ai) - new_ai) < 0.001:
                print(f"  ⏭️ {ds} ({r['wd']}) 변화없음 ({new_ai:.3f})")
                skip += 1
                continue

            db.collection('ktoa_daily').document(ds).set({
                'bw_ai_prev': new_ai,
                'date': ds,
                'bw_ai_prev_updated_at': datetime.now(KST),
            }, merge=True)
            change = f"{old_ai:.3f} → {new_ai:.3f}" if old_ai else f"신규 {new_ai:.3f}"
            print(f"  ✅ {ds} ({r['wd']}) {change}"
                  f"{' 🗳️' if r['day'] == 3 else ''}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {ds} 실패: {e}")
            fail += 1

    print(f"\n=== 완료: 업데이트 {ok}건 / 변화없음 {skip}건 / 실패 {fail}건 ===")


if __name__ == '__main__':
    main()