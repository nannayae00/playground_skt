#!/usr/bin/env python3
"""
한국어 날짜 파싱 모듈
- 자연어 인식: "작년", "올해", "지난달", "이번달"
- 명절 인식: "구정", "설날", "추석"
- 연휴 계산: 명절 전후 3일
"""

from datetime import datetime, timedelta, date
import re
from typing import Optional, Tuple, List
import calendar



class KoreanDateParser:
    """한국어 날짜 파싱 클래스"""
    
    # 음력 명절 날짜 (양력 변환) - 2024~2027년
    LUNAR_HOLIDAYS = {
        2024: {
            '설날': date(2024, 2, 10),
            '추석': date(2024, 9, 17),
        },
        2025: {
            '설날': date(2025, 1, 29),
            '추석': date(2025, 10, 6),
        },
        2026: {
            '설날': date(2026, 2, 17),
            '추석': date(2026, 9, 25),
        },
        2027: {
            '설날': date(2027, 2, 6),
            '추석': date(2027, 9, 15),
        }
    }
    
    def __init__(self, base_date: Optional[date] = None):
        """
        Args:
            base_date: 기준 날짜 (None이면 오늘)
        """
        self.base_date = base_date or datetime.now().date()
    
    def parse(self, text: str) -> Tuple[Optional[date], Optional[date], str]:
        """
        텍스트에서 날짜 범위 추출
        
        Returns:
            (start_date, end_date, description)
            - start_date: 시작일
            - end_date: 종료일 (단일 날짜면 None)
            - description: 인식된 표현 (예: "2025년 2월", "작년 구정연휴")
        """
        text = text.lower().strip()
        
        # 1. 명절 연휴 패턴 (최우선)
        result = self._parse_holiday(text)
        if result[0]:
            return result
        
        # 2. 상대적 표현 (작년, 올해 등)
        result = self._parse_relative(text)
        if result[0]:
            return result
        
        # 3. 절대적 표현 (2025년 2월 등)
        result = self._parse_absolute(text)
        if result[0]:
            return result
        
        return None, None, ""
    
    def _parse_holiday(self, text: str) -> Tuple[Optional[date], Optional[date], str]:
        """명절 연휴 파싱"""
        
        # 구정/설날 패턴
        holiday_patterns = {
            '구정': '설날',
            '설날': '설날',
            '설': '설날',
            '추석': '추석',
            '한가위': '추석',
        }
        
        for keyword, holiday_name in holiday_patterns.items():
            if keyword in text:
                # 연도 추출
                year = self._extract_year(text)
                
                if year and year in self.LUNAR_HOLIDAYS:
                    holiday_date = self.LUNAR_HOLIDAYS[year][holiday_name]
                    
                    # 연휴인지 단일 날짜인지 확인
                    if '연휴' in text or '기간' in text:
                        # 연휴: 명절 전후 각 1일 (총 3일)
                        start = holiday_date - timedelta(days=1)
                        end = holiday_date + timedelta(days=1)
                        desc = f"{year}년 {holiday_name} 연휴 ({start.strftime('%m/%d')}~{end.strftime('%m/%d')})"
                        return start, end, desc
                    else:
                        # 단일 날짜
                        desc = f"{year}년 {holiday_name} ({holiday_date.strftime('%m/%d')})"
                        return holiday_date, None, desc
        
        return None, None, ""
    
    def _parse_relative(self, text: str) -> Tuple[Optional[date], Optional[date], str]:
        """상대적 날짜 표현 파싱"""
        
        # 작년 패턴
        if '작년' in text:
            target_year = self.base_date.year - 1
            
            # 작년 + 월
            month_match = re.search(r'(\d{1,2})월', text)
            if month_match:
                month = int(month_match.group(1))
                start = date(target_year, month, 1)
                last_day = calendar.monthrange(target_year, month)[1]
                end = date(target_year, month, last_day)
                desc = f"{target_year}년 {month}월"
                return start, end, desc
            
            # 작년 전체
            start = date(target_year, 1, 1)
            end = date(target_year, 12, 31)
            desc = f"{target_year}년"
            return start, end, desc
        
        # 올해 패턴
        if '올해' in text or '금년' in text or '올 해' in text:
            target_year = self.base_date.year
            
            # 올해 + 월
            month_match = re.search(r'(\d{1,2})월', text)
            if month_match:
                month = int(month_match.group(1))
                start = date(target_year, month, 1)
                last_day = calendar.monthrange(target_year, month)[1]
                end = date(target_year, month, last_day)
                desc = f"{target_year}년 {month}월"
                return start, end, desc
            
            # 올해 전체
            start = date(target_year, 1, 1)
            end = self.base_date
            desc = f"{target_year}년 (현재까지)"
            return start, end, desc
        
        # 지난달 패턴
        if '지난달' in text or '저번달' in text or '전달' in text:
            if self.base_date.month == 1:
                target_year = self.base_date.year - 1
                target_month = 12
            else:
                target_year = self.base_date.year
                target_month = self.base_date.month - 1
            
            start = date(target_year, target_month, 1)
            last_day = calendar.monthrange(target_year, target_month)[1]
            end = date(target_year, target_month, last_day)
            desc = f"{target_year}년 {target_month}월"
            return start, end, desc
        
        # 이번달 패턴
        if '이번달' in text or '이달' in text or '금월' in text:
            start = date(self.base_date.year, self.base_date.month, 1)
            end = self.base_date
            desc = f"{self.base_date.year}년 {self.base_date.month}월 (현재까지)"
            return start, end, desc
        
        # 지난주 패턴
        if '지난주' in text or '전주' in text or '저번주' in text:
            # 지난주 월요일 찾기
            days_since_monday = self.base_date.weekday()
            last_monday = self.base_date - timedelta(days=days_since_monday + 7)
            last_sunday = last_monday + timedelta(days=6)
            desc = f"지난주 ({last_monday.strftime('%m/%d')}~{last_sunday.strftime('%m/%d')})"
            return last_monday, last_sunday, desc
        
        # 이번주 패턴
        if '이번주' in text or '금주' in text:
            days_since_monday = self.base_date.weekday()
            this_monday = self.base_date - timedelta(days=days_since_monday)
            desc = f"이번주 ({this_monday.strftime('%m/%d')}~현재)"
            return this_monday, self.base_date, desc
        
        return None, None, ""
    
    def _parse_absolute(self, text: str) -> Tuple[Optional[date], Optional[date], str]:
        """절대적 날짜 표현 파싱"""
        
        # YYYY년 MM월 패턴
        match = re.search(r'(\d{4})년\s*(\d{1,2})월', text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            
            # 일까지 있는지 확인
            day_match = re.search(r'(\d{1,2})일', text)
            if day_match:
                day = int(day_match.group(1))
                target_date = date(year, month, day)
                desc = f"{year}년 {month}월 {day}일"
                return target_date, None, desc
            else:
                # 월 전체
                start = date(year, month, 1)
                last_day = calendar.monthrange(year, month)[1]
                end = date(year, month, last_day)
                desc = f"{year}년 {month}월"
                return start, end, desc
        
        # YY년 MM월 패턴 (2자리 연도)
        match = re.search(r'(\d{2})년\s*(\d{1,2})월', text)
        if match:
            yy = int(match.group(1))
            year = 2000 + yy if yy < 100 else yy
            month = int(match.group(2))
            
            start = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end = date(year, month, last_day)
            desc = f"{year}년 {month}월"
            return start, end, desc
        
        # MM월만 있는 경우
        match = re.search(r'(\d{1,2})월', text)
        if match:
            month = int(match.group(1))
            
            # 연도 추정
            if month > self.base_date.month:
                year = self.base_date.year - 1
            else:
                year = self.base_date.year
            
            start = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end = date(year, month, last_day)
            desc = f"{year}년 {month}월"
            return start, end, desc
        
        return None, None, ""
    
    def _extract_year(self, text: str) -> Optional[int]:
        """텍스트에서 연도 추출"""
        
        # 작년
        if '작년' in text or '지난해' in text:
            return self.base_date.year - 1
        
        # 올해
        if '올해' in text or '금년' in text or '이번' in text:
            return self.base_date.year
        
        # 내년
        if '내년' in text or '다음해' in text:
            return self.base_date.year + 1
        
        # 4자리 연도
        match = re.search(r'(\d{4})년?', text)
        if match:
            return int(match.group(1))
        
        # 2자리 연도
        match = re.search(r"'?(\d{2})년?", text)
        if match:
            yy = int(match.group(1))
            return 2000 + yy if yy < 100 else yy
        
        # 명시 없으면 현재 연도
        return self.base_date.year


def parse_korean_date(text: str, base_date: Optional[date] = None) -> Tuple[Optional[date], Optional[date], str]:
    """
    간편 함수: 한국어 날짜 표현 파싱
    
    Args:
        text: 파싱할 텍스트
        base_date: 기준 날짜 (None이면 오늘)
    
    Returns:
        (start_date, end_date, description)
    
    Examples:
        >>> parse_korean_date("작년 2월은 어땠어?")
        (date(2025, 2, 1), date(2025, 2, 28), "2025년 2월")
        
        >>> parse_korean_date("작년 구정연휴 실적은?")
        (date(2025, 1, 28), date(2025, 1, 30), "2025년 설날 연휴 (01/28~01/30)")
        
        >>> parse_korean_date("지난달은?")
        (date(2026, 1, 1), date(2026, 1, 31), "2026년 1월")
    """
    parser = KoreanDateParser(base_date)
    return parser.parse(text)


# 테스트 코드
if __name__ == "__main__":
    # 현재 날짜를 2026-02-09로 가정
    test_date = date(2026, 2, 9)
    
    test_cases = [
        "작년 2월은 어땠어?",
        "작년 구정연휴에 실적은 어떠어?",
        "작년 구정 실적은?",
        "지난달 실적",
        "이번달 추이",
        "올해 1월",
        "2025년 12월",
        "12월 실적",
        "지난주 데이터",
    ]
    
    print("=" * 60)
    print(f"테스트 기준 날짜: {test_date}")
    print("=" * 60)
    
    for text in test_cases:
        start, end, desc = parse_korean_date(text, test_date)
        print(f"\n질문: {text}")
        if start:
            if end:
                print(f"결과: {start} ~ {end}")
            else:
                print(f"결과: {start}")
            print(f"설명: {desc}")
        else:
            print("결과: 인식 실패")