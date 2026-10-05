"""
dcinside_job.py
──────────────────────────────────────────────────────────────────────────────
디시인사이드 MVNO 모니터링 Cloud Run Job
- Gemini 3단계 분석: 주제 클러스터링 → 본문 수집 → 심화 분석
- 결과: 주제별 사업자 분포 + top3 주목 글 + 링크

환경변수:
  SCRAPE_SOURCE_TYPE : manual | morning | auto (기본: manual)
  SCRAPE_DAYS        : 수집 기간 (기본: 1)
  SCRAPE_GALLERIES   : 수집 갤러리 comma 구분 (기본: mvno)
  REQUESTER_CHAT_ID  : 텔레그램 수동 요청 방 ID
  TELEGRAM_BOT_TOKEN : 봇 토큰
  TELEGRAM_CHAT_ID   : 로그방 ID
  CHAT_DC_RESULT     : 디시 자동결과방 ID
  GEMINI_API_KEY     : Gemini API 키

[수정 이력]
v2.16 | 2026-09-20 | 사업자 섞인 클러스터 강제 재분리 - gemini_cluster 프롬프트가
                  | "사업자 다르면 반드시 별도 클러스터"를 명시하는데도 실제로는
                  | "시월/조이텔 핫딜"처럼 서로 다른 사업자 36건이 한 클러스터로
                  | 뭉치는 경우가 있어서, Gemini가 이미 집계한 providers 비율대로
                  | Python에서 결정론적으로 재분리(_split_multiprovider_clusters).
                  | count/weight_score도 비중대로 배분, top3 대표글은 제목에 해당
                  | 사업자명이 들어간 것만 재배정
v2.15 | 2026-09-20 | 메시지 포맷/내용 선별 개편 (가독성/TMI 피드백 반영):
                  | (1) 사업자마다 망을 직접 페어링해서 표시 - "시월 · 조이텔/LGU+망"처럼
                  |     여러 사업자에 망 하나를 뭉뚱그리던 걸 "시월모바일(LGU+) ·
                  |     조이텔(SKT)"로. core.mvno_classifier.PROVIDER_NETWORKS 기반,
                  |     Gemini가 축약형으로 줄 때 대비 부분일치 매칭도 지원.
                  | (2) 클러스터당 대표글 1개만 보여주고 나머지는 "+N건"으로 압축 -
                  |     top3 전부 제목+URL 나열하던 게 TMI라는 피드백.
                  | (3) 상위 3개 클러스터만 풀 표시(본문수집+심화분석), 나머지는
                  |     AI 호출 없이 "기타 동향: 주제 (N건)"으로 압축 - 자잘한 글
                  |     과감히 쳐내라는 피드백 + AI 비용 절감 부수효과.
v2.14 | 2026-09-20 | (1) 존재하지 않는 scrapers.mvno_classifier.normalize_provider를
                  | import하려다 매번 조용히 실패 → 모든 디시 게시글의 provider/network가
                  | 항상 빈 값으로 저장되던 버그 수정 (core.mvno_classifier로 경로 수정,
                  | ppomppu_job.py에서 발견한 것과 동일한 버그 패턴).
                  | (2) 제목을 URL 하이퍼링크로 바꾸고 esc() 헬퍼로 HTML 이스케이프 적용
                  | (제목에 &,<,> 있으면 파싱 실패로 메시지가 조용히 씹히던 문제 포함).
                  | (3) send_to()가 텔레그램 응답 상태를 안 보고 있어서 400 등으로
                  | 거부돼도 몰랐던 문제 수정 - 실패 시 로그로 남기도록 함
v2.13 | 2026-05-21 | community_context 빌더 추가
v2.12 | 2026-05-16 | 파급력 최고등급 이모지 변경: 💰★★★ → 💰⭐⭐⭐ (뽐뿌 통일)
                  | - 비용절감용 800토큰 제한이 원인이었음
                  | - 클러스터링만 제한 없이, 나머지는 800 유지
                  | - 잡담 키워드 필터링은 유지
                  | - finish_reason 로깅 추가
v2.8 | 2026-05-04 | max_output_tokens 4000→8192, 클러스터 수 7개 제한, JSON 파싱 강화
v2.7 | 2026-05-04 | JSON 파싱 강화 — 줄바꿈/제어문자 제거, max_output_tokens 4000으로 증가
v2.6 | 2026-05-02 | 핫딜 파급력 이모지 4단계 개편
                  | - weight_score 5000↑ → 💰★★★, 3000↑ → 💰★★☆
                  | - weight_score 1000↑ → 💰★☆☆, 이하 → 💰☆☆☆
v2.5 | 2026-05-02 | Gemini max_output_tokens=800 추가 (출력 토큰 비용 절감)
v2.4 | 2026-04-23 | 포맷 재개편
                  | - 별점 완전 제거 → priority 이모지로만 구분
                  | - priority 1(핫딜/요금제): 💰+별(⭐⭐/⭐/) 파급력 표시
                  |   · weight_score 3000↑ → 💰⭐⭐, 1000↑ → 💰⭐, 이하 → 💰
                  | - 헤더: "이모지 사업자/망 — 이슈명" 형식으로 사업자/망 강조
                  | - 개별 글 별점 제거, 조회수/댓글만 표시
v2.3 | 2026-04-23 | 포맷 개선
                  | - format_cluster: 넘버링 제거, 별점(_dc_star) 추가
                  | - 링크 수: priority 1~2 → top3, priority 3~4 → top1, 잡담 → 완전 생략
                  | - 개별 글에도 별점 표시
                  | - gemini_cluster: 사업자 단위 분리 강화 (에스원/이야기모바일 각각 분리)
                  | - analyze_gallery: 빈 블록(잡담) 필터링
v2.2 | 2026-04-22 | 클러스터 우선순위 개편
                  | - 정렬 기준: 건수 → 가중점수(조회수+댓글×10) 합산으로 변경
                  | - gemini_cluster: 사업자 단위 강제 분리, 5순위 체계, priority 필드 추가
                  | - gemini_deep: 요금제 숫자/조건 명시 강제, 잡담 클러스터 요약 생략
                  | - format_cluster: 우선순위 이모지, 가중점수 표시, 잡담 표시 억제
                  | - analyze_gallery: 잡담(priority=5) 클러스터 맨 뒤 배치, 3건 미만 제외
v2.1 | 2026-04-21 | post_id 생성 로직 개선 (슬래시 포함 시 Firestore 경로 오류 수정)
v2.0 | 2026-03-24 | 💬 분석 사업자명 나열 금지, 이슈 중심으로 수정
v1.9 | 2026-03-20 | 🔥 핫글 이모지 제거, 🔗 링크 이모지 제거 (시인성 개선)
v1.8 | 2026-03-11 | datetime KST 기준으로 수정 (Cloud Run UTC 오프셋 대응)
v1.7 | 2026-03-10 | 심화분석 키워드 & 연결 형식 강화, 부연설명/괄호/조회수 언급 금지
v1.6 | 2026-03-10 | 이모지 10개로 확장, sentiment 필수값 강화, 💬 줄바꿈 제거
v1.5 | 2026-03-10 | Firebase 저장(사업자/망/sentiment 전체글 태깅), 클러스터 sentiment 헤더 표시
v1.4 | 2026-03-10 | 이모지 복구, 3건 미만 클러스터 제외
v1.3 | 2026-03-10 | 조이텔/통신사망 별도 클러스터, 건수 내림차순 정렬, 헤더 변경, * 기호 제거
v1.2 | 2026-03-10 | 심화분석 팩트 중심 1~2줄 축약 (추정성 해석 제거)
v1.1 | 2026-03-10 | 클러스터링 사업자 단위 세분화, 정책/요금제 우선 정렬
v1.0 | 2026-03-10 | 최초 작성 (Gemini 3단계 클러스터링)
──────────────────────────────────────────────────────────────────────────────
"""

import os, sys, json, re, time, html, requests
from datetime import datetime, timedelta
import pytz
KST = pytz.timezone("Asia/Seoul")
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_LOG       = os.getenv('TELEGRAM_CHAT_ID', '')
CHAT_DC        = os.getenv('CHAT_DC_RESULT', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://m.dcinside.com/',
}

GALLERY_CONFIG = {
    'mvno':          {'name': '알뜰폰 갤러리', 'emoji': '📱'},
    'cellularphone': {'name': '휴대폰 갤러리', 'emoji': '📲'},
    'galaxy':        {'name': '갤럭시 갤러리', 'emoji': '🌌'},
}

# 사업자 → 망 매핑 (자회사=단독망, 그 외=3사공통)
PROVIDER_NETWORK = {
    # SKT망 단독
    'SK7모바일': 'SKT', '에어모바일': 'SKT', '스마텔': 'SKT', '텔링크': 'SKT',
    # KT망 단독
    'KT엠모바일': 'KT', 'KT스카이라이프': 'KT', '마블링': 'KT', '알닷': 'KT',
    # LGU+망 단독
    '헬로모바일': 'LGU+', 'U+유모바일': 'LGU+', '이야기모바일': 'LGU+',
    # 3사공통 (명시 안하면 기본값)
}

SENTIMENT_LABEL = {
    '불만': '😡불만',
    '긍정': '👍긍정',
    '문의': '❓문의',
    '중립': '😐중립',
}

def get_network(provider):
    """사업자명으로 망 반환. 없으면 3사공통"""
    return PROVIDER_NETWORK.get(provider, '3사공통')


# ── 텔레그램 ──────────────────────────────────────────────────────────────────
def esc(text) -> str:
    """parse_mode='HTML'로 보내는 메시지에 동적 텍스트(제목/사업자명/요약 등) 끼워넣을 때
    반드시 거쳐야 함. 제목에 &, <, > 있으면 이스케이프 없이는 HTML 파싱 실패로
    메시지 전송이 조용히 실패함."""
    return html.escape(str(text)) if text else ""


def send_to(chat_id, text):
    if not TELEGRAM_TOKEN or not chat_id:
        return
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text,
                  'parse_mode': 'HTML', 'disable_web_page_preview': True},
            timeout=10
        )
        # [v2.14] 응답 상태를 확인 안 해서 HTML 파싱 실패 등으로 텔레그램이
        # 거부해도(400) 조용히 씹히던 문제 - 실패 시 로그로 남김
        if not resp.ok:
            print(f'⚠️ Telegram 전송 실패 ({resp.status_code}): {resp.text[:300]} | text={text[:200]!r}')
    except Exception as e:
        print(f'⚠️ Telegram 전송 실패: {e}')

def send_log(text):
    print(text)
    send_to(CHAT_LOG, text)

def send_result(text):
    send_to(CHAT_LOG, text)
    source_type = os.getenv('SCRAPE_SOURCE_TYPE', 'manual')
    requester   = os.getenv('REQUESTER_CHAT_ID', '')
    if source_type == 'manual':
        if requester and requester != CHAT_LOG:
            send_to(requester, text)
    elif CHAT_DC and CHAT_DC != CHAT_LOG:
        send_to(CHAT_DC, text)

def send_long(text):
    if len(text) <= 3800:
        send_result(text)
        return
    lines = text.split('\n')
    chunk = ''
    for line in lines:
        if len(chunk) + len(line) + 1 > 3800:
            send_result(chunk)
            chunk = line
        else:
            chunk += ('\n' if chunk else '') + line
    if chunk:
        send_result(chunk)


# ── 본문 수집 ─────────────────────────────────────────────────────────────────
def fetch_post_content(url):
    try:
        clean_url = re.sub(r'\?page=\d+', '', url)
        resp = requests.get(clean_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        content_el = (
            soup.select_one('div.write_div') or
            soup.select_one('div.inner_view') or
            soup.select_one('div.s_write')
        )
        if not content_el:
            return ''
        for tag in content_el.select('img, script, style'):
            tag.decompose()
        return content_el.get_text(separator=' ', strip=True)[:500]
    except Exception as e:
        print(f'  ⚠️ 본문 수집 실패 {url}: {e}')
        return ''


# ── Gemini ────────────────────────────────────────────────────────────────────
def call_gemini(prompt, max_output_tokens=None):
    if not GEMINI_API_KEY:
        print('⚠️ GEMINI_API_KEY 없음')
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        config = types.GenerateContentConfig(max_output_tokens=max_output_tokens) if max_output_tokens else None
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        # 응답 잘림 여부 확인
        if resp.candidates:
            reason = resp.candidates[0].finish_reason
            if str(reason) not in ('FinishReason.STOP', 'STOP', '1'):
                print(f'⚠️ Gemini 응답 잘림: finish_reason={reason}')
        return resp.text.strip()
    except Exception as e:
        print(f'⚠️ Gemini 호출 실패: {e}')
        return None


def gemini_cluster(posts):
    """1단계: 제목 전체 → 주제 클러스터링 + 사업자 추출"""

    # ── 잡담 키워드 필터링 (Gemini 호출 전 제거) ──────────────────────────────
    JUNK_KEYWORDS = [
        '점심', '저녁', '아침', '밥', '먹', '날씨', '야구', '축구', '농구',
        '게임', '주식', '코인', '비트코인', '주말', '오늘', '어제', '내일',
        '취업', '알바', '군대', '군필', '자대', '영화', '드라마', '유튜브',
        '사진', '고양이', '강아지', '펫', '결혼', '연애', '썸', '여행',
        '맛집', '카페', '커피', '운동', '헬스', '다이어트',
    ]

    def is_junk(title: str) -> bool:
        t = title.lower()
        return any(kw in t for kw in JUNK_KEYWORDS)

    filtered = [p for p in posts if not is_junk(p.get('title', ''))]
    removed = len(posts) - len(filtered)
    if removed > 0:
        print(f'  🧹 잡담 필터링: {removed}개 제거 → {len(filtered)}개 분석')
    posts_to_use = filtered if len(filtered) >= 10 else posts  # 너무 적으면 원본 사용

    # 조회수+댓글*10 점수 기준 상위 300개만 사용 (토큰 초과 방지)
    scored = sorted(range(len(posts_to_use)), key=lambda i: posts_to_use[i].get('views',0) + posts_to_use[i].get('comments',0)*10, reverse=True)
    sample_idx = scored[:300]
    sample = [posts_to_use[i] for i in sample_idx]
    titles_text = '\n'.join(
        f"{i+1}. [조회{p.get('views',0)}/댓글{p.get('comments',0)}] {p['title']}"
        for i, p in enumerate(sample)
    )
    prompt = f"""다음은 디시인사이드 알뜰폰 갤러리의 최근 게시글 목록입니다.

{titles_text}

**분석 요청:**

1. 글들을 5~7개 클러스터로 분류. 아래 기준을 엄격히 따르세요:

   [분리 규칙]
   - 사업자가 다르면 반드시 별도 클러스터 (에스원과 이야기모바일은 같은 요금제라도 분리)
   - 특정 사업자+요금제 이슈는 사업자 단위로 분리
     예) "조이텔 1780원", "알닷 원칩 이슈", "에스원 9900원", "이야기모바일 9900원" 각각 별도
   - 가격 숫자가 명시된 글은 반드시 별도 클러스터로
   - LGU+ eSIM/유심 교체 이슈처럼 현재 진행 중인 통신사 정책 이슈는 별도 클러스터
   - 잡담/일상/커뮤니티 이슈(알뜰폰과 직접 무관한 것)는 하나의 "기타잡담" 클러스터로 묶기

   [우선순위 체계 - priority 필드에 반드시 기입]
   priority 1: 요금제 핫딜/파격가 (구체적 가격 숫자 포함, 신규출시/단종)
   priority 2: 사업자 장애/서비스 이슈 (접속불가, 개통오류, 정책변경)
   priority 3: 통신사 유심/eSIM 정책 이슈 (현재 이슈 중인 것)
   priority 4: 번호이동/개통/사용법 문의
   priority 5: 잡담/일상/알뜰폰 무관 (기타잡담)

2. 각 클러스터에서 언급된 통신망(SKT/KT/LGU+)과 사업자명 집계

3. 각 클러스터에서 (조회수 + 댓글수×10) 점수 상위 top3 글 번호 추출

4. 클러스터 전체의 (조회수 + 댓글수×10) 합산 점수 계산 → weight_score 필드

**JSON만 응답 (백틱·마크다운·줄바꿈 절대 금지, 모든 문자열은 한 줄로):**
[
  {{
    "topic": "주제명 (20자 이내, 사업자명+핵심이슈 포함)",
    "priority": 1~5,
    "count": 글수,
    "weight_score": 가중점수합산,
    "providers": {{"사업자명": 언급수}},
    "networks": {{"SKT": 수, "KT": 수, "LGU+": 수}},
    "top3_indices": [번호1, 번호2, 번호3],
    "summary": "핵심 이슈 한줄 (30자 이내, 가격/조건 숫자 포함, 줄바꿈 금지)",
    "sentiment": "불만|긍정|문의|중립 중 반드시 하나"
  }}
]"""

    result = call_gemini(prompt)  # 클러스터링은 토큰 제한 없이
    if not result:
        return [], sample_idx, posts_to_use
    try:
        return _parse_json_safe(result), sample_idx, posts_to_use
    except Exception as e:
        print(f'⚠️ 클러스터링 파싱 실패: {e}\n{result[:1000]}')
        return [], sample_idx, posts_to_use


def _parse_json_safe(text: str):
    """JSON 파싱 — 다양한 에러케이스 처리"""
    import re

    # 1. 백틱/마크다운 제거
    clean = text.replace('```json', '').replace('```', '').strip()

    # 2. JSON 배열만 추출 (앞뒤 설명문 제거)
    match = re.search(r'\[.*\]', clean, re.DOTALL)
    if match:
        clean = match.group(0)

    # 3. 줄바꿈/탭을 공백으로 치환 (JSON 구조는 유지)
    clean = clean.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')

    # 4. 연속 공백 정리
    clean = re.sub(r' +', ' ', clean)

    # 5. 후행 쉼표 제거 (JSON 표준 위반)
    clean = re.sub(r',\s*([}\]])', r'\1', clean)

    # 6. 파싱 시도
    return json.loads(clean)


def gemini_deep(topic, posts_with_content, priority=4):
    """3단계: 본문 포함 심화 분석"""
    posts_text = '\n\n'.join(
        f"제목: {p['title']}\n조회:{p.get('views',0)} 댓글:{p.get('comments',0)}\n본문: {p.get('content','(없음)')}"
        for p in posts_with_content
    )

    # 잡담 클러스터는 간략하게
    if priority >= 5:
        return '알뜰폰 무관 잡담/일상 글 모음'

    prompt = f"""디시인사이드 알뜰폰 갤러리 '{topic}' 관련 주요 게시글입니다.

{posts_text}

아래 규칙으로 한 줄 요약:
- 팩트만, 추정/해석 금지
- 요금제 관련이면 반드시 가격/데이터/조건 숫자 포함 (예: 1780원, 5GB, 평생할인)
- 이슈/동향 핵심만 & 로 연결 (3개 이하)
- 사업자명 단독 나열 금지
- 마크다운 기호(**, *, •), 괄호, 조회수 언급 금지
- 예시(요금): 1780원 SKT망 5GB 출시 & 가입 가능 여부 문의 급증
- 예시(이슈): 알닷 원칩 재고 소진 & 개통 오류 접수 & 대안 문의"""

    return call_gemini(prompt) or '분석 실패'


# ── 메시지 포맷 ───────────────────────────────────────────────────────────────
def _hotdeal_star(weight_score):
    """핫딜/요금제 클러스터 파급력 별 (가중점수 합산 기준)"""
    if weight_score >= 5000:   return '💰⭐⭐⭐'
    elif weight_score >= 3000: return '💰★★☆'
    elif weight_score >= 1000: return '💰★☆☆'
    else:                      return '💰☆☆☆'

def _provider_network_tag(provider: str) -> str:
    """[v2.15] 사업자명에 망을 직접 페어링해서 반환 (예: '시월모바일(LGU+)').
    여러 사업자를 '·'로 나열하면서 망은 따로 뭉뚱그려 보여주던 문제 - 어느
    사업자가 어느 망인지 안 보인다는 피드백으로 페어링 방식으로 변경.
    core.mvno_classifier.PROVIDER_NETWORKS(단일망 확정 데이터)를 우선 쓰고,
    없으면 이 파일의 로컬 PROVIDER_NETWORK로 보강."""
    try:
        from core.mvno_classifier import PROVIDER_NETWORKS
        candidates = PROVIDER_NETWORKS.get(provider, [])
        if not candidates and provider:
            # Gemini가 축약형("시월")으로 줄 때가 많아서 부분일치도 시도
            for canonical, nets in PROVIDER_NETWORKS.items():
                if provider in canonical or canonical in provider:
                    candidates = nets
                    break
        if len(candidates) == 1:
            return f"{provider}({candidates[0]})"
    except Exception:
        pass
    net = PROVIDER_NETWORK.get(provider)
    if net and net != '3사공통':
        return f"{provider}({net})"
    return provider


def format_cluster(cluster, top3_posts, deep_analysis, rank, sample_idx=None, all_posts=None):
    topic      = cluster.get('topic', '')
    count      = cluster.get('count', 0)
    providers  = cluster.get('providers', {})
    priority   = cluster.get('priority', 4)
    weight     = cluster.get('weight_score', 0)

    # 잡담 클러스터는 완전 생략
    if priority >= 5:
        return ''

    # priority 1(핫딜/요금제)은 💰+별, 나머지는 기존 이모지
    if priority == 1:
        priority_label = _hotdeal_star(weight)
    else:
        priority_label = {2: '🔥', 3: '📋', 4: '💬'}.get(priority, '💬')

    # [v2.15] 사업자(상위 3개)마다 망을 직접 붙여서 표시 - "시월 · 조이텔/LGU+망"처럼
    # 여러 사업자에 망 하나를 뭉뚱그리지 않고 "시월모바일(LGU+) · 조이텔(SKT)"로 페어링
    sorted_prov = sorted(providers.items(), key=lambda x: x[1], reverse=True)[:3]
    prov_net = ' · '.join(_provider_network_tag(k) for k, v in sorted_prov) if sorted_prov else '미분류'

    sentiment_str = SENTIMENT_LABEL.get(cluster.get('sentiment', ''), '')

    lines = [
        f"{priority_label} {esc(prov_net)} — {esc(topic)} ({count}건) {sentiment_str}",
        f"   💬 {esc(deep_analysis)}",
    ]

    # [v2.15] 대표글 1개만 하이퍼링크로 보여주고 나머지는 "+N건" 압축 - 클러스터당
    # 최대 3개씩 제목+URL을 풀어서 보여주던 게 TMI라는 피드백 반영
    # [v2.18] priority 1~2(핫딜/장애·서비스 이슈)는 중요도가 높으니 링크를
    # 최대 3개까지 보여주고, 나머지(3~4)는 기존대로 대표글 1개만 표시
    link_limit = 3 if priority <= 2 else 1
    if top3_posts:
        for p in top3_posts[:link_limit]:
            lines.append(
                f" [{p.get('views',0):,}조회/댓글{p.get('comments',0)}] "
                f"<a href='{esc(p.get('url',''))}'>{esc(p['title'])}</a>"
            )
        extra = count - min(len(top3_posts), link_limit)
        if extra > 0:
            lines.append(f"    +{extra}건 더")

    return '\n'.join(lines)


def _split_multiprovider_clusters(clusters, sample_idx, posts_to_use):
    """[v2.16] gemini_cluster 프롬프트가 "사업자 다르면 반드시 별도 클러스터"를
    명시하지만 실제로는 잘 안 지켜져서(예: "시월/조이텔 핫딜"처럼 서로 다른
    사업자 36건이 한 클러스터로 뭉침), Gemini가 이미 집계해둔 providers
    딕셔너리를 기준으로 Python에서 사업자별로 강제 재분리.
    비중(providers 카운트 비율)대로 count/weight_score를 나누고, top3 대표글은
    제목에 해당 사업자명이 들어간 것만 재배정.
    [v2.17] top3(최대 3개)에서 못 찾으면 클러스터링에 쓰인 전체 샘플에서
    제목에 사업자명 들어간 글 중 조회수×댓글수 최고인 걸로 대체 - 대표글이
    top3에 없는 사업자는 링크 없이 건수만 나오던 문제 수정."""
    result = []
    for cluster in clusters:
        providers = {k: v for k, v in cluster.get('providers', {}).items() if v > 0}
        if len(providers) <= 1:
            result.append(cluster)
            continue

        total = sum(providers.values())
        top3_idx = cluster.get('top3_indices', [])
        top3_posts = [(i, posts_to_use[sample_idx[i-1]]) for i in top3_idx if 0 <= i-1 < len(sample_idx)]
        base_topic = cluster.get('topic', '')

        for prov, cnt in sorted(providers.items(), key=lambda x: -x[1]):
            matched = [i for i, p in top3_posts if prov in p.get('title', '')]
            if not matched:
                # [v2.17] top3(최대 3개) 안에 그 사업자 제목이 없으면 대표글 없이
                # 건수만 나오던 문제 - 클러스터링에 쓰인 전체 샘플(최대 300개)에서
                # 제목에 사업자명 들어간 글 중 조회수×댓글수 최고인 걸로 대체
                candidates = [
                    (i + 1, posts_to_use[sample_idx[i]])
                    for i in range(len(sample_idx))
                    if prov in posts_to_use[sample_idx[i]].get('title', '')
                ]
                if candidates:
                    best_idx, _ = max(
                        candidates,
                        key=lambda ip: ip[1].get('views', 0) * (ip[1].get('comments', 0) + 1)
                    )
                    matched = [best_idx]
            sub = dict(cluster)
            sub['topic'] = f"{prov} {base_topic}"[:24]
            sub['count'] = max(1, round(cluster.get('count', 0) * cnt / total)) if total else cnt
            sub['weight_score'] = round(cluster.get('weight_score', 0) * cnt / total) if total else 0
            sub['providers'] = {prov: cnt}
            sub['top3_indices'] = matched
            result.append(sub)
    return result


# ── 메인 분석 파이프라인 ──────────────────────────────────────────────────────
def analyze_gallery(gallery_key, posts, days):
    cfg = GALLERY_CONFIG[gallery_key]
    now = datetime.now(KST).replace(tzinfo=None)
    start = now - timedelta(days=days)
    range_label = f"{start.strftime('%-m/%-d %H시')}~{now.strftime('%-m/%-d %H시')}"

    send_log(f"🤖 [{cfg['name']}] 1단계: 주제 클러스터링 ({len(posts)}개)...")
    clusters, sample_idx, posts_to_use = gemini_cluster(posts)
    if not clusters:
        send_result(f"{cfg['emoji']} {cfg['name']}\n{range_label}\n\n클러스터링 실패")
        return

    # [v2.16] 사업자 섞인 클러스터 강제 재분리 (Gemini가 "사업자 다르면 분리"
    # 규칙을 완벽히 지키지 않는 경우 대비)
    before_split = len(clusters)
    clusters = _split_multiprovider_clusters(clusters, sample_idx, posts_to_use)
    if len(clusters) > before_split:
        send_log(f"  🔀 사업자별 재분리: {before_split}개 → {len(clusters)}개")

    # 정렬: priority 오름차순 → weight_score 내림차순 (잡담은 맨 뒤)
    clusters = sorted(clusters, key=lambda c: (c.get('priority', 4), -c.get('weight_score', 0)))

    # [v2.15] 3건 미만/잡담(priority 5) 클러스터 제외 후, 상위 FULL_DISPLAY_LIMIT개만
    # 풀 표시(본문수집+심화분석) 대상으로 좁힘 - "자잘한 글은 과감히 버려라"는
    # 피드백 반영. 나머지는 AI 호출 없이 주제+건수만 압축 표시 (AI 비용도 절감)
    # [v2.17] priority 1~2(요금제 핫딜/장애·서비스 이슈)는 count<3이어도 노출 -
    # 조회수/댓글이 아무리 높아도 단독 이슈글이 "건수 3개 미만"이라는 이유만으로
    # 통째로 묻히던 문제 수정 (예: 단독 요금제 불만글이 댓글 다수 달려도 씹힘)
    clusters = [c for c in clusters
                if c.get('priority', 4) < 5
                and (c.get('count', 0) >= 3 or c.get('priority', 4) <= 2)]
    FULL_DISPLAY_LIMIT = 3
    full_clusters = clusters[:FULL_DISPLAY_LIMIT]
    compact_clusters = clusters[FULL_DISPLAY_LIMIT:]

    send_log(f"  클러스터 {len(clusters)}개(풀표시 {len(full_clusters)}) | 2단계: 본문 수집...")
    for cluster in full_clusters:
        for idx in cluster.get('top3_indices', []):
            real_idx = idx - 1
            if 0 <= real_idx < len(sample_idx):
                p = posts_to_use[sample_idx[real_idx]]
                if not p.get('content'):
                    p['content'] = fetch_post_content(p['url'])
                    time.sleep(0.3)

    send_log(f"  3단계: 심화 분석...")
    cluster_blocks = []
    for i, cluster in enumerate(full_clusters):
        top3_posts = [posts_to_use[sample_idx[idx-1]] for idx in cluster.get('top3_indices', [])
                      if 0 <= idx-1 < len(sample_idx)]
        priority = cluster.get('priority', 4)
        deep = gemini_deep(cluster['topic'], top3_posts, priority) if top3_posts else cluster.get('summary', '')
        deep = re.sub(r' +', ' ', deep.replace('\n', ' ').replace('*', '').replace('•', '')).strip()
        block = format_cluster(cluster, top3_posts, deep, i + 1, sample_idx, posts_to_use)
        if block:
            cluster_blocks.append(block)

    header = f"{cfg['emoji']} 디씨 {cfg['name']} 트렌드 ({len(posts)}개 글 분석)\n{range_label}"
    sep = '\n' + '─' * 30 + '\n'
    full_msg = header + sep + ('\n\n' + '─'*30 + '\n\n').join(cluster_blocks)

    if compact_clusters:
        compact_lines = [f" · {esc(c.get('topic',''))} ({c.get('count',0)}건)" for c in compact_clusters]
        full_msg += f"\n\n{'─'*30}\n📌 기타 동향\n" + '\n'.join(compact_lines)

    send_long(full_msg)

    # Firebase 저장
    save_posts_to_firebase(gallery_key, posts, clusters)
    return clusters, len(posts)  # community_context용



# ── Firebase 저장 ─────────────────────────────────────────────────────────────
def save_posts_to_firebase(gallery_key, posts, clusters):
    """글별 사업자/망/sentiment 태깅 후 Firebase 저장"""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core.firebase_handler import FirebaseHandler
        fb = FirebaseHandler()
        if not fb.db:
            print('⚠️ Firebase 미연결 - 저장 생략')
            return
    except Exception as e:
        print(f'⚠️ Firebase 초기화 실패: {e}')
        return

    # 클러스터 인덱스 → sentiment/topic 매핑 (전체 글 대상)
    idx_to_sentiment = {}
    idx_to_topic = {}
    for cluster in clusters:
        sentiment = cluster.get('sentiment', '중립')
        topic = cluster.get('topic', '')
        # top3뿐 아니라 클러스터 전체 글에 매핑하기 위해
        # Gemini가 반환한 top3_indices 외 전체는 providers 집계로 추정 불가
        # → 제목 기반 normalize_provider로 직접 태깅
        for idx in cluster.get('top3_indices', []):
            real_idx = idx - 1
            idx_to_sentiment[real_idx] = sentiment
            idx_to_topic[real_idx] = topic

    try:
        from core.mvno_classifier import normalize_provider
        use_classifier = True
    except Exception:
        use_classifier = False

    saved, skipped = 0, 0
    for i, post in enumerate(posts):
        try:
            # post_id 생성: scraper의 'dc_{gal_id}_{num}' 형태 우선
            # fallback: URL에서 숫자 ID 추출
            raw_id = post.get('post_id', '')
            if not raw_id:
                url = post.get('url', '')
                nums = re.findall(r'/(\d+)(?:\?|$)', url)
                raw_id = f"dc_{gallery_key}_{nums[-1]}" if nums else f"dc_{gallery_key}_{abs(hash(url))}"
            post_id = str(raw_id).replace('/', '_').replace(' ', '_').strip('_')
            # 제목으로 사업자 직접 태깅 (전체 글)
            if use_classifier:
                provider = normalize_provider(post.get('title', '')) or ''
            else:
                provider = post.get('provider', '')
            network = get_network(provider) if provider else ''
            sentiment = idx_to_sentiment.get(i, '중립')
            topic = idx_to_topic.get(i, '')

            result = fb.save_dcinside_post({
                'post_id':   str(post_id),
                'gallery':   gallery_key,
                'title':     post.get('title', ''),
                'url':       post.get('url', ''),
                'views':     post.get('views', 0),
                'comments':  post.get('comments', 0),
                'posted_at': post.get('posted_at'),
                'provider':  provider,
                'network':   network,
                'sentiment': sentiment,
                'topic':     topic,
            })
            if result:
                saved += 1
            else:
                skipped += 1
        except Exception as e:
            print(f'  ⚠️ 저장 실패 {post.get("title","")[:20]}: {e}')

    print(f'  💾 Firebase 저장: 신규 {saved}건 / 업데이트 {skipped}건')


def save_community_context_dc(clusters, all_posts_count, source_type, date_str=None):
    try:
        from google.cloud import firestore as _fs
        import firebase_admin
        from firebase_admin import credentials as _cred
        from datetime import datetime, timezone, timedelta
        _KST = timezone(timedelta(hours=9))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(_cred.ApplicationDefault())
        _db = _fs.Client(project="mvno-484509", database="mvno-data")
        _now = datetime.now(_KST)
        date_str = date_str or _now.strftime("%Y-%m-%d")
        hour_key = _now.strftime("%H")   # 실행 시간 (08/17 등)
        checked  = _now.strftime("%m/%d %H:%M")
        SEP = chr(9473) * 28
        valid = sorted(
            [c for c in clusters if c.get("priority", 4) < 5],
            key=lambda c: (c.get("priority", 4), -c.get("weight_score", 0))
        )
        top3 = valid[:3]
        hotdeal   = [c for c in valid if c.get("priority") == 1]
        hot_issue = [c for c in valid if c.get("priority") == 2]
        alerts, normals = [], []
        if hotdeal:
            topics = " / ".join(c.get("topic","")[:20] for c in hotdeal[:2])
            alerts.append("핫딜/요금제 클러스터 " + str(len(hotdeal)) + "개 -- " + topics)
        if hot_issue:
            topics = " / ".join(c.get("topic","")[:20] for c in hot_issue[:2])
            alerts.append("핫이슈 클러스터 " + str(len(hot_issue)) + "개 -- " + topics)
        if not hotdeal and not hot_issue:
            normals.append("핫딜/핫이슈 클러스터 없음 -- 평이한 동향")
        normals.append("전체 글 " + str(all_posts_count) + "개 분석 / 유효 클러스터 " + str(len(valid)) + "개")
        prov_count = {}
        for c in valid:
            for pv, cnt in (c.get("providers") or {}).items():
                prov_count[pv] = prov_count.get(pv, 0) + cnt
        L = []
        L.append("[MVNO 커뮤니티 AI컨텍스트 | " + date_str + " | " + checked + " 디씨인사이드 기준]")
        L.append("※ 커뮤니티 반응 데이터. 재계산 금지. 해석만 할 것.")
        L.append("")
        L.append(SEP)
        L.append("■ SUMMARY (AI 해석 우선순위)")
        L.append(SEP)
        for a in alerts:  L.append("  ALERT: " + a)
        for n in normals: L.append("  NORMAL: " + n)
        L.append("※ 상세 내용은 하단 각 섹션 참조")
        L.append("")
        L.append(SEP)
        L.append("■ 1. 주요 클러스터 Top 3 [디씨인사이드]")
        L.append(SEP)
        if top3:
            for i, c in enumerate(top3, 1):
                priority = c.get("priority", 4)
                weight   = c.get("weight_score", 0)
                topic    = c.get("topic", "")
                count    = c.get("count", 0)
                sentiment= c.get("sentiment", "")
                impact = {2:"핫이슈", 3:"일반이슈", 4:"정보공유"}.get(priority, "기타")
                if priority == 1:
                    if weight >= 5000:   impact = "파급력:최상"
                    elif weight >= 3000: impact = "파급력:상"
                    elif weight >= 1000: impact = "파급력:중"
                    else:                impact = "파급력:하"
                prov_top = sorted((c.get("providers") or {}).items(), key=lambda x: -x[1])[:3]
                prov_str = " · ".join(k for k,v in prov_top) if prov_top else "미분류"
                L.append("[" + str(i) + "] " + impact + " | " + sentiment + " | " + str(count) + "건")
                L.append("  주제: " + topic)
                L.append("  사업자: " + prov_str)
                if i < len(top3): L.append("")
        else:
            L.append("유효 클러스터 없음")
        L.append("")
        L.append(SEP)
        L.append("■ 2. 사업자별 언급 현황")
        L.append(SEP)
        if prov_count:
            for pv, cnt in sorted(prov_count.items(), key=lambda x: -x[1])[:10]:
                L.append("  " + pv + ": " + str(cnt) + "건")
        else:
            L.append("  사업자 집계 없음")
        L.append("")
        L.append(SEP)
        L.append("■ 3. 수집 현황")
        L.append(SEP)
        L.append("전체: " + str(all_posts_count) + "개 / 유효 클러스터: " + str(len(valid)) + "개")
        L.append("핫딜/요금제: " + str(len(hotdeal)) + "개 / 핫이슈: " + str(len(hot_issue)) + "개")
        new_text = chr(10).join(L)
        doc_ref  = _db.collection("community_context").document(date_str)
        existing = doc_ref.get()
        ex_dict  = existing.to_dict() if existing.exists else {}

        # 시간대별 merge: text_dcinside_08 / text_dcinside_17 / ...
        time_field = "text_dcinside_" + hour_key
        ex_dict[time_field] = new_text
        ex_dict["date"]     = date_str
        ex_dict["saved_at"] = _now
        ex_dict["version"]  = "v1.0"

        # 최종 text = 뽐뿌 합산 + 디씨 전 시간대 합산
        dcinside_keys = sorted([k for k in ex_dict if k.startswith("text_dcinside_")])
        dcinside_parts = [ex_dict[k] for k in dcinside_keys if ex_dict.get(k)]
        dcinside_merged = (chr(10)*2 + "── " + chr(10)*2).join(dcinside_parts)
        if dcinside_merged:
            ex_dict["text_dcinside"] = dcinside_merged

        all_parts = []
        if ex_dict.get("text_ppomppu"): all_parts.append(ex_dict["text_ppomppu"])
        if dcinside_merged: all_parts.append(dcinside_merged)
        ex_dict["text"] = (chr(10)*2 + chr(9473)*28 + chr(10)*2).join(all_parts)

        doc_ref.set(ex_dict)
        print("community_context merge 저장: " + date_str + " / dcinside_" + hour_key + " (" + str(len(new_text)) + "자)")
    except Exception as e:
        print("community_context 저장 실패: " + str(e))
        import traceback as _tb; print(_tb.format_exc()[-300:])


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    source_type      = os.getenv('SCRAPE_SOURCE_TYPE', 'manual')
    days             = float(os.getenv('SCRAPE_DAYS', '1'))
    galleries_env    = os.getenv('SCRAPE_GALLERIES', 'mvno')
    target_galleries = [g.strip() for g in galleries_env.split(',') if g.strip()]

    send_log(f"🦎 디시 분석 시작 [{source_type}] | {', '.join(target_galleries)} | {days}일치")

    from scrapers.dcinside_scraper import scrape_gallery

    all_clusters = []
    total_post_count = 0
    for gallery_key in target_galleries:
        cfg = GALLERY_CONFIG.get(gallery_key, {})
        send_log(f"📥 {cfg.get('name', gallery_key)} 수집 중...")
        try:
            posts = scrape_gallery(gallery_key, days=days)
        except Exception as e:
            send_log(f"⚠️ 수집 실패: {e}")
            continue

        if not posts:
            send_log(f"  수집 글 없음")
            continue

        send_log(f"  {len(posts)}개 수집 → 분석 시작")
        result = analyze_gallery(gallery_key, posts, days)
        if result:
            _clusters, _cnt = result
            all_clusters.extend(_clusters)
            total_post_count += _cnt

    if source_type in ("auto", "morning") and all_clusters:
        save_community_context_dc(all_clusters, total_post_count, source_type)

    send_log(f"✅ 디시 분석 완료")


if __name__ == '__main__':
    main()