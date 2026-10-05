# data_processor.py
# ============================================================
# [수정 이력]
# v1.0 | 2026-05-27 | 최초 작성
#   - Firestore 원시 데이터 → 대시보드 표시용 지표 계산
#   - 실시간 탭 8개 카드 지표 산출
#   - 페이스 게이지 / 월마감 예측 계산
#   - 최근 5영업일 트렌드 테이블 데이터 가공
# ============================================================

from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


# ══════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════

def _safe(d: dict, *keys, default=0):
    """중첩 dict 안전 접근. 마지막 키가 없으면 default 반환"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur if cur is not None else default

def _pct(num, den, ndigits=1) -> Optional[float]:
    try:
        return round(num / den * 100, ndigits)
    except (ZeroDivisionError, TypeError):
        return None

def _delta_str(val, prev, unit="") -> str:
    """전일 대비 변화량 문자열"""
    if val is None or prev is None:
        return "—"
    diff = val - prev
    sign = "▲" if diff > 0 else ("▼" if diff < 0 else "—")
    return f"{sign}{abs(diff):,.1f}{unit}"

def fmt_n(v, ndigits=0) -> str:
    if v is None:
        return "—"
    if ndigits == 0:
        return f"{int(v):,}"
    return f"{v:,.{ndigits}f}"

def fmt_pct(v) -> str:
    return f"{v:.1f}%" if v is not None else "—"


# ══════════════════════════════════════════════════════════
# 실시간 탭 메인 처리
# ══════════════════════════════════════════════════════════

def process_realtime(today: dict, yesterday: Optional[dict], last_week: Optional[dict], is_close: bool) -> dict:
    """
    ktoa_hourly (또는 ktoa_daily) 원시 데이터 → 실시간 탭 전체 지표 dict
    """
    out = {}

    # ── 영업일수 ──────────────────────────────────────────
    bw = _safe(today, "bw_ai_w0") or _safe(today, "bw_manual") or 1
    bw_prev = _safe(today, "bw_ai_prev") or bw
    out["bw"]      = bw
    out["bw_prev"] = bw_prev
    out["bw_manual"] = _safe(today, "bw_manual")
    out["snapshot_hour"] = today.get("_snapshot_hour", datetime.now(KST).hour)

    # ── MNP 시장 규모 ─────────────────────────────────────
    total      = _safe(today, "total")
    total_mno  = _safe(today, "total_mno")
    total_mvno = _safe(today, "total_mvno")
    out["total"]      = total
    out["total_mno"]  = total_mno
    out["total_mvno"] = total_mvno

    # ── SKT OUT (T-Out) ───────────────────────────────────
    mno_out_s  = _safe(today, "mno_out", "S")
    mno_out_계  = _safe(today, "mno_out", "계") or 1
    out["mno_out_s"] = mno_out_s
    out["tout_pct"]  = _pct(mno_out_s, mno_out_계)

    # 전일 T-Out 비율
    if yesterday:
        yd_s = _safe(yesterday, "mno_out", "S")
        yd_계 = _safe(yesterday, "mno_out", "계") or 1
        out["tout_pct_yd"] = _pct(yd_s, yd_계)
    else:
        out["tout_pct_yd"] = None

    # ── SM 신규 MS% ───────────────────────────────────────
    mvno_in_sm = _safe(today, "mvno_in", "SM")
    mvno_in_계  = _safe(today, "mvno_in", "계") or 1
    out["mvno_in_sm"] = mvno_in_sm
    out["mvno_in_계"]  = mvno_in_계
    out["sm_ms_pct"]  = _pct(mvno_in_sm, mvno_in_계)

    # ── SM 해지 MS% ───────────────────────────────────────
    mvno_out_sm = _safe(today, "mvno_out", "SM")
    mvno_out_계  = _safe(today, "mvno_out", "계") or 1
    out["mvno_out_sm"] = mvno_out_sm
    out["mvno_out_계"]  = mvno_out_계
    out["sm_churn_pct"] = _pct(mvno_out_sm, mvno_out_계)

    # ── SM 순증감 ─────────────────────────────────────────
    net_sm = _safe(today, "net_change", "SM")
    out["net_sm"] = net_sm

    # ── MNO Out 전체 ─────────────────────────────────────
    out["mno_out_계"] = _safe(today, "mno_out", "계")

    # ── 군별 순증감 ───────────────────────────────────────
    out["net_s"] = _safe(today, "net_change", "S")
    out["net_k"] = _safe(today, "net_change", "K")
    out["net_l"] = _safe(today, "net_change", "L")
    out["net_mno"] = _safe(today, "net_change", "MNO계")
    out["net_sm"] = _safe(today, "net_change", "SM")
    out["net_km"] = _safe(today, "net_change", "KM")
    out["net_lm"] = _safe(today, "net_change", "LM")
    out["net_계"]  = _safe(today, "net_change", "계")

    # ── MNO In (군별) ─────────────────────────────────────
    out["mno_in_s"] = _safe(today, "mno_in", "S")
    out["mno_in_k"] = _safe(today, "mno_in", "K")
    out["mno_in_l"] = _safe(today, "mno_in", "L")
    out["mno_in_계"] = _safe(today, "mno_in", "계")

    # ── MVNO 신규/해지 군별 ───────────────────────────────
    out["mvno_in_km"] = _safe(today, "mvno_in", "KM")
    out["mvno_in_lm"] = _safe(today, "mvno_in", "LM")
    out["mvno_in_계"]  = mvno_in_계
    out["mvno_out_km"] = _safe(today, "mvno_out", "KM")
    out["mvno_out_lm"] = _safe(today, "mvno_out", "LM")
    out["mvno_out_계"]  = mvno_out_계

    # ── 월 누적 ───────────────────────────────────────────
    out["cum_mvno_in"]  = _safe(today, "cum_mvno_in", "계")
    out["cum_mvno_out"] = _safe(today, "cum_mvno_out", "계")
    out["cum_net_sm"]   = _safe(today, "cum_net", "SM")
    out["cum_net_계"]   = _safe(today, "cum_net", "계")
    out["cum_mno_out_s"]= _safe(today, "cum_mno_out", "S")

    # ── 예측값 ───────────────────────────────────────────
    out["fc_daily"]    = today.get("fc_daily")      # 일마감 예측
    out["fc_low"]      = today.get("fc_low")
    out["fc_mid"]      = today.get("fc_mid")
    out["fc_high"]     = today.get("fc_high")
    out["fc_on_track"] = today.get("fc_on_track")

    # fc_mvno_in, fc_mno_out, fc_mvno_out, fc_net (Low/Mid/High)
    for fc_key in ["fc_mvno_in", "fc_mno_out", "fc_mvno_out", "fc_net"]:
        fc_val = today.get(fc_key, {})
        for sub in ["SM", "KM", "LM", "계", "S", "K", "L"]:
            for level in ["low", "mid", "high"]:
                k = f"{fc_key}_{sub}_{level}"
                v = None
                if isinstance(fc_val, dict):
                    inner = fc_val.get(sub, {})
                    if isinstance(inner, dict):
                        v = inner.get(level)
                out[k] = v

    # ── 페이스 게이지 (장중 전용) ─────────────────────────
    if not is_close and bw and bw_prev:
        # 현재 누적 ÷ 영업일 진행률 × 총 영업일 ≈ 월 예상
        bw_progress = bw_prev / bw if bw else 1
        out["pace_pct"] = round(bw_progress * 100, 1)
    else:
        out["pace_pct"] = None

    # ── 장중/마감 모드 ────────────────────────────────────
    out["is_close"] = is_close

    # ── 날짜/시간 메타 ────────────────────────────────────
    out["date_label"] = datetime.now(KST).strftime("%-m월 %-d일")
    out["doc_id"]     = today.get("_doc_id", "")

    return out


# ══════════════════════════════════════════════════════════
# 트렌드 테이블 (최근 5영업일)
# ══════════════════════════════════════════════════════════

def process_trend_table(daily_list: list[dict]) -> list[dict]:
    """
    ktoa_daily 최근 N건 → 트렌드 테이블 rows
    """
    rows = []
    for d in daily_list:
        mvno_in_sm = _safe(d, "mvno_in", "SM")
        mvno_in_계  = _safe(d, "mvno_in", "계") or 1
        ms_pct     = _pct(mvno_in_sm, mvno_in_계)

        mno_out_s  = _safe(d, "mno_out", "S")
        mno_out_계  = _safe(d, "mno_out", "계") or 1
        tout_pct   = _pct(mno_out_s, mno_out_계)

        net_sm = _safe(d, "net_change", "SM")
        total  = _safe(d, "total")

        doc_id = d.get("_doc_id", "")
        try:
            from datetime import date
            dt = date.fromisoformat(doc_id)
            day_label = ["월","화","수","목","금","토","일"][dt.weekday()]
            date_label = f"{dt.month}/{dt.day}({day_label})"
        except Exception:
            date_label = doc_id

        rows.append({
            "date_label": date_label,
            "doc_id":     doc_id,
            "total":      fmt_n(total),
            "ms_pct":     fmt_pct(ms_pct),
            "ms_cls":     "tg2" if (ms_pct or 0) >= 20 else ("tw2" if (ms_pct or 0) >= 18 else "td2"),
            "tout_pct":   fmt_pct(tout_pct),
            "tout_cls":   "td2" if (tout_pct or 0) >= 60 else ("tw2" if (tout_pct or 0) >= 47.5 else "tg2"),
            "net_sm":     (f"▲{net_sm:,}" if net_sm > 0 else f"▼{abs(net_sm):,}") if net_sm else "—",
            "net_cls":    "tg2" if (net_sm or 0) > 0 else "td2",
        })
    return rows


# ══════════════════════════════════════════════════════════
# 군별 득실 테이블
# ══════════════════════════════════════════════════════════

def process_gain_loss_table(today: dict) -> list[dict]:
    """MNP 시장 군별 득실 테이블"""
    rows = []
    for op_code, op_name, op_cls in [("S", "SKT", "skt"), ("K", "KT", "kt"), ("L", "LGU+", "lgu")]:
        in_val  = _safe(today, "mno_in", op_code)
        out_val = _safe(today, "mno_out_all", op_code)  # MNO 발신 전체
        net_val = _safe(today, "net_change", op_code)
        rows.append({
            "op": op_name, "cls": op_cls,
            "in":  fmt_n(in_val),
            "out": fmt_n(out_val),
            "net": (f"▲{net_val:,}" if (net_val or 0) > 0 else f"▼{abs(net_val or 0):,}"),
            "net_cls": "tg2" if (net_val or 0) > 0 else "td2",
        })
    return rows
