"""
main.py  v3.5
- RS/RM 분리 최신분석 표
- auto/manual source_type 비교 분리
- 뽐뿌 MVNO 모니터링 추가
- 봇 자신의 메시지 무시 (무한루프 방지)
- 그룹 채팅 봇 username 체크 추가
- 수집 명령어 변경: '수집' → '수집해줘'
- trigger_scrape_job: 직접 수집 → Cloud Run Job 실행으로 변경
"""

from flask import Flask, request, jsonify
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
CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')
KOREA_TZ  = pytz.timezone('Asia/Seoul')


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def get_korea_time():
    return datetime.now(KOREA_TZ)

def send_telegram(text, parse_mode="Markdown"):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        log(f"❌ 텔레그램 전송 에러: {e}")
        return False

def send_telegram_file(file_path, caption):
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        with open(file_path, 'rb') as f:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={'chat_id': CHAT_ID, 'caption': caption},
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
]

def build_excel(plans, path):
    from core.comparator import Comparator
    comp = Comparator()
    plans = comp.tag_plans_with_lowest(plans)

    rows = []
    for i, p in enumerate(plans, 1):
        row = {'_no': i}
        for field, _, _ in EXCEL_COLS[1:]:
            val = p.get(field, '')
            if field == 'discount_months' and val == 0: val = ''
            if field == 'is_rs':        val = 'RS' if val else 'RM'
            if field in ('is_lowest_rs', 'is_lowest_rm'): val = '★' if val else ''
            if field == 'subscribers' and val == 0: val = ''
            row[field] = val
        rows.append(row)

    df = pd.DataFrame(rows, columns=[f for f, _, _ in EXCEL_COLS])
    df.to_excel(path, index=False, engine='openpyxl')

    try:
        wb = load_workbook(path)
        ws = wb.active
        hdr_fill = PatternFill("solid", fgColor="1F4E79")
        hdr_font = Font(bold=True, color="FFFFFF", size=10)
        thin = Border(
            left=Side(style='thin'),  right=Side(style='thin'),
            top=Side(style='thin'),   bottom=Side(style='thin')
        )
        odd_fill  = PatternFill("solid", fgColor="EBF3FB")
        even_fill = PatternFill("solid", fgColor="FFFFFF")

        for ci, (_, kor, width) in enumerate(EXCEL_COLS, 1):
            c            = ws.cell(row=1, column=ci)
            c.value      = kor
            c.fill       = hdr_fill
            c.font       = hdr_font
            c.alignment  = Alignment(horizontal='center', vertical='center')
            c.border     = thin
            ws.column_dimensions[get_column_letter(ci)].width = width
        ws.row_dimensions[1].height = 22

        price_cols = {10, 12}
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            fill = odd_fill if row[0].row % 2 == 0 else even_fill
            for cell in row:
                cell.border    = thin
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.fill      = fill
                if cell.column in price_cols and isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0'
        ws.freeze_panes = 'A2'
        wb.save(path)
    except Exception as e:
        log(f"⚠️ 스타일 적용 실패: {e}")
    return path


# ── 분석 표 (RS/RM 분리) ──────────────────────────────────────────────────────

def build_summary_table(curr_plans, prev_plans):
    comp      = Comparator()
    prev_rs   = comp.get_segment_min_prices(prev_plans, rs_only=True)  if prev_plans else {}
    prev_rm   = comp.get_segment_min_prices(prev_plans, rs_only=False) if prev_plans else {}
    curr_rs   = comp.get_segment_min_prices(curr_plans, rs_only=True)
    curr_rm   = comp.get_segment_min_prices(curr_plans, rs_only=False)
    changes_rs = comp.analyze_changes(curr_rs, prev_rs)
    changes_rm = comp.analyze_changes(curr_rm, prev_rm)

    def fmt(v):   return f"{v:,}" if v else "  -  "
    def arrow(d):
        if d < 0: return f"({abs(d):,}↓)".center(7)
        if d > 0: return f"({d:,}↑)".center(7)
        return " " * 7

    def tbl(label, summary, changes):
        msg  = f"📊 *{label} 망별 최저가*\n```\n"
        msg += "구간     │  SKT  │  KT   │ LGU+\n"
        msg += "─────────────────────────────────\n"
        for seg, nets in summary.items():
            s = fmt(nets.get('SKT',  0))
            k = fmt(nets.get('KT',   0))
            l = fmt(nets.get('LGU+', 0))
            msg += f"{seg:<8} │{s:^7}│{k:^7}│{l:^6}\n"
            ds = changes.get(seg, {})
            row = [arrow(ds.get('SKT',0)), arrow(ds.get('KT',0)), arrow(ds.get('LGU+',0))]
            if any(x.strip() for x in row):
                msg += f"         │{'│'.join(row)}\n"
        msg += "```\n_↓ 직전 대비 하락 / ↑ 상승_"
        return msg

    return tbl("RS", curr_rs, changes_rs) + "\n\n" + tbl("RM", curr_rm, changes_rm)


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

def trigger_scrape_job(source_type='auto'):
    """Cloud Run Job을 실행하여 수집 작업을 위임"""
    try:
        import google.auth
        import google.auth.transport.requests

        PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'mvno-484509')
        JOB_NAME   = 'moyo-scrape-job'
        REGION     = 'asia-northeast3'

        # GCP 인증 토큰 획득
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token

        # Cloud Run Jobs API 호출
        url = (
            f"https://run.googleapis.com/v2/projects/{PROJECT_ID}"
            f"/locations/{REGION}/jobs/{JOB_NAME}:run"
        )
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "overrides": {
                    "containerOverrides": [{
                        "env": [{"name": "SCRAPE_SOURCE_TYPE", "value": source_type}]
                    }]
                }
            },
            timeout=30
        )

        if resp.status_code in (200, 201):
            log(f"✅ Job 실행 시작 ({source_type})")
            return True
        else:
            log(f"❌ Job 실행 실패: {resp.status_code} {resp.text}")
            return False

    except Exception as e:
        log(f"❌ Job 트리거 실패:\n{traceback.format_exc()}")
        return False


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

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
        if not body or 'message' not in body:
            return jsonify({"status": "ok"})

        msg  = body['message']

        # ── 봇 자신의 메시지 무시 (무한루프 방지) ────
        sender = msg.get('from', {})
        if sender.get('is_bot'):
            return jsonify({"status": "ok"})
        # 봇 username으로도 체크 (그룹 채팅 대응)
        if 'bot' in sender.get('username', '').lower():
            return jsonify({"status": "ok"})
        # ─────────────────────────────────────────────

        chat_id = msg.get('chat', {}).get('id')
        text = msg.get('text', '').strip()
        text_lower = text.lower()

        if not text:
            return jsonify({"status": "ok"})

        # ── 1. 뽐뿌 체크 (신규) ──────────────────────────────────────────────
        if text == '뽐뿌' or text == '/ppomppu':
            send_telegram("🔍 뽐뿌 체크를 시작합니다...")
            result = webhook_ppomppu()
            
            if isinstance(result, tuple):
                send_telegram("❌ 뽐뿌 체크 실패. 로그를 확인해주세요.")
            else:
                reply = f"""✅ 뽐뿌 체크 완료

총 {result.get('total_scraped', 0)}개 수집
신규 {result.get('new_posts', 0)}개
MVNO {result.get('mvno_posts', 0)}개 감지"""
                send_telegram(reply)
            return jsonify({"status": "ok"})

        # ── 2. 최신분석 ──────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['최신', '분석', '요약', '비교']):
            analysis = get_latest_analysis()
            if not analysis:
                send_telegram("⚠️ 데이터 없음. '수집'을 먼저 해주세요.")
                return jsonify({"status": "ok"})

            latest_plans = analysis['plans']
            db = FirebaseHandler()
            prev = db.get_previous_data('moyo', compare_type=None)
            prev_plans = _safe_plans(prev) if prev else []

            summary = build_summary_table(latest_plans, prev_plans)
            msg = (
                f"📊 *최신 분석* ({analysis['checked_at'].strftime('%m/%d %H:%M')})\n"
                f"총 *{analysis['total_plans']}개*\n\n{summary}"
            )
            send_telegram(msg)

        # ── 3. 엑셀 파일 ──────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['엑셀', '파일', 'excel']):
            if not HAS_PANDAS:
                send_telegram("⚠️ pandas 미설치. 엑셀 생성 불가.")
                return jsonify({"status": "ok"})
            analysis = get_latest_analysis()
            if not analysis or not analysis['plans']:
                send_telegram("⚠️ 데이터 없음. '수집'을 먼저 해주세요.")
                return jsonify({"status": "ok"})

            path = f"/tmp/moyo_{analysis['checked_at'].strftime('%m%d_%H%M')}.xlsx"
            build_excel(analysis['plans'], path)
            send_telegram_file(path, "📊 전체 요금제 명단")

        # ── 4. 가성비/최저가 ──────────────────────────────────────────────────
        elif any(k in text_lower for k in ['가성비', '최저', 'top']):
            analysis = get_latest_analysis()
            if analysis and analysis['plans']:
                valid = [p for p in analysis['plans'] if p.get('final_price',0) > 0]
                top5  = sorted(valid, key=lambda x: x['final_price'])[:5]
                msg   = "💰 *최저가 Top 5*\n\n"
                for i, p in enumerate(top5, 1):
                    msg += (f"{i}. *{p.get('provider','?')}* {p.get('name','?')}\n"
                            f"   {p.get('data','?')} | {p.get('final_price',0):,}원| {p.get('network','?')}\n\n")
                send_telegram(msg)
            else:
                send_telegram("⚠️ 데이터 없음. '수집'을 먼저 해주세요.")

        # ── 5. 수집 트리거 ────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['수집해줘', '체크해줘', '모요체크']):
            send_telegram("🔍 수집 작업을 시작합니다! (약 15분 소요)")
            if not trigger_scrape_job(source_type='manual'):
                send_telegram("❌ 수집 시작 실패. 서버 로그를 확인해주세요.")

        # ── 6. 도움말 ─────────────────────────────────────────────────────────
        elif any(k in text_lower for k in ['도움', 'help', '명령']):
            send_telegram(
                "📋 *명령어 안내*\n\n"
                "• `최신분석` / `요약`     — RS/RM 망별 최저가 표\n"
                "• `엑셀` / `파일`        — 전체 명단 xlsx\n"
                "• `가성비` / `최저가`    — 최저가 Top 5\n"
                "• `수집해줘` / `모요체크`    — Moyo 데이터 수집\n"
                "• `뽐뿌`                 — 뽐뿌 MVNO 글 수집 🆕\n"
            )

        return jsonify({"status": "ok"})

    except Exception as e:
        log(f"❌ Webhook 처리 에러:\n{traceback.format_exc()}")
        return jsonify({"status": "error"}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 뽐뿌 모니터링 엔드포인트 (신규)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/webhook_ppomppu', methods=['POST'])
def webhook_ppomppu():
    """뽐뿌 모니터링 웹훅 (Cloud Scheduler용)"""
    try:
        from scrapers.ppomppu_scraper import PpomppuScraper, filter_mvno_posts, filter_new_posts
        from core.firebase_handler import FirebaseHandler
        
        log("🔍 뽐뿌 모니터링 시작")
        
        # Step 1: 뽐뿌 크롤링 (7일)
        scraper = PpomppuScraper()
        all_posts = scraper.scrape(days=7, max_pages=10)
        
        if not all_posts:
            return {"status": "ok", "message": "수집된 게시글 없음", "new_posts": 0}
        
        # Step 2: Firebase에서 기존 게시글 ID 가져오기
        firebase = FirebaseHandler()
        existing_ids = firebase.get_existing_ppomppu_ids(limit=2000)
        
        # Step 3: 신규 글만 필터링
        new_posts = filter_new_posts(all_posts, existing_ids)
        
        if not new_posts:
            return {"status": "ok", "message": "신규 게시글 없음", "new_posts": 0}
        
        # Step 4: MVNO 필터링
        mvno_posts = filter_mvno_posts(
            new_posts, 
            fetch_content=True,
            use_ai=False
        )
        
        if not mvno_posts:
            return {"status": "ok", "message": "MVNO 관련 게시글 없음", "new_posts": 0}
        
        # Step 5: Firebase 저장 + Telegram 알림
        saved_count = 0
        for post in mvno_posts:
            if firebase.save_ppomppu_post(post):
                saved_count += 1
                send_ppomppu_alert(post)
        
        return {
            "status": "ok",
            "total_scraped": len(all_posts),
            "new_posts": len(new_posts),
            "mvno_posts": len(mvno_posts),
            "saved": saved_count
        }
        
    except Exception as e:
        log(f"❌ 뽐뿌 모니터링 에러: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}, 500


def send_ppomppu_alert(post):
    """뽐뿌 게시글 Telegram 알림 발송"""
    try:
        filter_result = post.get('filter_result', {})
        provider = filter_result.get('provider', '알뜰폰')
        confidence = filter_result.get('confidence', 0.0)
        method = filter_result.get('method', 'unknown')
        
        post_id = post['post_id']
        short_url = f"https://m.ppomppu.co.kr/new/bbs_view.php?no={post_id}"
        
        message = f"""🔔 <b>뽐뿌 알뜰폰 신규 글</b>

📱 <b>{provider}</b> ({confidence:.1%} 신뢰도)
📝 {post['title']}

👁 조회 {post['views']:,} | 💬 댓글 {post['comments']}
📅 {post['posted_at'].strftime('%Y-%m-%d')}

🔗 {short_url}

<i>필터: {method}</i>"""
        
        if not BOT_TOKEN or not CHAT_ID:
            log("⚠️ Telegram 설정 없음")
            return
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            log(f"✅ Telegram 알림 발송: {post_id}")
            firebase = FirebaseHandler()
            firebase.mark_ppomppu_notified(post_id)
        else:
            log(f"⚠️ Telegram 발송 실패: {response.status_code}")
            
    except Exception as e:
        log(f"❌ Telegram 알림 에러: {e}")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))