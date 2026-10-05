# -*- coding: utf-8 -*-
"""
gift_moyo_scraper.py - 모요 사은품 수집 (KT·LG 자회사)

[수정 이력]
- v0.8 (2026-07-08) API 페이지네이션 확정 → 최종 안정화
    * 페이지네이션 키 확정: ?page=N&size=100 (쿼리스트링, POST body 무효)
    * 전략: ranking API 전체 순회 → mobilePlanOperatorBrandName 으로 자회사 필터
    * Playwright 불필요 (순수 requests)
    * 100건씩 최대 25페이지 → 2,500건 커버 (현재 total ~2,300)
    * 자회사 목표 건수(TARGET_COUNT) 달성 후 조기 종료
    * gift_texts: giftGroupList title + subTitle 병합 (개월수 포함)
- v0.7 (2026-07-08) 토글 클릭 시도 → innerText에 사은품 없음 확인 (폐기)
- v0.6 (2026-07-08) DOM 카드 파싱 방식 (폐기)
- v0.5 (2026-07-08) __NEXT_DATA__ 방식 (폐기)
- v0.4 (2026-07-07) POST body 파라미터 시도 (폐기)
- v0.1~0.3 (2026-07-07) 각종 시도 (폐기)
"""

import requests
from datetime import datetime, timezone

API_URL = 'https://api.moyoplan.com/core/api/v2/moyo/plan-search/ranking'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/126.0 Safari/537.36'),
    'Referer': 'https://www.moyoplan.com/',
    'Origin':  'https://www.moyoplan.com',
    'Accept':  'application/json',
}
PAGE_SIZE    = 100
SITE         = 'moyo'
EARLY_STOP_AFTER = 3   # 전 브랜드 발견 후 N페이지 추가 없으면 종료

TARGET_BRANDS = {
    'KT엠모바일':    ('KT엠모바일', 'KT M모바일', 'kt m모바일', 'KT'),  # API에서 'KT'로 저장됨
    'KT스카이라이프': ('스카이라이프',),
    'LG헬로모바일':  ('헬로모바일', 'LG헬로'),
    'U+유모바일':    ('유모바일', 'U+유모바일'),
}
_MNO_MAP = {'SKT': 'SKT', 'KT': 'KT', 'LGU': 'LGU+'}


def _match_brand(brand_name: str) -> str | None:
    for std_name, aliases in TARGET_BRANDS.items():
        for a in aliases:
            # 'KT' 는 'KT스카이라이프' 오매칭 방지를 위해 exact match
            if a == 'KT':
                if brand_name == 'KT':
                    return std_name
            elif a in brand_name:
                return std_name
    return None


def _to_plan(meta: dict, provider: str) -> dict:
    gifts = []
    for g in meta.get('giftGroupList') or []:
        text = (g.get('title') or '').strip()
        sub  = (g.get('subTitle') or '').strip()
        if sub and sub not in text:
            text = f'{text} ({sub})'
        if text:
            gifts.append(text)
    return {
        'site':               SITE,
        'plan_id':            meta.get('id'),
        'provider':           provider,
        'brand_raw':          meta.get('mobilePlanOperatorBrandName', ''),
        'network':            _MNO_MAP.get(meta.get('mno', ''), meta.get('mno', '')),
        'network_generation': meta.get('network', ''),
        'name':               meta.get('name', ''),
        'data_gb':            meta.get('dataTotal', 0),
        'base_price':         meta.get('originalFee', 0),
        'final_price':        meta.get('discountFee', 0),
        'discount_months':    meta.get('discountPeriod', 0),
        'gift_texts':         gifts,
        'gift_types':         [g.get('representationItemType', '')
                               for g in meta.get('giftGroupList') or []],
        'scraped_at':         datetime.now(timezone.utc).isoformat(),
    }


def scrape_moyo_gifts(**_kwargs) -> list:
    """
    ranking API 전체 순회 → KT·LG 자회사 필터 → 사은품 포함 plan list 반환.
    Playwright 불필요, 동기 함수.
    조기 종료: 목표 브랜드 전체 발견 후 EARLY_STOP_AFTER 페이지 추가 없으면 종료.
    """
    s = requests.Session()
    results, page = [], 1
    no_new_streak = 0
    all_brands_found = False

    while True:
        params = {'sorting': 'recommend_v2', 'page': page, 'size': PAGE_SIZE}
        r = s.post(API_URL, json={}, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()

        body  = r.json().get('result') or {}
        metas = body.get('planMetas', [])
        total = body.get('totalSize', 0)
        if not metas:
            break

        before = len(results)
        for meta in metas:
            brand    = meta.get('mobilePlanOperatorBrandName', '')
            provider = _match_brand(brand)
            if provider and not meta.get('isDeleted'):
                results.append(_to_plan(meta, provider))

        added = len(results) - before
        found_brands = {p['provider'] for p in results}
        all_brands_found = (set(TARGET_BRANDS.keys()) <= found_brands)

        print(f'  page {page}: {len(metas)}건 / 자회사 +{added} 누적 {len(results)}건 '
              f'/ 발견 브랜드 {sorted(found_brands)}')

        # 조기 종료: 전 브랜드 발견 후 추가 없는 페이지가 EARLY_STOP_AFTER회 연속
        if all_brands_found:
            no_new_streak = no_new_streak + 1 if added == 0 else 0
            if no_new_streak >= EARLY_STOP_AFTER:
                print(f'  전 브랜드 발견 + {EARLY_STOP_AFTER}페이지 추가 없음 → 조기 종료')
                break

        if page * PAGE_SIZE >= total:
            break
        page += 1

    return results


if __name__ == '__main__':
    plans = scrape_moyo_gifts()
    print(f'\n=== 자회사 사은품 수집 ({len(plans)}건) ===')
    by_prov = {}
    for p in plans:
        by_prov.setdefault(p['provider'], []).append(p)

    for prov, items in sorted(by_prov.items()):
        with_gift = [p for p in items if p['gift_texts']]
        print(f'\n■ {prov}: {len(items)}건 (사은품 {len(with_gift)}건)')
        for p in with_gift[:3]:
            print(f"  - {p['name'][:45]} | {p['final_price']:,}원")
            for g in p['gift_texts']:
                print(f'      🎁 {g}')