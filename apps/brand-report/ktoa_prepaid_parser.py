"""
ktoa_prepaid_parser.py  v1.0
작성일: 2026-10-16

[수정 이력]
v1.0 | 2026-10-16 | 최초 작성
  - KTOA 번호현황 조회 > 선불 등록현황(일별) 표 파싱
  - 표 구조 (팀 엑셀 '선불정보 DB구축 통계' 월 시트와 동일, 2026-10 시트로 검증):
    블록명 행: 총 계 / SKT / KT / LGU+ / 전체_MVNO 합계 / ... / 우들모바일LG(L57)
    분류 행  : 구분 / 소계 / 신규가입 / 번호이동 / 선후불전환 / 예비번호
    지표 행  : 등록 / 해지 / 순수 / Port-In / Port-Out / 순수 / 후→선 / 선→후 / 순수 / 등록 / 해지 / 순수
    데이터행 : 0열=일자, 블록마다 13열(소계 + 지표 12개). "합계"/"점유율" 행은 건너뜀
  - 블록 시작 위치는 지표 행에서 [등록, 해지, ?, Port-In] 패턴으로 찾음 → 사업자가
    늘거나 순서가 바뀌어도 열 번호를 고칠 필요 없음
  - 사이트 다운로드 파일(.xls/.xlsx, HTML 형식 .xls 포함)과 팀 엑셀(.xlsm) 모두 같은
    함수(parse_grid)로 읽어서, 수집값 검증에도 그대로 씀
"""

import re
from io import StringIO
import logging
from datetime import datetime, date

import pandas as pd

log = logging.getLogger(__name__)

# 블록 13열의 순서 (소계 + 지표 12개)
METRICS = [
    "subtotal",                         # 소계 (= 순수 4개 합)
    "new_reg", "new_term", "new_net",   # 신규가입 등록 / 해지 / 순수
    "port_in", "port_out", "port_net",  # 번호이동 Port-In / Port-Out / 순수
    "post_to_pre", "pre_to_post", "conv_net",  # 선후불전환 후→선 / 선→후 / 순수
    "spare_reg", "spare_term", "spare_net",    # 예비번호 등록 / 해지 / 순수
]
BLOCK_WIDTH = len(METRICS)  # 13

TOTAL_KEY = "TOTAL"
MNO_KEYS = {"SKT": "SKT", "KT": "KT", "LGU+": "LGU+"}
CODE_RE = re.compile(r"\(([A-Z]\d{2})\)\s*$")   # 우들모바일LG(L57) → L57


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


def _to_int(val) -> int:
    try:
        s = str(val).replace(",", "").strip()
        if s in ("", "nan", "None", "-", "NaN"):
            return 0
        return int(float(s))
    except Exception:
        return 0


def _to_date_str(v) -> str | None:
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip() if v is not None else ""
    m = re.match(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def block_key(name: str) -> str:
    """블록 이름 → 저장 키. 사업자코드가 있으면 코드, 총계는 TOTAL, 나머지는 이름(공백 제거)."""
    n = _norm(name)
    if n in ("총계",):
        return TOTAL_KEY
    if n in MNO_KEYS:
        return MNO_KEYS[n]
    m = CODE_RE.search(str(name))
    if m:
        return m.group(1)
    return n


def _find_block_starts(row: list) -> list[int]:
    """지표 행에서 각 블록의 시작열(소계 열)을 찾는다."""
    starts = []
    cells = [_norm(c).lower() for c in row]
    for c in range(1, len(cells) - 3):
        if (cells[c].startswith("등록") and cells[c + 1].startswith("해지")
                and cells[c + 3].startswith("port-in")):
            starts.append(c - 1)
    return starts


def _block_name(grid: list[list], header_row: int, start: int) -> str:
    """지표 행 위쪽에서 블록 이름을 찾는다. 병합셀은 맨 왼쪽(소계 열) 칸에 값이 있고,
    블록명 행이 가장 위에 있으므로 위에서부터 첫 값을 쓴다."""
    for r in range(0, header_row):
        row = grid[r]
        if start < len(row):
            n = _norm(row[start])
            if n and n not in ("구분", "소계"):
                return str(row[start]).strip()
    return f"block_{start}"


def parse_grid(grid: list[list]) -> dict:
    """
    2차원 표(list of rows) → {
      "blocks": [{"key", "name", "code", "col"}],
      "days": {"YYYY-MM-DD": {block_key: {metric: int, ...}, ...}},
    }
    """
    header_row = None
    starts: list[int] = []
    for r, row in enumerate(grid[:15]):
        s = _find_block_starts(row)
        if len(s) > len(starts):
            header_row, starts = r, s
    if header_row is None or not starts:
        raise ValueError("지표 행(등록/해지/Port-In)을 찾지 못함 - 표 구조 확인 필요")

    blocks = []
    seen = set()
    for st in starts:
        name = _block_name(grid, header_row, st)
        key = block_key(name)
        if key in seen:  # 이름이 겹치면 열 번호로 구분 (데이터 유실 방지)
            key = f"{key}@{st}"
        seen.add(key)
        m = CODE_RE.search(name)
        blocks.append({"key": key, "name": name, "code": m.group(1) if m else None, "col": st})

    days = {}
    for row in grid[header_row + 1:]:
        if not row:
            continue
        d = _to_date_str(row[0])
        if not d:
            continue  # 합계 / 점유율 / 주석 행
        if all(v is None or str(v).strip() == "" for v in row[1:]):
            continue  # 날짜만 있고 값이 없는 행 (팀 엑셀의 미래 날짜)
        day = {}
        for b in blocks:
            vals = [_to_int(row[b["col"] + i]) if b["col"] + i < len(row) else 0
                    for i in range(BLOCK_WIDTH)]
            day[b["key"]] = dict(zip(METRICS, vals))
        days[d] = day

    log.info(f"선불 등록현황 파싱: 블록 {len(blocks)}개, {len(days)}일치")
    return {"blocks": blocks, "days": days}


def read_grid(file_path: str, sheet=0) -> list[list]:
    """사이트 다운로드 파일을 2차원 리스트로 읽는다. HTML 형식 .xls도 처리."""
    try:
        df = pd.read_excel(file_path, header=None, sheet_name=sheet)
    except Exception as e:
        log.info(f"read_excel 실패({e}) → HTML 표로 재시도")
        raw = open(file_path, "rb").read()
        for enc in ("utf-8", "cp949"):  # 사이트 HTML 엑셀은 charset 표기가 없을 수 있음
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        tables = pd.read_html(StringIO(text), header=None)
        df = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    df = df.astype(object).where(pd.notna(df), None)
    return df.values.tolist()


def parse_prepaid_file(file_path: str, sheet=0) -> dict:
    return parse_grid(read_grid(file_path, sheet))


def check_consistency(parsed: dict) -> list[str]:
    """
    표 자체의 정합성 점검 (저장 전 이상 감지용). 문제 목록을 반환.
      - 순수 = 등록 - 해지 (3개 구분), 소계 = 순수 4개 합
      - 총계 = SKT + KT + LGU+ + 개별 사업자 합 (MVNO 합계·소계 블록 제외)
    """
    issues = []
    pairs = [("new_net", "new_reg", "new_term"), ("port_net", "port_in", "port_out"),
             ("conv_net", "post_to_pre", "pre_to_post"), ("spare_net", "spare_reg", "spare_term")]
    agg_keys = {b["key"] for b in parsed["blocks"] if "합계" in b["name"]}
    for d, day in parsed["days"].items():
        for key, m in day.items():
            for net, a, b in pairs:
                if m[net] != m[a] - m[b]:
                    issues.append(f"{d} {key} {net}={m[net]} ≠ {a}-{b}={m[a] - m[b]}")
            s = m["new_net"] + m["port_net"] + m["conv_net"] + m["spare_net"]
            if m["subtotal"] != s:
                issues.append(f"{d} {key} subtotal={m['subtotal']} ≠ 순수합 {s}")
        if TOTAL_KEY in day:
            for metric in METRICS:
                parts = sum(v[metric] for k, v in day.items() if k != TOTAL_KEY and k not in agg_keys)
                if parts != day[TOTAL_KEY][metric]:
                    issues.append(f"{d} 총계 {metric}={day[TOTAL_KEY][metric]} ≠ 블록합 {parts}")
    return issues
