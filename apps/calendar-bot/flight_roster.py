"""
flight_roster.py

[수정 이력]
v1.0 | 2026-10-20 | 최초 작성 - 승무원 비행 스케줄표(DATE/FLIGHT/SHOWUP/SECTOR/STD/STA)를
     | Gemini가 일정으로 바로 바꾸면 "03 15:30"(3일 15:30)처럼 날짜+시간이 붙은 칸,
     | 자정 넘김, 여러 편 묶기에서 시간이 자주 틀리던 문제. Gemini는 표를 글자 그대로
     | 받아적기만 하고(roster rows), 시간 해석과 왕복 묶기는 여기서 코드로 처리
"""

import re
from datetime import date, datetime, timedelta

BASE_AIRPORTS = {"ICN", "GMP"}

AIRPORT_CITY = {
    "ICN": "인천", "GMP": "김포", "PUS": "부산", "CJU": "제주",
    "JFK": "뉴욕", "LAX": "LA", "SFO": "샌프란시스코", "SEA": "시애틀", "HNL": "호놀룰루",
    "YVR": "밴쿠버", "ATL": "애틀랜타", "ORD": "시카고", "LAS": "라스베이거스",
    "NRT": "나리타", "HND": "하네다", "NGO": "나고야", "KIX": "오사카", "ITM": "오사카",
    "FUK": "후쿠오카", "CTS": "삿포로", "OKA": "오키나와",
    "HKG": "홍콩", "TPE": "타이베이", "MFM": "마카오",
    "PEK": "베이징", "PKX": "베이징", "PVG": "상하이", "SHA": "상하이", "CAN": "광저우",
    "HGH": "항저우", "SZX": "선전", "TAO": "칭다오", "DLC": "다롄", "SHE": "선양",
    "BKK": "방콕", "HKT": "푸껫", "SGN": "호치민", "HAN": "하노이", "DAD": "다낭",
    "CXR": "나트랑", "PQC": "푸꾸옥", "MNL": "마닐라", "CEB": "세부", "SIN": "싱가포르",
    "KUL": "쿠알라룸푸르", "CGK": "자카르타", "DPS": "발리", "PNH": "프놈펜", "KTI": "프놈펜",
    "VTE": "비엔티안", "RGN": "양곤", "DEL": "델리", "ULN": "울란바토르", "UBN": "울란바토르",
    "SYD": "시드니", "BNE": "브리즈번", "MEL": "멜버른", "AKL": "오클랜드", "GUM": "괌", "SPN": "사이판",
    "FCO": "로마", "CDG": "파리", "LHR": "런던", "FRA": "프랑크푸르트", "MUC": "뮌헨",
    "AMS": "암스테르담", "BCN": "바르셀로나", "MAD": "마드리드", "IST": "이스탄불",
    "PRG": "프라하", "VIE": "비엔나", "ZRH": "취리히", "BUD": "부다페스트", "DXB": "두바이",
}

_ROW_DATE = re.compile(r"(\d{1,2})\s*[/.\-월]\s*(\d{1,2})")
_DAY_TIME = re.compile(r"(?:(\d{1,2})\s+)?(\d{1,2}):(\d{2})")
_AIRPORT = re.compile(r"^[A-Z]{3}$")


def _city(code: str) -> str:
    return AIRPORT_CITY.get(code, code)


def _parse_row_date(text: str, today: date):
    m = _ROW_DATE.search(text or "")
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    # 연말에 다음 해 1월 스케줄을 보내는 경우
    if (today - d).days > 180:
        d = date(today.year + 1, month, day)
    return d


def _shift_month(d: date, n: int) -> tuple:
    m = d.month - 1 + n
    return d.year + m // 12, m % 12 + 1


def _parse_cell_time(text: str, row_date: date):
    """'03 15:30', 'T2 03 15:30', '15:30' → datetime. 앞의 숫자는 그 달의 '일'이고,
    달이 넘어가는 경우(30일 출발 → 01일 도착)를 위해 행 날짜에 가장 가까운 달을 고름."""
    m = _DAY_TIME.search(text or "")
    if not m:
        return None
    day_s, hh, mm = m.groups()
    hh, mm = int(hh), int(mm)
    if hh > 23 or mm > 59:
        return None
    if not day_s:
        return datetime(row_date.year, row_date.month, row_date.day, hh, mm)
    day = int(day_s)
    candidates = []
    for n in (-1, 0, 1):
        y, mo = _shift_month(row_date, n)
        try:
            candidates.append(datetime(y, mo, day, hh, mm))
        except ValueError:
            pass
    if not candidates:
        return None
    return min(candidates, key=lambda dt: abs((dt.date() - row_date).days))


def _trip_event(trip: dict) -> dict:
    places = []
    for dep, arr in trip["sectors"]:
        for code in (dep, arr):
            if code not in BASE_AIRPORTS and code not in places:
                places.append(code)
    title = "/".join(_city(c) for c in places) or "비행"
    start, end = trip["start"], trip["end"] or trip["start"]
    desc = "편명 " + ", ".join(trip["flights"]) + " | " + ", ".join(f"{d}/{a}" for d, a in trip["sectors"])
    return {
        "title": title,
        "date": start.strftime("%Y-%m-%d"),
        "date_end": end.strftime("%Y-%m-%d"),
        "time_start": start.strftime("%H:%M"),
        "time_end": end.strftime("%H:%M"),
        "location": None,
        "description": desc,
        "input_type": "schedule",
    }


def _all_day(d: date, title: str) -> dict:
    ds = d.strftime("%Y-%m-%d")
    return {"title": title, "date": ds, "date_end": ds, "time_start": None, "time_end": None,
            "location": None, "description": None, "input_type": "schedule"}


def build_events(rows: list, today: date) -> list:
    """Gemini가 받아적은 행 → 일정 목록.
    - 출발편 SHOWUP(없으면 STD) ~ 귀국편 STA를 한 일정으로 묶음 (기지 ICN/GMP 도착 시 종료)
    - 비행 사이 체류지 행(SYD 등)은 흡수, DAY OFF·STBY·휴가 등은 종일 일정으로 유지"""
    events, trip, cur = [], None, None

    def close_trip():
        nonlocal trip
        if trip:
            events.append(_trip_event(trip))
            trip = None

    for r in rows:
        d = _parse_row_date(r.get("date"), today) or cur
        if d is None:
            continue
        cur = d
        flight = (r.get("flight") or "").strip()
        sector = re.sub(r"\s+", "", (r.get("sector") or "").upper())
        if "/" in sector:
            dep, arr = sector.split("/", 1)
            show = _parse_cell_time(r.get("showup"), d)
            std = _parse_cell_time(r.get("std"), d)
            sta = _parse_cell_time(r.get("sta"), d)
            if trip is None:
                start = show or std or datetime(d.year, d.month, d.day)
                trip = {"start": start, "end": None, "flights": [], "sectors": []}
            if flight:
                trip["flights"].append(flight)
            trip["sectors"].append((dep, arr))
            trip["end"] = sta or std or trip["end"]
            if arr in BASE_AIRPORTS:
                close_trip()
            continue

        text = flight or (r.get("sector") or "").strip()
        if not text:
            continue
        if _AIRPORT.match(text.upper()) and text.upper() not in BASE_AIRPORTS:
            if trip is not None:
                continue  # 체류지 - 왕복 일정에 흡수
            events.append(_all_day(d, _city(text.upper())))
            continue
        close_trip()
        events.append(_all_day(d, text))
    close_trip()
    return events
