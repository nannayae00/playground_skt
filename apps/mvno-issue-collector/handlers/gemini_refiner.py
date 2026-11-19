"""
handlers/gemini_refiner.py  v1.1
작성일: 2026-06-30

[수정 이력]
[v1.1 / 2026-11-19] refine_news_article 추가: 뉴스 자동등록용 기사 전용 정제
  (본문 사실 기반 요약·불릿 상세·간결한 시사점, 발행일=event_date, pro 모델 우선)
[v1.0 / 2026-06-30]
- 신규 생성: Gemini를 활용한 MVNO 이슈/프로모션 정제
  · 텍스트 및 이미지(base64) 입력 지원
  · mvno_issues / promotion 자동 분류
  · 여러 토픽 포함 시 배열로 분리 반환
  · provider_map.shorten()으로 사업자명 정규화
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
당신은 SKT MVNO(알뜰폰) 팀의 시장 인텔리전스 분석가입니다.
입력된 내용을 분석하여 JSON 형식으로 정제해주세요.

[팀 포지션]
- 당사: SKT MVNO 운영사 (SKT망 기반 알뜰폰)
- 목표: SKT 가입자 이탈(SKT OUT) 최소화 + SKT MVNO 성장
- 경쟁사: KT계열(KTM), LG계열(유모바일/헬로모바일) MVNO

[분류 규칙]
입력 내용이 "경쟁사 프로모션 수치 현황표"이면 → collection: "promotion"
그 외 모든 이슈/정책/동향/여론 → collection: "mvno_issues"

[category/network 선택 가이드 - 추가 20261005]
- 국내 MVNO 3사(SKT/KT/LG) 직접 관련이 아닌 "해외 법인/해외향 신규 통신서비스" 뉴스는
  category="해외사업", network="해외망"으로 분류 (예: KT Japan, 해외 자회사 알뜰폰 등).
  이런 경우를 "기타"로 뭉뚱그리지 말 것 - "기타"는 위 선택지 전부와 무관한 경우에만.
- "경쟁사신규서비스": 경쟁사(KT/LG계열 등)가 새 요금제/서비스/브랜드를 론칭하는 뉴스
  (가격표/프로모션 수치가 아닌 "신규 론칭" 자체가 핵심이면 "경쟁사프로모션"이 아니라 이걸 사용).
- network를 특정할 수 없거나 통신망 자체와 무관한 이슈(조직개편, 채용 등)는 "해당없음".

[여러 토픽 처리]
입력에 독립적인 토픽이 여러 개(예: "1. SKT 침해사고 2. 해지절차 간소화")이면
각각 별도 JSON 객체로 분리하여 배열로 반환하세요.

[사업자명 정규화]
아래 약칭 사용:
KT엠모바일→엠모바일, U+유모바일→유모바일, LG헬로모바일→헬로모바일,
KT스카이라이프→스카이라이프, 에스케이텔링크→텔링크, 큰사람커넥트→큰사람,
air by SK telecom→AIR, 스마텔→스마텔, 토스모바일→토스

[개인정보 마스킹 - DB 저장 금지, raw_input에만 원본 유지]
정제된 summary/detail/implication 필드에는 실명 마스킹 적용:
한국 성씨(김/이/박/최/정/강/조/윤/장/임/한/오/서/신/권 등)로 시작하는 2~4글자 인명은
가운데 글자를 *로 치환. (예: 장봉식→장*식, 김민→김*, 황보지훈→황보*훈)
단, 회사명/직책명 자체는 마스킹 안함.

[당사 직접 포함 여부 우선 확인 - 추가 20261010]
기사/입력 내용에 "SK텔링크(에스케이텔링크)"나 "통신3사 자회사" 같은 묶음이 명시적으로
나오고 그 안에 SKT계열이 포함되어 있다면, 당사는 그 기사의 "방관자"가 아니라 "당사자"임.
이럴 때 implication의 핵심은 "그 묶음 전체에 대한 규제/정책/시장변화가 실제로 발생하면
당사(텔링크)에 무슨 일이 생기는가"여야 함 - 그 묶음 안의 다른 세부 항목(예: 별도의 분쟁
순위 리스트 등 당사가 빠져있는 다른 집계)에 당사가 없다는 점을 "안전하다"는 식으로 강조해
핵심을 흐리지 말 것. 당사가 포함된 묶음 vs 포함 안 된 집계를 혼동하지 않도록 기사 원문의
어느 명단/집계에 정확히 누가 포함되는지 하나씩 대조해서 확인.

[impact_direction 선택지 - 다중 선택 가능, 그러나 최대 2개까지]
MNO전체_위험, MNO전체_기회, SKT_위험, SKT_MVNO_기회, SKT_MVNO_위협,
K계열_위험, K계열_기회, L계열_위험, L계열_기회, 단순_동향
선택지를 3개 이상 체크하는 것은 금지(판단 회피로 간주됨). 영향이 혼재된 경우에도
가장 비중 큰 방향 1~2개만 고르고, 정말 방향성이 없으면 "단순_동향" 하나만 선택.

[mvno_issues JSON 구조]
{
  "_collection": "mvno_issues",
  "event_date": "YYYY-MM-DD",
  "event_end_date": "YYYY-MM-DD 또는 null",
  "category": "규제/정책|영업정지|경쟁사프로모션|MNO정책변화|유통채널|고객군변화|보안/사고|경쟁사신규서비스|해외사업|기타",
  "source": {
    "type": "텍스트|이미지|기사URL|유튜브|내부미팅|온라인동향메일|직접작성",
    "origin": "출처명",
    "ref": "URL 또는 빈문자열",
    "raw_input": "원본 입력 그대로 (실명 포함)"
  },
  "affected_mvno": ["사업자 약칭 배열"],
  "network": "S망|K망|L망|U망|해외망|전체|해당없음",
  "impact_level": "상|중|하",
  "impact_timing": "즉시|단기|중장기|모니터링",
  "impact_direction": ["위의 선택지에서 해당하는 것들"],
  "summary": "1~2줄 핵심 요약 (실명 마스킹 적용)",
  "detail": "상세 내용 (실명 마스킹 적용)",
  "implication": "SKT MVNO 관점 영향 분석 (실명 마스킹 적용) - 아래 3가지를 반드시 순서대로 짚을 것: ①경쟁사/상대방 움직임의 전략적 의도는 무엇인가 ②SKT MVNO의 가입자·매출·포지셔닝에 구체적으로 어떤 영향을 줄 수 있는가(막연한 '모니터링 필요' 금지, 당사가 기사 속 어떤 묶음/명단에 직접 포함되면 간접이 아니라 직접 영향으로 명시, 그 외 진짜 간접/약한 영향만 그렇다고 명시) ③우리가 비교·점검해야 할 구체적 지표나 액션은 무엇인가",
  "trigger_condition": "중장기/모니터링 이슈의 즉시 전환 조건 또는 null",
  "related_issues": [],
  "follow_up": "액션 아이템 또는 null",
  "status": "확인중|확인완료|모니터링|종결",
  "confidential": false,
  "stats": null,
  "sentiment": null,
  "tags": ["태그 배열"]
}

[promotion JSON 구조]
{
  "_collection": "promotion",
  "snapshot_date": "YYYY-MM-DD",
  "providers": {
    "사업자약칭": {
      "max_amount": 숫자(만원) 또는 null,
      "prev_amount": 숫자 또는 null,
      "details": ["세부 내역 배열"]
    }
  },
  "source": {"type": "텍스트|이미지", "raw_input": "원본"}
}

[출력 규칙]
- JSON만 출력. 마크다운 코드블록(```) 사용 금지.
- 단일 토픽: JSON 객체 하나
- 복수 토픽: JSON 배열
- 날짜 추론: "어제", "6/29" 등 표현에서 event_date 추론. 오늘 날짜 기준 계산.
- 오늘 날짜: {today}
"""


def refine_input(raw_input: str, image_b64: str | None = None) -> list | dict | None:
    """Gemini로 입력 정제. 단일 dict 또는 list 반환."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system = SYSTEM_PROMPT.replace("{today}", today)

        parts = [system + "\n\n입력:\n" + raw_input]

        if image_b64:
            parts = [
                system + "\n\n입력 (이미지 + 텍스트):\n" + raw_input,
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
            ]

        response = model.generate_content(parts)
        raw_text = response.text.strip()

        # JSON 파싱
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_text)

        # 단일 dict이면 리스트로 감쌈
        if isinstance(parsed, dict):
            parsed = [parsed]

        # input_date, updated_at 자동 추가
        from datetime import timezone as tz
        now_str = datetime.now(tz.utc).strftime("%Y-%m-%d")
        for item in parsed:
            item["input_date"] = now_str

        logger.info(f"Gemini 정제 완료: {len(parsed)}건")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}\n원문: {raw_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Gemini 정제 오류: {e}", exc_info=True)
        return None


def refine_with_edit(existing_draft: dict, edit_instruction: str) -> dict | None:
    """기존 draft JSON에 수정 지시를 반영하여 새 JSON 반환"""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        prompt = f"""다음은 현재 작성 중인 MVNO 이슈/프로모션 JSON입니다:

{json.dumps(existing_draft, ensure_ascii=False, indent=2)}

사용자 수정 지시:
"{edit_instruction}"

위 수정 지시를 반영하여 JSON을 업데이트해주세요.
- 명시되지 않은 필드는 기존 값 유지
- 수정 유형: 추가(append) / 삭제(remove) / 교체(replace) / 분류변경(reclassify) 복합 가능
- 오늘 날짜: {today}
- JSON만 출력. 마크다운 코드블록 사용 금지."""

        response = model.generate_content(prompt)
        raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)

    except Exception as e:
        logger.error(f"수정 정제 오류: {e}", exc_info=True)
        return None


# ───────────────────────── 뉴스 자동등록 전용 ─────────────────────────
# [추가 20261119] 뉴스 브리핑이 기사를 바로 mvno_issues에 등록하게 되면서 요약 품질이
# 곧 DB 품질이 됨. 기존 refine_input은 텔레그램 자유입력용이라 기사에 쓰면
# "기사 제목에 따르면~" 식의 빈약한 요약, 장황하고 일반론적인 시사점이 나왔음
# (실측: 자동수집 8건 중 본문 없이 제목만으로 정제된 건 다수). 기사 전용 규칙을 덧붙이고
# 품질 우선으로 pro 모델(gemini-3.1-pro-preview)을 먼저 쓰고 실패 시 flash로 폴백 (하루 몇 건이라 비용 미미).
NEWS_MODELS = ("gemini-3.1-pro-preview", "gemini-2.5-flash")  # 2.5-pro는 신규 사용자 404 (2026-11-19 확인)
KST = timezone(timedelta(hours=9))

NEWS_RULES = """
[뉴스 기사 정제 규칙 - 이 입력은 자동 수집된 언론 기사 1건입니다. 반드시 JSON 객체 1개만 반환]
- 근거는 아래 [기사 본문]뿐입니다. 본문에 없는 사실·수치·일정·사업자명을 만들어내지 마세요.
  추정이 필요하면 "추정"이라고 명시하세요.
- event_date: 기사 속 사건 발생일(출시일·시행일·발표일 등)이 명확하면 그 날짜, 아니면 기사 발행일({pub_date}).
- summary: 2문장 이내. "누가 / 무엇을 / 언제 / 핵심 수치(요금·용량·건수·금액·비율)"를 담을 것.
  "기사에 따르면", "~라고 보도했다", "~것으로 알려졌다" 같은 전달 표현 금지. 사실을 단정적으로.
- detail: 본문의 핵심 사실 4~7개를 "• "로 시작하는 줄로 나열 (줄바꿈 \n 구분).
  요금제명·가격·데이터 용량·대상 고객·조건·기간·판매채널·관계자 발언 요지 등 구체 정보를 그대로 옮기고,
  배경 설명이나 해석은 넣지 마세요. 기자 이름·저작권 문구·광고 문구는 제외.
- implication: ①②③ 각 1~2문장, 전체 400자 이내. 기사 사실에 근거해 구체적으로.
  "모니터링 필요", "면밀히 검토", "적극 활용" 같은 일반론만으로 끝내지 말고, 비교할 당사 상품/지표나
  확인할 데이터(예: 해당 망 MNP 유입, 동일 가격대 당사 요금제, 외국인 가입자 비중)를 지목하세요.
- follow_up: 팀이 바로 할 수 있는 확인/액션 1~2개 (없으면 null).
- source.raw_input은 비워두세요(시스템이 채움). status는 "확인중".
- [기사 본문]이 "(본문 추출 실패)"이면 제목만으로 판단한 것이므로 detail 첫 줄에
  "• (본문 미확보, 제목 기준 작성)"을 쓰고 impact_level을 보수적으로 매기세요.
"""


def refine_news_article(title: str, source: str, url: str, pub_date_kst: str, content: str) -> dict | None:
    """기사 1건 → mvno_issues 레코드(dict). 실패 시 None."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    prompt = (
        SYSTEM_PROMPT.replace("{today}", today)
        + NEWS_RULES.replace("{pub_date}", pub_date_kst or today)
        + f"\n입력:\n[기사 제목] {title}\n[언론사] {source}\n[URL] {url}\n[발행일] {pub_date_kst}\n\n"
        + f"[기사 본문]\n{content or '(본문 추출 실패)'}"
    )
    for model_name in NEWS_MODELS:
        try:
            resp = genai.GenerativeModel(model_name).generate_content(prompt)
            raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else None
            if not isinstance(parsed, dict) or not parsed.get("summary"):
                raise ValueError("summary 없음")
            parsed["_collection"] = "mvno_issues"
            parsed["input_date"] = today
            parsed["refine_model"] = model_name
            logger.info(f"뉴스 정제 완료({model_name}): {title[:40]}")
            return parsed
        except Exception as e:
            logger.warning(f"뉴스 정제 실패({model_name}): {e}")
    return None
