"""
handlers/summary.py  v1.0
작성일: 2026-06-30

[수정 이력]
[v1.0 / 2026-06-30]
- 신규 생성: /summary 수동 조회 + daily 자동 리포트
  · 최근 7일 mvno_issues 요약
  · 최신 promotion 현황
  · Gemini 인사이트 생성
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
import google.generativeai as genai

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT", "mvno-484509")
DATABASE = "mvno-data"
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID, database=DATABASE)
    return _db


def build_summary(days: int = 7) -> str:
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # 최근 이슈 조회
    issues = list(
        db.collection("mvno_issues")
        .where("event_date", ">=", since)
        .order_by("event_date", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )

    # 최신 promotion
    promos = list(
        db.collection("promotion")
        .order_by("snapshot_date", direction=firestore.Query.DESCENDING)
        .limit(3)
        .stream()
    )

    if not issues and not promos:
        return f"📭 최근 {days}일간 등록된 이슈가 없습니다."

    # 이슈 목록 구성
    lines = [f"📊 <b>MVNO 시장 인텔리전스 요약</b> (최근 {days}일)\n"]

    # 즉시/단기 이슈 우선
    urgent = [i for i in issues if i.to_dict().get("impact_timing") in ("즉시", "단기")]
    others = [i for i in issues if i not in urgent]

    if urgent:
        lines.append("🔴 <b>즉시/단기 이슈</b>")
        for doc in urgent[:5]:
            d = doc.to_dict()
            lines.append(f"• [{d.get('event_date','')}] {d.get('summary','')[:80]}")
            lines.append(f"  └ {', '.join(d.get('impact_direction',[]))}")

    if others:
        lines.append("\n🟡 <b>중장기/모니터링</b>")
        for doc in others[:5]:
            d = doc.to_dict()
            lines.append(f"• [{d.get('event_date','')}] {d.get('summary','')[:80]}")

    # 최신 프로모션
    if promos:
        lines.append("\n💰 <b>최신 자회사 프로모션 현황</b>")
        latest = promos[0].to_dict()
        lines.append(f"기준일: {latest.get('snapshot_date','')}")
        for pvdr, info in latest.get("providers", {}).items():
            amt = info.get("max_amount")
            if amt:
                lines.append(f"  • {pvdr}: 최대 {amt}만원")

    # Gemini 인사이트
    try:
        insight = _generate_insight(issues, promos)
        if insight:
            lines.append(f"\n🤖 <b>AI 인사이트</b>\n{insight}")
    except Exception as e:
        logger.warning(f"인사이트 생성 오류: {e}")

    return "\n".join(lines)


def _generate_insight(issues, promos) -> str:
    issue_texts = "\n".join([
        f"- {d.to_dict().get('summary','')} ({d.to_dict().get('impact_direction',[])})"
        for d in issues[:10]
    ])
    promo_texts = "\n".join([
        f"- {d.id}: {list(d.to_dict().get('providers',{}).keys())}"
        for d in promos[:3]
    ])

    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""다음은 최근 MVNO 시장 이슈와 프로모션 현황입니다.
SKT MVNO 팀 관점에서 핵심 시사점을 3줄 이내로 요약해주세요.

[이슈]
{issue_texts}

[프로모션]
{promo_texts}"""

    response = model.generate_content(prompt)
    return response.text.strip()[:500]


def send_daily_report():
    """Cloud Scheduler에서 매일 호출되는 daily 리포트 전송"""
    from handlers.telegram import send_message
    if not CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID 환경변수 없음")
        return

    text = build_summary(days=1)
    text = f"🌅 <b>Daily MVNO 인텔리전스</b> ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n\n" + text
    send_message(CHAT_ID, text)
    logger.info("daily 리포트 전송 완료")
