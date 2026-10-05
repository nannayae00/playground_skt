#!/usr/bin/env python3
"""
Context Bundler
QuerySpec에 따라 Firestore 데이터를 수집하고
핵심 데이터 + 참고 컨텍스트를 하나의 번들로 묶어 반환

[수정 이력]
v1.3 | 2026-04-13 | bw(영업일수) 데이터 번들 추가
  - _attach_monthly_goal(): bw_manual, bw_ai_prev, 이번달 누적 bw, 잔여 영업일 계산 추가
  - ContextBundle.monthly_goal에 bw 관련 필드 포함
  - build_context_prompt에서 bw 기반 예측 지침 활용 가능
v1.2 | 2026-04-09 | ktoa_events 연동 추가
  - ContextBundle.events 필드 추가
  - get_relevant_events(): 분석 기준일 ±30일 ktoa_events 조회
  - build(): events 수집 공통 적용 (db 있을 때만)
v1.1 | 2026-04-09 | 순환참조(circular import) 수정
  - _get_record(): 'from main import ktoa_daily_to_record' 제거
  - 상단 import에 'from utils import ktoa_daily_to_record' 추가
v1.0 | 2026-04-09 | 최초 작성
  - 핵심 데이터: 요청 날짜/기간 데이터
  - 참고 데이터: 같은 요일 N주치, 최근 N일, 월 목표, 공휴일 맥락
  - ranking intent: 올해+작년 전체 스캔 후 상위 N개 추출
  - 데이터 없는 날(일요일/공휴일) graceful 처리
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional
from dataclasses import dataclass, field

from ai_intent_parser import QuerySpec, RankingSpec
from utils import ktoa_daily_to_record  # v1.1: circular import 방지용 (main.py 대신)

logger = logging.getLogger(__name__)

# ============================================================
# 번들 구조
# ============================================================

@dataclass
class ContextBundle:
    """Gemini 분석에 넘길 최종 데이터 번들"""

    # 사용자가 실제로 요청한 핵심 데이터
    primary: list = field(default_factory=list)

    # 비교/참고용 데이터
    same_weekday_history: list = field(default_factory=list)   # 같은 요일 N주치
    recent_days: list = field(default_factory=list)            # 최근 N일 흐름
    ranking_results: list = field(default_factory=list)        # ranking 결과

    # 맥락 정보
    monthly_goal: dict = field(default_factory=dict)           # 월 목표
    holiday_context: list = field(default_factory=list)        # 전후 공휴일 정보
    events: list = field(default_factory=list)                 # v1.2: ktoa_events (±30일)
    context_texts: list = field(default_factory=list)          # v1.5: ktoa_context 텍스트 (최근 N일)

    # 메타
    query_description: str = ""
    missing_dates: list = field(default_factory=list)          # 데이터 없는 날짜
    used_fallback: bool = False

    def is_empty(self) -> bool:
        return (
            not self.primary
            and not self.ranking_results
            and not self.recent_days
        )

    def summary(self) -> str:
        return (
            f"primary={len(self.primary)}건 "
            f"weekday_hist={len(self.same_weekday_history)}건 "
            f"recent={len(self.recent_days)}건 "
            f"ranking={len(self.ranking_results)}건 "
            f"events={len(self.events)}건 "
            f"context={len(self.context_texts)}건"
        )


# ============================================================
# Context Bundler
# ============================================================

class ContextBundler:
    """
    QuerySpec → ContextBundle

    all_data: get_from_firestore()로 가져온 전체 레코드 리스트
              (ktoa_daily_to_record 변환 완료 상태)
    db: Firestore client (단일 날짜 직접 조회용 fallback)
    monthly_goals: config.MONTHLY_GOALS dict
    """

    def __init__(self, all_data: list, db=None, monthly_goals: dict = None):
        self.all_data = all_data
        self.db = db
        self.monthly_goals = monthly_goals or {}

        # 날짜 → 레코드 인덱스 (빠른 조회)
        self._date_index: dict = {
            r.get("date"): r
            for r in all_data
            if r.get("date")
        }

    # ----------------------------------------------------------
    # 메인
    # ----------------------------------------------------------

    def build(self, spec: QuerySpec) -> ContextBundle:
        bundle = ContextBundle(
            query_description=spec.description,
            used_fallback=spec.used_fallback,
        )

        if spec.intent == "ranking":
            self._build_ranking(spec, bundle)
        elif spec.intent == "trend":
            self._build_trend(spec, bundle)
        else:
            # query / compare / aggregate
            self._build_primary(spec, bundle)
            self._build_context(spec, bundle)

        # 공통: 월 목표 & 공휴일 맥락 & 이벤트
        if spec.context_include_monthly_goal:
            self._attach_monthly_goal(spec, bundle)
        if spec.context_include_holiday:
            self._attach_holiday_context(spec, bundle)
        if self.db:                                    # v1.2: ktoa_events 조회
            self._attach_events(spec, bundle)
        if self.db:                                    # v1.5: ktoa_context 텍스트 조회
            self._attach_context_texts(spec, bundle)

        logger.info(f"번들 완성: {bundle.summary()}")
        return bundle

    # ----------------------------------------------------------
    # 핵심 데이터 수집
    # ----------------------------------------------------------

    def _build_primary(self, spec: QuerySpec, bundle: ContextBundle):
        """query / compare / aggregate — 요청 날짜/기간 조회"""

        # 1) 명시된 날짜 목록
        for date_str in spec.target_dates:
            record = self._get_record(date_str)
            if record:
                bundle.primary.append(record)
            else:
                bundle.missing_dates.append(date_str)
                logger.info(f"데이터 없는 날짜: {date_str}")

        # 2) 기간 범위
        scope = spec.search_scope
        if scope.start_date and scope.end_date:
            records = self._get_range(scope.start_date, scope.end_date)
            bundle.primary.extend(records)

        # 3) this_year / last_year (날짜 명시 없는 경우)
        if not spec.target_dates and not scope.start_date:
            today = datetime.now().date()
            if scope.this_year:
                records = self._get_range(
                    f"{today.year}-01-01",
                    today.strftime("%Y-%m-%d")
                )
                bundle.primary.extend(records)
            if scope.last_year:
                records = self._get_range(
                    f"{today.year - 1}-01-01",
                    f"{today.year - 1}-12-31"
                )
                bundle.primary.extend(records)

        # 중복 제거 & 날짜순
        bundle.primary = self._dedup_sort(bundle.primary)

    def _build_trend(self, spec: QuerySpec, bundle: ContextBundle):
        """trend — recent_days + (필요시) 작년 동기"""
        today = datetime.now().date()
        days = spec.search_scope.recent_days or 60

        start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        bundle.primary = self._get_range(start, end)

        # 작년 동기도 참고용으로
        if spec.search_scope.last_year:
            ly_start = (today.replace(year=today.year - 1) - timedelta(days=days)).strftime("%Y-%m-%d")
            ly_end = today.replace(year=today.year - 1).strftime("%Y-%m-%d")
            bundle.same_weekday_history = self._get_range(ly_start, ly_end)

    # ----------------------------------------------------------
    # Ranking
    # ----------------------------------------------------------

    def _build_ranking(self, spec: QuerySpec, bundle: ContextBundle):
        """ranking — 올해+작년 전체 스캔 후 상위 N개 추출"""
        today = datetime.now().date()
        candidates = []

        if spec.search_scope.this_year:
            candidates += self._get_range(
                f"{today.year}-01-01",
                today.strftime("%Y-%m-%d")
            )
        if spec.search_scope.last_year:
            candidates += self._get_range(
                f"{today.year - 1}-01-01",
                f"{today.year - 1}-12-31"
            )

        if not spec.ranking:
            spec.ranking = RankingSpec()

        field_path = spec.ranking.field    # e.g. "mno_out.S"
        top_n = spec.ranking.top_n
        order = spec.ranking.order

        def extract_val(record: dict) -> float:
            """중첩 필드 추출 (mno_out.S → record['mno_out']['S'])"""
            parts = field_path.split(".")
            # 최상위 레벨에 직접 있는 경우
            top_key = parts[0]
            sub_key = parts[1] if len(parts) > 1 else None

            # ktoa_daily_to_record 구조: 최상위에 mvno_in, mno_out 등 노출
            val = record.get(top_key)
            if isinstance(val, dict) and sub_key:
                return float(val.get(sub_key, 0) or 0)
            # data 딕셔너리 하위 탐색
            data = record.get("data", {})
            val2 = data.get(top_key)
            if isinstance(val2, dict) and sub_key:
                return float(val2.get(sub_key, 0) or 0)
            return 0.0

        # 영업일 데이터만 (val > 0 인 날)
        valid = [(r, extract_val(r)) for r in candidates if extract_val(r) > 0]
        valid.sort(key=lambda x: x[1], reverse=(order == "desc"))

        top = valid[:top_n]
        bundle.ranking_results = [
            {**r, "_rank_value": v, "_rank_field": field_path}
            for r, v in top
        ]

        # 참고: 전체 후보도 recent에 담아 Gemini가 패턴 분석할 수 있게
        bundle.recent_days = candidates

    # ----------------------------------------------------------
    # 참고 컨텍스트
    # ----------------------------------------------------------

    def _build_context(self, spec: QuerySpec, bundle: ContextBundle):
        """같은 요일 N주치 + 최근 N일"""

        # 기준 날짜들
        ref_dates = []
        for d_str in spec.target_dates:
            try:
                ref_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass
        if not ref_dates and bundle.primary:
            try:
                ref_dates = [datetime.strptime(bundle.primary[-1]["date"], "%Y-%m-%d").date()]
            except Exception:
                pass

        if not ref_dates:
            return

        ref = ref_dates[0]

        # 같은 요일 N주치
        weeks = spec.context_same_weekday_weeks
        for w in range(1, weeks + 1):
            past = ref - timedelta(weeks=w)
            record = self._get_record(past.strftime("%Y-%m-%d"))
            if record:
                bundle.same_weekday_history.append(record)

        # 최근 N일
        recent_n = spec.context_recent_days
        start = (ref - timedelta(days=recent_n)).strftime("%Y-%m-%d")
        end = (ref - timedelta(days=1)).strftime("%Y-%m-%d")
        bundle.recent_days = self._get_range(start, end)

    # ----------------------------------------------------------
    # 월 목표 & 공휴일 맥락
    # ----------------------------------------------------------

    def _attach_monthly_goal(self, spec: QuerySpec, bundle: ContextBundle):
        """월 목표, 현재 누적, 영업일수(bw) 계산 — v1.3: 잔여 영업일수 직접 계산"""
        today = datetime.now().date()
        year = today.year
        month = today.month
        from calendar import monthrange
        last_day = monthrange(year, month)[1]

        # monthly_goals가 문자열인 경우 안전 처리
        goal = None
        if isinstance(self.monthly_goals, dict):
            goal_key = f"{year}-{month:02d}"
            goal = self.monthly_goals.get(goal_key) or self.monthly_goals.get(str(month))

        # 이번달 전체 레코드 (all_data에서)
        this_month_records = sorted(
            [r for r in self.all_data if r.get("date", "").startswith(f"{year}-{month:02d}")],
            key=lambda x: x.get("date", "")
        )

        # ★ 미래 날짜 bw_ai_prev는 Firestore에서 직접 조회
        future_bw_ai = {}
        future_bw_manual = {}
        if self.db:
            try:
                for day in range(today.day + 1, last_day + 1):
                    ds = f"{year:04d}-{month:02d}-{day:02d}"
                    doc = self.db.collection('ktoa_daily').document(ds).get()
                    if doc.exists:
                        d = doc.to_dict()
                        if d.get('bw_ai_prev'):
                            future_bw_ai[ds] = float(d['bw_ai_prev'])
                        if d.get('bw_manual'):
                            future_bw_manual[ds] = float(d['bw_manual'])
            except Exception as e:
                logger.warning(f"미래 bw 조회 실패: {e}")

        # 경과 bw 누적 (실적 있는 날)
        elapsed_bw_manual  = sum(r.get("bw_manual",  0) or 0 for r in this_month_records)
        elapsed_bw_ai      = sum(r.get("bw_ai_prev", 0) or 0 for r in this_month_records)
        elapsed_bw_final   = sum(r.get("bw_final",   0) or 0 for r in this_month_records)

        # ★ 잔여 bw 계산
        # 실무자: 미래 bw_manual 있으면 사용, 없으면 bw_ai_prev로 대체
        remaining_bw_manual = 0.0
        remaining_bw_ai     = 0.0
        for day in range(today.day + 1, last_day + 1):
            ds = f"{year:04d}-{month:02d}-{day:02d}"
            d_obj = datetime.strptime(ds, "%Y-%m-%d").date()
            if d_obj.weekday() == 6:  # 일요일 제외
                continue
            ai_val  = future_bw_ai.get(ds, 0)
            man_val = future_bw_manual.get(ds, ai_val)  # manual 없으면 ai 사용
            remaining_bw_manual += man_val
            remaining_bw_ai     += ai_val

        remaining_bw_manual = round(remaining_bw_manual, 2)
        remaining_bw_ai     = round(remaining_bw_ai, 2)
        elapsed_bw_manual   = round(elapsed_bw_manual, 2)
        elapsed_bw_ai       = round(elapsed_bw_ai, 2)

        # 최신 실적 레코드 (실적 있는 마지막 영업일)
        latest = None
        for r in reversed(this_month_records):
            if (r.get('mno_out') or {}).get('S', 0) > 0 or (r.get('mvno_in') or {}).get('계', 0) > 0:
                latest = r
                break
        if not latest and this_month_records:
            latest = this_month_records[-1]

        # ── bw 기반 일평균 및 월마감 예측 계산
        cum_skt_out = (latest.get("cum_mno_out") or {}).get("S", 0) if latest else 0
        cum_net_sm  = (latest.get("cum_net") or {}).get("SM", 0) if latest else 0
        cum_mvno_in_sm = (latest.get("cum_mvno_in") or {}).get("SM", 0) if latest else 0

        # 일평균: bw 가중 일평균 (누적실적 / 경과bw)
        avg_skt_bw  = round(cum_skt_out / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0
        avg_net_bw  = round(cum_net_sm  / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0
        avg_in_bw   = round(cum_mvno_in_sm / elapsed_bw_ai, 1) if elapsed_bw_ai > 0 else 0

        # bw 기반 월마감 예측 (현재까지 누적 + 잔여bw × 일평균)
        pred_skt_manual = int(cum_skt_out + remaining_bw_manual * avg_skt_bw)
        pred_skt_ai     = int(cum_skt_out + remaining_bw_ai     * avg_skt_bw)
        pred_net_manual = int(cum_net_sm  + remaining_bw_manual * avg_net_bw)
        pred_net_ai     = int(cum_net_sm  + remaining_bw_ai     * avg_net_bw)

        # fc 예측값 (DB 저장값 우선, 없으면 전 영업일 탐색)
        def _get_fc(rec, key, default=0):
            val = rec.get(key, default) if rec else default
            return val if val else default

        _fc_rec = latest  # 최신 레코드에서 우선
        # fc_low가 없거나 0이면 전 영업일 탐색 (최대 7일)
        if not _get_fc(_fc_rec, "fc_low") and self.db:
            try:
                for _prev in this_month_records[-2::-1]:  # 역순으로 탐색
                    if _prev.get("fc_low"):
                        _fc_rec = _prev
                        break
            except Exception:
                pass

        _fc_low  = _get_fc(_fc_rec, "fc_low")
        _fc_mid  = _get_fc(_fc_rec, "fc_mid")
        _fc_high = _get_fc(_fc_rec, "fc_high")
        _fc_on_track = _fc_rec.get("fc_on_track", False) if _fc_rec else False
        _fc_net  = _fc_rec.get("fc_net",  {}) if _fc_rec else {}
        _fc_mvno_in = _fc_rec.get("fc_mvno_in", {}) if _fc_rec else {}
        _fc_mno_out = _fc_rec.get("fc_mno_out", {}) if _fc_rec else {}
        _fc_date = _fc_rec.get("date", "") if _fc_rec else ""

        bundle.monthly_goal = {
            "goal": goal,
            "current_date": today.strftime("%Y-%m-%d"),
            "latest_record_date": latest.get("date") if latest else None,
            "cum_mvno_in":  latest.get("cum_mvno_in")  if latest else None,
            "cum_mno_out":  latest.get("cum_mno_out")  if latest else None,
            "cum_net":      latest.get("cum_net")      if latest else None,
            "cum_mno_in":   latest.get("cum_mno_in")   if latest else None,
            "cum_mno_out_all": latest.get("cum_mno_out_all") if latest else None,
            # ★ 영업일수
            "bw_elapsed_days":     len(this_month_records),
            "elapsed_bw_manual":   elapsed_bw_manual,
            "elapsed_bw_ai":       elapsed_bw_ai,
            "elapsed_bw_final":    round(elapsed_bw_final, 2),
            "remaining_bw_manual": remaining_bw_manual,
            "remaining_bw_ai":     remaining_bw_ai,
            "latest_bw_manual":  latest.get("bw_manual")  if latest else None,
            "latest_bw_ai_prev": latest.get("bw_ai_prev") if latest else None,
            "latest_bw_final":   latest.get("bw_final")   if latest else None,
            # ★ bw 기반 일평균
            "avg_skt_per_bw":  avg_skt_bw,   # T Out 일평균 (bw 가중)
            "avg_net_sm_per_bw": avg_net_bw, # SM 순증감 일평균 (bw 가중)
            "avg_in_sm_per_bw":  avg_in_bw,  # SM 신규 일평균 (bw 가중)
            # ★ bw 기반 월마감 예측 (직접 계산)
            "pred_skt_manual": pred_skt_manual,  # 실무자 bw 기준 T Out 예측
            "pred_skt_ai":     pred_skt_ai,      # AI bw 기준 T Out 예측
            "pred_net_manual": pred_net_manual,  # 실무자 bw 기준 SM 순증감 예측
            "pred_net_ai":     pred_net_ai,      # AI bw 기준 SM 순증감 예측
            # ★ fc 예측값 (DB 저장값, 없으면 전 영업일)
            "fc_low":      _fc_low,
            "fc_mid":      _fc_mid,
            "fc_high":     _fc_high,
            "fc_on_track": _fc_on_track,
            "fc_net":      _fc_net,
            "fc_mvno_in":  _fc_mvno_in,
            "fc_mno_out":  _fc_mno_out,
            "fc_date":     _fc_date,  # fc값 기준 날짜
        }

    def _attach_holiday_context(self, spec: QuerySpec, bundle: ContextBundle):
        """요청 날짜 전후 ±3일 공휴일/주말 맥락"""
        import holidays as _holidays
        kr_hol = _holidays.KR()

        ref_dates = []
        for d_str in spec.target_dates:
            try:
                ref_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass

        for ref in ref_dates:
            context = []
            for delta in range(-3, 4):
                d = ref + timedelta(days=delta)
                is_holiday = d in kr_hol
                is_weekend = d.weekday() >= 5
                context.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "weekday": ["월","화","수","목","금","토","일"][d.weekday()],
                    "is_holiday": is_holiday,
                    "is_weekend": is_weekend,
                    "holiday_name": kr_hol.get(d, ""),
                    "is_working_day": not (is_holiday or is_weekend),
                    "delta": delta,   # -3~+3, 0=요청일
                })
            bundle.holiday_context.extend(context)

    def _attach_events(self, spec: QuerySpec, bundle: ContextBundle):
        """
        v1.2: ktoa_events — 분석 기준일 ±30일 이내 이벤트 조회
        문서 구조: {name, category, carrier, start_date, end_date, impact, memo}
        데이터가 많지 않으므로 전체 스트림 후 기간 필터링
        """
        try:
            today = datetime.now().date()

            # 기준일 결정: target_dates 있으면 그 날짜, 없으면 오늘
            if spec.target_dates:
                try:
                    ref = datetime.strptime(spec.target_dates[0], "%Y-%m-%d").date()
                except ValueError:
                    ref = today
            elif spec.search_scope.start_date:
                try:
                    ref = datetime.strptime(spec.search_scope.start_date, "%Y-%m-%d").date()
                except ValueError:
                    ref = today
            else:
                ref = today

            window_start = ref - timedelta(days=30)
            window_end   = ref + timedelta(days=30)

            docs = self.db.collection("ktoa_events").stream()
            for doc in docs:
                d = doc.to_dict()
                # start_date 또는 end_date가 window 안에 있으면 포함
                s = d.get("start_date", "")
                e = d.get("end_date", s)
                try:
                    s_date = datetime.strptime(s, "%Y-%m-%d").date()
                    e_date = datetime.strptime(e, "%Y-%m-%d").date()
                    # 이벤트 기간이 window와 겹치면 포함
                    if s_date <= window_end and e_date >= window_start:
                        bundle.events.append({
                            "name":       d.get("name", ""),
                            "category":   d.get("category", ""),
                            "carrier":    d.get("carrier", ""),
                            "start_date": s,
                            "end_date":   e,
                            "impact":     d.get("impact", ""),
                            "memo":       d.get("memo", ""),
                        })
                except (ValueError, TypeError):
                    continue

            # 시작일 기준 정렬
            bundle.events.sort(key=lambda x: x.get("start_date", ""))
            logger.info(f"ktoa_events 조회: {len(bundle.events)}건 (기준일: {ref}, ±30일)")

        except Exception as e:
            logger.warning(f"ktoa_events 조회 실패 (분석은 계속): {e}")

    # ----------------------------------------------------------
    # 유틸
    # ----------------------------------------------------------

    def _get_record(self, date_str: str) -> Optional[dict]:
        """단일 날짜 조회 — 캐시 → Firestore 직접 조회 순"""
        record = self._date_index.get(date_str)
        if record:
            return record

        # Firestore 직접 조회 (캐시 미스)
        if self.db:
            try:
                doc = self.db.collection("ktoa_daily").document(date_str).get()
                if doc.exists:
                    r = ktoa_daily_to_record(doc.id, doc.to_dict())
                    # 캐시에 추가
                    self._date_index[date_str] = r
                    return r
                else:
                    logger.info(f"ktoa_daily/{date_str} 문서 없음")
            except Exception as e:
                logger.error(f"Firestore 직접 조회 실패 ({date_str}): {e}")

        return None

    def _get_range(self, start_str: str, end_str: str) -> list:
        """기간 범위 조회"""
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            return []

        result = []
        for r in self.all_data:
            d_str = r.get("date")
            if not d_str:
                continue
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
                if start <= d <= end:
                    result.append(r)
            except ValueError:
                continue

        result.sort(key=lambda x: x.get("date", ""))
        return result

    def _dedup_sort(self, records: list) -> list:
        """중복 제거 후 날짜순 정렬"""
        seen = {}
        for r in records:
            d = r.get("date")
            if d and d not in seen:
                seen[d] = r
        return sorted(seen.values(), key=lambda x: x.get("date", ""))# force Mon May 11 07:01:54 AM UTC 2026

    def _attach_context_texts(self, spec: QuerySpec, bundle: ContextBundle):
        """
        v1.6: ktoa_context + period context 통합 조회
        - 일별: query/trend → 최근 7~30일 일별 context
        - 주차별: 주차 비교 질문 → ktoa_context_week
        - 순기별: 순기 비교 질문 → ktoa_context_decade
        - 월별: 월별 비교 질문 → ktoa_context_month
        """
        try:
            from ktoa_context_builder import get_context_texts
            from datetime import datetime as _dt

            # 기준일 결정
            if spec.target_dates:
                try:
                    ref_date = spec.target_dates[-1]
                    _dt.strptime(ref_date, "%Y-%m-%d")
                except (ValueError, IndexError):
                    ref_date = _dt.now().strftime("%Y-%m-%d")
            elif spec.search_scope and spec.search_scope.end_date:
                ref_date = spec.search_scope.end_date
            else:
                ref_date = _dt.now().strftime("%Y-%m-%d")

            # description에서 period intent 감지
            desc = (spec.description or '').lower()
            period_keywords = {
                'weekly':  ['주차', '주간', '1주', '2주', '주별'],
                'decade':  ['순기', '1순기', '2순기', '3순기', '10일', '20일'],
                'monthly': ['월별', '월간', '전월', '지난달', '4월', '3월', '2월', '1월'],
            }

            period_intent = None
            for ptype, keywords in period_keywords.items():
                if any(kw in desc for kw in keywords):
                    period_intent = ptype
                    break

            # aggregation이 monthly면 월별 context 우선
            if spec.aggregation == 'monthly' and not period_intent:
                period_intent = 'monthly'

            if period_intent:
                try:
                    from ktoa_context_period_builder import get_period_context
                    period_texts = get_period_context(period_intent, ref_date)
                    if period_texts:
                        bundle.context_texts = period_texts
                        logger.info(f"period_context 조회: {period_intent} {ref_date} → {len(period_texts)}건")
                        return
                except Exception as pe:
                    logger.warning(f"period_context 조회 실패 (일별로 폴백): {pe}")

            # 일별 context (기본)
            days_map = {
                "trend":     30,
                "compare":   30,
                "aggregate": 30,
                "query":     7,
                "ranking":   14,
            }
            days = days_map.get(spec.intent, 7)
            bundle.context_texts = get_context_texts(ref_date, days=days)
            logger.info(f"context_texts 조회: {ref_date} 기준 {len(bundle.context_texts)}건 ({days}일)")

        except Exception as e:
            logger.warning(f"_attach_context_texts 실패 (무시): {e}")
            bundle.context_texts = []