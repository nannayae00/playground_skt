"""
find_duplicate_brand_names.py  v1.0
작성일: 2026-08-17

[수정 이력]
v1.0 (2026-08-17): 최초 작성. KCT(원본명 5개로 쪼개짐)/한패스(원본명이
  "한패스SKT" vs "한패스모바일[LG]"로 달라서 clean_name이 "한패스" vs
  "한패스모바일" 둘로 쪼개짐) 사례를 보고, 이런 패턴이 전체 사업자 중에
  또 있는지 전수조사하기 위해 작성.

  판정 방식: ktoa_mvno_brand_insights의 문서ID(=clean_name) 전체를 모아서,
  서로 포함관계(한쪽이 다른쪽의 부분문자열)인 쌍을 후보로 뽑음 - 완벽한
  탐지는 아니지만(진짜 다른 회사인데 이름이 우연히 겹치는 경우도 섞일 수
  있음) 1차 스크리닝용으로 충분함. 후보로 나온 쌍은 debug_hanpass.py처럼
  개별로 더 깊게 확인해서 진짜 합칠지 판단할 것.

사용법:
    python3 find_duplicate_brand_names.py
"""

from ktoa_mvno_period_aggregator import _get_db

db = _get_db()

docs = list(db.collection("ktoa_mvno_brand_insights").stream())
names = sorted(d.id for d in docs)
print(f"전체 사업자(문서) 수: {len(names)}\n")

candidates = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        if a == b:
            continue
        # 포함관계(부분문자열)면 후보 - 단, 너무 짧은 이름(2자 이하)은 오탐 많아서 제외
        if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
            candidates.append((a, b))

print(f"=== 이름이 서로 포함관계인 후보 {len(candidates)}쌍 (합칠지 검토 필요) ===\n")
for a, b in candidates:
    print(f"'{a}'  <->  '{b}'")

if not candidates:
    print("(포함관계 후보 없음 - 이 기준으로는 추가로 합칠 게 안 보입니다)")