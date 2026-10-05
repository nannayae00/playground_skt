"""
save_brand_context.py
Context DB(ktoa_brand_context_daily/weekly/monthly) 저장 헬퍼

[수정 이력]
- v2.0 (2026-08-27): 설계 전면 변경(사용자 확정) - 사업자별 필드 구조화 저장
  방식을 폐기하고, 기존 ktoa_context 컬렉션과 동일한 패턴(문서 1개 = 기간
  1개, text 필드에 텔레그램 리포트 원문을 통째로 저장)으로 변경. "다른
  프로그램에서 그걸 쪼개서 보면 될듯" - 파싱/구조화는 컨슈머(대시보드) 쪽
  책임으로 넘기고, 여기서는 메시지1~4 원문을 이어붙여 그대로 저장하는 것으로
  단순화. v1.x의 build_context_doc/save_docs/collect_*_context_rows류 함수는
  전부 폐기(사업자별 in/out/baseline/sev를 따로 계산하던 로직 불필요해짐).
- v1.2~v1.0: (사업자별 필드 구조화 저장 - 폐기됨, 히스토리만 남김)
"""

from google.cloud import firestore

VERSION = "v1.0"


def build_full_text(messages: list) -> str:
    """
    메시지 리스트(None은 제외)를 기존 콘솔 출력(main()의 '='*50 구분선)과
    동일한 형태로 이어붙임 - 사람이 읽어도 텔레그램으로 나간 것과 똑같이
    보이고, 다른 프로그램이 파싱할 때도 이 구분선을 기준으로 쪼개면 됨.
    """
    sep = "\n\n" + "=" * 50 + "\n\n"
    return sep.join(m for m in messages if m)


def save_context_text(db: firestore.Client, collection: str, doc_id: str, fields: dict) -> None:
    """
    기존 ktoa_context 컬렉션과 동일한 패턴으로 저장: 문서 1개 = 기간 1개,
    text 필드에 리포트 원문. fields에 date(daily) 또는
    period_start/period_end(weekly/monthly) + text를 담아서 넘기면
    saved_at(서버 타임스탬프)/version을 붙여서 저장.
    """
    doc = dict(fields)
    doc["saved_at"] = firestore.SERVER_TIMESTAMP
    doc.setdefault("version", VERSION)
    db.collection(collection).document(doc_id).set(doc)