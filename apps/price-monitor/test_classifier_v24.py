#!/usr/bin/env python3
"""
MVNO Classifier v2.5 배포 전 테스트
실행: cd ~/price-monitor && python3 test_classifier_v24.py
"""
import sys, re
sys.path.insert(0, '.')
from core.mvno_classifier import normalize_provider, extract_network_from_title

TESTS = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🔴 오탐 차단 (수집되면 안 됨)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ("[토스]260606 토스 두근두근 팀플전",          "coupon",    None,        "토스 앱 이벤트"),
    ("[토스]퀴즈 퍼셀",                            "coupon",    None,        "토스 앱 퀴즈"),
    ("[토스]260606 토스알바 밸런스게임 팀플전",    "coupon",    None,        "토스 앱 게임"),
    ("토스 환율게 웃긴 상황",                      "freeboard", None,        "토스 환율"),
    ("토스 올영 퀴즈",                             "freeboard", None,        "토스 퀴즈"),
    ("정치 패널들이 이야기 하는 서울시장 패배원인", "freeboard", None,        "정치 이야기"),
    ("일본 스모 관련 몇몇 이야기",                 "freeboard", None,        "일반 이야기"),
    ("현충일 live",                                "freeboard", None,        "현충일 생방"),
    ("[CJ온스타일] 6/9 LIVE! LG 트롬 오브제",     "pmarket",   None,        "홈쇼핑 LIVE"),
    ("헬로 좋다 오늘도",                           "freeboard", None,        "헬로 일반"),
    ("티다 콘서트 티켓",                           "freeboard", None,        "티다 가수"),
    ("티다 뭐야",                                  "freeboard", None,        "티다 단독질문"),
    ("너겟 과자 맛있다",                           "freeboard", None,        "너겟 음식"),

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ✅ MVNO 정상 수집
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ("토스모바일 요금제 추천",                      "phone",     "토스모바일",  "토스모바일 정규명"),
    ("이야기모바일 5G 요금제 문의",                 "phone",     "이야기모바일","이야기모바일 정규명"),
    ("헬로모바일 고객센터 연결어떤가요",            "phone",     "헬로모바일",  "헬로모바일 정규명"),
    ("헬로 모바일 어제까지가 맞네요",               "phone",     "헬로모바일",  "헬로 모바일 띄어쓰기"),
    ("에이모바일 망했네요",                         "phone",     "에이모바일",  "에이모바일"),
    ("시월모바일 5G 150기가 27500원",              "phone",     "시월모바일",  "시월모바일"),
    ("유모바일 다모아결합 초대",                    "phone",     "U+유모바일",  "유모바일"),
    ("kg모바일 안면인증 번호이동",                  "phone",     "KG모바일",    "KG모바일"),
    ("핀다이렉트 이벤트 혜택",                      "phone",     "핀다이렉트",  "핀다이렉트"),
    ("Skylife 알뜰폰 추천인",                      "phone",     "스카이라이프","스카이라이프"),
    ("[프리티] SKT망 통화 500분 20GB",             "ppomppu",   "프리티",      "ppomppu 핫딜"),
    ("[조이텔] SK망 300분 100건 5GB",              "ppomppu",   "조이텔",      "ppomppu 핫딜"),
    ("[SKT에어] 5G망 100기가+5mbps",               "ppomppu",   "SKT에어",     "SKT에어 핫딜"),
    ("[SKT] 5G AIR 요금제 100GB+5Mbps",           "ppomppu",   "SKT에어",     "SKT AIR 조합"),
    # freeboard에서도 동반 키워드 있으면 수집
    ("토스 알뜰폰 가입했어요",                      "freeboard", "토스모바일",  "freeboard 알뜰폰"),
    ("이야기 모바일 개통 후기",                     "freeboard", "이야기모바일","freeboard 개통"),
    ("헬로 알뜰 요금제 추천해요",                   "freeboard", "헬로모바일",  "freeboard 알뜰"),

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 📶 MNO 직영 온라인 수집
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ("티다 요금제 추천",                            "phone",     "T다이렉트",   "티다 요금제"),
    ("티다 가입 후기",                              "freeboard", "T다이렉트",   "티다 가입"),
    ("티다이렉트 5G 할인",                          "phone",     "T다이렉트",   "티다이렉트"),
    ("T direct shop 5G 110GB 월 15000원",          "phone",     "T다이렉트",   "T direct shop"),
    ("T다이렉트샵 요금제",                          "phone",     "T다이렉트",   "T다이렉트샵"),
    ("너겟 요금제 5G 추천",                         "phone",     "너겟",        "너겟 요금제"),
    ("너겟 알뜰폰 후기",                            "freeboard", "너겟",        "너겟 알뜰폰"),
    ("온라인 전용 요금제, 너겟",                     "phone",     "너겟",        "너겟 전용요금제"),
]

NETWORK_TESTS = [
    ("[프리티] SKT망 통화 500분 데이터 20GB",    "SKT"),
    ("[조이텔] SK망 300분 100건 5GB",            "SKT"),
    ("[스마텔] sk망100GB+5mbps",                 "SKT"),
    ("[헬로모바일] KT망 100GB 특가",             "KT"),
    ("[시월모바일] LGU+망 150GB",                "LGU+"),
    ("[유모바일] U+망 무제한",                    "LGU+"),
    ("[SKT에어] 5G망 100기가+5mbps",             None),
    ("토스모바일 요금제 추천",                    None),
    ("SKT 에어컨 이벤트",                        None),
]

# ──────────────────────────────────────────────────────────────
MNO_DIRECT = {"너겟", "T다이렉트", "SKT에어"}

print("=" * 70)
print("🧪 MVNO Classifier v2.5 배포 전 테스트")
print("=" * 70)

pass_cnt = 0
fail_cnt = 0
fail_logs = []

print("\n📋 [1] normalize_provider 테스트")
print("-" * 70)

for title, board, exp, desc in TESTS:
    result = normalize_provider(title, board=board)
    ok = result == exp

    if ok:
        pass_cnt += 1
    else:
        fail_cnt += 1
        fail_logs.append({
            "type": "provider", "title": title, "board": board,
            "expected": exp, "got": result, "desc": desc
        })

    section = "📶직영" if result in MNO_DIRECT else ("🔔MVNO" if result else "🚫차단")
    got_str = result or "차단"
    exp_str = exp or "차단"
    status = "OK" if ok else f"FAIL(예상:{exp_str}/실제:{got_str})"
    print(f"  {'✅' if ok else '❌'} {section} [{board:10}] {title[:42]:<42} # {desc}")

print(f"\n  결과: {pass_cnt}/{len(TESTS)} 통과")

print("\n📋 [2] extract_network_from_title 테스트")
print("-" * 70)

net_pass = 0
for title, exp in NETWORK_TESTS:
    result = extract_network_from_title(title)
    ok = result == exp
    if ok:
        net_pass += 1
    else:
        fail_logs.append({
            "type": "network", "title": title,
            "expected": exp, "got": result
        })
    print(f"  {'✅' if ok else '❌'} {title:<48} → {result or '없음'} (예상:{exp or '없음'})")

print(f"\n  결과: {net_pass}/{len(NETWORK_TESTS)} 통과")

total = len(TESTS) + len(NETWORK_TESTS)
total_pass = pass_cnt + net_pass

print("\n" + "=" * 70)
print(f"📊 종합: {total_pass}/{total} 통과", "🎉" if total_pass == total else f"  ({total - total_pass}개 실패)")

if fail_logs:
    print("\n🔴 실패 상세:")
    print("-" * 70)
    for i, f in enumerate(fail_logs, 1):
        print(f"\n  [{i}] {f.get('desc', f['type'])}")
        print(f"       제목: {f['title']}")
        if 'board' in f:
            print(f"       게시판: {f['board']}")
        print(f"       예상: {f['expected'] or '차단(None)'}")
        print(f"       실제: {f['got'] or '차단(None)'}")
        if f.get('got') is None and f['expected']:
            print(f"       → 힌트: 동반 키워드 부족 or 별칭 미등록")
        elif f.get('got') and f['expected'] is None:
            print(f"       → 힌트: WEAK_ALIASES 미등록 or 오탐")
else:
    print("\n✅ 전체 통과! 배포해도 안전합니다.")