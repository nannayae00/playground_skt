"""
ppomppu_scraper.py (개선 버전)
──────────────────────────────────────────────────────────────────────────────
뽐뿌 커뮤니티 크롤링 - 실제 HTML 구조 반영
- 최근 7일 게시글 수집
- MVNO 관련 글 필터링 (핸드폰/통신 관련 게시판 우선)
- 신규 글만 선별 (기존 수집 결과와 비교)
──────────────────────────────────────────────────────────────────────────────
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import time

BASE_URL = "https://m.ppomppu.co.kr/new/bbs_list.php"

# 크롤링할 게시판 목록 (MVNO 관련 가능성 높은 순서)
BOARDS = [
    # 🔥 핵심 게시판 (MVNO 관련 핵심!)
    "phone",          # 휴대폰 포럼 ⭐⭐⭐
    "phone_consult",  # 핸드폰 상담 ⭐⭐⭐
    
    # 뽐뿌 메인 게시판
    "ppomppu",        # 뽐뿌게시판
    "ppomppu2",       # 뽐뿌게시판2
    
    # 가격비교 (프로모션 많음)
    "pmarket",        # 가격비교1
    "pmarket2",       # 가격비교2
    "pmarket3",       # 가격비교3
    
    # 이벤트/쿠폰 (통신사 프로모션)
    "event2",         # 이벤트
    "coupon",         # 쿠폰
    "campaign",       # 캠페인
    
    # 상담 게시판
    "card_consult",   # 카드 상담 (통신사 결합)
    "etc_consult",    # 기타 상담
    
    # 기타
    "freeboard",      # 자유게시판
    "computer",       # PC/인터넷
    "issue",          # 이슈게시판
]


class PpomppuScraper:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        })
    
    def scrape(self, days=7, max_pages=10, boards=None):
        """
        뽐뿌 게시판 크롤링
        
        Args:
            days: 최근 N일 게시글 수집 (기본 7일)
            max_pages: 최대 페이지 수 (기본 10페이지)
            boards: 크롤링할 게시판 리스트 (기본: BOARDS 전체)
        
        Returns:
            list of dict: 게시글 리스트
        """
        if boards is None:
            boards = BOARDS
        
        print(f"🔍 뽐뿌 스크래핑 시작 (최근 {days}일, 게시판 {len(boards)}개)")
        
        cutoff_date = datetime.now() - timedelta(days=days)
        all_posts = []
        seen_ids = set()
        
        # 여러 게시판 순회
        for board_id in boards:
            print(f"\n📋 [{board_id}] 게시판 크롤링 시작")
            
            for page in range(1, max_pages + 1):
                try:
                    posts = self._scrape_page(board_id, page, cutoff_date, seen_ids)
                    
                    if not posts:
                        print(f"🛑 [{board_id}] {page}페이지: 더 이상 새 글 없음 → 다음 게시판")
                        break
                    
                    all_posts.extend(posts)
                    
                    msg = f"✅ [{board_id}] {page}페이지 완료 | 이번 {len(posts)}개 | 누적 {len(all_posts)}개"
                    print(msg)
                    if self.progress_callback:
                        self.progress_callback(msg)
                    
                    time.sleep(0.5)  # 서버 부하 방지
                    
                except Exception as e:
                    print(f"⚠️ [{board_id}] {page}페이지 에러: {e}")
                    continue
        
        print(f"\n🎉 최종 수집: {len(all_posts)}개 (게시판 {len(boards)}개)")
        return all_posts
    
    def _scrape_page(self, board_id, page_num, cutoff_date, seen_ids):
        """단일 페이지 크롤링"""
        url = f"{BASE_URL}?id={board_id}&page={page_num}"
        
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 게시글 링크 추출
        posts = []
        
        # <a class="noeffect" href="/new/bbs_view.php?id=freeboard&no=XXX"> 형태
        links = soup.select('a.noeffect[href*="bbs_view.php"]')
        
        for link in links:
            try:
                href = link.get('href', '')
                
                # no= 파라미터 추출
                match = re.search(r'no=(\d+)', href)
                if not match:
                    continue
                
                post_id = match.group(1)
                
                # 중복 체크
                if post_id in seen_ids:
                    continue
                
                # 제목 추출 (링크 안의 텍스트)
                title_elem = link.select_one('.title')
                if not title_elem:
                    # 다른 구조일 수 있으니 전체 텍스트 가져오기
                    title = link.get_text(strip=True)
                    # 너무 길면 자르기
                    if len(title) > 200:
                        continue
                else:
                    title = title_elem.get_text(strip=True)
                
                if not title:
                    continue
                
                # 날짜 추출 (<time> 태그)
                time_elem = link.select_one('time')
                if time_elem:
                    time_str = time_elem.get_text(strip=True)
                    posted_at = self._parse_ppomppu_date(time_str)
                else:
                    posted_at = datetime.now()
                
                # cutoff_date 체크 (너무 오래된 글은 스킵)
                if posted_at < cutoff_date:
                    continue
                
                # URL 완성
                if href.startswith('/'):
                    full_url = f"https://m.ppomppu.co.kr/new{href}"
                else:
                    full_url = href
                
                # 조회수 추출 (<span class="view">208</span>)
                views = 0
                view_elem = link.select_one('.view')
                if view_elem:
                    view_text = view_elem.get_text(strip=True)
                    views = self._extract_number(view_text, r'(\d+)')
                
                # 댓글 수 추출 (<span class="rp">4</span>)
                comments = 0
                comment_elem = link.select_one('.rp')
                if comment_elem:
                    comment_text = comment_elem.get_text(strip=True)
                    comments = self._extract_number(comment_text, r'(\d+)')
                
                post = {
                    'post_id': post_id,
                    'title': title,
                    'url': full_url,
                    'views': views,
                    'comments': comments,
                    'posted_at': posted_at,
                    'scraped_at': datetime.now(),
                }
                
                posts.append(post)
                seen_ids.add(post_id)
                
            except Exception as e:
                print(f"⚠️ 게시글 파싱 실패: {e}")
                continue
        
        return posts
    
    def fetch_content(self, post_url):
        """
        게시글 본문 내용 가져오기
        
        Args:
            post_url: 게시글 URL
        
        Returns:
            dict: {'content': '본문', 'author': '작성자'}
        """
        try:
            response = self.session.get(post_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 본문 추출 (실제 구조에 맞게 수정 필요)
            content_div = soup.select_one('.board_txt')
            content = content_div.get_text(strip=True) if content_div else ''
            
            # 작성자 추출
            author_elem = soup.select_one('.nick')
            author = author_elem.get_text(strip=True) if author_elem else '익명'
            
            return {
                'content': content,
                'author': author
            }
        except Exception as e:
            print(f"⚠️ 본문 가져오기 실패: {e}")
            return {
                'content': '',
                'author': '익명'
            }
    
    def _extract_number(self, text, pattern):
        """정규표현식으로 숫자 추출"""
        match = re.search(pattern, text)
        if match:
            return int(match.group(1).replace(',', ''))
        return 0
    
    def _parse_ppomppu_date(self, time_str):
        """
        뽐뿌 <time> 태그 날짜 파싱
        
        Args:
            time_str: "17:15:49" (당일) 또는 "26-02-23" (이전 날짜)
        
        Returns:
            datetime 객체
        """
        if not time_str:
            return datetime.now()
        
        time_str = time_str.strip()
        
        try:
            # 패턴 1: HH:MM:SS (당일)
            if ':' in time_str and len(time_str.split(':')) == 3:
                time_part = datetime.strptime(time_str, '%H:%M:%S').time()
                return datetime.combine(datetime.today(), time_part)
            
            # 패턴 2: YY-MM-DD
            elif '-' in time_str and len(time_str) <= 8:
                parts = time_str.split('-')
                if len(parts) == 3:
                    year = int(parts[0])
                    # 2자리 연도면 2000년대로 변환
                    if year < 100:
                        year += 2000
                    month = int(parts[1])
                    day = int(parts[2])
                    return datetime(year, month, day)
            
            # 파싱 실패 시 현재 시간
            return datetime.now()
            
        except Exception as e:
            print(f"⚠️ 날짜 파싱 실패: {time_str} ({e})")
            return datetime.now()


# ══════════════════════════════════════════════════════════════════════════════
# 신규 글 필터링 (기존 수집 결과와 비교)
# ══════════════════════════════════════════════════════════════════════════════

def filter_new_posts(scraped_posts, existing_post_ids):
    """
    기존 수집 결과와 비교하여 신규 글만 반환
    
    Args:
        scraped_posts: 이번에 수집한 게시글 리스트
        existing_post_ids: 기존에 수집했던 post_id 집합
    
    Returns:
        list: 신규 게시글만
    """
    new_posts = [
        post for post in scraped_posts
        if post['post_id'] not in existing_post_ids
    ]
    
    print(f"📊 신규 글 필터링: {len(new_posts)}/{len(scraped_posts)}개")
    return new_posts


# ══════════════════════════════════════════════════════════════════════════════
# MVNO 필터링 통합 (mvno_classifier 사용)
# ══════════════════════════════════════════════════════════════════════════════

def filter_mvno_posts(posts, fetch_content=False, use_ai=True, top_n=10):
    """
    MVNO 관련 게시글만 필터링 + AI 분석 + 중요도 정렬
    
    Args:
        posts: 게시글 리스트
        fetch_content: True면 본문도 가져와서 분석 (느림)
        use_ai: True면 AI 분석 활성화 (권장)
        top_n: 상위 N개만 반환 (기본 10개)
    
    Returns:
        list: MVNO 관련 게시글 (중요도 높은 순)
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.mvno_classifier import classify_post, ai_analyze_and_summarize
    
    scraper = PpomppuScraper()
    filtered = []
    
    for post in posts:
        title = post['title']
        content = ''
        
        # 본문 가져오기 (옵션)
        if fetch_content:
            detail = scraper.fetch_content(post['url'])
            content = detail.get('content', '')
            post['content'] = content
            post['author'] = detail.get('author', '익명')
            time.sleep(0.3)  # 서버 부하 방지
        
        # 1단계: 룰베이스 필터링
        result = classify_post(title, content, use_ai=False)
        
        if not result:
            continue
        
        # 2단계: AI 분석 (중요도 점수 + 요약)
        if use_ai:
            ai_result = ai_analyze_and_summarize(
                title, 
                content, 
                views=post.get('views', 0),
                comments=post.get('comments', 0)
            )
            
            if ai_result and ai_result.get('is_mvno'):
                # AI 결과 병합
                result.update(ai_result)
                post['filter_result'] = result
                filtered.append(post)
        else:
            # AI 없이 룰베이스만
            post['filter_result'] = result
            filtered.append(post)
    
    # 3단계: 중요도 정렬
    def get_score(post):
        result = post.get('filter_result', {})
        ai_score = result.get('relevance_score', 0)  # 0-10점
        views = post.get('views', 0)
        comments = post.get('comments', 0)
        
        # 종합 점수 = AI점수*10 + 조회수/100 + 댓글*2
        return ai_score * 10 + views / 100 + comments * 2
    
    filtered.sort(key=get_score, reverse=True)
    
    # 상위 N개만
    top_posts = filtered[:top_n] if top_n else filtered
    
    print(f"✅ MVNO 필터링 완료: {len(top_posts)}/{len(filtered)}개 (전체 {len(posts)}개 중)")
    return top_posts


# ══════════════════════════════════════════════════════════════════════════════
# 테스트 코드
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # 테스트 실행 - 소수 게시판으로 빠른 테스트
    scraper = PpomppuScraper()
    
    # 주요 게시판만 테스트 (빠르게)
    test_boards = ["phone", "phone_consult"]
    posts = scraper.scrape(days=7, max_pages=5, boards=test_boards)
    
    # MVNO 필터링 + AI 분석
    print("\n" + "=" * 80)
    print("🔍 MVNO AI 필터링 (상위 10개)")
    print("=" * 80)
    mvno_posts = filter_mvno_posts(posts, fetch_content=False, use_ai=True, top_n=10)
    
    if mvno_posts:
        for i, post in enumerate(mvno_posts, 1):
            result = post.get('filter_result', {})
            
            print(f"\n{'='*80}")
            print(f"🔥 #{i} | 중요도 {result.get('relevance_score', 0)}/10 | "
                  f"조회 {post['views']:,} | 댓글 {post['comments']}")
            print(f"📱 {result.get('provider', '알뜰폰')}")
            print(f"💡 {result.get('summary', post['title'][:50])}")
            if result.get('key_points'):
                print(f"🔑 {', '.join(result['key_points'])}")
            print(f"🔗 {post['url']}")
    else:
        print("\n⚠️ MVNO 관련 글이 없습니다.")