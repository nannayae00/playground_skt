"""
ktoa_prepaid_report.py  v1.0
작성일: 2026-10-16

[수정 이력]
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


def build_list_message(summary: dict, kind: str, floor: int = LIST_FLOOR, title: str | None = None) -> str:
    k = KINDS[kind]
    title = title or f"📊 선불 {k['label']} 주요 사업자별 실적 ({summary['date']})"
    lines = [title, f"[ {k['cols']} ]"]
    for net, net_key, label in NETS:
        total = summary["networks"].get(net_key, {})
        lines.append(f"\n◎ {label} ({_triple(total, k, '/')})")
        rows = [(b["short"], b[net]) for b in summary["brands"].values()
                if net in b and (b[net].get(k["in"], 0) >= floor or b[net].get(k["out"], 0) >= floor)]
        rows.sort(key=lambda r: (-r[1][k["in"]], -r[1][k["out"]]))
        if not rows:
            lines.append(f"  ({floor:,}건 이상 사업자 없음)")
        for i, (name, m) in enumerate(rows, 1):
            lines.append(f"{i}) {name} : {_triple(m, k, ' / ')}")
    return "\n".join(lines)


def build_ms_message(summaries: dict, target: date, kind: str) -> str:
    k = KINDS[kind]
    field = k["in"]
    date_str = target.isoformat()
    today = summaries[date_str]["brands"]
    recent = [summaries[d]["brands"] for d in summaries if d != date_str]

    lines = [f"📊 선불 {k['label']} 사업자/망별 M/S ({date_str})",
             f"({'신규 등록' if kind == '010' else 'Port-In'} 기준, 비교 값은 M/S 기준 최근 7일 평균 대비 %p 차이)"]
    rows = []
    for name, b in today.items():
        s_today = b.get("S", {}).get(field, 0)
        if s_today < MS_MIN_S:
            continue
        nets = [n for n, _, _ in NETS
                if b.get(n, {}).get(field, 0) or any(r.get(name, {}).get(n, {}).get(field, 0) for r in recent)]
        if len(nets) < 2 or "S" not in nets:
            continue
        today_v = {n: b.get(n, {}).get(field, 0) for n in nets}
        recent_v = {n: sum(r.get(name, {}).get(n, {}).get(field, 0) for r in recent) for n in nets}
        rows.append((b["short"], today_v, recent_v))

    rows.sort(key=lambda r: -sum(r[1].values()))
    if not rows:
        lines.append(f"\n(대상 사업자 없음 - S망 {MS_MIN_S}건 이상 + 2개 망 이상)")
    for name, today_v, recent_v in rows:
        t_sum, r_sum = sum(today_v.values()), sum(recent_v.values())
        lines.append(f"\n◎ {name} : 총 {t_sum:,}건 (100%)")
        for n, v in today_v.items():
            pct = v / t_sum * 100 if t_sum else 0.0
            diff = _signed(pct - recent_v[n] / r_sum * 100, ".1f", "%p") if r_sum else "비교불가"
            lines.append(f"  {n}: {v:,}건 ({pct:.0f}%) : {diff}")
    return "\n".join(lines)


def build_prepaid_reports(target: date, db=None) -> list[str]:
    """메시지 6종(일 실적·M/S·월누적 × 010/MNP). 해당일 summary가 없으면 빈 리스트."""
    db = db or _get_db()
    summaries = load_summaries(db, target)
    if target.isoformat() not in summaries:
        log.warning(f"[{target}] {SUMMARY_COLLECTION} 문서 없음 - 선불 리포트 생략")
        return []
    s = summaries[target.isoformat()]
    month = load_month(db, target)
    mtd = sum_summaries(month, target)
    mtd_floor = LIST_FLOOR * len(month)
    period = f"{target.replace(day=1):%m/%d}~{target:%m/%d}, {len(month)}일"
    msgs = []
    for kind in ("010", "MNP"):
        msgs += [
            build_list_message(s, kind),
            build_ms_message(summaries, target, kind),
            build_list_message(mtd, kind, floor=mtd_floor,
                               title=f"📊 선불 {kind} 월누적 사업자별 실적 ({period})\n(일평균 {LIST_FLOOR}건 이상 사업자)"),
        ]
    return msgs


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
