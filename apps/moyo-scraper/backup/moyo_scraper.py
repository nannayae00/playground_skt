from playwright.async_api import async_playwright
from datetime import datetime
import re
import asyncio

class MoyoScraper:
    def __init__(self, progress_callback=None):
        self.base_url = "https://www.moyoplan.com/plans"
        self.max_pages = 250
        self.empty_page_threshold = 3
        self.progress_callback = progress_callback
    
    def scrape(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._scrape_async())
        finally:
            loop.close()
    
    async def _scrape_async(self):
        print("🔍 모요 스크래핑 시작...")
        all_plans = []
        seen_ids = set()
        consecutive_empty = 0
        screenshot_path = None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-gpu',
                        '--single-process',
                        '--no-zygote',
                        '--disable-dev-shm-usage',
                        '--remote-debugging-port=0'
                ]
            )
            page = await browser.new_page()
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'ko-KR,ko;q=0.9',
            })
            
            for page_num in range(1, self.max_pages + 1):
                print(f"\n📄 페이지 {page_num} 로딩...")
                url = self.base_url if page_num == 1 else f"{self.base_url}?page={page_num}"
                
                try:
                    await page.goto(url, timeout=120000, wait_until='commit')

                    await page.wait_for_timeout(1000)
                    
                    if page_num == 1:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        screenshot_path = f"/tmp/moyo_{timestamp}.png"
                        await page.screenshot(path=screenshot_path)
                    
                    html_content = await page.content()
                    found_ids = re.findall(r'/plans/(\d+)', html_content)
                    
                    if not found_ids:
                        print(f"   ⚠️ 요금제를 찾을 수 없음")
                        consecutive_empty += 1
                        if consecutive_empty >= self.empty_page_threshold:
                            print(f"🛑 연속 {consecutive_empty}페이지 실패 - 중단")
                            break
                        continue
                    
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
                    
                    new_count = 0
                    failed_ids = []
                    
                    for plan_id in unique_ids:
                        try:
                            link_selector = f'a[href="/plans/{plan_id}"]'
                            links = await page.locator(link_selector).all()
                            
                            if not links:
                                failed_ids.append((plan_id, "링크 없음"))
                                continue
                            
                            text = await links[0].inner_text()
                            lines = [l.strip() for l in text.split('\n') if l.strip()]
                            
                            if len(lines) < 3:
                                failed_ids.append((plan_id, "텍스트 부족"))
                                continue
                            
                            provider = "Unknown"
                            for line in lines:
                                if line and not line[0].isdigit() and len(line) > 1:
                                    provider = line
                                    break
                            
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
                                    if '통화' not in line and '문자' not in line and '망' not in line:
                                        if provider not in line or len(line) > len(provider) + 5:
                                            name = line
                            
                            if not name:
                                name = f"요금제 {plan_id}"
                            
                            price_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*원', text)
                            final_price = int(price_match.group(1).replace(',', '')) if price_match else 0
                            
                            base_price_match = re.search(r'이후\s+(\d{1,3}(?:,\d{3})*)\s*원', text)
                            base_price = int(base_price_match.group(1).replace(',', '')) if base_price_match else final_price
                            
                            month_match = re.search(r'(\d+)개월', text)
                            discount_months = int(month_match.group(1)) if month_match else 7
                            
                            data_gb = 0
                            data_str = "Unknown"
                            if data_info:
                                data_str = data_info
                                gb_matches = re.findall(r'(\d+)\s*GB', data_info)
                                if gb_matches:
                                    data_gb = int(gb_matches[0])
                            else:
                                gb_matches = re.findall(r'(\d+)\s*GB', text)
                                if gb_matches:
                                    data_gb = int(gb_matches[0])
                                    data_str = f"{data_gb}GB"
                            
                            subscribers = 0
                            src = subscriber_info if subscriber_info else text
                            sub_match = re.search(r'([\d,]+)\s*명', src)
                            if sub_match:
                                subscribers = int(sub_match.group(1).replace(',', ''))
                            
                            network = 'Unknown'
                            if 'SKT' in text or 'SK텔레콤' in text:
                                network = 'SKT'
                            elif 'KT' in text:
                                network = 'KT'
                            elif 'LG' in text or 'U+' in text:
                                network = 'LGU+'
                            
                            all_plans.append({
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
                            })
                            new_count += 1
                            
                        except Exception as e:
                            failed_ids.append((plan_id, f"에러: {str(e)[:30]}"))
                            continue
                    
                    if failed_ids and page_num <= 5:
                        print(f"   ⚠️ 파싱 실패 예시: {failed_ids[:3]}")
                    
                    print(f"   ✅ 신규 {new_count}개 (총 {len(all_plans)}개)")
                    
                    if self.progress_callback and len(all_plans) % 100 == 0 and len(all_plans) > 0:
                        self.progress_callback(f"📦 수집 중... {len(all_plans)}개 (페이지 {page_num})")
                    
                    consecutive_empty = 0
                    
                except Exception as e:
                    print(f"   ⚠️ 에러: {e}")
                    consecutive_empty += 1
                    if consecutive_empty >= self.empty_page_threshold:
                        break
                    continue
            
            await browser.close()
        
        print(f"\n✅ {len(all_plans)}개 수집 완료")
        return all_plans, screenshot_path or "/tmp/moyo_empty.png"


if __name__ == '__main__':
    scraper = MoyoScraper()
    plans, screenshot = scraper.scrape()
    print(f"\n📊 총 {len(plans)}개 요금제")
