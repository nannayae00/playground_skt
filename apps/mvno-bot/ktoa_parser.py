"""
ktoa_parser.py  v2.0
작성일: 2026-03-16

[수정 이력]
v1.0 | 2026-03-16 | 최초 작성
v2.0 | 2026-03-16 | 실제 엑셀 구조 확인 후 파서 전면 재작성
  - 엑셀: 매트릭스 형태 (22행 x 8열)
  - row 1:    기준시각
  - row 3~4:  SKT, row 6~7: KT, row 9~10: LGU+
  - row 13~15: MVNO 3사
  - row 18~19: 순수증감
  - row 21:   합계
"""

import re
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

OPERATOR_MAP = {
    "SKT":       "SKT",
    "KT":        "KT",
    "LGU+":      "LGU",
    "MVNO-SKT":  "MVNO_SKT",
    "MVNO-KT":   "MVNO_KT",
    "MVNO-LGU+": "MVNO_LGU",
}
COL_ORDER = ["SKT", "KT", "LGU", "MVNO_SKT", "MVNO_KT", "MVNO_LGU"]


def _to_int(val) -> Optional[int]:
    try:
        s = str(val).replace(",", "").strip()
        if s in ("", "nan", "None", "-", "NaN"):
            return None
        return int(float(s))
    except Exception:
        return None


def parse_ktoa_excel(file_path: str, collected_at: datetime) -> dict:
    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        log.error(f"엑셀 읽기 실패: {e}")
        raise

    log.info(f"엑셀 shape: {df.shape}")

    result = {
        "date":           collected_at.strftime("%Y-%m-%d"),
        "collected_at":   collected_at,
        "reference_time": "",
        "matrix":         {},
        "net_change":     {},
        "total":          None,
        "mvno_total_in":  None,
    }

    # 기준시각 + 날짜 추출 (row 1)
    ref_cell = str(df.iloc[1, 0]) if len(df) > 1 else ""
    time_match = re.search(r"(\d+시\s*\d+분\s*이전)", ref_cell)
    if time_match:
        result["reference_time"] = time_match.group(1)
    date_match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", ref_cell)
    if date_match:
        y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        result["date"] = f"{y:04d}-{m:02d}-{d:02d}"

    # 매트릭스 파싱
    matrix = {}
    for i in range(len(df)):
        cell = str(df.iloc[i, 0]).strip()
        op_key = OPERATOR_MAP.get(cell)
        if op_key:
            nums = [_to_int(df.iloc[i, c]) for c in range(1, 8)]
            if all(v is None for v in nums) and i + 1 < len(df):
                nums = [_to_int(df.iloc[i+1, c]) for c in range(1, 8)]
            if any(v is not None for v in nums):
                row_data = {key: (nums[j] if nums[j] is not None else 0) for j, key in enumerate(COL_ORDER)}
                row_data["소계"] = nums[6] if nums[6] is not None else 0
                matrix[op_key] = row_data

    result["matrix"] = matrix

    # 순수증감
    for i in range(len(df)):
        if "순수증감" in str(df.iloc[i, 0]):
            if i + 1 < len(df):
                nums = [_to_int(df.iloc[i+1, c]) for c in range(1, 7)]
                result["net_change"] = {key: (nums[j] if nums[j] is not None else 0) for j, key in enumerate(COL_ORDER)}
            break

    # 합계
    for i in range(len(df)):
        if str(df.iloc[i, 0]).strip() == "합계":
            result["total"] = _to_int(df.iloc[i, 1])
            break

    # MVNO 합계
    result["mvno_total_in"] = sum(matrix.get(k, {}).get("소계", 0) for k in ["MVNO_SKT", "MVNO_KT", "MVNO_LGU"])

    log.info(f"파싱 완료 | {result['date']} | {result['reference_time']} | 합계={result['total']} | MVNO IN={result['mvno_total_in']}")
    return result


    