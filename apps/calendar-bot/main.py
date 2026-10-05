"""
main.py

[수정 이력]
v1.0 | 2026-03-19 | 최초 작성
v1.1 | 2026-03-19 | 이미지 수신 및 Gemini Vision 파싱 추가
v1.2 | 2026-03-19 | 이미지 다운로드 오류 수정
v1.3 | 2026-03-19 | 항공 스케줄 날짜 범위 표시 추가
v1.4 | 2026-03-20 | /list, /search, 삭제 기능 추가
v1.5 | 2026-03-20 | 자연어 의도 파악 → 자동 명령어 연결
v1.6 | 2026-03-20 | Firestore 세션, 중복체크, 예약문자 파싱 추가
v1.7 | 2026-03-20 | 날짜 포맷 변경 - 연도 약식 + 요일 추가
v1.8 | 2026-03-21 | 비서 리액션 추가 - 전후 일정 충돌/간격 체크, 늦은밤/이른아침 감지
v1.9 | 2026-03-21 | 조회 시 바쁜 정도 코멘트, 삭제 후 프로페셔널 멘트 추가
v2.1 | 2026-03-22 | 텔레그램 callback_data 64바이트 초과 버그 수정 - 긴 event_id 처리
v2.2 | 2026-03-25 | 고차원 분석 질문(analyze) + 일정 수정(modify) 기능 추가
v2.3 | 2026-03-31 | 수정 확인 키보드에 ✏️ 재수정 버튼 추가
v2.4 | 2026-05-27 | update_id 기반 중복 요청 방지 - 이미지 전송 시 확인창 2회 표시 버그 수정
v2.5 | 2026-06-29 | webhook 즉시 200 응답 + 백그라운드 처리 - Cloud Run 다중 인스턴스 retry 문제 해결
v2.6 | 2026-06-29 | 등록 버튼 중복 클릭 방지 - 세션 먼저 삭제 후 등록 처리
v2.7 | 2026-09-20 | v2.6의 수정이 실제로는 안 막고 있던 race condition 수정.
     | get()으로 세션을 읽는 시점과 register_events() 안에서 clear()하는
     | 시점이 원자적이지 않아서, 진짜 더블클릭(서로 다른 callback_query 2건)
     | 시 두 요청 다 세션을 읽고 둘 다 캘린더 등록까지 진행되던 문제.
     | sessions.consume()(Firestore 트랜잭션 기반 원자적 읽기+삭제)으로 교체
v2.8 | 2026-09-20 | list intent에 keyword 필드 추가 - "다음주 점심일정들"처럼
     | 날짜+키워드가 같이 오면 키워드가 버려지던 문제 수정
v2.9 | 2026-09-20 | 두 가지 수정: (1) '✏️ 재수정' 버튼 클릭 후 상태
     | (waiting_modify_reedit)를 아무 데서도 처리하지 않아 버튼이 사실상
     | 동작 안 하던 문제 - handle_modify_reedit 추가. (2) 삭제 버튼 callback_data가
     | 64바이트 제한으로 긴 event_id(반복 일정 인스턴스 등)를 앞에서 잘라
     | 보내는데, 삭제 시 그 잘린 문자열을 그대로 event_id로 써서 항상 실패하던
     | 문제 - 목록 표시 시 세션에 원본 events를 저장해두고 삭제 시 prefix로
     | 복원하도록 수정
v3.0 | 2026-09-20 | 조회/검색/브리핑에서 중복 등록된 일정이 두 줄씩 보이던 문제 -
     | dedupe_events로 화면 표시만 정리 (데이터는 그대로 유지).
     | cleanup_duplicates 기능 추가 - "다음주 중복된 일정 확인해서 삭제해줘"처럼
     | 말하면 기간 내 중복 그룹을 찾아 보여주고 버튼 확인 한 번으로 정리(각
     | 그룹에서 가장 먼저 등록된 것만 남기고 삭제). "생일" 포함 제목은 제외
     | (연락처 동기화 중복이라 봇이 만든 중복과 원인이 다름)
v3.1 | 2026-09-20 | 일정을 여러 메시지로 나눠 보내면 확인 누르기 전에 이전
     | 메시지분이 sessions.set()에 덮어써져서 마지막 메시지 일정만 남던 문제 -
     | waiting_confirm 상태면 새 일정을 이어붙이도록 수정 (handle_text, handle_image)
"""

import os
import html
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests

from gemini_handler import GeminiHandler
from calendar_handler import CalendarHandler, dedupe_events
from session_manager import SessionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

gemini = GeminiHandler()
calendar = CalendarHandler()
sessions = SessionManager()


def esc(text) -> str:
    """[v2.8] parse_mode="HTML"로 보내는 메시지에 동적 텍스트(일정 제목/장소/
    검색어/에러 메시지 등)를 끼워넣을 때 반드시 거쳐야 함. 제목에 &, <, > 가
    있으면(예: "R&D 회의") 이스케이프 없이는 텔레그램이 HTML 파싱에 실패해
    메시지 전송이 조용히 실패했었음."""
    return html.escape(str(text)) if text else ""


def send_message(chat_id: int, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    if not resp.ok:
        logger.error(f"sendMessage 실패 ({resp.status_code}): {resp.text[:300]} | text={text[:200]!r}")


def make_modify_keyboard(events: list) -> dict:
    buttons = []
    for i, ev in enumerate(events):
        title = ev.get("title", "일정")
        date = format_date(ev.get("date", ""))
        callback = f"mod_{ev['id']}"
        if len(callback.encode()) > 64:
            callback = f"mod_{ev['id'][:55]}"
        buttons.append([{"text": f"✏️ {i+1}) {title} {date}", "callback_data": callback}])
    buttons.append([{"text": "취소", "callback_data": "cancel"}])
    return {"inline_keyboard": buttons}


def make_modify_confirm_keyboard() -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ 수정 완료", "callback_data": "modify_confirm"},
        {"text": "✏️ 재수정", "callback_data": "modify_reedit"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]]}


def make_confirm_keyboard():
    return {"inline_keyboard": [[
        {"text": "✅ 등록", "callback_data": "confirm"},
        {"text": "✏️ 수정", "callback_data": "edit"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]]}


def make_confirm_anyway_keyboard():
    """중복 있을 때 강제등록 키보드"""
    return {"inline_keyboard": [[
        {"text": "✅ 그냥 등록", "callback_data": "confirm_anyway"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]]}


def make_cleanup_confirm_keyboard(count: int) -> dict:
    return {"inline_keyboard": [[
        {"text": f"🗑️ {count}건 삭제", "callback_data": "cleanup_confirm"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]]}


def make_delete_keyboard(events: list) -> dict:
    buttons = []
    for i, ev in enumerate(events):
        title = ev.get("title", "일정")
        date = format_date(ev.get("date", ""))
        # callback_data는 64바이트 제한 - event_id만 사용
        callback = f"del_{ev['id']}"
        if len(callback.encode()) > 64:
            callback = f"del_{ev['id'][:55]}"
        buttons.append([{"text": f"🗑️ {i+1}) {title} {date}", "callback_data": callback}])
    buttons.append([{"text": "닫기", "callback_data": "close_list"}])
    return {"inline_keyboard": buttons}


WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

def format_date(date_str: str) -> str:
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        yy = str(dt.year)[2:]
        dow = WEEKDAY_KO[dt.weekday()]
        return f"'{yy}-{dt.strftime('%m-%d')} ({dow})"
    except:
        return date_str

def format_event_line(ev: dict, idx: int = None) -> str:
    date = ev.get("date", "")
    date_end = ev.get("date_end", "")
    time_start = ev.get("time_start", "")
    time_end = ev.get("time_end", "")
    title = esc(ev.get("title", "제목 없음"))
    location = esc(ev.get("location", ""))
    date_fmt = format_date(date)
    if date_end and date_end != date:
        date_range = f"{date_fmt}~{format_date(date_end)}"
    else:
        date_range = date_fmt
    time_str = ""
    if time_start and time_end:
        time_str = f" {time_start}~{time_end}"
    elif time_start:
        time_str = f" {time_start}"
    loc_str = f" 📍{location}" if location else ""
    prefix = f"<b>{idx})</b> " if idx else ""
    return f"  {prefix}{title} | {date_range}{time_str}{loc_str}"


def format_events_message(events: list) -> str:
    if not events:
        return "파싱된 일정이 없습니다."
    lines = ["📅 <b>다음 일정들을 등록할까요?</b>\n"]
    for i, ev in enumerate(events, 1):
        lines.append(format_event_line(ev, i))
    lines.append("\n수정이 필요하면 '✏️ 수정'을 누르거나 수정 내용을 직접 입력하세요.")
    return "\n".join(lines)


def format_list_message(events: list, title: str = "📅 일정 목록") -> str:
    if not events:
        return "📭 조회된 일정이 없습니다."
    lines = [f"<b>{title}</b>\n"]
    for i, ev in enumerate(events, 1):
        lines.append(format_event_line(ev, i))
    return "\n".join(lines)


def download_telegram_file(file_id: str) -> tuple:
    resp = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
    resp_json = resp.json()
    if not resp_json.get("ok"):
        raise Exception(f"getFile 실패: {resp_json}")
    file_path = resp_json["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    file_resp = requests.get(file_url)
    ext = file_path.split(".")[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}
    return file_resp.content, mime_map.get(ext, "image/jpeg")


def parse_date_range(date_from_str: str, date_to_str: str):
    """MM/DD 문자열 두 개를 올해 기준으로 datetime 범위로 변환.
    [v2.8] date_to가 date_from보다 빠르게 계산되면(예: 12/29~1/3처럼 연말~연초를
    걸치는 구간) date_to를 다음해로 보정 — 예전엔 무조건 올해로만 계산해서
    종료일이 시작일보다 앞서는 역전된 범위가 되어 조회가 깨졌음"""
    now = datetime.now()
    try:
        date_from = datetime.strptime(f"{now.year}/{date_from_str}", "%Y/%m/%d")
        date_to = datetime.strptime(f"{now.year}/{date_to_str}", "%Y/%m/%d")
        if date_to < date_from:
            date_to = datetime.strptime(f"{now.year + 1}/{date_to_str}", "%Y/%m/%d")
        return date_from, date_to
    except:
        return now, now


def register_events(chat_id: int, events: list):
    """캘린더 등록 공통 함수. 호출 전에 sessions.consume()으로 세션을 이미
    원자적으로 가져온 상태여야 함 (더블클릭 시 중복 등록 방지)"""
    send_message(chat_id, "⏳ 구글 캘린더에 등록중입니다...")
    try:
        results = calendar.add_events(events)
        success = [r for r in results if r["success"]]
        fail = [r for r in results if not r["success"]]
        msg = f"✅ <b>{len(success)}개 일정이 등록되었습니다!</b>\n"
        for r in success:
            msg += f"\n• {esc(r['title'])} → <a href='{r['link']}'>캘린더에서 보기</a>"
        if fail:
            msg += f"\n\n❗ 실패 {len(fail)}건:"
            for r in fail:
                msg += f"\n• {esc(r['title'])}: {esc(r['error'])}"
        send_message(chat_id, msg)
    except Exception as e:
        logger.error(f"Calendar error: {e}")
        send_message(chat_id, f"❗ 캘린더 등록 실패: {esc(str(e))}")


# 중복 update 방지 (Firestore 기반 - 다중 인스턴스 대응)
import threading

def _process_update(data: dict):
    """백그라운드에서 실제 처리 - Firestore로 중복 방지"""
    update_id = data.get("update_id")
    if not update_id:
        return

    # Firestore로 중복 체크 (다중 인스턴스 safe)
    try:
        from google.cloud import firestore as _fs
        db = _fs.Client()
        ref = db.collection("processed_updates").document(str(update_id))
        # 트랜잭션으로 원자적 체크+등록
        @_fs.transactional
        def _check_and_set(transaction, ref):
            snap = ref.get(transaction=transaction)
            if snap.exists:
                return False
            transaction.set(ref, {"ts": _fs.SERVER_TIMESTAMP})
            return True
        already = not _check_and_set(_fs.Client().transaction(), ref)
        if already:
            logger.warning(f"Duplicate update_id {update_id}, skipping")
            return
    except Exception as e:
        logger.warning(f"Firestore 중복체크 실패, 계속 진행: {e}")

    if "callback_query" in data:
        handle_callback(data["callback_query"])
    elif "message" in data:
        handle_message(data["message"])


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logger.info(f"Webhook received: {json.dumps(data, ensure_ascii=False)[:300]}")
    # 즉시 200 응답 - 텔레그램 retry 방지
    threading.Thread(target=_process_update, args=(data,), daemon=True).start()
    return jsonify({"ok": True})


def handle_message(message: dict):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    photo = message.get("photo")
    document = message.get("document")

    if text == "/start":
        send_message(chat_id,
            "👋 <b>일정 등록 봇입니다!</b>\n\n"
            "자연어로 편하게 말씀하시면 알아서 처리해드려요!\n\n"
            "<b>💬 예시:</b>\n"
            "• <code>오늘 일정 알려줘</code>\n"
            "• <code>다음주 뭐있어?</code>\n"
            "• <code>시애틀 일정 언제야?</code>\n"
            "• <code>3/21 하키 10시</code>\n"
            "• <code>시애틀 일정 지워줘</code>\n"
            "• 예약 확인 문자 붙여넣기\n"
            "• 스케줄표 사진 전송 📸\n\n"
            "<b>명령어:</b>\n"
            "• <code>/list</code>, <code>/list 4/5</code>, <code>/list 4/5~4/10</code>\n"
            "• <code>/search 키워드</code>"
        )
        return

    if text == "/cancel":
        sessions.clear(chat_id)
        send_message(chat_id, "❌ 취소되었습니다.")
        return

    if text.startswith("/list"):
        handle_list(chat_id, text[5:].strip())
        return

    if text.startswith("/search"):
        handle_search(chat_id, text[7:].strip())
        return

    session = sessions.get(chat_id)
    if session and session.get("state") == "waiting_edit":
        if text:
            handle_edit(chat_id, text, session)
        else:
            send_message(chat_id, "✏️ 수정 내용을 텍스트로 입력해주세요.")
        return

    if session and session.get("state") == "waiting_modify_reedit":
        if text:
            handle_modify_reedit(chat_id, text, session)
        else:
            send_message(chat_id, "✏️ 수정 내용을 텍스트로 입력해주세요.")
        return

    if photo or (document and document.get("mime_type", "").startswith("image/")):
        handle_image(chat_id, message)
        return

    if text:
        handle_natural_language(chat_id, text)
        return

    send_message(chat_id, "❗ 텍스트나 이미지를 보내주세요.")


def handle_natural_language(chat_id: int, text: str):
    try:
        intent = gemini.detect_intent(text)
        action = intent.get("action", "unknown")
        logger.info(f"Intent: {intent}")

        if action == "list":
            date_from_str = intent.get("date_from", datetime.now().strftime("%m/%d"))
            date_to_str = intent.get("date_to", date_from_str)
            keyword = intent.get("keyword") or None
            date_from, date_to = parse_date_range(date_from_str, date_to_str)
            logger.info(f"Listing events from {date_from} to {date_to}, keyword={keyword}")
            try:
                events, has_more = calendar.list_events(date_from, date_to, with_more=True, keyword=keyword)
                events = dedupe_events(events)
            except Exception as ce:
                logger.error(f"Calendar list error: {ce}", exc_info=True)
                send_message(chat_id, f"❗ 캘린더 조회 중 오류가 발생했어요: {esc(str(ce))}")
                return
            label = date_from_str if date_from_str == date_to_str else f"{date_from_str}~{date_to_str}"
            if keyword:
                label = f"{label} '{keyword}'"
            msg = format_list_message(events, f"📅 {esc(label)} 일정")
            if has_more:
                msg += "\n\n➕ 결과가 더 있어요 — 기간을 좁혀서 다시 조회해보세요."
            try:
                comment = gemini.get_list_comment(events) if events else None
            except Exception:
                comment = None
            if comment:
                msg += f"\n\n💬 <i>{esc(comment)}</i>"
            if events:
                sessions.set(chat_id, {"state": "delete_list", "events": events})
            send_message(chat_id, msg, make_delete_keyboard(events) if events else None)

        elif action == "search":
            handle_search(chat_id, intent.get("keyword", ""))

        elif action == "delete_search":
            keyword = intent.get("keyword", "")
            send_message(chat_id, f"🔍 <b>'{esc(keyword)}'</b> 일정을 찾고 있어요...")
            events = calendar.search_events(keyword)
            if not events:
                send_message(chat_id, f"📭 '{esc(keyword)}' 일정을 찾지 못했어요.")
            else:
                sessions.set(chat_id, {"state": "delete_list", "events": events})
                send_message(chat_id, format_list_message(events, "🗑️ 삭제할 일정을 선택하세요"),
                    make_delete_keyboard(events))

        elif action == "analyze":
            date_from_str = intent.get("date_from", datetime.now().strftime("%m/%d"))
            date_to_str = intent.get("date_to", date_from_str)
            question = intent.get("question", text)
            date_from, date_to = parse_date_range(date_from_str, date_to_str)
            send_message(chat_id, f"🔍 {esc(date_from_str)}~{esc(date_to_str)} 일정 분석 중...")
            try:
                events = calendar.list_events(date_from, date_to)
                if not events:
                    send_message(chat_id, f"📭 {esc(date_from_str)}~{esc(date_to_str)} 기간에 일정이 없어요.")
                    return
                answer = gemini.analyze_events(events, question)
                send_message(chat_id, f"🤖 <b>분석 결과</b>\n\n{esc(answer)}")
            except Exception as ce:
                logger.error(f"Analyze error: {ce}", exc_info=True)
                send_message(chat_id, f"❗ 분석 중 오류가 발생했어요: {esc(str(ce))}")

        elif action == "modify":
            keyword = intent.get("keyword", "")
            date_from_str = intent.get("date_from", datetime.now().strftime("%m/%d"))
            date_to_str = intent.get("date_to", date_from_str)
            request = intent.get("request", text)
            date_from, date_to = parse_date_range(date_from_str, date_to_str)
            send_message(chat_id, f"🔍 '{esc(keyword)}' 일정을 찾고 있어요...")
            try:
                events = calendar.search_events(keyword) if keyword else calendar.list_events(date_from, date_to)
                events = [e for e in events if date_from.strftime("%Y-%m-%d") <= e["date"] <= date_to.strftime("%Y-%m-%d")]
                if not events:
                    send_message(chat_id, f"📭 '{esc(keyword)}' 일정을 찾지 못했어요.")
                    return
                if len(events) > 1:
                    msg = format_list_message(events, "✏️ 수정할 일정을 선택하세요")
                    sessions.set(chat_id, {"state": "waiting_modify_select", "events": events, "request": request})
                    send_message(chat_id, msg, make_modify_keyboard(events))
                    return
                ev = events[0]
                modified = gemini.get_modify_event(ev, request)
                if not modified:
                    send_message(chat_id, "❗ 수정 내용을 이해하지 못했어요.")
                    return
                sessions.set(chat_id, {"state": "waiting_modify_confirm", "original": ev, "modified": modified})
                msg = f"✏️ <b>이렇게 수정할까요?</b>\n\n{format_events_message([modified])}"
                send_message(chat_id, msg, make_modify_confirm_keyboard())
            except Exception as ce:
                logger.error(f"Modify error: {ce}", exc_info=True)
                send_message(chat_id, f"❗ 수정 중 오류가 발생했어요: {esc(str(ce))}")

        elif action == "cleanup_duplicates":
            date_from_str = intent.get("date_from")
            date_to_str = intent.get("date_to")
            if date_from_str and date_to_str:
                date_from, date_to = parse_date_range(date_from_str, date_to_str)
                label = date_from_str if date_from_str == date_to_str else f"{date_from_str}~{date_to_str}"
            else:
                date_from = datetime.now()
                date_to = date_from + timedelta(days=365)
                label = "전체"
            send_message(chat_id, f"🔍 {esc(label)} 기간 중복 일정 확인 중...")
            try:
                events = calendar.list_events(date_from, date_to)
                groups = calendar.find_duplicate_groups(events)
                if not groups:
                    send_message(chat_id, f"✅ {esc(label)} 기간에 중복된 일정이 없어요.")
                    return
                candidates = []
                lines = [f"⚠️ <b>중복 일정 {len(groups)}건 발견</b>\n"]
                for g in groups:
                    keep = g["keep"]
                    dups = g["dups"]
                    lines.append(f"• {esc(keep['title'])} {keep['date']} {keep.get('time_start') or ''} (남기고 {len(dups)}건 삭제)")
                    candidates.extend(dups)
                lines.append(f"\n각 일정에서 가장 먼저 등록된 것만 남기고, 총 {len(candidates)}건을 삭제할까요?")
                sessions.set(chat_id, {"state": "waiting_cleanup_confirm", "candidates": candidates})
                send_message(chat_id, "\n".join(lines), make_cleanup_confirm_keyboard(len(candidates)))
            except Exception as ce:
                logger.error(f"Cleanup error: {ce}", exc_info=True)
                send_message(chat_id, f"❗ 중복 확인 중 오류가 발생했어요: {esc(str(ce))}")

        else:
            handle_text(chat_id, text)

    except Exception as e:
        logger.error(f"Intent error: {e}", exc_info=True)
        handle_text(chat_id, text)


def handle_list(chat_id: int, arg: str):
    now = datetime.now()
    if not arg:
        date_from = now
        date_to = now + timedelta(days=6 - now.weekday() if now.weekday() != 6 else 0)
    else:
        try:
            if "~" in arg:
                parts = arg.split("~")
                date_from, date_to = parse_date_range(parts[0].strip(), parts[1].strip())
            else:
                date_from = datetime.strptime(f"{now.year}/{arg}", "%Y/%m/%d")
                date_to = date_from
        except:
            send_message(chat_id, "❗ 날짜 형식 오류\n예) <code>/list 4/5</code>")
            return
    try:
        events, has_more = calendar.list_events(date_from, date_to, with_more=True)
        events = dedupe_events(events)
        title = "📅 이번 주 일정" if not arg else f"📅 {esc(arg)} 일정"
        msg = format_list_message(events, title)
        if has_more:
            msg += "\n\n➕ 결과가 더 있어요 — 기간을 좁혀서 다시 조회해보세요."
        if events:
            sessions.set(chat_id, {"state": "delete_list", "events": events})
        send_message(chat_id, msg, make_delete_keyboard(events) if events else None)
    except Exception as e:
        send_message(chat_id, f"❗ 조회 오류: {esc(str(e))}")


def handle_search(chat_id: int, keyword: str):
    if not keyword:
        send_message(chat_id, "❗ 검색어를 입력해주세요.\n예) <code>/search 시애틀</code>")
        return
    try:
        events, has_more = calendar.search_events(keyword, with_more=True)
        events = dedupe_events(events)
        msg = format_list_message(events, f"🔍 '{esc(keyword)}' 검색 결과")
        if has_more:
            msg += "\n\n➕ 결과가 더 있어요 — 검색어를 더 구체적으로 입력해보세요."
        if events:
            sessions.set(chat_id, {"state": "delete_list", "events": events})
        send_message(chat_id, msg, make_delete_keyboard(events) if events else None)
    except Exception as e:
        send_message(chat_id, f"❗ 검색 오류: {esc(str(e))}")


def _get_assistant_comment(events: list) -> str | None:
    """1개 일정일 때만 비서 코멘트 생성"""
    if len(events) != 1:
        return None
    try:
        ev = events[0]
        date_str = ev.get("date")
        if not date_str:
            return None
        from datetime import datetime
        date_from = datetime.strptime(date_str, "%Y-%m-%d")
        nearby = calendar.list_events(date_from, date_from)
        return gemini.get_assistant_comment(ev, nearby)
    except Exception as e:
        logger.error(f"Assistant comment error: {e}")
        return None


def _merge_with_pending(chat_id: int, new_events: list) -> list:
    """[v3.1] 확인 대기 중(waiting_confirm)인 일정이 있으면 새로 들어온 일정을
    이어붙임. 예전엔 그냥 sessions.set()으로 덮어써서, 일정을 여러 메시지로
    나눠 보내면 확인을 누르기 전에 이전 메시지분이 사라지고 마지막 메시지의
    일정만 남았음.
    [v3.2] 이어붙이기만 하고 중복 제거가 없어서, 확인을 누르기 전에 같은(또는
    같아 보이는) 문구를 두 번 보내면 - 예: 응답이 늦어 보여서 재전송 - 같은
    일정이 그대로 두 번 합쳐져 등록 확인 카드에 중복으로 뜨고 그대로 등록까지
    되던 문제. dedupe_events(날짜+제목+시작시간 기준)로 합친 뒤 중복 제거."""
    session = sessions.get(chat_id)
    if session and session.get("state") == "waiting_confirm":
        merged = session.get("events", []) + new_events
        return dedupe_events(merged)
    return new_events


def handle_text(chat_id: int, text: str):
    send_message(chat_id, "⏳ 일정을 분석중입니다...")
    try:
        events = gemini.parse_schedule(text)
        if not events:
            send_message(chat_id, "❗ 일정을 찾지 못했어요.")
            return
        events = _merge_with_pending(chat_id, events)

        # 중복 체크
        dups = calendar.check_duplicates(events)
        if dups:
            dup_msg = "⚠️ <b>이미 등록된 비슷한 일정이 있어요!</b>\n\n"
            for d in dups:
                dup_msg += f"• <b>{esc(d['event']['title'])}</b> {d['event']['date']} → 이미 있음\n"
            dup_msg += "\n그래도 등록하시겠어요?"
            sessions.set(chat_id, {"state": "waiting_confirm", "events": events})
            send_message(chat_id, dup_msg, make_confirm_anyway_keyboard())
        else:
            sessions.set(chat_id, {"state": "waiting_confirm", "events": events})
            # 1개 일정일 때 비서 코멘트
            comment = _get_assistant_comment(events)
            msg = format_events_message(events)
            if comment:
                msg += f"\n\n💬 <i>{esc(comment)}</i>"
            send_message(chat_id, msg, make_confirm_keyboard())
    except Exception as e:
        logger.error(f"Parse error: {e}")
        send_message(chat_id, f"❗ 오류: {esc(str(e))}")


def handle_image(chat_id: int, message: dict):
    send_message(chat_id, "📸 이미지에서 일정을 분석중입니다...")
    try:
        file_id = message["photo"][-1]["file_id"] if message.get("photo") else message["document"]["file_id"]
        image_bytes, mime_type = download_telegram_file(file_id)
        events = gemini.parse_schedule_from_image(image_bytes, mime_type)
        if not events:
            send_message(chat_id, "❗ 이미지에서 일정을 찾지 못했어요.")
            return
        events = _merge_with_pending(chat_id, events)

        # 중복 체크
        dups = calendar.check_duplicates(events)
        if dups:
            dup_msg = "⚠️ <b>이미 등록된 비슷한 일정이 있어요!</b>\n\n"
            for d in dups:
                dup_msg += f"• <b>{esc(d['event']['title'])}</b> {d['event']['date']} → 이미 있음\n"
            dup_msg += "\n그래도 등록하시겠어요?"
            sessions.set(chat_id, {"state": "waiting_confirm", "events": events})
            send_message(chat_id, dup_msg, make_confirm_anyway_keyboard())
        else:
            sessions.set(chat_id, {"state": "waiting_confirm", "events": events})
            # 1개 일정일 때 비서 코멘트
            comment = _get_assistant_comment(events)
            msg = format_events_message(events)
            if comment:
                msg += f"\n\n💬 <i>{esc(comment)}</i>"
            send_message(chat_id, msg, make_confirm_keyboard())
    except Exception as e:
        logger.error(f"Image error: {e}", exc_info=True)
        send_message(chat_id, f"❗ 이미지 분석 오류: {esc(str(e))}")


def handle_edit(chat_id: int, text: str, session: dict):
    send_message(chat_id, "⏳ 수정 내용을 반영중입니다...")
    try:
        updated_events = gemini.apply_edit(session.get("events", []), text)
        sessions.set(chat_id, {"state": "waiting_confirm", "events": updated_events})
        send_message(chat_id,
            "✏️ <b>수정된 일정입니다. 확인해주세요.</b>\n\n" + format_events_message(updated_events),
            make_confirm_keyboard())
    except Exception as e:
        send_message(chat_id, f"❗ 수정 오류: {esc(str(e))}")


def handle_modify_reedit(chat_id: int, text: str, session: dict):
    """[v2.9] '✏️ 재수정' 버튼 클릭 후 입력한 텍스트를 처리. 기존 원본 일정(original)에
    새 수정 요청을 다시 적용."""
    send_message(chat_id, "⏳ 수정 내용을 반영중입니다...")
    try:
        original = session.get("original")
        if not original:
            send_message(chat_id, "❗ 원본 일정 정보가 없어요. 다시 시도해주세요.")
            return
        modified = gemini.get_modify_event(original, text)
        if not modified:
            send_message(chat_id, "❗ 수정 내용을 이해하지 못했어요.")
            return
        sessions.set(chat_id, {"state": "waiting_modify_confirm", "original": original, "modified": modified})
        msg = f"✏️ <b>이렇게 수정할까요?</b>\n\n{format_events_message([modified])}"
        send_message(chat_id, msg, make_modify_confirm_keyboard())
    except Exception as e:
        send_message(chat_id, f"❗ 수정 오류: {esc(str(e))}")


def handle_callback(callback: dict):
    chat_id = callback["message"]["chat"]["id"]
    data = callback.get("data")

    requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback["id"]})

    # 삭제
    if data and data.startswith("del_"):
        event_id = data[4:]
        # [v2.9] callback_data 64바이트 제한으로 긴 event_id(반복 일정 등)가
        # make_delete_keyboard에서 잘려서 전달됨. 잘린 상태로 그대로 삭제 시도하면
        # 존재하지 않는 id라 항상 실패했음. 목록 표시 시 세션에 저장해둔 전체
        # events에서 prefix로 원본 id를 복원.
        session = sessions.get(chat_id)
        if session:
            match = next((e for e in session.get("events", []) if e["id"][:len(event_id)] == event_id), None)
            if match:
                event_id = match["id"]
        success = calendar.delete_event(event_id)
        send_message(chat_id, "🗑️ 삭제되었습니다." if success else "❗ 삭제 실패했습니다.")
        return

    if data == "close_list":
        return

    # [v2.7] 더블클릭 등 동시 요청 대비 — 등록은 sessions.consume()으로 원자적
    # 소비. 동시에 두 콜백이 들어와도 Firestore 트랜잭션 덕분에 하나만 세션을
    # 가져가고, 나머지는 None을 받아 조용히 무시됨 (중복 캘린더 등록 방지)
    if data in ("confirm", "confirm_anyway"):
        consumed = sessions.consume(chat_id)
        if not consumed:
            return
        register_events(chat_id, consumed.get("events", []))
        return

    # [v2.9] 중복 일정 정리 확인 - consume()으로 더블클릭 시 중복삭제 시도 방지
    if data == "cleanup_confirm":
        consumed = sessions.consume(chat_id)
        if not consumed:
            return
        candidates = consumed.get("candidates", [])
        send_message(chat_id, f"⏳ {len(candidates)}건 삭제 중...")
        success = 0
        fail = 0
        for ev in candidates:
            if calendar.delete_event(ev["id"]):
                success += 1
            else:
                fail += 1
        msg = f"✅ 중복 일정 {success}건 정리했어요."
        if fail:
            msg += f"\n❗ 실패 {fail}건"
        send_message(chat_id, msg)
        return

    session = sessions.get(chat_id)
    if not session:
        send_message(chat_id, "❗ 세션이 만료되었습니다. 다시 입력해주세요.")
        return

    events = session.get("events", [])

    if data == "edit":
        sessions.set(chat_id, {**session, "state": "waiting_edit"})
        send_message(chat_id,
            "✏️ 수정할 내용을 입력해주세요.\n\n"
            "<b>예시:</b>\n"
            "• <code>일정2는 14시부터 16시까지임</code>\n"
            "• <code>일정1 장소는 강남역임</code>")

    elif data and data.startswith("mod_"):
        event_id = data[4:]
        request = session.get("request", "")
        ev = next((e for e in events if e["id"][:len(event_id)] == event_id), None)
        if not ev:
            send_message(chat_id, "❗ 일정을 찾을 수 없어요.")
            return
        from gemini_handler import GeminiHandler
        modified = gemini.get_modify_event(ev, request)
        if not modified:
            send_message(chat_id, "❗ 수정 내용을 이해하지 못했어요.")
            return
        sessions.set(chat_id, {"state": "waiting_modify_confirm", "original": ev, "modified": modified})
        msg = f"✏️ <b>이렇게 수정할까요?</b>\n\n{format_events_message([modified])}"
        send_message(chat_id, msg, make_modify_confirm_keyboard())

    elif data == "modify_reedit":
        sessions.set(chat_id, {**session, "state": "waiting_modify_reedit"})
        send_message(chat_id, "✏️ 어떻게 수정할까요? 수정 내용을 입력해주세요.")
        return

    elif data == "modify_confirm":
        original = session.get("original")
        modified = session.get("modified")
        if not original or not modified:
            send_message(chat_id, "❗ 수정 정보가 없어요.")
            return
        success = calendar.update_event(original["id"], modified)
        sessions.clear(chat_id)
        if success:
            send_message(chat_id, f"✅ 일정이 수정됐어요!\n\n{format_events_message([modified])}")
        else:
            send_message(chat_id, "❗ 수정 중 오류가 발생했어요.")

    elif data == "cancel":
        sessions.clear(chat_id)
        send_message(chat_id, "❌ 취소되었습니다.")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})




@app.route("/daily-briefing", methods=["POST", "GET"])
def daily_briefing():
    """Cloud Scheduler에서 호출하는 아침 알림 엔드포인트"""
    try:
        from scheduler import send_daily_briefing
        send_daily_briefing()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Daily briefing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)