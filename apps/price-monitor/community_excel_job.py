"""
community_excel_job.py
──────────────────────────────────────────────────────────────────────────────
커뮤니티 동향 엑셀 전용 Cloud Run Job
- Firestore에서 뽐뿌/디씨/유튜브 데이터 조회
- 엑셀 생성 후 텔레그램 전송
- main.py의 background thread 방식 대체 (컨테이너 idle 종료 문제 해결)

환경변수:
  TELEGRAM_BOT_TOKEN : 텔레그램 봇 토큰
  REQUESTER_CHAT_ID  : 엑셀 파일 전송 대상 채팅방 ID
  EXCEL_DAYS         : 조회 기간 (기본: 30)

[수정 이력]
v1.0 | 2026-04-23 | 최초 작성 (main.py background thread에서 Job으로 분리)
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import traceback
from datetime import datetime
import pytz

KOREA_TZ  = pytz.timezone('Asia/Seoul')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = os.getenv('REQUESTER_CHAT_ID', '')
DAYS      = int(os.getenv('EXCEL_DAYS', '30'))


def log(msg):
    print(f"[{datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main():
    log(f"🚀 커뮤니티 엑셀 Job 시작 (chat_id={CHAT_ID}, days={DAYS})")

    if not BOT_TOKEN or not CHAT_ID:
        log("❌ TELEGRAM_BOT_TOKEN 또는 REQUESTER_CHAT_ID 미설정")
        sys.exit(1)

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from excel_exporter import run_excel_export
        run_excel_export(BOT_TOKEN, CHAT_ID, days=DAYS)
        log("✅ 커뮤니티 엑셀 Job 완료")
    except Exception as e:
        log(f"❌ 커뮤니티 엑셀 Job 에러: {e}")
        log(traceback.format_exc())
        # 에러 알림
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": f"❌ 엑셀 생성 실패: {e}"},
                timeout=10
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()