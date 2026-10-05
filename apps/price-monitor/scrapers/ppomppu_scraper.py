"""
ppomppu_scraper.py
──────────────────────────────────────────────────────────────────────────────
뽐뿌 커뮤니티 크롤링 - 2단계 필터링 + AI 분석
- 1단계: 제목으로 빠른 필터링 (1,200개 → 17개)
- 2단계: 후보만 상세 정보 수집 (본문, 정확한 시간, 조회수, 댓글)
- 3단계: AI 분석 (본문 포함, 중요도 점수, 요약)

[수정 이력]
v1.0 | 2026-03-01 | 최초 작성
v1.1 | 2026-03-05 | span.cont 기준 제목 파싱 수정 (img 태그 제거)
v1.2 | 2026-03-08 | 통신사 핫글 AI 2차 검증 추가 (오탐 제거)
v1.3 | 2026-03-09 | confirmed 글도 AI 재검증 추가 (모나 울 등 오탐 방지, confidence>0.8)
v1.4 | 2026-03-09 | send_telegram source_type 기준 분기 수정 (수동 시 자동결과방 발송 차단)
v1.5 | 2026-05-16 | 고조회수 게시글 점수 자동 상향 (10k+→70점, 20k+→80점, 댓글50+→+5점)
                  | if final_summary 블록 밖으로 이동 (AI 실패 시에도 보정 적용)
                  | if-elif 순서 수정 (20k 조건을 10k보다 먼저 체크)
v1.6 | 2026-06-02 | fetch_detail에 이미지URL/링크 수집 추가
                  | 별3개(7점+) 게시글 Gemini Vision 분석 도입
                  | network/price/data_desc/contract_months 자동 추출
v1.7 | 2026-06-02 | post dict에 board 필드 추가 (_scrape_page, _scrape_pop_board)
                  | classify_post 호출 시 board 전달 (오탐 방지 게시판 필터 연동)
v1.8 | 2026-09-20 | 429(Too Many Requests) 뜨면 게시판/글을 통째로 포기하고
                  | 넘어가던 문제 수정 - _get_with_retry() 추가 (Retry-After 헤더
                  | 또는 지수백오프로 최대 4회 재시도). 실제 감사 결과 13개
                  | 게시판 중 9개가 이렇게 통째로 누락되고 있었음.
                  | _scrape_page/_scrape_pop_board/fetch_detail 전부 적용
v3.4 | 2026-07-03 | 탈락 로그 조회수 추가 + 대리점 광고글 차단
      | - 탈락 로그에 조회수 포함 👁N 형태로 출력
      | - MNO_EVENT_KW에서 '공식인증대리점' 제거 (pmarket2 광고 우회 버그)
      | - 대리점 광고 패턴 블랙리스트 추가 (T매장내방, SK번이기변 등)
      | - 게시판별 수집 글 수 집계 로그 추가
v3.0 | 2026-06-10 | filter_mvno_posts 대대적 개선
      | - 제목만 AI 판단 단계 완전 제거 (오탐 근본 원인)
      | - mno_candidates 진입 시 normalize_provider 재확인 (프리티/조이텔 버그)
      | - mno_candidates 기준 강화 (통신 키워드 필수)
      | - 본문에서 망 추출 (별3개 글, 제목에 망 없는 경우)
      | - NON_MVNO_BOARDS 차단 절대화 (AI 우회 불가)
v2.0 | 2026-06-06 | filter_mvno_posts 전면 개선
      | - confirmed_ambiguous/keyword_only AI 단계 전에도 NON_MVNO_BOARDS 필터 추가
      | - AI 분석 호출 전 board 체크로 coupon/freeboard 글 완전 차단
      | - 상세 디버그 로그 추가 (각 단계별 board/경로 추적)
v1.9 | 2026-06-06 | filter_mvno_posts: check_mno_high_traffic 호출 전 NON_MVNO_BOARDS 필터 추가
      | - coupon/freeboard 고조회수 글(토스 쿠폰 등)이 MNO 후보로 진입하는 경로 차단
      | - 원인: classify_post는 board 필터 있었으나 mno_high_traffic 경로에는 없었음
v1.8 | 2026-06-02 | Vision 조건 체크 전 고조회수 보정 먼저 실행
                  | provider_whitelist 확정 글도 고조회수면 Vision 분석 가능
v1.5 | 2026-05-16 | 고조회수 게시글 점수 자동 상향 로직 추가 (10k+ → 70점, 20k+ → 80점, 댓글50+ → +5점)
v1.6 | 2026-05-29 | Gemini 비용 최적화 (AI 호출 횟수 절감)
                  | - is_safe_confirmed() import 추가
                  | - confirmed 글을 confirmed_safe / confirmed_ambiguous 로 분리
                  |   : 사업자명 명확 + 요금제 키워드 있는 글 → AI 1차 정제 스킵
                  |   : 짧은 별칭 / AMBIGUOUS_ALIASES / 키워드 없는 글 → 기존대로 AI 검증
                  | - 기능/오탐방지 로직 변경 없음, AI 호출 횟수만 감소
──────────────────────────────────────────────────────────────────────────────
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import time

BASE_URL = "https://m.ppomppu.co.kr/new/bbs_list.php"
POP_URL = "https://m.ppomppu.co.kr/new/pop_bbs.php"  # 인기/Hot 게시판

# 크롤링할 게시판 목록
BOARDS = [
    # 🔥 핵심 게시판 (MVNO 글 집중)
    "phone",          # 휴대폰 포럼 ⭐⭐⭐
    "phone_consult",  # 핸드폰 상담 ⭐⭐⭐

    # 가격비교
    "pmarket",
    "pmarket2",
    "pmarket3",

    # 이벤트/쿠폰
    "event2",
    "coupon",
    "campaign",

    # 상담
    "card_consult",
    "etc_consult",

    # 기타
    "freeboard",
    "computer",
    "issue",
]

# 인기(Hot) 게시판 - bbs_list.php와 URL 구조 다름, 별도 수집
POP_BOARDS = [
    "ppomppu",   # 뽐뿌 인기
    "ppomppu2",  # 뽐뿌2 인기
    "phone",     # 휴대폰 인기
]


class PpomppuScraper:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        })

    def _get_with_retry(self, url, max_retries=4, base_delay=3):
        """[v1.8] 429(Too Many Requests) 뜨면 그 게시판/글 전체를 포기하고 다음으로
        넘어가던 문제 수정. 예전엔 raise_for_status()가 바로 예외를 던지고,
        호출부에서 그걸 잡아서 게시판 하나를 통째로 스킵했음 - 감사해보니
        13개 게시판 중 9개가 이렇게 통째로 누락되고 있었음.
        429는 Retry-After 헤더(있으면) 또는 지수 백오프로 대기 후 재시도."""
        last_exc = None
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after and retry_after.strip().isdigit():
                        wait = float(retry_after)
                    else:
                        wait = base_delay * (2 ** attempt)
                    print(f"      ⏳ 429 Too Many Requests - {wait:.0f}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                last_exc = e
                wait = base_delay * (2 ** attempt)
                print(f"      ⚠️ 요청 실패({e}) - {wait:.0f}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                time.sleep(wait)
        raise last_exc if last_exc else RuntimeError(f"요청 실패: {url}")

    def scrape(self, days=7, boards=None):
        """뽐뿌 게시판 크롤링 (기간만 체크, 페이지 무제한)"""
        if boards is None:
            boards = BOARDS
        
        print(f"🔍 뽐뿌 스크래핑 시작 (최근 {days}일, 게시판 {len(boards)}개)")
        
        cutoff_date = datetime.now() - timedelta(days=days)
        all_posts = []
        seen_ids = set()
        
        for board_id in boards:
            print(f"\n📋 [{board_id}] 게시판 크롤링 시작")
            
            page = 1
            consecutive_exceeded = 0  # 페이지 전체가 cutoff 초과(너무 오래됨)인 경우

            while True:
                try:
                    posts, all_old, total_on_page = self._scrape_page(board_id, page, cutoff_date, seen_ids)

                    if all_old or (not posts and total_on_page == 0):
                        # cutoff 이전 글만 있거나, 페이지 자체가 비어있으면 종료
                        consecutive_exceeded += 1
                        if consecutive_exceeded >= 2:
                            print(f"🛑 [{board_id}] {page}p: 신규 글 없음 → 종료")
                            break
                    else:
                        consecutive_exceeded = 0

                    if posts:
                        all_posts.extend(posts)
                        msg = f"✅ [{board_id}] {page}p 완료 | 이번 {len(posts)}개 | 누적 {len(all_posts)}개"
                        print(msg)
                        if self.progress_callback:
                            self.progress_callback(msg)

                    page += 1
                    time.sleep(0.2)

                except Exception as e:
                    print(f"⚠️ [{board_id}] {page}p 에러: {e} → 다음 게시판")
                    break  # 에러 시 해당 게시판 종료, 다음 게시판으로
        
        # 인기(Hot) 게시판 별도 수집
        print(f"\n📋 [인기게시판] 수집 시작")
        for board_id in POP_BOARDS:
            try:
                pop_posts = self._scrape_pop_board(board_id, cutoff_date, seen_ids)
                all_posts.extend(pop_posts)
                if pop_posts:
                    print(f"✅ [인기:{board_id}] {len(pop_posts)}개 수집")
            except Exception as e:
                print(f"⚠️ [인기:{board_id}] 에러: {e}")

        print(f"\n🎉 최종 수집: {len(all_posts)}개 (일반 {len(boards)}개 + 인기 {len(POP_BOARDS)}개 게시판)")
        return all_posts
    
    def _scrape_page(self, board_id, page_num, cutoff_date, seen_ids):
        """단일 페이지 크롤링 (기본 정보만)"""
        url = f"{BASE_URL}?id={board_id}&page={page_num}"

        response = self._get_with_retry(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        response.close()  # 응답 즉시 해제
        posts = []
        # 게시판마다 클래스가 다름: phone→noeffect, ppomppu→list_b_01n
        links = soup.select('a[href*="bbs_view.php"]')
        # noeffect 중 공지(id=notice)는 제외
        links = [l for l in links if 'notice' not in l.get('href', '') and any(c in l.get('class', []) for c in ['noeffect', 'list_b_01n', 'list_b_02n', 'list_b_03n'])]
        total_on_page = 0  # cutoff 이전 글 포함 전체 카운트 (seen_ids 제외)
        
        for link in links:
            try:
                href = link.get('href', '')
                match = re.search(r'no=(\d+)', href)
                if not match:
                    continue
                
                post_id = match.group(1)
                if post_id in seen_ids:
                    continue
                total_on_page += 1  # seen 아닌 글만 카운트
                
                # 제목 (<strong> 안의 텍스트만, 이미지와 댓글 수 제외)
                cont_elem = link.select_one('span.cont')
                if cont_elem:
                    for tag in cont_elem.find_all('img'):
                        tag.decompose()
                    title = cont_elem.get_text(strip=True)
                else:
                    strong_elem = link.select_one('strong')
                    if strong_elem:
                        for tag in strong_elem.find_all(['img', 'span']):
                            tag.decompose()
                        title = strong_elem.get_text(strip=True)
                    else:
                        title = ''
                if not title or len(title) > 200:
                    continue
                
                if not title:
                    continue
                
                # 날짜
                time_elem = link.select_one('time')
                if time_elem:
                    time_str = time_elem.get_text(strip=True)
                    posted_at = self._parse_ppomppu_date(time_str)
                else:
                    posted_at = datetime.now()
                
                if posted_at < cutoff_date:
                    continue
                
                # URL
                if href.startswith('/'):
                    full_url = f"https://m.ppomppu.co.kr{href}"
                else:
                    full_url = href
                
                # 조회수 (span.view 안의 숫자)
                views = 0
                view_elem = link.select_one('.view')
                if view_elem:
                    view_text = view_elem.get_text(strip=True)
                    views = self._extract_number(view_text, r'(\d+)')
                
                # 댓글 (span.rp)
                comments = 0
                comment_elem = link.select_one('.rp')
                if comment_elem:
                    comment_text = comment_elem.get_text(strip=True)
                    comments = self._extract_number(comment_text, r'(\d+)')
                
                post = {
                    'post_id': post_id,
                    'title': title,
                    'url': full_url,
                    'board': board_id,   # 게시판 ID (오탐 방지용)
                    'posted_at': posted_at,
                    'scraped_at': datetime.now(),
                    'views': views,
                    'comments': comments,
                    'content': '',
                    'author': '익명'
                }
                
                posts.append(post)
                seen_ids.add(post_id)
                
            except Exception as e:
                continue
        
        soup.decompose()  # BeautifulSoup 트리 메모리 해제
        # all_old: cutoff 이전 글만 있거나 빈 페이지
        all_old = (len(posts) == 0 and total_on_page > 0)
        return posts, all_old, total_on_page
    
    def _scrape_pop_board(self, board_id, cutoff_date, seen_ids):
        """인기(Hot) 게시판 수집 - pop_bbs.php 전용"""
        posts = []
        for page in range(1, 6):  # 인기 게시판은 최대 5페이지
            url = f"{POP_URL}?id={board_id}&bot_type=pop_bbs&page={page}"
            try:
                response = self._get_with_retry(url)
                soup = BeautifulSoup(response.content, 'html.parser')
                response.close()

                links = soup.select('a[href*="bbs_view.php"]')
                page_new = 0

                for link in links:
                    try:
                        href = link.get('href', '')
                        import re as _re
                        match = _re.search(r'no=(\d+)', href)
                        if not match:
                            continue
                        post_id = match.group(1)
                        if post_id in seen_ids:
                            continue

                        # 제목
                        cont_elem = link.select_one('span.cont')
                        if cont_elem:
                            for tag in cont_elem.find_all('img'):
                                tag.decompose()
                            title = cont_elem.get_text(strip=True)
                        else:
                            strong_elem = link.select_one('strong')
                            if strong_elem:
                                for tag in strong_elem.find_all(['img', 'span']):
                                    tag.decompose()
                                title = strong_elem.get_text(strip=True)
                            else:
                                title = ''
                        if not title or len(title) > 200:
                            continue

                        # 날짜
                        time_elem = link.select_one('time')
                        posted_at = self._parse_ppomppu_date(time_elem.get_text(strip=True)) if time_elem else datetime.now()
                        if posted_at < cutoff_date:
                            continue

                        # URL
                        full_url = f"https://m.ppomppu.co.kr{href}" if href.startswith('/') else href

                        # 조회수/댓글
                        views = 0
                        view_elem = link.select_one('.view')
                        if view_elem:
                            views = self._extract_number(view_elem.get_text(strip=True), r'(\d+)')
                        comments = 0
                        comment_elem = link.select_one('.rp')
                        if comment_elem:
                            comments = self._extract_number(comment_elem.get_text(strip=True), r'(\d+)')

                        posts.append({
                            'post_id': post_id,
                            'title': title,
                            'url': full_url,
                            'board': board_id,   # 게시판 ID (오탐 방지용)
                            'posted_at': posted_at,
                            'scraped_at': datetime.now(),
                            'views': views,
                            'comments': comments,
                            'content': '',
                            'author': '익명',
                            'source': f'pop_{board_id}',
                        })
                        seen_ids.add(post_id)
                        page_new += 1
                    except Exception:
                        continue

                soup.decompose()
                if page_new == 0:
                    break  # 새 글 없으면 종료
                time.sleep(0.2)

            except Exception as e:
                print(f"   ⚠️ 인기:{board_id} {page}p 에러: {e}")
                break

        return posts

    def fetch_detail(self, post_url):
        """
        게시글 상세 정보 수집
        - 정확한 시간
        - 본문 텍스트
        - 본문 내 이미지 URL (별3개 Vision 분석용)
        - 본문 내 링크 (망 판단용)
        - 댓글수
        """
        try:
            response = self._get_with_retry(post_url)
            soup = BeautifulSoup(response.content, 'html.parser')
            response.close()  # 응답 즉시 해제

            # 본문
            content_div = soup.select_one('.board_txt') or soup.select_one('.cont')
            content = content_div.get_text(strip=True) if content_div else ''
            
            # 본문 내 이미지 URL 수집 (Vision 분석용, 최대 5장)
            # [버그수정, Claude] 뽐뿌 모바일(m.ppomppu.co.kr)의 실제 첨부 이미지는
            # '//cdn4.ppomppu.co.kr/zboard/...' 형태의 프로토콜 상대경로(schema-relative
            # URL)인데, src.startswith('http') 체크가 이걸 전부 걸러내서 본문에 이미지가
            # 있어도 image_urls가 항상 빈 리스트로 나오던 문제 발견. 그 결과 Vision 분석이
            # (relevance_score/조회수 조건을 만족해도) 사실상 한 번도 실행되지 못했고,
            # 통신망 정보가 이미지에만 있는 글(예: 카카오톡 개통완료 캡처)은 전부
            # "통신망: 미확인"으로 빠졌음(사장님 지적: "게시물 이미지 파싱하면 KT망인게
            # 나옴"). //로 시작하면 https:를 붙여 정상 URL로 정규화 후 판정.
            image_urls = []
            if content_div:
                for img in content_div.select('img')[:5]:
                    src = img.get('src') or img.get('data-src') or ''
                    if src.startswith('//'):
                        src = 'https:' + src
                    if src and src.startswith('http') and not 'icon' in src.lower():
                        image_urls.append(src)
            
            # 본문 내 링크 수집 (망 판단용)
            # uplusmvno.com → LGU+, sktmvno.com → SKT, ktmvno.com → KT
            links_text = ''
            if content_div:
                for a in content_div.select('a[href]'):
                    links_text += ' ' + a.get('href', '')
            
            # 작성자
            author_elem = soup.select_one('.ct')
            author = author_elem.get_text(strip=True) if author_elem else '익명'
            
            # 정확한 시간 (class="hi")
            time_elem = soup.select_one('.hi')
            posted_at = datetime.now()
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                try:
                    # "2026-02-20 10:10" 형식
                    posted_at = datetime.strptime(time_text, '%Y-%m-%d %H:%M')
                except:
                    try:
                        posted_at = datetime.strptime(time_text, '%Y-%m-%d %H:%M:%S')
                    except:
                        pass
            
            # 댓글수 (class="cmt-total")
            comments = 0
            comment_elem = soup.select_one('.cmt-total')
            if comment_elem:
                comment_text = comment_elem.get_text(strip=True)
                comments = self._extract_number(comment_text, r'(\d+)')
            
            result = {
                'content': content + ' ' + links_text,  # 링크 텍스트 포함
                'image_urls': image_urls,               # Vision 분석용
                'author': author,
                'posted_at': posted_at,
                'comments': comments
            }
            soup.decompose()  # BeautifulSoup 트리 메모리 해제
            return result
        except Exception as e:
            print(f"⚠️ 상세 정보 실패: {e}")
            return {
                'content': '',
                'image_urls': [],
                'author': '익명',
                'posted_at': datetime.now(),
                'comments': 0
            }
    
    def _extract_number(self, text, pattern):
        """숫자 추출"""
        match = re.search(pattern, text)
        if match:
            return int(match.group(1).replace(',', ''))
        return 0
    
    def _parse_ppomppu_date(self, time_str):
        """날짜 파싱"""
        if not time_str:
            return datetime.now()
        
        time_str = time_str.strip()
        
        try:
            # HH:MM:SS (당일)
            if ':' in time_str and len(time_str.split(':')) == 3:
                time_part = datetime.strptime(time_str, '%H:%M:%S').time()
                return datetime.combine(datetime.today(), time_part)
            
            # YY-MM-DD
            elif '-' in time_str and len(time_str) <= 8:
                parts = time_str.split('-')
                if len(parts) == 3:
                    year = int(parts[0])
                    if year < 100:
                        year += 2000
                    month = int(parts[1])
                    day = int(parts[2])
                    return datetime(year, month, day)
            
            return datetime.now()
            
        except Exception as e:
            return datetime.now()


# ══════════════════════════════════════════════════════════════════════════════
def extract_network_from_content(content: str) -> str:
    """본문에서 통신망 추출 (제목에 망 표시 없는 경우용)"""
    if not content:
        return None
    text = content.lower()
    # 우선순위: 명시적 망 표기 먼저
    # [버그수정, Claude] "kt15g", "skt5g"처럼 망이름+숫자(데이터량)를 띄어쓰기/기호
    # 없이 붙여 쓰는 뽐뿌 흔한 표기(예: "kt15G 350분 100원 요금제")를 기존 패턴이
    # 못 잡던 문제 - \d+g\b 형태 추가. SKT 패턴을 KT보다 먼저 체크하는 순서는
    # 그대로 유지해야 "skt15g" 안의 "kt15g" 부분 문자열이 KT로 오판되지 않음
    # (SKT 패턴이 먼저 매칭돼 반환되므로 KT 체크까지 못 감).
    patterns = [
        (r'(skt망|sk망|sk텔레콤망|skt\s*lte|skt\s*5g|skt\s*\d+g\b)', 'SKT'),
        (r'(kt망|kt\s*lte|kt\s*5g|kt\s*\d+g\b)', 'KT'),
        (r'(lgu\+망|lgu\+|u\+망|유플러스망|lg유플러스망|u\+\s*\d+g\b|lgu\+\s*\d+g\b)', 'LGU+'),
    ]
    for pattern, network in patterns:
        if re.search(pattern, text):
            return network
    return None


# MVNO 필터링 (2단계 처리)
# ══════════════════════════════════════════════════════════════════════════════

def filter_mvno_posts(posts, use_ai=True, top_n=None, progress_telegram=None):
    """
    MVNO + 통신사 핫글 필터링
    - MVNO: 룰베이스 → AI 정제
    - 3대 통신사: 조회수 5,000 이상이면 포함
    - 조회수 높을수록 상위 노출
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.mvno_classifier import classify_post, ai_analyze_and_summarize, ai_vision_analyze, check_mno_high_traffic, is_safe_confirmed, normalize_provider, extract_network_from_title

    def tg(msg):
        print(msg)
        if progress_telegram:
            try:
                progress_telegram(msg)
            except Exception:
                pass

    # 제목 중복 제거 (같은 제목 반복 광고글 방지)
    seen_titles = set()
    deduped = []
    for post in posts:
        title_key = post['title'][:30]  # 앞 30자 기준 중복 체크
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            deduped.append(post)
    if len(deduped) < len(posts):
        print(f"   중복 제목 제거: {len(posts)}개 → {len(deduped)}개")
    posts = deduped

    # 2단계: 룰베이스 필터링
    # provider_whitelist로 확정된 글 vs 키워드만 매칭된 글 분리
    NON_MVNO_BOARDS = {'freeboard', 'coupon', 'computer', 'issue', 'ppomppu', 'ppomppu2', 'pmarket', 'pmarket2', 'pmarket3'}
    # [v3.4] 게시판별 수집 글 수 집계
    from collections import Counter as _Counter
    board_counts = _Counter(p.get('board', 'unknown') for p in posts)
    print(f"[게시판집계] 총 {len(posts)}개:")
    for _board, _cnt in sorted(board_counts.items(), key=lambda x: -x[1]):
        print(f"  [{_board}]: {_cnt}개")

    confirmed = []    # 사업자명 화이트리스트 확정 → AI 검증 불필요
    keyword_only = [] # 키워드 패턴만 → AI 정제 필요
    mno_high_traffic = []
    mno_candidates = []   # AI 검증 전 MNO 후보

    for post in posts:
        board = post.get('board', '')
        result = classify_post(post['title'], '', use_ai=False, board=board)
        if result:
            # [v3.1] NON_MVNO_BOARDS 차단 (ppomppu는 provider_whitelist만 허용)
            if board in NON_MVNO_BOARDS:
                if board == 'ppomppu' and result.get('method') == 'provider_whitelist':
                    pass  # ppomppu 인기게시판: 사업자명 확정글만 허용
                else:
                    views = post.get('views', 0)
                    print(f"[탈락:게시판차단] [{board}] 👁{views:,} {post['title'][:60]}")
                    continue
            post['filter_result'] = result
            if result.get('method') == 'provider_whitelist':
                confirmed.append(post)   # 사업자명 확정 → AI 스킵
                print(f"   ✅ confirmed: [{board}] {post['title'][:40]} → {result.get('provider')}")
            else:
                keyword_only.append(post) # 키워드만 → AI 정제
                print(f"   🔍 keyword_only: [{board}] {post['title'][:40]}")
            continue
        # 3대 통신사 고조회수 체크 → AI 검증 후 확정
        # [v1.9 버그수정] NON_MVNO_BOARDS 게시판은 고조회수라도 MNO 후보 제외
        # coupon/freeboard 토스 쿠폰 글이 MNO 후보로 진입하는 경로 차단
        # [v3.1] freeboard 예외: 통신사 직접 이벤트 키워드(골드번호 등)는 수집 허용
        # [v3.4] '공식인증대리점' 제거 — pmarket2 대리점 광고글이 우회하던 버그 수정
        # 대리점 광고 패턴은 별도 블랙리스트로 차단
        MNO_EVENT_KW = ['골드번호', '선호번호', '번호세탁']
        DEALER_AD_PATTERNS = ['공식인증대리점', 'T매장 내방', '대리점 내방', '성지 내방',
                              '번이기변/유심', 'SK번이기변', 'KT번이기변', 'LG번이기변']
        is_dealer_ad = any(p in post['title'] for p in DEALER_AD_PATTERNS)
        is_mno_event = any(kw in post['title'] for kw in MNO_EVENT_KW) and not is_dealer_ad
        if post.get('board') in NON_MVNO_BOARDS and not is_mno_event:
            continue
        mno_result = check_mno_high_traffic(post['title'], '', post.get('views', 0))
        if not mno_result:
            views = post.get('views', 0)
            print(f"[탈락:룰베이스] [{board}] 👁{views:,} {post['title'][:60]}")
        if mno_result:
            # [v3.0] mno_candidates 강화: 통신 키워드 필수
            TELECOM_REQUIRED = ['요금제', '유심', '번호이동', '개통', '알뜰', '통신', '데이터', 
                                 'skt', 'kt', 'lgu', '삼성', '갤럭시', '아이폰', '스마트폰']
            title_lower = post['title'].lower()
            if not any(kw in title_lower for kw in TELECOM_REQUIRED):
                views = post.get('views', 0)
                print(f"[탈락:MNO기준미달] [{board}] 👁{views:,} {post['title'][:60]}")
                continue
            # [v3.0] MVNO 사업자 재확인 → confirmed_safe로 전환
            mvno_check = normalize_provider(post['title'], board=post.get('board', ''))
            if mvno_check:
                print(f"   ✅ MNO→MVNO 전환: {post['title'][:40]} → {mvno_check}")
                mno_result['provider'] = mvno_check
                mno_result['method'] = 'provider_whitelist'
                mno_result['is_mno_high_traffic'] = False
                post['filter_result'] = mno_result
                confirmed.append(post)
            else:
                post['filter_result'] = mno_result
                mno_candidates.append(post)

    tg(f"🔎 룰베이스 완료: {len(posts)}개 → MVNO확정 {len(confirmed)}개 + 키워드후보 {len(keyword_only)}개 + 통신사핫글후보 {len(mno_candidates)}개")

    if not confirmed and not keyword_only and not mno_candidates:
        return []

    # 3단계: 스카이라이프 인터넷/TV 제외 (모바일 요금제만)
    INTERNET_EXCLUDE = ['인터넷', 'TV', '셋톱박스', 'IPTV', '와이파이', 'wifi', 'internet']
    confirmed_filtered = []
    for post in confirmed:
        title = post['title']
        # 스카이라이프인데 인터넷/TV 관련이면 제외
        if '스카이라이프' in title and any(kw in title for kw in INTERNET_EXCLUDE):
            continue
        confirmed_filtered.append(post)
    confirmed = confirmed_filtered

    # 4단계: AI 정제 (confirmed 중 애매한 것 + keyword_only)
    # confirmed 중 사업자명 명확 + 요금제 키워드 있는 글은 AI 스킵 (비용 절감 v1.6)
    confirmed_safe = []       # AI 스킵 → 바로 통과
    confirmed_ambiguous = []  # AI 검증 필요 (짧은 별칭, 요금제 키워드 없음 등)
    for post in confirmed:
        provider = post['filter_result'].get('provider', '')
        if is_safe_confirmed(provider, post['title']):
            confirmed_safe.append(post)
        else:
            confirmed_ambiguous.append(post)

    # [v2.0] AI 분석 전 NON_MVNO_BOARDS 최종 차단 (confirmed_ambiguous/keyword_only 경로 차단)
    pre_ai_blocked = 0
    confirmed_ambiguous_filtered = []
    keyword_only_filtered = []
    for post in confirmed_ambiguous:
        if post.get('board') in NON_MVNO_BOARDS:
            print(f"   🚫 AI전 차단(confirmed_ambiguous): [{post.get('board')}] {post['title'][:40]}")
            pre_ai_blocked += 1
        else:
            confirmed_ambiguous_filtered.append(post)
    for post in keyword_only:
        if post.get('board') in NON_MVNO_BOARDS:
            print(f"   🚫 AI전 차단(keyword_only): [{post.get('board')}] {post['title'][:40]}")
            pre_ai_blocked += 1
        else:
            keyword_only_filtered.append(post)
    if pre_ai_blocked:
        tg(f"🚫 AI 전 NON_MVNO_BOARDS 차단: {pre_ai_blocked}개")
    confirmed_ambiguous = confirmed_ambiguous_filtered
    keyword_only = keyword_only_filtered

    # [v3.0] 제목만 AI 판단 단계 완전 제거
    # - 제목만으로 AI 판단 시 board 정보 없어서 오탐 살려내는 문제 근본 해결
    # - confirmed_ambiguous/keyword_only는 본문 수집 후 5단계 본문 AI에서 판단
    candidates = confirmed_safe + confirmed_ambiguous + keyword_only
    tg(f"📋 후보: safe {len(confirmed_safe)}개 + ambiguous {len(confirmed_ambiguous)}개 + keyword {len(keyword_only)}개")

    # MNO 후보 AI 검증 (오탐 제거 - 갤럭시 런닝화 등)
    if use_ai and mno_candidates:
        tg(f"🤖 통신사 핫글 AI 검증 ({len(mno_candidates)}개)...")
        for post in mno_candidates:
            try:
                ai_result = ai_analyze_and_summarize(
                    title=post['title'],
                    content='',
                    views=post.get('views', 0),
                    comments=post.get('comments', 0)
                )
                # AI가 통신 무관이라고 확신하면 제외, 나머지는 포함
                if ai_result and not ai_result.get('is_mvno') and ai_result.get('confidence', 0) > 0.7:
                    continue
                mno_high_traffic.append(post)
            except Exception:
                mno_high_traffic.append(post)  # AI 실패 시 일단 포함
        tg(f"✅ 통신사 핫글 검증: {len(mno_candidates)}개 → {len(mno_high_traffic)}개")
    else:
        mno_high_traffic = mno_candidates

    # MNO 핫글은 맨 뒤에 병합 (MVNO 우선 보장)
    if mno_high_traffic:
        tg(f"📡 통신사 핫글 {len(mno_high_traffic)}개 추가 (MVNO 뒤에 배치)")
        all_posts_merged = candidates + mno_high_traffic
    else:
        all_posts_merged = candidates

    if not all_posts_merged:
        return []

    # 4단계: 상세 페이지 수집 (MVNO + MNO 전체)
    tg(f"📄 상세 정보 수집 ({len(all_posts_merged)}개)")
    scraper = PpomppuScraper()

    for i, post in enumerate(all_posts_merged, 1):
        print(f"   ({i}/{len(all_posts_merged)}) {post['title'][:40]}...")
        try:
            detail = scraper.fetch_detail(post['url'])
            post['content'] = detail['content']
            post['image_urls'] = detail.get('image_urls', [])  # Vision 분석용
            post['author'] = detail['author']
            post['posted_at'] = detail['posted_at']
            post['comments'] = detail['comments']
            time.sleep(0.2)
        except Exception as e:
            print(f"      ⚠️ 에러: {e}")

    # [v3.0] 본문에서 망 추출 (별3개 글 + 제목에 망 없는 경우)
    for post in all_posts_merged:
        fr = post.get('filter_result', {})
        if fr.get('is_mno_high_traffic'):
            continue  # 통신사 핫글은 스킵
        if fr.get('network'):
            continue  # 이미 망 있으면 스킵
        # 별3개(7점+) 또는 조회수 10k+ 글만 본문에서 망 추출
        score = fr.get('relevance_score', 0)
        views = post.get('views', 0)
        if score >= 7 or views >= 10000:
            content_text = post.get('content', '')
            network = extract_network_from_content(content_text)
            if network:
                post['filter_result']['network'] = network
                print(f"   🌐 본문 망 추출: {network} ← {post['title'][:35]}")

    # 5단계: 본문 AI 요약 (MVNO + MNO 전체)
    if use_ai:
        tg(f"🤖 본문 AI 요약 ({len(all_posts_merged)}개)")
        for i, post in enumerate(all_posts_merged, 1):
            if i % 10 == 0:
                print(f"   AI 요약 진행: {i}/{len(all_posts_merged)}개...")
            try:
                final_summary = ai_analyze_and_summarize(
                    title=post['title'],
                    content=post['content'],
                    views=post['views'],
                    comments=post['comments']
                )
                if final_summary:
                    # [v3.0] confirmed_ambiguous/keyword_only는 본문 AI로 최종 판단
                    method = post.get('filter_result', {}).get('method', '')
                    if method != 'provider_whitelist':
                        # 사업자명 확정 아닌 글 → AI가 MVNO 아니면 제거
                        if not final_summary.get('is_mvno') and final_summary.get('confidence', 0) > 0.75:
                            print(f"   🚫 본문AI 오탐 제거: {post['title'][:40]}")
                            post['filter_result']['_remove'] = True
                    post['filter_result'].update(final_summary)
                
                # 고조회수 보정 먼저 실행 (Vision 조건 체크 전!)
                views_pre = post.get('views', 0)
                comments_pre = post.get('comments', 0)
                pre_score = post['filter_result'].get('relevance_score', 5)
                if views_pre >= 20000:
                    post['filter_result']['relevance_score'] = max(pre_score, 80)
                elif views_pre >= 10000:
                    post['filter_result']['relevance_score'] = max(pre_score, 70)
                if comments_pre >= 50:
                    s = post['filter_result'].get('relevance_score', 5)
                    post['filter_result']['relevance_score'] = min(s + 5, 100)

                # 별3개 게시글 Vision 분석 (2026-06-02 추가)
                # relevance_score 7점 이상 + 이미지 있는 경우만
                current_score_check = post['filter_result'].get('relevance_score', 0)
                image_urls = post.get('image_urls', [])
                if current_score_check >= 7 and image_urls:
                    print(f"      🔭 Vision 분석 시작 ({len(image_urls)}장)")
                    vision_result = ai_vision_analyze(
                        title=post['title'],
                        content=post.get('content', ''),
                        image_urls=image_urls
                    )
                    if vision_result:
                        # 망 정보 업데이트 (Vision이 더 정확)
                        if vision_result.get('network'):
                            post['filter_result']['network'] = vision_result['network']
                        # 요금/데이터 업데이트
                        if vision_result.get('price'):
                            post['filter_result']['vision_price'] = vision_result['price']
                        if vision_result.get('data_desc'):
                            post['filter_result']['vision_data'] = vision_result['data_desc']
                        if vision_result.get('contract_months'):
                            post['filter_result']['contract_months'] = vision_result['contract_months']
                        if vision_result.get('vision_summary'):
                            post['filter_result']['vision_summary'] = vision_result['vision_summary']
                        post['filter_result']['vision_analyzed'] = True
                
                # 고조회수 게시글 점수 자동 상향 (2026-05-16 추가)
                # AI 분석 성공 여부와 무관하게 항상 실행
                views = post.get('views', 0)
                comments = post.get('comments', 0)
                current_score = post['filter_result'].get('relevance_score', 5)
                
                # 조회수 20,000 이상 → 최소 80점 보장 (큰 수부터!)
                if views >= 20000:
                    boosted_score = max(current_score, 80)
                    if boosted_score > current_score:
                        post['filter_result']['relevance_score'] = boosted_score
                        post['filter_result']['high_traffic_boost'] = True
                        print(f"      📈 초고조회수 보정: {current_score}점 → {boosted_score}점 (조회 {views:,})")
                        current_score = boosted_score
                
                # 조회수 10,000 이상 → 최소 70점 보장
                elif views >= 10000:
                    boosted_score = max(current_score, 70)
                    if boosted_score > current_score:
                        post['filter_result']['relevance_score'] = boosted_score
                        post['filter_result']['high_traffic_boost'] = True
                        print(f"      📈 고조회수 보정: {current_score}점 → {boosted_score}점 (조회 {views:,})")
                        current_score = boosted_score
                
                # 댓글 50개 이상 → +5점 보너스
                if comments >= 50:
                    current_score = post['filter_result'].get('relevance_score', 5)
                    new_score = min(current_score + 5, 100)
                    post['filter_result']['relevance_score'] = new_score
                    post['filter_result']['high_engagement_boost'] = True
                    print(f"      💬 고댓글 보정: +5점 (댓글 {comments}개) → {new_score}점")
                        
            except Exception as e:
                print(f"      ⚠️ AI 에러: {e}")

    # 6단계: 정렬 - MVNO 무조건 앞, MNO 핫글 뒤
    def get_score(post):
        result = post.get('filter_result', {})
        views = post.get('views', 0)
        comments = post.get('comments', 0)
        title = post.get('title', '')
        is_mno = result.get('is_mno_high_traffic', False)

        # AI 중요도 점수 (본문 분석 후 업데이트된 값 사용)
        ai_score = result.get('relevance_score', 5)

        # 조회수 점수 (0~30)
        if views >= 10000:
            view_score = 30
        elif views >= 5000:
            view_score = 20
        elif views >= 1000:
            view_score = 10
        else:
            view_score = views / 200  # 최대 5점

        # 댓글 점수 (0~20)
        if comments >= 20:
            comment_score = 20
        elif comments >= 10:
            comment_score = 10
        else:
            comment_score = comments * 0.5  # 최대 5점

        # 긴급성 보너스 (오늘까지, 마감, 특가, 한정 등)
        urgency_keywords = ['오늘까지', '마감', '한정', '긴급', '종료예정', '곧마감', '마지막']
        urgency_bonus = 15 if any(kw in title for kw in urgency_keywords) else 0

        if is_mno:
            # MNO 핫글: 최대 50점 → MVNO(100+) 보다 항상 낮음
            return view_score + comment_score
        else:
            # MVNO: 100 베이스 + AI점수(0~100) + 조회수(0~30) + 댓글(0~20) + 긴급성(0~15)
            return 100 + ai_score * 10 + view_score + comment_score + urgency_bonus

    # [v3.0] 본문 AI에서 오탐으로 판단된 글 제거
    before = len(all_posts_merged)
    all_posts_merged = [p for p in all_posts_merged if not p.get('filter_result', {}).get('_remove')]
    if len(all_posts_merged) < before:
        tg(f"🚫 본문AI 오탐 제거: {before - len(all_posts_merged)}개")

    all_posts_merged.sort(key=get_score, reverse=True)
    final = all_posts_merged[:top_n] if top_n else all_posts_merged

    mvno_count = len([p for p in final if not p.get('filter_result', {}).get('is_mno_high_traffic')])
    mno_count = len(final) - mvno_count
    tg(f"✅ 최종: {len(final)}개 (MVNO {mvno_count}개 먼저 → 통신사 핫글 {mno_count}개)")
    return final


# ══════════════════════════════════════════════════════════════════════════════
# 테스트 코드
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # 전체 게시판 크롤링
    scraper = PpomppuScraper()
    posts = scraper.scrape(days=2)
    
    # MVNO 필터링 (전체)
    mvno_posts = filter_mvno_posts(posts, use_ai=True, top_n=None)
    
    # 결과 출력
    if mvno_posts:
        # MVNO / MNO 분리
        mvno_list = [p for p in mvno_posts if not p.get('filter_result', {}).get('is_mno_high_traffic')]
        mno_list  = [p for p in mvno_posts if p.get('filter_result', {}).get('is_mno_high_traffic')]
        # MNO는 조회수 내림차순
        mno_list.sort(key=lambda p: p.get('views', 0), reverse=True)

        def print_post(i, post, show_score=True):
            result = post.get('filter_result', {})
            posted_at = post.get('posted_at', '')
            date_str = posted_at.strftime('%m-%d %H:%M') if posted_at else '시간 없음'
            score_str = f" | 중요도 {result.get('relevance_score', 0)}/10" if show_score else ""
            print(f"\n{'='*80}")
            print(f"🔥 #{i}{score_str} | 📅 {date_str}")
            provider = result.get('provider')
            if provider and provider != 'None':
                print(f"📱 {provider}")
            print(f"💡 {post['title']}")
            content_summary = result.get('content_summary', '')
            if content_summary:
                print(f"📄 [본문요약] {content_summary}")
            print(f"👁 조회 {post['views']:,} | 💬 댓글 {post['comments']}")
            print(f"🔗 {post['url']}")

        # MVNO 출력
        print("\n" + "="*80)
        print("🔥 MVNO 필터링 결과")
        print("="*80) 
        for i, post in enumerate(mvno_list, 1):
            print_post(i, post, show_score=True)

        # 통신사 핫글 출력
        if mno_list:
            print("\n\n" + "="*80)
            print("🔥 통신사 핫글")
            print("="*80)
            for i, post in enumerate(mno_list, 1):
                print_post(i, post, show_score=False)
    else:
        print("\n⚠️ MVNO 관련 글이 없습니다.")
def filter_new_posts(all_posts, existing_ids):
    """신규 글만 필터링"""
    new_posts = [p for p in all_posts if p['post_id'] not in existing_ids]
    print(f"✅ 신규 글: {len(new_posts)}개 (전체 {len(all_posts)}개)")
    return new_posts