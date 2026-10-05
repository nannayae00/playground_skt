# report_builder.py
# YouTube Market Analyzer — Telegram 메시지 포맷터
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성
# v1.1 | 2025-03-26 | 마크다운 제거, 여론종합 제거
# v1.2 | 2025-03-28 | 댓글 0개 시 감성분석 섹션 숨김
# v1.3 | 2026-09-19 | 대표 댓글 불필요한 말줄임표(...) 제거, 분석 커버리지(전체 댓글 수 대비
#      | 분석 수) 표기 추가

from typing import Optional


def _sentiment_bar(ratio: dict) -> str:
    pos = ratio.get("긍정", 0)
    neg = ratio.get("부정", 0)
    neu = ratio.get("중립", 0)

    def bar(pct: int) -> str:
        filled = round(pct / 10)
        return "█" * filled + "░" * (10 - filled)

    return (
        f"🟢 긍정 {pos}%  {bar(pos)}\n"
        f"🔴 부정 {neg}%  {bar(neg)}\n"
        f"⚪ 중립 {neu}%  {bar(neu)}"
    )


def _fmt(n: int) -> str:
    if n >= 100_000_000: return f"{n/100_000_000:.1f}억"
    if n >= 10_000:      return f"{n/10_000:.1f}만"
    if n >= 1_000:       return f"{n/1_000:.1f}천"
    return str(n)


def _truncate(text: str, limit: int) -> str:
    """잘린 경우에만 말줄임표를 붙인다 (짧은 텍스트에 불필요한 ... 방지)."""
    return text[:limit] + "..." if len(text) > limit else text


def _coverage_label(analyzed: int, official_total: int) -> str:
    """전체 댓글 수(답글 포함, YouTube 통계 기준) 대비 실제 분석 수를 표기."""
    if official_total > analyzed > 0:
        return f"전체 {official_total}개 중 {analyzed}개 분석"
    return f"{analyzed}개"


def build_video_report(
    video_info: dict,
    summary: dict,
    comment_analysis: dict,
    index: int = 1,
) -> str:
    title    = video_info.get("title", "제목 없음")
    channel  = video_info.get("channel", "")
    pub      = video_info.get("published_at", "")
    views    = _fmt(video_info.get("view_count", 0))
    likes    = _fmt(video_info.get("like_count", 0))
    comments = _fmt(video_info.get("comment_count", 0))
    url      = video_info.get("url", "")

    # 요약
    lines    = summary.get("summary_lines", [])
    keywords = summary.get("keywords", [])
    insight  = summary.get("insight", "")
    has_tr   = summary.get("has_transcript", False)
    tr_note  = "" if has_tr else "\n⚠️ 자막 없음 — 설명문 기반 요약"

    summary_block = "\n".join([f"• {l}" for l in lines[:3]])
    kw_block      = "  ".join(keywords[:6]) if keywords else "—"

    sep = "━" * 30

    # 요약 섹션
    msg = (
        f"{sep}\n"
        f"🎬 영상 {index}\n"
        f"{title}\n"
        f"{url}\n\n"
        f"📺 {channel}  |  📅 {pub}\n"
        f"👁 {views}  👍 {likes}  💬 {comments}\n"
        f"{sep}\n"
        f"📝 핵심 요약{tr_note}\n"
        f"{summary_block}\n\n"
        f"🏷 키워드: {kw_block}\n\n"
        f"💡 {insight}\n"
        f"{sep}\n"
    )

    # 댓글 섹션 — 0개면 생략
    total = comment_analysis.get("total", 0)
    if total == 0:
        msg += "💬 댓글 없음\n"
    else:
        ratio    = comment_analysis.get("sentiment_ratio", {})
        sent_bar = _sentiment_bar(ratio)
        clusters = comment_analysis.get("clusters", [])
        emojis   = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
        cluster_block = ""
        for i, c in enumerate(clusters[:5]):
            label = c.get("label", "")
            rep   = _truncate(c.get("representative", ""), 60)
            count = c.get("count", 0)
            cluster_block += f"\n{emojis[i]} {label} ({count}건)\n   └ {rep}\n"

        key_issue = comment_analysis.get("key_issue", "")
        coverage  = _coverage_label(total, video_info.get("comment_count", 0))

        msg += (
            f"💬 댓글 감성 ({coverage})\n"
            f"{sent_bar}\n\n"
            f"🗂 주요 여론 클러스터{cluster_block}\n"
        )
        if key_issue:
            msg += f"📌 {key_issue}\n"

    msg += sep
    return msg


def build_search_header(keyword: str, count: int) -> str:
    return (
        f"🔍 '{keyword}' 검색 결과\n"
        f"최근 인기 영상 {count}개를 분석합니다. 잠시만 기다려주세요...\n"
        f"⏳ 영상당 약 20~40초 소요됩니다."
    )


def build_progress_message(index: int, total: int, title: str) -> str:
    bars = "▓" * index + "░" * (total - index)
    return f"⚙️ 분석 중... [{bars}] {index}/{total}\n📹 {title[:40]}..."


def build_link_detected_message(url: str) -> str:
    return "🔗 YouTube 링크 감지!\n📊 영상 분석을 시작합니다... (20~40초 소요)"


def build_error_message(context: str) -> str:
    return f"⚠️ 오류 발생: {context}\n다시 시도해주세요."


def build_rag_answer(question: str, answer: str) -> str:
    return f"🤖 질문: {question}\n\n💬 답변:\n{answer}"


def build_help_message() -> str:
    return (
        "🎬 YouTube Market Analyzer\n\n"
        "YouTube 링크 전송 — 자동 분석\n"
        "/search 키워드 — 키워드로 영상 검색 + 분석\n"
        "/ask 질문 — 최근 분석 영상 기반 질문\n"
        "/history — 최근 분석 영상 확인\n"
        "/help — 도움말"
    )