#!/usr/bin/env python3
"""
데이터 집계기 (Data Aggregator)
aggregate intent(순기별/주차별/월별) 전용으로 유지
query/compare/trend/ranking은 ContextBundler가 담당

[수정 이력]
v1.2 | 2026-04-09 | 순환참조(circular import) 수정
  - _filter_by_periods(): 'from main import ktoa_daily_to_record' 제거
  - 상단 import에 'from utils import ktoa_daily_to_record' 추가
v1.1 | 2026-04-09 | 버그픽스 반영
  - _get_ym(): year/month/day 필드 없을 때 date 필드에서 fallback 추출
  - _compute_10day_periods(): "elif 21 <= 31:" → "elif day >= 21:" 버그 수정
  - _filter_by_periods(): 단일 날짜 Firestore 직접 조회 fallback 추가
v1.0 | ~2026-04-06 | 초기 버전
"""

from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import calendar

from query_parser import QueryIntent, Period
from utils import ktoa_daily_to_record  # v1.2: circular import 방지용 (main.py 대신)


@dataclass
class AggregatedData:
    records: List[Dict[str, Any]]
    aggregation: str
    periods: List[Period]
    description: str

    def __repr__(self):
        return f"AggregatedData({self.aggregation}, {len(self.records)}건, {self.description})"


class DataAggregator:

    def __init__(self, all_data: List[Dict[str, Any]], db=None):
        self.all_data = all_data
        self.db = db
        self._date_index = {r.get("date"): r for r in all_data if r.get("date")}

    def aggregate(self, intent: QueryIntent) -> AggregatedData:
        filtered = self._filter_by_periods(intent.periods)

        if not filtered:
            return AggregatedData([], intent.aggregation, intent.periods, "데이터 없음")

        dispatch = {
            "daily":   self._aggregate_daily,
            "10day":   self._aggregate_10day,
            "weekly":  self._aggregate_weekly,
            "monthly": self._aggregate_monthly,
            "yearly":  self._aggregate_yearly,
        }
        fn = dispatch.get(intent.aggregation, self._aggregate_daily)
        return fn(filtered, intent)

    # ──────────────────────────────────────────────
    # 필터링
    # ──────────────────────────────────────────────

    def _filter_by_periods(self, periods: List[Period]) -> List[Dict]:
        filtered = []

        for period in periods:
            if period.start_date == period.end_date:
                # ★ 단일 날짜: 직접 조회 우선
                date_str = period.start_date.strftime("%Y-%m-%d")
                record = self._date_index.get(date_str)

                if not record and self.db:
                    try:
                        doc = self.db.collection("ktoa_daily").document(date_str).get()
                        if doc.exists:
                            record = ktoa_daily_to_record(doc.id, doc.to_dict())
                            self._date_index[date_str] = record
                    except Exception as e:
                        print(f"❌ Firestore 직접 조회 실패 ({date_str}): {e}")

                if record:
                    r = record.copy()
                    r["_period_desc"] = period.description
                    filtered.append(r)
            else:
                for record in self.all_data:
                    d_str = record.get("date")
                    if not d_str:
                        continue
                    try:
                        d = datetime.strptime(d_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if period.start_date <= d <= period.end_date:
                        r = record.copy()
                        r["_period_desc"] = period.description
                        filtered.append(r)

        filtered.sort(key=lambda x: x.get("date", ""))
        return filtered

    # ──────────────────────────────────────────────
    # 집계
    # ──────────────────────────────────────────────

    def _aggregate_daily(self, data: List[Dict], intent: QueryIntent) -> AggregatedData:
        desc = f"{intent.periods[0].description} 일별" if len(intent.periods) == 1 else "복수 기간 일별"
        return AggregatedData(data, "daily", intent.periods, desc)

    def _get_ym(self, record: Dict):
        """★ year/month/day 필드 없으면 date 필드에서 추출"""
        y = record.get("year")
        m = record.get("month")
        d = record.get("day")
        if not all([y, m, d]):
            date_str = record.get("date", "")
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    y, m, d = dt.year, dt.month, dt.day
                except ValueError:
                    pass
        return y, m, d

    def _aggregate_10day(self, data: List[Dict], intent: QueryIntent) -> AggregatedData:
        all_periods = []
        for period in intent.periods:
            y, mn = period.start_date.year, period.start_date.month
            monthly = [r for r in data if (lambda a,b,c: a==y and b==mn)(*self._get_ym(r))]
            if monthly:
                all_periods.extend(self._compute_10day_periods(monthly, y, mn))

        desc = f"{intent.periods[0].description} 순기별" if len(intent.periods) == 1 else "복수 기간 순기별"
        return AggregatedData(all_periods, "10day", intent.periods, desc)

    def _compute_10day_periods(self, monthly_data: List[Dict], year: int, month: int) -> List[Dict]:
        day10 = day20 = day_last = None

        for record in monthly_data:
            _, _, day = self._get_ym(record)
            if day is None:
                continue
            if 1 <= day <= 10:
                if not day10 or day > self._get_ym(day10)[2]:
                    day10 = record
            elif 11 <= day <= 20:
                if not day20 or day > self._get_ym(day20)[2]:
                    day20 = record
            elif day >= 21:    # ★ 버그픽스: "elif 21 <= 31:" → "elif day >= 21:"
                if not day_last or day > self._get_ym(day_last)[2]:
                    day_last = record

        def get_day(r): return self._get_ym(r)[2]

        def sub_cumulative(target: Dict, base: Dict) -> Dict:
            """target 누적 - base 누적"""
            result = target.copy()
            td, bd = target.get("data", {}), base.get("data", {})
            new_data = {}
            for key, val in td.items():
                if key.startswith("누적_") and key in bd:
                    bv = bd[key]
                    if isinstance(val, dict):
                        new_data[key] = {k: v - bv.get(k, 0) for k, v in val.items()}
                    else:
                        new_data[key] = val - bv
                else:
                    new_data[key] = val
            result["data"] = new_data
            return result

        result = []
        if day10:
            p1 = day10.copy()
            p1.update({"period_name": f"1순기 (1~{get_day(day10)}일)",
                        "period_type": "10day",
                        "display_date": f"{year}-{month:02d}-{get_day(day10):02d}"})
            result.append(p1)

        if day20 and day10:
            p2 = sub_cumulative(day20, day10)
            p2.update({"period_name": f"2순기 ({get_day(day10)+1}~{get_day(day20)}일)",
                        "period_type": "10day",
                        "display_date": f"{year}-{month:02d}-{get_day(day20):02d}"})
            result.append(p2)

        if day_last:
            base = day20 if day20 else day10
            if base:
                p3 = sub_cumulative(day_last, base)
                label = f"3순기 ({get_day(base)+1}~{get_day(day_last)}일)" if day20 \
                        else f"2+3순기 ({get_day(base)+1}~{get_day(day_last)}일)"
                p3.update({"period_name": label, "period_type": "10day",
                            "display_date": f"{year}-{month:02d}-{get_day(day_last):02d}"})
                result.append(p3)

        return result

    def _aggregate_weekly(self, data: List[Dict], intent: QueryIntent) -> AggregatedData:
        from datetime import date as dt_date, timedelta

        all_weeks = []
        for period in intent.periods:
            y, mn = period.start_date.year, period.start_date.month
            monthly = [r for r in data if (lambda a,b,c: a==y and b==mn)(*self._get_ym(r))]
            if monthly:
                all_weeks.extend(self._compute_weekly_periods(monthly, y, mn))

        desc = f"{intent.periods[0].description} 주차별" if len(intent.periods) == 1 else "복수 기간 주차별"
        return AggregatedData(all_weeks, "weekly", intent.periods, desc)

    def _compute_weekly_periods(self, monthly_data: List[Dict], year: int, month: int) -> List[Dict]:
        from datetime import date as dt_date, timedelta

        first_day = dt_date(year, month, 1)
        first_weekday = first_day.weekday()
        week_start_of_first = first_day - timedelta(days=first_weekday)
        current_start = week_start_of_first if first_weekday <= 3 \
                        else week_start_of_first + timedelta(7)

        month_end = dt_date(year, month, calendar.monthrange(year, month)[1])
        week_ranges, week_num = [], 1

        while current_start <= month_end:
            week_end = current_start + timedelta(6)
            week_ranges.append({"week": week_num, "start": current_start, "end": week_end})
            current_start = week_end + timedelta(1)
            week_num += 1

        result = []
        for wr in week_ranges:
            recs = [r for r in self.all_data
                    if r.get("date") and
                    wr["start"] <= dt_date.fromisoformat(r["date"]) <= wr["end"]]
            if not recs:
                continue

            recs.sort(key=lambda x: x.get("date", ""))
            dates = [dt_date.fromisoformat(r["date"]) for r in recs]
            sd, ed = min(dates), max(dates)
            range_str = f"{sd.day}~{ed.day}일" if sd.month == ed.month \
                        else f"{sd.month}/{sd.day}~{ed.month}/{ed.day}"

            first_r, last_r = recs[0], recs[-1]
            fd, ld = first_r.get("data", {}), last_r.get("data", {})
            converted = {}
            for key, lv in ld.items():
                if key.startswith("누적_"):
                    fv = fd.get(key, {})
                    dk = key.replace("누적_", "당일_")
                    fdv = fd.get(dk, {})
                    if isinstance(lv, dict):
                        converted[key] = {
                            k: v - (fv.get(k,0) if isinstance(fv,dict) else 0)
                               + (fdv.get(k,0) if isinstance(fdv,dict) else 0)
                            for k, v in lv.items()
                        }
                    else:
                        fdv_scalar = fdv if isinstance(fdv,(int,float)) else 0
                        converted[key] = lv - (fv or 0) + fdv_scalar

            rec = last_r.copy()
            rec.update({"period_name": f"{wr['week']}주차 ({range_str})",
                         "period_type": "weekly",
                         "display_date": last_r.get("date"),
                         "data": converted})
            result.append(rec)

        return result

    def _aggregate_monthly(self, data: List[Dict], intent: QueryIntent) -> AggregatedData:
        monthly = {}
        for r in data:
            y, m, d = self._get_ym(r)
            if not all([y, m, d]):
                continue
            key = f"{y}-{m:02d}"
            if key not in monthly or d > self._get_ym(monthly[key])[2]:
                monthly[key] = r

        sorted_m = sorted(monthly.values(), key=lambda x: x.get("date", ""))
        desc = f"{intent.periods[0].description} 월별" if len(intent.periods) == 1 else "월별 비교"
        return AggregatedData(sorted_m, "monthly", intent.periods, desc)

    def _aggregate_yearly(self, data: List[Dict], intent: QueryIntent) -> AggregatedData:
        yearly = {}
        for r in data:
            y, _, _ = self._get_ym(r)
            if not y:
                continue
            if y not in yearly or r.get("date","") > yearly[y].get("date",""):
                yearly[y] = r

        sorted_y = sorted(yearly.values(), key=lambda x: self._get_ym(x)[0] or 0)
        return AggregatedData(sorted_y, "yearly", intent.periods, "연별 비교")