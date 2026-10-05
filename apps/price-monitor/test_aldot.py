"""
test_ald.py  v1.0
─────────────────────────────────────────────────────────────────────────────
알닷 스크래퍼 독립 테스트 스크립트
실행: python test_ald.py

출력:
  - 수집된 요금제 샘플 5개 상세 출력
  - 전체 통계 (총 수집수, 망별/5G여부 분포, RS 비율)
  - 파싱 실패 케이스 경고
─────────────────────────────────────────────────────────────────────────────
"""

import sys
import os
import json
import asyncio
from pathlib import Path

# ── 경로 설정 (scrapers/ 패키지 인식) ────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── 임시 scrapers 패키지 구조 만들기 (같은 디렉터리에 파일이 있을 경우 대응) ──
# scrapers/ 디렉터리가 없으면 현재 디렉터리에서 직접 import 시도
try:
    from scrapers.aldot_scraper import AldotScraper
    from scrapers.base_scraper import make_plan
except ModuleNotFoundError:
    # scraper 파일들이 현재 디렉터리에 있는 경우
    # 임시로 scrapers 패키지처럼 동작하게 패치
    import importlib, types

    def _patch_scrapers_pkg():
        pkg = types.ModuleType('scrapers')
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = 'scrapers'
        sys.modules['scrapers'] = pkg

        # base_scraper
        spec = importlib.util.spec_from_file_location(
            'scrapers.base_scraper', ROOT / 'base_scraper.py')
        mod = importlib.util.module_from_spec(spec)
        sys.modules['scrapers.base_scraper'] = mod
        spec.loader.exec_module(mod)

        # ald_scraper
        spec2 = importlib.util.spec_from_file_location(
            'scrapers.aldot_scraper', ROOT / 'aldot_scraper.py')
        mod2 = importlib.util.module_from_spec(spec2)
        sys.modules['scrapers.aldot_scraper'] = mod2
        spec2.loader.exec_module(mod2)

        return mod2.AldotScraper, mod.make_plan

    AldScraper, make_plan = _patch_scrapers_pkg()


# ── 진행 메시지 콜백 ────────────────────────────────────────────────────────

def progress(msg: str):
    print(f'  {msg}', flush=True)


# ── 통계 출력 헬퍼 ──────────────────────────────────────────────────────────

def print_stats(plans: list):
    if not plans:
        print('\n❌ 수집된 요금제 없음!')
        return

    total = len(plans)
    net_dist   = {}
    gen_dist   = {}
    rs_count   = sum(1 for p in plans if p.get('is_rs'))
    price_zero = sum(1 for p in plans if p.get('final_price', 0) == 0)
    no_data    = sum(1 for p in plans if not p.get('data'))

    for p in plans:
        net = p.get('network', '?')
        gen = p.get('network_generation', '?')
        net_dist[net] = net_dist.get(net, 0) + 1
        gen_dist[gen] = gen_dist.get(gen, 0) + 1

    print(f'\n{"="*60}')
    print(f'  총 수집: {total}개')
    print(f'  RS 요금제: {rs_count}개 ({rs_count/total*100:.1f}%)')
    print(f'  가격=0 이상: {price_zero}개')
    print(f'  데이터 없음: {no_data}개')
    print(f'\n  [망 분포]')
    for k, v in sorted(net_dist.items()):
        print(f'    {k}: {v}개')
    print(f'\n  [세대 분포]')
    for k, v in sorted(gen_dist.items()):
        print(f'    {k}: {v}개')
    print(f'{"="*60}')


def print_sample(plans: list, n: int = 5):
    print(f'\n── 샘플 {min(n, len(plans))}개 ──────────────────────────────────')
    for i, p in enumerate(plans[:n], 1):
        print(f'\n  [{i}] {p.get("provider")} / {p.get("name")}')
        print(f'       plan_id : {p.get("plan_id")}')
        print(f'       데이터  : {p.get("data")}  (data_gb={p.get("data_gb")})')
        print(f'       통화/문자: {p.get("voice")} / {p.get("sms")}')
        print(f'       망      : {p.get("network")} {p.get("network_generation")}')
        print(f'       가격    : 최종 {p.get("final_price"):,}원  기본 {p.get("base_price"):,}원  할인{p.get("discount_months")}개월')
        print(f'       is_rs   : {p.get("is_rs")}')


def print_price_range(plans: list):
    """가격 분포 확인"""
    if not plans: return
    prices = sorted(p['final_price'] for p in plans if p.get('final_price', 0) > 0)
    if not prices: return
    print(f'\n  [가격 범위]')
    print(f'    최저: {prices[0]:,}원  /  최고: {prices[-1]:,}원  /  중간: {prices[len(prices)//2]:,}원')

    # 구간별
    buckets = {'~5천': 0, '5천~1만': 0, '1만~2만': 0, '2만~3만': 0, '3만~': 0}
    for pr in prices:
        if   pr <  5000:  buckets['~5천']    += 1
        elif pr < 10000:  buckets['5천~1만'] += 1
        elif pr < 20000:  buckets['1만~2만'] += 1
        elif pr < 30000:  buckets['2만~3만'] += 1
        else:             buckets['3만~']    += 1
    for k, v in buckets.items():
        bar = '█' * (v // 3)
        print(f'    {k:8s}: {v:4d}개  {bar}')


# ── 메인 ────────────────────────────────────────────────────────────────────

async def main():
    print('=' * 60)
    print('  알닷(aldot) 스크래퍼 테스트')
    print('  대상: https://www.uplusmvno.com/plan/plan-list')
    print('=' * 60)

    scraper = AldotScraper(progress_callback=progress)
    plans, screenshot_path = scraper.scrape()

    # 결과 출력
    print_sample(plans, n=5)
    print_stats(plans)
    print_price_range(plans)

    # JSON 저장 (파싱 결과 확인용)
    out_path = ROOT / 'aldot_test_result.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)
    print(f'\n  💾 결과 저장: {out_path}')

    # 파싱 품질 체크
    issues = []
    for p in plans:
        if not p.get('data'):
            issues.append(f"  ⚠️  plan_id={p['plan_id']} : 데이터 없음")
        if p.get('provider') in ('알닷', '') and p.get('name') == p.get('plan_id'):
            issues.append(f"  ⚠️  plan_id={p['plan_id']} : provider/name 파싱 의심")

    if issues:
        print(f'\n  [파싱 주의 항목 {len(issues)}건]')
        for msg in issues[:10]:
            print(msg)
        if len(issues) > 10:
            print(f'  ... 외 {len(issues)-10}건')
    else:
        print('\n  ✅ 파싱 품질 이상 없음')

    print('\n테스트 완료.')
    return plans


if __name__ == '__main__':
    result = asyncio.run(main())