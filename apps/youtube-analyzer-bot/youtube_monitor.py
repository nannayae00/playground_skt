# youtube_monitor.py
# YouTube Market Analyzer — MVNO 영상 센싱 (Cloud Run Job)
# 하루 3회 실행: 08:00 / 13:00 / 20:00 KST
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성 — 센싱 + 알림만
# v1.1 | 2025-03-26 | 신규 영상 발견 시 요약+댓글분석 자동 실행, 메시지 1장 통합
# v1.2 | 2025-03-28 | 댓글 0개 시 섹션 숨김, 키워드 3개로 축소, max_results=30, days=14
# v1.3 | 2025-03-31 | 요약 실패 시 섹션 숨김, f-string 백슬래시 오류 수정
# v1.4 | 2025-03-31 | 구분선 제거, 영상보기 링크 제거, 요약 없을 때 감성 기반 자동 요약
# v1.5 | 2025-03-31 | 팀 단체방 동시 전송 (TELEGRAM_TEAM_CHAT_ID)
# v1.6 | 2026-06-15 | 트렌드 이슈 키워드 검색 추가 (통합요금제/5G SA/최적요금제 등)
#       | - TREND_MONITOR_KEYWORDS: MVNO 직접언급 없는 바이럴 콘텐츠 센싱
#       | - filter_trend_videos(): detect_trend_issues() 기반 필터링
#       | - 리포트에 🔥 트렌드 이슈 태그 표시
# v1.7 | 2026-06-15 | 트렌드 태그 미표시 버그 수정
#       | - filter_mvno_videos()에서도 detect_trend_issues() 체크
#       | - MVNO 키워드로 먼저 잡힌 영상도 트렌드 이슈가 있으면 _trend_issues 부여
#       | - MVNO/트렌드 키워드 어느 경로로 잡히든 헤더·🔥태그 정확히 표시됨
#       | - get_video_info() 반환값에 _trend_issues 복사 (핵심 원인이었음)
# v1.8 | 2026-06-15 | 댓글 전체수/분석수 표시 추가
#       | - video["comment_count"](전체, 답글포함) vs 분석된 댓글수 비교 표시
#       | - 차이가 있으면 "댓글 N개 중 M개 샘플링 분석" 형태로 안내
#       | - get_comments()는 최상위 댓글만 가져오므로(API 특성),
#       |   전체수와 차이는 주로 답글(replies) 분량
# v1.9 | 2026-09-19 | get_comments()가 답글도 함께 수집하도록 바뀌어 "(답글 제외)"
#       | 라벨이 더는 사실이 아니므로 제거. 그래도 차이가 남으면(다건 답글 스레드 등
#       | API가 일부만 반환하는 경우) 여전히 "N개 중 M개 분석"으로 투명하게 표시
# v2.0 | 2026-09-19 | 키워드별 관련도순(relevance) + 최신순(date) 검색 병행.
#       | relevance 단독으로는 막 올라와 조회수/좋아요가 적은 신규 영상이 순위
#       | 밖으로 밀려 검색 결과에 아예 안 잡히는 문제가 있었음 (쿼터 사용량 2배)
# v2.1 | 2026-09-19 | 14일 지난 영상도 조회수 IMPORTANT_VIEW_THRESHOLD 이상이면
#       | "놓쳤던 주요 뉴스"로 리포트 (기존엔 그냥 seen 처리만 되고 조용히 묻힘)
#       | MONITOR_KEYWORDS에 T다이렉트샵/SKT 에어 요금제 추가
# v2.2 | 2026-09-19 | YouTube API 쿼터 초과 시 조용히 빈 결과로 넘어가지 않고
#       | QuotaExceededError를 잡아 텔레그램으로 즉시 알림 후 이번 실행을 중단.
#       | 이전엔 쿼터가 다 떨어지면 그날 센싱이 통째로 안 되는데 아무도 몰랐음
# v2.3 | 2026-09-19 | 쿼터 재배분: 트렌드 키워드는 관련도순 1회만 검색(절감),
#       | MONITOR_KEYWORDS에 스마텔/토스모바일/헬로모바일/리브엠 추가(재투자).
#       | 순증가는 하루 +300유닛 수준으로 거의 비용 중립
# v2.4 | 2026-09-19 | 요청에 따라 일반 MVNO(스마텔/토스모바일)는 빼고 자회사
#       | 중심으로 재정리 — SUBSIDIARY_KEYWORDS 신설(헬로모바일/헬로비전/리브엠/
#       | 텔링크/유모바일/엠모바일, 관련도순 1회). TREND_MONITOR_KEYWORDS에
#       | 너겟(LGU+)/요고(KT) 추가. all_keyword_sets에 검색 순서(dual/single)를
#       | kw_type과 분리해 자회사 키워드는 "mvno" 필터를 타면서도 단일검색 가능하게 함
# v2.5 | 2026-09-19 | 온라인 다이렉트 채널을 트렌드 키워드에서 분리해
#       | ONLINE_CHANNEL_KEYWORDS로 독립 (T다이렉트샵/SKT 에어/너겟/요고,
#       | 대쉬보드의 "온라인" 카테고리와 동일 축). 리포트 헤더도
#       | "📺 온라인 채널 소식"으로 구분 표시해 일반 트렌드 이슈와 섞이지 않게 함
# v2.6 | 2026-09-19 | Gemini API 호출 다수 실패 시 텔레그램 알림 추가.
#       | comment_analyzer.GEMINI_STATS로 감성분석 성공/실패 횟수를 추적해,
#       | 실패해도 "중립"으로 조용히 채워지느라 API 키/크레딧 문제를 아무도
#       | 못 알아채는 상황(쿼터 초과와 동일한 패턴)을 방지
# v2.7 | 2026-09-20 | 신규 영상마다 전체 리포트를 보내던 방식 → 한 번의 실행에서
#       | 발견된 신규 영상을 조회수순 압축 목록 한 장으로 먼저 보여주고, 상위
#       | TOP_DETAIL_COUNT(5)개만 전체 분석(자막 요약+댓글 감성) 리포트를 이어서
#       | 전송. 키워드가 늘면서 신규가 몰릴 때 채널 도배 방지 + 사소한 영상까지
#       | Gemini로 분석하던 비용 절감. (덤으로 클러스터 대표 댓글의 불필요한
#       | "..." 도 재수정 — 이전 커밋에서 prod 소스로 덮어쓰며 유실됐던 부분)
# v2.8 | 2026-09-20 | 압축 목록 + 급상승 알림 + 최종 요약, 세 개로 나눠 보내던
#       | 메시지를 "🔥 핫글 / 🆕 신규추가 / 📈 급등" 섹션의 요약 메시지 하나로
#       | 통합 (build_run_summary). 제목에 YouTube 링크를 HTML 하이퍼링크로
#       | 걸어서 바로 클릭 가능하게 함 (parse_mode="HTML", html.escape로 이스케이프)
# v2.9 | 2026-09-20 | 요약 맨 위에 이번에 잡힌 신규 영상들의 발행일 범위 표시
#       | (예: "📅 발행일 범위: 2026-02-20 ~ 2026-09-19") — 오래된 영상이 섞여
#       | 신규 건수가 튀는 건지(키워드 신규 추가 직후 백로그 등) 바로 알 수 있게
# v3.0 | 2026-09-20 | 온라인 채널 키워드로 잡힌 SKT/KT/LG U+ 공식 채널 영상은
#       | 전체 분석(상세 리포트) 대상에서 제외 — 조회수가 압도적으로 커서
#       | TOP_DETAIL_COUNT를 항상 독차지해 소규모 MVNO 채널이 상세분석을 못 받는
#       | 문제가 있었음. 요약(핫글/신규추가) 목록에는 그대로 남음
# v3.1 | 2026-09-21 | 핫글/신규추가 선정 기준 수정 (실사용 피드백 - 2020/2021년
#       | 영상이 핫글 1위로 뜨고, 신규추가엔 조회수 0~수백대 자잘한 영상까지 나옴).
#       | 원인: IMPORTANT_VIEW_THRESHOLD로 잡힌 "놓쳤던 뉴스"(발행일 무관, 누적
#       | 조회수만 기준)가 신규 영상과 같은 풀에서 조회수로만 정렬돼서, 몇 년 된
#       | 영상의 누적 조회수가 최근 영상을 밀어냄. 핫글은 HOT_WINDOW_DAYS(30일)
#       | 이내 발행분만 순위 대상으로 제한, 신규추가는 NEW_ADDED_MIN_VIEWS(1000)
#       | 미만 제외. 대상에서 빠진 "놓쳤던 뉴스"도 mark_seen은 그대로 되어
#       | 다음 실행에 다시 잡히진 않음(상세분석도 더는 안 나감)

import os
import html
import logging
from datetime import datetime, timezone, timedelta

import google.generativeai as genai
from google.cloud import firestore
from telegram import Bot
import asyncio

from youtube_client import search_videos, get_video_info, get_comments, QuotaExceededError
from transcript_handler import get_transcript, summarize_video
from comment_analyzer import analyze_comments, save_analysis_to_firestore, get_gemini_stats
from mvno_classifier import classify_post, detect_trend_issues

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_TEAM_CHAT_ID = os.environ.get("TELEGRAM_TEAM_CHAT_ID", "")  # 팀 단체방
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

db = firestore.Client(database="mvno-data")
SEEN_COLLECTION   = "youtube_seen_videos"
RESULT_COLLECTION = "youtube_monitor_logs"

MONITOR_KEYWORDS = [
    "알뜰폰",
    "MVNO 유심",
    "유심 요금제",
]

# [v2.4] MNO 자회사/금융계열 MVNO — mvno_classifier의 AFFILIATED_MVNO와 동일 그룹.
# 신규 딜보다 공지성 콘텐츠가 많아 시의성이 덜 급해서 관련도순 1회만 검색(절감).
# "헬로비전"은 모회사가 케이블방송도 겸업이라 "헬로비전 알뜰폰" 복합어로만 검색
SUBSIDIARY_KEYWORDS = [
    "헬로모바일",
    "헬로비전 알뜰폰",
    "리브엠",
    "텔링크",
    "유모바일",
    "엠모바일",
]

# [v1.6] 트렌드 이슈 키워드 - MVNO 직접 언급 없어도
# 통신비/요금제 관련 바이럴 콘텐츠 센싱 (테크몽, ITSub잇섭 등 IT 유튜버)
TREND_MONITOR_KEYWORDS = [
    "요금제 통합",
    "5G 단독모드",
    "최적요금제",
    "통신비 절감",
    "요금제 비교",
]

# [v2.5] 온라인 다이렉트 채널 — MVNO는 아니지만 대쉬보드의 "온라인" 카테고리와
# 동일 축(3사 온라인 전용 요금제)이라 독립 카테고리로 분리. 관련도순 1회만 검색.
# "에어"/"너겟" 단독은 에어컨/치킨너겟 등과 오탐 가능해 복합어로만 검색
ONLINE_CHANNEL_KEYWORDS = [
    "T다이렉트샵",       # SKT
    "SKT 에어 요금제",   # SKT
    "너겟 요금제",       # LG U+
    "요고 요금제",       # KT
]

VIRAL_THRESHOLD_PCT = 50

# [v3.0] 온라인 채널 키워드(T다이렉트샵/에어/너겟/요고)가 3사 공식 채널 자체를
# 잡아올 때가 있는데, 조회수가 압도적으로 커서 상위 TOP_DETAIL_COUNT를 독차지해
# 정작 소규모 MVNO 채널이 상세분석을 못 받는 문제가 있었음. 요약 목록(핫글/
# 신규추가)에는 그대로 두되, 전체 분석 대상 선정에서만 제외
_MNO_OFFICIAL_CHANNEL_HINTS = ("SK텔레콤", "SKT", "KT텔레콤", "LG유플러스", "LG U+")


def _is_mno_official(video: dict) -> bool:
    channel = video.get("channel", "")
    return any(hint.lower() in channel.lower() for hint in _MNO_OFFICIAL_CHANNEL_HINTS)

# [v2.1] 14일이 지난 영상이라도 조회수가 이 이상이면 "놓쳤던 주요 뉴스"로 리포트.
# 오래된 뉴스로 리포트가 도배되는 걸 막으면서도, "알뜰폰 업계 직격탄" 같은 중요
# 이슈가 나이 때문에 조용히 묻히는 걸 방지 (check_mno_high_traffic과 동일한 기준선)
IMPORTANT_VIEW_THRESHOLD = 10_000

# [v2.7] 한 번의 실행에서 신규 영상이 여러 건 몰려도, 전체 분석(자막 요약+댓글
# 감성)은 조회수 상위 이 개수까지만. 나머지는 압축 목록으로만 안내
TOP_DETAIL_COUNT = 5


def _search_videos_multi_order(keyword: str, max_results: int = 30) -> list:
    """
    [v2.0] relevance(관련도순) + date(최신순) 검색을 병행해 video_id로 중복 제거.
    relevance만 쓰면 막 올라와 조회수/좋아요가 아직 없는 신규 영상이 순위 밖으로
    밀려 검색 결과에서 통째로 누락될 수 있어, date 검색으로 그 빈틈을 메운다.
    """
    by_id = {}
    for order in ("relevance", "date"):
        for video in search_videos(keyword, max_results=max_results, order=order):
            by_id.setdefault(video["video_id"], video)
    return list(by_id.values())


# ──────────────────────────────────────────────
# Firestore 중복 체크
# ──────────────────────────────────────────────

def is_seen(video_id: str) -> bool:
    return db.collection(SEEN_COLLECTION).document(video_id).get().exists


def mark_seen(video_id: str, video_info: dict, classify_result: dict):
    db.collection(SEEN_COLLECTION).document(video_id).set({
        "video_id": video_id,
        "title": video_info.get("title", ""),
        "channel": video_info.get("channel", ""),
        "view_count": video_info.get("view_count", 0),
        "view_count_history": [video_info.get("view_count", 0)],
        "published_at": video_info.get("published_at", ""),
        "url": video_info.get("url", ""),
        "provider": classify_result.get("provider", ""),
        "first_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    })


def update_view_count(video_id: str, new_view_count: int) -> dict:
    doc_ref = db.collection(SEEN_COLLECTION).document(video_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"is_viral": False}

    data = doc.to_dict()
    prev_count = data.get("view_count", 0)
    history = data.get("view_count_history", [])
    increase_pct = ((new_view_count - prev_count) / max(prev_count, 1)) * 100

    history.append(new_view_count)
    doc_ref.update({
        "view_count": new_view_count,
        "view_count_history": history[-10:],
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "is_viral": increase_pct >= VIRAL_THRESHOLD_PCT and prev_count > 1000,
        "prev_count": prev_count,
        "new_count": new_view_count,
        "increase_pct": round(increase_pct, 1),
    }


def is_recent_enough(published_at: str, days: int = 7) -> bool:
    try:
        pub_date = datetime.strptime(published_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return pub_date >= datetime.now(timezone.utc) - timedelta(days=days)
    except Exception:
        return True


def filter_mvno_videos(videos: list, keyword: str) -> list:
    results = []
    for video in videos:
        result = classify_post(
            title=video.get("title", ""),
            content=video.get("description", ""),
            use_ai=False,
        )
        if result:
            video["_classify"] = result
            video["_search_keyword"] = keyword
            # [v1.7] MVNO 키워드로 잡혔어도 트렌드 이슈 키워드가
            # 함께 매칭되면 _trend_issues를 부여 (헤더/🔥태그 표시용)
            trend_issues = detect_trend_issues(
                title=video.get("title", ""),
                content=video.get("description", ""),
            )
            if trend_issues:
                video["_trend_issues"] = trend_issues
            results.append(video)
    return results


def filter_trend_videos(videos: list, keyword: str) -> list:
    """
    [v1.6] MVNO 사업자명 매칭과 무관하게,
    통신비/요금제 트렌드 이슈 키워드로 영상 필터링.
    (예: "요금제 미쳤습니다", "통합요금제 현실" 등 바이럴 콘텐츠)
    """
    results = []
    for video in videos:
        issues = detect_trend_issues(
            title=video.get("title", ""),
            content=video.get("description", ""),
        )
        if issues:
            video["_trend_issues"] = issues
            video["_search_keyword"] = keyword
            # classify_post도 시도 (사업자명 같이 언급된 경우 대비)
            result = classify_post(
                title=video.get("title", ""),
                content=video.get("description", ""),
                use_ai=False,
            )
            video["_classify"] = result or {"provider": "", "method": "trend_issue"}
            results.append(video)
    return results


# ──────────────────────────────────────────────
# 숫자 포맷
# ──────────────────────────────────────────────

def _fmt(n: int) -> str:
    if n >= 10_000: return f"{n/10_000:.1f}만"
    if n >= 1_000:  return f"{n/1_000:.1f}천"
    return str(n)


def _truncate(text: str, limit: int) -> str:
    """잘린 경우에만 말줄임표를 붙인다 (짧은 텍스트에 불필요한 ... 방지)."""
    return text[:limit] + "..." if len(text) > limit else text


# ──────────────────────────────────────────────
# 통합 리포트 메시지 (영상 1장)
# ──────────────────────────────────────────────

def build_monitor_report(
    video: dict,
    summary: dict,
    comment_analysis: dict,
    keyword: str,
    is_recent: bool = True,
) -> str:
    title    = video.get("title", "")
    channel  = video.get("channel", "")
    pub      = video.get("published_at", "")
    views    = _fmt(video.get("view_count", 0))
    likes    = _fmt(video.get("like_count", 0))
    url      = video.get("url", "")
    # [v1.8] 영상 전체 댓글수 (답글 포함, YouTube API statistics 기준)
    total_comment_count = video.get("comment_count", 0)

    # 요약
    lines    = summary.get("summary_lines", [])
    keywords = summary.get("keywords", [])
    insight  = summary.get("insight", "")
    # 요약 실패 여부 판단
    summary_failed = not lines or lines == ["요약 생성 실패"] or lines == ["AI 요약 오류"]
    if summary_failed:
        summary_block = ""
        kw_block = ""
    else:
        summary_block = "\n".join([f"• {l}" for l in lines[:3]])
        kw_block = "  ".join(keywords[:5]) if keywords else "—"

    # 감성
    ratio = comment_analysis.get("sentiment_ratio", {})
    total = comment_analysis.get("total", 0)
    pos   = ratio.get("긍정", 0)
    neg   = ratio.get("부정", 0)
    neu   = ratio.get("중립", 0)

    def bar(p):
        f = round(p/10)
        return "█"*f + "░"*(10-f)

    # 클러스터
    clusters = comment_analysis.get("clusters", [])
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
    cluster_block = ""
    for i, c in enumerate(clusters[:3]):
        label = c.get("label","")
        rep   = _truncate(c.get("representative",""), 50)
        count = c.get("count", 0)
        cluster_block += "\n" + emojis[i] + " " + label + " (" + str(count) + "건)\n   └ " + rep + "\n"

    key_issue = comment_analysis.get("key_issue", "")

    # 요약 섹션
    summary_section = ""
    if not summary_failed:
        summary_section += "📝 핵심 요약\n" + summary_block + "\n\n"
        if kw_block:
            summary_section += "🏷 키워드: " + kw_block + "\n"
        if insight:
            summary_section += "💡 " + insight + "\n"
    elif total > 0:
        # 요약 없을 때 댓글 감성 기반 자동 요약
        dominant = "긍정" if pos >= neg and pos >= neu else ("부정" if neg >= neu else "중립")
        summary_section += "📝 댓글 반응 기반 요약\n"
        if total_comment_count > total:
            summary_section += "• 댓글 " + str(total_comment_count) + "개 중 " + str(total) + "개 분석 — " + dominant + " 반응 우세 (" + str(max(pos,neg,neu)) + "%)\n"
        else:
            summary_section += "• 댓글 " + str(total) + "개 분석 — " + dominant + " 반응 우세 (" + str(max(pos,neg,neu)) + "%)\n"
        if key_issue:
            summary_section += "• " + key_issue + "\n"

    # [v1.9] 댓글 수 표시: 전체(답글포함) vs 분석된 댓글수
    # (get_comments()가 답글도 수집하므로 보통 거의 일치. 다건 답글 스레드처럼
    #  API가 일부만 반환하는 경우에만 차이가 남음)
    if total_comment_count > total and total > 0:
        comment_count_label = f"댓글 {total_comment_count}개 중 {total}개 분석"
    else:
        comment_count_label = f"{total}개"

    # 댓글 섹션
    if total == 0:
        if total_comment_count > 0:
            comment_section = f"💬 댓글 {total_comment_count}개 (분석 가능한 최상위 댓글 없음)\n"
        else:
            comment_section = "💬 댓글 없음\n"
    else:
        comment_section = (
            "💬 댓글 감성 (" + comment_count_label + ")\n"
            + "🟢 긍정 " + str(pos) + "%  " + bar(pos) + "\n"
            + "🔴 부정 " + str(neg) + "%  " + bar(neg) + "\n"
            + "⚪ 중립 " + str(neu) + "%  " + bar(neu) + "\n"
        )
        if cluster_block.strip():
            comment_section += "\n🗂 주요 여론" + cluster_block + "\n"
            if key_issue:
                comment_section += "📌 " + key_issue + "\n"

    # [v1.6] 트렌드 이슈 태그 (있으면 표시)
    trend_issues = video.get("_trend_issues", [])
    trend_tag = ""
    if trend_issues:
        trend_tag = "🔥 " + " · ".join(trend_issues) + "\n"

    # [v2.5] 온라인 다이렉트 채널(T다이렉트샵/에어/너겟/요고)은 일반 "트렌드"와
    # 구분되는 별도 카테고리로 표시 (대쉬보드의 "온라인" 카테고리와 동일 축)
    is_online = "온라인다이렉트" in trend_issues

    if not is_recent:
        # [v2.1] 14일은 지났지만 조회수가 높아 중요도 기준으로 리포트된 경우
        if is_online:
            header_label = "📺 놓쳤던 온라인 채널 소식"
        elif trend_issues:
            header_label = "📺 놓쳤던 트렌드 이슈"
        else:
            header_label = "📺 놓쳤던 주요 뉴스"
    else:
        if is_online:
            header_label = "📺 온라인 채널 소식"
        elif trend_issues:
            header_label = "📺 신규 트렌드 영상"
        else:
            header_label = "📺 신규 MVNO 영상"

    msg = (
        header_label + " | " + keyword + "\n"
        + trend_tag + "\n"
        + "🎬 " + title + "\n"
        + url + "\n"
        + "📺 " + channel + "  |  📅 " + pub + "\n"
        + "👁 " + views + "  👍 " + likes + "\n\n"
        + summary_section
        + "\n"
        + comment_section
    )
    return msg.strip()


def _link(title: str, url: str, limit: int = 45) -> str:
    """HTML 하이퍼링크. parse_mode="HTML"로 보낼 메시지에서만 사용 — 제목에
    <, >, & 등이 섞여도 깨지지 않도록 반드시 이스케이프한다."""
    safe_title = html.escape(_truncate(title, limit))
    return f'<a href="{url}">{safe_title}</a>'


def build_run_summary(
    run_time: str,
    total_searched: int,
    top: list,
    rest: list,
    viral_alerts: list,
) -> list:
    """
    [v2.8] 압축 목록 + 급상승 알림 + 최종 요약을 하나의 메시지로 통합.
    [v3.2] "🔥 핫글(조회수 상위)" 별도 섹션 폐지 - top도 결국 조회수 순 정렬일 뿐,
    풀에 조회수 높은 영상이 없으면 수십 건짜리 영상까지 "핫글"로 표시되는 문제
    (사용자 피드백: "조회수 1000개도 아닌데 먼 핫글"). top/rest를 "🆕 신규" 하나로
    합쳐 표시하고, top(=상세분석 대상, 이제 조회수 1,000건 초과만 포함)만 📊로 구분.
    📈 급등 섹션은 그대로 유지. 제목은 HTML 하이퍼링크로 걸어 바로 클릭 가능하게 함.
    Telegram 메시지 길이 제한(4096자)을 넘으면 여러 장으로 나눠 반환 (parse_mode="HTML"
    로 보내야 하므로 모든 조각이 개별적으로도 올바른 HTML이 되도록 줄 단위로만 분할).
    """
    new_count   = len(top) + len(rest)
    viral_count = len(viral_alerts)

    lines = [
        f"📊 YouTube MVNO 센싱 요약 — {run_time}",
    ]

    # [v2.9] 이번 실행에서 잡힌 신규 영상들의 발행일 범위 — 오래된 영상이 섞여
    # 신규 건수가 튀는 건지(예: 키워드 신규 추가 직후 백로그) 한눈에 파악하기 위함
    all_new = top + rest
    top_ids = {v.get("video_id") for v in top}
    published_dates = [v.get("published_at", "") for v in all_new if v.get("published_at")]
    if published_dates:
        oldest, newest = min(published_dates), max(published_dates)
        date_range = oldest if oldest == newest else f"{oldest} ~ {newest}"
        lines.append(f"📅 발행일 범위: {date_range}")

    lines.append(f"검색 {total_searched}개 · 신규 {new_count}개 · 급상승 {viral_count}개")

    if all_new:
        detail_note = f", 📊 표시 {len(top)}건은 아래 상세분석 리포트 이어짐" if top else ""
        lines.append(f"\n🆕 신규 ({len(all_new)}건{detail_note})")
        for i, v in enumerate(all_new, 1):
            views    = _fmt(v.get("view_count", 0))
            comments = _fmt(v.get("comment_count", 0))
            marker   = "📊" if v.get("video_id") in top_ids else f"{i}."
            lines.append(f"{marker} {_link(v.get('title',''), v.get('url',''))} (조회 {views} · 댓글 {comments})")

    if viral_alerts:
        lines.append("\n📈 급등")
        for video, info in viral_alerts:
            prev = _fmt(info["prev_count"])
            new  = _fmt(info["new_count"])
            pct  = info["increase_pct"]
            lines.append(f"🔥 {_link(video.get('title',''), video.get('url',''))} — {prev}→{new} (+{pct}%)")

    if not top and not rest and not viral_alerts:
        lines.append("\n🔇 신규 없음")

    # 메시지 하나가 너무 길어지지 않도록 줄 단위로만 분할 (태그 중간에서 안 잘리게)
    messages, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > 3500:
            messages.append(current.strip())
            current = ""
        current += line + "\n"
    if current.strip():
        messages.append(current.strip())
    return messages or ["\n".join(lines)]


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

async def _send(bot, text, preview=False, parse_mode=None):
    """개인 + 팀 채널 동시 전송"""
    targets = [TELEGRAM_CHAT_ID]
    if TELEGRAM_TEAM_CHAT_ID:
        targets.append(TELEGRAM_TEAM_CHAT_ID)
    for chat_id in targets:
        try:
            await bot.send_message(
                chat_id, text, disable_web_page_preview=not preview, parse_mode=parse_mode
            )
        except Exception as e:
            logger.warning(f"메시지 전송 실패 ({chat_id}): {e}")


async def run():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    run_time = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=9))
    ).strftime("%Y-%m-%d %H:%M KST")

    logger.info(f"YouTube 센싱 시작 — {run_time}")

    total_searched = 0
    new_count      = 0
    viral_count    = 0

    # [v1.6] 일반 MVNO 키워드 + 트렌드 이슈 키워드 통합 처리
    # [v2.4] SUBSIDIARY_KEYWORDS(자회사) 추가 — 필터는 "mvno" 경로를 타되,
    # 검색 순서는 트렌드 키워드처럼 관련도순 1회만(쿼터 절감)
    all_keyword_sets = [(kw, "mvno", "dual") for kw in MONITOR_KEYWORDS] \
                      + [(kw, "mvno", "single") for kw in SUBSIDIARY_KEYWORDS] \
                      + [(kw, "trend", "single") for kw in TREND_MONITOR_KEYWORDS] \
                      + [(kw, "trend", "single") for kw in ONLINE_CHANNEL_KEYWORDS]

    # [v2.7] 발견되는 즉시 전체 리포트를 보내던 방식 → 한 번의 실행 동안 신규
    # 영상을 다 모은 뒤, 조회수 상위 TOP_DETAIL_COUNT개만 전체 분석(자막 요약+
    # 댓글 감성) 리포트를 보내고 나머지는 압축 목록 한 장으로만 안내.
    # 키워드가 늘면서 한 번에 신규가 몰릴 때 채널이 도배되는 걸 막고,
    # 사소한 영상까지 Gemini로 분석하던 비용도 같이 줄어듦.
    new_candidates = []  # [{video, keyword, is_recent}]
    viral_alerts   = []  # [(video, viral_info)] — [v2.8] 요약 메시지에 합쳐서 전송

    try:
        for keyword, kw_type, search_order in all_keyword_sets:
            logger.info(f"검색: {keyword} ({kw_type}, {search_order})")
            # [v2.3] 쿼터 절감: 시의성이 중요한 핵심 MVNO 키워드만 관련도+최신순
            # 이중 검색, 나머지(자회사/트렌드)는 관련도순 1회만
            if search_order == "dual":
                videos = _search_videos_multi_order(keyword, max_results=30)
            else:
                videos = search_videos(keyword, max_results=30, order="relevance")
            total_searched += len(videos)

            if not videos:
                continue

            if kw_type == "mvno":
                mvno_videos = filter_mvno_videos(videos, keyword)
                logger.info(f"MVNO 영상: {len(mvno_videos)}개")
            else:
                mvno_videos = filter_trend_videos(videos, keyword)
                logger.info(f"트렌드 이슈 영상: {len(mvno_videos)}개")

            for video in mvno_videos:
                video_id       = video["video_id"]
                classify_result = video["_classify"]

                if not is_seen(video_id):
                    is_recent    = is_recent_enough(video.get("published_at", ""), days=14)
                    is_important = video.get("view_count", 0) >= IMPORTANT_VIEW_THRESHOLD

                    # 키워드/실행마다 한 번만 seen 처리 — 같은 영상이 다른 키워드로
                    # 다시 걸려도 여기서 이미 걸러짐
                    mark_seen(video_id, video, classify_result)

                    if is_recent or is_important:
                        video["_search_keyword"] = keyword
                        video["_is_recent"] = is_recent
                        new_candidates.append(video)

                else:
                    viral_info = update_view_count(video_id, video.get("view_count", 0))
                    if viral_info.get("is_viral"):
                        logger.info(f"급상승: {video['title'][:50]}")
                        viral_alerts.append((video, viral_info))
                        viral_count += 1

        new_count = len(new_candidates)

        # 조회수 상위 TOP_DETAIL_COUNT개만 전체 분석, 나머지는 목록만.
        # [v3.0] 3사 공식 채널은 조회수가 압도적으로 커서 상위권을 독차지하므로
        # 전체 분석 대상에서는 제외 (요약 목록엔 그대로 남음 — rest에 포함됨)
        # [v3.1, 버그수정] IMPORTANT_VIEW_THRESHOLD로 잡힌 "놓쳤던 뉴스"(발행일
        # 무관, 누적 조회수만 10,000 이상이면 포함)가 신규 영상과 같은 풀에서
        # 조회수만으로 정렬되다 보니, 몇 년 지난 SKT 공식 광고(누적 120만
        # 조회수) 같은 게 핫글 1위를 차지하고 진짜 최근 트렌드 영상이 밀려나던
        # 문제 - 핫글은 HOT_WINDOW_DAYS 이내 발행분만 순위 대상으로 제한.
        # 신규추가도 조회수 0~수백의 자잘한 영상까지 다 나오던 문제 - 최소
        # 조회수(NEW_ADDED_MIN_VIEWS) 미만은 목록에서 제외 (단, mark_seen은
        # 이미 끝났으니 다음 실행에 다시 잡히진 않음)
        # [v3.2, 버그수정] "핫글"(top)엔 NEW_ADDED_MIN_VIEWS 기준이 빠져 있어서
        # 조회수 36~355건짜리 영상까지 "조회수 상위" 핫글로 뜨는 문제 (사용자 피드백:
        # "조회수 1000개도 아닌데 먼 핫글"). 상세분석 대상도 신규추가와 동일하게
        # 1,000건 초과만 대상으로 통일.
        HOT_WINDOW_DAYS      = 30
        NEW_ADDED_MIN_VIEWS  = 1000

        new_candidates.sort(key=lambda v: v.get("view_count", 0), reverse=True)
        detail_eligible = [v for v in new_candidates if not _is_mno_official(v)]
        hot_eligible = [
            v for v in detail_eligible
            if is_recent_enough(v.get("published_at", ""), days=HOT_WINDOW_DAYS)
            and v.get("view_count", 0) > NEW_ADDED_MIN_VIEWS
        ]
        top     = hot_eligible[:TOP_DETAIL_COUNT]
        top_ids = {v["video_id"] for v in top}
        # [v3.3] "저조회수도 신규엔 목록으로 다 보이게" - rest(=신규 목록에서 상세분석
        # 없이 나열만 되는 항목)에서 NEW_ADDED_MIN_VIEWS 조회수 하한을 제거. 상세분석
        # 대상(top, 📊 표시)만 계속 1,000건 초과로 걸러지고, 신규 발견 자체는 조회수와
        # 무관하게 전부 목록에 나오도록 함 (오늘처럼 전부 저조회수인 날에도 "신규 0개"로
        # 사라지지 않고 목록은 보이게).
        rest    = [
            v for v in new_candidates
            if v["video_id"] not in top_ids
            and is_recent_enough(v.get("published_at", ""), days=HOT_WINDOW_DAYS)
        ]

        # [v2.8] 핫글/신규추가/급등을 한 메시지로 (HTML 하이퍼링크). 길면 여러 장
        for summary_msg in build_run_summary(run_time, total_searched, top, rest, viral_alerts):
            await _send(bot, summary_msg, parse_mode="HTML")

        for video in top:
            video_id  = video["video_id"]
            keyword   = video["_search_keyword"]
            is_recent = video["_is_recent"]
            logger.info(
                f"{'신규' if is_recent else '놓쳤던 주요 뉴스'} 상세 분석: {video['title'][:50]}"
            )

            video_info = get_video_info(video_id) or video
            video_info["search_keyword"] = keyword
            # [v1.7] get_video_info()가 새 dict를 반환하면 _trend_issues가
            # 누락되므로 검색 결과(video)에서 복사해줌 (헤더/🔥태그 표시용)
            if "_trend_issues" in video:
                video_info["_trend_issues"] = video["_trend_issues"]

            transcript = get_transcript(video_id)
            summary    = summarize_video(video_info, transcript)
            summary["raw_transcript"] = transcript or ""

            comments         = get_comments(video_id, 300, channel_title=video_info.get("channel", ""))
            comment_analysis = analyze_comments(video_id, video_info["title"], comments)

            save_analysis_to_firestore(video_info, summary, comment_analysis)

            report = build_monitor_report(
                video_info, summary, comment_analysis, keyword, is_recent=is_recent
            )
            await _send(bot, report, preview=True)

        if rest:
            logger.info(f"압축 목록 {len(rest)}건 (상세 분석 생략)")

    except QuotaExceededError as e:
        # [v2.2] 쿼터 초과 시 조용히 빈 결과로 넘어가지 않고 즉시 알림 후 이번 실행 중단.
        # 이후 키워드들도 어차피 다 실패할 것이므로 계속 도는 건 의미가 없음.
        logger.error(f"YouTube API 쿼터 초과 — 센싱 중단: {e}")
        await _send(
            bot,
            "🚨 YouTube API 쿼터 초과로 이번 센싱이 중단됐습니다.\n"
            f"진행 상황: {keyword} 검색 중 중단 (총 {total_searched}개 검색, "
            f"신규 {new_count}개 처리 후)\n"
            "쿼터는 태평양시간 자정에 초기화되며, 다음 예정 실행 때 자동 재개됩니다.",
        )
        return

    # [v2.6] Gemini 호출 실패율이 높으면 알림 — 실패해도 "중립"으로 조용히
    # 채워지기 때문에, API 키/크레딧 문제가 생겨도 리포트만 보면 정상처럼 보임.
    # 표본이 너무 적으면(3회 미만) 우연한 실패로 오인할 수 있어 제외
    gemini_stats    = get_gemini_stats()
    sentiment_total = gemini_stats["sentiment_ok"] + gemini_stats["sentiment_failed"]
    if sentiment_total >= 3 and gemini_stats["sentiment_failed"] / sentiment_total > 0.5:
        await _send(
            bot,
            "⚠️ Gemini API 호출 다수 실패 감지\n"
            f"감성분석 {gemini_stats['sentiment_failed']}/{sentiment_total}회 실패 — "
            "이번 리포트의 댓글 감성 비율은 신뢰하기 어려울 수 있습니다.\n"
            "API 키 상태나 크레딧 잔액을 확인해주세요.",
        )

    # 로그 저장
    db.collection(RESULT_COLLECTION).add({
        "run_time": run_time,
        "total_searched": total_searched,
        "new_count": new_count,
        "viral_count": viral_count,
        "keywords": MONITOR_KEYWORDS + SUBSIDIARY_KEYWORDS + TREND_MONITOR_KEYWORDS,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"센싱 완료 — 신규 {new_count}개 / 급상승 {viral_count}개")


if __name__ == "__main__":
    asyncio.run(run())