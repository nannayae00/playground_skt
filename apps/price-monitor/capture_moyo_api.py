# -*- coding: utf-8 -*-
"""
capture_moyo_api.py - 모요 API 실제 요청 body 캡처 (페이지네이션 스키마 확인용)

[수정 이력]
- v0.3 (2026-07-08) 캡처 필터 확장
    * 'plan-search' 필터 시 0건 → 테마 페이지가 다른 엔드포인트를 쓰는 것으로 추정
    * api.moyoplan.com 도메인 전체 요청을 캡처하도록 필터 완화
      (GET 포함, path 무관 - 실제 사용 엔드포인트 특정용)
- v0.2 (2026-07-08) networkidle 타임아웃 수정
    * 모요는 SPA라 백그라운드 폴링 등으로 networkidle 이 영원히 안 잡힘
      → wait_until='domcontentloaded' + 고정 대기(3초)로 변경
    * goto 실패해도 그 전까지 캡처된 요청은 저장하도록 try/finally 처리
    * 페이지 이동 타임아웃 90s → 30s 로 단축 (실패 시 빨리 다음 단계로)
- v0.1 (2026-07-07) 최초 작성
    * 테마 페이지(LG/KT 자회사) 접속 + 스크롤/페이지 이동하며
      plan-search API 요청의 POST body 를 그대로 캡처
    * 결과: moyo_api_requests.txt (Claude에게 공유용)

[실행]
    python capture_moyo_api.py
"""

import json
from playwright.sync_api import sync_playwright

THEME_URLS = [
    'https://www.moyoplan.com/plans/themes/lg-subsidiary?from=search-plans',
    'https://www.moyoplan.com/plans/themes/kt-subsidiary?from=search-plans',
]

captured = []
all_urls = []  # 진단용: moyoplan.com 관련 전체 요청 URL (타입 무관)


def on_request(request):
    if 'moyoplan.com' in request.url:
        all_urls.append(f'[{request.resource_type}] {request.method} {request.url}')
    # path 필터 제거, moyoplan.com 관련 API/XHR/fetch 전부 캡처
    if 'moyoplan.com' not in request.url:
        return
    if request.resource_type not in ('xhr', 'fetch'):
        return
    entry = {
        'method': request.method,
        'url': request.url,
        'body': request.post_data,
    }
    captured.append(entry)
    print(f'📡 {request.method} {request.url}')
    if request.post_data:
        print(f'   body: {request.post_data[:300]}')


def save_captured():
    with open('moyo_api_requests.txt', 'w', encoding='utf-8') as f:
        for e in captured:
            f.write(f'{"="*60}\n{e["method"]} {e["url"]}\n')
            if e['body']:
                try:
                    f.write(json.dumps(json.loads(e['body']),
                                       ensure_ascii=False, indent=2))
                except Exception:
                    f.write(str(e['body']))
            f.write('\n')
    print(f'\n총 {len(captured)}건 캡처 → moyo_api_requests.txt')
    if not captured and all_urls:
        with open('moyo_all_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(set(all_urls))))
        print(f'⚠️ API 캡처 0건. moyoplan.com 관련 전체 요청 '
              f'{len(set(all_urls))}건 → moyo_all_urls.txt 저장 (진단용)')
    elif not all_urls:
        print('⚠️ moyoplan.com 관련 요청 자체가 0건 - 페이지 로드 실패 가능성')
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/126.0 Safari/537.36'),
            locale='ko-KR')
        page = context.new_page()
        page.on('request', on_request)

        try:
            for url in THEME_URLS:
                print(f'\n{"="*60}\n접속: {url}')
                try:
                    page.goto(url, wait_until='domcontentloaded',
                              timeout=30000)
                except Exception as e:
                    print(f'   ⚠️ goto 실패(계속 진행): {e}')
                page.wait_for_timeout(3000)  # 초기 API 호출 대기

                # 스크롤 3회 (무한스크롤 방식이면 추가 요청 발생)
                for i in range(3):
                    try:
                        page.mouse.wheel(0, 3000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)

                # 페이지네이션 버튼 방식이면 '2' 버튼 클릭 시도
                try:
                    btn = page.query_selector(
                        'button:has-text("2"), a:has-text("2")')
                    if btn:
                        btn.click()
                        page.wait_for_timeout(2000)
                        print('   (2페이지 버튼 클릭됨)')
                except Exception:
                    pass
        finally:
            browser.close()
            save_captured()

    print('파일 내용을 Claude에게 붙여넣어 주세요.')


if __name__ == '__main__':
    main()