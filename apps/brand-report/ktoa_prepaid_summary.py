"""
ktoa_prepaid_summary.py  v1.0
작성일: 2026-10-16

[수정 이력]
v1.0 | 2026-10-16 | 최초 작성
  - ktoa_prepaid_daily(사이트 표 원본)에서 리포트·분석에 필요한 지표만 사업자 단위로
    다시 묶어 ktoa_prepaid_summary/{YYYY-MM-DD}에 저장 (사용자 확정 설계, 2026-10-16)
    {
      "date": "2026-10-15",
      "networks": {"SM"|"KM"|"LM"|"MVNO": {reg, term, net, pin, pout, pnet}},  # 사이트 합계 블록 값
      "brands": {
        "프리텔레콤": {"short": "프리텔",
                      "S": {"code": "S09", reg, term, net, pin, pout, pnet},
                      "K": {...}, "L": {...}, "total": {...}},
      },
      "check": {"SM": true, "KM": true, "LM": true},   # 사업자 합 = 망 합계 블록 여부
    }
  - 선후불전환·예비번호는 저장하지 않음 (원본 ktoa_prepaid_daily에는 남아 있음)
  - 사업자 묶음: 코드 앞글자(S/K/L)로 망을 정하고, 이름에서 망 접미사·(재판매)·(미사용)을
    떼서 같은 이름끼리 묶음 (MNP 리포트 clean_brand_name과 같은 규칙 + 선불 전용 별칭)
  - 값이 모두 0인 망·사업자는 저장하지 않음. 폐업_ 사업자도 값이 있으면 그대로 저장

사용법:
    python3 ktoa_prepaid_summary.py 2026-10-01 2026-10-15   # 원본에서 summary 다시 만들기
"""

import re
import sys
import logging

from google.cloud import firestore as fs

from ktoa_mvno_firestore import _get_db

log = logging.getLogger(__name__)

RAW_COLLECTION = "ktoa_prepaid_daily"
COLLECTION = "ktoa_prepaid_summary"

FIELDS = {  # summary 키 ← 원본 지표 키
    "reg": "new_reg", "term": "new_term", "net": "new_net",
    "pin": "port_in", "pout": "port_out", "pnet": "port_net",
}
NETWORK_BLOCKS = {"SM": "SKT_MVNO합계", "KM": "KT_MVNO합계", "LM": "LGU+_MVNO합계", "MVNO": "전체_MVNO합계"}
PREFIX_TO_NET = {"S": "SM", "K": "KM", "L": "LM"}

# 코드 없는 사업자 블록의 망 (ktoa_mvno_operator_registry: KCT=SKT, LG헬로비전KT=KT, 세종텔레콤(KT)=KT)
UNCODED_NETWORK = {"KCT": "S", "LG헬로비전KT": "K", "세종": "K"}

NAME_SUFFIX = re.compile(r"(\(SKT\)|\(KT\)|\(LGU\+\)|\(LG\)|SKT|KT|LGU\+|LG|\(재판매\)|\(미사용\))$")
CODE_SUFFIX = re.compile(r"\([A-Z]\d{2}\)$")
# 이름이 망마다 다른 같은 사업자 → 대표 이름
ALIASES = {
    "프리티": "프리텔레콤", "한패스": "한패스모바일", "친구아이엔씨": "친구아이앤씨",
    "세종": "세종텔레콤", "LG헬로비전": "LG헬로비전",
}
SHORT_NAMES = {
    "에넥스텔레콤": "에넥스", "프리텔레콤": "프리텔", "스테이지파이브": "스테이지",
    "큰사람커넥트": "큰사람", "KT엠모바일": "KT엠", "KT스카이라이프": "스카이라이프",
    "더원플랫폼": "더원", "코드모바일": "코드", "LG헬로비전": "헬로비전",
    "토스모바일": "토스", "시월텔레콤": "시월", "미디어로그": "미디어",
    "고고팩토리": "고고", "KB국민은행": "KB", "아이즈비전": "아이즈",
    "SK텔링크": "텔링크", "ACN코리아": "ACN", "CK커뮤스트리": "CK",
    "KDDI코리아": "KDDI", "KG모바일": "KG", "MTT텔레콤": "MTT",
    "니즈텔레콤": "니즈", "세종텔레콤": "세종", "스피츠모바일": "스피츠",
    "씨엔커뮤니케이션": "씨엔", "아이디스파워텔": "아이디스", "앤알커뮤니케이션": "앤알",
    "엔티온텔레콤": "엔티온", "오파스넷": "오파스", "와이드모바일": "와이드",
    "우들모바일": "우들", "원텔레콤": "원텔", "인스코리아": "인스",
    "장성모바일한국": "장성", "제주방송": "제주", "찬스모바일": "찬스",
    "친구아이앤씨": "친구", "파인디지털": "파인", "한국이텔레콤": "한국이",
    "한패스모바일": "한패스", "화인통신": "화인", "마블프로듀스": "마블",
    "서경방송": "서경", "한국피엠오": "피엠오", "위너스텔": "위너스",
}


def brand_of(block_key: str, block: dict) -> tuple[str, str] | None:
    """원본 블록 → (망 S/K/L, 대표 사업자명). 사업자 블록이 아니면 None."""
    code = block.get("code")
    if code:
        if code.endswith("00"):          # S00 등 번호부 블록
            return None
        net = code[0]
    elif block_key in UNCODED_NETWORK:
        net = UNCODED_NETWORK[block_key]
    else:
        return None
    name = CODE_SUFFIX.sub("", block.get("name") or block_key).strip()
    prev = None
    while prev != name:                  # "세종텔레콤KT(미사용)"처럼 접미사가 겹친 경우
        prev, name = name, NAME_SUFFIX.sub("", name).strip()
    return net, ALIASES.get(name, name)


def _metrics(block: dict) -> dict:
    return {k: int(block.get(src) or 0) for k, src in FIELDS.items()}


def _add(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in FIELDS}


def build_summary(raw: dict) -> dict:
    """ktoa_prepaid_daily 문서 하나 → summary 문서."""
    blocks = raw["blocks"]
    networks = {n: _metrics(blocks[k]) for n, k in NETWORK_BLOCKS.items() if k in blocks}

    brands, net_sums = {}, {n: {} for n in PREFIX_TO_NET.values()}
    for key in raw.get("block_order") or blocks:
        b = blocks.get(key)
        hit = b and brand_of(key, b)
        if not hit:
            continue
        net, name = hit
        m = _metrics(b)
        net_sums[PREFIX_TO_NET[net]] = _add(net_sums[PREFIX_TO_NET[net]], m)
        if not any(m.values()):
            continue
        entry = brands.setdefault(name, {"short": SHORT_NAMES.get(name, name)})
        if net in entry:                 # 같은 망에 같은 이름 블록이 둘 (드묾) → 합산
            codes = entry[net]["code"] + "," + (b.get("code") or key)
            entry[net] = {"code": codes, **_add(entry[net], m)}
        else:
            entry[net] = {"code": b.get("code") or key, **m}
        entry["total"] = _add(entry.get("total", {}), m)

    check = {n: networks.get(n) == net_sums[n] for n in PREFIX_TO_NET.values() if n in networks}
    bad = [n for n, ok in check.items() if not ok]
    if bad:
        log.warning(f"[{raw['date']}] 사업자 합 ≠ 망 합계: "
                    + ", ".join(f"{n} 합계={networks[n]} 사업자합={net_sums[n]}" for n in bad))
    return {"date": raw["date"], "networks": networks, "brands": brands, "check": check}


def save_summaries(dates: list[str], db=None) -> int:
    """원본 문서에서 summary를 만들어 저장 (같은 날짜는 통째로 덮어씀)."""
    db = db or _get_db()
    n = 0
    batch = db.batch()
    for d in dates:
        raw = db.collection(RAW_COLLECTION).document(d).get()
        if not raw.exists:
            log.warning(f"[{d}] 원본 없음 - summary 건너뜀")
            continue
        s = build_summary(raw.to_dict())
        s["built_at"] = fs.SERVER_TIMESTAMP
        batch.set(db.collection(COLLECTION).document(d), s)
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    log.info(f"{COLLECTION} 저장 완료: {n}건")
    return n


if __name__ == "__main__":
    from datetime import date, timedelta
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    s, e = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
    save_summaries([(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)])
