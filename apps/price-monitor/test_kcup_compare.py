# -*- coding: utf-8 -*-
"""
test_kcup_compare.py - compare_kcup() 실데이터 테스트
gift_job.py와 동일 환경(GCP Cloud Shell, GEMINI_API_KEY/Firestore 인증 설정된 상태)에서 실행.

사용법:
  python3 test_kcup_compare.py            # KT엠모바일만
  python3 test_kcup_compare.py --all      # KT엠모바일 + U+유모바일 둘 다
"""

import os
import sys
import io
import time
import requests
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

from scrapers.gift_moyo_scraper import scrape_moyo_gifts
from scrapers.gift_ktm_event_scraper import scrape_with_cache as scrape_ktm
from scrapers.gift_umobile_event_scraper import scrape_with_cache as scrape_umobile
from core.gift_comparator import compare_kcup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GIFT_CHANNEL_ID = os.environ.get("GIFT_CHANNEL_ID", "")  # 세미콜론으로 여러 채널 구분 가능


def send_telegram(messages: list):
    """
    메시지 리스트를 건별로 하나씩 텔레그램에 발송 (합쳐서 보내지 않음).
    GIFT_CHANNEL_ID가 'chatid1;chatid2' 형태면 두 채널 모두에 발송.
    """
    if not TELEGRAM_TOKEN or not GIFT_CHANNEL_ID:
        print("⚠️ TELEGRAM_TOKEN/GIFT_CHANNEL_ID 없음 - 발송 스킵")
        return

    chat_ids = [c.strip() for c in GIFT_CHANNEL_ID.split(";") if c.strip()]
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    sent = 0
    for msg in messages:
        for chat_id in chat_ids:
            try:
                r = requests.post(url, json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }, timeout=15)
                if r.status_code == 200:
                    sent += 1
                else:
                    print(f"  ⚠️ 발송 실패 (chat_id={chat_id}): {r.status_code} {r.text[:200]}")
            except Exception as e:
                print(f"  ⚠️ 발송 예외 (chat_id={chat_id}): {e}")
            time.sleep(0.3)  # 텔레그램 rate limit 여유
    print(f"📨 텔레그램 발송 완료: {sent}건 (메시지 {len(messages)}건 × 채널 {len(chat_ids)}개)")

db = firestore.Client(database="mvno-data")  # (default) DB엔 event_cache가 없고 mvno-data에 있는 것으로 확인됨


class _Tee(io.TextIOBase):
    """print() 출력을 화면 + 파일 양쪽에 동시에 쓰기 위한 스트림 래퍼"""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def load_cached_posts(db, collection_name: str) -> list:
    """
    scrape_with_cache()를 호출하지 않고, 이미 Firestore에 캐싱된 이벤트만 그대로 읽어옴.
    Vision/Playwright 전혀 호출하지 않으므로 비용/시간 0에 가까움 - 신규 이벤트가 있어도 스킵됨.
    (ktm_event_cache / umobile_event_cache 컬렉션 문서 스키마: post_id/url/title/date_start/date_end/plans)

    캐시 테이블엔 이미 종료된 이벤트도 정리 안 되고 남아있으므로, date_end가 오늘(KST) 이전인
    문서는 제외한다 (실제 사이트 라이브 수집이라면 종료된 이벤트는 목록에 애초에 안 나옴).
    date_end가 없거나 형식이 안 맞아 파싱 실패하면, 잘못 걸러내는 것보다 안전하게 포함시킨다.
    """
    from datetime import date as _date

    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).date()

    posts, skipped_expired = [], 0
    for doc in db.collection(collection_name).stream():
        d = doc.to_dict()
        if not d.get("plans"):
            continue
        date_end = d.get("date_end", "")
        try:
            if date_end and _date.fromisoformat(date_end[:10]) < today:
                skipped_expired += 1
                continue
        except ValueError:
            pass  # 파싱 실패 시 안전하게 포함
        posts.append(d)

    if skipped_expired:
        print(f"  (종료된 이벤트 {skipped_expired}건 제외)")
    return posts


def run(live: bool = False, max_posts: int = 5):
    print("=" * 60)
    print("STEP 1: 모요 전체 수집 (KT/LG 자회사)")
    print("=" * 60)
    moyo_plans = scrape_moyo_gifts()
    print(f"모요 수집 완료: {len(moyo_plans)}건\n")

    mode_label = f"라이브 수집 (신규 이벤트는 Vision 실제 호출, max_posts={max_posts})" \
                 if live else "Firestore 캐시만 읽기 (신규 파싱 없음)"

    print("=" * 60)
    print(f"STEP 2: KT엠모바일 - {mode_label}")
    print("=" * 60)
    if live:
        ktm_posts = scrape_ktm(db, max_posts=max_posts)
    else:
        ktm_posts = load_cached_posts(db, "ktm_event_cache")
    print(f"KT엠모바일 이벤트: {len(ktm_posts)}건\n")

    print("=" * 60)
    print("STEP 3: compare_kcup() - KT엠모바일")
    print("=" * 60)
    ktm_msgs = compare_kcup(moyo_plans, ktm_posts,
                            moyo_provider='KT엠모바일',
                            direct_label='KT엠모바일 직영')
    print(f"생성된 특이사항 메시지: {len(ktm_msgs)}건\n")
    for m in ktm_msgs:
        print(m)
        print("-" * 40)

    all_msgs = list(ktm_msgs)

    if "--all" in sys.argv:
        print("=" * 60)
        print(f"STEP 4: U+유모바일 - {mode_label}")
        print("=" * 60)
        if live:
            umobile_posts = scrape_umobile(db, max_posts=max_posts)
        else:
            umobile_posts = load_cached_posts(db, "umobile_event_cache")
        print(f"U+유모바일 이벤트: {len(umobile_posts)}건\n")
        umobile_msgs = compare_kcup(moyo_plans, umobile_posts,
                                    moyo_provider='U+유모바일',
                                    direct_label='U+유모바일 직영')
        print(f"생성된 특이사항 메시지: {len(umobile_msgs)}건\n")
        for m in umobile_msgs:
            print(m)
            print("-" * 40)
        all_msgs += umobile_msgs

    print("=" * 60)
    print(f"총 특이사항: {len(all_msgs)}건")
    print("=" * 60)

    if "--send" in sys.argv:
        print()
        send_telegram(all_msgs)
    else:
        print("\n(--send 옵션 없어서 실제 발송은 안 함 - 위 메시지 확인 후 --send 붙여서 재실행)")

    return all_msgs


if __name__ == "__main__":
    KST = timezone(timedelta(hours=9))
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    log_path = f"kcup_test_{ts}.log"

    real_stdout = sys.stdout
    with open(log_path, "w", encoding="utf-8") as f:
        sys.stdout = _Tee(real_stdout, f)
        try:
            run(live=("--live" in sys.argv), max_posts=5)
        finally:
            sys.stdout = real_stdout

    print(f"\n📄 로그 저장 완료: {log_path}  (현재 디렉토리 기준)")