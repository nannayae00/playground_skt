"""
handlers/input_handler.py  v1.1
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30] 신규 생성
[v1.1 / 2026-07-02] URL 크롤링 추가: 기사 URL 감지 시 본문 자동 추출 후 Gemini 정제
                     · BeautifulSoup으로 본문 파싱 (article > p 태그 우선)
                     · 유튜브 URL은 기존 Transcript API 방식 유지
                     · 크롤링 실패 시 원본 텍스트로 fallback
"""

import logging
import base64
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from handlers.telegram import send_message, send_message_with_buttons, download_file
from handlers.gemini_refiner import refine_input
from handlers.session import save_session, get_session
from handlers.duplicate_checker import check_duplicate

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s]+')


def _fetch_article(url: str) -> str | None:
    """기사 URL에서 본문 텍스트 추출"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # [수정 20261005] 두 가지 버그 수정.
        # (1) 기존엔 셀렉터를 순서대로 시도하며 매번 content를 덮어써서, 200자를
        #     못 넘기면 "마지막으로 매칭된 셀렉터의 결과"가 최종값이 되는 문제가
        #     있었음 - 매 셀렉터의 결과 중 "가장 긴" 것을 최종 채택하도록 수정.
        # (2) [진짜 원인] 네이버뉴스는 본문을 <article id="dic_area">가 정확히
        #     감싸고 있어서 1번째 셀렉터("article")가 맞게 찾는데도, 본문 텍스트가
        #     <p> 태그 없이 순수 텍스트+<br>로만 들어있어서 find_all("p")가 0개를
        #     반환 → candidate가 빈 문자열이 돼서 그 좋은 매칭을 버리고 다음(엉뚱한)
        #     셀렉터로 넘어가 기자정보/저작권 박스를 줍게 됨(실무자 보고 증상과
        #     정확히 일치, 실제 URL로 재현 확인함). <p> 기반 추출이 너무 짧으면
        #     해당 요소의 전체 텍스트(get_text)로 폴백하도록 수정.
        content = ""
        for selector in ["article", "main", "[class*='article']", "[class*='content']", "[class*='news']"]:
            el = soup.select_one(selector)
            if el:
                paragraphs = el.find_all("p")
                candidate = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
                if len(candidate) < 200:
                    raw = el.get_text(separator="\n", strip=True)
                    if len(raw) > len(candidate):
                        candidate = raw
                if len(candidate) > len(content):
                    content = candidate
                if len(content) > 200:
                    break

        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)

        return content[:4000] if content else None

    except Exception as e:
        logger.warning(f"URL 크롤링 실패 ({url}): {e}")
        return None


def handle_message(message: dict):
    chat_id = str(message["chat"]["id"])
    user_name = message.get("from", {}).get("first_name", "")
    text = message.get("text", "")
    caption = message.get("caption", "")

    if text.startswith("/summary"):
        from handlers.summary import build_summary
        summary_text = build_summary()
        send_message(chat_id, summary_text)
        return

    if text.startswith("/cancel"):
        save_session(chat_id, None)
        send_message(chat_id, "✅ 현재 입력 세션이 취소되었습니다.")
        return

    session = get_session(chat_id)
    if session and session.get("status") == "awaiting_edit":
        from handlers.edit_handler import handle_edit
        handle_edit(chat_id, text, session)
        return

    if "photo" in message:
        _handle_photo(chat_id, message, caption or text)
        return

    if text:
        _handle_text(chat_id, text, user_name)
        return

    send_message(chat_id, "📎 텍스트, 사진, URL을 보내주세요.")


def _handle_text(chat_id: str, text: str, user_name: str):
    send_message(chat_id, "⏳ 분석 중입니다...")

    raw_input = text
    image_b64 = None

    # 유튜브 URL
    if "youtube.com/watch" in text or "youtu.be/" in text:
        youtube_text = _fetch_youtube_transcript(text)
        if youtube_text:
            raw_input = f"[유튜브 자막]\n{youtube_text}"
        else:
            send_message(chat_id, "⚠️ 유튜브 자막을 가져올 수 없습니다. 내용을 직접 붙여넣어 주세요.")
            return

    # 일반 URL 크롤링
    elif URL_PATTERN.search(text):
        urls = URL_PATTERN.findall(text)
        extra_text = URL_PATTERN.sub("", text).strip()  # URL 제외한 나머지 텍스트

        crawled_parts = []
        for url in urls[:2]:  # 최대 2개 URL만 크롤링
            article_text = _fetch_article(url)
            if article_text:
                crawled_parts.append(f"[크롤링: {url}]\n{article_text}")
                logger.info(f"크롤링 성공: {url} ({len(article_text)}자)")
            else:
                crawled_parts.append(f"[URL: {url}]")

        if crawled_parts:
            raw_input = "\n\n".join(crawled_parts)
            if extra_text:
                raw_input = f"[사용자 메모: {extra_text}]\n\n" + raw_input

    _process_and_send_preview(chat_id, raw_input, image_b64, user_name)


def _handle_photo(chat_id: str, message: dict, extra_text: str):
    send_message(chat_id, "⏳ 이미지 분석 중입니다...")

    photo = message["photo"][-1]
    file_bytes = download_file(photo["file_id"])
    image_b64 = base64.b64encode(file_bytes).decode("utf-8")

    raw_input = extra_text or "[이미지 입력]"
    user_name = message.get("from", {}).get("first_name", "")

    _process_and_send_preview(chat_id, raw_input, image_b64, user_name)


def _process_and_send_preview(chat_id: str, raw_input: str, image_b64: str | None, user_name: str):
    result = refine_input(raw_input, image_b64)
    if not result:
        send_message(chat_id, "❌ 정제 실패. 다시 시도해주세요.")
        return

    records = result if isinstance(result, list) else [result]

    for record in records:
        record["input_by"] = {"display_name": user_name}

        dup = check_duplicate(record)
        dup_notice = ""
        if dup:
            dup_notice = f"\n\n⚠️ <b>유사 이슈가 있습니다:</b>\n{dup['id']}\n{dup['summary']}\n기존 항목에 추가하려면 '추가'를 눌러주세요."

        preview = _build_preview(record)
        collection = record.get("_collection", "mvno_issues")

        save_session(chat_id, {
            "status": "awaiting_confirmation",
            "draft": record,
            "collection": collection,
            "duplicate": dup,
        })

        buttons = _build_buttons(collection, bool(dup))
        send_message_with_buttons(chat_id, preview + dup_notice, buttons)


def _build_preview(record: dict) -> str:
    collection = record.get("_collection", "mvno_issues")
    coll_label = "📋 이슈" if collection == "mvno_issues" else "📊 프로모션현황"

    if collection == "mvno_issues":
        lines = [
            f"<b>{coll_label}로 등록할까요?</b>",
            f"",
            f"📅 <b>이벤트 일자:</b> {record.get('event_date', '-')}",
            f"🏷 <b>카테고리:</b> {record.get('category', '-')}",
            f"📡 <b>망:</b> {record.get('network', '-')}",
            f"⚡ <b>영향 즉시성:</b> {record.get('impact_timing', '-')}",
            f"📊 <b>영향 수준:</b> {record.get('impact_level', '-')}",
            f"🎯 <b>영향 방향:</b> {', '.join(record.get('impact_direction', []))}",
            f"",
            f"📝 <b>요약:</b>",
            f"{record.get('summary', '-')}",
            f"",
            f"💡 <b>당사 시사점:</b>",
            # [수정 20261005] 200자 하드컷 제거 - 텔레그램 메시지 한도(4096자)는
            # 충분히 여유 있고, implication이 잘려 보이는 게 "분석이 부실하다"는
            # 오해를 줬음(실무자 지적). 전체 노출.
            f"{record.get('implication', '-')}",
        ]
        if record.get("follow_up"):
            lines += [f"", f"✅ <b>Follow-up:</b> {record['follow_up']}"]
        if record.get("confidential"):
            lines += [f"", f"🔒 <b>보안 이슈</b>"]
    else:
        providers = record.get("providers", {})
        provider_lines = []
        for k, v in providers.items():
            amt = v.get('max_amount')
            amt_str = f"최대 {amt}만원" if amt else ""
            prev = v.get('prev_amount')
            change = f" (↑{amt-prev}만원)" if amt and prev and amt > prev else ""
            provider_lines.append(f"  • <b>{k}</b>: {amt_str}{change}")
            # details 최대 3개까지 표시
            for d in (v.get('details') or [])[:3]:
                provider_lines.append(f"    └ {d}")

        lines = [
            f"<b>{coll_label}로 등록할까요?</b>",
            f"",
            f"📅 <b>기준일:</b> {record.get('snapshot_date', '-')}",
            f"",
            f"<b>사업자별 혜택:</b>",
        ] + provider_lines

    return "\n".join(lines)


def _build_buttons(collection: str, has_duplicate: bool) -> list:
    alt_collection = "promotion" if collection == "mvno_issues" else "mvno_issues"
    alt_label = "📊 프로모션으로" if collection == "mvno_issues" else "📋 이슈로"

    row1 = [
        {"text": "✅ 등록", "callback_data": f"confirm:{collection}"},
        {"text": f"🔄 {alt_label}", "callback_data": f"reclassify:{alt_collection}"},
    ]
    row2 = [
        {"text": "✏️ 수정", "callback_data": "edit"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]
    buttons = [row1, row2]

    if has_duplicate:
        buttons.append([{"text": "➕ 기존 항목에 추가", "callback_data": "append_to_dup"}])

    return buttons


def _fetch_youtube_transcript(url: str) -> str | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
        if not match:
            return None
        video_id = match.group(1)
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])
        return " ".join([t["text"] for t in transcript])[:4000]
    except Exception as e:
        logger.warning(f"유튜브 자막 추출 실패: {e}")
        return None