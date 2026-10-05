"""
dcinside_scraper.py
──────────────────────────────────────────────────────────────────────────────
디시인사이드 갤러리 크롤링 - MVNO/통신 관련 게시글 수집
- 지원 갤러리: 알뜰폰(mvnogallery), 휴대폰(cellularphone), 갤럭시(galaxy)
- requests 기반 (Playwright 불필요)
- 기존 ppomppu_scraper와 동일한 출력 포맷 (filter_mvno_posts 연동)

[수정 이력]
v1.5 | 2026-09-20 | 429(Too Many Requests) 뜨면 그 페이지에서 바로 break하고 이후
      | 페이지를 통째로 포기하던 문제 수정 - _get_with_retry() 추가
      | (ppomppu_scraper.py와 동일 패턴)
v1.0 | 2026-03-10 | 최초 작성
v1.1 | 2026-03-10 | pages_limit 기본값 10→50 (하루치 수집 대응)
v1.2 | 2026-03-11 | datetime.now() → KST 기준으로 수정 (Cloud Run UTC 오프셋 대응)
v1.3 | 2026-03-24 | oldest_on_page 버그 수정 (cutoff 이전 글도 페이지 종료 판단에 반영)
v1.4 | 2026-03-24 | 날짜만 있는 글(03.23) 시간을 23:59로 파싱 (cutoff 조기 스킵 방지)
v1.3 | 2026-03-24 | oldest_on_page 버그 수정 (cutoff 이전 글도 페이지 종료 판단에 반영)
v1.4 | 2026-03-24 | 날짜만 있는 글(03.23) 시간을 23:59로 파싱 (cutoff 조기 스킵 방지)
v1.3 | 2026-03-24 | oldest_on_page 버그 수정 (cutoff 이전 글도 페이지 종료 판단에 반영)
──────────────────────────────────────────────────────────────────────────────
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
KST = pytz.timezone("Asia/Seoul")
import re
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://m.dcinside.com/',
}


def _get_with_retry(url, headers=None, timeout=10, max_retries=4, base_delay=3):
    """[v1.5] 429 뜨면 그 페이지에서 바로 break하고 이후 페이지 전체를
    포기하던 문제 수정 (ppomppu_scraper.py의 동일 수정과 같은 패턴)."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                retry_after = resp.headers.get('Retry-After')
                wait = float(retry_after) if retry_after and retry_after.strip().isdigit() else base_delay * (2 ** attempt)
                print(f'  ⏳ 429 Too Many Requests - {wait:.0f}초 대기 후 재시도 ({attempt+1}/{max_retries})')
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            wait = base_delay * (2 ** attempt)
            print(f'  ⚠️ 요청 실패({e}) - {wait:.0f}초 대기 후 재시도 ({attempt+1}/{max_retries})')
            time.sleep(wait)
    raise last_exc if last_exc else RuntimeError(f'요청 실패: {url}')

# 갤러리 설정
GALLERIES = {
    'mvno': {
        'id': 'mvnogallery',
        'name': '알뜰폰 갤러리',
        'filter': False,       # MVNO 전용 갤러리 → 필터링 없이 전수집
    },
    'cellularphone': {
        'id': 'cellularphone',
        'name': '휴대폰 갤러리',
        'filter': True,        # 잡글 많음 → MVNO 필터링 적용
    },
    'galaxy': {
        'id': 'galaxy',
        'name': '갤럭시 갤러리',
        'filter': True,
    },
}

DC_BASE = 'https://m.dcinside.com/board'


def _parse_posted_at(time_str, today=None):
    """
    디시 시간 문자열 → datetime
    - '11:17' → 오늘 날짜 적용
    - '03.09' → 연도 자동 적용
    """
    if today is None:
        today = datetime.now(KST).replace(tzinfo=None)
    time_str = time_str.strip()
    try:
        if ':' in time_str:
            h, m = map(int, time_str.split(':'))
            return today.replace(hour=h, minute=m, second=0, microsecond=0)
        elif '.' in time_str:
            month, day = map(int, time_str.split('.'))
            year = today.year
            dt = datetime(year, month, day, 23, 59)
            # 미래면 작년으로
            if dt > today:
                dt = dt.replace(year=year - 1)
            return dt
    except Exception:
        pass
    return today


def scrape_gallery(gallery_key, days=1, pages_limit=50):
    """
    디시인사이드 갤러리 게시글 수집

    Args:
        gallery_key: 'mvno' | 'cellularphone' | 'galaxy'
        days: 수집 기간 (일 단위)
        pages_limit: 최대 페이지 수 (무한루프 방지)

    Returns:
        list of dict (ppomppu_scraper 동일 포맷)
        {
            'post_id', 'title', 'url', 'views', 'comments',
            'posted_at', 'author', 'category', 'source'
        }
    """
    gal = GALLERIES.get(gallery_key)
    if not gal:
        raise ValueError(f'Unknown gallery: {gallery_key}')

    gal_id = gal['id']
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)
    posts = []
    today = datetime.now(KST).replace(tzinfo=None)

    print(f'[{gal["name"]}] 수집 시작 (최근 {days}일)')

    for page in range(1, pages_limit + 1):
        url = f'{DC_BASE}/{gal_id}?page={page}'
        try:
            resp = _get_with_retry(url, headers=HEADERS, timeout=10)
        except Exception as e:
            print(f'  ⚠️ 페이지 {page} 요청 실패(재시도 소진): {e}')
            break

        soup = BeautifulSoup(resp.text, 'html.parser')
        items = soup.select('ul.gall-detail-lst li')

        if not items:
            print(f'  페이지 {page}: 게시글 없음 → 종료')
            break

        oldest_on_page = None
        new_count = 0

        for li in items:
            # 광고/공지 스킵
            if li.get('class') and any(c in li.get('class', []) for c in ['adv-inner', 'notice']):
                continue

            a_lt = li.select_one('a.lt')
            if not a_lt:
                continue

            # 제목
            title_el = a_lt.select_one('span.subjectin')
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            # URL + post_id
            # [v1.6] href에 "?page=34" 같은 쿼리스트링이 붙어있어 문자열이
            # 숫자로 안 끝나는 경우가 흔함 - r'/(\d+)$'가 매번 실패해서
            # Firestore post_id에 href 전체가 그대로 들어가던 버그 수정
            href = a_lt.get('href', '')
            post_id_match = re.search(r'/(\d+)(?:\?|$)', href)
            post_id = post_id_match.group(1) if post_id_match else href
            full_url = href if href.startswith('http') else f'https://m.dcinside.com{href}'

            # ginfo: [카테고리, 작성자, 시간, 조회수, 추천]
            ginfo = a_lt.select('ul.ginfo li')
            category = ginfo[0].get_text(strip=True) if ginfo else ''
            author   = ginfo[1].get_text(strip=True) if len(ginfo) > 1 else ''
            time_str = ginfo[2].get_text(strip=True) if len(ginfo) > 2 else ''
            views_raw = ginfo[3].get_text(strip=True) if len(ginfo) > 3 else '0'
            views = int(re.sub(r'[^0-9]', '', views_raw) or 0)

            # 댓글 수
            ct_el = li.select_one('span.ct')
            comments = int(ct_el.get_text(strip=True) or 0) if ct_el else 0

            # 날짜 파싱
            posted_at = _parse_posted_at(time_str, today)

            # oldest_on_page는 cutoff 체크 전에 업데이트 (페이지 종료 판단용)
            if oldest_on_page is None or posted_at < oldest_on_page:
                oldest_on_page = posted_at

            # 기간 체크
            if posted_at < cutoff:
                continue

            posts.append({
                'post_id':   f'dc_{gal_id}_{post_id}',
                'title':     title,
                'url':       full_url,
                'views':     views,
                'comments':  comments,
                'posted_at': posted_at,
                'author':    author,
                'category':  category,
                'source':    f'dcinside_{gallery_key}',
            })
            new_count += 1

        print(f'  페이지 {page}: {new_count}개 수집 (누적 {len(posts)}개)')

        # 페이지의 가장 오래된 글이 cutoff 이전이면 종료
        if oldest_on_page and oldest_on_page < cutoff:
            print(f'  cutoff 도달 → 수집 종료')
            break

        time.sleep(0.5)  # 서버 부하 방지

    print(f'[{gal["name"]}] 총 {len(posts)}개 수집 완료')
    return posts


def scrape_all(days=1, galleries=None):
    """
    여러 갤러리 한번에 수집

    Args:
        days: 수집 기간
        galleries: ['mvno', 'cellularphone', 'galaxy'] (None이면 전체)

    Returns:
        dict { gallery_key: [posts] }
    """
    if galleries is None:
        galleries = list(GALLERIES.keys())

    result = {}
    for key in galleries:
        result[key] = scrape_gallery(key, days=days)
        time.sleep(1)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 테스트
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    posts = scrape_gallery('mvno', days=0.1, pages_limit=2)
    print(f'\n--- 샘플 출력 (3개) ---')
    for p in posts[:3]:
        print(f"[{p['posted_at'].strftime('%m-%d %H:%M')}] {p['title']}")
        print(f"  조회: {p['views']} | 댓글: {p['comments']} | {p['url']}")