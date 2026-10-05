"""
두 파이프라인(기존 ktoa_daily / 신규 ktoa_carrier_summary) 교차검증 결과를
둘만 있는 텔레그램 방으로 전송.
"""
import os
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
PRIVATE_CHAT_ID = "-1003761301521"  # 둘만 있는 방

msg = """✅ MNP 데이터 교차검증 결과 (2026-07 전체)

기존 파이프라인(ktoa_daily, KTOA "MVNO 통합" 탭 기준)과
신규 파이프라인(ktoa_carrier_summary, 전체 사업자 상세 130개 합산) 대조 완료.

검증 범위: 2026-07-01 ~ 2026-07-27 (27일)
검증 지표: MVNO IN/OUT(SM·KM·LM), MNO Out(S·K·L) — 일별 9개 지표

결과: 27일 × 9지표 = 243개 숫자 전부 완전 일치 (불일치 0건)

두 파이프라인이 서로 다른 소스(6사 요약 화면 vs 개별 사업자 130개)에서
독립적으로 수집했음에도 정확히 같은 결과가 나와, 신규 파이프라인의
정확성이 교차검증으로 확인됨."""

url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
resp = requests.post(url, json={"chat_id": PRIVATE_CHAT_ID, "text": msg}, timeout=10)
result = resp.json()
if result.get("ok"):
    print("전송 완료")
else:
    print(f"전송 실패: {result}")