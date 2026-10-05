"""
scrape_job.py  v2.1
- source_type: auto(스케줄) / manual(텔레그램)
- auto끼리만 비교 / manual은 최신 auto와 비교
- 신규 판단: 최근 5개 수집 plan_id 합집합과 비교 (누락 오탐 방지)
- 수집 후 엑셀 자동 전송
- 시작 메시지: [자동]/[수동] 구분
- 완료 메시지: 요약 테이블 포함
"""

import os
import sys
from datetime import datetime
import pytz
import requests

from scrapers.moyo_scraper import MoyoScraper
from core.firebase_handler import FirebaseHandler
from core.comparator import Comparator


# ── 요약 테이블 ───────────────────────────────────────────────────────────────

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
        msg  = f"📊 {label} 망별 최저가\n"
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
        msg += "↓ 직전 대비 하락 / ↑ 상승"
        return msg

    return tbl("RS", curr_rs, changes_rs) + "\n\n" + tbl("RM", curr_rm, changes_rm)

try:
    import pandas as pd
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

KOREA_TZ  = pytz.timezone('Asia/Seoul')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')


# ── 텔레그램 ──────────────────────────────────────────────────────────────────

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
    except: pass

def send_telegram_file(file_path, caption):
    if not BOT_TOKEN or not CHAT_ID: return
    try:
        with open(file_path, 'rb') as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={'chat_id': CHAT_ID, 'caption': caption},
                files={'document': f},
                timeout=60
            )
    except Exception as e:
        print(f"⚠️ 파일 전송 실패: {e}")


# ── 엑셀 생성 ─────────────────────────────────────────────────────────────────

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
    rows = []
    for i, p in enumerate(plans, 1):
        row = {'_no': i}
        for field, _, _ in EXCEL_COLS[1:]:
            val = p.get(field, '')
            if field == 'discount_months' and val == 0: val = ''
            if field == 'is_rs':                        val = 'RS' if val else 'RM'
            if field in ('is_lowest_rs', 'is_lowest_rm'): val = '★' if val else ''
            if field == 'subscribers' and val == 0:     val = ''
            row[field] = val
        rows.append(row)

    df = pd.DataFrame(rows, columns=[f for f, _, _ in EXCEL_COLS])
    df.to_excel(path, index=False, engine='openpyxl')

    try:
        wb       = load_workbook(path)
        ws       = wb.active
        hdr_fill = PatternFill("solid", fgColor="1F4E79")
        hdr_font = Font(bold=True, color="FFFFFF", size=10)
        thin     = Border(left=Side(style='thin'), right=Side(style='thin'),
                          top=Side(style='thin'),  bottom=Side(style='thin'))
        odd_fill  = PatternFill("solid", fgColor="EBF3FB")
        even_fill = PatternFill("solid", fgColor="FFFFFF")

        for ci, (_, kor, width) in enumerate(EXCEL_COLS, 1):
            c           = ws.cell(row=1, column=ci)
            c.value     = kor
            c.fill      = hdr_fill
            c.font      = hdr_font
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border    = thin
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
        print(f"⚠️ 스타일 실패: {e}")
    return path


# ── 변경 내역 메시지 ──────────────────────────────────────────────────────────

def build_plan_changes(curr_plans, prev_plans, recent_ids=None):
    """
    recent_ids: 최근 5개 수집 plan_id 합집합.
                여기 이미 있으면 이번 수집에서 누락된 것 → 신규 아님.
    """
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
            continue
        # 가격 변경
        cp, pp = p.get('final_price',0), prev.get('final_price',0)
        if cp > 0 and pp > 0 and cp != pp:
            entry = {'provider': p.get('provider','?'), 'network': p.get('network','?'),
                     'name': p.get('name','?'), 'price': cp, 'diff': cp-pp,
                     'is_rs': p.get('is_rs', False)}
            (down if cp < pp else up).append(entry)
        # 선택수 급등
        cs, ps = p.get('subscribers',0), prev.get('subscribers',0)
        if ps > 0 and cs > ps:
            ds, rate = cs-ps, (cs-ps)/ps
            if rate >= SURGE_RATE and ds >= SURGE_MIN:
                surged.append({'provider': p.get('provider','?'), 'network': p.get('network','?'),
                               'name': p.get('name','?'), 'price': p.get('final_price',0),
                               'curr_subs': cs, 'diff_subs': ds, 'rate': rate,
                               'is_rs': p.get('is_rs', False)})

    # 신규: recent_ids에 없는 것만 진짜 신규
    for pid in (curr_ids - prev_ids):
        if recent_ids and pid in recent_ids:
            continue  # 이전에 있던 요금제가 한번 누락된 것 → 무시
        p = curr_by_id[pid]
        new_plans.append({'provider': p.get('provider','?'), 'network': p.get('network','?'),
                          'name': p.get('name','?'), 'price': p.get('final_price',0),
                          'is_rs': p.get('is_rs', False)})

    # 삭제: recent_ids 기준으로 최근 5개 모두에서 없어진 것만
    for pid in (prev_ids - curr_ids):
        if recent_ids and pid in recent_ids:
            continue  # 아직 최근 기록에 있음 → 일시 누락일 수 있음
        p = prev_by_id[pid]
        removed.append({'provider': p.get('provider','?'), 'name': p.get('name','?'),
                        'is_rs': p.get('is_rs', False)})

    if not any([down, up, new_plans, removed, surged]):
        return ""

    rs1 = lambda e: (0 if e['is_rs'] else 1)
    down.sort(key=lambda e: (rs1(e), e['diff']))
    up.sort(key=lambda e: (rs1(e), e['diff']))
    new_plans.sort(key=lambda e: (rs1(e), -e.get('price',0)))
    surged.sort(key=lambda e: (rs1(e), -e['diff_subs']))

    MAX = 20
    def fc(e):
        a = f"↓{abs(e['diff']):,}" if e['diff']<0 else f"↑{e['diff']:,}"
        return f"[{'RS' if e['is_rs'] else 'RM'}] {e['provider']}({e['network']}), {e['name'][:25]}, {e['price']:,}원({a})"
    def fn(e):
        return f"[{'RS' if e['is_rs'] else 'RM'}] {e['provider']}({e['network']}), {e['name'][:25]}, {e['price']:,}원"
    def fs(e):
        return (f"[{'RS' if e['is_rs'] else 'RM'}] {e['provider']}({e['network']}), {e['name'][:25]}, "
                f"{e['price']:,}원 | {e['curr_subs']:,}명(+{e['diff_subs']:,}, +{e['rate']*100:.0f}%)")

    lines = [f"🔄 변경 내역 | 가격↓{len(down)} ↑{len(up)} | 신규 {len(new_plans)} | 삭제 {len(removed)} | 급등 {len(surged)}", ""]
    for title, items, fmt_fn in [("■ 하향 요금제", down, fc), ("■ 상향 요금제", up, fc),
                                   ("■ 신규 요금제", new_plans, fn), ("■ 선택수 급등", surged, fs)]:
        if items:
            lines.append(title)
            lines += [fmt_fn(e) for e in items[:MAX]]
            if len(items) > MAX: lines.append(f"  ... 외 {len(items)-MAX}개")
            lines.append("")
    if removed:
        lines.append(f"■ 삭제된 요금제: {len(removed)}개")
        for e in removed[:10]:
            lines.append(f"[{'RS' if e['is_rs'] else 'RM'}] {e['provider']}, {e['name'][:25]}")
        if len(removed) > 10: lines.append(f"  ... 외 {len(removed)-10}개")

    return "\n".join(lines)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    source_type = os.getenv('SCRAPE_SOURCE_TYPE', 'auto')
    label = '자동' if source_type == 'auto' else '수동'
    korea_time  = datetime.now(KOREA_TZ)
    print(f"🚀 스크래핑 시작: {korea_time.strftime('%Y-%m-%d %H:%M:%S')} ({source_type})")

    # ── 시작 메시지 ──────────────────────────────────────────────────────────
    send_telegram(f"🔍 [{label}] 수집 작업을 시작합니다! (약 15분 소요)")

    try:
        def progress(msg):
            print(msg)
            send_telegram(msg)

        scraper = MoyoScraper(progress_callback=progress)
        plans, screenshot = scraper.scrape()
        print(f"✅ {len(plans)}개 수집 완료")

        db = FirebaseHandler()

        # ── 비교 대상 결정 ──────────────────────────────────────────────────
        # auto: 직전 auto와 비교
        # manual: 최신 auto와 비교, 없으면 직전 manual
        if source_type == 'auto':
            previous = db.get_previous_data('moyo', compare_type='auto')
        else:
            previous = db.get_latest_auto_data('moyo')
            if not previous:
                previous = db.get_previous_data('moyo')

        prev_plans = previous.get('plans', []) if previous else []

        # 최근 5개 plan_id 합집합 (신규 오탐 방지)
        recent_ids = db.get_recent_plan_ids('moyo', limit=5)

        # ── 최저가 태깅 후 저장 ─────────────────────────────────────────────
        comparator = Comparator()
        plans = comparator.tag_plans_with_lowest(plans)
        db.save_check_result('moyo', plans, screenshot, source_type=source_type)
        print("✅ Firebase 저장 완료")

        rs_count = sum(1 for p in plans if p.get('is_rs'))
        checked_at = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')

        # 요약 테이블 생성
        summary = build_summary_table(plans, prev_plans)

        # 변경 내역 요약 (신규/단종 건수만)
        changes_msg = build_plan_changes(plans, prev_plans, recent_ids=recent_ids)
        changes_brief = ""
        if changes_msg:
            new_cnt = changes_msg.count('신규')
            del_cnt = changes_msg.count('삭제된') 
            parts = []
            if new_cnt: parts.append(f"🆕 신규 요금제: {new_cnt}개")
            if del_cnt: parts.append(f"❌ 단종: {del_cnt}개")
            changes_brief = "\n\n📊 직전 수집 대비 변경 사항\n" + "\n".join(parts) if parts else ""

        result = (
            f"✅ 수집 완료 [{label}] ({checked_at})\n"
            f"총 {len(plans)}개 (RS {rs_count}개 / RM {len(plans)-rs_count}개)\n\n"
            f"{summary}"
            f"{changes_brief}"
        )
        send_telegram(result)

        # ── 엑셀 전송 (auto 수집 시에만) ────────────────────────────────────
        if source_type == 'auto' and HAS_PANDAS:
            try:
                excel_path = f"/tmp/moyo_{datetime.now(KOREA_TZ).strftime('%m%d_%H%M')}.xlsx"
                build_excel(plans, excel_path)
                send_telegram_file(
                    excel_path,
                    f"📊 모요 요금제 ({len(plans)}건) | {datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')}"
                )
                print("✅ 엑셀 전송 완료")
            except Exception as e:
                print(f"⚠️ 엑셀 전송 실패: {e}")

    except Exception as e:
        import traceback
        print(f"❌ 에러: {e}\n{traceback.format_exc()}")
        send_telegram(f"❌ 수집 실패\n\n{str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()