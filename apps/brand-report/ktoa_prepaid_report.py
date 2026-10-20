"""
ktoa_prepaid_report.py  v1.0
작성일: 2026-10-16

[수정 이력]
v1.4 | 2026-10-20 | 010·MNP 월누적 실적에도 전월 동기간 비교 추가 (사용자 요청): 망·사업자 줄 아래
                     "└ 전월 IN / OUT / 순증", 신규(IN) 증감률은 ±5% 이상만 표시
v1.3 | 2026-10-20 | 월누적 M/S를 "전월 동기간 → 당월" 비교 형식으로 변경 (사용자 요청):
                     사업자별 총계 건수 증감·증감률, 망별 건수(M/S) 전월 → 당월.
                     M/S 변화(%p)는 ±5%p 이상일 때만 표시 (한 줄이 길어지지 않게)
v1.2 | 2026-10-16 | 메시지 구성 변경 (사용자 요청): 010은 일 실적 / 일 M/S / 월누적 실적 / 월누적 M/S
                     4개, MNP는 실적과 M/S를 합쳐 일 / 월누적 2개 → 총 6개. 월누적 M/S는 전월 동기간 대비.
                     M/S 기준 설명 문구 축약
v1.1 | 2026-10-16 | 월누적 메시지 2종 추가 (사용자 요청) - 010/MNP 각각 M/S 메시지 뒤에 별도 발송.
                     표시 기준은 일평균 30건 이상(월누적 ≥ 30 × 경과일수)
v1.0 | 2026-10-16 | 최초 작성 (사용자 확정 설계, 2026-10-16)
  - ktoa_prepaid_summary로 선불 텔레그램 메시지 4종 생성. mvno-brand-report-job이
    MNP 사업자별 리포트 뒤에 이어서 발송 (run_mvno_brand_job.run_prepaid)
    ① 선불 010 주요 사업자별 실적 [신규/해지/순증감]
    ② 선불 010 사업자/망별 M/S (신규 등록 기준)
    ③ 선불 MNP 주요 사업자별 실적 [IN/OUT/순증감]
    ④ 선불 MNP 사업자/망별 M/S (Port-In 기준)
  - ①③ 표시 기준: 망마다 해당일 등록(IN) 또는 해지(OUT)가 30건 이상인 사업자, 등록(IN) 순
  - ②④ 표시 기준: S망 포함 2개 망 이상에서 영업하고 해당일 S망 건수 10건 이상인 사업자
    (영업 망 = 해당일 또는 최근 7일 중 값이 있었던 망). 비교값은 최근 7일(달력일)
    합계 기준 M/S 대비 %p 차이 - MNP 리포트(ktoa_mvno_report 메시지3)와 같은 방식
  - 메시지 원문은 ktoa_prepaid_context_daily/{YYYY-MM-DD}에 저장 (ktoa_brand_context_daily와 같은 패턴)

사용법:
    python3 ktoa_prepaid_report.py 2026-10-15              # 콘솔 출력만
    python3 ktoa_prepaid_report.py 2026-10-15 --telegram   # 브랜드 리포트 방으로 발송 + context 저장
"""

import argparse
import logging
from datetime import date, timedelta

from ktoa_mvno_firestore import _get_db
from ktoa_prepaid_summary import COLLECTION as SUMMARY_COLLECTION

log = logging.getLogger(__name__)

CONTEXT_COLLECTION = "ktoa_prepaid_context_daily"
NETS = [("S", "SM", "S-MVNO"), ("K", "KM", "K-MVNO"), ("L", "LM", "L-MVNO")]
LIST_FLOOR = 30      # ①③ 사업자 표시 기준
MS_MIN_S = 10        # ②④ S망 최소 건수
MS_LOOKBACK_DAYS = 7

KINDS = {
    "010": {"in": "reg", "out": "term", "net": "net", "label": "010", "cols": "신규/해지/순증감"},
    "MNP": {"in": "pin", "out": "pout", "net": "pnet", "label": "MNP", "cols": "IN/OUT/순증감"},
}


def _signed(v: float, fmt: str = ",.0f", unit: str = "") -> str:
    return f"+{v:{fmt}}{unit}" if v >= 0 else f"▲{abs(v):{fmt}}{unit}"


def _triple(m: dict, k: dict, sep: str) -> str:
    return f"{m.get(k['in'], 0):,}{sep}{m.get(k['out'], 0):,}{sep}{_signed(m.get(k['net'], 0))}"


def load_summaries(db, target: date, days_back: int = MS_LOOKBACK_DAYS) -> dict:
    """{date_str: summary} - target과 그 전 days_back일."""
    out = {}
    for i in range(days_back + 1):
        d = (target - timedelta(days=i)).isoformat()
        doc = db.collection(SUMMARY_COLLECTION).document(d).get()
        if doc.exists:
            out[d] = doc.to_dict()
    return out


def load_month(db, target: date) -> list[dict]:
    """target이 속한 달 1일 ~ target summary 목록."""
    q = (db.collection(SUMMARY_COLLECTION)
         .where("date", ">=", target.replace(day=1).isoformat())
         .where("date", "<=", target.isoformat()))
    return [d.to_dict() for d in q.stream()]


def sum_summaries(summaries: list[dict], target: date) -> dict:
    """여러 날 summary를 합쳐 summary와 같은 모양으로 (월누적용)."""
    def add(a, b):
        return {f: a.get(f, 0) + b.get(f, 0) for f in ("reg", "term", "net", "pin", "pout", "pnet")}
    nets, brands = {}, {}
    for s in summaries:
        for n, m in s["networks"].items():
            nets[n] = add(nets.get(n, {}), m)
        for name, b in s["brands"].items():
            e = brands.setdefault(name, {"short": b["short"]})
            for n in ("S", "K", "L", "total"):
                if n in b:
                    e[n] = add(e.get(n, {}), b[n])
    return {"date": target.isoformat(), "networks": nets, "brands": brands}


def build_list_lines(summary: dict, kind: str, floor: int = LIST_FLOOR, prev: dict | None = None) -> list[str]:
    """
    망별 헤더(합계) + 해당 망에서 IN 또는 OUT이 floor 이상인 사업자 목록.
    prev(전월 동기간 합계)를 주면 각 줄 아래에 "└ 전월 IN / OUT / 순증 (IN 증감률)"을 붙임 (v1.4, 월누적용).
    IN 증감률은 ±5% 이상일 때만 표시.
    """
    k = KINDS[kind]

    def prev_line(cur_m: dict, prev_m: dict | None, indent: str) -> list[str]:
        if prev is None:
            return []
        prev_m = prev_m or {}
        line = f"{indent}└ 전월 {_triple(prev_m, k, ' / ')}"
        p_in, c_in = prev_m.get(k["in"], 0), cur_m.get(k["in"], 0)
        if p_in and abs(c_in - p_in) / p_in * 100 >= MS_DIFF_SHOW:
            line += f" ({'신규' if kind == '010' else 'IN'} {_signed((c_in - p_in) / p_in * 100)}%)"
        return [line]

    lines = [f"[ {k['cols']} ]"]
    for net, net_key, label in NETS:
        total = summary["networks"].get(net_key, {})
        lines.append(f"\n◎ {label} ({_triple(total, k, '/')})")
        lines += prev_line(total, prev["networks"].get(net_key) if prev else None, "  ")
        rows = [(name, b["short"], b[net]) for name, b in summary["brands"].items()
                if net in b and (b[net].get(k["in"], 0) >= floor or b[net].get(k["out"], 0) >= floor)]
        rows.sort(key=lambda r: (-r[2][k["in"]], -r[2][k["out"]]))
        if not rows:
            lines.append(f"  ({floor:,}건 이상 사업자 없음)")
        for i, (name, short, m) in enumerate(rows, 1):
            lines.append(f"{i}) {short} : {_triple(m, k, ' / ')}")
            lines += prev_line(m, prev["brands"].get(name, {}).get(net) if prev else None, "   ")
    return lines


def build_ms_lines(today: dict, compare: list[dict], kind: str, min_s: int = MS_MIN_S) -> list[str]:
    """
    사업자/망별 M/S 본문. today = 대상 기간 brands, compare = 비교 기간 brands 목록(합산해서 M/S 계산).
    대상: S망 min_s건 이상 + S망 포함 2개 망 이상(대상·비교 기간 중 값이 있었던 망).
    """
    field = KINDS[kind]["in"]
    rows = []
    for name, b in today.items():
        if b.get("S", {}).get(field, 0) < min_s:
            continue
        nets = [n for n, _, _ in NETS
                if b.get(n, {}).get(field, 0) or any(c.get(name, {}).get(n, {}).get(field, 0) for c in compare)]
        if len(nets) < 2 or "S" not in nets:
            continue
        today_v = {n: b.get(n, {}).get(field, 0) for n in nets}
        comp_v = {n: sum(c.get(name, {}).get(n, {}).get(field, 0) for c in compare) for n in nets}
        rows.append((b["short"], today_v, comp_v))

    rows.sort(key=lambda r: -sum(r[1].values()))
    lines = []
    if not rows:
        lines.append(f"\n(대상 사업자 없음 - S망 {min_s:,}건 이상 + 2개 망 이상)")
    for name, today_v, comp_v in rows:
        t_sum, c_sum = sum(today_v.values()), sum(comp_v.values())
        lines.append(f"\n◎ {name} : 총 {t_sum:,}건 (100%)")
        for n, v in today_v.items():
            pct = v / t_sum * 100 if t_sum else 0.0
            diff = _signed(pct - comp_v[n] / c_sum * 100, ".1f", "%p") if c_sum else "비교불가"
            lines.append(f"  {n}: {v:,}건 ({pct:.0f}%) : {diff}")
    return lines


MS_DIFF_SHOW = 5.0   # 월누적 M/S 비교에서 %p를 표시하는 최소 변화폭


def build_ms_compare_lines(cur: dict, prev: dict, kind: str, min_s: int) -> list[str]:
    """
    월누적 M/S 비교 본문 (v1.3): 전월 동기간 → 당월.
    대상은 build_ms_lines와 같음 (당월 S망 min_s건 이상 + S망 포함 2개 망 이상).
    """
    field = KINDS[kind]["in"]
    rows = []
    for name, b in cur.items():
        if b.get("S", {}).get(field, 0) < min_s:
            continue
        p = prev.get(name, {})
        nets = [n for n, _, _ in NETS if b.get(n, {}).get(field, 0) or p.get(n, {}).get(field, 0)]
        if len(nets) < 2 or "S" not in nets:
            continue
        rows.append((b["short"], {n: p.get(n, {}).get(field, 0) for n in nets},
                     {n: b.get(n, {}).get(field, 0) for n in nets}))

    rows.sort(key=lambda r: -sum(r[2].values()))
    lines = []
    if not rows:
        lines.append(f"\n(대상 사업자 없음 - S망 {min_s:,}건 이상 + 2개 망 이상)")
    for name, pv, cv in rows:
        p_sum, c_sum = sum(pv.values()), sum(cv.values())
        if p_sum:
            chg = f"{_signed(c_sum - p_sum)}건, {_signed((c_sum - p_sum) / p_sum * 100)}%"
        else:
            chg = "전월 없음"
        lines.append(f"\n◎ {name} : 총 {p_sum:,}건 → {c_sum:,}건 ({chg})")
        for n in pv:
            pp = pv[n] / p_sum * 100 if p_sum else 0.0
            cp = cv[n] / c_sum * 100 if c_sum else 0.0
            line = f"  {n}: {pv[n]:,}건 ({pp:.0f}%) → {cv[n]:,}건 ({cp:.0f}%)"
            if p_sum and abs(cp - pp) >= MS_DIFF_SHOW:
                line += f" : {_signed(cp - pp, '.1f', '%p')}"
            lines.append(line)
    return lines


def _prev_month_same_period(target: date) -> tuple[date, date]:
    """전월 1일 ~ 전월의 target.day일 (전월이 짧으면 말일)."""
    prev_last = target.replace(day=1) - timedelta(days=1)
    return prev_last.replace(day=1), prev_last.replace(day=min(target.day, prev_last.day))


def load_range(db, start: date, end: date) -> list[dict]:
    q = (db.collection(SUMMARY_COLLECTION)
         .where("date", ">=", start.isoformat()).where("date", "<=", end.isoformat()))
    return [d.to_dict() for d in q.stream()]


def build_prepaid_reports(target: date, db=None) -> list[str]:
    """
    메시지 6종 (v1.2, 사용자 확정 구성):
      ① 010 사업자별 실적  ② 010 사업자/망별 M/S  ③ 010 월누적 실적  ④ 010 월누적 망별 M/S
      ⑤ MNP 전일(실적+M/S)  ⑥ MNP 월누적(실적+M/S)
    일 M/S는 최근 7일, 월누적 M/S는 전월 같은 기간 대비 %p. 해당일 summary가 없으면 빈 리스트.
    """
    db = db or _get_db()
    summaries = load_summaries(db, target)
    d = target.isoformat()
    if d not in summaries:
        log.warning(f"[{target}] {SUMMARY_COLLECTION} 문서 없음 - 선불 리포트 생략")
        return []
    day = summaries[d]
    recent = [summaries[x]["brands"] for x in summaries if x != d]

    month = load_month(db, target)
    mtd = sum_summaries(month, target)
    n_days = len(month)
    ps, pe = _prev_month_same_period(target)
    prev = sum_summaries(load_range(db, ps, pe), pe)
    period = f"{target.replace(day=1):%m/%d}~{target:%m/%d}, {n_days}일"
    note_day = "(M/S 기준 최근 7일 평균 대비 %p 차이)"
    note_mtd = f"(전월 동기간 {ps:%m/%d}~{pe:%m/%d} → 당월, M/S 변화는 ±{MS_DIFF_SHOW:.0f}%p 이상만 표시)"
    mtd_floor, mtd_min_s = LIST_FLOOR * n_days, MS_MIN_S * n_days

    def msg(*parts):
        return "\n".join(x for p in parts for x in ([p] if isinstance(p, str) else p))

    return [
        msg(f"📊 선불 010 주요 사업자별 실적 ({d})", build_list_lines(day, "010")),
        msg(f"📊 선불 010 사업자/망별 M/S ({d})", note_day, build_ms_lines(day["brands"], recent, "010")),
        msg(f"📊 선불 010 월누적 사업자별 실적 ({period})", f"(일평균 {LIST_FLOOR}건 이상 사업자)",
            build_list_lines(mtd, "010", mtd_floor, prev)),
        msg(f"📊 선불 010 월누적 망별 M/S ({period})", note_mtd,
            build_ms_compare_lines(mtd["brands"], prev["brands"], "010", mtd_min_s)),
        msg(f"📊 선불 MNP 전일 ({d})", build_list_lines(day, "MNP"),
            "\n[ 사업자/망별 M/S ]", note_day, build_ms_lines(day["brands"], recent, "MNP")),
        msg(f"📊 선불 MNP 월누적 ({period})", f"(일평균 {LIST_FLOOR}건 이상 사업자)",
            build_list_lines(mtd, "MNP", mtd_floor, prev),
            "\n[ 사업자/망별 M/S ]", note_mtd, build_ms_compare_lines(mtd["brands"], prev["brands"], "MNP", mtd_min_s)),
    ]


def save_context(db, target: date, messages: list[str]) -> None:
    from save_brand_context import build_full_text, save_context_text
    d = target.isoformat()
    save_context_text(db, CONTEXT_COLLECTION, d, {"date": d, "text": build_full_text(messages)})


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    p = argparse.ArgumentParser(description="KTOA 선불 사업자별 리포트 (6종)")
    p.add_argument("target_date", help="YYYY-MM-DD")
    p.add_argument("--telegram", action="store_true", help="브랜드 리포트 방으로 발송 + context 저장")
    a = p.parse_args()

    target = date.fromisoformat(a.target_date)
    db = _get_db()
    msgs = build_prepaid_reports(target, db)
    print(("\n\n" + "=" * 50 + "\n\n").join(msgs) or "(summary 없음)")
    if a.telegram and msgs:
        from ktoa_mvno_report import send_telegram
        send_telegram(msgs)
        save_context(db, target, msgs)
        print(f"\n[텔레그램 발송 완료 - {len(msgs)}건]")


if __name__ == "__main__":
    main()
