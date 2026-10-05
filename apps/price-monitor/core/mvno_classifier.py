"""
mvno_classifier.py
──────────────────────────────────────────────────────────────────────────────
MVNO 관련 게시글 필터링
- 사업자명 화이트리스트 (별칭 지원)
- 키워드 패턴 매칭
- Gemini AI 판별 (애매한 케이스)

[수정 이력]
v3.7 | 2026-09-20 | infer_network_from_provider() 추가 - firebase_handler.py가
      | 존재하지 않는 scrapers.mvno_classifier의 동명 함수를 import하려다
      | 매번 조용히 실패하던 버그를 여기에 실제 구현해서 수정 (PROVIDER_NETWORKS
      | 기반 단일망 사업자 추론)
v3.6 | 2026-09-20 | KT "요고모바일" 온라인 전용 요금제 추가 (너겟/T다이렉트/SKT에어와
      | 같은 MNO 직영 온라인 카테고리). bare "요고"는 일상어라 오탐 위험 커서
      | "kt"와 같이 나올 때만 인정 + "필요고" 등 부분일치 오탐 차단.
      | MNO_DIRECT_PROVIDERS, ppomppu_job.py의 MNO_DIRECT 섹션 분류에도 반영.
v3.5 | 2026-09-20 | (1) check_keywords: phone 게시판 "알뜰" 단어경계(\b) 매칭이
      | "알뜰통신사"/"알뜰유심"처럼 붙여쓴 복합어를 못 잡던 문제 - 부분일치 추가.
      | (2) "SKT에어" 별칭에 "에어" 단독 추가 (WEAK_ALIASES 동반키워드로 안전화) -
      | "에어 가입/유심/요금제"처럼 "SKT"/"air" 명시 안 한 실제 글들이 전부 누락됐음
v2.8 | 2026-06-15 | 트렌드 이슈 키워드 + 시월 별칭 추가
      | - 시월모바일 별칭에 "시월" 추가 (WEAK_ALIASES로 오탐 방지)
      | - TREND_ISSUE_KEYWORDS 추가: 통합요금제/5G SA/최적요금제/단통법 등
      | - is_trend_issue() 함수 추가 - 뽐뿌/디씨/유튜브 공통 사용 가능
v2.7 | 2026-06-11 | 사업자별 망/자회사/금융 정보 추가
      | - PROVIDER_NETWORKS: 사업자별 망 후보 (단일망은 확정, 다망은 후보)
      | - AFFILIATED_PROVIDERS: 통신사 자회사 목록
      | - FINANCIAL_PROVIDERS: 금융/IT 계열 목록
      | - classify_post에 is_affiliated 플래그 추가
v2.6 | 2026-06-10 | 골드번호 등 통신사 이벤트 키워드 추가 (조회수 무관)
      | - 골드번호, 선호번호, 번호세탁 등 통신사 직접 이벤트 키워드
      | - 조회수 무관 수집 (키워드 있으면 무조건)
v2.5 | 2026-06-07 | MNO 직영 온라인 사업자 추가 (너겟/T direct/SKT에어 섹션 분리)
      | - MVNO_PROVIDER_ALIASES에 너겟/T direct 추가
      | - is_mno_direct 플래그로 4섹션 분리 지원
v2.4 | 2026-06-06 | WEAK_ALIASES 도입 - 별칭별 동반 키워드 체크
      | - 토스/이야기/live/리브/헬로 등 단독 시 오탐 많은 별칭
      | - 동반 키워드(모바일/알뜰/유심/요금/개통 등) 없으면 차단
      | - 게시판 무관하게 제목 내용 기준으로 판단
v2.3 | 2026-06-06 | extract_network_from_title() 함수 추가
      | - 제목에서 룰베이스로 통신망 즉시 추출 (AI 불필요)
      | - SK망/SKT망/KT망/LGU+망/U+망 패턴 지원
v2.2 | 2026-06-06 | normalize_provider 버그 수정 (오탐 근본 원인 제거)
      | - [버그1] 정규명 체크에 board 필터 누락 → NON_MVNO_BOARDS에서도 정규명 통과되던 문제 수정
      | - [버그2] NON_MVNO_BOARDS에서 AMBIGUOUS 별칭 차단 누락 수정
      | - [버그3] "모나" 정규명 → "모나모바일"로 변경 (단독 오매칭 방지)
v2.1 | 2026-06-05 | MVNO_PROVIDER_ALIASES 전체 재정비 (공식 목록 기반 55개)
      | - 3사/2사/1사 구분, AMBIGUOUS 별칭 안전화 (오탐 방지)
      | - 프리티/조이텔 추가, SKT+AIR 분리 체크, SKT망/KT망 예외 처리
v1.8 | 2026-06-05 | board 필터 강화 및 통신사 핫글 오탐 방지
      | - NON_MVNO_BOARDS에 ppomppu/pmarket 계열 추가
      | - check_mno_high_traffic: MVNO 사업자명 있으면 통신사 핫글 제외 (조이텔/프리티 오탐 방지)
      | - SKT에어 PROVIDER_ALIASES 추가
v1.7 | 2026-06-02 | 사업자 별칭 오탐 방지
      | - 리브모바일: "live" 단독 별칭 제거 (LIVE방송 오탐)
      | - 헬로모바일: "LG헬로" 제거 (LG헬로비전 케이블TV 오탐)
      | - NON_MVNO_BOARD_STRICT: coupon/freeboard에서 짧은 별칭 제한
      | - normalize_provider: board 파라미터 추가, 게시판 기반 필터 적용
v1.6 | 2026-06-02 | check_mno_high_traffic 오탐 방지
      | - '삼성', '갤럭시', '애플' 단독 매칭 제거
      | - 단말 키워드 + 통신 맥락 동시 존재할 때만 핫글 판정
v1.5 | 2026-06-02 | ai_vision_analyze() 함수 추가
      | - 별3개(relevance_score≥7) 게시글 전용 Gemini Vision 분석
      | - 이미지에서 network/price/data_desc/contract_months 자동 추출
      | - 이미지 최대 3장, base64 인코딩 전송
v1.4 | 2026-06-02 | 오탐 방지 강화
      | - AMBIGUOUS_ALIASES에 "이야기" 추가
      | - NON_MVNO_BOARDS 상수 추가 (freeboard/coupon 등)
      | - ai_analyze_and_summarize 프롬프트: network 필드, 본문 1500자, content_summary
v1.3 | 2026-05-16 | 3사 유심 브랜드 키워드 추가 (간편유심, 바로배송유심, 원칩 등)
v1.2 | 2026-05-29 | check_mno_high_traffic() 함수 누락 복구
v1.1 | 2026-05-29 | Gemini 비용 최적화 (호출 횟수 절감)
v1.0 | 최초 작성
──────────────────────────────────────────────────────────────────────────────
"""

import re
import json
import os

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-generativeai 패키지 없음. pip install google-generativeai")

# ══════════════════════════════════════════════════════════════════════════════
# 사업자명 별칭 매핑 (정규명: [별칭들...])
# ══════════════════════════════════════════════════════════════════════════════

MVNO_PROVIDER_ALIASES = {
    # ── 3사 공통 (13개) ──────────────────────────────────────────
    "헬로모바일":    ["헬로모바일", "헬로 모바일", "LG헬로모바일", "헬로유심", "헬로"],  # 단독은 WEAK_ALIASES 동반 키워드 필수
    "토스모바일":    ["토스모바일", "toss모바일", "토스심", "토스", "toss"],  # 단독은 WEAK_ALIASES 동반 키워드 필수
    "아이즈모바일":  ["아이즈모바일", "아이즈비전"],               # "아이즈" 단독은 AMBIGUOUS
    "모빙":         ["모빙", "mobing"],
    "스마텔":       ["스마텔", "smartel"],
    "이야기모바일":  ["이야기모바일", "이야기"],                    # 단독은 WEAK_ALIASES 동반 키워드 필수
    "에이모바일":    ["에이모바일", "A모바일", "a모바일"],
    "티플러스":     ["티플러스", "T플러스", "tplus"],
    "프리티":       ["프리티", "priety", "프리티모바일", "prettymobile"],
    "핀다이렉트":   ["핀다이렉트", "핀다", "핀", "pin"],           # 단독은 WEAK_ALIASES 동반 키워드 필수
    "리브엠":       ["리브엠", "리브모바일", "liiv m", "liivm", "KB리브", "live모바일", "live", "리브"],  # 단독은 WEAK_ALIASES 동반 키워드 필수
    "스노우맨":     ["스노우맨", "snowman모바일"],                 # "snow"/"스노우" 단독은 AMBIGUOUS
    "한패스모바일":  ["한패스모바일", "한패스"],

    # ── 2사 공통 ──────────────────────────────────────────────────
    "조이텔":       ["조이텔", "joytel"],
    "고고모바일":   ["고고모바일"],                                # "고고" 단독은 AMBIGUOUS
    "안심모바일":   ["안심모바일", "에스원안심"],
    "밸류컴":       ["밸류컴"],
    "에르엘":       ["에르엘", "RL모바일"],                        # "RL" 단독은 AMBIGUOUS
    "에이프러스":   ["에이프러스", "에어프러스"],
    "여유모바일":   ["여유모바일"],
    "인스모바일":   ["인스모바일"],                                # "인스" 단독은 AMBIGUOUS
    "지엠이모바일": ["지엠이모바일", "GME모바일"],
    "친구모바일":   ["친구모바일"],
    "플래시모바일": ["플래시모바일"],

    # ── SKT 단독 ──────────────────────────────────────────────────
    "SK세븐모바일":  ["SK세븐모바일", "SK7모바일", "sk7모바일", "세븐모바일"],  # "세븐" 단독은 AMBIGUOUS
    "알비레오모바일":["알비레오모바일"],
    "SKT에어":      ["SKT에어", "에어바이SK", "air by SK telecom", "에어바이sk", "sktair", "SKT AIR", "5g air", "에어"],

    # ── MNO 직영 온라인 요금제 (별도 섹션) ──────────────────────────
    "너겟":         ["너겟", "nugget", "LGU+너겟", "U+너겟", "너겟요금제"],
    "T다이렉트":    ["T direct shop", "T다이렉트샵", "t direct", "tdirect", "T다이렉트", "티다이렉트", "티다"],
    # [v3.6] KT 온라인 전용 요금제 브랜드. "요고" 단독은 일상어("요거/이거"의 방언)라
    # 매우 흔해서 오탐 위험 큼 → 여기 별칭은 "요고모바일" 등 안전한 복합형만 등록하고,
    # bare "요고"는 normalize_provider()에서 "kt"와 같이 나올 때만 별도로 인정함
    "요고":         ["요고모바일", "요고 모바일", "kt요고", "kt 요고"],

    # ── KT 단독 ──────────────────────────────────────────────────
    "KT엠모바일":   ["KT엠모바일", "KT엠", "엠모바일", "KTM모바일", "KTM 모바일", "ktm"],
    "이지모바일":   ["이지모바일"],                                # "이지" 단독은 AMBIGUOUS
    "드림모바일":   ["드림모바일"],
    "쉐이크모바일": ["쉐이크모바일"],                              # "쉐이크" 단독은 AMBIGUOUS
    "스카이라이프": ["스카이라이프", "KT스카이라이프", "skylife"],
    "스피츠모바일": ["스피츠모바일"],
    "아이플러스유": ["아이플러스유"],
    "엔텔레콤":     ["엔텔레콤", "앤텔레콤"],
    "오파스모바일": ["오파스모바일"],
    "웰알뜰폰":     ["웰알뜰폰"],
    "케이티엠모바일":["케이티엠모바일"],
    "퍼스트모바일": ["퍼스트모바일"],

    # ── LGU+ 단독 ────────────────────────────────────────────────
    "U+유모바일":   ["유모바일", "U+유모바일", "유플러스알뜰", "유플러스유모바일"],
    "시월모바일":   ["시월모바일", "시월"],                          # "시월" 단독은 WEAK_ALIASES로 동반키워드 체크
    "슈가모바일":   ["슈가모바일"],                                # "슈가" 단독은 AMBIGUOUS
    "찬스모바일":   ["찬스모바일"],                                # "찬스" 단독은 AMBIGUOUS
    "화인통신":     ["화인통신"],
    "코나아이":     ["코나아이"],
    "온국민폰":     ["온국민폰"],
    "이지톡":       ["이지톡"],
    "위너스텔":     ["위너스텔", "winners"],
    "KCTV알뜰폰":  ["KCTV알뜰폰", "KCTV"],
    "KG모바일":    ["KG모바일", "케이지모바일"],
    "마블링":       ["마블링"],
    "사람과연결":   ["사람과연결"],
    # "아정당": 제거 - 부동산/정치 관련 오탐 多
    "우리WON모바일":["우리WON모바일", "우리원모바일"],
    "에스원안심모바일":["에스원안심모바일"],
    "더원모바일":   ["더원모바일"],                                # "더원" 단독은 AMBIGUOUS
    "모나모바일":   ["모나모바일", "mona모바일"],                   # "모나" 단독은 AMBIGUOUS에서 차단
}

# 제외할 사업자 (3대 통신사 직영)
EXCLUDE_PROVIDERS = {
    "SKT", "KT", "LG U+", "SK텔레콤", "KT텔레콤", "LG유플러스"
}

# MNO 직영 온라인 요금제 (MVNO 아님, 별도 섹션으로 분리)
MNO_DIRECT_PROVIDERS = {"너겟", "T다이렉트", "SKT에어", "요고"}

# ══════════════════════════════════════════════════════════════════════════════
# 사업자별 망 후보 (단일망=확정, 복수망=본문에서 추가 확인 필요)
# 출처: KTOA MVNO 등록 데이터 (2026.06 기준)
# ══════════════════════════════════════════════════════════════════════════════
PROVIDER_NETWORKS = {
    # ── SKT 단일망
    "SK세븐모바일":  ["SKT"],
    "알비레오모바일": ["SKT"],
    "안심모바일":    ["SKT", "KT", "LGU+"],
    "고고모바일":    ["SKT", "KT"],
    # ── KT 단일망
    "KT엠모바일":    ["KT"],   # KT망 단일
    "케이티엠모바일": ["KT"],
    "이지모바일":    ["KT"],
    "쉐이크모바일":  ["KT"],
    "드림모바일":    ["KT"],
    "스카이라이프":  ["KT"],
    "오파스모바일":  ["KT"],
    "퍼스트모바일":  ["KT"],
    # ── LGU+ 단일망
    "KG모바일":     ["LGU+"],
    "슈가모바일":    ["LGU+"],
    "시월모바일":    ["LGU+"],
    "마블링":       ["LGU+"],
    "우리WON모바일": ["SKT", "KT", "LGU+"],
    "코나아이":     ["LGU+"],
    "온국민폰":     ["LGU+"],
    "화인통신":     ["LGU+"],
    "유플러스알뜰모바일": ["LGU+"],
    "이지톡":       ["LGU+"],
    "찬스모바일":    ["LGU+"],
    # ── KT+LGU+
    "에이플러스":   ["KT", "LGU+"],
    "에르엘":       ["KT", "LGU+"],
    "인스모바일":   ["KT", "LGU+"],
    "여유모바일":   ["KT", "LGU+"],
    "밸류컴":       ["KT", "LGU+"],
    "친구모바일":   ["KT", "LGU+"],
    "지엠이모바일": ["KT", "LGU+"],
    # ── 3망 모두
    "프리티":       ["SKT", "KT", "LGU+"],
    "헬로모바일":   ["LGU+"],
    "토스모바일":   ["SKT", "KT", "LGU+"],
    "리브엠":       ["SKT", "KT", "LGU+"],
    "핀다이렉트":   ["SKT", "KT", "LGU+"],
    "스노우맨":     ["SKT", "KT", "LGU+"],
    "한패스모바일": ["SKT", "KT", "LGU+"],
    "A모바일":      ["SKT", "KT", "LGU+"],
    "에이모바일":   ["SKT", "KT", "LGU+"],
    "이야기모바일": ["SKT", "KT", "LGU+"],
    "스마텔":       ["SKT", "KT", "LGU+"],
    "아이즈모바일": ["SKT", "KT", "LGU+"],
    "모빙":         ["SKT", "KT", "LGU+"],
    "티플러스":     ["SKT", "KT", "LGU+"],
    "조이텔":       ["SKT"],
    "U+유모바일":   ["LGU+"],
}


def infer_network_from_provider(provider):
    """사업자명으로 망을 확정 추론 (단일망 사업자만, 다중망이면 None).
    [v3.6] firebase_handler.py가 존재하지 않는 scrapers.mvno_classifier의
    infer_network_from_provider를 import하려다 매번 ModuleNotFoundError로
    조용히 실패하던 문제 - 여기(core.mvno_classifier)에 실제로 구현."""
    if not provider:
        return None
    candidates = PROVIDER_NETWORKS.get(provider, [])
    return candidates[0] if len(candidates) == 1 else None


# ── 통신사 자회사 (🏢 자회사&금융 섹션)
AFFILIATED_PROVIDERS = {
    # SKT 자회사
    "SK세븐모바일",
    "알비레오모바일",
    # KT 자회사
    "KT엠모바일",      # KT엠모바일 (별칭: 엠모바일/KTM모바일/ktm)
    "케이티엠모바일",  # 케이티엠모바일 (동일 사업자 다른 표기)
    "스카이라이프",
    # LGU+ 자회사
    "U+유모바일",
    "헬로모바일",
}

# ── 금융/IT 계열 (🏢 자회사&금융 섹션)
FINANCIAL_PROVIDERS = {
    "토스모바일",   # 토스
    "리브엠",       # KB국민은행
    "우리WON모바일", # 우리은행
}

# ══════════════════════════════════════════════════════════════════════════════
# 키워드 패턴 (정규표현식)
# ══════════════════════════════════════════════════════════════════════════════

MVNO_KEYWORDS = [
    # 직접 언급
    r'\b알뜰폰\b', r'\b알뜰\b', r'\bMVNO\b', r'\bmvno\b',
    r'\b유심\b', r'\bUSIM\b', r'\busim\b', 
    r'\beSIM\b', r'\besim\b', r'\b이심\b',
    
    # 데이터 표기 패턴 (알뜰폰 특징)
    r'\d+GB\s*\+\s*\d+Mbps',     # "100GB + 5Mbps"
    r'매일\s*\d+GB',              # "매일 5GB"
    r'무제한일\s*\d+GB',          # "무제한일 5GB"
    r'\d+GB\+',                  # "100GB+"
    
    # 초저가 패턴
    r'월\s*[1-9]\d{2,3}원',      # "월 1,100원" (1,000~9,999원)
    r'[1-9]\d{2,3}원',           # "1,100원"
    
    # 프로모션/이벤트 키워드
    r'알뜰폰\s*(프로모션|이벤트|할인|특가)',
    r'유심\s*(할인|특가|이벤트)',
    r'요금제\s*(특가|할인)',
]


# 짧거나 일반 단어와 혼동 가능한 별칭 → 사업자명 매칭돼도 AI 검증 필요
AMBIGUOUS_ALIASES = {
    # 단독 사용 시 오탐 위험 별칭
    "토스", "이야기", "리브", "핀", "고고", "인스",
    "찬스", "슈가", "시월", "세븐", "이지", "쉐이크",
    "RL", "snow", "live", "모나", "더원", "헬로",
    "아이즈", "스노우", "pin", "toss",
}

# MVNO 게시글 가능성 낮은 게시판
NON_MVNO_BOARDS = {'freeboard', 'coupon', 'computer', 'issue', 'ppomppu', 'ppomppu2', 'pmarket', 'pmarket2', 'pmarket3'}

# 비MVNO 게시판에서 오탐되는 짧은 별칭
# 해당 게시판에서는 정확한 사업자명 전체가 있어야만 허용
NON_MVNO_BOARD_STRICT = {"토스", "리브", "live", "이야기", "핀", "toss"}

# 단독으로 쓰이면 오탐이 많은 별칭 → 동반 키워드가 있어야만 MVNO로 인정
# 동반 키워드 없으면 게시판 무관하게 차단
# 통신 관련 동반 키워드 공통 목록
_TELECOM_KW = ["모바일", "알뜰", "유심", "요금", "개통", "심", "알뜰폰", "mvno",
               "lte", "5g", "데이터", "통화", "문자", "번호이동", "유플러스", "skt", "kt",
               "가입", "요금제", "월정액", "평생", "회선", "번이", "신규", "공시",
               "통신사", "통신"]

WEAK_ALIASES = {
    # ── 🔴 높음: 일반 단어와 완전히 겹침 → 동반 키워드 필수 ──
    "토스":     _TELECOM_KW,
    "toss":     _TELECOM_KW,
    "이야기":   _TELECOM_KW,
    "live":     _TELECOM_KW + ["리브", "liiv"],
    "리브":     _TELECOM_KW + ["엠", "liiv"],
    "헬로":     _TELECOM_KW,

    # ── 🟡 중간: 혼동 가능, 동반 키워드 권장 ──
    "핀":       ["다이렉트"] + _TELECOM_KW,
    "pin":      ["다이렉트"] + _TELECOM_KW,
    "세븐모바일": _TELECOM_KW,          # SK세븐모바일 별칭 (7-Eleven 혼동)
    "마블링":   _TELECOM_KW,            # 마블링(고기) 혼동
    "winners":  _TELECOM_KW,            # 위너스텔 영문 별칭
    "ktm":       ["모바일", "알뜰", "엠모바일", "kt"],  # KTM오토바이 혼동
    "ktm 모바일": _TELECOM_KW,  # "KTM 모바일" 공백 포함 표기
    "kt엠":      _TELECOM_KW,  # "KT엠" 줄임말
    "kg":       ["모바일"] + _TELECOM_KW,     # KG그룹/KG케미칼 등 혼동 방지

    # ── 기존 AMBIGUOUS 별칭들 (단독 안전 확인용) ──
    "고고":     _TELECOM_KW,
    "인스":     _TELECOM_KW,
    "찬스":     _TELECOM_KW,
    "슈가":     _TELECOM_KW,
    "시월":     _TELECOM_KW,
    "이지":     _TELECOM_KW,
    "쉐이크":   _TELECOM_KW,
    "snow":     _TELECOM_KW + ["man"],
    "스노우":   _TELECOM_KW + ["맨"],
    "더원":     _TELECOM_KW,
    # MNO 직영 온라인 - 단독 시 오탐 가능
    "티다":     _TELECOM_KW + ["이렉트", "다이렉트"],  # 티다이렉트/티다 요금제 등
    "너겟":     _TELECOM_KW + ["nugget"],               # 너겟 단독 질문("뭐야") 등 차단
    # [v3.5] "에어"는 SKT에어 별칭 중 "SKT"/"air"를 명시한 형태만 잡혀서
    # "에어 가입", "에어 유심" 처럼 그냥 "에어"라고만 쓰는 실제 글들이 전부 누락됐음
    # (에어컨/에어팟/에어맥스 등과 겹치는 매우 흔한 단어라 동반 키워드 필수로 안전하게 허용)
    "에어":     _TELECOM_KW,
}

# 제목에 이 키워드 중 하나라도 있으면 요금제 관련 글로 판단 → AI 스킵 가능
SAFE_SKIP_KEYWORDS = [
    'GB', 'Mbps', 'mbps', '요금제', '유심', 'USIM', 'usim',
    'eSIM', 'esim', '이심', '알뜰폰', 'MVNO', '특가', '할인',
    '프로모션', '이벤트', '개통', '월정액', '데이터',
]

# ══════════════════════════════════════════════════════════════════════════════
# [v2.8] 통신 트렌드/이슈 키워드
# 뽐뿌/디씨갤러리/유튜브 등에서 MVNO 직접 언급 없이도
# 바이럴/정책 이슈가 될 수 있는 통신 관련 키워드 센싱용
# 사업자명 매칭과는 별도로, 별도 "이슈" 섹션 분류에 사용
# ══════════════════════════════════════════════════════════════════════════════
TREND_ISSUE_KEYWORDS = {
    # 요금제 통합/개편 (26년 6월 SKT/KT/LGU+ 통합요금제 출시 이슈)
    "통합요금제": ["통합요금제", "요금제 통합", "LTE 5G 통합", "5G LTE 통합",
                  "2만원대 요금제", "2만원대 5G", "통신비 절감"],

    # 5G SA (단독모드) - AI팩토리 연계 이슈
    "5G_SA": ["5G SA", "5GSA", "5G 단독모드", "단독모드", "SA 전환",
              "NSA", "비단독모드", "5G 진짜"],

    # 최적요금제 고지 의무화
    "최적요금제": ["최적요금제", "요금제 추천", "요금제 고지", "최적 요금제"],

    # 단통법 (폐지/이슈 - 과거 이슈 포함)
    "단통법": ["단통법", "단말기유통법", "단통법 폐지", "공시지원금", "추가지원금",
              "선택약정", "지원금 상한"],

    # 통신비/정책 일반
    "통신비_정책": ["통신비 인하", "통신비 절감", "가계통신비", "통신 정책",
                  "도매대가", "전파사용료"],

    # 바이럴 가능성 (유튜버/인플루언서 콘텐츠)
    "바이럴": ["요금제 미쳤", "요금제 비교", "알뜰폰 추천", "통신사 비교",
              "휴대폰 요금제 추천", "요금제 꿀팁"],
}

# 평탄화된 전체 트렌드 키워드 리스트 (빠른 매칭용)
_ALL_TREND_KEYWORDS = [kw for kws in TREND_ISSUE_KEYWORDS.values() for kw in kws]


def detect_trend_issues(title, content=''):
    """
    제목/본문에서 트렌드 이슈 키워드를 탐지.
    MVNO 사업자명 매칭과는 독립적으로 동작.

    Returns:
        list[str]: 매칭된 이슈 카테고리 목록 (예: ['통합요금제', '5G_SA'])
                   매칭 없으면 빈 리스트
    """
    text = (title + ' ' + content).lower()
    matched = []
    for category, keywords in TREND_ISSUE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                matched.append(category)
                break
    return matched


def is_trend_issue(title, content=''):
    """트렌드 이슈 키워드가 하나라도 매칭되면 True"""
    return len(detect_trend_issues(title, content)) > 0


def is_safe_confirmed(provider, title):
    """
    AI 스킵 가능한 confirmed 글인지 판단.
    - 짧은 별칭 / AMBIGUOUS_ALIASES → False (AI 검증 필요)
    - 사업자명 + 요금제 키워드 동시 존재 → True (AI 스킵 가능)
    - 사업자명만 단독 → False (AI 검증 필요)
    """
    if not provider:
        return False
    # 짧거나 애매한 별칭이 매칭된 경우
    if provider in AMBIGUOUS_ALIASES or len(provider) <= 3:
        return False
    # 요금제 관련 키워드가 제목에 있는 경우만 스킵
    return any(kw in title for kw in SAFE_SKIP_KEYWORDS)


# ══════════════════════════════════════════════════════════════════════════════
# 함수: 사업자명 정규화
# ══════════════════════════════════════════════════════════════════════════════

def normalize_provider(text, board=None):
    """
    텍스트에서 사업자명 감지 및 정규화
    
    Args:
        text: 검색할 텍스트 (제목 + 본문)
    
    Returns:
        정규화된 사업자명 또는 None
    """
    if not text:
        return None
    
    text_lower = text.lower()

    # SKT에어 관련: "SKT"+"AIR" 또는 "SKT에어" → MVNO이므로 EXCLUDE 체크 전체 스킵
    is_skt_air = ("skt" in text_lower and "air" in text_lower) or "skt에어" in text_lower or "에어바이sk" in text_lower

    # [v3.1] T다이렉트/너겟 선매칭: EXCLUDE 체크 전에 먼저 확인
    # "티다 쿠폰", "sk 기변은 티다가 유리한가요" 등에 "SK"가 포함되면
    # EXCLUDE에서 탈락하는 버그 방지
    TIDA_BLOCKLIST = ["티달력", "티다운", "티다이어트"]
    TDIRECT_ALIASES = ["티다이렉트", "티다", "t다이렉트", "tdirect", "t direct"]
    if not any(bl in text_lower for bl in TIDA_BLOCKLIST):
        if any(a in text_lower for a in TDIRECT_ALIASES):
            return "T다이렉트"
    if any(a in text_lower for a in ["너겟", "nugget"]):
        return "너겟"
    if any(a in text_lower for a in ["sktair", "에어바이sk"]):
        return "SKT에어"

    # [v3.6] KT 요고모바일 선매칭 (EXCLUDE 체크에서 "kt" 때문에 탈락 방지)
    # "요고모바일"은 그 자체로 안전한 복합어라 무조건 인정.
    # bare "요고"는 매우 흔한 일상어("요거"의 방언)라 "kt"와 같이 나올 때만 인정하고,
    # "필요고"(필요+고) 같은 흔한 오탐 부분일치는 별도 차단.
    YOGO_BLOCKLIST = ["필요고"]
    if any(a in text_lower for a in ["요고모바일", "요고 모바일"]):
        return "요고"
    if "kt" in text_lower and "요고" in text_lower \
            and not any(bl in text_lower for bl in YOGO_BLOCKLIST):
        return "요고"

    if not is_skt_air:
        # 제외 사업자 체크 (3대 통신사)
        for excluded in EXCLUDE_PROVIDERS:
            if excluded.lower() in text_lower:
                # 단, "KT엠모바일"처럼 알뜰폰인 경우는 제외하지 않음
                if "엠모바일" not in text_lower and "m모바일" not in text_lower \
                        and "kt엠" not in text_lower and "ktm" not in text_lower:
                    # "SKT망", "KT망" 형태는 망 표시 → MVNO일 수 있으므로 계속
                    if (excluded.lower() + "망") in text_lower:
                        continue
                    # "SKT에어" 같은 MVNO 사업자명은 제외하지 않음
                    if (excluded.lower() + "에어") in text_lower:
                        continue
                    return None
    
    # 정규명 및 별칭 체크
    for canonical, aliases in MVNO_PROVIDER_ALIASES.items():
        # ── 정규명 체크 ──────────────────────────────────────────────
        if canonical.lower() in text_lower:
            # [v2.2 버그수정] NON_MVNO_BOARDS에서 짧은/AMBIGUOUS 정규명도 차단
            if board in NON_MVNO_BOARDS:
                if canonical in AMBIGUOUS_ALIASES or len(canonical) <= 3:
                    pass  # 아래 별칭 루프로 넘어가서 더 엄격하게 처리
                elif canonical in NON_MVNO_BOARD_STRICT:
                    pass  # 동일
                else:
                    return canonical
            else:
                return canonical
            # [v2.4] 정규명이 NON_MVNO_BOARDS에서 차단됐더라도
            # WEAK_ALIASES 동반 키워드 있으면 통과 (freeboard 알뜰폰 후기 등)
            for alias in aliases:
                if alias.lower() in WEAK_ALIASES:
                    required = WEAK_ALIASES[alias.lower()]
                    if any(kw in text_lower for kw in required):
                        return canonical

        # ── 별칭 체크 ────────────────────────────────────────────────
        for alias in aliases:
            # [v2.8] WEAK_ALIASES 등록된 한글 별칭은 \b(단어경계)가
            # 한글-숫자 경계를 인식 못해 매칭 실패하는 문제가 있음
            # (예: "시월110원" → "시월" 뒤 \b 인식 안 됨)
            # 동반 키워드로 안전성을 이미 확보하므로 \b 없이 매칭
            if alias.lower() in WEAK_ALIASES:
                matched = alias.lower() in text_lower
            else:
                matched = bool(re.search(r'\b' + re.escape(alias.lower()) + r'\b', text_lower))
            if matched:
                # [v2.4] WEAK_ALIASES: 동반 키워드 체크 (게시판 무관하게 적용)
                if alias.lower() in WEAK_ALIASES:
                    required = WEAK_ALIASES[alias.lower()]
                    if not any(kw in text_lower for kw in required):
                        continue  # 동반 키워드 없으면 무조건 차단
                    return canonical  # 동반 키워드 있으면 게시판 무관 통과
                # NON_MVNO_BOARDS 게시판 필터 (WEAK_ALIASES 아닌 별칭에만 적용)
                if board in NON_MVNO_BOARDS:
                    # STRICT 목록 별칭: 정확한 정규명 전체가 있어야만 허용
                    if alias in NON_MVNO_BOARD_STRICT:
                        if canonical.lower() not in text_lower:
                            continue
                    # [v2.2 버그수정] AMBIGUOUS 별칭: NON_MVNO_BOARDS에서 전면 차단
                    if alias in AMBIGUOUS_ALIASES:
                        continue
                return canonical

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: 사업자명 화이트리스트 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_provider_whitelist(title, content='', board=None):
    """
    사업자명 기반 1차 필터링
    
    Returns:
        dict 또는 None
        {
            'is_mvno': True,
            'method': 'provider_whitelist',
            'provider': '감지된 사업자명',
            'confidence': 1.0
        }
    """
    full_text = f"{title} {content}"
    detected = normalize_provider(full_text, board=board)
    
    if detected:
        return {
            'is_mvno': True,
            'method': 'provider_whitelist',
            'provider': detected,
            'confidence': 1.0
        }
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: 키워드 패턴 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_keywords(title, content='', board=None):
    """
    키워드 패턴 2차 필터링

    Returns:
        dict 또는 None
        {
            'is_mvno': True,
            'method': 'keyword_pattern',
            'keywords': [매칭된 키워드들],
            'confidence': 0.0~1.0
        }
    """
    full_text = f"{title} {content}"

    matched_keywords = []
    for pattern in MVNO_KEYWORDS:
        if re.search(pattern, full_text, re.IGNORECASE):
            matched_keywords.append(pattern)

    # [v3.0] phone 게시판 한정:
    # "알뜰폰" 또는 "알뜰" 1개만 매칭돼도 통과
    # (알뜰 관련 정리글/비교글 누락 방지 — phone 게시판은 통신 특화이므로 오탐 위험 낮음)
    # [v3.5] \b알뜰\b / \b알뜰폰\b은 Python re에서 한글이 \w로 취급돼서 공백 없이
    # 붙여쓴 복합어("알뜰통신사", "알뜰유심", "알뜰요금제" 등)는 단어경계가 안 생겨
    # 매칭 자체가 실패함. 실제 누락 사례: "알뜰통신사 이동" (phone 게시판, 조회수 375)가
    # matched_keywords에 전혀 안 잡혀서 이 블록까지 오지도 못했음.
    # phone 게시판은 이미 위 주석대로 오탐 위험이 낮다고 판단한 곳이므로, 여기서만
    # "알뜰"이 제목에 부분 포함되는지 추가로 검사 (일반 게시판/2개매칭 로직은 그대로 유지).
    ALDDAL_PATTERNS = {r'\b알뜰폰\b', r'\b알뜰\b'}
    has_alddal = any(kw in ALDDAL_PATTERNS for kw in matched_keywords) or '알뜰' in title
    if board == 'phone' and has_alddal:
        if '알뜰' in title and not any(kw in ALDDAL_PATTERNS for kw in matched_keywords):
            matched_keywords = matched_keywords + ['알뜰(복합어)']
        return {
            'is_mvno': True,
            'method': 'keyword_pattern',
            'keywords': matched_keywords,
            'confidence': 0.6,
        }

    # 일반: 2개 이상 매칭 시 알뜰폰으로 판단
    if len(matched_keywords) >= 2:
        confidence = min(0.9, len(matched_keywords) * 0.3)
        return {
            'is_mvno': True,
            'method': 'keyword_pattern',
            'keywords': matched_keywords,
            'confidence': confidence
        }
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 3: Claude AI 판별 (애매한 케이스)
# ══════════════════════════════════════════════════════════════════════════════

def ai_check(title, content='', detected_provider=None):
    """
    Claude API로 최종 판별 (비용 발생 주의!)
    
    Args:
        title: 게시글 제목
        content: 게시글 본문 (최대 500자)
        detected_provider: 이미 감지된 사업자명 (있다면)
    
    Returns:
        dict
        {
            'is_mvno': True/False,
            'method': 'ai_check',
            'provider': '감지된 사업자명 또는 None',
            'confidence': 0.0~1.0,
            'reason': '판단 이유'
        }
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY 없음 - AI 체크 건너뜀")
        return {
            'is_mvno': False,
            'method': 'ai_check',
            'provider': None,
            'confidence': 0.0,
            'reason': 'API key not found'
        }
    
    client = Anthropic(api_key=api_key)
    
    provider_list = ', '.join(list(MVNO_PROVIDER_ALIASES.keys())[:20])
    
    prompt = f"""다음 게시글이 알뜰폰(MVNO) 관련 내용인지 판단해주세요.

제목: {title}
본문: {content[:500]}
{f'감지된 사업자: {detected_provider}' if detected_provider else ''}

알뜰폰 사업자 예시:
{provider_list} 등

판단 기준:
1. 알뜰폰 사업자가 언급되었는가?
2. 요금제가 알뜰폰 특성을 가지는가? (GB+Mbps, 저렴한 가격 등)
3. "유심", "알뜰폰", "MVNO" 키워드가 있는가?
4. 3대 통신사(SKT, KT, LG U+) 직영 요금제는 제외

JSON만 응답:
{{"is_mvno": true/false, "confidence": 0.0~1.0, "provider": "감지된 사업자명 또는 null", "reason": "판단 이유"}}"""
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text
        # JSON 파싱
        result = json.loads(result_text)
        result['method'] = 'ai_check'
        return result
        
    except Exception as e:
        print(f"⚠️ AI 체크 실패: {e}")
        return {
            'is_mvno': False,
            'method': 'ai_check',
            'provider': None,
            'confidence': 0.0,
            'reason': f'Error: {str(e)}'
        }


# ══════════════════════════════════════════════════════════════════════════════
# 통합 필터링 함수
# ══════════════════════════════════════════════════════════════════════════════

def classify_post(title, content='', use_ai=False, board=None):
    """
    게시글이 MVNO 관련인지 3단계로 판별
    
    Args:
        title: 게시글 제목
        content: 게시글 본문
        use_ai: True면 AI 체크 활성화 (비용 발생)
    
    Returns:
        dict 또는 None
    """
    # Step 1: 사업자명 화이트리스트
    result = check_provider_whitelist(title, content, board=board)
    if result:
        # [v2.7] is_affiliated / network_candidates 추가
        provider = result.get('provider', '')
        result['is_affiliated'] = provider in AFFILIATED_PROVIDERS
        result['is_financial'] = provider in FINANCIAL_PROVIDERS
        result['network_candidates'] = PROVIDER_NETWORKS.get(provider, [])
        return result
    
    # Step 2: 키워드 패턴 ([v3.0] board 전달 — phone 게시판 알뜰 단독 허용)
    result = check_keywords(title, content, board=board)
    if result:
        return result
    
    # Step 3: AI 판별 (옵션)
    if use_ai:
        # AI 체크는 "요금제", "데이터", "GB" 등이 포함된 경우만
        if any(kw in title + content for kw in ['요금제', '데이터', 'GB', '통신', '유심']):
            result = ai_check(title, content)
            if result['is_mvno'] and result['confidence'] > 0.6:
                return result
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
# AI 판단 + 요약 + 중요도 점수
# ══════════════════════════════════════════════════════════════════════════════

def ai_analyze_and_summarize(title, content, views=0, comments=0):
    """
    Gemini API로 MVNO 판별 + 요약 + 중요도 점수
    
    Args:
        title: 게시글 제목
        content: 게시글 본문 (최대 1000자)
        views: 조회수
        comments: 댓글 수
    
    Returns:
        dict
        {
            'is_mvno': True/False,
            'provider': '감지된 사업자명',
            'relevance_score': 0-10,  # 중요도 점수
            'summary': '한 줄 요약',
            'key_points': ['핵심1', '핵심2'],
            'confidence': 0.0~1.0
        }
    """
    if not GEMINI_AVAILABLE:
        return None
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("⚠️ GEMINI_API_KEY 또는 GOOGLE_API_KEY 없음")
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""다음 뽐뿌 게시글을 분석해주세요.

제목: {title}
본문: {content[:1500]}
조회수: {views}
댓글: {comments}

**분석 기준:**

1. **MVNO 관련 여부 판단**
   - 알뜰폰 사업자 언급? (스마텔, 헬로모바일, SK7모바일, 유모바일, 토스모바일 등)
   - MVNO 특유의 요금제? (GB+Mbps, 저가 요금제)
   - 유심, 알뜰폰, MVNO 키워드?
   - ❌ 제외: 3대 통신사(SKT, KT, LG U+) 직영, 에어콘/가전제품

2. **중요도 점수 (0-10점)**
   - 조회수, 댓글 수 고려
   - 실질적 정보 가치 (프로모션, 정책 변경, 가격 정보)
   - 역대가/최저가/신규출시 등 시장 영향력 높은 경우 8점 이상

3. **통신망 판단**
   - 본문/URL에서 SKT/KT/LGU+ 망 파악
   - 단서: "SK망", "KT망", "U+망", sktmvno.com, uplusmvno.com, ktmvno.com
   - 명확하지 않으면 null

4. **한 줄 요약**
   - 30자 이내로 핵심만 (content_summary 필드)

5. **핵심 포인트**
   - 주요 키워드 2-3개

**JSON만 응답:**
{{
  "is_mvno": true/false,
  "provider": "사업자명 or null",
  "network": "SKT/KT/LGU+ 중 하나 or null",
  "relevance_score": 0-10,
  "content_summary": "한 줄 요약",
  "key_points": ["키워드1", "키워드2"],
  "confidence": 0.0-1.0
}}"""
        
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # JSON 파싱 (```json 제거)
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(result_text)
        result['method'] = 'ai_analyze_gemini'
        return result
        
    except Exception as e:
        print(f"⚠️ Gemini AI 분석 실패: {e}")
        return None


def ai_vision_analyze(title, content, image_urls, current_result=None):
    """
    Gemini Vision으로 이미지까지 분석 (별3개 게시글 전용)
    
    Args:
        title: 게시글 제목
        content: 게시글 본문 텍스트
        image_urls: 본문 이미지 URL 목록 (최대 3장)
        current_result: 기존 AI 분석 결과 (업데이트용)
    
    Returns:
        dict {
            'network': 'SKT/KT/LGU+ or null',
            'price': 요금 (int),
            'data_desc': '데이터 설명',
            'contract_months': 약정개월,
            'vision_summary': '이미지 기반 요약',
            'vision_analyzed': True
        }
    """
    if not GEMINI_AVAILABLE or not image_urls:
        return None
    
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        return None
    
    try:
        import requests as req
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 이미지 최대 3장만 분석 (비용 절감)
        target_images = image_urls[:3]
        
        # 이미지 다운로드
        parts = []
        for url in target_images:
            try:
                r = req.get(url, timeout=10)
                if r.status_code == 200:
                    import base64
                    img_data = base64.b64encode(r.content).decode('utf-8')
                    # MIME 타입 판단
                    mime = 'image/jpeg'
                    if url.lower().endswith('.png'):
                        mime = 'image/png'
                    elif url.lower().endswith('.gif'):
                        mime = 'image/gif'
                    elif url.lower().endswith('.webp'):
                        mime = 'image/webp'
                    parts.append({'inline_data': {'mime_type': mime, 'data': img_data}})
            except Exception as e:
                print(f"      ⚠️ 이미지 다운로드 실패: {url[:50]} - {e}")
                continue
        
        if not parts:
            print("      ⚠️ Vision: 다운로드된 이미지 없음")
            return None
        
        # 텍스트 프롬프트 추가
        parts.append({'text': f"""다음 알뜰폰(MVNO) 게시글의 이미지를 분석해주세요.

게시글 제목: {title}
게시글 본문: {content[:500]}

이미지에서 다음 정보를 찾아주세요:
1. **통신망**: SKT망/KT망/LGU+망 중 어느 것인지
   - 단서: 로고, URL(uplusmvno.com=LGU+, sktmvno.com=SKT, ktmvno.com=KT), 망 표기
2. **요금**: 월 납부 금액 (숫자만)
3. **데이터**: 데이터 용량 + 속도 (예: 125GB + 5Mbps)
4. **약정**: 약정 개월 수 (없으면 0)
5. **핵심 정보**: 이미지에서 파악한 중요 내용 한 줄

JSON만 응답:
{{
  "network": "SKT/KT/LGU+ 중 하나 or null",
  "price": 요금숫자 or null,
  "data_desc": "데이터 설명 or null",
  "contract_months": 약정개월수 or 0,
  "vision_summary": "이미지 기반 핵심 정보 한 줄",
  "vision_analyzed": true
}}"""})
        
        response = model.generate_content(parts)
        result_text = response.text.strip()
        
        # JSON 파싱
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(result_text)
        result['vision_analyzed'] = True
        print(f"      🔭 Vision 분석 완료: 망={result.get('network')}, 요금={result.get('price')}, 데이터={result.get('data_desc')}")
        return result
        
    except Exception as e:
        print(f"      ⚠️ Vision 분석 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 테스트 코드
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # 테스트 케이스
    test_cases = [
        ("스마텔 100GB 1,100원 개꿀!", ""),
        ("[스마텔] (4개월 단기할인) sk망100GB+5mbps 무제한 알뜰폰 요금제 (1,100원)", ""),
        ("헬로모바일 유심 할인 이벤트", ""),
        ("SK7모바일 200GB 요금제", "세븐모바일에서 출시한 신규 요금제입니다"),
        ("air 에어 100GB 특가", ""),
        ("갤럭시 S24 출시", "삼성 신제품"),  # False
    ]
    
    print("=" * 80)
    print("🧪 MVNO 분류기 테스트")
    print("=" * 80)
    
    for title, content in test_cases:
        print(f"\n제목: {title}")
        result = classify_post(title, content, use_ai=False)
        if result:
            print(f"✅ MVNO: {result['provider']} ({result['method']}, {result['confidence']:.2f})")
        else:
            print("❌ MVNO 아님")

# ══════════════════════════════════════════════════════════════════════════════
# 3대 통신사 고조회수 글 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_mno_high_traffic(title, content='', views=0):
    """
    3대 통신사 고조회수 게시글 체크
    - 조회수 5,000 이상 + 통신사/단말 키워드 포함 시 해당
    - MVNO가 아닌 통신사 핫글로 별도 분류
    - 골드번호/선호번호 등 통신사 이벤트는 조회수 500 이상이면 수집

    Returns:
        dict 또는 None
    """
    # [v2.6] 통신사 직접 이벤트 키워드 → 조회수 무관 수집
    MNO_EVENT_KEYWORDS = ['골드번호', '선호번호', '번호세탁', '공식인증대리점', 'T다이렉트샵']
    if any(kw in title for kw in MNO_EVENT_KEYWORDS):
        return {
            'is_mvno': False,
            'is_mno_high_traffic': True,
            'method': 'mno_event_keyword',
            'confidence': 0.9
        }

    if views < 5000:
        return None

    full_text = f"{title} {content}"

    # 0단계: MVNO 사업자명이 있으면 통신사 핫글 제외!
    # SKT AIR/SKT에어는 별도 체크 (제목에 [SKT]만 있어도 AIR 있으면 MVNO)
    if "air" in title.lower() and "skt" in title.lower():
        return None
    if "skt에어" in title.lower() or "에어바이sk" in title.lower():
        return None

    MVNO_PROVIDERS = [
        # 3사 공통
        '헬로모바일', '토스모바일', '아이즈모바일', '모빙', '스마텔',
        '이야기모바일', '에이모바일', 'A모바일', '티플러스', '프리티',
        '핀다이렉트', '리브엠', '리브모바일', '스노우맨', '한패스모바일',
        # 2사 공통
        '조이텔', '고고모바일', '안심모바일', '밸류컴', '에르엘',
        '에이프러스', '여유모바일', '인스모바일', '지엠이모바일',
        '친구모바일', '플래시모바일',
        # SKT 단독
        'SK세븐모바일', 'SK7모바일', '알비레오모바일', 'SKT에어', '에어바이SK',
        # MNO 직영 온라인
        '너겟', 'T다이렉트', '티다이렉트', '요고모바일',
        # KT 단독
        'KT엠모바일', '이지모바일', '드림모바일', '쉐이크모바일', '스카이라이프',
        '스피츠모바일', '아이플러스유', '엔텔레콤', '오파스모바일',
        '웰알뜰폰', '케이티엠모바일', '퍼스트모바일',
        # LGU+ 단독
        'U+유모바일', '유모바일', '시월모바일', '슈가모바일', '찬스모바일',
        '화인통신', '코나아이', '온국민폰', '이지톡', '위너스텔',
        'KCTV알뜰폰', 'KG모바일', '마블링', '사람과연결', '아정당',
        '우리WON모바일', '에스원안심모바일', '더원모바일', '모나모바일',
    ]
    if any(p in title for p in MVNO_PROVIDERS):
        return None  # MVNO 사업자명 있으면 통신사 핫글 아님!

    # 1단계: 명확한 통신사/단말 키워드 (단독 체크)
    MNO_KEYWORDS_STRICT = [
        'SKT', 'KT', 'LG U+', 'SK텔레콤', 'LG유플러스',
        '아이폰', '5G요금제',
        '갤럭시S', '갤럭시Z', '갤S', '폴드', '플립',
    ]
    for kw in MNO_KEYWORDS_STRICT:
        if kw in full_text:
            return {
                'is_mvno': False,
                'is_mno_high_traffic': True,
                'method': 'mno_high_traffic',
                'confidence': 0.9
            }

    # 2단계: 단말 키워드 + 통신 관련 맥락 함께 있을 때만
    # "삼성전자 부동산/파업" 등 오탐 방지
    DEVICE_KEYWORDS = ['갤럭시', '삼성', '애플']
    TELECOM_CONTEXT = ['개통', '요금제', '통신', '5G', 'LTE', '단말', '출시', '스펙', '폰']
    has_device = any(kw in full_text for kw in DEVICE_KEYWORDS)
    has_context = any(kw in full_text for kw in TELECOM_CONTEXT)
    if has_device and has_context:
        return {
            'is_mvno': False,
            'is_mno_high_traffic': True,
            'method': 'mno_high_traffic',
            'confidence': 0.9
        }

    return None

# ══════════════════════════════════════════════════════════════════════════════
# 제목에서 통신망 룰베이스 추출
# ══════════════════════════════════════════════════════════════════════════════

def extract_network_from_title(title):
    """
    제목에서 통신망을 룰베이스로 즉시 추출 (AI 호출 없음)

    지원 패턴:
      SKT : "SK망", "SKT망" (대소문자 무관)
      KT  : "KT망" (대소문자 무관)
      LGU+: "LGU+망", "U+망", "LG망", "LGU망"

    Returns:
        'SKT' / 'KT' / 'LGU+' / None
    """
    if not title:
        return None

    t  = title          # 원본 (대소문자 구분 패턴)
    tl = title.lower()  # 소문자 (대소문자 무관 패턴)

    # ── LGU+ 먼저 체크 (U+ 포함, SKT/KT보다 앞에 있어야 오매칭 방지) ──
    LGU_PATTERNS = ['lgu+망', 'u+망', 'lg u+망', 'lgu망', 'lg망']
    if any(p in tl for p in LGU_PATTERNS):
        return 'LGU+'

    # ── SKT ──
    SKT_PATTERNS = ['skt망', 'sk망']
    if any(p in tl for p in SKT_PATTERNS):
        return 'SKT'

    # ── KT (SKT 체크 후에 해야 "SKT망"이 KT로 오매칭 안 됨) ──
    KT_PATTERNS = ['kt망']
    if any(p in tl for p in KT_PATTERNS):
        return 'KT'

    return None