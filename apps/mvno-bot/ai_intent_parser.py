#!/usr/bin/env python3
"""
AI Intent Parser
자연어 질문 → QuerySpec JSON 변환 (Gemini 기반)
실패 시 룰베이스 query_parser로 자동 fallback

[수정 이력]
v1.6 | 2026-05-11 | bw/영업일수 질문 예시 및 규칙 추가
  - 프롬프트 예시4: 잔여 영업일수(bw 기준) 질문 처리
  - 프롬프트 예시5: 월별 영업일수(bw) 비교 질문 처리
  - 영업일수(bw) 질문 규칙 추가 (monthly_goal 직접 인용, 자체계산 금지)
v1.2 | 2026-04-09 | JSON 잘림 + 마크다운 처리 개선
  - max_output_tokens: 1024 → 2048 (compare 등 복잡한 케이스 잘림 방지)
  - _extract_json(): 마크다운 코드블록 모든 변형 제거 (```json, ```JSON 등)
v1.2 | 2026-04-13 | 마크다운 출력 근본 차단 + 키워드 확장
  - AIIntentParser.__init__(): system_instruction으로 JSON 전용 모델(json_model) 별도 생성
    → "First character must be {" 강제로 마크다운 코드블록 완전 차단
  - parse(): self.model → self.json_model 사용
  - handle_message() 키워드 확장: 예측, 전망, 알려줘, 보여줘, 해줘, 많은, 높은, 낮은 등 추가
v1.1 | 2026-04-09 | JSON 파싱 실패 개선
  - _build_parser_prompt(): JSON 내 // 주석 제거 (표준 JSON 미지원으로 파싱 실패 원인)
  - parse(): generation_config를 dict → genai.types.GenerationConfig 객체로 변경
  - parse(): self.today → 호출 시점 날짜로 갱신 (장기 운영 시 날짜 고정 버그 방지)
  - _extract_json(): JSON5 스타일 주석(//) 제거 전처리 추가
  - _extract_json(): 파싱 실패 시 응답 원문 로깅 추가 (디버깅용)
v1.0 | 2026-04-09 | 최초 작성
"""

import json
import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# QuerySpec 스키마
# ============================================================

@dataclass
class SearchScope:
    this_year: bool = True
    last_year: bool = False
    recent_days: Optional[int] = None          # ranking 외 트렌드용
    start_date: Optional[str] = None           # YYYY-MM-DD
    end_date: Optional[str] = None             # YYYY-MM-DD

@dataclass
class RankingSpec:
    field: str = "mno_out.S"
    order: str = "desc"                        # desc / asc
    top_n: int = 5

@dataclass
class QuerySpec:
    # 의도
    intent: str = "query"                      # query/compare/trend/ranking/aggregate

    # 조회 날짜 (단일/복수 날짜 명시)
    target_dates: list = field(default_factory=list)   # ["2026-04-07", ...]

    # 기간 범위
    search_scope: SearchScope = field(default_factory=SearchScope)

    # 집계
    aggregation: str = "daily"                 # daily/monthly/10day/weekly

    # 지표 (None = 전체)
    fields: Optional[list] = None              # ["mno_out.S", "mvno_in.계"]

    # 랭킹형 전용
    ranking: Optional[RankingSpec] = None

    # 컨텍스트 요청
    context_same_weekday_weeks: int = 4        # 같은 요일 N주치
    context_recent_days: int = 7               # 최근 N일
    context_include_monthly_goal: bool = True
    context_include_holiday: bool = True

    # AI가 이해한 내용 (디버깅용)
    description: str = ""

    # fallback 여부
    used_fallback: bool = False


# ============================================================
# 필드명 정규화 매핑
# ============================================================

FIELD_ALIASES = {
    # T-Out / SKT Out
    "t_out": "mno_out.S",
    "t out": "mno_out.S",
    "skt_out": "mno_out.S",
    "skt out": "mno_out.S",
    "티아웃": "mno_out.S",
    "mno_out.s": "mno_out.S",      # 소문자 보정
    # KT Out / LGU Out
    "kt_out": "mno_out.K",
    "lgu_out": "mno_out.L",
    "mno_out.k": "mno_out.K",
    "mno_out.l": "mno_out.L",
    # 시장 전체
    "시장": "mvno_in.계",
    "시장size": "mvno_in.계",
    "mvno_in": "mvno_in.계",
    "mvno_in.계": "mvno_in.계",
    # SM
    "sm": "mvno_in.SM",
    "당사": "mvno_in.SM",
    "sm신규": "mvno_in.SM",
    # 순증감 (SM 당사 기본)
    "순증감": "net_change.SM",
    "net_change": "net_change.SM",
    "전체순증감": "net_change.계",
    "시장순증감": "net_change.계",
    # 누적
    "cum_t_out": "cum_mno_out.S",
    "누적_t_out": "cum_mno_out.S",
    "누적순증감": "cum_net.SM",
    "전체누적순증감": "cum_net.계",
}

VALID_FIELDS = {
    "mno_out.S", "mno_out.K", "mno_out.L", "mno_out.계",
    "mvno_in.SM", "mvno_in.KM", "mvno_in.LM", "mvno_in.계",
    "mvno_out.SM", "mvno_out.KM", "mvno_out.LM", "mvno_out.계",
    "net_change.SM", "net_change.KM", "net_change.LM", "net_change.계",
    "cum_mno_out.S", "cum_mno_out.K", "cum_mno_out.L", "cum_mno_out.계",
    "cum_mvno_in.SM", "cum_mvno_in.KM", "cum_mvno_in.LM", "cum_mvno_in.계",
    "cum_net.SM", "cum_net.KM", "cum_net.LM", "cum_net.계",
    "cum_mvno_out.SM", "cum_mvno_out.KM", "cum_mvno_out.LM", "cum_mvno_out.계",
}

VALID_INTENTS = {"query", "compare", "trend", "ranking", "aggregate"}
VALID_AGGREGATIONS = {"daily", "monthly", "10day", "weekly"}


# ============================================================
# Gemini 프롬프트 템플릿
# ============================================================

def _build_parser_prompt(question: str, today: str, today_weekday: str) -> str:
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    this_month = today[:7]
    return f"""JSON만 출력. 절대 금지: 마크다운(```), 설명, 주석, 공백 줄.
첫 글자는 반드시 {{ 이어야 함.

배경: SK MVNO(SM) 실적 분석 시스템. 사용자는 SM(SKT알뜰폰) 팀원.
- "순증감" 단독 언급 = SM 순증감(net_change.SM) 의미
- "시장 순증감"/"전체 순증감" = net_change.계
- "신규"/"in" = mvno_in.SM (SM 당사)
- "시장 신규"/"시장 규모" = mvno_in.계
- "T Out"/"티아웃"/"SKT out" = mno_out.S

오늘: {{today}}({{today_weekday}}), 어제: {{yesterday}}

intent: query(날짜조회) compare(비교) trend(추이,recent_days>=30) ranking(극값) aggregate(순기/주차/월별)
fields: mno_out.S(T-Out) mno_out.계(MNO전체) mvno_in.SM(당사신규) mvno_in.계(시장) net_change.SM(SM순증감) net_change.계(전체순증감) cum_mno_out.S(누적T-Out) cum_net.SM(SM누적순증감)

예시1→{{"intent":"query","target_dates":["{yesterday}"],"search_scope":{{"this_year":true,"last_year":false,"recent_days":null,"start_date":null,"end_date":null}},"aggregation":"daily","fields":["mno_out.S"],"ranking":null,"context_same_weekday_weeks":4,"context_recent_days":7,"context_include_monthly_goal":true,"context_include_holiday":true,"description":"어제 T-Out"}}
예시2→{{"intent":"trend","target_dates":[],"search_scope":{{"this_year":true,"last_year":false,"recent_days":30,"start_date":"{this_month}-01","end_date":"{yesterday}"}},"aggregation":"daily","fields":["net_change.SM"],"ranking":null,"context_same_weekday_weeks":0,"context_recent_days":30,"context_include_monthly_goal":true,"context_include_holiday":false,"description":"이번달 SM 순증감 트렌드"}}
예시3→{{"intent":"trend","target_dates":[],"search_scope":{{"this_year":true,"last_year":false,"recent_days":30,"start_date":"{this_month}-01","end_date":"{yesterday}"}},"aggregation":"daily","fields":["mno_out.S","net_change.SM"],"ranking":null,"context_same_weekday_weeks":0,"context_recent_days":30,"context_include_monthly_goal":true,"context_include_holiday":false,"description":"5월 마감예상 SKT OUT 및 SM 순증감"}}

예시4→{{"intent":"trend","target_dates":[],"search_scope":{{"this_year":true,"last_year":false,"recent_days":null,"start_date":"{this_month}-01","end_date":"{yesterday}"}},"aggregation":"daily","fields":["bw_manual","bw_ai_prev"],"ranking":null,"context_same_weekday_weeks":0,"context_recent_days":31,"context_include_monthly_goal":true,"context_include_holiday":false,"description":"5월 잔여 영업일수(bw 기준)"}}
예시5→{{"intent":"compare","target_dates":[],"search_scope":{{"this_year":true,"last_year":false,"recent_days":null,"start_date":"{{last_month}}-01","end_date":"{yesterday}"}},"aggregation":"monthly","fields":["bw_manual","bw_ai_prev"],"ranking":null,"context_same_weekday_weeks":0,"context_recent_days":60,"context_include_monthly_goal":true,"context_include_holiday":false,"description":"4월과 5월 영업일수(bw) 비교"}}

영업일수(bw) 질문 규칙:
- "잔여 영업일수"/"남은 영업일" = trend intent, this_month 범위, fields:["bw_manual","bw_ai_prev"], context_include_monthly_goal:true
- "bw기준"/"영업일수 비교" = fields:["bw_manual","bw_ai_prev"] 반드시 포함
- 영업일수는 monthly_goal의 remaining_bw_manual/remaining_bw_ai 값을 직접 인용할 것 (자체 계산 금지)
- 월 총 영업일수 = 경과 bw + 잔여 bw (절대 더하지 말고 monthly_goal에서 조회)

날짜 해석 규칙:
- "마감예상"/"마감 예상"/"월말 예상" = trend intent, start_date:{{this_month}}-01, end_date:{{yesterday}}, context_include_monthly_goal:true
- "현재까지"/"어제까지" = end_date:{{yesterday}}, start_date 해당 월 1일
- "이번달" = start_date:{{this_month}}-01, end_date:{{yesterday}}
- 미래 날짜(오늘 이후) target_dates 절대 금지. 마감예상은 날짜 조회가 아닌 trend+monthly_goal 조합

질문:{question}"""


# ============================================================
# 검증 함수
# ============================================================

def _normalize_fields(fields: Optional[list]) -> Optional[list]:
    """필드명 소문자/별칭 → 정규화"""
    if fields is None:
        return None
    result = []
    for f in fields:
        normalized = FIELD_ALIASES.get(f.lower(), f)
        if normalized in VALID_FIELDS:
            result.append(normalized)
        else:
            logger.warning(f"알 수 없는 필드명 무시: {f}")
    return result if result else None


def _validate_date(date_str: str) -> bool:
    """날짜 형식 + 유효성 검증"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # 너무 먼 과거/미래 차단
        if dt.year < 2024 or dt.year > 2030:
            return False
        return True
    except ValueError:
        return False


def _validate_and_fix(raw: dict, today: date) -> Optional[QuerySpec]:
    """
    Gemini 출력 dict → QuerySpec 변환 + 검증
    치명적 오류 시 None 반환 (→ fallback)
    """
    try:
        intent = raw.get("intent", "query")
        if intent not in VALID_INTENTS:
            logger.warning(f"알 수 없는 intent: {intent}, query로 보정")
            intent = "query"

        # target_dates 검증
        target_dates = []
        for d in raw.get("target_dates", []):
            if isinstance(d, str) and _validate_date(d):
                target_dates.append(d)
            else:
                logger.warning(f"유효하지 않은 날짜 제외: {d}")

        # target_dates 없는 query → 어제
        if intent == "query" and not target_dates:
            yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            target_dates = [yesterday]
            print(f"날짜 없는 query → 어제({yesterday}) 사용")

        # search_scope
        scope_raw = raw.get("search_scope", {})
        scope = SearchScope(
            this_year=scope_raw.get("this_year", True),
            last_year=scope_raw.get("last_year", False),
            recent_days=scope_raw.get("recent_days"),
            start_date=scope_raw.get("start_date"),
            end_date=scope_raw.get("end_date"),
        )
        # start/end 날짜 검증
        if scope.start_date and not _validate_date(scope.start_date):
            scope.start_date = None
        if scope.end_date and not _validate_date(scope.end_date):
            scope.end_date = None

        # ranking intent 보정
        if intent == "ranking":
            scope.this_year = True
            scope.last_year = True
            scope.recent_days = None

        # aggregation
        aggregation = raw.get("aggregation", "daily")
        if aggregation not in VALID_AGGREGATIONS:
            aggregation = "daily"

        # fields 정규화
        fields = _normalize_fields(raw.get("fields"))

        # ranking 스펙
        ranking = None
        if intent == "ranking" and raw.get("ranking"):
            r = raw["ranking"]
            ranking = RankingSpec(
                field=_normalize_fields([r.get("field", "mno_out.S")])[0]
                      if _normalize_fields([r.get("field", "mno_out.S")]) else "mno_out.S",
                order=r.get("order", "desc") if r.get("order") in ("asc", "desc") else "desc",
                top_n=int(r.get("top_n", 5)),
            )
            if ranking.field not in VALID_FIELDS:
                ranking.field = "mno_out.S"

        return QuerySpec(
            intent=intent,
            target_dates=target_dates,
            search_scope=scope,
            aggregation=aggregation,
            fields=fields,
            ranking=ranking,
            context_same_weekday_weeks=int(raw.get("context_same_weekday_weeks", 4)),
            context_recent_days=int(raw.get("context_recent_days", 7)),
            context_include_monthly_goal=bool(raw.get("context_include_monthly_goal", True)),
            context_include_holiday=bool(raw.get("context_include_holiday", True)),
            description=str(raw.get("description", "")),
        )

    except Exception as e:
        logger.error(f"QuerySpec 변환 실패: {e}")
        return None


# ============================================================
# Fallback: 룰베이스 → QuerySpec 변환
# ============================================================

def _fallback_to_queryspec(question: str, today: date) -> QuerySpec:
    """
    query_parser.py 룰베이스 결과를 QuerySpec으로 변환
    AI 파싱 완전 실패 시 사용
    """
    from query_parser import QueryParser

    parser = QueryParser(base_date=today)
    intent_obj = parser.parse(question)

    target_dates = []
    start_date = None
    end_date = None

    if intent_obj.periods:
        p = intent_obj.periods[0]
        if p.start_date == p.end_date:
            target_dates = [p.start_date.strftime("%Y-%m-%d")]
        else:
            start_date = p.start_date.strftime("%Y-%m-%d")
            end_date = p.end_date.strftime("%Y-%m-%d")

    # aggregation 매핑
    agg_map = {
        "daily": "daily",
        "10day": "10day",
        "weekly": "weekly",
        "monthly": "monthly",
        "yearly": "monthly",
    }

    spec = QuerySpec(
        intent="query",
        target_dates=target_dates,
        search_scope=SearchScope(
            this_year=True,
            last_year=False,
            start_date=start_date,
            end_date=end_date,
        ),
        aggregation=agg_map.get(intent_obj.aggregation, "daily"),
        fields=None,
        description=f"[룰베이스 fallback] {intent_obj.aggregation} / {intent_obj.comparison}",
        used_fallback=True,
    )

    logger.info(f"Fallback QuerySpec: {spec.description}")
    return spec


# ============================================================
# 메인 파서 클래스
# ============================================================

class AIIntentParser:
    """
    자연어 질문 → QuerySpec
    Gemini 실패 시 룰베이스 fallback 자동 전환
    """

    def __init__(self, gemini_model):
        """
        Args:
            gemini_model: google.generativeai.GenerativeModel 인스턴스
        """
        self.model = gemini_model
        self.today = datetime.now().date()
        # ★ [v1.2] JSON 전용 모델 — system_instruction으로 마크다운 완전 차단
        try:
            import google.generativeai as genai
            self.json_model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction="You are a JSON-only output machine. Output raw JSON with no markdown, no code blocks, no explanation. First character must be {."
            )
        except Exception:
            self.json_model = gemini_model  # fallback to original model

    def parse(self, question: str) -> QuerySpec:
        """
        메인 파싱 엔트리포인트
        ★ [v1.1] 호출 시점 날짜 갱신 + GenerationConfig 객체 사용
        """
        # ★ 호출 시점 날짜 갱신 (초기화 시 고정되지 않도록)
        self.today = datetime.now().date()
        today_str = self.today.strftime("%Y-%m-%d")
        weekday_kr = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][self.today.weekday()]

        prompt = _build_parser_prompt(question, today_str, weekday_kr)

        # Step 1: Gemini 호출 (JSON 전용 모델 사용)
        try:
            import google.generativeai as genai
            response = self.json_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=2048,
                )
            )
            raw_text = response.text.strip()
            logger.info(f"AI 파서 원문: {raw_text[:300]}")

        except Exception as e:
            logger.error(f"Gemini 호출 실패: {e} → fallback")
            return _fallback_to_queryspec(question, self.today)

        # Step 2: JSON 추출
        raw_dict = self._extract_json(raw_text)
        if raw_dict is None:
            logger.warning(f"JSON 추출 실패 → fallback (원문: {raw_text[:200]})")
            return _fallback_to_queryspec(question, self.today)

        # Step 3: 검증 + QuerySpec 변환
        spec = _validate_and_fix(raw_dict, self.today)
        if spec is None:
            logger.warning("QuerySpec 검증 실패 → fallback")
            return _fallback_to_queryspec(question, self.today)

        logger.info(f"AI 파서 성공: intent={spec.intent}, desc={spec.description}")
        return spec

    def _extract_json(self, text: str) -> Optional[dict]:
        """
        응답에서 JSON 블록 추출
        ★ [v1.1] JS 스타일 주석(//) 제거 전처리 추가
        ★ [v1.2] 마크다운 코드블록 변형 전부 처리, 파싱 실패 시 원문 로깅
        """
        # 마크다운 코드블록 모든 변형 제거
        text = re.sub(r"```[\w]*\s*", "", text)  # ```json, ```JSON, ``` 등
        text = re.sub(r"```", "", text)
        text = text.strip()

        # 중괄호 범위 추출
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning(f"JSON 중괄호 없음. 원문: {text[:150]}")
            return None

        json_str = text[start:end]

        # JS 스타일 주석 제거 (// ... 줄 끝까지)
        json_str = re.sub(r'//[^\n]*', '', json_str)
        # 후행 콤마 제거 (JSON 표준 위반)
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 오류: {e}\n원문: {json_str[:300]}")
            return None


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    import os
    import google.generativeai as genai

    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    model = genai.GenerativeModel("gemini-2.0-flash")
    parser = AIIntentParser(model)

    test_cases = [
        # P0
        ("3월 11일 티아웃",              "query",    ["2026-03-11"]),
        ("어제 실적",                    "query",    None),
        ("이번달 순증감",               "query",    None),
        ("3월 누적 T Out",              "query",    None),
        ("지난주 화요일이랑 이번주 화요일 비교", "compare", None),
        # ranking
        ("SKT 많이 빠진 날이 언제야",    "ranking",  None),
        ("SM 가장 잘 나온 날",          "ranking",  None),
        ("티아웃이 제일 적었던 날",      "ranking",  None),
        # trend
        ("요즘 시장 흐름 어때",          "trend",    None),
        # aggregate
        ("3월 순기별 실적",             "aggregate","10day"),
        # fallback 유도
        ("ㅌㅇ 어때",                   None,       None),
        ("안녕",                        "query",    None),
    ]

    print("=" * 70)
    pass_count = 0
    for question, expected_intent, expected_dates in test_cases:
        spec = parser.parse(question)
        ok = (expected_intent is None) or (spec.intent == expected_intent)
        mark = "✅" if ok else "❌"
        if ok: pass_count += 1
        print(f"\n{mark} [{spec.intent}{'→fallback' if spec.used_fallback else ''}] {question}")
        print(f"   dates={spec.target_dates} scope=({spec.search_scope.this_year}/{spec.search_scope.last_year}) agg={spec.aggregation}")
        print(f"   fields={spec.fields} desc={spec.description}")

    print(f"\n{'='*70}")
    print(f"결과: {pass_count}/{len([c for c in test_cases if c[1]])} 통과")