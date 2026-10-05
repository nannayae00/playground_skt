#!/bin/bash
# 4개 파일에 이번 변경사항이 제대로 반영됐는지 확인
cd ~/price-monitor

echo "=== 1) scrapers/gift_ktm_event_scraper.py ==="
[ -f scrapers/gift_ktm_event_scraper.py ] && echo "✅ 파일 존재" || echo "❌ 파일 없음"
grep -q "ktm_image_cache" scrapers/gift_ktm_event_scraper.py && echo "✅ 이미지 전역 캐시 있음" || echo "❌ 이미지 전역 캐시 없음"
grep -q "google.genai" scrapers/gift_ktm_event_scraper.py && echo "✅ google.genai 사용" || echo "❌ google.genai 없음"
echo ""

echo "=== 2) gift_job.py ==="
grep -q "scrape_ktm_with_cache" gift_job.py && echo "✅ KT 스크래퍼 import 있음" || echo "❌ import 없음"
grep -q "format_moyo_vs_direct_multi" gift_job.py && echo "✅ 3자 비교 함수 사용" || echo "❌ 3자 비교 함수 없음"
grep -q "_save_ktm_detail" gift_job.py && echo "✅ KT 상세 저장 함수 있음" || echo "❌ 없음"
echo ""

echo "=== 3) core/gift_comparator.py ==="
grep -q "def format_moyo_vs_direct_multi" core/gift_comparator.py && echo "✅ 3자 비교 함수 정의됨" || echo "❌ 없음"
grep -q "gap_threshold: int = 100000" core/gift_comparator.py && echo "✅ 10만원 임계값 반영" || echo "❌ 임계값 반영 안됨"
echo ""

echo "=== 4) gift_callback_handler.py ==="
grep -q "'ktm':.*'KT엠모바일(모요)'" gift_callback_handler.py && echo "✅ ktm 라벨 수정됨" || echo "❌ ktm 라벨 그대로"
grep -q "'ktm_direct'" gift_callback_handler.py && echo "✅ ktm_direct 라벨 추가됨" || echo "❌ ktm_direct 라벨 없음"
echo ""

echo "=== 5) 문법 오류 체크 (import까진 안 가고 컴파일만) ==="
python3 -m py_compile scrapers/gift_ktm_event_scraper.py && echo "✅ gift_ktm_event_scraper.py 문법 OK" || echo "❌ 문법 오류"
python3 -m py_compile gift_job.py && echo "✅ gift_job.py 문법 OK" || echo "❌ 문법 오류"
python3 -m py_compile core/gift_comparator.py && echo "✅ gift_comparator.py 문법 OK" || echo "❌ 문법 오류"
python3 -m py_compile gift_callback_handler.py && echo "✅ gift_callback_handler.py 문법 OK" || echo "❌ 문법 오류"