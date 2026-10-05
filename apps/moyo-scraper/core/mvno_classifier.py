"""
mvno_classifier.py
──────────────────────────────────────────────────────────────────────────────
MVNO 관련 게시글 필터링
- 사업자명 화이트리스트 (별칭 지원)
- 키워드 패턴 매칭
- Gemini AI 판별 (애매한 케이스)
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
    # 주요 사업자 (별칭 포함)
    "SK7모바일": ["sk7모바일", "sk세븐모바일", "세븐모바일", "SK세븐", "세븐", "sk7"],
    "스마텔": ["smartel", "스마트텔"],
    "헬로모바일": ["헬로", "LG헬로모바일", "LG헬로", "헬로유심"],
    # "에어": ["air", "air by SK telecom", "에어바이SK", "SK에어", "에어바이sk"],  # 에어콘과 혼동 방지
    "KT엠모바일": ["엠모바일", "KTM모바일", "KT M모바일", "ktm"],
    "U+유모바일": ["유모바일", "U+유", "LG유모바일", "유플러스유모바일"],
    "모빙": ["mobing", "moVing"],
    "티플러스": ["T플러스", "tplus", "T+", "티+"],
    "프리티": ["priety", "프리티모바일"],
    "토스모바일": ["토스", "toss모바일", "toss", "토스심"],
    "아이즈모바일": ["아이즈", "eyes모바일", "eyes"],
    "이야기모바일": ["이야기"],
    "스노우맨": ["snowman", "스노우", "snow"],
    "인스모바일": ["인스"],
    "찬스모바일": ["찬스"],
    "고고모바일": ["고고"],
    "에이모바일": ["A모바일"],
    "KG모바일": ["케이지모바일", "KG", "kg모바일"],
    "리브모바일": ["리브", "live모바일", "live"],
    "이지모바일": ["이지"],
    "시월모바일": ["시월"],
    "KT스카이라이프": ["스카이라이프", "skylife"],
    "더원모바일": ["더원", "theone"],
    "쉐이크모바일": ["쉐이크", "shake"],
    "슈가모바일": ["슈가", "sugar"],
    "마블링": ["marbling"],
    "모나": ["mona"],
    "핀다이렉트": ["핀", "pin"],
    "에르엘": ["RL"],
    "위너스텔": ["winners", "위너스"],
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
    r'\b알뜰폰\b', r'\bMVNO\b', r'\bmvno\b',
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
    
    # 제외 사업자 체크 (3대 통신사)
    for excluded in EXCLUDE_PROVIDERS:
        if excluded.lower() in text_lower:
            # 단, "KT엠모바일"처럼 알뜰폰인 경우는 제외하지 않음
            if "엠모바일" not in text_lower and "m모바일" not in text_lower:
                return None
    
    # 정규명 및 별칭 체크
    for canonical, aliases in MVNO_PROVIDER_ALIASES.items():
        # 정규명 체크
        if canonical.lower() in text_lower:
            return canonical
        
        # 별칭 체크
        for alias in aliases:
            # 단어 경계를 고려한 매칭 (부분 매칭 방지)
            if re.search(r'\b' + re.escape(alias.lower()) + r'\b', text_lower):
                return canonical
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: 사업자명 화이트리스트 체크
# ══════════════════════════════════════════════════════════════════════════════

def check_provider_whitelist(title, content=''):
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
    detected = normalize_provider(full_text)
    
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
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""다음 뽐뿌 게시글을 분석해주세요.

제목: {title}
본문: {content[:1000]}
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
   - 핫이슈/이벤트 여부

3. **한 줄 요약**
   - 20자 이내로 핵심만

4. **핵심 포인트**
   - 주요 키워드 2-3개

**JSON만 응답:**
{{
  "is_mvno": true/false,
  "provider": "사업자명 or null",
  "relevance_score": 0-10,
  "summary": "한 줄 요약",
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