# -*- coding: utf-8 -*-
"""
gift_job.py - 프로모션 사은품 센싱 메인 잡 (Cloud Run Job)

[수정 이력]
- v0.4 (2026-07-08) 모요 v0.8 동기함수 전환 반영
    * scrape_moyo_gifts 가 동기함수 (Playwright 불필요)
    * Playwright 는 유모바일 직영몰에만 사용
- v0.3 (2026-07-08) Playwright 단일 브라우저 구조 (폐기)
- v0.2 (2026-07-07) 모요 API 방식 (폐기)
- v0.1 (2026-07-07) 최초 작성

[배포]
gcloud run jobs deploy gift-sensing-job --source . \
    --region asia-northeast3 --project mvno-484509
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright

from scrapers.gift_moyo_scraper import scrape_moyo_gifts
from scrapers.umobile_scraper import scrape_umobile, PROVIDER as UMOBILE
from core.gift_comparator import compare_sites, format_telegram, format_moyo_report, format_summary_report

KST = timezone(timedelta(hours=9))

try:
    from core.firebase_handler import get_db
except ImportError:
    get_db = None

TELEGRAM_TOKEN  = os.environ.get('TELEGRAM_TOKEN', '')
GIFT_CHANNEL_ID = os.environ.get('GIFT_CHANNEL_ID', '')


async def _scrape_umobile_direct() -> list:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 Chrome/126.0 Safari/537.36'),
            locale='ko-KR')
        page = await context.new_page()
        plans = await scrape_umobile(page)
        await browser.close()
    return plans


def run():
    print('[1/4] 모요 자회사 사은품 수집 (API)...')
    moyo_plans = scrape_moyo_gifts()           # 동기 함수
    print(f'  → 총 {len(moyo_plans)}건')

    print('[2/4] 유모바일 직영 수집 (Playwright)...')
    umobile_plans = asyncio.run(_scrape_umobile_direct())
    print(f'  → {len(umobile_plans)}건')

    print('[3/4] 사이트간 비교 (유모바일)...')
    moyo_umobile = [x for x in moyo_plans if x['provider'] == UMOBILE]
    result = compare_sites(moyo_umobile, umobile_plans)
    print(f'  → 매칭 {result["matched"]}건, 이슈 {len(result["issues"])}건')

    print('[4/4] 저장 + 알림...')
    _save_firestore(moyo_plans, umobile_plans, result)
    # 1번: 자회사 LG/KT 요약
    _send_telegram(format_summary_report(moyo_plans))
    # 2~5번: 회사별 상세 (추후 활성화)
    # for prov in ['U+유모바일', 'LG헬로모바일', 'KT스카이라이프', 'KT엠모바일']:
    #     msg = format_moyo_report(moyo_plans, provider=prov)
    #     _send_telegram(msg)
    # 사이트간 비교 리포트
    _send_telegram(format_telegram(result))
    print('완료')


def _save_firestore(moyo, umobile, result):
    if not get_db:
        print('  (firebase_handler 미탑재 - 저장 스킵)')
        return
    db    = get_db()
    today = datetime.now(KST).strftime('%Y-%m-%d')
    db.collection('gift_snapshots').document(today).set({
        'moyo': moyo, 'umobile_direct': umobile,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    })
    for issue in result['issues']:
        if issue['over_threshold']:
            db.collection('gift_issues').add({
                **issue, 'date': today,
                'created_at': datetime.now(timezone.utc).isoformat(),
            })


def _send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not GIFT_CHANNEL_ID:
        print('  (텔레그램 설정 없음)\n' + msg)
        return
    import requests
    requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
        json={'chat_id': GIFT_CHANNEL_ID, 'text': msg, 'parse_mode': 'HTML'},
        timeout=15)


if __name__ == '__main__':
    run()