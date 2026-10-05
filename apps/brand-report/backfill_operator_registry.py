"""
backfill_operator_registry.py  v1.1
작성일: 2026-08-07

[수정 이력]
v1.1 (2026-08-18): "이미 registry에 있으면 건드리지 않음(멱등)" 로직 제거.
  원래는 안전장치였는데, 실제로는 2016~2023년 원본 데이터 백필 *이전*에
  1차 시딩(2024-12~현재 범위만)됐던 잘못된 first_in_date 값들이 그대로
  남아있는 문제를 일으켰음(예: SK텔링크/한국이텔레콤/와이드모바일처럼
  실제로는 몇 년 전부터 활동 중이던 사업자가 "최근에 처음 시작"으로
  잘못 기록됨 → 일일 리포트의 "신규사업자" 메시지에 가짜 신규로 계속
  나타나는 오탐 발생). 10년 전체 재스캔 결과로 기존 값도 항상 덮어쓰도록
  변경 - 이제 여러 번 돌려도 최신 스캔 결과로 계속 갱신되는 방식(더 이상
  "1회성 시딩"이 아니라 "재계산 스크립트"에 가까움, 필요시 반복 실행 가능).
v1.0 (2026-08-07): 최초 작성. ktoa_mvno_operator_registry 컬렉션 최초 시딩용
  1회성 스크립트 (ktoa_mvno_firestore.py v2.1의 register_new_operators()/
  check_in_start()와 짝을 이루는 백필 - 이미 활동 중인 기존 사업자들을
  registry에 채워넣어야, 이후 실시간 감지 로직이 "이미 아는 사업자"와
  "진짜 신규"를 구분할 수 있음).

  - first_in_date(실적 시작일): 2024-12-01 ~ 오늘까지 ktoa_mvno_brand_in을
    전부 훑어서 total_in>0이 처음 나온 날짜를 정확히 계산해서 채움(사용자
    요청 - "예전 것도 24년부터 있으니 백필로 시작일은 채울 수 있음").
  - first_seen_at(등록일): 실제 KTOA 등록일은 우리가 추적을 시작하기 전
    이력이라 알 방법이 없음. 데이터 확인 가능한 첫 날짜(=first_in_date와
    동일하거나, IN이 계속 0이었으면 brand_in 문서 자체가 처음 나타난 날)로
    "추정"해서 채우고, is_estimated_first_seen=True로 명시 - 실제 등록일과
    다를 수 있다는 걸 필드로 구분해둠(2026-08-07 이후 신규 감지분은 실시간
    확인이라 False).
  - 이미 활동 중인 사업자이므로 in_start_notified=True로 저장해서, 시딩
    직후 check_in_start()가 "실적 시작"으로 다시 오탐 알림하지 않도록 함.
  - 알림 없음(최초 시딩이므로 조용히 채우기만 함).
  - 이미 registry에 있는 코드는 건드리지 않음(멱등 - 여러 번 실행해도 안전).

실행 환경: Cloud Shell에서 실행 (로컬 샌드박스는 Firestore 접근 불가).
"""

import logging
from datetime import date, timedelta

from google.cloud import firestore as fs

from ktoa_mvno_period_aggregator import _get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def backfill(start: date, end: date) -> int:
    db = _get_db()

    first_seen: dict[str, str] = {}   # code -> 최초로 brand_in 문서에 나타난 날짜(IN 0 포함)
    first_in: dict[str, str] = {}     # code -> total_in>0이 최초로 나온 날짜
    name_map: dict[str, str] = {}
    network_map: dict[str, str] = {}

    d = start
    total_days = (end - start).days + 1
    checked = 0
    while d <= end:
        ds = d.isoformat()
        docs = db.collection("ktoa_mvno_brand_in").where("date", "==", ds).stream()
        for doc in docs:
            data = doc.to_dict()
            code = data.get("brand_code")
            if not code:
                continue

            name_map[code] = data.get("brand")
            network_map[code] = data.get("network")

            if code not in first_seen:
                first_seen[code] = ds

            if (data.get("total_in") or 0) > 0 and code not in first_in:
                first_in[code] = ds

        checked += 1
        if checked % 30 == 0:
            log.info(f"진행: {checked}/{total_days}일 확인, 지금까지 {len(name_map)}개 코드 발견")
        d += timedelta(days=1)

    log.info(f"스캔 완료: 총 {len(name_map)}개 코드")

    batch = db.batch()
    count = 0
    written = 0
    skipped = 0

    for code in name_map:
        ref = db.collection("ktoa_mvno_operator_registry").document(code)
        existed = ref.get().exists
        if existed:
            skipped += 1  # "건너뜀"이 아니라 "덮어쓴 기존 항목" 카운트로 의미 변경(아래 로그 문구도 맞춰 수정)

        payload = {
            "code": code,
            "name": name_map[code],
            "network": network_map.get(code),
            "first_seen_at": first_seen.get(code),
            "is_estimated_first_seen": True,  # 실제 KTOA 등록일 아님 - 데이터상 최초 확인일
            "first_in_date": first_in.get(code),  # 없으면 None(실적 한 번도 없었던 코드)
            "in_start_notified": True,  # 이미 활동 중이므로 실시간 감지 대상 아님
            "updated_at": fs.SERVER_TIMESTAMP,
        }
        batch.set(ref, payload, merge=True)
        count += 1
        if not existed:
            written += 1

        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()

    log.info(f"registry 재계산 완료: 신규 {written}개, 기존 값 재계산해서 덮어씀 {skipped}개")
    return written


if __name__ == "__main__":
    n = backfill(date(2016, 1, 1), date.today())
    print(f"완료: {n}개 사업자 registry 시딩")