"""
gemini_handler.py

[수정 이력]
v1.0 | 2026-03-19 | 최초 작성
v1.1 | 2026-03-19 | 이미지 파싱 추가
v1.2 | 2026-03-19 | 항공 스케줄표 파싱 규칙 추가
v1.3 | 2026-03-20 | 자연어 의도 파악 추가
v1.4 | 2026-03-20 | 예약문자 특화 파싱 추가
v1.5 | 2026-03-21 | 비서 코멘트 기능 추가 (get_assistant_comment)
v1.6 | 2026-03-21 | 조회 코멘트(get_list_comment), 삭제 멘트(get_delete_comment) 추가
v1.7 | 2026-03-21 | 전체 톤 살갑고 친근하게 변경
v1.8 | 2026-03-21 | 귀국 다음날 피로 경고 멘트 제거
v1.9 | 2026-03-21 | Gemini 빈 응답 처리 - detect_intent fallback 추가
v2.0 | 2026-03-25 | 고차원 질문(analyze_events) + 일정 수정(get_modify_event) 추가
v2.1 | 2026-03-31 | TODAY/CURRENT_YEAR 동적 계산으로 변경 - 날짜 고정 버그 수정
v2.2 | 2026-06-29 | 항공 스케줄 시간 기준 수정 - time_start=SHOWUP, time_end=STA
v2.3 | 2026-09-20 | 제목 수정 시 "점심 홍길동"처럼 입력하면 Gemini가 "점심"을
     | 카테고리/시간대 힌트로만 해석해서 "홍길동"만 남기던 문제 - EDIT_SYSTEM_PROMPT,
     | MODIFY_PROMPT에 "입력한 텍스트를 그대로 사용" 규칙 명시
v2.4 | 2026-09-20 | "다음주 점심일정들 알려줘"처럼 날짜+키워드가 같이 오면 intent가
     | "list"로 분류되면서 키워드가 버려지고 해당 기간 전체 일정이 나오던 문제 -
     | list action에 keyword 필드 추가
v2.5 | 2026-09-20 | cleanup_duplicates action 추가 - "다음주 중복된 일정
     | 확인해서 삭제해줘"처럼 특정 기간 중복 일정 찾아서 정리하는 요청 지원
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
import google.generativeai as genai

# [v-fix 20261008] 서버(Cloud Run)는 UTC라 datetime.now()가 KST 오전 9시 전엔 전날로 잡힘
# → 한국시간 기준 현재 시각(naive, 기존 코드와 동일하게 tzinfo 없이) 사용
_KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)


logger = logging.getLogger(__name__)

def _get_today() -> str:
    return now_kst().strftime("%Y-%m-%d")

def _get_current_year() -> int:
    return now_kst().year

def _get_weekday() -> str:
    return now_kst().strftime("%A")

def _build_parse_prompt() -> str:
    today = _get_today()
    year = _get_current_year()
    weekday = _get_weekday()
    return f"""당신은 한국어 일정/스케줄 파싱 전문가입니다.
현재 연도는 {year}년입니다. 오늘 날짜는 {today}이고, 오늘은 {weekday}입니다.

사용자가 보낸 텍스트 또는 이미지에서 일정 정보를 추출하여 JSON 배열로 반환하세요.

각 일정은 다음 필드를 포함해야 합니다:
- title: 일정 제목 (한국어)
- date: YYYY-MM-DD 형식 (시작일)
- date_end: YYYY-MM-DD 형식 (종료일, 당일이면 date와 동일)
- time_start: HH:MM 형식 (24시간제), 없으면 null
- time_end: HH:MM 형식 (24시간제), 없으면 null
- location: 장소명, 없으면 null
- description: 추가 메모, 없으면 null
- input_type: "reservation"(예약문자), "schedule"(스케줄표), "simple"(간단입력) 중 하나

=== 일반 규칙 ===
- 공항 코드는 도시명으로 변환 (JFK→뉴욕, ICN→인천, GMP→김포, NRT→나고야, KIX/ITM→오사카, HKG→홍콩, SEA→시애틀, HGH→항저우 등)
- 시간이 오전/오후로 표현되면 24시간제로 변환
- 날짜에 연도가 없으면 {year}년으로 설정
- "이번주 X요일" → 오늘({today}, {weekday})이 속한 주(월~일)에서 그 요일. 이미 지난 요일이면
  다음주가 아니라 그대로 이번주의 그 날짜(과거)로 계산
- "다음주 X요일" → 오늘이 속한 주의 다음 주(월~일)에서 그 요일
- "내일", "모레", "글피" 등도 오늘({today}) 기준으로 정확히 날짜 계산
- 요일 계산은 반드시 오늘이 {weekday}라는 사실을 기준으로 정확히 산출 (임의 추측 금지)

=== 예약문자/알림톡 규칙 (input_type: reservation) ===
- 예약번호, 고객명, 결제금액 등은 description에 포함
- 업체명/서비스명을 title로
- 예약 날짜/시간을 date/time_start로
- 예약 확인, 배송 완료 등 알림은 해당 날짜 일정으로
- 예시: "OO호텔 체크인 4/5 15:00" → title: "OO호텔 체크인"

=== 항공 스케줄표 규칙 (input_type: schedule) ===
1. 편명(숫자)은 제목에서 제거
2. 제목은 목적지만, 인천은 제외
3. 시간 기준:
   - time_start = SHOWUP 시간 (집합/출근 시간) - 스케줄표에서 SHOWUP 컬럼 값 사용
   - time_end = 마지막 편의 STA (도착 예정 시간)
   - SHOWUP이 없는 편(귀국편 등)은 해당 편의 STD 사용
4. 당일 왕복: 출발편 SHOWUP ~ 귀국편 STA 로 합치기
5. 체류 있는 왕복: date=출발일, date_end=귀국일로 합치기, 체류지 단독 일정 흡수
6. STBY확인, 휴무, DAY OFF 등은 그대로 유지

반드시 JSON 배열만 반환, 다른 텍스트 없음
"""

def _build_intent_prompt() -> str:
    today = _get_today()
    weekday = _get_weekday()
    return f"""당신은 일정 관리 봇의 의도 파악 전문가입니다.
오늘 날짜는 {today} 입니다. 오늘은 {weekday} 입니다.

사용자의 자연어 입력을 분석하여 아래 JSON 형식으로만 반환하세요.

action 종류:
- "add": 일정 추가
- "list": 일정 조회
- "search": 키워드 검색
- "delete_search": 삭제 의도 + 키워드
- "analyze": 고차원 분석 질문 (바쁜 날, 가능한 날, 통계 등)
- "modify": 기존 일정 수정 요청
- "cleanup_duplicates": 특정 기간에 중복 등록된 일정을 찾아서 정리(삭제)해달라는 요청
  (예: 같은 일정이 실수로 여러 번 등록됐을 때, 매주 반복 등록된 일정 중 겹치는 것 정리)
- "unknown": 일정과 무관한 입력

반환 형식:
{{"action": "list", "date_from": "MM/DD", "date_to": "MM/DD", "keyword": "선택사항, 특정 종류의 일정만 필터링할 때만 (예: 점심, 회의, 골프)"}}
{{"action": "search", "keyword": "키워드"}}
{{"action": "delete_search", "keyword": "키워드"}}
{{"action": "analyze", "date_from": "MM/DD", "date_to": "MM/DD", "question": "원본질문"}}
{{"action": "modify", "keyword": "수정할 일정 키워드", "date_from": "MM/DD", "date_to": "MM/DD", "request": "수정 요청 내용"}}
{{"action": "cleanup_duplicates", "date_from": "MM/DD", "date_to": "MM/DD"}}
{{"action": "add"}}
{{"action": "unknown"}}

날짜 규칙:
- "오늘" → 오늘 날짜
- "내일" → 내일 날짜
- "이번주" → 오늘~이번주 일요일
- "다음주" → 다음주 월~일
- "이번달" → 이번달 1일~말일
- 날짜 명시되면 그 날짜로

list 예시:
- "다음주 점심일정들 알려줘" → {{"action": "list", "date_from": "MM/DD", "date_to": "MM/DD", "keyword": "점심"}}
- "이번주 일정 알려줘" → {{"action": "list", "date_from": "MM/DD", "date_to": "MM/DD"}}

analyze 예시:
- "4월에 점심 가능한 날" → {{"action": "analyze", "date_from": "04/01", "date_to": "04/30", "question": "4월에 점심 가능한 날"}}
- "이번달 바쁜 날 TOP3" → {{"action": "analyze", "date_from": "04/01", "date_to": "04/30", "question": "이번달 바쁜 날 TOP3"}}
- "다음주 오전 빈 시간" → {{"action": "analyze", "date_from": "MM/DD", "date_to": "MM/DD", "question": "다음주 오전 빈 시간"}}

modify 예시:
- "27일 골프 9시로 바꿔줘" → {{"action": "modify", "keyword": "골프", "date_from": "03/27", "date_to": "03/27", "request": "시간을 9시로 변경"}}
- "내일 회의 제목 변경해줘" → {{"action": "modify", "keyword": "회의", "date_from": "내일날짜", "date_to": "내일날짜", "request": "제목 변경"}}

cleanup_duplicates 예시:
- "다음주 중복된 일정 확인해서 삭제해줘" → {{"action": "cleanup_duplicates", "date_from": "다음주 월요일 MM/DD", "date_to": "다음주 일요일 MM/DD"}}
- "이번달 중복 일정 정리해줘" → {{"action": "cleanup_duplicates", "date_from": "이번달 1일 MM/DD", "date_to": "이번달 말일 MM/DD"}}
- 기간 언급이 전혀 없으면 date_from/date_to 필드를 아예 생략 (전체 기간으로 처리됨)

반드시 JSON만 반환
"""

EDIT_SYSTEM_PROMPT = """당신은 일정 수정 전문가입니다.
기존 일정 목록과 사용자의 수정 요청을 받아서 수정된 일정 목록을 JSON 배열로 반환하세요.

규칙:
- 수정 요청에 명시된 일정만 수정, 나머지는 그대로 유지
- "일정2"처럼 번호로 지칭할 때는 배열의 두 번째 항목 수정
- 제목(title)을 바꿀 때는 사용자가 입력한 텍스트를 절대 요약하거나 일부 단어를
  빼지 말고 그대로 사용. 예: "제목은 점심 홍길동임" → title: "점심 홍길동"
  ("점심"을 카테고리로 해석해서 "홍길동"만 남기면 안 됨)
- 반드시 전체 일정 배열 반환
- JSON 배열만 반환
"""


class GeminiHandler:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _parse_json_response(self, text: str):
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if not text:
            raise ValueError("Gemini 응답이 비어있습니다.")
        return json.loads(text)

    def detect_intent(self, user_text: str) -> dict:
        logger.info(f"Detecting intent: {user_text}")
        full_prompt = f"{_build_intent_prompt()}\n\n사용자 입력: {user_text}"
        response = self.model.generate_content(full_prompt)
        raw = response.text.strip()
        logger.info(f"Intent response: {raw}")
        try:
            return self._parse_json_response(raw)
        except Exception as e:
            logger.warning(f"Intent parse failed: {e}, raw: {raw[:100]}")
            return {"action": "add"}

    def parse_schedule(self, user_text: str) -> list:
        logger.info(f"Parsing schedule: {user_text[:100]}")
        full_prompt = f"{_build_parse_prompt()}\n\n사용자 입력:\n{user_text}"
        response = self.model.generate_content(full_prompt)
        raw = response.text.strip()
        logger.info(f"Parse response: {raw[:300]}")
        return self._parse_json_response(raw)

    def parse_schedule_from_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> list:
        logger.info(f"Parsing image, size: {len(image_bytes)}")
        image_part = {"mime_type": mime_type, "data": image_bytes}
        prompt = f"{_build_parse_prompt()}\n\n위 이미지에서 일정을 모두 추출해주세요."
        response = self.model.generate_content([prompt, image_part])
        raw = response.text.strip()
        logger.info(f"Image parse response: {raw[:300]}")
        return self._parse_json_response(raw)

    def apply_edit(self, current_events: list, edit_request: str) -> list:
        logger.info(f"Applying edit: {edit_request}")
        context = (
            f"현재 일정 목록:\n{json.dumps(current_events, ensure_ascii=False, indent=2)}\n\n"
            f"수정 요청: {edit_request}"
        )
        full_prompt = f"{EDIT_SYSTEM_PROMPT}\n\n{context}"
        response = self.model.generate_content(full_prompt)
        raw = response.text.strip()
        return self._parse_json_response(raw)

    def get_assistant_comment(self, new_event: dict, nearby_events: list):
        """새 일정 등록 시 비서 코멘트"""
        try:
            context = (
                f"등록할 새 일정:\n{json.dumps(new_event, ensure_ascii=False, indent=2)}\n\n"
                f"같은 날 기존 일정들:\n{json.dumps(nearby_events, ensure_ascii=False, indent=2)}"
            )
            full_prompt = f"{ASSISTANT_COMMENT_PROMPT}\n\n{context}"
            response = self.model.generate_content(full_prompt)
            raw = response.text.strip()
            result = self._parse_json_response(raw)
            return result.get("comment")
        except Exception as e:
            logger.error(f"Assistant comment error: {e}")
            return None

    def get_list_comment(self, events: list) -> str | None:
        """조회 결과 바쁜 정도 코멘트"""
        try:
            if len(events) < 3:
                return None
            context = f"조회된 일정 목록:\n{json.dumps(events, ensure_ascii=False, indent=2)}"
            full_prompt = f"{LIST_COMMENT_PROMPT}\n\n{context}"
            response = self.model.generate_content(full_prompt)
            raw = response.text.strip()
            result = self._parse_json_response(raw)
            return result.get("comment")
        except Exception as e:
            logger.error(f"List comment error: {e}")
            return None

    def analyze_events(self, events: list, question: str) -> str:
        """고차원 분석 질문 처리 - 일정 데이터 + 질문을 Gemini에게 넘겨서 분석"""
        try:
            context = (
                f"일정 데이터:\n{json.dumps(events, ensure_ascii=False, indent=2)}\n\n"
                f"질문: {question}"
            )
            full_prompt = f"{ANALYZE_PROMPT}\n\n{context}"
            response = self.model.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Analyze error: {e}")
            return "❗ 분석 중 오류가 발생했어요."

    def get_modify_event(self, event: dict, request: str) -> dict:
        """기존 일정 수정 - Gemini가 수정된 필드 반환"""
        try:
            context = (
                f"기존 일정:\n{json.dumps(event, ensure_ascii=False, indent=2)}\n\n"
                f"수정 요청: {request}"
            )
            full_prompt = f"{MODIFY_PROMPT}\n\n{context}"
            response = self.model.generate_content(full_prompt)
            raw = response.text.strip()
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error(f"Modify error: {e}")
            return None

    def get_delete_comment(self, title: str) -> str:
        """삭제 후 살갑고 자연스러운 멘트"""
        import random
        comments = [
            f"'{title}' 일정 삭제했어요! 다른 일정이 생기면 알려주세요 😊",
            f"'{title}' 일정을 캘린더에서 지웠어요 👌",
            f"네, '{title}' 일정 삭제 완료했습니다!",
            f"'{title}' 일정 없앴어요. 편하게 쉬세요~ ✨",
        ]
        return random.choice(comments)


ASSISTANT_COMMENT_PROMPT = """당신은 친근하고 센스 있는 한국어 개인 비서입니다.
사용자가 등록하려는 새 일정과 같은 날 기존 일정들을 보고,
자연스럽고 간결한 한국어로 한 줄 코멘트를 해주세요.

체크 우선순위:
1. 기존 일정과 시간이 겹치면 → 강하게 경고 ⚠️
2. 전후 일정과 간격이 30분 미만 → 이동시간 경고
3. 23시 이후 또는 06시 이전 일정 → 언급 🌙
4. 이날 일정이 3개 이상 → 바쁜 하루 언급
6. 제목에 식사/점심/저녁/밥/술/회식 키워드 → 맛있는 거 드시겠네요 🍽️
7. 제목에 생일/기념일/anniversary 키워드 → 축하 멘트 🎉
8. 토/일 일정 → 주말 언급
9. 이슈 없으면 null 반환 (코멘트 강요 금지)

반드시 JSON으로만 반환:
{"comment": "코멘트 내용"} 또는 {"comment": null}

좋은 코멘트 예시:
- "앞 일정이랑 20분밖에 안 남았어요 ⚠️ 이동시간 괜찮으세요?"
- "밤 11시 일정이네요 🌙 맞나요?"
- "오늘 일정이 벌써 4개네요. 바쁜 하루가 될 것 같아요 💪"
- "맛있는 저녁 드시겠네요 🍽️"
- "주말에도 일정이 있으시네요 😊"
- "특별한 날이네요 🎉 즐거운 시간 보내세요!"
"""

BRIEFING_SUMMARY_PROMPT = """당신은 친근한 한국어 개인 비서입니다.
오늘과 내일 일정 목록을 보고, 자연스러운 한 줄 요약 코멘트를 해주세요.
일정이 없으면 여유로운 하루라고 말해주세요.
딱 1~2문장, 반말 금지, JSON으로만 반환.

{"summary_today": "오늘 요약", "summary_tomorrow": "내일 요약"}
"""

LIST_COMMENT_PROMPT = """당신은 친근하고 센스있는 한국어 개인 비서입니다.
조회된 일정 목록을 보고 따뜻하고 자연스러운 말투로 짧게 코멘트해 주세요.
반드시 JSON: {"comment": "코멘트"} 또는 {"comment": null}

기준 및 말투 예시:
- 0~2개: null
- 3개: "오늘 일정이 3개네요. 바쁜 하루가 될 것 같아요 💪"
- 4개 이상: "일정이 꽤 빡빡하게 잡혀 있어요! 이동 시간도 챙기세요 🏃"
- 야간(22시 이후) 일정 포함: "야간 일정이 포함돼 있어요 🌙 무리하지 마세요!"
- 연속 4시간 이상 쉬는 시간 없이 일정: "쉬는 시간 없이 연속 일정이에요. 중간에 잠깐 쉬어가세요 ☕"
- 이슈 없으면 null
"""

ANALYZE_PROMPT = """당신은 친근하고 똑똑한 한국어 개인 비서입니다.
주어진 일정 데이터를 분석하여 사용자의 질문에 답해주세요.

분석 규칙:
- 점심 가능한 날: 11:00~13:00 사이에 시간 일정이 없는 날 (종일 일정은 무시)
- 저녁 가능한 날: 18:00~20:00 사이에 시간 일정이 없는 날
- 오전 빈 시간: 09:00~12:00 사이에 일정이 없는 날
- 바쁜 날: 일정 개수가 많거나 시간 일정이 빽빽한 날
- DAY OFF / 휴무 등 종일 일정도 바쁜 날 판단 시 고려
- 날짜 표시는 MM/DD (요일) 형식

답변:
- 친근하고 자연스러운 한국어
- 결과를 간결한 목록으로 정리
- 이모지 적절히 사용
- 마크다운 없이 일반 텍스트로
"""

MODIFY_PROMPT = """당신은 일정 수정 전문가입니다.
기존 일정과 수정 요청을 받아서 수정된 일정을 JSON으로 반환하세요.

규칙:
- 수정 요청에 명시된 필드만 변경, 나머지는 그대로 유지
- 제목(title)을 바꿀 때는 사용자가 입력한 텍스트를 절대 요약하거나 일부 단어를
  빼지 말고 그대로 사용. 예: "제목을 점심 홍길동으로 바꿔줘" → title: "점심 홍길동"
  ("점심"을 카테고리/시간대 힌트로만 해석해서 "홍길동"만 남기면 안 됨)
- 시간 변경 시 time_start, time_end 모두 조정 (time_end가 없으면 time_start + 1시간)
- 날짜 형식: YYYY-MM-DD, 시간 형식: HH:MM (24시간제)
- 반드시 전체 일정 JSON 객체 반환 (id 포함)

반드시 JSON만 반환
"""