"""
main.py  v1.2
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30] 신규 생성
[v1.1 / 2026-07-02] webhook 즉시 200 반환 후 백그라운드 처리 (WORKER TIMEOUT 해결)
[v1.2 / 2026-07-02] update_id 기반 중복 처리 방지 (텔레그램 재전송 중복 등록 차단)
"""

import os
import logging
import threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify

from handlers.telegram import send_message, send_message_with_buttons, answer_callback
from handlers.input_handler import handle_message
from handlers.callback_handler import handle_callback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 최근 처리된 update_id 캐시 (메모리, 최대 200개)
_processed_updates: set = set()
_processed_lock = threading.Lock()
MAX_CACHE = 200


def _is_duplicate_update(update_id: int) -> bool:
    """같은 update_id 재전송 여부 확인"""
    with _processed_lock:
        if update_id in _processed_updates:
            return True
        _processed_updates.add(update_id)
        # 캐시 초과 시 오래된 것 제거 (간단히 전체 리셋)
        if len(_processed_updates) > MAX_CACHE:
            _processed_updates.clear()
            _processed_updates.add(update_id)
        return False


def _process_update(data: dict):
    """백그라운드에서 실제 처리"""
    try:
        if "callback_query" in data:
            handle_callback(data["callback_query"])
        elif "message" in data:
            handle_message(data["message"])
    except Exception as e:
        logger.error(f"update 처리 오류: {e}", exc_info=True)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": True})

    # update_id 중복 체크
    update_id = data.get("update_id")
    if update_id and _is_duplicate_update(update_id):
        logger.info(f"중복 update 무시: {update_id}")
        return jsonify({"ok": True})

    # 즉시 200 반환, 처리는 백그라운드
    threading.Thread(target=_process_update, args=(data,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/daily-report", methods=["POST", "GET"])
def daily_report():
    threading.Thread(
        target=lambda: __import__('handlers.summary', fromlist=['send_daily_report']).send_daily_report(),
        daemon=True
    ).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)