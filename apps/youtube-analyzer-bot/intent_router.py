# intent_router.py
# YouTube Market Analyzer — 자연어 의도 파악 + 명령어 라우팅
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성
#   - Gemini 기반 자연어 → 명령어 의도 분류
#   - 5가지 인텐트: search / ask / history / help / unknown
#   - 키워드 추출 (search용), 질문 정제 (ask용)
#   - 로컬 규칙 1차 → Gemini 2차 (비용 최소화)

import re
import json
import logging
import os

import google.generativeai as genai

logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
_model = genai.GenerativeModel("gemini-2.5-flash")

# ──────────────────────────────────────────────
# 인텐트 타입 정의
# ──────────────────────────────────────────────

INTENT_SEARCH  = "search"    # 키워드로 유튜브 검색
INTENT_ASK     = "ask"       # 분석 데이터에 질문
INTENT_HISTORY = "history"   # 최근 분석 내역
INTENT_HELP    = "help"      # 도움말
INTENT_UNKNOWN = "unknown"   # 판단 불가


# ──────────────────────────────────────────────
# 1차: 로컬 규칙 기반 (빠르고 무료)
# ──────────────────────────────────────────────

_SEARCH_HINTS = [
    r"검색해", r"찾아", r"알려줘", r"어때", r"요즘", r"최근",
    r"영상\s*(있어|없어|찾아)", r"유튜브에서", r"관련\s*영상",
]
_ASK_HINTS = [
    r"사람들이", r"댓글", r"여론", r"반응", r"생각",
    r"불만", r"만족", r"얼마나", r"많이", r"어떻게\s*생각",
    r"이탈", r"탈퇴", r"어떤\s*(말|얘기|소리)",
]
_HISTORY_HINTS = [r"이전", r"마지막", r"전에\s*분석", r"방금", r"아까", r"최근\s*분석"]
_HELP_HINTS    = [r"사용법", r"어떻게\s*(써|사용)", r"뭐\s*할\s*수", r"기능", r"도움"]


def _match_any(text: str, patterns: list) -> bool:
    for p in patterns:
        if re.search(p, text):
            return True
    return False


def _local_classify(text: str) -> str | None:
    """명확한 패턴은 로컬에서 즉시 분류, 애매하면 None 반환"""
    if _match_any(text, _HISTORY_HINTS):
        return INTENT_HISTORY
    if _match_any(text, _HELP_HINTS):
        return INTENT_HELP
    # ask/search는 겹칠 수 있어 Gemini에게 넘김
    return None


# ──────────────────────────────────────────────
# 2차: Gemini 기반 의도 분류
# ──────────────────────────────────────────────

_ROUTER_PROMPT = """너는 MVNO(알뜰폰) 분석 Telegram 봇의 의도 분류기다.

사용자 메시지를 보고 아래 4가지 중 하나로 분류해라.

인텐트 종류:
- search : YouTube에서 특정 주제/키워드 영상을 검색하고 싶을 때
           예) "알뜰폰 요금제 최근 영상 알려줘", "토스모바일 유튜브 어때"
- ask    : 이미 분석된 영상 데이터를 기반으로 질문할 때
           예) "사람들이 QoS에 대해 어떻게 생각해?", "댓글에서 불만이 많아?"
- history: 최근에 분석한 영상 목록/정보를 보고 싶을 때
- help   : 봇 사용법을 물어볼 때
- unknown: 위에 해당하지 않거나 YouTube/MVNO와 무관한 경우

추가로:
- search면 핵심 검색 키워드를 추출해라 (조사/어미 제거)
- ask면 질문을 깔끔하게 정제해라 (구어체 → 분석 질문)

JSON으로만 응답:
{
  "intent": "search|ask|history|help|unknown",
  "keyword": "검색 키워드 (search일 때만, 없으면 null)",
  "refined_question": "정제된 질문 (ask일 때만, 없으면 null)",
  "confidence": 0.0~1.0
}"""


def _gemini_classify(text: str) -> dict:
    """Gemini로 의도 분류"""
    try:
        prompt = f"{_ROUTER_PROMPT}\n\n사용자 메시지: {text}"
        resp = _model.generate_content(prompt)
        raw = resp.text.strip().lstrip("```json").rstrip("```").strip()
        result = json.loads(raw)
        return result
    except Exception as e:
        logger.warning(f"Gemini 의도 분류 실패: {e}")
        return {
            "intent": INTENT_UNKNOWN,
            "keyword": None,
            "refined_question": None,
            "confidence": 0.0,
        }


# ──────────────────────────────────────────────
# 메인 라우팅 함수
# ──────────────────────────────────────────────

def route(text: str) -> dict:
    """
    자연어 텍스트를 분석해 인텐트와 파라미터 반환

    반환 예시:
      {"intent": "search",  "keyword": "알뜰폰 요금제 비교", "confidence": 0.95}
      {"intent": "ask",     "refined_question": "QoS에 대한 부정 여론 비중은?", "confidence": 0.9}
      {"intent": "history", "confidence": 1.0}
      {"intent": "unknown", "confidence": 0.3}
    """
    text = text.strip()

    # 1차: 로컬 규칙
    local_intent = _local_classify(text)
    if local_intent in (INTENT_HISTORY, INTENT_HELP):
        return {"intent": local_intent, "confidence": 1.0}

    # 2차: Gemini
    result = _gemini_classify(text)

    # confidence 낮으면 unknown 처리
    if result.get("confidence", 0) < 0.55:
        result["intent"] = INTENT_UNKNOWN

    return result
