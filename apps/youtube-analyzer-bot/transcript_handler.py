# transcript_handler.py
# YouTube Market Analyzer — 자막 추출 및 Gemini 기반 영상 요약
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성
# v1.1 | 2025-03-22 | Optional import 패치
# v1.2 | 2025-03-26 | 자동자막 강제 사용, MVNO 조건부 프롬프트
# v1.3 | 2025-03-26 | youtube-transcript-api 1.2.4 새 API
# v1.4 | 2025-03-26 | 프롬프트 정제 — 마크다운 금지, 지시문 미출력
# v1.5 | 2025-03-31 | 레이블 패턴 제거 로직 추가, 프롬프트 개선
# v1.7 | 2026-05-02 | 트랜스크립트 8000→4000자 축소, max_output_tokens=600 추가 (토큰 비용 절감)
# v1.6 | 2025-03-31 | 요약 간결체 — 서술어/접두어 제거, 압축형 출력

from typing import Optional
import logging
import os
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

MVNO_KEYWORDS = [
    "알뜰폰", "mvno", "유심", "esim", "이심", "요금제",
    "헬로모바일", "토스모바일", "sk7모바일", "kt엠모바일", "유모바일",
    "스마텔", "모빙", "티플러스", "아이즈모바일"
]

_ytt = YouTubeTranscriptApi()


def is_mvno_related(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    return any(kw in text for kw in MVNO_KEYWORDS)


def get_transcript(video_id: str) -> Optional[str]:
    """자막 추출 — 한국어 우선, 없으면 영어, 없으면 자동생성"""
    for langs in [["ko"], ["en"], ["ko", "en"]]:
        try:
            entries = _ytt.fetch(video_id, languages=langs)
            text = " ".join([e.text for e in entries]).strip()
            if text:
                logger.info(f"자막 획득 ({langs}): {video_id}")
                return text[:4000]
        except Exception:
            pass

    try:
        entries = _ytt.fetch(video_id)
        text = " ".join([e.text for e in entries]).strip()
        if text:
            logger.info(f"자막 획득 (자동): {video_id}")
            return text[:4000]
    except Exception as e:
        logger.warning(f"자막 없음 ({video_id}): {e}")

    return None


def summarize_video(video_info: dict, transcript: Optional[str]) -> dict:
    """Gemini 영상 요약"""
    title       = video_info.get("title", "")
    channel     = video_info.get("channel", "")
    description = video_info.get("description", "")
    mvno        = is_mvno_related(title, description)

    if transcript:
        content_input = f"[자막]\n{transcript}"
        has_transcript = True
    elif description:
        content_input = f"[설명문]\n{description}"
        has_transcript = False
    else:
        return {"summary_lines": ["정보 없음"], "keywords": [], "insight": "", "has_transcript": False}

    insight_guide = (
        "MVNO/알뜰폰 업계 시사점을 한 문장으로"
        if mvno else
        "이 영상의 핵심 포인트를 한 문장으로"
    )

    prompt = f"""다음 YouTube 영상을 분석해서 아래 형식으로 답해줘.
규칙:
- 마크다운 기호(*, **, _, `, #) 절대 사용 금지
- 각 줄은 내용만 출력 (앞에 "첫번째:", "요점:" 같은 레이블 절대 금지)
- • 또는 - 기호로 시작해도 됨
- 문장 끝 서술어 생략 (예: "~합니다", "~됩니다", "~있습니다" 제거)
- 접두어/설명 없이 핵심 내용만 명사형/압축형으로

제목: {title}
채널: {channel}
{content_input}

==핵심요약==
• 핵심 주제 (명사형, 20자 이내)
• 주요 내용 (핵심만, 40자 이내)
• 핵심 포인트 (결론만, 30자 이내)

==주요키워드==
키워드1, 키워드2, 키워드3, 키워드4, 키워드5

==인사이트==
{insight_guide}
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=600)
        )
        raw = response.text.strip()

        summary_lines, keywords, insight = [], [], ""

        if "==핵심요약==" in raw:
            section = raw.split("==핵심요약==")[1].split("==주요키워드==")[0].strip()
            for line in section.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 레이블 패턴 제거 (예: "첫번째 요점을 한 문장으로:", "1.", "요점1:" 등)
                import re
                line = re.sub(r'^(첫번째|두번째|세번째|[0-9]+\.?|요점\d*)[^\s]*\s*:?\s*', '', line)
                line = line.lstrip("•-").strip()
                if line:
                    summary_lines.append(line)

        if "==주요키워드==" in raw:
            kw_section = raw.split("==주요키워드==")[1].split("==인사이트==")[0].strip()
            keywords = [k.strip() for k in kw_section.split(",") if k.strip()]

        if "==인사이트==" in raw:
            insight = raw.split("==인사이트==")[1].strip()
            # 인사이트도 레이블 제거
            import re
            insight = re.sub(r'^[^:]+:\s*', '', insight).strip()

        return {
            "summary_lines": summary_lines[:3] or ["요약 생성 실패"],
            "keywords": keywords[:6],
            "insight": insight,
            "has_transcript": has_transcript,
        }

    except Exception as e:
        logger.error(f"Gemini 요약 오류: {e}")
        return {"summary_lines": ["AI 요약 오류"], "keywords": [], "insight": "", "has_transcript": has_transcript}