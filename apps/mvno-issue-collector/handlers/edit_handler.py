"""
handlers/edit_handler.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: 사용자 자유 수정 지시 처리
  · Gemini refine_with_edit() 호출 후 새 미리보기 출력
"""

import logging
from handlers.telegram import send_message, send_message_with_buttons
from handlers.gemini_refiner import refine_with_edit
from handlers.session import save_session

logger = logging.getLogger(__name__)


def handle_edit(chat_id: str, edit_instruction: str, session: dict):
    send_message(chat_id, "⏳ 수정 반영 중...")

    draft = session.get("draft", {})
    collection = session.get("collection", "mvno_issues")

    new_draft = refine_with_edit(draft, edit_instruction)
    if not new_draft:
        send_message(chat_id, "❌ 수정 처리 중 오류가 발생했습니다. 다시 시도해주세요.")
        return

    # 분류 변경 감지
    if new_draft.get("_collection") and new_draft["_collection"] != collection:
        collection = new_draft["_collection"]

    session["draft"] = new_draft
    session["collection"] = collection
    session["status"] = "awaiting_confirmation"
    save_session(chat_id, session)

    # 미리보기 재출력
    from handlers.input_handler import _build_preview, _build_buttons
    preview = _build_preview(new_draft)
    buttons = _build_buttons(collection, bool(session.get("duplicate")))
    send_message_with_buttons(chat_id, "✏️ <b>수정 완료! 확인해주세요:</b>\n\n" + preview, buttons)
