"""
handlers/gemini_refiner.py  v1.0
작성일: 2026-06-30

[수정 이력]
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
from datetime import datetime, timezone

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

[impact_direction 선택지 - 다중 선택 가능]
MNO전체_위험, MNO전체_기회, SKT_위험, SKT_MVNO_기회, SKT_MVNO_위협,
K계열_위험, K계열_기회, L계열_위험, L계열_기회, 단순_동향

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
  "implication": "SKT MVNO 관점 영향 분석 (실명 마스킹 적용) - 아래 3가지를 반드시 순서대로 짚을 것: ①경쟁사/상대방 움직임의 전략적 의도는 무엇인가 ②SKT MVNO의 가입자·매출·포지셔닝에 구체적으로 어떤 영향을 줄 수 있는가(막연한 '모니터링 필요' 금지, 영향이 간접적/약하면 그렇다고 명시) ③우리가 비교·점검해야 할 구체적 지표나 액션은 무엇인가",
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
