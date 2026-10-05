"""
ktoa_mvno_parser.py  v1.0
작성일: 2026-07-27

[수정 이력]
v1.0 | 2026-07-27 | 최초 작성
  - "사업자" 기준 조회 엑셀 파싱 (월 단위, 일자별 from-매트릭스)
  - 실측 구조 (2026_07_27_17_57_57.xls, 아이즈비전SKT 기준):
    row0: 코드 헤더 (일자,총계,소계,SKT,KTF,LGT,KCT,SKL,CJM,ONS,S01..S19,K01..K48,L01..L57)
    row1: 사업자명 (SKT,KT,LGU+,KCT,SK텔링크,LG헬로비전KT,세종텔레콤,아이즈비전SKT,유니컴즈SKT,...)
    row2~N: 일자별 데이터 (0열=일자, 1열=총계, 2열=소계, 3열~=from별 유입건수)
    마지막-1행: "합계"
    마지막행: "점유율"
"""

import re
import logging

import pandas as pd

log = logging.getLogger(__name__)


def _to_int(val):
    try:
        s = str(val).replace(",", "").strip()
        if s in ("", "nan", "None", "-", "NaN"):
            return 0
        return int(float(s))
    except Exception:
        return 0


def parse_ktoa_mvno_excel(file_path: str, to_name: str, to_code: str, to_network: str) -> dict:
    """
    반환 구조:
    {
      "to": "아이즈비전SKT",
      "to_code": "S09",
      "to_network": "SKT",
      "days": {
        "2026-07-01": {
          "total_market": 35216,   # 그날 시장 전체 총계
          "total_in": 789,          # 소계 (이 사업자로의 총 유입)
          "flows": {"SKT": 52, "KT": 24, ..., "유니컴즈SKT": 23, ...}
        },
        ...
      }
    }
    """
    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        log.error(f"엑셀 읽기 실패 ({to_name}): {e}")
        raise

    if df.shape[0] < 3:
        raise ValueError(f"엑셀 행 수 비정상 ({to_name}): shape={df.shape}")

    # row0 = 코드, row1 = 사업자명. 두 헤더 행 중 실제 매핑에 쓰는 건 row1(사업자명)
    header_names = df.iloc[1].tolist()

    # from 컬럼은 3번째 컬럼(index 3)부터 시작 (0=일자,1=총계,2=소계)
    from_cols = list(range(3, df.shape[1]))
    from_names = {c: str(header_names[c]).strip() for c in from_cols}

    days = {}
    for i in range(2, df.shape[0]):
        date_cell = str(df.iloc[i, 0]).strip()

        # "합계" / "점유율" 행 등 날짜가 아닌 행은 스킵
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_cell):
            continue

        total_market = _to_int(df.iloc[i, 1])
        total_in = _to_int(df.iloc[i, 2])

        # 실적이 아예 없는 날(휴무일 등)도 문서는 남기되 total_in=0으로 저장
        flows = {}
        for c in from_cols:
            name = from_names[c]
            if not name or name in ("nan", "None"):
                continue
            flows[name] = _to_int(df.iloc[i, c])

        days[date_cell] = {
            "total_market": total_market,
            "total_in": total_in,
            "flows": flows,
        }

    log.info(f"[{to_name}] 파싱 완료: {len(days)}일치")

    return {
        "to": to_name,
        "to_code": to_code,
        "to_network": to_network,
        "days": days,
    }
