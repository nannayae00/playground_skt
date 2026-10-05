# main.py
# YouTube Market Analyzer — Telegram Webhook 봇 (Flask)
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성 — Polling 방식
# v1.1 | 2025-03-22 | 자연어 라우팅 추가
# v1.2 | 2025-03-26 | Webhook 방식 전환
# v1.3 | 2025-03-26 | 전용 이벤트 루프 스레드
# v1.4 | 2025-03-27 | 즉시 200 OK 반환 + 백그라운드 처리 (중복 실행 방지)

import os
import re
import logging
import asyncio
import threading
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from youtube_client import search_videos, get_video_info, get_comments, extract_video_id
from transcript_handler import get_transcript, summarize_video
from comment_analyzer import analyze_comments, save_analysis_to_firestore, query_analysis
from intent_router import route, INTENT_SEARCH, INTENT_ASK, INTENT_HISTORY, INTENT_HELP, INTENT_UNKNOWN
from report_builder import (
    build_video_report, build_search_header, build_progress_message,
    build_link_detected_message, build_error_message, build_rag_answer, build_help_message,
)

logging.basicConfig(format="%(asctime)s — %(name)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_IDS = os.environ.get("ALLOWED_CHAT_IDS", "").split(",")
WEBHOOK_URL      = os.environ.get("WEBHOOK_URL", "")

flask_app = Flask(__name__)

# 전용 이벤트 루프 — 백그라운드 스레드에서 영구 실행
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()
user_session: dict[int, dict] = {}

# 중복 처리 방지 — 처리 중인 update_id 추적
_processing: set = set()
_processing_lock = threading.Lock()


def is_allowed(chat_id: int) -> bool:
    if not ALLOWED_CHAT_IDS or ALLOWED_CHAT_IDS == [""]:
        return True
    return str(chat_id) in ALLOWED_CHAT_IDS


# ──────────────────────────────────────────────
# 분석 파이프라인
# ──────────────────────────────────────────────

async def _analyze_single_video(update, context, video_id, index=1, total=1, search_keyword=""):
    chat_id = update.effective_chat.id
    try:
        video_info = get_video_info(video_id)
        if not video_info:
            await context.bot.send_message(chat_id, "⚠️ 영상 정보를 가져올 수 없습니다.")
            return False

        video_info["search_keyword"] = search_keyword
        progress_msg = await context.bot.send_message(
            chat_id, build_progress_message(index, total, video_info["title"])
        )

        transcript       = await asyncio.to_thread(get_transcript, video_id)
        summary          = await asyncio.to_thread(summarize_video, video_info, transcript)
        summary["raw_transcript"] = transcript or ""
        comments         = await asyncio.to_thread(get_comments, video_id, 300, video_info.get("channel", ""))
        comment_analysis = await asyncio.to_thread(analyze_comments, video_id, video_info["title"], comments)
        doc_id           = await asyncio.to_thread(save_analysis_to_firestore, video_info, summary, comment_analysis)

        user_session[chat_id] = {
            "video_id": video_id,
            "doc_id": doc_id,
            "title": video_info["title"],
            "date_str": datetime.now(timezone.utc).strftime("%Y%m%d"),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

        try: await progress_msg.delete()
        except Exception: pass

        report = build_video_report(video_info, summary, comment_analysis, index=index)
        await context.bot.send_message(chat_id, report, disable_web_page_preview=False)

        if not search_keyword:
            await context.bot.send_message(
                chat_id,
                "💬 분석 완료! 궁금한 점은 자연어로 바로 물어보세요.\n"
                "예) 사람들이 QoS에 대해 어떻게 생각해?"
            )
        return True

    except Exception as e:
        logger.error(f"영상 분석 오류 ({video_id}): {e}", exc_info=True)
        await context.bot.send_message(chat_id, build_error_message(str(e)[:100]))
        return False


async def _do_search(update, context, keyword):
    chat_id = update.effective_chat.id
    header  = await update.message.reply_text(build_search_header(keyword, 3))
    videos  = await asyncio.to_thread(search_videos, keyword, 3)
    if not videos:
        await header.edit_text(f"⚠️ '{keyword}'에 대한 영상을 찾을 수 없습니다.")
        return
    await header.edit_text(f"🔍 '{keyword}' — 영상 {len(videos)}개 분석 중...")
    success = 0
    for i, v in enumerate(videos, 1):
        ok = await _analyze_single_video(update, context, v["video_id"], i, len(videos), keyword)
        if ok: success += 1
    await context.bot.send_message(chat_id, f"✅ 분석 완료! ({success}/{len(videos)}개)")


async def _do_ask(update, context, question):
    chat_id = update.effective_chat.id
    session = user_session.get(chat_id)
    if not session:
        await update.message.reply_text("⚠️ 먼저 영상을 분석해주세요.")
        return
    thinking = await update.message.reply_text(f"🤔 분석 중...\n📹 {session['title'][:50]}")
    answer   = await asyncio.to_thread(query_analysis, session["video_id"], question, session["date_str"])
    try: await thinking.delete()
    except Exception: pass
    await context.bot.send_message(chat_id, build_rag_answer(question, answer))


async def _do_history(update, context):
    chat_id = update.effective_chat.id
    session = user_session.get(chat_id)
    if not session:
        await update.message.reply_text("📭 최근 분석한 영상이 없습니다.")
        return
    await update.message.reply_text(
        f"📋 최근 분석 영상\n\n🎬 {session['title']}\n🕐 {session['analyzed_at'][:19]} UTC"
    )


# ──────────────────────────────────────────────
# 핸들러
# ──────────────────────────────────────────────

async def cmd_start(update, context):
    if not is_allowed(update.effective_chat.id): return
    await update.message.reply_text(build_help_message())

async def cmd_help(update, context):
    if not is_allowed(update.effective_chat.id): return
    await update.message.reply_text(build_help_message())

async def cmd_search(update, context):
    if not is_allowed(update.effective_chat.id): return
    keyword = " ".join(context.args).strip() if context.args else ""
    if not keyword:
        await update.message.reply_text("❗ 키워드를 입력해주세요.\n예) /search 알뜰폰 요금제")
        return
    await _do_search(update, context, keyword)

async def cmd_ask(update, context):
    if not is_allowed(update.effective_chat.id): return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("❗ 질문을 입력해주세요.")
        return
    await _do_ask(update, context, question)

async def cmd_history(update, context):
    if not is_allowed(update.effective_chat.id): return
    await _do_history(update, context)


YOUTUBE_URL_PATTERN = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)\S+")

async def handle_message(update, context):
    if not is_allowed(update.effective_chat.id): return
    text = update.message.text or ""

    match = YOUTUBE_URL_PATTERN.search(text)
    if match:
        url      = match.group(0)
        video_id = extract_video_id(url)
        if not video_id:
            await update.message.reply_text("⚠️ YouTube 링크에서 영상 ID를 추출할 수 없습니다.")
            return
        await update.message.reply_text(build_link_detected_message(url))
        await _analyze_single_video(update, context, video_id=video_id)
        return

    if len(text.strip()) < 4: return

    routing_msg   = await update.message.reply_text("🧠 이해 중...")
    intent_result = await asyncio.to_thread(route, text)
    intent        = intent_result.get("intent", INTENT_UNKNOWN)

    try: await routing_msg.delete()
    except Exception: pass

    if intent == INTENT_SEARCH:
        keyword = intent_result.get("keyword") or text.strip()
        await update.message.reply_text(f"🔍 '{keyword}' 로 YouTube를 검색할게요!")
        await _do_search(update, context, keyword)
    elif intent == INTENT_ASK:
        await _do_ask(update, context, intent_result.get("refined_question") or text.strip())
    elif intent == INTENT_HISTORY:
        await _do_history(update, context)
    elif intent == INTENT_HELP:
        await update.message.reply_text(build_help_message())
    else:
        await update.message.reply_text(
            "🤔 무엇을 도와드릴까요?\n\n"
            "• YouTube 링크를 보내면 자동 분석\n"
            "• 알뜰폰 요금제 영상 찾아줘 — 키워드 검색\n"
            "• 사람들 반응이 어때? — 분석 데이터 질문\n"
            "• /help — 사용법"
        )


# ──────────────────────────────────────────────
# Flask Webhook — 즉시 200 OK + 백그라운드 처리
# ──────────────────────────────────────────────

@flask_app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data      = request.get_json(force=True)
    update_id = data.get("update_id", 0)

    # 중복 처리 방지
    with _processing_lock:
        if update_id in _processing:
            logger.info(f"중복 update_id {update_id} 무시")
            return jsonify({"ok": True}), 200
        _processing.add(update_id)

    # 즉시 200 OK 반환 후 백그라운드에서 처리
    def process_in_background():
        try:
            update = Update.de_json(data, ptb_app.bot)
            future = asyncio.run_coroutine_threadsafe(ptb_app.process_update(update), _loop)
            future.result(timeout=600)
        except Exception as e:
            logger.error(f"백그라운드 처리 오류: {e}", exc_info=True)
        finally:
            with _processing_lock:
                _processing.discard(update_id)

    threading.Thread(target=process_in_background, daemon=True).start()
    return jsonify({"ok": True}), 200  # 즉시 반환


# ──────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────

def init():
    ptb_app.add_handler(CommandHandler("start",   cmd_start))
    ptb_app.add_handler(CommandHandler("help",    cmd_help))
    ptb_app.add_handler(CommandHandler("search",  cmd_search))
    ptb_app.add_handler(CommandHandler("ask",     cmd_ask))
    ptb_app.add_handler(CommandHandler("history", cmd_history))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def _init():
        await ptb_app.initialize()
        if WEBHOOK_URL:
            await ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
            logger.info(f"Webhook 설정: {WEBHOOK_URL}/webhook")

    asyncio.run_coroutine_threadsafe(_init(), _loop).result(timeout=30)
    logger.info("YouTube Market Analyzer Bot 시작됨 (v1.4 — 즉시응답 + 중복방지)")


if __name__ == "__main__":
    init()
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, threaded=True)