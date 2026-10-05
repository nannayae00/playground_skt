"""
[수정 이력]
- v1.0 (2026-07-29): 최초 작성. mnp_260727.xlsx의 'Raw_당월' 시트(5~7월,
  147,198행 flow 데이터)를 이용해 5월/6월분만 ktoa_mvno_brand_in에 백필.
  7월은 이미 정상 수집되어 있어 대상에서 제외. brand_in을 채운 뒤
  ktoa_mvno_firestore.build_brand_out(ym)을 그대로 호출해 brand_out도
  같은 로직으로 파생 생성(직접 계산하지 않음 - 기존 함수 재사용).

엑셀 컬럼: Date, MNP사업자명_원본, 전사업자명_원본, 건수, MNP사업자_Code,
  MNP사업자_Name, MNP사업자_MVNO, MNP사업자_NW, MNP사업자_Type,
  전사업자_Code, 전사업자_Name, 전사업자_MVNO, 전사업자_NW, 전사업자_Type

MNP사업자_NW 실측값(KMVNO/LMVNO/SMVNO/SKT/KT/LGU+)과 Firestore 실제
network 필드값(KT/LGU/SKT, Cloud Shell 실측 확인)이 달라 변환 필요:
  SMVNO -> SKT, KMVNO -> KT, LMVNO -> LGU, LGU+(원조) -> LGU,
  SKT(원조) -> SKT, KT(원조) -> KT

실행 환경: 로컬에서는 Firestore 접근 불가. Cloud Shell
  (~/mvno-bot-cloudrun/mvno-bot-cloudrun/brand-report)에 엑셀 파일과
  함께 올려서 실행할 것.

사용법:
    python3 backfill_may_june.py /path/to/mnp_260727.xlsx
"""

import sys
import logging
from collections import defaultdict
from datetime import datetime

import openpyxl
from google.cloud import firestore

from ktoa_mvno_firestore import build_brand_out  # 기존 함수 재사용 (OUT은 직접 계산하지 않음)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
TARGET_MONTHS = {"2026-05", "2026-06"}  # 7월은 이미 수집됨 - 백필 대상 아님

# 엑셀 MNP사업자_NW/전사업자_NW 값 -> Firestore 실제 network 필드값 변환
NETWORK_MAP = {
    "SMVNO": "SKT", "KMVNO": "KT", "LMVNO": "LGU",
    "SKT": "SKT", "KT": "KT", "LGU+": "LGU",
}


def read_excel_flows(xlsx_path: str) -> dict:
    """
    엑셀을 읽어 {date_str: {to_brand: {"network": str, "code": str, "flows": {from_brand: count}}}}
    형태로 집계. TARGET_MONTHS에 속하는 날짜만 포함.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Raw_당월"]

    # date_str -> to_brand -> {"network":.., "code":.., "flows": {from_brand: count}}
    data: dict[str, dict[str, dict]] = defaultdict(dict)

    row_count = 0
    skipped_month = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        date_val = row[0]
        if date_val is None:
            continue
        if not isinstance(date_val, datetime):
            continue
        date_str = date_val.strftime("%Y-%m-%d")
        ym = date_val.strftime("%Y-%m")
        if ym not in TARGET_MONTHS:
            skipped_month += 1
            continue

        to_brand = row[1]         # MNP사업자명_원본
        from_brand = row[2]       # 전사업자명_원본
        count = row[3]            # 건수
        to_code = row[4]          # MNP사업자_Code
        to_nw_raw = row[7]        # MNP사업자_NW
        to_network = NETWORK_MAP.get(to_nw_raw)

        if to_network is None:
            log.warning(f"알 수 없는 network 값 스킵: {to_nw_raw} (brand={to_brand}, date={date_str})")
            continue
        if count is None:
            continue

        bucket = data[date_str].setdefault(
            to_brand, {"network": to_network, "code": to_code, "flows": {}}
        )
        bucket["flows"][from_brand] = bucket["flows"].get(from_brand, 0) + count
        row_count += 1

    log.info(f"읽은 행: {row_count}건 (대상월 외 스킵: {skipped_month}건), 대상 날짜 수: {len(data)}")
    return data


def write_brand_in(db, data: dict) -> None:
    """
    read_excel_flows() 결과를 ktoa_mvno_brand_in/{date}_{brand} 문서로 저장.
    기존 문서가 있으면 merge=True로 덮어쓴다(사용자 확정).
    reference_total은 그날 모든 MNP사업자 total_in 합산(사용자 확정).
    """
    total_written = 0

    for date_str, brands in data.items():
        # reference_total: 그날 전체 MNP사업자 total_in 합산
        day_total = sum(sum(b["flows"].values()) for b in brands.values())

        batch = db.batch()
        batch_count = 0

        for to_brand, info in brands.items():
            total_in = sum(info["flows"].values())
            doc_id = f"{date_str}_{to_brand}"
            ref = db.collection("ktoa_mvno_brand_in").document(doc_id)
            payload = {
                "date": date_str,
                "brand": to_brand,
                "brand_code": info["code"],
                "network": info["network"],
                "total_in": total_in,
                "reference_total": day_total,
                "inflows": info["flows"],
                "collected_at": firestore.SERVER_TIMESTAMP,
                "backfilled": True,  # 백필로 생성된 문서임을 표시 (구분 목적)
            }
            batch.set(ref, payload, merge=True)
            batch_count += 1
            total_written += 1

            if batch_count >= 450:  # Firestore batch 한도(500) 여유있게
                batch.commit()
                batch = db.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()

        log.info(f"{date_str}: {len(brands)}개 브랜드 저장 완료")

    log.info(f"brand_in 총 저장 문서 수: {total_written}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 backfill_may_june.py /path/to/mnp_260727.xlsx")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    log.info(f"엑셀 읽기 시작: {xlsx_path}")
    data = read_excel_flows(xlsx_path)

    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

    log.info("brand_in 백필 시작")
    write_brand_in(db, data)

    for ym in sorted(TARGET_MONTHS):
        log.info(f"brand_out 파생 생성 시작: {ym}")
        build_brand_out(ym)  # 기존 함수 재사용 - brand_in의 inflows를 transpose

    log.info("=== 백필 완료 ===")


if __name__ == "__main__":
    main()