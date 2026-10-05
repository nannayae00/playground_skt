#!/usr/bin/env python3
"""
backfill_sejong_migration.py  v1.0
작성일: 2026-09-07

[수정 이력]
v1.0 | 2026-09-07 | 최초 작성 (Claude)
  - 8/18~8/31, 9/1~9/4 세종→고고 이관 데이터 1회성 백필
  - 반드시 날짜 오름차순으로 save_sejong_migration() 호출해야
    누적(cum)이 정확히 쌓임 (get_previous_sejong_migration_cum이 직전일 참조)
  - 실행: python3 backfill_sejong_migration.py
  - 실행 전 확인: ktoa_firestore.py가 GOOGLE_APPLICATION_CREDENTIALS 등
    Firestore 인증 환경에서 실행돼야 함 (Cloud Shell 등)
"""

import ktoa_firestore

# (date_str, S망, K망, L망) — L망은 전 기간 데이터 없음 확인되어 0으로 백필
# (실시간 입력부터는 미확인 시 None으로 들어감)
DATA = [
    ('2026-08-18', 0, 0, 0),
    ('2026-08-19', 1, 1, 0),
    ('2026-08-20', 0, 1, 0),
    ('2026-08-21', 3, 0, 0),
    ('2026-08-22', 0, 0, 0),
    ('2026-08-23', 0, 0, 0),
    ('2026-08-24', 0, 0, 0),
    ('2026-08-25', 1, 8, 0),
    ('2026-08-26', 1, 48, 0),
    ('2026-08-27', 0, 157, 0),
    ('2026-08-28', 0, 287, 0),
    ('2026-08-29', 0, 0, 0),
    ('2026-08-30', 0, 0, 0),
    ('2026-08-31', 2, 305, 0),
    # 9월 (월 경계 → cum 자동 리셋됨)
    ('2026-09-01', 0, 269, 0),
    ('2026-09-02', 0, 690, 0),
    ('2026-09-03', 0, 260, 0),
    ('2026-09-04', 0, 500, 0),
]


def main():
    for date_str, sm, km, lm in DATA:
        payload = ktoa_firestore.save_sejong_migration(date_str, sm, km, lm)
        print(f"{date_str}  daily={payload['daily']}  cum={payload['cum']}")

    print("\n백필 완료. 검증:")
    print("  8월 말(8/31) cum 예상: SM=8, KM=807")
    print("  9월 말(9/4)  cum 예상: SM=0, KM=1719")


if __name__ == '__main__':
    main()