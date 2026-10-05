#!/bin/bash
# backfill_test.sh v1.1
# 2026-05-01 ~ 2026-05-19 context 생성 + 메일 발송 테스트

echo "================================================"
echo " MVNO Daily Context Backfill + Mail Test"
echo " 기간: 2026-05-01 ~ 2026-05-19"
echo "================================================"

python3 - << 'PYEOF'
import subprocess
import sys
from datetime import datetime, timedelta

start = datetime(2026, 5, 1)
end   = datetime(2026, 5, 19)
cur   = start

while cur <= end:
    date_str = cur.strftime('%Y-%m-%d')
    print(f"\n{'─'*40}")
    print(f"📅 처리 중: {date_str}")
    print(f"{'─'*40}")

    # 1. ktoa_context backfill
    print("[1/3] ktoa_context 생성...")
    r1 = subprocess.run(
        ['python3', '-c',
         f"from ktoa_context_builder import backfill_context; backfill_context('{date_str}', '{date_str}')"],
        capture_output=True, text=True
    )
    print(r1.stdout[-300:] if r1.stdout else "(출력 없음)")
    if r1.stderr: print("STDERR:", r1.stderr[-200:])

    # 2. youtube_context 생성
    print("[2/3] youtube_context 생성...")
    r2 = subprocess.run(
        ['python3', 'youtube_context_builder.py', date_str],
        capture_output=True, text=True
    )
    print(r2.stdout[-300:] if r2.stdout else "(출력 없음)")
    if r2.stderr: print("STDERR:", r2.stderr[-200:])

    # 3. 메일 발송
    print("[3/3] 메일 발송...")
    r3 = subprocess.run(
        ['python3', 'daily_mailer.py', date_str],
        capture_output=True, text=True
    )
    print(r3.stdout[-400:] if r3.stdout else "(출력 없음)")
    if r3.stderr: print("STDERR:", r3.stderr[-200:])

    print(f"✅ {date_str} 완료")

    import time
    time.sleep(2)
    cur += timedelta(days=1)

print("\n================================================")
print(" ✅ Backfill 완료: 2026-05-01 ~ 2026-05-19")
print("================================================")
PYEOF