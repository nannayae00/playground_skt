#!/usr/bin/env python3
"""
질문 분석기 (Query Parser) — Fallback 전용
AI Intent Parser 실패 시 룰베이스로 동작

[수정 이력]
v1.1 | 2026-04-09 | 버그픽스 반영 + fallback 전용으로 정리
  - _detect_aggregation(): 특정 날짜(MM월DD일/어제/오늘) → daily 최우선
  - _detect_aggregation(): 이번달/이달/지난달 → monthly 명시
  - _extract_specific_date(): 신규 — MM월DD일, 어제, 오늘 처리
  - _extract_single_period(): daily 시 specific_date 먼저 추출
  - _extract_year(): 일(day) 숫자를 연도로 오인식하는 버그 수정
    (4자리 필수, 2자리는 반드시 '년' suffix 필요)
  - _compute_10day_periods()의 "elif 21 <= 31:" → "elif day >= 21:" 버그 수정
v1.0 | ~2026-04-06 | 초기 버전
"""

from datetime import datetime, date, timedelta
from typing import Optional, List
from dataclasses import dataclass
import re
import calendar


@dataclass
class Period:
    start_date: date
    end_date: date
    description: str

    def __repr__(self):
        return f"Period({self.start_date} ~ {self.end_date}, '{self.description}')"


@dataclass
class QueryIntent:
    periods: List[Period]
    aggregation: str   # daily / 10day / weekly / monthly / yearly
    comparison: str    # single / compare / trend
    question: str

    def __repr__(self):
        return f"QueryIntent(agg={self.aggregation}, cmp={self.comparison}, periods={len(self.periods)})"


class QueryParser:

    def __init__(self, base_date: Optional[date] = None):
        self.base_date = base_date or datetime.now().date()
        self.lunar_holidays = {
            2024: {"설날": date(2024, 2, 10), "추석": date(2024, 9, 17)},
            2025: {"설날": date(2025, 1, 29), "추석": date(2025, 10, 6)},
            2026: {"설날": date(2026, 2, 17), "추석": date(2026, 9, 25)},
            2027: {"설날": date(2027, 2, 6),  "추석": date(2027, 9, 15)},
        }

    # ──────────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────────

    def parse(self, question: str) -> QueryIntent:
        question = question.lower().strip()
        aggregation = self._detect_aggregation(question)
        comparison  = self._detect_comparison(question)
        periods     = self._extract_periods(question, aggregation, comparison)
        if not periods:
            periods = [self._get_default_period(aggregation)]
        return QueryIntent(periods=periods, aggregation=aggregation,
                           comparison=comparison, question=question)

    # ──────────────────────────────────────────────
    # Aggregation 감지
    # ──────────────────────────────────────────────

    def _has_specific_day(self, question: str) -> bool:
        if re.search(r"\d{1,2}월\s*\d{1,2}일", question):
            return True
        if any(w in question for w in ["어제", "오늘", "그저께", "그제"]):
            return True
        if re.search(r"(?<!\w)\d{1,2}일", question):
            return True
        return False

    def _detect_aggregation(self, question: str) -> str:
        # ★ 특정 날짜(일 포함) → daily 최우선
        if self._has_specific_day(question):
            explicit = ["순기", "주차", "주별", "월별", "연별", "년별"]
            if not any(w in question for w in explicit):
                return "daily"

        if any(w in question for w in ["일별", "매일", "하루", "당일"]):
            return "daily"
        if any(w in question for w in ["구정", "설날", "추석", "연휴"]):
            return "weekly"
        if any(w in question for w in ["순기", "1순기", "2순기", "3순기"]):
            return "10day"
        if any(w in question for w in ["주차", "1주차", "2주차", "3주차", "4주차", "주별"]):
            return "weekly"

        monthly_patterns = [
            r"월별", r"각\s*월", r"매\s*월",
            r"제일.*달", r"가장.*달", r"최고.*달", r"최저.*달",
            r"어느.*월", r"몇.*월", r"(\d{2,4})년.*월별",
        ]
        if any(re.search(p, question) for p in monthly_patterns):
            return "monthly"

        # ★ 이번달/이달/지난달 → monthly 명시
        if any(w in question for w in ["이번달", "이달", "지난달", "저번달"]):
            return "monthly"
        if re.search(r"\d{1,2}월", question):
            return "monthly"

        yearly_patterns = [r"연별|년별", r"작년.*전체", r"올해.*전체", r"(\d{2,4})년.*전체"]
        if any(re.search(p, question) for p in yearly_patterns):
            return "yearly"
        if any(w in question for w in ["작년", "올해"]) and not re.search(r"\d{1,2}월", question):
            return "monthly"

        return "daily"

    def _detect_comparison(self, question: str) -> str:
        if any(k in question for k in ["비교", "vs", "대비", "와 ", "과 ", "랑 ", "차이", "다른", "같은", "유사"]):
            return "compare"
        if any(k in question for k in ["추이", "트렌드", "변화", "흐름", "패턴", "어떻게", "어떠"]):
            return "trend"
        return "single"

    # ──────────────────────────────────────────────
    # Period 추출
    # ──────────────────────────────────────────────

    def _extract_periods(self, question: str, aggregation: str, comparison: str) -> List[Period]:
        if comparison == "compare":
            periods = self._extract_multiple_periods(question, aggregation)
            if periods:
                return periods
        period = self._extract_single_period(question, aggregation)
        return [period] if period else []

    def _extract_multiple_periods(self, question: str, aggregation: str) -> List[Period]:
        months = re.findall(r"(\d{1,2})월", question)
        if len(months) >= 2:
            year = self._extract_year(question)
            result = []
            for m in months:
                month = int(m)
                result.append(Period(
                    start_date=date(year, month, 1),
                    end_date=date(year, month, calendar.monthrange(year, month)[1]),
                    description=f"{year}년 {month}월"
                ))
            return result

        if "작년" in question and "올해" in question:
            ly, ty = self.base_date.year - 1, self.base_date.year
            return [
                Period(date(ly,1,1), date(ly,12,31), f"{ly}년"),
                Period(date(ty,1,1), self.base_date,  f"{ty}년 (현재까지)"),
            ]
        return []

    def _extract_single_period(self, question: str, aggregation: str) -> Optional[Period]:
        # ★ daily → 특정 날짜 먼저
        if aggregation == "daily":
            p = self._extract_specific_date(question)
            if p:
                return p

        p = self._extract_holiday_period(question)
        if p:
            if aggregation == "weekly":
                d = p.start_date
                wk_start = d - timedelta(days=d.weekday())
                wk_end   = wk_start + timedelta(days=5)
                return Period(wk_start, wk_end, f"{p.description} 포함 주차")
            return p

        p = self._extract_relative_period(question)
        if p: return p
        return self._extract_absolute_period(question, aggregation)

    def _extract_specific_date(self, question: str) -> Optional[Period]:
        """MM월 DD일 / 어제 / 오늘"""
        match = re.search(r"(\d{1,2})월\s*(\d{1,2})일", question)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            year = self._extract_year(question)
            if month > self.base_date.month and "년" not in question:
                year = self.base_date.year - 1
            try:
                target = date(year, month, day)
            except ValueError:
                return None
            wd = ["월","화","수","목","금","토","일"][target.weekday()]
            return Period(target, target, f"{year}년 {month}월 {day}일({wd})")

        if "어제" in question:
            t = self.base_date - timedelta(days=1)
            wd = ["월","화","수","목","금","토","일"][t.weekday()]
            return Period(t, t, f"어제 ({t.strftime('%Y-%m-%d')},{wd})")

        if "오늘" in question:
            t = self.base_date
            wd = ["월","화","수","목","금","토","일"][t.weekday()]
            return Period(t, t, f"오늘 ({t.strftime('%Y-%m-%d')},{wd})")

        return None

    def _extract_holiday_period(self, question: str) -> Optional[Period]:
        patterns = {"구정":"설날","설날":"설날","설":"설날","추석":"추석","한가위":"추석"}
        for kw, name in patterns.items():
            if kw in question:
                year = self._extract_year(question)
                if year in self.lunar_holidays:
                    hd = self.lunar_holidays[year][name]
                    if "연휴" in question or "기간" in question:
                        return Period(hd - timedelta(1), hd + timedelta(1), f"{year}년 {name} 연휴")
                    return Period(hd, hd, f"{year}년 {name}")
        return None

    def _extract_relative_period(self, question: str) -> Optional[Period]:
        if "작년" in question:
            y = self.base_date.year - 1
            m = re.search(r"(\d{1,2})월", question)
            if m:
                mn = int(m.group(1))
                return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")
            return Period(date(y,1,1), date(y,12,31), f"{y}년")

        if "올해" in question or "금년" in question:
            y = self.base_date.year
            m = re.search(r"(\d{1,2})월", question)
            if m:
                mn = int(m.group(1))
                return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")
            return Period(date(y,1,1), self.base_date, f"{y}년 (현재까지)")

        if "지난달" in question or "저번달" in question:
            y, mn = (self.base_date.year-1, 12) if self.base_date.month == 1 \
                    else (self.base_date.year, self.base_date.month-1)
            return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")

        if "이번달" in question or "이달" in question:
            return Period(
                date(self.base_date.year, self.base_date.month, 1),
                self.base_date,
                f"{self.base_date.year}년 {self.base_date.month}월 (현재까지)"
            )

        if "지난주" in question or "전주" in question:
            mon = self.base_date - timedelta(days=self.base_date.weekday()) - timedelta(7)
            sat = mon + timedelta(5)
            return Period(mon, sat, f"지난주 ({mon.strftime('%m/%d')}~{sat.strftime('%m/%d')})")

        if "이번주" in question:
            mon = self.base_date - timedelta(days=self.base_date.weekday())
            sat = mon + timedelta(5)
            end = min(self.base_date, sat)
            return Period(mon, end, f"이번주 ({mon.strftime('%m/%d')}~현재)")

        return None

    def _extract_absolute_period(self, question: str, aggregation: str) -> Optional[Period]:
        # YYYY년 MM월
        m = re.search(r"(\d{4})년\s*(\d{1,2})월", question)
        if m:
            y, mn = int(m.group(1)), int(m.group(2))
            return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")

        # YY년 MM월
        m = re.search(r"'?(\d{2})년\s*(\d{1,2})월", question)
        if m:
            y, mn = 2000+int(m.group(1)), int(m.group(2))
            return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")

        # YYYY년
        m = re.search(r"\b(\d{4})\b", question)
        if m:
            y = int(m.group(1))
            if 2000 <= y <= 2099:
                return Period(date(y,1,1), date(y,12,31), f"{y}년")

        # YY년
        m = re.search(r"'?(\d{2})년", question)
        if m:
            y = 2000 + int(m.group(1))
            return Period(date(y,1,1), date(y,12,31), f"{y}년")

        # MM월
        m = re.search(r"(\d{1,2})월", question)
        if m:
            mn = int(m.group(1))
            y = self.base_date.year - 1 if mn > self.base_date.month else self.base_date.year
            return Period(date(y,mn,1), date(y,mn,calendar.monthrange(y,mn)[1]), f"{y}년 {mn}월")

        return None

    def _extract_year(self, question: str) -> int:
        if "작년" in question or "지난해" in question: return self.base_date.year - 1
        if "올해" in question or "금년" in question:   return self.base_date.year
        if "내년" in question:                          return self.base_date.year + 1
        # ★ 4자리 + 유효범위 검사
        m = re.search(r"\b(\d{4})\b", question)
        if m:
            v = int(m.group(1))
            if 2000 <= v <= 2099: return v
        # ★ 2자리는 반드시 '년' suffix
        m = re.search(r"'?(\d{2})년", question)
        if m: return 2000 + int(m.group(1))
        return self.base_date.year

    def _get_default_period(self, aggregation: str) -> Period:
        if aggregation == "monthly":
            return Period(date(self.base_date.year,1,1), self.base_date,
                          f"{self.base_date.year}년 (현재까지)")
        if aggregation in ("10day", "weekly"):
            return Period(date(self.base_date.year, self.base_date.month, 1), self.base_date,
                          f"{self.base_date.year}년 {self.base_date.month}월")
        start = self.base_date - timedelta(days=29)
        return Period(start, self.base_date, "최근 30일")


# ──────────────────────────────────────────────────────────────
# 테스트
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = QueryParser(base_date=date(2026, 4, 9))
    cases = [
        ("3월 11일 시장size skt out 비교해줘", "daily",   "2026-03-11"),
        ("4월 6일 실적",                       "daily",   "2026-04-06"),
        ("어제 실적",                           "daily",   "2026-04-08"),
        ("오늘 순증감",                         "daily",   "2026-04-09"),
        ("3월 누적 T Out",                      "monthly", "2026-03"),
        ("이번달 순증감",                       "monthly", None),
        ("1월 순기별 실적은?",                  "10day",   None),
        ("1월 주차별 실적은?",                  "weekly",  None),
        ("작년 1월과 2월 비교",                 "monthly", None),
    ]
    ok = 0
    for q, exp_agg, _ in cases:
        intent = parser.parse(q)
        passed = intent.aggregation == exp_agg
        if passed: ok += 1
        print(f"{'✅' if passed else '❌'} [{intent.aggregation}] {q}")
        for p in intent.periods:
            print(f"    {p}")
    print(f"\n{ok}/{len(cases)} 통과")