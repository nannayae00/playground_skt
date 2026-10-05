# =============================================================================
# main.py - 텔레그램 파일 → 사내 이메일 브릿지
# =============================================================================
# [수정 이력]
# v1.0 | 2026-03-17 | 최초 작성
#   - 텔레그램 봇 파일 수신 → Gmail SMTP → 사내메일 발송
#   - 화이트리스트 기반 접근 제어 (내 텔레그램 ID만)
#   - 모든 파일 형식 지원
#   - Cloud Run 배포용 (Flask + Webhook)
# v1.1 | 2026-03-17 | 사진 묶음 발송 지원
#   - media_group_id 감지 → 3초 대기 후 한 메일에 전체 첨부
#   - 단일 파일은 기존과 동일하게 즉시 발송
# v1.2 | 2026-03-20 | Webhook 즉시 응답 + 백그라운드 처리
#   - 대용량 파일 처리 시 텔레그램 재시도 루프 버그 수정
#   - Webhook 수신 즉시 200 OK 반환, 처리는 백그라운드 스레드
# v1.3 | 2026-03-24 | 파일명 + MIME 타입 수정
#   - 사진/동영상 등 파일명 없는 경우 확장자 포함 파일명 자동 생성
#   - 첨부파일 MIME 타입 명시로 Gmail noname 버그 수정
# =============================================================================

import os
import logging
import mimetypes
import smtplib
import threading
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── 환경변수 ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_WEBHOOK_URL = os.environ["TELEGRAM_WEBHOOK_URL"]
ALLOWED_USER_IDS     = set(int(x) for x in os.environ["ALLOWED_USER_IDS"].split(","))

GMAIL_ADDRESS        = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD   = os.environ["GMAIL_APP_PASSWORD"]
OFFICE_MAIL          = os.environ["OFFICE_MAIL"]

TELEGRAM_API         = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ── Media Group 버퍼 ──────────────────────────────────────────────────────────
media_group_buffer: dict = {}
media_group_lock = threading.Lock()
MEDIA_GROUP_WAIT = 3  # 초

# ── MIME 타입 매핑 ─────────────────────────────────────────────────────────────
MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".mp3":  "audio/mpeg",
    ".ogg":  "audio/ogg",
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip":  "application/zip",
}

def get_mime_type(file_name: str) -> tuple[str, str]:
    """(maintype, subtype) 반환 - 예: ('image', 'jpeg')"""
    ext = os.path.splitext(file_name)[1].lower()
    mime = MIME_MAP.get(ext) or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    maintype, subtype = mime.split("/", 1)
    return maintype, subtype


# ── 텔레그램 메시지 발송 ───────────────────────────────────────────────────────
def send_tg_message(chat_id: int, text: str):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"텔레그램 메시지 전송 실패: {e}")


# ── 파일 다운로드 ──────────────────────────────────────────────────────────────
def download_file(file_id: str) -> tuple:
    r = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=10)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    file_name = file_path.split("/")[-1]
    file_r = requests.get(
        f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}",
        timeout=120
    )
    file_r.raise_for_status()
    return file_r.content, file_name


# ── 첨부파일 MIME part 생성 ────────────────────────────────────────────────────
def make_attachment(file_bytes: bytes, file_name: str) -> MIMEBase:
    maintype, subtype = get_mime_type(file_name)
    part = MIMEBase(maintype, subtype)
    part.set_payload(file_bytes)
    encoders.encode_base64(part)
    # RFC2231 인코딩으로 한글 파일명 깨짐 방지
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", file_name)
    )
    return part


# ── Gmail SMTP 단일 파일 발송 ──────────────────────────────────────────────────
def send_email_single(file_bytes: bytes, file_name: str, caption: str = ""):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = OFFICE_MAIL
    msg["Subject"] = f"[TG→메일] {file_name}"

    body = caption if caption else f"텔레그램에서 전송된 파일입니다.\n\n파일명: {file_name}"
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(make_attachment(file_bytes, file_name))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, OFFICE_MAIL, msg.as_string())

    logger.info(f"단일 메일 발송 완료 → {OFFICE_MAIL} | {file_name}")


# ── Gmail SMTP 묶음 파일 발송 ──────────────────────────────────────────────────
def send_email_group(files: list, caption: str = ""):
    count = len(files)
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = OFFICE_MAIL
    msg["Subject"] = f"[TG→메일] 파일 {count}개 묶음"

    file_list = "\n".join(f"  • {f['name']}" for f in files)
    body = caption if caption else f"텔레그램에서 전송된 파일 묶음입니다.\n\n총 {count}개 파일:\n{file_list}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for f in files:
        msg.attach(make_attachment(f["bytes"], f["name"]))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, OFFICE_MAIL, msg.as_string())

    logger.info(f"묶음 메일 발송 완료 → {OFFICE_MAIL} | {count}개 파일")


# ── Media Group 타이머 만료 → 묶음 발송 ───────────────────────────────────────
def flush_media_group(group_id: str):
    with media_group_lock:
        group = media_group_buffer.pop(group_id, None)
    if not group:
        return

    chat_id    = group["chat_id"]
    caption    = group["caption"]
    file_infos = group["files"]

    send_tg_message(chat_id, f"⏳ 파일 {len(file_infos)}개 묶음 처리 중...")

    try:
        downloaded = []
        for idx, info in enumerate(file_infos, 1):
            file_bytes, actual_name = download_file(info["file_id"])
            name = info["file_name"]
            # photo 타입은 파일명 없으므로 실제 다운로드된 확장자 사용
            if name == "photo.jpg":
                ext = os.path.splitext(actual_name)[1] or ".jpg"
                name = f"photo_{idx}{ext}"
            downloaded.append({"bytes": file_bytes, "name": name})

        send_email_group(downloaded, caption)
        send_tg_message(chat_id,
            f"✅ 묶음 메일 발송 완료!\n"
            f"📎 파일 {len(downloaded)}개 첨부\n"
            f"📧 수신: {OFFICE_MAIL}"
        )
    except Exception as e:
        logger.error(f"묶음 처리 실패: {e}", exc_info=True)
        send_tg_message(chat_id, f"❌ 오류 발생\n{str(e)}")


# ── 단일 파일 백그라운드 처리 ──────────────────────────────────────────────────
def process_single_file(chat_id: int, file_id: str, file_name: str, caption: str):
    send_tg_message(chat_id, f"⏳ 처리 중...\n📄 {file_name}")
    try:
        file_bytes, actual_name = download_file(file_id)
        # photo 타입은 실제 다운로드 확장자 사용
        if file_name == "photo.jpg":
            ext = os.path.splitext(actual_name)[1] or ".jpg"
            final_name = f"photo{ext}"
        else:
            final_name = file_name
        send_email_single(file_bytes, final_name, caption)
        send_tg_message(chat_id,
            f"✅ 메일 발송 완료!\n"
            f"📄 파일: {final_name}\n"
            f"📧 수신: {OFFICE_MAIL}"
        )
    except Exception as e:
        logger.error(f"처리 실패: {e}", exc_info=True)
        send_tg_message(chat_id, f"❌ 오류 발생\n{str(e)}")


# ── 파일 정보 추출 ─────────────────────────────────────────────────────────────
def extract_file_info(message: dict) -> tuple:
    caption = message.get("caption", "")

    if "document" in message:
        doc = message["document"]
        return doc["file_id"], doc.get("file_name", "document"), caption
    if "photo" in message:
        photo = message["photo"][-1]
        return photo["file_id"], "photo.jpg", caption
    if "video" in message:
        v = message["video"]
        return v["file_id"], v.get("file_name", "video.mp4"), caption
    if "audio" in message:
        a = message["audio"]
        return a["file_id"], a.get("file_name", "audio.mp3"), caption
    if "voice" in message:
        return message["voice"]["file_id"], "voice.ogg", caption
    if "sticker" in message:
        return message["sticker"]["file_id"], "sticker.webp", caption

    return None, None, caption


# ── Webhook 엔드포인트 ─────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": True})

    message = data.get("message") or data.get("edited_message")
    if not message:
        return jsonify({"ok": True})

    chat_id   = message["chat"]["id"]
    user_id   = message["from"]["id"]
    user_name = message["from"].get("first_name", "Unknown")

    if user_id not in ALLOWED_USER_IDS:
        logger.warning(f"허가되지 않은 접근: user_id={user_id}, name={user_name}")
        threading.Thread(target=send_tg_message, args=(chat_id, "❌ 권한이 없습니다."), daemon=True).start()
        return jsonify({"ok": True})

    text = message.get("text", "")

    if text == "/start":
        def _start():
            send_tg_message(chat_id,
                "📬 텔레그램 → 사내 이메일 브릿지\n\n"
                "파일을 이 채팅에 보내면 사내 메일로 자동 전송됩니다.\n"
                f"📧 수신: {OFFICE_MAIL}\n\n"
                "• 모든 파일 형식 지원\n"
                "• 사진 여러 장 → 한 메일에 묶어서 발송\n"
                "• 파일과 함께 메모 입력 시 메일 본문에 포함"
            )
        threading.Thread(target=_start, daemon=True).start()
        return jsonify({"ok": True})

    if text == "/status":
        def _status():
            send_tg_message(chat_id,
                "✅ 봇 정상 작동 중\n"
                f"📧 발신: {GMAIL_ADDRESS}\n"
                f"📥 수신: {OFFICE_MAIL}"
            )
        threading.Thread(target=_status, daemon=True).start()
        return jsonify({"ok": True})

    file_id, file_name, caption = extract_file_info(message)
    if not file_id:
        if text and not text.startswith("/"):
            threading.Thread(
                target=send_tg_message,
                args=(chat_id, "📎 파일을 첨부해서 보내주세요.\n텍스트만으로는 메일을 보낼 수 없습니다."),
                daemon=True
            ).start()
        return jsonify({"ok": True})

    group_id = message.get("media_group_id")

    if group_id:
        with media_group_lock:
            if group_id not in media_group_buffer:
                media_group_buffer[group_id] = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "files": [],
                    "timer": None,
                }
            media_group_buffer[group_id]["files"].append({
                "file_id": file_id,
                "file_name": file_name,
            })
            if caption:
                media_group_buffer[group_id]["caption"] = caption

            old_timer = media_group_buffer[group_id]["timer"]
            if old_timer:
                old_timer.cancel()

            timer = threading.Timer(MEDIA_GROUP_WAIT, flush_media_group, args=[group_id])
            media_group_buffer[group_id]["timer"] = timer
            timer.start()

        return jsonify({"ok": True})

    # 단일 파일 → 백그라운드 처리
    threading.Thread(
        target=process_single_file,
        args=(chat_id, file_id, file_name, caption),
        daemon=True
    ).start()
    return jsonify({"ok": True})


# ── Webhook 등록 ───────────────────────────────────────────────────────────────
@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    r = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": f"{TELEGRAM_WEBHOOK_URL}/webhook"})
    return jsonify(r.json())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)