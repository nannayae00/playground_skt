"""
handlers/callback_handler.py  v1.3
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30] 신규 생성
[v1.1 / 2026-07-02] 504 타임아웃 수정: 콜백 즉시 응답 후 저장은 백그라운드 스레드 처리
[v1.2 / 2026-10-05] newsreg: 콜백 추가 (news_scraper 뉴스 다이제스트의 기사별 등록 버튼).
                     session.py는 chat당 세션 슬롯이 1개뿐이라 그대로 쓰면 여러 기사를
                     동시에 보낼 때 세션 충돌이 생기므로, news_drafts 컬렉션에 기사별로
                     독립 저장된 draft를 콜백데이터의 draft_id로 직접 조회하는 별도 경로.
[v1.3 / 2026-10-06] newsreg:preview 추가 - 번호 버튼 클릭 시 바로 저장하지 않고 등록될
                     내용을 미리 보여준 뒤 수정 가능하게 함. 이 시점부터는 기사 1건만
                     다루므로 session.py에 올려서 기존 confirm/edit/cancel 플로우를
                     그대로 재사용 (중복 구현 없이 edit_handler 등 기존 코드 재사용).
"""

import logging
import threading
from handlers.telegram import answer_callback, send_message, send_message_with_buttons
from handlers.session import get_session, save_session
from handlers.firestore_writer import save_issue
from handlers.news_drafts import get_draft, delete_draft

logger = logging.getLogger(__name__)


def handle_callback(callback_query: dict):
    query_id = callback_query["id"]
    chat_id = str(callback_query["message"]["chat"]["id"])
    data = callback_query.get("data", "")

    # 텔레그램에 즉시 응답 (5초 내 필수)
    answer_callback(query_id)

    if data.startswith("newsreg:"):
        _handle_news_callback(chat_id, data)
        return

    session = get_session(chat_id)
    if not session:
        send_message(chat_id, "⏰ 세션이 만료되었습니다. 다시 입력해주세요.")
        return

    draft = session.get("draft", {})
    collection = session.get("collection", "mvno_issues")

    # ✅ 등록 → 백그라운드 저장
    if data.startswith("confirm:"):
        target_collection = data.split(":")[1]
        save_session(chat_id, None)
        send_message(chat_id, "⏳ 저장 중...")
        threading.Thread(
            target=_save_and_notify,
            args=(chat_id, draft, target_collection),
            daemon=True
        ).start()

    # 🔄 분류 변경
    elif data.startswith("reclassify:"):
        new_collection = data.split(":")[1]
        draft["_collection"] = new_collection
        session["collection"] = new_collection
        session["draft"] = draft
        save_session(chat_id, session)

        label = "이슈(mvno_issues)" if new_collection == "mvno_issues" else "프로모션현황(promotion)"
        buttons = [
            [{"text": "✅ 등록", "callback_data": f"confirm:{new_collection}"},
             {"text": "❌ 취소", "callback_data": "cancel"}]
        ]
        send_message_with_buttons(chat_id, f"🔄 분류를 <b>{label}</b>로 변경했습니다.\n그대로 등록할까요?", buttons)

    # ✏️ 수정
    elif data == "edit":
        session["status"] = "awaiting_edit"
        save_session(chat_id, session)
        send_message(chat_id, "✏️ 수정 내용을 자유롭게 입력해주세요.\n\n예) '프로모션으로 등록하고, OO 내용은 삭제, 이런 말은 추가'")

    # ❌ 취소
    elif data == "cancel":
        save_session(chat_id, None)
        send_message(chat_id, "❌ 취소되었습니다.")

    # ➕ 기존 항목에 추가
    elif data == "append_to_dup":
        dup = session.get("duplicate")
        if dup:
            save_session(chat_id, None)
            send_message(chat_id, "⏳ 추가 중...")
            threading.Thread(
                target=_append_and_notify,
                args=(chat_id, dup, draft),
                daemon=True
            ).start()


def _handle_news_callback(chat_id: str, data: str):
    try:
        _, action, draft_id = data.split(":", 2)
    except ValueError:
        return

    draft = get_draft(draft_id)
    if not draft:
        send_message(chat_id, "⏰ 이미 처리되었거나 만료된 기사입니다.")
        return

    record = draft.get("record", {})
    dup = draft.get("duplicate")

    if action == "preview":
        # 다이제스트의 "N번 확인" 버튼. 이 draft를 session으로 넘기고 수동입력 플로우와
        # 동일한 미리보기+버튼(✅등록/🔄분류변경/✏️수정/❌취소/➕기존에추가)을 재사용.
        delete_draft(draft_id)
        collection = record.get("_collection", "mvno_issues")
        save_session(chat_id, {
            "status": "awaiting_confirmation",
            "draft": record,
            "collection": collection,
            "duplicate": dup,
        })

        from handlers.input_handler import _build_preview, _build_buttons
        preview = _build_preview(record)
        dup_notice = ""
        if dup:
            dup_notice = f"\n\n⚠️ <b>유사 이슈가 있습니다:</b>\n{dup['id']}\n{dup['summary']}\n기존 항목에 추가하려면 '추가'를 눌러주세요."
        buttons = _build_buttons(collection, bool(dup))
        send_message_with_buttons(chat_id, preview + dup_notice, buttons)


def _save_and_notify(chat_id: str, draft: dict, collection: str):
    try:
        doc_id = save_issue(draft, collection)
        if doc_id:
            send_message(chat_id, f"✅ <b>저장 완료!</b>\n📁 {collection}\n🆔 {doc_id}")
        else:
            send_message(chat_id, "❌ 저장 중 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"백그라운드 저장 오류: {e}", exc_info=True)
        send_message(chat_id, "❌ 저장 중 오류가 발생했습니다.")


def _append_and_notify(chat_id: str, dup: dict, new_record: dict):
    try:
        from handlers.firestore_writer import append_to_existing
        ok = append_to_existing(dup["id"], dup["collection"], new_record)
        if ok:
            send_message(chat_id, f"➕ <b>기존 항목에 추가 완료!</b>\n🆔 {dup['id']}")
        else:
            send_message(chat_id, "❌ 추가 중 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"백그라운드 추가 오류: {e}", exc_info=True)
        send_message(chat_id, "❌ 추가 중 오류가 발생했습니다.")