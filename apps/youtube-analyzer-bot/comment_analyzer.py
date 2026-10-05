# comment_analyzer.py
# YouTube Market Analyzer — 댓글 클러스터링 + 감성 분석 + Firestore 저장
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성
# v1.1 | 2025-03-22 | Cloud Shell 경로 패치
# v1.3 | 2026-05-02 | 댓글 200→100개, batch_size 60→100, max_output_tokens 추가 (토큰 비용 절감)
# v1.2 | 2025-03-26 | 모델명 gemini-2.5-flash, 임베딩 제거, DB mvno-data
# v1.4 | 2026-06-15 | 감성분석 100% 중립 폴백 버그 디버깅
#       | - batch_size 100→50으로 축소 (max_output_tokens 부족 의심)
#       | - max_output_tokens 800→2000으로 증가
#       | - 예외 발생 시 raw 응답 로깅 추가 (원인 파악용)
#       | - JSON 파싱 전 정규식으로 배열/객체 부분만 추출 (트레일링 텍스트 대응)
#       | - 클러스터링 max_output_tokens 600→1200, 동일 디버깅 로깅 적용
# v1.5 | 2026-06-15 | 100% 중립 근본 원인 수정 — JSON 응답이 max_output_tokens에서 잘림
#       | - 원인: Gemini 2.5 Flash가 thinking 토큰을 max_output_tokens에서 함께 소비
#       |   + 멀티라인/들여쓰기 JSON이 토큰을 과다 소비 → 50개 항목도 2000토큰 초과
#       | - 프롬프트에 "한 줄 압축 JSON, 들여쓰기 금지" 명시로 토큰 절약
#       | - 감성분석: batch_size 50→30, max_output_tokens 2000→4000
#       | - 클러스터링: max_output_tokens 1200→3000
#       | - 응답이 끊겨도 부분 파싱 시도 (마지막 완전한 객체까지만 복구)
# v1.6 | 2026-09-19 | 초단문 무의미 댓글("ㅋㅋ", "ㅇㅇ" 등) LLM 호출 없이 중립 처리
#       | (get_comments()가 답글까지 수집하도록 바뀌며 배치당 건수가 늘어난 데 대한
#       | 비용 상쇄. "굿"/"비추"처럼 의미 있는 초단문은 그대로 LLM 호출)
# v1.7 | 2026-09-19 | Gemini 호출 실패를 그냥 "중립"으로 채우고 넘어가면 API 키/
#       | 크레딧 문제가 생겨도 리포트가 정상처럼 보여서 아무도 못 알아챔.
#       | 배치/클러스터링 성공·실패 횟수를 GEMINI_STATS에 기록 — 호출 측
#       | (youtube_monitor.py)에서 실패율이 높으면 텔레그램 알림을 보낼 수 있게 함

import os
import json
import re
import logging
from typing import Optional
from datetime import datetime, timezone

# 감탄사/맞장구류 초단문 — 의미 판별이 사실상 불가능해 LLM 호출 없이 중립 처리
_LOW_SIGNAL_PATTERN = re.compile(r"^[ㄱ-ㅎㅏ-ㅣㅋㅎㅇㄷㅜㅠ.!?~\s]{1,3}$")


def _is_low_signal(text: str) -> bool:
    return bool(_LOW_SIGNAL_PATTERN.match(text.strip()))

import google.generativeai as genai
from google.cloud import firestore

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

db = firestore.Client(database="mvno-data")
COLLECTION = "youtube_analyses"

# [v1.7] Gemini 호출 성공/실패 카운터 — 프로세스(=Cloud Run Job 1회 실행) 생명주기 동안 누적.
# 실패해도 "중립"으로 조용히 채워지는 걸 감시하기 위함 (get_gemini_stats로 조회)
GEMINI_STATS = {"sentiment_ok": 0, "sentiment_failed": 0, "cluster_ok": 0, "cluster_failed": 0}


def get_gemini_stats() -> dict:
    return dict(GEMINI_STATS)


# ──────────────────────────────────────────────
# Pass 1: 감성 태깅
# ──────────────────────────────────────────────

def _batch_sentiment(comments: list, batch_size: int = 30) -> list:
    tagged = []

    # 초단문(맞장구/이모티콘성) 댓글은 비용 절감을 위해 LLM 호출에서 제외
    llm_targets = []
    for comment in comments:
        if _is_low_signal(comment["text"]):
            comment["sentiment"] = "중립"
            tagged.append(comment)
        else:
            llm_targets.append(comment)

    for i in range(0, len(llm_targets), batch_size):
        batch = llm_targets[i: i + batch_size]
        texts = "\n".join([f"{j+1}. {c['text'][:150]}" for j, c in enumerate(batch)])
        prompt = f"""아래 유튜브 댓글들의 감성을 분류해주세요.

댓글:
{texts}

각 댓글을 "긍정", "부정", "중립" 중 하나로 분류하여
반드시 한 줄로 압축된 JSON 배열로만 응답하세요 (줄바꿈, 들여쓰기, 공백 없이).

출력 형식 예시 (이 형식 그대로, 다른 텍스트 절대 없이):
[{{"id":1,"sentiment":"긍정"}},{{"id":2,"sentiment":"부정"}},{{"id":3,"sentiment":"중립"}}]

총 {len(batch)}개 항목을 빠짐없이, 한 줄로 출력하세요.
"""
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(max_output_tokens=4000)
            )
            raw = resp.text.strip()
            # 마크다운 펜스 제거 (앞/뒤 어디에 있든 처리)
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            raw = raw.strip()

            try:
                # 정상 케이스: 완전한 JSON 배열
                match = re.search(r"\[.*\]", raw, re.DOTALL)
                results = json.loads(match.group(0) if match else raw)
            except json.JSONDecodeError:
                # [v1.5] 응답이 잘린 경우: 완전한 {"id":N,"sentiment":"X"} 객체만
                # 끝까지 긁어모아 부분 복구 (마지막 잘린 항목은 버림)
                items = re.findall(
                    r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"sentiment"\s*:\s*"(긍정|부정|중립)"\s*\}',
                    raw
                )
                if not items:
                    raise
                results = [{"id": int(i), "sentiment": s} for i, s in items]
                logger.info(f"감성 배치 {i}: 응답 일부 손상 — 부분 복구 {len(results)}/{len(batch)}개")

            sentiment_map = {r["id"]: r["sentiment"] for r in results}

            valid_sentiments = {"긍정", "부정", "중립"}
            for j, comment in enumerate(batch):
                s = sentiment_map.get(j + 1, "중립")
                comment["sentiment"] = s if s in valid_sentiments else "중립"
                tagged.append(comment)

            # 응답 항목 수가 배치 크기와 다르면 경고
            if len(results) != len(batch):
                logger.warning(
                    f"감성 배치 {i}: 요청 {len(batch)}개 vs 응답 {len(results)}개 — "
                    f"일부 항목 기본값(중립) 적용됨"
                )
            GEMINI_STATS["sentiment_ok"] += 1
        except Exception as e:
            # 디버깅을 위해 원본 응답 일부를 로그에 남김
            raw_preview = ""
            try:
                raw_preview = resp.text[:300]
            except Exception:
                raw_preview = "(응답 자체를 가져오지 못함)"
            logger.warning(
                f"감성 배치 오류 (배치 {i}, {len(batch)}개): {type(e).__name__}: {e}\n"
                f"응답 미리보기: {raw_preview!r}"
            )
            GEMINI_STATS["sentiment_failed"] += 1
            for comment in batch:
                comment["sentiment"] = "중립"
                tagged.append(comment)
    return tagged


# ──────────────────────────────────────────────
# Pass 2: 클러스터링
# ──────────────────────────────────────────────

def _cluster_comments(comments: list, video_title: str) -> dict:
    # 댓글 10개 미만이면 클러스터링 생략
    if len(comments) < 10:
        return {"clusters": [], "overall_summary": "", "key_issue": ""}

    top = sorted(comments, key=lambda x: x["like_count"], reverse=True)[:100]
    block = "\n".join([f"- [{c['sentiment']}] {c['text'][:120]}" for c in top])

    prompt = f"""한국 MVNO(알뜰폰) 시장 분석 전문가로서 아래 YouTube 영상 댓글을 분석해주세요.
영상: "{video_title}"

{block}

분석 결과를 한 줄로 압축된 JSON으로만 응답하세요 (줄바꿈, 들여쓰기 없이, 마크다운 기호 사용 금지).
representative 댓글 원문은 30자 이내로 짧게 요약해서 넣으세요.

출력 형식 예시 (이 구조 그대로 한 줄로):
{{"clusters":[{{"label":"클러스터명","count":5,"representative":"대표댓글 요약","dominant_sentiment":"긍정"}}],"overall_summary":"여론 요약 1문장","key_issue":"핵심 이슈 1문장"}}

클러스터는 3~5개.
"""
    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=3000)
        )
        raw = resp.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        # JSON 객체 부분만 추출
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

        result = json.loads(raw)
        GEMINI_STATS["cluster_ok"] += 1
        return result
    except Exception as e:
        raw_preview = ""
        try:
            raw_preview = resp.text[:300]
        except Exception:
            raw_preview = "(응답 자체를 가져오지 못함)"
        logger.error(f"클러스터링 오류: {type(e).__name__}: {e}\n응답 미리보기: {raw_preview!r}")
        GEMINI_STATS["cluster_failed"] += 1
        return {"clusters": [], "overall_summary": "", "key_issue": ""}


# ──────────────────────────────────────────────
# 메인 분석
# ──────────────────────────────────────────────

def analyze_comments(video_id: str, video_title: str, comments: list) -> dict:
    if not comments:
        return {
            "sentiment_ratio": {"긍정": 0, "부정": 0, "중립": 100},
            "clusters": [],
            "overall_summary": "댓글이 없습니다.",
            "key_issue": "",
            "total": 0,
        }

    logger.info(f"[{video_id}] 댓글 {len(comments)}개 감성 분석 시작...")
    tagged = _batch_sentiment(comments)

    counts = {"긍정": 0, "부정": 0, "중립": 0}
    for c in tagged:
        s = c.get("sentiment", "중립")
        counts[s] = counts.get(s, 0) + 1

    total = len(tagged)
    ratio = {k: round(v / total * 100) for k, v in counts.items()}

    logger.info(f"[{video_id}] 클러스터링 시작...")
    cluster_result = _cluster_comments(tagged, video_title)

    return {
        "sentiment_ratio": ratio,
        "clusters": cluster_result.get("clusters", []),
        "overall_summary": cluster_result.get("overall_summary", ""),
        "key_issue": cluster_result.get("key_issue", ""),
        "total": total,
        "tagged_comments": tagged,
    }


# ──────────────────────────────────────────────
# Firestore 저장
# ──────────────────────────────────────────────

def save_analysis_to_firestore(video_info: dict, summary: dict, comment_analysis: dict) -> str:
    video_id = video_info["video_id"]
    doc_id   = f"{video_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    doc_data = {
        "video_id":   video_id,
        "video_info": video_info,
        "summary": {
            "lines":          summary.get("summary_lines", []),
            "keywords":       summary.get("keywords", []),
            "insight":        summary.get("insight", ""),
            "has_transcript": summary.get("has_transcript", False),
            "transcript_embedding": [],
        },
        "comment_analysis": {
            "total":           comment_analysis["total"],
            "sentiment_ratio": comment_analysis["sentiment_ratio"],
            "clusters":        comment_analysis["clusters"],
            "overall_summary": comment_analysis["overall_summary"],
            "key_issue":       comment_analysis["key_issue"],
        },
        "embedded_comments": [],
        "analyzed_at":    datetime.now(timezone.utc).isoformat(),
        "search_keywords": video_info.get("search_keyword", ""),
    }

    db.collection(COLLECTION).document(doc_id).set(doc_data)
    logger.info(f"Firestore 저장 완료: {COLLECTION}/{doc_id}")
    return doc_id


# ──────────────────────────────────────────────
# RAG 질의
# ──────────────────────────────────────────────

def query_analysis(video_id: str, question: str, date_str: str = None) -> str:
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime('%Y%m%d')

    doc_id = f"{video_id}_{date_str}"
    doc    = db.collection(COLLECTION).document(doc_id).get()

    if not doc.exists:
        return "해당 영상의 분석 데이터를 찾을 수 없습니다. 먼저 영상을 분석해주세요."

    data = doc.to_dict()
    ca   = data.get("comment_analysis", {})

    clusters_text = "\n".join(
        [f"• {c['label']}: {c.get('representative', '')}" for c in ca.get("clusters", [])]
    )

    prompt = f"""한국 MVNO(알뜰폰) 시장 전문 분석가로서 아래 데이터를 바탕으로 질문에 답해주세요.

영상: {data['video_info']['title']}
채널: {data['video_info']['channel']}

여론 요약: {ca.get('overall_summary', '')}

주요 의견 클러스터:
{clusters_text}

감성 비율: 긍정 {ca.get('sentiment_ratio', {}).get('긍정', 0)}% | 부정 {ca.get('sentiment_ratio', {}).get('부정', 0)}% | 중립 {ca.get('sentiment_ratio', {}).get('중립', 0)}%

질문: {question}

데이터 기반으로 간결하게 답변하세요. 마크다운 기호 사용 금지.
"""

    try:
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        logger.error(f"RAG 답변 생성 실패: {e}")
        return "답변 생성 중 오류가 발생했습니다."