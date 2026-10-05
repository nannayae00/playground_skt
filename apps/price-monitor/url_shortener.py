"""
url_shortener.py (선택사항)
──────────────────────────────────────────────────────────────────────────────
URL 단축 서비스 통합
- 기본: 뽐뿌 자체 짧은 URL 사용
- 옵션: bit.ly, is.gd 등 단축 서비스
──────────────────────────────────────────────────────────────────────────────
"""

import requests


def shorten_with_isgd(long_url):
    """
    is.gd 무료 URL 단축 서비스
    
    Args:
        long_url: 원본 URL
    
    Returns:
        str: 단축 URL 또는 원본 URL (실패 시)
    """
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={long_url}"
        response = requests.get(api_url, timeout=5)
        
        if response.status_code == 200:
            short_url = response.text.strip()
            print(f"✅ URL 단축: {short_url}")
            return short_url
        else:
            print(f"⚠️ URL 단축 실패: {response.status_code}")
            return long_url
            
    except Exception as e:
        print(f"⚠️ URL 단축 에러: {e}")
        return long_url


def shorten_with_tinyurl(long_url):
    """
    TinyURL 무료 단축 서비스
    
    Args:
        long_url: 원본 URL
    
    Returns:
        str: 단축 URL 또는 원본 URL (실패 시)
    """
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        
        if response.status_code == 200:
            short_url = response.text.strip()
            print(f"✅ URL 단축: {short_url}")
            return short_url
        else:
            print(f"⚠️ URL 단축 실패: {response.status_code}")
            return long_url
            
    except Exception as e:
        print(f"⚠️ URL 단축 에러: {e}")
        return long_url


def get_short_ppomppu_url(post_id, board_id='ppomppu'):
    """
    뽐뿌 자체 짧은 URL 생성 (가장 권장)
    
    Args:
        post_id: 게시글 번호 (예: "680783")
        board_id: 게시판 ID (기본: "ppomppu")
    
    Returns:
        str: 짧은 URL
    
    Examples:
        >>> get_short_ppomppu_url("680783")
        'https://m.ppomppu.co.kr/new/bbs_view.php?no=680783'
    """
    # 모바일 URL이 가장 짧음
    return f"https://m.ppomppu.co.kr/new/bbs_view.php?no={post_id}"


def smart_shorten_url(original_url, post_id=None, use_external=False):
    """
    스마트 URL 단축
    
    Args:
        original_url: 원본 URL
        post_id: 뽐뿌 게시글 번호 (있으면)
        use_external: True면 외부 단축 서비스 사용
    
    Returns:
        str: 단축 URL
    """
    # 1. 뽐뿌 게시글이면 자체 짧은 URL 사용 (가장 권장)
    if 'ppomppu.co.kr' in original_url and post_id:
        return get_short_ppomppu_url(post_id)
    
    # 2. 이미 짧으면 그대로 사용
    if len(original_url) < 50:
        return original_url
    
    # 3. 외부 단축 서비스 사용 (옵션)
    if use_external:
        return shorten_with_isgd(original_url)
    
    return original_url


# ══════════════════════════════════════════════════════════════════════════════
# 사용 예시
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # 테스트
    long_url = "https://m.ppomppu.co.kr/new/bbs_view.php?id=ppomppu&no=680783&keyword=&page=1"
    post_id = "680783"
    
    print("=" * 80)
    print("📋 URL 단축 테스트")
    print("=" * 80)
    
    print(f"\n원본 URL ({len(long_url)}자):")
    print(long_url)
    
    print(f"\n뽐뿌 자체 짧은 URL:")
    short_url = get_short_ppomppu_url(post_id)
    print(f"{short_url} ({len(short_url)}자)")
    
    print(f"\nis.gd 단축:")
    isgd_url = shorten_with_isgd(long_url)
    print(f"{isgd_url} ({len(isgd_url)}자)")
    
    print(f"\nTinyURL 단축:")
    tiny_url = shorten_with_tinyurl(long_url)
    print(f"{tiny_url} ({len(tiny_url)}자)")
    
    print(f"\n스마트 단축 (권장):")
    smart_url = smart_shorten_url(long_url, post_id)
    print(f"{smart_url} ({len(smart_url)}자)")


# ══════════════════════════════════════════════════════════════════════════════
# main.py 통합 예시
# ══════════════════════════════════════════════════════════════════════════════

"""
main.py의 send_ppomppu_alert() 함수에서 사용:

from core.url_shortener import smart_shorten_url

def send_ppomppu_alert(post):
    ...
    
    # URL 단축
    short_url = smart_shorten_url(
        post['url'], 
        post_id=post['post_id'],
        use_external=False  # 외부 서비스 사용 여부
    )
    
    message = f'''...
🔗 {short_url}
...'''
"""
