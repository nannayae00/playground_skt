from playwright.sync_api import sync_playwright
from datetime import datetime
import re

class MoyoScraper:
    def __init__(self):
        self.base_url = "https://www.moyoplan.com/plans"
        self.max_pages = 250  # 2,500개 커버
        self.empty_page_threshold = 3
    
    def scrape(self):
        """모요 스크래핑 - HTML 파싱"""
        print("🔍 모요 스크래핑 시작 (HTML 파싱)...")
        
        all_plans = []
        seen_ids = set()
        consecutive_empty = 0
        screenshot_path = None
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for page_num in range(1, self.max_pages + 1):
                print(f"\n📄 페이지 {page_num} 로딩...")
                
                if page_num == 1:
                    url = self.base_url
                else:
                    url = f"{self.base_url}?page={page_num}"
                
                try:
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')
                    page.wait_for_timeout(1000)  # 1초로 단축
                    
                    # 스크린샷 (첫 페이지만)
                    if page_num == 1:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        screenshot_path = f"/tmp/moyo_{timestamp}.png"
                        page.screenshot(path=screenshot_path)
                    
                    # 페이지 전체 HTML 가져오기
                    html_content = page.content()
                    
                    # /plans/숫자 패턴으로 plan ID 추출
                    plan_id_pattern = r'/plans/(\d+)'
                    found_ids = re.findall(plan_id_pattern, html_content)
                    
                    if not found_ids:
                        print(f"   ⚠️ 요금제를 찾을 수 없음")
                        consecutive_empty += 1
                        if consecutive_empty >= self.empty_page_threshold:
                            print(f"🛑 연속 {consecutive_empty}페이지 실패 - 중단")
                            break
                        continue
                    
                    # 중복 제거된 ID 리스트
                    unique_ids = []
                    for pid in found_ids:
                        if pid not in seen_ids:
                            unique_ids.append(pid)
                            seen_ids.add(pid)
                    
                    if not unique_ids:
                        print(f"   ℹ️ 신규 0개 (총 {len(all_plans)}개)")
                        consecutive_empty += 1
                        if consecutive_empty >= self.empty_page_threshold:
                            print(f"🛑 연속 {consecutive_empty}페이지 신규 없음 - 중단")
                            break
                        continue
                    
                    # 각 plan ID에 대해 상세 정보 추출
                    new_count = 0
                    failed_ids = []  # 파싱 실패한 ID 추적
                    
                    for plan_id in unique_ids:
                        try:
                            # 해당 plan 링크 찾기
                            link_selector = f'a[href="/plans/{plan_id}"]'
                            links = page.locator(link_selector).all()
                            
                            if not links:
                                failed_ids.append((plan_id, "링크 없음"))
                                continue
                            
                            # 첫 번째 링크 사용 (보통 카드 전체를 감싸는 링크)
                            main_link = links[0]
                            
                            # 링크 전체 텍스트
                            text = main_link.inner_text()
                            
                            # 기본 정보 파싱
                            lines = [l.strip() for l in text.split('\n') if l.strip()]
                            
                            if len(lines) < 3:
                                failed_ids.append((plan_id, "텍스트 부족"))
                                continue
                            
                            # 공급사 (첫 줄에서 추출 - 숫자가 아닌 것)
                            provider = "Unknown"
                            for line in lines:
                                if line and not line[0].isdigit() and len(line) > 1:
                                    provider = line
                                    break
                            
                            # 요금제명 찾기 - 더 관대하게
                            name = None
                            data_info = None
                            price_info = None
                            subscriber_info = None
                            
                            for line in lines:
                                if 'GB' in line or 'Mbps' in line:
                                    if not data_info:
                                        data_info = line
                                elif '원' in line:
                                    if not price_info:
                                        price_info = line
                                elif '명' in line or '선택' in line:
                                    subscriber_info = line
                                elif not name and len(line) > 3:
                                    # 특수 패턴 제외
                                    if '통화' not in line and '문자' not in line and '망' not in line:
                                        if provider not in line or len(line) > len(provider) + 5:
                                            name = line
                            
                            # 최소 정보: plan_id만 있어도 저장
                            if not name:
                                name = f"요금제 {plan_id}"  # 기본 이름 부여
                                failed_ids.append((plan_id, "이름 자동생성"))
                            
                            # 가격 파싱 - 더 관대하게
                            price_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*원', text)
                            final_price = 0
                            if price_match:
                                final_price = int(price_match.group(1).replace(',', ''))
                            
                            base_price_match = re.search(r'이후\s+(\d{1,3}(?:,\d{3})*)\s*원', text)
                            base_price = final_price
                            if base_price_match:
                                base_price = int(base_price_match.group(1).replace(',', ''))
                            
                            # 할인 개월 수
                            discount_months = 7  # 기본값
                            month_match = re.search(r'(\d+)개월', text)
                            if month_match:
                                discount_months = int(month_match.group(1))
                            
                            # 데이터 파싱 - 더 관대하게
                            data_gb = 0
                            data_str = "Unknown"
                            if data_info:
                                data_str = data_info
                                # 모든 GB 패턴 찾기
                                gb_matches = re.findall(r'(\d+)\s*GB', data_info)
                                if gb_matches:
                                    data_gb = int(gb_matches[0])
                            else:
                                # 전체 텍스트에서 데이터 찾기
                                gb_matches = re.findall(r'(\d+)\s*GB', text)
                                if gb_matches:
                                    data_gb = int(gb_matches[0])
                                    data_str = f"{data_gb}GB"
                            
                            # 가입자 수 - 더 관대하게
                            subscribers = 0
                            if subscriber_info:
                                sub_match = re.search(r'([\d,]+)\s*명', subscriber_info)
                                if sub_match:
                                    subscribers = int(sub_match.group(1).replace(',', ''))
                            else:
                                # 전체 텍스트에서 찾기
                                sub_match = re.search(r'([\d,]+)\s*명', text)
                                if sub_match:
                                    subscribers = int(sub_match.group(1).replace(',', ''))
                            
                            # 통신망 추정 (텍스트에서)
                            network = 'Unknown'
                            if 'SKT' in text or 'SK텔레콤' in text:
                                network = 'SKT'
                            elif 'KT' in text:
                                network = 'KT'
                            elif 'LG' in text or 'U+' in text:
                                network = 'LGU+'
                            
                            plan = {
                                'source_platform': 'moyo',
                                'provider': provider,
                                'network': network,
                                'display_name': f"{network[0] if network != 'Unknown' else '?'}({provider})",
                                'is_competitor': network in ['KT', 'LGU+'],
                                'name': name,
                                'data': data_str,
                                'data_gb': data_gb,
                                'base_price': base_price,
                                'final_price': final_price,
                                'monthly_discount': base_price - final_price,
                                'discount_months': discount_months,
                                'total_support': (base_price - final_price) * discount_months,
                                'subscribers': subscribers,
                                'plan_id': plan_id,
                            }
                            
                            all_plans.append(plan)
                            new_count += 1
                            
                        except Exception as e:
                            # 파싱 실패해도 계속 진행
                            failed_ids.append((plan_id, f"에러: {str(e)[:30]}"))
                            continue
                    
                    # 실패한 케이스 출력 (처음 3개만)
                    if failed_ids and page_num <= 5:
                        print(f"   ⚠️ 파싱 실패 예시: {failed_ids[:3]}")
                    
                    print(f"   ✅ 신규 {new_count}개 (총 {len(all_plans)}개)")
                    consecutive_empty = 0
                    
                except Exception as e:
                    print(f"   ⚠️ 에러: {e}")
                    consecutive_empty += 1
                    if consecutive_empty >= self.empty_page_threshold:
                        break
                    continue
            
            browser.close()
        
        print(f"\n✅ {len(all_plans)}개 수집 완료")
        return all_plans, screenshot_path or "/tmp/moyo_empty.png"

if __name__ == '__main__':
    print("=" * 50)
    print("모요 스크래퍼 테스트 (HTML 파싱)")
    print("=" * 50)
    
    scraper = MoyoScraper()
    plans, screenshot = scraper.scrape()
    
    print(f"\n📊 총 {len(plans)}개 요금제")
    
    if plans:
        print("\n처음 5개:")
        for i, p in enumerate(plans[:5], 1):
            print(f"\n[{i}] {p['display_name']}")
            print(f"    요금제: {p['name']}")
            print(f"    데이터: {p['data']}")
            print(f"    가격: {p['final_price']:,}원 (정가: {p['base_price']:,}원)")
            print(f"    총 지원금: {p['total_support']:,}원")
            print(f"    선택한 사람: {p['subscribers']:,}명")
        
        comp = [p for p in plans if p['is_competitor']]
        skt = [p for p in plans if not p['is_competitor']]
        
        print(f"\n📈 통계:")
        print(f"    전체: {len(plans)}개")
        print(f"    경쟁사(KT/LG): {len(comp)}개")
        print(f"    우리편(SKT): {len(skt)}개")
        
        with_subs = [p for p in plans if p['subscribers'] > 0]
        if with_subs:
            avg_subs = sum(p['subscribers'] for p in with_subs) / len(with_subs)
            max_subs = max(p['subscribers'] for p in with_subs)
            print(f"\n👥 가입자 통계:")
            print(f"    가입자 정보 있는 요금제: {len(with_subs)}개")
            print(f"    평균 가입자: {avg_subs:,.0f}명")
            print(f"    최대 가입자: {max_subs:,}명")
    else:
        print("\n❌ 요금제를 찾지 못했습니다")
    
    print(f"\n📸 스크린샷: {screenshot}")
    print("\n" + "=" * 50)