"""
calendar_handler.py

[수정 이력]
v1.0 | 2026-03-19 | 최초 작성 - Google Calendar API 일정 등록
v1.1 | 2026-03-19 | 서비스 계정 → OAuth2 방식으로 변경 (개인 구글 계정용)
v1.2 | 2026-03-19 | date_end 지원 추가 (항공 체류 일정 여러 날 처리)
v1.3 | 2026-03-20 | 조회(list/search) 및 삭제 기능 추가
v1.4 | 2026-03-20 | 중복 일정 체크 기능 추가
v1.5 | 2026-03-22 | requests 직접 호출로 변경, 매 요청마다 새 session - hang 완전 해결
v1.6 | 2026-03-25 | update_event 추가 (일정 수정)
v1.7 | 2026-09-20 | check_duplicates - 시간 무시하고 제목만 비교하던 버그 수정
     | (같은 날 다른 시간의 동명 일정도 무조건 "중복"으로 떴음).
     | list_events/search_events - maxResults 늘리고(20→50, 10→30) nextPageToken
     | 유무로 "더 있음" 여부를 알 수 있는 옵션 추가 (조용히 잘리던 문제)
v1.8 | 2026-09-20 | find_duplicate_groups 추가 (봇이 실수로 두 번 등록한 일정을
     | 찾아 정리하는 기능용) + dedupe_events 추가 (조회 화면에 같은 일정이
     | 중복으로 두 줄씩 보이던 문제 - 실제 데이터는 안 건드리고 표시만 정리)
v1.9 | 2026-09-20 | list_events(keyword=)/search_events - Google Calendar API의
     | q 파라미터가 붙여쓴 한글 복합어를 제대로 부분일치 못 시키는 문제
     | ("점심" 검색 시 "MVNo팀 점심"은 잡히는데 "IIC점심"은 빠짐). q 서버측
     | 필터링 대신 _fetch_all_pages로 기간 내 전체를 받아 클라이언트에서
     | substring 매칭하도록 변경
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


def dedupe_events(events: list) -> list:
    """조회 화면 표시용 - 같은 날+제목+시작시간인 일정은 하나만 남김.
    실제 캘린더 데이터를 지우는 게 아니라 화면에 보여줄 때만 합쳐서 보여줌."""
    seen = set()
    result = []
    for ev in events:
        key = (ev.get("date"), (ev.get("title") or "").replace(" ", ""), ev.get("time_start"))
        if key in seen:
            continue
        seen.add(key)
        result.append(ev)
    return result

CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


def _get_access_token() -> str:
    """매번 새 session으로 토큰 갱신 - connection 재사용 문제 방지"""
    with requests.Session() as s:
        resp = s.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        logger.info("Access token refreshed")
        return token


def _call_api(method: str, url: str, **kwargs) -> requests.Response:
    """매번 새 session으로 API 호출 - connection hang 방지"""
    token = _get_access_token()
    with requests.Session() as s:
        resp = s.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            **kwargs
        )
        resp.raise_for_status()
        return resp


def _fetch_all_pages(url: str, params: dict, hard_cap: int = 500) -> tuple:
    """[v1.9] 페이지 전체를 다 모아서 반환 (items, truncated 여부).
    키워드 클라이언트측 필터링 시, 매칭되는 일정이 첫 페이지 뒤에 있으면
    놓치는 걸 방지하기 위해 hard_cap까지 페이지네이션."""
    items = []
    page_token = None
    while True:
        p = dict(params)
        if page_token:
            p["pageToken"] = page_token
        resp = _call_api("GET", url, params=p)
        data = resp.json()
        items.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token or len(items) >= hard_cap:
            return items, bool(page_token)


class CalendarHandler:
    def __init__(self):
        pass

    def _build_event_body(self, event: dict) -> dict:
        date_str = event.get("date")
        date_end_str = event.get("date_end") or date_str
        time_start = event.get("time_start")
        time_end = event.get("time_end")
        title = event.get("title", "일정")
        location = event.get("location")
        description = event.get("description")

        if time_start:
            start_dt = datetime.strptime(f"{date_str} {time_start}", "%Y-%m-%d %H:%M")
            if time_end:
                end_dt = datetime.strptime(f"{date_end_str} {time_end}", "%Y-%m-%d %H:%M")
            else:
                end_dt = start_dt + timedelta(hours=1)
            body = {
                "summary": title,
                "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Asia/Seoul"},
                "end": {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Asia/Seoul"},
            }
        else:
            end_date = datetime.strptime(date_end_str, "%Y-%m-%d").date()
            end_date_exclusive = end_date + timedelta(days=1)
            body = {
                "summary": title,
                "start": {"date": date_str},
                "end": {"date": end_date_exclusive.strftime("%Y-%m-%d")},
            }

        if location:
            body["location"] = location
        if description:
            body["description"] = description
        return body

    def add_events(self, events: list) -> list:
        results = []
        for event in events:
            title = event.get("title", "일정")
            try:
                body = self._build_event_body(event)
                resp = _call_api(
                    "POST",
                    f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events",
                    json=body,
                )
                created = resp.json()
                results.append({"success": True, "title": title, "link": created.get("htmlLink", "")})
                logger.info(f"Event created: {title}")
            except Exception as e:
                logger.error(f"Failed to create event '{title}': {e}")
                results.append({"success": False, "title": title, "error": str(e)})
        return results

    def list_events(self, date_from: datetime, date_to: datetime, with_more: bool = False, keyword: str = None):
        params = {
            "timeMin": date_from.strftime("%Y-%m-%dT00:00:00+09:00"),
            "timeMax": date_to.strftime("%Y-%m-%dT23:59:59+09:00"),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        }
        if not keyword:
            resp = _call_api("GET", f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events", params=params)
            data = resp.json()
            events = self._parse_events(data.get("items", []))
            if with_more:
                return events, bool(data.get("nextPageToken"))
            return events

        # [v1.9] Google Calendar API의 q 파라미터는 붙여쓴 한글 복합어를 제대로
        # 부분일치 못 함 - "점심" 검색 시 "MVNo팀 점심"(공백 있음)은 잡히는데
        # "IIC점심"(붙어있음)은 빠짐. q로 서버측 필터링 대신 기간 내 전체를
        # 받아와서 클라이언트에서 직접 substring 매칭.
        raw_items, truncated = _fetch_all_pages(f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events", params)
        events = self._parse_events(raw_items)
        kw = keyword.replace(" ", "")
        events = [e for e in events if kw in e.get("title", "").replace(" ", "")]
        if with_more:
            return events, truncated
        return events

    def search_events(self, keyword: str, with_more: bool = False):
        now = datetime.now()
        params = {
            "timeMin": now.strftime("%Y-%m-%dT00:00:00+09:00"),
            "timeMax": (now + timedelta(days=90)).strftime("%Y-%m-%dT23:59:59+09:00"),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }
        # [v1.9] list_events와 동일하게 q 파라미터 대신 클라이언트측 substring 매칭
        raw_items, truncated = _fetch_all_pages(f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events", params)
        events = self._parse_events(raw_items)
        kw = keyword.replace(" ", "")
        events = [e for e in events if kw in e.get("title", "").replace(" ", "")]
        if with_more:
            return events, truncated
        return events

    def _parse_events(self, items: list) -> list:
        events = []
        for item in items:
            start = item.get("start", {})
            end = item.get("end", {})
            if "dateTime" in start:
                start_dt = datetime.fromisoformat(start["dateTime"])
                end_dt = datetime.fromisoformat(end["dateTime"])
                date_str = start_dt.strftime("%Y-%m-%d")
                time_start = start_dt.strftime("%H:%M")
                end_date_str = end_dt.strftime("%Y-%m-%d")
                time_end = end_dt.strftime("%H:%M")
            else:
                date_str = start.get("date", "")
                end_date_raw = end.get("date", date_str)
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date() - timedelta(days=1)
                end_date_str = end_date.strftime("%Y-%m-%d")
                time_start = None
                time_end = None
            events.append({
                "id": item["id"],
                "title": item.get("summary", "(제목 없음)"),
                "date": date_str,
                "date_end": end_date_str,
                "time_start": time_start,
                "time_end": time_end,
                "location": item.get("location"),
                "created": item.get("created"),
            })
        return events

    def update_event(self, event_id: str, event: dict) -> bool:
        """기존 일정 수정 (PATCH)"""
        try:
            body = self._build_event_body(event)
            _call_api(
                "PATCH",
                f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events/{event_id}",
                json=body,
            )
            logger.info(f"Event updated: {event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            return False

    def delete_event(self, event_id: str) -> bool:
        try:
            _call_api("DELETE", f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events/{event_id}")
            logger.info(f"Event deleted: {event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            return False

    def check_duplicates(self, events: list) -> list:
        """같은 날 + 같은 제목 + 같은 시작 시간(둘 다 종일 일정이면 시간 없음도 일치)
        일 때만 중복으로 판단. 예전엔 제목만 봐서 같은 날 다른 시간대 동명 일정도
        전부 중복으로 떴음 (예: 오전 "회의"와 오후 "회의")."""
        results = []
        for ev in events:
            date_str = ev.get("date")
            if not date_str:
                continue
            try:
                date_from = datetime.strptime(date_str, "%Y-%m-%d")
                existing = self.list_events(date_from, date_from)
                ev_title = ev.get("title", "").replace(" ", "")
                ev_time = ev.get("time_start")
                dups = [
                    e for e in existing
                    if e["title"].replace(" ", "") == ev_title
                    and e.get("time_start") == ev_time
                ]
                if dups:
                    results.append({"event": ev, "duplicates": dups})
            except Exception as e:
                logger.error(f"Duplicate check error: {e}")
        return results

    def find_duplicate_groups(self, events: list) -> list:
        """같은 날 + 같은 제목 + 같은 시작 시간인 이벤트를 그룹으로 묶어서,
        가장 먼저 생성된 것(keep)과 나머지(dups)로 나눠 반환.
        "생일" 포함 제목은 제외 - 구글 연락처 생일 동기화가 별개 반복 일정
        두 개로 잡혀있는 경우가 있어 봇이 만든 중복과 성격이 다름."""
        groups = defaultdict(list)
        for ev in events:
            date_str = ev.get("date")
            if not date_str:
                continue
            key = (date_str, (ev.get("title") or "").replace(" ", ""), ev.get("time_start"))
            groups[key].append(ev)
        result = []
        for (date_str, title, time_start), evs in groups.items():
            if len(evs) < 2 or "생일" in title:
                continue
            evs_sorted = sorted(evs, key=lambda e: e.get("created") or "")
            result.append({"keep": evs_sorted[0], "dups": evs_sorted[1:]})
        return result