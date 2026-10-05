"""
brand_in은 그대로 두고 carrier_summary만 재생성 (스크래핑 재실행 불필요).
"""
from ktoa_mvno_firestore import build_carrier_summary

YM = "2026-07"
build_carrier_summary(YM)
print("carrier_summary 재생성 완료")