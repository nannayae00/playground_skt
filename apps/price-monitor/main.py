"""
main.py  v4.19
수정일시: 2026-07-09

[v4.19 / 2026-07-09]
- 사은품 버튼 callback_query 처리 추가 (gift_callback_handler.py)

[v4.18 / 2026-05-21]
- /run_daily_mailer 엔드포인트 추가 (Cloud Scheduler 20:40 호출용)

[v4.17 / 2026-05-21]
- /run_youtube_context 엔드포인트 추가 (Cloud Scheduler 20:10 호출용)
  · youtube_context_builder.save_youtube_context() 백그라운드 실행

[v4.16 / 2026-04-23]
- 엑셀 명령어: build_excel() 시그니처 변경 대응 (aldot_plans=[], mvnohub_plans=[] 추가)
- 도움말: 모요 확인 소요시간 45분 → 50분 업데이트

[v4.15 / 2026-04-23]
- "커뮤니티 동향" 처리 방식 변경: background thread → Cloud Run Job
  · background thread는 컨테이너 idle 시 강제 종료되는 문제 해결
  · trigger_excel_job() 함수 추가: community-excel-job 트리거
  · REQUESTER_CHAT_ID, EXCEL_DAYS 환경변수로 chat_id/기간 전달

[v4.14 / 2026-04-13]
- "동향 요약" 명령어 추가: 뽐뿌/디씨/유튜브 통합 엑셀 파일 전송
  · excel_exporter.run_excel_export() 호출 (background thread)
  · 기존 "엑셀" 키워드(모요 요금제 엑셀)와 충돌 방지를 위해 앞에 배치

[v4.13 / 2026-04-09]
- 알닷 확인 명령어 추가: 알닷만 수집 (SCRAPE_TYPE=aldot)
- trigger_scrape_job에 scrape_type 파라미터 추가
- 도움말 업데이트: 모요 확인/알닷 확인 소요시간 안내

[v4.12 변경사항]
- 최신분석/RS/RM reply: parse_mode="Markdown" 명시 → 코드블록 정상 렌더링

[v4.11]
- RS 명령어: 최신분석 포맷 + RS 가입수 Top5 통합
- main.py build_excel 제거 → scrape_job.py import로 통일
- 수동수집 결과: scrape_job send_result/send_file 수동 전송 보장

[v4.10]
- 최신분석 블록: build_guide_comparison, build_summary_table, build_excel import 누락 수정 (NameError 해결)

[v4.9]
- RM 명령어 추가: 가격대별 최대 데이터 + 가입수 Top 5 (전주 대비 증감)
- 엑셀 RM Top5 시트 추가
- 엑셀 전체요금제 시트에 가이드이하(◎) 필드 추가

[v4.8]
- 최신분석: 헤더(📋 수집 시각) + RS표 + 가이드 포함으로 통일
- build_excel: RS 망별 최저가 시트 추가 (최저가 빨간 굵게 표시)

[v4.7]
- 가이드 날짜 입력 정규식 버그 수정 (3/1 등 정상 인식)
- 가이드 확인: guide_date 필드 우선 표시 (기존 updated_at 사용 버그 수정)

[v4.6]
- 모요 인기 명령어 추가: 3사별 가입자수 Top 5
- RS 명령어 추가: 가격대별 최대 데이터 + RS 가입수 Top 5
- 도움말 업데이트

[v4.5]
- 도움말 내용 전면 개편: 수집/조회/가이드 섹션 분리, 각 기능 설명 추가
- 트리거 키워드 추가: 도움말, 도와줘

[v4.4]
- build_summary_table: 🔥 → * 변경, 3사 동일 최저가면 미표기
- 가이드 변경: 금액 입력 후 기준 날짜 추가 입력 (예: 3/1)

[v4.3]
- build_summary_table: 🔥 복원, 3사 동일 최저가면 미표기

[v4.2]
- 가이드 금액 입력/저장/확인 기능 추가
  · '가이드 변경' → 구간별 금액 순차 입력 → Firebase 저장
  · '가이드 확인' → 저장된 가이드 금액 조회
  · 입력 대화 상태 관리 구조 개선 (state 기반)

[v4.1]
- build_summary_table: RS만 표시 (RM 제거)
- 테이블 정렬 개선: 코드블록 + * 기호로 구간 최저가 표시

[v4.0]
- 채팅방별 응답 분리
  · CHAT_LOG (로그방): 진행상황 + 결과 모두 수신
  · 요청한 방: 결과만 수신 (진행상황 미출력)
  · 자동 스케줄링 결과는 별도 방으로 발송 예정
- 모요 확인 날짜 대화 추가
  · "모요 확인" 입력 시 → 몇 일치 할지 질문 → 사용자 입력 받아 수집
- send_to(chat_id, text) 함수 추가 (특정 방 지정 발송)
- trigger_scrape_job에 days 파라미터 추가
- trigger_ppomppu_job에 requester_chat_id 파라미터 추가
- 뽐뿌 Cloud Run Job 구조로 변경 (컨테이너 강제종료 문제 해결)

[이전 버전]
- v3.6: 뽐뿌 중복 실행 방지 + fire-and-forget 구조로 OOM 해결
- v3.5: 뽐뿌 MVNO 모니터링 추가
- v3.0: RS/RM 분리 최신분석 표, Cloud Run Job 트리거 방식으로 변경
"""

from flask import Flask, request, jsonify
import threading
from datetime import datetime
import requests
import os
import traceback
import pytz

try:
    import pandas as pd
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

from scrapers.moyo_scraper import MoyoScraper
from core.firebase_handler import FirebaseHandler
from core.comparator import Comparator

app      = Flask(__name__)
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
KOREA_TZ  = pytz.timezone('Asia/Seoul')

# ── 채팅방 ID 설정 ────────────────────────────────────────────────────────────
CHAT_LOG      = os.getenv('TELEGRAM_CHAT_ID', '-5281356843')   # 로그방 (기존)
CHAT_PPOMPPU  = '-5107871044'    # 뽐뿌 자동결과방
CHAT_MOYO     = '-1003843687198' # 모요 자동결과방

# 대화 상태 저장
# 'ppomppu'       : 뽐뿌 days 입력 대기
# 'guide_7G+'     : 가이드 7G+ 입력 대기
# 'guide_10G+'    : 가이드 10G+ 입력 대기 ... 등
_moyo_waiting = {}



# ── 유틸 ──────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def get_korea_time():
    return datetime.now(KOREA_TZ)

def send_to(chat_id, text, parse_mode="HTML"):
    """특정 채팅방에 메시지 발송"""
    if not BOT_TOKEN or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                  "disable_web_page_preview": True},
            timeout=60
        )
        return r.status_code == 200
    except Exception as e:
        log(f"❌ 텔레그램 전송 에러: {e}")
        return False

def send_telegram(text, parse_mode="Markdown"):
    """로그방에 메시지 발송 (기존 호환용)"""
    return send_to(CHAT_LOG, text, parse_mode)

def send_telegram_file(file_path, caption, chat_id=None):
    target = chat_id or CHAT_LOG
    if not BOT_TOKEN or not target:
        return False
    try:
        with open(file_path, 'rb') as f:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={'chat_id': target, 'caption': caption},
                files={'document': f},
                timeout=60
            )
        return r.status_code == 200
    except Exception as e:
        log(f"❌ 파일 전송 에러: {e}")
        return False


# ── Firestore 헬퍼 ────────────────────────────────────────────────────────────

def _safe_plans(raw_data) -> list:
    if not raw_data: return []
    plans = raw_data.get('plans', [])
    if isinstance(plans, list):   return plans
    if isinstance(plans, dict):   return list(plans.values())
    return []

def get_latest_analysis():
    try:
        db     = FirebaseHandler()
        latest = db.get_latest_data('moyo')
        if not latest: return None
        plans      = _safe_plans(latest)
        checked_at = latest.get('checked_at')
        korea_time = (checked_at.astimezone(KOREA_TZ)
                      if hasattr(checked_at, 'astimezone') else get_korea_time())
        return {'checked_at': korea_time, 'total_plans': len(plans), 'plans': plans}
    except Exception as e:
        log(f"❌ get_latest_analysis 에러: {e}")
        return None


# ── 엑셀 ──────────────────────────────────────────────────────────────────────

EXCEL_COLS = [
    ('_no',               'No',          5),
    ('provider',          '알뜰폰사업자', 14),
    ('name',              '요금제명',    24),
    ('data',              '데이터',       9),
    ('segment',           '구간',         9),
    ('is_rs',             'RS여부',       8),
    ('is_lowest_rs',      'RS최저가',     9),
    ('is_lowest_rm',      'RM최저가',     9),
    ('voice',             '통화',        10),
    ('sms',               '문자',        10),
    ('network',           '사용망',       8),
    ('network_generation','네트워크',     9),
    ('final_price',       '할인후금액',  12),
    ('discount_months',   '할인개월',    10),
    ('base_price',        '할인전금액',  12),
    ('subscribers',       '가입자수',    10),
    ('guide_below',       '가이드이하',  10),
]

# build_excel → scrape_job.py에서 import하여 사용


# ── 분석 표 (RS/RM 분리) ──────────────────────────────────────────────────────

def build_summary_table(curr_plans, prev_plans):
    comp       = Comparator()
    prev_rs    = comp.get_segment_min_prices(prev_plans, rs_only=True) if prev_plans else {}
    curr_rs    = comp.get_segment_min_prices(curr_plans, rs_only=True)
    changes_rs = comp.analyze_changes(curr_rs, prev_rs)

    NETS = ['SKT', 'KT', 'LGU+']

    def fmt(v, is_min):
        if not v: return '     - '
        num = f'{v:,}'
        return (num + '*').rjust(8) if is_min else (num + ' ').rjust(8)

    def arrow(d):
        if d < 0: return f"({abs(d):,}↓)".rjust(8)
        if d > 0: return f"({d:,}↑)".rjust(8)
        return ' ' * 8

    def tbl(label, summary, changes):
        msg  = f"📊 {label} 망별 최저가\n```\n"
        msg += f"{'구간':<8}│{'SKT':>8} │{'KT':>8} │{'LGU+':>8}\n"
        msg += "─" * 38 + "\n"
        for seg, nets in summary.items():
            prices    = {n: nets.get(n, 0) for n in NETS}
            min_val   = min((v for v in prices.values() if v > 0), default=0)
            min_count = sum(1 for v in prices.values() if v == min_val and v > 0)
            cells = [fmt(prices[n], prices[n] == min_val and min_val > 0 and min_count < 3)
                     for n in NETS]
            msg += f"{seg:<8}│{cells[0]} │{cells[1]} │{cells[2]}\n"
            ds  = changes.get(seg, {})
            row = [arrow(ds.get(n, 0)) for n in NETS]
            if any(x.strip() for x in row):
                msg += f"{'':8}│{row[0]} │{row[1]} │{row[2]}\n"
        msg += "* 구간최저(2사이하) / ↓하락 / ↑상승\n```"
        return msg

    return tbl("RS", curr_rs, changes_rs)


# ── 요금제별 변경 내역 ────────────────────────────────────────────────────────

def build_plan_changes(curr_plans, prev_plans, recent_ids=None):
    if not prev_plans:
        return ""

    prev_by_id   = {p.get('plan_id'): p for p in prev_plans if p.get('plan_id')}
    curr_by_id   = {p.get('plan_id'): p for p in curr_plans if p.get('plan_id')}
    prev_by_name = {(p.get('provider','')+'|'+p.get('name','')): p for p in prev_plans}

    prev_ids = set(prev_by_id.keys())
    curr_ids = set(curr_by_id.keys())

    down, up, new_plans, removed, surged = [], [], [], [], []

    SURGE_RATE = 0.20
    SURGE_MIN  = 500

    for p in curr_plans:
        pid  = p.get('plan_id')
        key  = p.get('provider','')+'|'+p.get('name','')
        prev = prev_by_id.get(pid) or prev_by_name.get(key)
        if not prev:
            if recent_ids and pid in recent_ids:
                continue
            new_plans.append(p)
            continue
        diff = p.get('final_price',0) - prev.get('final_price',0)
        if diff < 0:
            down.append((p, diff))
        elif diff > 0:
            up.append((p, diff))
        pcount, count = prev.get('subscribers',0), p.get('subscribers',0)
        if count > pcount:
            delta = count - pcount
            if delta >= SURGE_MIN or (pcount > 0 and delta/pcount >= SURGE_RATE):
                surged.append((p, delta))

    for pid in prev_ids - curr_ids:
        prev = prev_by_id[pid]
        if recent_ids and pid in recent_ids:
            continue
        removed.append(prev)

    msg = ""
    if down:
        down.sort(key=lambda x: x[1])
        msg += "📉 *가격 인하* (Top 5)\n"
        for p, d in down[:5]:
            msg += f"• {p.get('provider','')} {p.get('name','')}: *{abs(d):,}원* 하락\n"
        msg += "\n"
    if up:
        up.sort(key=lambda x: x[1], reverse=True)
        msg += "📈 *가격 인상* (Top 5)\n"
        for p, d in up[:5]:
            msg += f"• {p.get('provider','')} {p.get('name','')}: *{d:,}원* 상승\n"
        msg += "\n"
    if new_plans:
        msg += f"🆕 *신규 요금제*: {len(new_plans)}개\n\n"
    if removed:
        msg += f"❌ *단종*: {len(removed)}개\n\n"
    if surged:
        surged.sort(key=lambda x: x[1], reverse=True)
        msg += f"🔥 *급상승 인기*\n"
        for p, d in surged[:3]:
            msg += f"• {p.get('provider','')} {p.get('name','')}: +{d:,}명\n"
    return msg if msg else "변경 사항 없음"


# ── 스크래핑 트리거 ───────────────────────────────────────────────────────────

def trigger_scrape_job(source_type='auto', days=None, scrape_type='all'):
    """Cloud Run Job을 실행하여 수집 작업을 위임
    scrape_type: 'all'(모요+알닷), 'aldot'(알닷만)
    """
    try:
        import google.auth
        import google.auth.transport.requests

        PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'mvno-484509')
        JOB_NAME   = 'moyo-scrape-job'
        REGION     = 'asia-northeast3'

        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        url = (
            f"https://run.googleapis.com/v2/projects/{PROJECT_ID}"
            f"/locations/{REGION}/jobs/{JOB_NAME}:run"
        )
        env_vars = [
            {"name": "SCRAPE_SOURCE_TYPE", "value": source_type},
            {"name": "SCRAPE_TYPE",        "value": scrape_type},
        ]
        if days:
            env_vars.append({"name": "SCRAPE_DAYS", "value": str(days)})

        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"overrides": {"containerOverrides": [{"env": env_vars}]}},
            timeout=30
        )

        if resp.status_code in (200, 201):
            log(f"✅ Job 실행 시작 ({source_type}, {days or '기본'}일)")
            return True
        else:
            log(f"❌ Job 실행 실패: {resp.status_code} {resp.text}")
            return False

    except Exception as e:
        log(f"❌ Job 트리거 실패:\n{traceback.format_exc()}")
        return False


def trigger_ppomppu_job(requester_chat_id=None, days=None):
    """뽐뿌 Cloud Run Job 실행"""
    try:
        import google.auth
        import google.auth.transport.requests

        PROJECT_ID  = os.getenv('GOOGLE_CLOUD_PROJECT', 'mvno-484509')
        JOB_NAME    = 'ppomppu-monitor-job'
        REGION      = 'asia-northeast3'

        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        url = (
            f"https://run.googleapis.com/v2/projects/{PROJECT_ID}"
            f"/locations/{REGION}/jobs/{JOB_NAME}:run"
        )
        env_vars = []
        if requester_chat_id:
            env_vars.append({"name": "REQUESTER_CHAT_ID", "value": str(requester_chat_id)})
        if days:
            env_vars.append({"name": "SCRAPE_DAYS", "value": str(days)})

        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"overrides": {"containerOverrides": [{"env": env_vars}]}} if env_vars else {},
            timeout=30
        )
        if resp.status_code in (200, 201):
            log("✅ 뽐뿌 Job 실행 시작")
            send_to(CHAT_LOG, "🚀 뽐뿌 Job 시작됐습니다.")
            return True
        else:
            log(f"❌ 뽐뿌 Job 실행 실패: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        log(f"❌ 뽐뿌 Job 트리거 실패: {traceback.format_exc()}")
        return False


def trigger_excel_job(requester_chat_id, days=30):
    """커뮤니티 동향 엑셀 Cloud Run Job 실행"""
    try:
        import google.auth
        import google.auth.transport.requests

        PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'mvno-484509')
        JOB_NAME   = 'community-excel-job'
        REGION     = 'asia-northeast3'

        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        url = (
            f"https://run.googleapis.com/v2/projects/{PROJECT_ID}"
            f"/locations/{REGION}/jobs/{JOB_NAME}:run"
        )
        env_vars = [
            {"name": "REQUESTER_CHAT_ID", "value": str(requester_chat_id)},
            {"name": "EXCEL_DAYS",        "value": str(days)},
        ]
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"overrides": {"containerOverrides": [{"env": env_vars}]}},
            timeout=30
        )
        if resp.status_code in (200, 201):
            log(f"✅ 커뮤니티 엑셀 Job 시작 (chat_id={requester_chat_id}, days={days})")
            return True
        else:
            log(f"❌ 커뮤니티 엑셀 Job 실패: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        log(f"❌ 커뮤니티 엑셀 Job 트리거 실패:\n{traceback.format_exc()}")
        return False




@app.route('/scrape_webhook', methods=['POST'])
def scrape_webhook():
    try:
        log("🔍 자동 수집 시작 (Cloud Scheduler)")
        if not trigger_scrape_job(source_type='auto'):
            return jsonify({"status": "error", "message": "수집 실패"}), 500
        return jsonify({"status": "ok"})
    except Exception as e:
        log(f"❌ Webhook 에러:\n{traceback.format_exc()}")
        return jsonify({"status": "error"}), 500


@app.route('/telegram_webhook', methods=['POST'])
@app.route('/telegram-webhook', methods=['POST'])  # 하이픈 버전 추가
def telegram_webhook():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"status": "ok"})

        # ── 사은품 버튼 콜백 처리 ────────────────────────────────────────────
        if 'callback_query' in body:
            try:
                from gift_callback_handler import handle_gift_callback
                if handle_gift_callback(body['callback_query']):
                    return jsonify({"status": "ok"})
            except Exception as e:
                log(f"❌ gift callback 처리 오류: {e}")
            return jsonify({"status": "ok"})

        if 'message' not in body:
            return jsonify({"status": "ok"})

        msg  = body['message']

        # 봇 자신의 메시지 무시
        sender = msg.get('from', {})
        if sender.get('is_bot') or 'bot' in sender.get('username', '').lower():
            return jsonify({"status": "ok"})

        chat_id    = str(msg.get('chat', {}).get('id', ''))
        text       = msg.get('text', '').strip()
        text_lower = text.lower()
        is_log     = (chat_id == str(CHAT_LOG))

        if not text:
            return jsonify({"status": "ok"})

        def reply(txt, parse_mode="HTML"):
            """요청 방에 응답. 로그방이 아니면 로그방에도 동시 전송"""
            send_to(chat_id, txt, parse_mode)
            if not is_log:
                send_to(CHAT_LOG, f"[{chat_id} 요청 결과]\n{txt}", parse_mode)

        def log_only(txt):
            """로그방에만 전송 (진행상황)"""
            send_to(CHAT_LOG, txt)

        # ── 대화 입력 대기 처리 ──────────────────────────────────────────────
        if chat_id in _moyo_waiting:
            state = _moyo_waiting[chat_id]

            # ── 뽐뿌 days 입력 ───────────────────────────────────────────────
            if state == 'ppomppu':
                del _moyo_waiting[chat_id]
                try:
                    days = float(text.strip())
                    if days <= 0 or days > 30:
                        raise ValueError
                except Exception:
                    reply("⚠️ 숫자로 입력해주세요.\n예) 1 = 24시간 / 0.5 = 12시간 / 2 = 48시간")
                    return jsonify({"status": "ok"})
                hours = int(days * 24)
                label = f"{hours}시간" if days < 1 else f"{days}일({hours}시간)"
                reply(f"🔍 뽐뿌 {label} 분석을 시작합니다! 잠시 후 결과를 보내드립니다.")
                log_only(f"🚀 뽐뿌 Job 트리거 ({days}일치, {chat_id} 요청)")
                webhook_ppomppu(requester_chat_id=chat_id, days=days)
                return jsonify({"status": "ok"})

            # ── 가이드 날짜 입력 ─────────────────────────────────────────────
            if state == 'guide_date':
                date_input = text.strip()
                # 형식 검증: 숫자/슬래시 조합 (3/1, 03/01, 3-1 등)
                import re
                cleaned = date_input.replace('-', '/').replace('.', '/')
                parts   = cleaned.split('/')
                try:
                    if len(parts) != 2:
                        raise ValueError
                    m, d = int(parts[0]), int(parts[1])
                    if not (1 <= m <= 12 and 1 <= d <= 31):
                        raise ValueError
                    date_str = f"{m:02d}/{d:02d}"
                except ValueError:
                    reply("⚠️ 날짜 형식으로 입력해주세요. 예) 3/1 또는 03/01")
                    return jsonify({"status": "ok"})
                # 저장
                final_prices = _moyo_waiting.pop('_guide_tmp', {})
                del _moyo_waiting[chat_id]
                print(f"✅ 가이드 저장: {date_str} 기준, prices={final_prices}")
                db = FirebaseHandler()
                db.save_guide_prices(final_prices, updated_by=chat_id, guide_date=date_str)
                from core.firebase_handler import FirebaseHandler as FH
                lines = [f"✅ 가이드 금액이 저장되었습니다 ({date_str} 기준)\n"]
                for seg in FH.GUIDE_SEGMENTS:
                    p = final_prices.get(seg, 0)
                    lines.append(f"  {seg:<8}: {p:,}원")
                reply("\n".join(lines))
                return jsonify({"status": "ok"})

            # ── 가이드 금액 입력 ─────────────────────────────────────────────
            if state.startswith('guide_'):
                from core.firebase_handler import FirebaseHandler as FH
                segments = FH.GUIDE_SEGMENTS
                current_seg = state[len('guide_'):]  # 'guide_7G+' → '7G+'

                # 금액 파싱
                try:
                    price = int(text.strip().replace(',', '').replace('원', ''))
                    if price <= 0:
                        raise ValueError
                except Exception:
                    reply(f"⚠️ 숫자로 입력해주세요. 예) 10000")
                    return jsonify({"status": "ok"})

                # 임시 저장 (세션)
                if '_guide_tmp' not in _moyo_waiting:
                    _moyo_waiting['_guide_tmp'] = {}
                _moyo_waiting['_guide_tmp'][current_seg] = price

                # 다음 구간으로
                idx = segments.index(current_seg)
                if idx + 1 < len(segments):
                    next_seg = segments[idx + 1]
                    _moyo_waiting[chat_id] = f'guide_{next_seg}'
                    reply(f"{next_seg} 가이드 금액은?")
                else:
                    # 마지막 구간 완료 → 날짜 입력 대기
                    _moyo_waiting[chat_id] = 'guide_date'
                    reply("기준 날짜를 입력해주세요. (예: 3/1 또는 03/01)")
                return jsonify({"status": "ok"})

        # ── 1. 뽐뿌 확인 ─────────────────────────────────────────────────────
        if text in ('뽐뿌 확인', '/ppomppu'):
            _moyo_waiting[chat_id] = 'ppomppu'
            reply("📅 몇 일치를 분석할까요? (숫자만 입력, 예: 2)")
            return jsonify({"status": "ok"})

        # ── 2. 동향 요약 엑셀 (뽐뿌/디씨/유튜브 통합) ─────────────────────────
        elif any(k in text_lower for k in ['커뮤니티 동향', '커뮤니티동향']):
            reply("📊 동향 요약 엑셀 생성 중...\n(뽐뿌 + 디씨 + 유튜브 / 최근 30일)\n잠시 후 파일을 보내드립니다.")
            if not trigger_excel_job(requester_chat_id=chat_id, days=30):
                reply("❌ 엑셀 Job 시작 실패. 서버 로그를 확인해주세요.")

        # ── 3. 최신분석 ──────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['최신', '분석', '요약', '비교']):
            analysis = get_latest_analysis()
            if not analysis:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")
                return jsonify({"status": "ok"})
            latest_plans = analysis['plans']
            rs_cnt = sum(1 for p in latest_plans if p.get('is_rs'))
            db = FirebaseHandler()
            prev = db.get_previous_data('moyo', compare_type=None)
            prev_plans = _safe_plans(prev) if prev else []
            from scrape_job import build_summary_table
            summary      = build_summary_table(latest_plans, prev_plans)
            guide_data   = db.get_guide_prices()
            from scrape_job import build_guide_comparison
            guide_msg    = build_guide_comparison(latest_plans, guide_data) if guide_data else ""
            checked_at   = analysis['checked_at'].strftime('%m/%d %H:%M')
            msg = (
                f"📋 수집 시각 ({checked_at})\n"
                f"총 {analysis['total_plans']}개 (RS {rs_cnt}개 / RM {analysis['total_plans']-rs_cnt}개)\n\n"
                f"{summary}"
                + (f"\n\n{guide_msg}" if guide_msg else "")
            )
            reply(msg, parse_mode="Markdown")

        # ── 3. 엑셀 파일 (모요 요금제) ───────────────────────────────────────
        elif any(k in text_lower for k in ['엑셀', '파일', 'excel']):
            if not HAS_PANDAS:
                reply("⚠️ pandas 미설치. 엑셀 생성 불가.")
                return jsonify({"status": "ok"})
            analysis = get_latest_analysis()
            if not analysis or not analysis['plans']:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")
                return jsonify({"status": "ok"})
            path = f"/tmp/moyo_{analysis['checked_at'].strftime('%m%d_%H%M')}.xlsx"
            from scrape_job import build_excel
            build_excel(analysis['plans'], [], path, mvnohub_plans=[])
            send_telegram_file(path, "📊 전체 요금제 명단", chat_id=chat_id)

        # ── 4. 가성비/최저가 ─────────────────────────────────────────────────
        elif any(k in text_lower for k in ['가성비', '최저', 'top']):
            analysis = get_latest_analysis()
            if analysis and analysis['plans']:
                valid = [p for p in analysis['plans'] if p.get('final_price', 0) > 0]
                top5  = sorted(valid, key=lambda x: x['final_price'])[:5]
                out   = "💰 최저가 Top 5\n\n"
                for i, p in enumerate(top5, 1):
                    out += (f"{i}. {p.get('provider','?')} {p.get('name','?')}\n"
                            f"   {p.get('data','?')} | {p.get('final_price',0):,}원 | {p.get('network','?')}\n\n")
                reply(out)
            else:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")

        # ── 5. 모요 인기 ─────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['모요 인기', '인기']):
            analysis = get_latest_analysis()
            if not analysis or not analysis['plans']:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")
                return jsonify({"status": "ok"})
            from scrape_job import build_popularity_table
            reply(build_popularity_table(analysis['plans']))

        # ── 6. RS 분석 ───────────────────────────────────────────────────────
        elif text_lower.strip() == 'rs':
            analysis = get_latest_analysis()
            if not analysis or not analysis['plans']:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")
                return jsonify({"status": "ok"})
            latest_plans = analysis['plans']
            rs_cnt = sum(1 for p in latest_plans if p.get('is_rs'))
            db = FirebaseHandler()
            prev = db.get_previous_data('moyo', compare_type=None)
            prev_plans = _safe_plans(prev) if prev else []
            from scrape_job import build_summary_table, build_guide_comparison, build_rs_analysis
            summary    = build_summary_table(latest_plans, prev_plans)
            guide_data = db.get_guide_prices()
            guide_msg  = build_guide_comparison(latest_plans, guide_data) if guide_data else ""
            checked_at = analysis['checked_at'].strftime('%m/%d %H:%M')
            rs_top5    = build_rs_analysis(latest_plans)
            # RS Top5 부분만 추출 (가격대별 표 제외, 가입수 Top5만)
            top5_start = rs_top5.find("📊 가입수 Top 5 (RS)")
            top5_only  = rs_top5[top5_start:] if top5_start != -1 else rs_top5
            msg = (
                f"📋 수집 시각 ({checked_at})\n"
                f"총 {analysis['total_plans']}개 (RS {rs_cnt}개 / RM {analysis['total_plans']-rs_cnt}개)\n\n"
                f"{summary}"
                + (f"\n\n{guide_msg}" if guide_msg else "")
                + f"\n\n{top5_only}"
            )
            reply(msg, parse_mode="Markdown")

        # ── 7. RM 분석 ───────────────────────────────────────────────────────
        elif text_lower.strip() == 'rm':
            analysis = get_latest_analysis()
            if not analysis or not analysis['plans']:
                reply("⚠️ 데이터 없음. '모요 확인'을 먼저 해주세요.")
                return jsonify({"status": "ok"})
            # 전주 데이터 (7일 전 08시)
            try:
                db         = FirebaseHandler()
                prev_week  = db.get_data_by_hour('moyo', target_hour=8, days_ago=7)
                prev_plans = _safe_plans(prev_week) if prev_week else []
            except Exception:
                prev_plans = []
            from scrape_job import build_rm_analysis
            reply(build_rm_analysis(analysis['plans'], prev_plans), parse_mode="Markdown")

        # ── 8. 가이드 변경 ───────────────────────────────────────────────────
        elif '가이드 변경' in text_lower or '가이드변경' in text_lower:
            from core.firebase_handler import FirebaseHandler as FH
            first_seg = FH.GUIDE_SEGMENTS[0]
            _moyo_waiting[chat_id] = f'guide_{first_seg}'
            _moyo_waiting['_guide_tmp'] = {}
            reply(f"{first_seg} 가이드 금액은?")

        # ── 6. 가이드 확인 ───────────────────────────────────────────────────
        elif '가이드 확인' in text_lower or '가이드확인' in text_lower:
            db = FirebaseHandler()
            guide_data = db.get_guide_prices()
            if not guide_data:
                reply("⚠️ 저장된 가이드 금액이 없습니다.\n'가이드 변경'으로 입력해주세요.")
            else:
                prices    = guide_data.get('prices', {})
                # guide_date 우선, 없으면 updated_at으로 fallback
                date_str  = guide_data.get('guide_date', '')
                if not date_str:
                    updated  = guide_data.get('updated_at')
                    date_str = (updated.astimezone(KOREA_TZ).strftime('%m/%d')
                                if updated and hasattr(updated, 'astimezone') else '날짜미상')
                from core.firebase_handler import FirebaseHandler as FH
                lines = [f"📋 현재 가이드 금액 ({date_str} 기준)\n"]
                for seg in FH.GUIDE_SEGMENTS:
                    p = prices.get(seg, 0)
                    lines.append(f"  {seg:<8}: {p:,}원" if p else f"  {seg:<8}: 미설정")
                reply("\n".join(lines))

        # ── 7. 알닷 확인 ─────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['알닷 확인', '알닷확인']):
            reply("📡 알닷 수집을 시작합니다! (약 30분 소요)")
            log_only(f"📡 알닷 수집 시작 ({chat_id} 요청)")
            if not trigger_scrape_job(source_type='manual', scrape_type='aldot'):
                reply("❌ 수집 시작 실패. 서버 로그를 확인해주세요.")

        # ── 8. 모요 확인 ─────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['모요 확인', '수집해줘', '체크해줘', '모요체크']):
            reply("🔍 모요 수집을 시작합니다! (약 15분 소요)")
            log_only(f"🔍 모요 수집 시작 ({chat_id} 요청)")
            if not trigger_scrape_job(source_type='manual'):
                reply("❌ 수집 시작 실패. 서버 로그를 확인해주세요.")

        # ── 10. 도움말 ────────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['도움말', '도와줘', '도움', 'help', '명령']):
            reply(
                "📋 <b>명령어 안내</b>\n\n"
                "🔍 <b>수집</b>\n"
                "• <code>모요 확인</code> — 모요+알닷+알뜰폰허브 전체 수집 (약 50분)\n"
                "• <code>알닷 확인</code> — 알닷만 수집 → RS 비교표 + 엑셀 (약 30분)\n"
                "• <code>뽐뿌 확인</code> — 뽐뿌 MVNO 게시글 수집 (기간 입력)\n"
                "\n"
                "📊 <b>조회/분석</b>\n"
                "• <code>최신분석</code> — 마지막 수집 기준 RS 망별 최저가 표\n"
                "• <code>RS</code> — RS 가격대별 최대 데이터 + 가입수 Top 5\n"
                "• <code>RM</code> — RM 가격대별 최대 데이터 + 가입수 Top 5 (전주 대비)\n"
                "• <code>모요 인기</code> — 3사별 가입자수 Top 5 (전체 요금제)\n"
                "• <code>최저가</code> — 전체 요금제 최저가 Top 5\n"
                "• <code>엑셀</code> — 마지막 수집 전체 요금제 xlsx\n"
                "• <code>커뮤니티 동향</code> — 뽐뿌/디씨/유튜브 통합 커뮤니티 엑셀\n"
                "\n"
                "🎯 <b>가이드 금액 (SKT RS 기준)</b>\n"
                "• <code>가이드 변경</code> — 구간별 가이드 금액 + 기준 날짜 입력\n"
                "• <code>가이드 확인</code> — 현재 저장된 가이드 금액 조회\n",
                parse_mode="HTML"
            )

        return jsonify({"status": "ok"})

    except Exception as e:
        log(f"❌ Webhook 처리 에러:\n{traceback.format_exc()}")
        return jsonify({"status": "error"}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 뽐뿌 모니터링 엔드포인트 (신규)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/webhook_ppomppu', methods=['POST'])
def webhook_ppomppu(requester_chat_id=None, days=None):
    """뽐뿌 모니터링 웹훅 - Cloud Run Job 트리거"""
    log("🚀 뽐뿌 Job 트리거 시작")
    if trigger_ppomppu_job(requester_chat_id=requester_chat_id, days=days):
        return jsonify({"status": "started", "message": "Job 실행 중"}), 200
    else:
        return jsonify({"status": "error", "message": "Job 실행 실패"}), 500





@app.route('/run_youtube_context', methods=['POST'])
def run_youtube_context():
    """YouTube context 생성 엔드포인트 (Cloud Scheduler 20:10 호출)"""
    def _run():
        try:
            from youtube_context_builder import save_youtube_context
            save_youtube_context()
            log("✅ youtube_context 생성 완료")
        except Exception as e:
            log(f"❌ youtube_context 생성 실패: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"}), 200



@app.route('/run_daily_mailer', methods=['POST'])
def run_daily_mailer():
    """일일 통합 메일 발송 엔드포인트 (Cloud Scheduler 20:40 호출)"""
    def _run():
        try:
            from daily_mailer import main as mailer_main
            ok = mailer_main()
            log("✅ daily_mailer 완료: " + str(ok))
        except Exception as e:
            log(f"❌ daily_mailer 실패: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"}), 200



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))