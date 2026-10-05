"""
mvno_classifier.py
──────────────────────────────────────────────────────────────────────────────
MVNO 관련 게시글 필터링
- 사업자명 화이트리스트 (별칭 지원)
- 키워드 패턴 매칭
- Gemini AI 판별 (애매한 케이스)

[수정 이력]
v1.0 | 2026-03-01 | 최초 작성
v1.1 | 2026-03-24 | EXCLUDE_PROVIDERS에 비교 플랫폼 추가 (모두의유심, 핀다, 알닷 등)
v1.2 | 2026-06-15 | 트렌드 이슈 키워드 추가 (price-monitor v2.8과 동기화)
      | - TREND_ISSUE_KEYWORDS: 통합요금제/5G SA/최적요금제/단통법 등
      | - detect_trend_issues() 함수 추가 - youtube_monitor.py에서 사용
v1.3 | 2026-09-19 | TREND_ISSUE_KEYWORDS에 "온라인다이렉트" 카테고리 추가
      | (T다이렉트샵/SKT 에어). youtube_monitor.py의 TREND_MONITOR_KEYWORDS에
      | 같은 검색어를 추가했는데, 여기 없으면 검색은 되어도 filter_trend_videos()
      | 단계에서 걸러져 리포트가 안 나감. "에어" 단독은 에어컨 등과 오탐 가능성이
      | 있어 "SKT 에어"/"에어 요금제"처럼 복합어로만 매칭
      | - 헬로모바일 별칭에 "헬로비전"(모회사) 추가
      | - "온라인다이렉트"에 너겟/요고(LGU+·KT 온라인 다이렉트 브랜드) 추가,
      |   "너겟" 단독은 치킨너겟과 오탐 가능해 "너겟 요금제"/"너겟폰"처럼 복합어로만
v1.4 | 2026-09-20 | check_provider_whitelist — 제목만 보도록 축소 (content 무시).
      | 실사례: 화장품 채널이 KB리브엠 쿠폰을 협찬받아 "🚨리브엠 12월 올영세일
      | 프로모션🚨"이라고 설명란에 적은 걸 confidence=1.0으로 자동 통과시켜
      | 통신과 무관한 콘텐츠가 리포트로 나감. 설명란은 협찬/해시태그가 많아
      | 사업자명 단어 하나만으로는 오탐 위험이 큼 — 제목에 있어야 신뢰
──────────────────────────────────────────────────────────────────────────────
"""

import re
import json
import os

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-genai 패키지 없음. pip install google-genai")

# ══════════════════════════════════════════════════════════════════════════════
# 사업자명 별칭 매핑 (정규명: [별칭들...])
# ══════════════════════════════════════════════════════════════════════════════

# 자회사 & 금융 계열 MVNO (3대 통신사 자회사 또는 금융사 운영)
AFFILIATED_MVNO = {
    'SK7모바일',        # SK 자회사
    '텔링크',           # SK 계열
    '헬로모바일',       # LG 자회사
    'U+유모바일',       # LG 자회사
    'KT엠모바일',       # KT 자회사
    'KT스카이라이프',   # KT 자회사
    'KB알뜰폰',         # 금융 (KB리브엠)
    '우리은행 알뜰폰',  # 금융 (우리WON모바일)
}

MVNO_PROVIDER_ALIASES = {
    # 주요 사업자 (오탐 없는 별칭만 유지)
    "SK7모바일": ["sk7모바일", "sk세븐모바일", "세븐모바일", "sk7"],
    "스마텔": ["smartel", "스마트텔"],
    "헬로모바일": ["헬로모바일", "헬로 모바일", "LG헬로모바일", "LG헬로", "헬로유심",
                 "헬로비전"],  # LG헬로비전(모회사, 케이블방송 겸업) — 검색어는 "헬로비전 알뜰폰" 복합어로만 사용
    "알닷": ["알닷", "알닷모바일", "알닷폰"],
    "에어모바일": ["에어모바일", "에어바이SK", "SK에어", "에어바이sk", "air by SK telecom"],
    "KT엠모바일": ["엠모바일", "KTM모바일", "KT M모바일", "KT엠모바일"],
    "U+유모바일": ["유모바일", "U+유모바일", "LG유모바일", "유플러스유모바일"],
    "모빙": ["모빙", "mobing"],
    "티플러스": ["티플러스", "T플러스", "tplus"],
    "프리티": ["프리티", "프리티모바일"],
    "토스모바일": ["토스모바일", "토스심", "토스 모바일", "토스유심"],
    "아이즈모바일": ["아이즈모바일", "eyes모바일"],
    "이야기모바일": ["이야기모바일"],       # "이야기" 단독 제거
    "스노우맨": ["스노우맨", "snowman"],    # "snow", "스노우" 단독 제거
    "인스모바일": ["인스모바일"],            # "인스" 단독 제거 (인스타 오탐)
    "찬스모바일": ["찬스모바일"],            # "찬스" 단독 제거
    "고고모바일": ["고고모바일"],            # "고고" 단독 제거
    "에이모바일": ["에이모바일", "A모바일"],
    "KG모바일": ["케이지모바일", "kg모바일"],  # "KG" 단독 제거
    "리브모바일": ["리브모바일", "live모바일"],  # "리브", "live" 단독 제거
    "이지모바일": ["이지모바일"],            # "이지" 단독 제거
    "시월모바일": ["시월모바일"],            # "시월" 단독 제거
    "조이텔": ["조이텔", "joitel", "조이텔모바일"],
    "우리은행 알뜰폰": ["우리won모바일", "우리원모바일", "우리 won 모바일", "우리won 모바일",
                        "우리 won모바일", "우리WON모바일", "우리알뜰폰"],
    "KB알뜰폰": ["kb리브엠", "kb리브", "리브엠", "kb 리브엠", "kb 리브", "리브 엠",
                 "kblivm", "livm", "kb알뜰폰"],
    "KT스카이라이프": ["스카이라이프", "kt스카이라이프"],
    "더원모바일": ["더원모바일"],            # "더원" 단독 제거
    "쉐이크모바일": ["쉐이크모바일"],        # "쉐이크" 단독 제거
    "슈가모바일": ["슈가모바일"],            # "슈가" 단독 제거
    "마블링": ["마블링모바일"],
    "모나": ["모나모바일"],
    "핀다이렉트": ["핀다이렉트"],           # "핀", "pin" 단독 제거
    "에르엘": ["에르엘모바일"],             # "RL" 단독 제거
    "위너스텔": ["위너스텔", "winners텔"],
}

# 제외할 사업자 (3대 통신사 직영)
EXCLUDE_PROVIDERS = {
    "SKT", "KT", "LG U+", "SK텔레콤", "KT텔레콤", "LG유플러스"
}

# ══════════════════════════════════════════════════════════════════════════════
# 키워드 패턴 (정규표현식)
# ══════════════════════════════════════════════════════════════════════════════

MVNO_KEYWORDS = [
    # 직접 언급
    r'알뜰폰', r'MVNO', r'mvno',
    r'유심', r'USIM', r'usim', 
    r'eSIM', r'esim', r'이심',
    
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


# ══════════════════════════════════════════════════════════════════════════════
# 함수: 사업자명 정규화
# ══════════════════════════════════════════════════════════════════════════════

def normalize_provider(text):
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

    # MVNO 사업자 먼저 체크 (3대 통신사 체크보다 우선)
    for canonical, aliases in MVNO_PROVIDER_ALIASES.items():
        # 정규명 체크
        if canonical.lower() in text_lower:
            return canonical
        # 별칭 체크 (한글은 \b 미지원 → 단순 포함 체크)
        for alias in aliases:
            alias_lower = alias.lower()
            # 영문은 단어경계, 한글은 단순 포함
            if re.search(r'[a-zA-Z]', alias_lower):
                if re.search(r'\b' + re.escape(alias_lower) + r'\b', text_lower):
                    return canonical
            else:
                if alias_lower in text_lower:
                    return canonical

    # 3대 통신사 체크 (MVNO 아닌 경우만)
    for excluded in EXCLUDE_PROVIDERS:
        if excluded.lower() in text_lower:
            return None

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: 사업자명 화이트리스트 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_provider_whitelist(title, content=''):
    """
    사업자명 기반 1차 필터링 — 제목만 본다 (content는 받되 사용하지 않음).
    설명란에는 협찬/쿠폰 스폰서 문구("OOO 세일 프로모션" 등)로 사업자명이 등장하는
    경우가 있는데, 실제로는 통신과 무관한 콘텐츠(예: 화장품 채널이 KB리브엠 쿠폰을
    협찬받아 올린 영상)라 confidence=1.0으로 자동 통과시키기엔 오탐 위험이 큼.
    제목에 사업자명이 있으면 진짜 그 사업자에 대한 콘텐츠일 확률이 훨씬 높음.

    Returns:
        dict 또는 None
        {
            'is_mvno': True,
            'method': 'provider_whitelist',
            'provider': '감지된 사업자명',
            'confidence': 1.0
        }
    """
    detected = normalize_provider(title)
    
    if detected:
        return {
            'is_mvno': True,
            'method': 'provider_whitelist',
            'provider': detected,
            'confidence': 1.0,
            'is_affiliated': detected in AFFILIATED_MVNO,
        }
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: 키워드 패턴 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_keywords(title, content=''):
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
    
    # 2개 이상 매칭 시 알뜰폰으로 판단
    if len(matched_keywords) >= 1:
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

def classify_post(title, content='', use_ai=False):
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
    result = check_provider_whitelist(title, content)
    if result:
        return result
    
    # Step 2: 키워드 패턴
    result = check_keywords(title, content)
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
        client = genai.Client(api_key=api_key)
        
        prompt = f"""다음 뽐뿌 게시글을 분석해주세요.

제목: {title}
본문: {content[:1000]}
조회수: {views}
댓글: {comments}

**분석 기준:**

1. **MVNO 관련 여부 판단 (매우 엄격하게!)**

   ✅ MVNO로 판단:
   - 알뜰폰 사업자 명시: 스마텔, 헬로모바일, SK7모바일, 유모바일, 토스모바일, 알닷 등
   - MVNO 특유 요금제: "GB+Mbps", "저가 요금제", "알뜰폰 요금제"
   - 명확한 키워드: "유심", "알뜰폰", "MVNO", "번호이동"

   ❌ MVNO 아님 (오탐 주의!):
   - "토스" 단독 → 토스뱅크/토스페이 가능성 (토스모바일/토스심 명시 필요)
   - "헬로" 단독 → 일반 단어 가능성 (헬로모바일 명시 필요)
   - 3대 통신사 직영: SKT, KT, LG U+
   - 에어콘, 가전제품, 금융, 부동산 등

2. **중요도 점수 (0-10점) - 아래 기준을 합산해서 판단**

   💰 저렴한 요금제 언급 시 높은 점수 (가장 중요):
   - 월 1,000원 미만 요금제 언급 → +3점
   - 월 1,000~5,000원 요금제 언급 → +2점
   - 월 5,000~10,000원 특가/할인 언급 → +1점
   - "평생할인", "영구할인", "특가", "최저가", "한정" 키워드 → +1점
   - 구체적 가격 수치 포함 (예: 8,000원, 100원) → +1점

   📊 조회수 반영:
   - 조회수 10,000 이상 → +2점
   - 조회수 5,000~9,999 → +1점
   - 조회수 1,000~4,999 → +0점

   💬 댓글 반영:
   - 댓글 20개 이상 → +1점
   - 댓글 10~19개 → +0.5점

   📋 정보 가치:
   - 신규 프로모션/이벤트 공지 → +1점
   - 요금제 정책 변경/단종 소식 → +1점
   - 단순 질문/후기 → +0점

   ※ 합산 후 10점 초과 시 10점으로 cap

3. **제목 요약**
   - 제목을 거의 그대로 유지 (30자 이내)
   - 핵심만 간결하게

4. **본문/댓글 요약**
   - 50-70자 정도로 본문의 핵심 내용 요약
   - 가격 정보, 기간, 혜택 등 구체적 숫자 반드시 포함
   - 댓글의 주요 내용도 포함 (있다면)

**JSON만 응답:**
{{
  "is_mvno": true/false,
  "provider": "사업자명 or null",
  "relevance_score": 0-10,
  "summary": "제목 요약 (30자)",
  "content_summary": "본문/댓글 요약 (50-70자)",
  "key_points": ["키워드1", "키워드2"],
  "confidence": 0.0-1.0
}}"""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
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
# 3대 통신사 글 감지 (조회수 기반 포함용)
# ══════════════════════════════════════════════════════════════════════════════

# 3대 통신사 관련 핵심 키워드 (통신/단말 특화, 일반어 제외)
MNO_KEYWORDS_REQUIRED = [
    # 통신사 직접 언급
    'SKT', 'SK텔레콤', 'LG U+', 'LGU+', 'LG유플러스',
    # 단말/요금 관련 (통신 맥락에서만 쓰이는 것)
    '갤럭시', '아이폰', '아이패드', '픽셀',
    '5G 요금제', 'LTE 요금제', '통신사 요금제',
    '번호이동', '기변', '자급제',
]
# KT는 단독으로 너무 광범위 → "KT 요금제", "KT기변" 등 조합만 허용
MNO_KT_PATTERNS = ['kt기변', 'kt 기변', 'kt요금', 'kt 요금', 'kt번호', 'kt 번호', 'kt개통', 'kt망']

MNO_VIEWS_THRESHOLD = 5000  # 5,000 이상이면 포함

# 명백히 통신 무관한 키워드가 제목에 있으면 제외
MNO_EXCLUDE_KEYWORDS = [
    '에어컨', '에어콘', '냉장고', '세탁기', '청소기', '가전',
    '화장품', '올리브영', '쇼핑몰', '택배',
    '주식', '코인', '부동산', '아파트', '견적',
    '맛집', '카페', '음식', '레시피',
    '영화', '드라마', '유튜브', '인스타',
    '정치', '국회', '선거', '대통령',
]


def check_mno_high_traffic(title, content='', views=0):
    """
    3대 통신사 관련 고조회수 글 감지
    조회수 5,000 이상 + 통신 핵심 키워드 포함 시 포함
    """
    if views < MNO_VIEWS_THRESHOLD:
        return None

    title_lower = title.lower()
    full_text = f"{title} {content}".lower()

    # 명백히 무관한 키워드 있으면 즉시 제외
    for exc in MNO_EXCLUDE_KEYWORDS:
        if exc in title:
            return None

    # 핵심 키워드 하나라도 포함되어야 함
    has_keyword = any(kw.lower() in full_text for kw in MNO_KEYWORDS_REQUIRED)
    has_kt = any(p in title_lower for p in MNO_KT_PATTERNS)

    if not has_keyword and not has_kt:
        return None

    # 3대 통신사 구분
    provider = None
    if any(k.lower() in full_text for k in ['skt', 'sk텔레콤']):
        provider = 'SKT'
    elif has_kt or 'kt' in title_lower:
        provider = 'KT'
    elif any(k.lower() in full_text for k in ['lgu+', 'lg u+', 'lg유플러스']):
        provider = 'LG U+'
    else:
        provider = '통신사'

    return {
        'is_mvno': False,
        'is_mno_high_traffic': True,
        'method': 'mno_high_traffic',
        'provider': provider,
        'confidence': 0.8,
        'views': views,
    }


# ══════════════════════════════════════════════════════════════════════════════
# [v1.2] 통신 트렌드/이슈 키워드 (price-monitor mvno_classifier.py v2.8과 동기화)
# 유튜브 등에서 MVNO 직접 언급 없이도
# 바이럴/정책 이슈가 될 수 있는 통신 관련 키워드 센싱용
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

    # [v1.3] 온라인 다이렉트 채널 (MVNO는 아니지만 가격 경쟁 구도상 비교 대상)
    # "에어"/"너겟" 단독은 에어컨/치킨너겟 등과 오탐 가능성이 있어 복합어로만 매칭
    "온라인다이렉트": ["T다이렉트샵", "티다이렉트샵", "SKT 에어", "에어 요금제",
                    "다이렉트샵", "너겟 요금제", "너겟폰", "요고 요금제", "요고폰"],
}


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