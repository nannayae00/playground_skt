# -*- coding: utf-8 -*-
"""
gift_job.py - 프로모션 사은품 센싱 메인 잡 (Cloud Run Job)

[수정 이력]
- v1.6 (2026-08-28) K CUP 메시지 '{TOTAL}' 플레이스홀더 치환 추가
    * gift_comparator.format_kcup_violation()이 헤더에 '(N/{TOTAL})' 형태로 만들어두면,
      두 사업자(KT엠모바일/U+유모바일) 결과를 다 합친 뒤 실제 총건수로 일괄 치환
- v1.5 (2026-08-28) K CUP 특이사항 메시지에 실행시각/순번 반영
    * compare_kcup() 호출 시 run_time(실행 시각)/start_index(배치 내 순번) 전달
      - KT엠모바일 결과 뒤에 U+유모바일이 이어지도록 두 번째 호출의 start_index를
        len(첫번째_결과)+1로 넘겨 전체 배치에서 번호가 이어지게 함
- v1.4 (2026-08-28) 모요 vs 직영 비교 메시지를 3자 통합 → 사업자별 2개로 분리
    * format_moyo_vs_direct_multi() 대신 format_moyo_vs_direct()를 사업자별로 두 번 호출
      (모요 vs 유모바일직영, 모요 vs 엠모바일직영 각각 별도 메시지)
    * 표 포맷을 구간/모요/직영/GAP 2열+GAP 형태로 통일 (기존 3열 모요/유모/엠모 통합표 폐지)
    * 버튼도 사업자별로 "모요(OO) 추이" / "OO 직영 추이" 2개씩 - gift_callback_handler.py의
      gift_trend_umobile / gift_trend_umobile_direct / gift_trend_ktm / gift_trend_ktm_direct
      콜백이 이미 존재해서 핸들러 쪽 수정은 불필요했음
- v1.3 (2026-08-25) 멀티 채널 발송 지원
    * GIFT_CHANNEL_ID → GIFT_CHANNEL_IDS로 변경, 세미콜론(;) 구분 문자열을 리스트로 파싱
      (콤마 아닌 이유: gcloud --set-env-vars 자체가 콤마로 여러 환경변수를 구분해서 값 안에 콤마 쓰면 깨짐)
    * _send_telegram()이 channel_id 미지정 시 GIFT_CHANNEL_IDS 전체에 순회 발송
    * 기존 단일 채널(LOG_CHANNEL_ID 등 channel_id 명시 호출)은 동작 그대로 유지
    * deploy.sh의 GIFT_CHANNEL_ID 환경변수 값을 "id1;id2" 형태로 바꾸면 방 추가/제거 가능
- v1.2 (2026-08-25) KT엠모바일 직영 이벤트 채널 통합
    * gift_ktm_event_scraper.scrape_with_cache/format_telegram_message import 추가
    * _save_ktm_detail() 추가 (_save_umobile_detail과 대칭, gift_reports/{date}/providers/ktm_direct)
    * _save_daily_tier()에 ktm_direct_band_max 파라미터 추가 → gift_daily_tier/{date}/ktm_direct 저장
    * run()에 [1.5/3] KT엠모바일 수집 단계 + 텔레그램 메시지 발송 추가 (유모바일 블록 뒤, 모요 수집 전)
    * 메시지 순서: ①모요 요약 ②유모바일 직영 이벤트 ③KT엠모바일 직영 이벤트 ④3자 비교 (마지막)
    * 마지막 비교 메시지를 2자(모요 vs 유모바일)에서 gift_comparator.format_moyo_vs_direct_multi()
      기반 3자(모요/유모/엠모) 비교로 교체
    * ⚠️ TelegramLogHandler가 'scrapers.gift_umobile_event_scraper' 로거만 구독 중.
      gift_ktm_event_scraper는 logging 모듈이 아닌 print()로 로그를 찍고 있어서
      현재 구조로는 KT 쪽 진행상황이 LOG_CHANNEL_ID로 안 감 (필요하면 print → logger.info 전환 필요)
- v1.1 (2026-07-27) 메시지 순서 변경(비교 마지막) + 비교에 추이 버튼 추가
- v1.0 (2026-07-15) 전일비교 + 7일추이 저장 + 직영비교 메시지
    * 전일 gift_daily_tier 로드 → format_summary_report(prev_snapshot)
    * gift_daily_tier/{date}/{prov_key} 저장 (7일 추이용)
    * 요약 메시지에 📈 추이 버튼 추가 (provider별)
    * 유모바일 직영 vs 모요 비교 메시지 추가
- v0.9 (2026-07-09) 텔레그램 로그 채널 추가
"""

import os
import logging
from datetime import datetime, timezone, timedelta, date

from scrapers.gift_moyo_scraper import scrape_moyo_gifts
from scrapers.gift_umobile_event_scraper import (
    scrape_with_cache, format_telegram_message
)
from scrapers.gift_ktm_event_scraper import (
    scrape_with_cache as scrape_ktm_with_cache,
    format_telegram_message as format_ktm_telegram_message,
)
from core.gift_comparator import (
    format_summary_report, format_moyo_report, build_group_index,
    compute_tier_max, compute_datakey_max, format_moyo_vs_direct,
    format_moyo_vs_direct_multi, TIER_ORDER,
    build_kcup_records, format_kcup_summary, build_kcup_buttons,
    format_kcup_violation,
)

TELEGRAM_TOKEN  = os.environ.get('TELEGRAM_TOKEN', '')
# 여러 방에 동시 발송하려면 GIFT_CHANNEL_ID 환경변수에 세미콜론(;)으로 구분해서 넣으면 됨
# 예: "GIFT_CHANNEL_ID=-1004446911605;-100XXXXXXXXXX"
# (콤마가 아닌 세미콜론인 이유: gcloud --set-env-vars 자체가 콤마로 여러 환경변수를 구분하기 때문에
#  값 안에 콤마를 쓰면 배포 명령이 깨짐)
GIFT_CHANNEL_IDS = [c.strip() for c in os.environ.get('GIFT_CHANNEL_ID', '').split(';') if c.strip()]
LOG_CHANNEL_ID  = '-1003873257156'
KST = timezone(timedelta(hours=9))

try:
    from core.firebase_handler import FirebaseHandler as _FH
    def get_db():
        return _FH().db
except ImportError:
    get_db = None

PROVIDERS = [
    ('U+유모바일',    'umobile'),
    ('LG헬로모바일',  'hello'),
    ('KT스카이라이프', 'skylife'),
    ('KT엠모바일',    'ktm'),
]


# ── 텔레그램 발송 ─────────────────────────────────────────────────────────────

def _send_telegram(msg: str, reply_markup: dict = None, channel_id: str = None):
    # channel_id를 명시하면(로그 채널 등) 그 한 곳에만, 아니면 GIFT_CHANNEL_IDS 전체에 발송
    targets = [channel_id] if channel_id else GIFT_CHANNEL_IDS
    if not TELEGRAM_TOKEN or not targets:
        print(f'  (텔레그램 미설정)\n{msg[:200]}')
        return
    import requests, json
    for cid in targets:
        payload = {'chat_id': cid, 'text': msg, 'parse_mode': 'HTML'}
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        try:
            r = requests.post(
                f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                json=payload, timeout=15)
            print(f'  발송 완료 ({r.status_code}) → {cid}')
        except Exception as e:
            print(f'  발송 실패 → {cid}: {e}')


def _log(msg: str):
    print(f'[LOG] {msg}')
    _send_telegram(msg, channel_id=LOG_CHANNEL_ID)


class TelegramLogHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        if any(k in msg for k in ['신규', '변경감지', '캐시 재사용', '완료:', '실패:']):
            _send_telegram(msg, channel_id=LOG_CHANNEL_ID)


def _setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    handler = TelegramLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('scrapers.gift_umobile_event_scraper')
    logger.addHandler(handler)
    logger.propagate = False


# ── Firestore ────────────────────────────────────────────────────────────────

def _load_prev_tier_snapshot(today_str: str) -> dict:
    """어제 gift_daily_tier → {provider: {tier: val}} 전일 비교용"""
    if not get_db: return {}
    try:
        yesterday = (date.fromisoformat(today_str) - timedelta(days=1)).isoformat()
        db  = get_db()
        doc = db.collection('gift_daily_tier').document(yesterday).get()
        if doc.exists:
            data = doc.to_dict() or {}
            # {prov_key: {tier: val}} → {provider_name: {tier: val}}
            KEY_TO_NAME = {
                'umobile': 'U+유모바일', 'hello': 'LG헬로모바일',
                'skylife': 'KT스카이라이프', 'ktm': 'KT엠모바일',
            }
            return {KEY_TO_NAME.get(k, k): v for k, v in data.items()
                    if isinstance(v, dict)}
    except Exception as e:
        print(f'  전일 스냅샷 로드 실패: {e}')
    return {}


def _save_daily_tier(moyo_plans: list, direct_band_max: dict, today_str: str,
                      ktm_direct_band_max: dict = None):
    """gift_daily_tier/{today} 에 구간별 최대값 저장 (7일 추이용)"""
    if not get_db: return
    try:
        db   = get_db()
        data = {}
        for prov_name, prov_key in PROVIDERS:
            tier_max = compute_tier_max(moyo_plans, provider=prov_name)
            data[prov_key] = {t: v for t, v in tier_max.items() if v > 0}
        # 유모바일 직영
        if direct_band_max:
            data['umobile_direct'] = {t: v for t, v in direct_band_max.items() if v > 0}
        # KT엠모바일 직영
        if ktm_direct_band_max:
            data['ktm_direct'] = {t: v for t, v in ktm_direct_band_max.items() if v > 0}
        db.collection('gift_daily_tier').document(today_str).set({
            **data,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        print(f'  gift_daily_tier/{today_str} 저장 완료')
    except Exception as e:
        print(f'  gift_daily_tier 저장 실패: {e}')


def _load_prev_datakey_snapshot(today_str: str) -> dict:
    """[추가 20260925] format_summary_report가 구간 대신 데이터제공량 단위로 바뀌면서
    전일 대비 비교도 그 단위로 해야 함 - gift_daily_tier(구간 단위, 7일 추이 기능이
    별도로 의존하므로 그대로 둠)와 별개로 gift_daily_datakey 컬렉션에서 로드."""
    if not get_db: return {}
    try:
        yesterday = (date.fromisoformat(today_str) - timedelta(days=1)).isoformat()
        db  = get_db()
        doc = db.collection('gift_daily_datakey').document(yesterday).get()
        if doc.exists:
            data = doc.to_dict() or {}
            KEY_TO_NAME = {
                'umobile': 'U+유모바일', 'hello': 'LG헬로모바일',
                'skylife': 'KT스카이라이프', 'ktm': 'KT엠모바일',
            }
            return {KEY_TO_NAME.get(k, k): v for k, v in data.items()
                    if isinstance(v, dict)}
    except Exception as e:
        print(f'  전일 데이터제공량 스냅샷 로드 실패: {e}')
    return {}


def _save_daily_datakey(moyo_plans: list, today_str: str,
                        direct_dk_max: dict = None, ktm_direct_dk_max: dict = None):
    """gift_daily_datakey/{today} 에 데이터제공량별 최대값 저장 (요약 리포트 전일 대비 +
    7일 추이 버튼용).
    [수정 20260925] 직영몰(umobile_direct/ktm_direct) 값이 빠져있어서 "📈 LG/KT 직영
    추이" 버튼이 여전히 옛 gift_daily_tier(구간 단위)만 읽어 "구간별로 나옴" 문제가
    있었음 - direct_dk_max/ktm_direct_dk_max도 함께 저장하도록 확장.
    """
    if not get_db: return
    try:
        db   = get_db()
        data = {}
        for prov_name, prov_key in PROVIDERS:
            dk_max = compute_datakey_max(moyo_plans, provider=prov_name)
            data[prov_key] = {dk: v for dk, v in dk_max.items() if v > 0}
        if direct_dk_max:
            data['umobile_direct'] = {dk: v for dk, v in direct_dk_max.items() if v > 0}
        if ktm_direct_dk_max:
            data['ktm_direct'] = {dk: v for dk, v in ktm_direct_dk_max.items() if v > 0}
        db.collection('gift_daily_datakey').document(today_str).set({
            **data,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        print(f'  gift_daily_datakey/{today_str} 저장 완료')
    except Exception as e:
        print(f'  gift_daily_datakey 저장 실패: {e}')


def _save_moyo_reports(moyo_plans: list, today: str):
    if not get_db:
        print('  (firebase_handler 미탑재 - 저장 스킵)')
        return
    db = get_db()
    for prov_name, prov_key in PROVIDERS:
        msg = format_moyo_report(moyo_plans, provider=prov_name)
        db.collection('gift_reports').document(today) \
          .collection('providers').document(prov_key).set({
              'text': msg, 'provider': prov_name,
              'updated_at': datetime.now(timezone.utc).isoformat(),
          })
    snapshot = {}
    for prov_name, _ in PROVIDERS:
        prov_plans = [p for p in moyo_plans if p['provider'] == prov_name]
        if not prov_plans: continue
        idx = build_group_index(prov_plans)
        snapshot[prov_name] = {
            f'{g["data_key"]}_{g["voice_key"]}': g['max_value']
            for g in idx.values()
        }
    db.collection('gift_snapshots').document(today).set({
        'moyo': snapshot,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    })
    print(f'  Firestore 저장: gift_reports/{today}, gift_snapshots/{today}')


def _save_umobile_detail(posts: list, today: str):
    if not get_db: return
    db    = get_db()
    lines = ['📋 U+유모바일 직영 사은품 상세\n']
    for post in posts:
        plans = [p for p in post.get('plans', []) if p.get('total_won', 0) > 0]
        if not plans: continue
        lines.append(f"📌 {post['title']}")
        if post.get('date_start') and post.get('date_end'):
            lines.append(f"   📅 {post['date_start']} ~ {post['date_end']}")
        lines.append('')
        for plan in plans:
            gb_info = f"{plan.get('total_gb','?')}GB (기본 {plan.get('base_gb','?')}GB)"
            lines.append(f"▶ {plan['plan_name']} ({gb_info})")
            for b in plan.get('benefits', []):
                amt, mon, tot = b.get('amount_won',0), b.get('months',1), b.get('total_won',0)
                cond, name    = b.get('condition',''), b.get('name','')
                if mon > 1:
                    u = f"{amt//10000}만" if amt >= 10000 else f"{amt//1000}천"
                    lines.append(f"  ✓ {cond}: {name} {u}원×{mon}개월 = {tot//10000}만원")
                else:
                    lines.append(f"  ✓ {cond}: {name} {tot//10000}만원")
            lines.append(f"  💰 합계: {plan['total_won']//10000}만원")
            lines.append('')
    detail_text = '\n'.join(lines).strip()
    db.collection('gift_reports').document(today) \
      .collection('providers').document('umobile_direct').set({
          'text': detail_text, 'provider': 'U+유모바일 직영',
          'updated_at': datetime.now(timezone.utc).isoformat(),
      })
    return detail_text


def _save_ktm_detail(posts: list, today: str):
    if not get_db: return
    db    = get_db()
    lines = ['📋 KT엠모바일 직영 사은품 상세\n']
    for post in posts:
        plans = [p for p in post.get('plans', []) if p.get('total_won', 0) > 0]
        if not plans: continue
        lines.append(f"📌 {post['title']}")
        if post.get('date_start') and post.get('date_end'):
            lines.append(f"   📅 {post['date_start']} ~ {post['date_end']}")
        lines.append('')
        for plan in plans:
            gb_info = f"{plan.get('total_gb','?')}GB (기본 {plan.get('base_gb','?')}GB)"
            lines.append(f"▶ {plan['plan_name']} ({gb_info})")
            for b in plan.get('benefits', []):
                amt, mon, tot = b.get('amount_won',0), b.get('months',1), b.get('total_won',0)
                cond, name    = b.get('condition',''), b.get('name','')
                if mon > 1:
                    u = f"{amt//10000}만" if amt >= 10000 else f"{amt//1000}천"
                    lines.append(f"  ✓ {cond}: {name} {u}원×{mon}개월 = {tot//10000}만원")
                else:
                    lines.append(f"  ✓ {cond}: {name} {tot//10000}만원")
            lines.append(f"  💰 합계: {plan['total_won']//10000}만원")
            lines.append('')
    detail_text = '\n'.join(lines).strip()
    db.collection('gift_reports').document(today) \
      .collection('providers').document('ktm_direct').set({
          'text': detail_text, 'provider': 'KT엠모바일 직영',
          'updated_at': datetime.now(timezone.utc).isoformat(),
      })
    return detail_text


def _save_kcup_details(records_by_provider: dict, today: str, run_time: str = None):
    """
    K CUP 위반 건별 상세(요금제명+프로모션 세부내역+이벤트 링크)를
    gift_reports/{today}/kcup_details/{seq} 에 저장 - 요약 메시지의 "상세보기" 버튼을
    누르면 gift_callback_handler.py가 이 seq로 조회해서 보여줌.

    [추가 20260925] "상세메시지는 링크나 버튼으로 구현" 요청 반영 - 기존엔 위반 건마다
    전체 상세를 바로 텔레그램 메시지로 발송했는데, 이제 요약 1건 + 버튼으로 바꾸면서
    상세는 눌렀을 때만 보이도록 여기 저장해둠.

    build_kcup_buttons()와 반드시 같은 순서(provider 순 → 그 안에서 GB 오름차순)로
    순회해야 seq가 버튼의 callback_data와 어긋나지 않음.
    """
    if not get_db:
        return
    db  = get_db()
    seq = 0
    for provider, records in records_by_provider.items():
        for r in records:
            detail_text = format_kcup_violation(
                r['gb_label'], '', '', r['channel_a'], r['channel_b'],
                provider=r['provider'], label_a='모요', label_b=r['direct_label'],
                compact=False, run_time=run_time)
            db.collection('gift_reports').document(today) \
              .collection('kcup_details').document(str(seq)).set({
                  'text': detail_text, 'provider': provider,
                  'gb_label': r['gb_label'], 'stage': r['stage'],
                  'updated_at': datetime.now(timezone.utc).isoformat(),
              })
            seq += 1


# ── 메인 ─────────────────────────────────────────────────────────────────────

def run():
    _setup_logging()
    start_time = datetime.now(KST)
    today      = start_time.strftime('%Y-%m-%d')
    now_str    = start_time.strftime('%Y-%m-%d  %H:%M')
    _log(f'🚀 gift-sensing-job 시작 ({start_time.strftime("%H:%M")})')

    # ── 1) 유모바일 직영 이벤트 수집 ─────────────────────────────
    print('[1/3] U+유모바일 직영 이벤트 수집...')
    _log('🎪 유모바일 직영 이벤트 수집 시작...')
    umobile_posts    = []
    direct_band_max  = {}
    direct_dk_max    = {}
    try:
        db            = get_db()
        umobile_posts = scrape_with_cache(db, max_posts=16, gift_only=True)
        cached        = sum(1 for p in umobile_posts if p.get('from_cache'))
        vision        = len(umobile_posts) - cached
        _log(f'✅ 유모바일 수집 완료: {len(umobile_posts)}건 (캐시 {cached} / Vision {vision})')
        _, _, direct_band_max, direct_dk_max = format_telegram_message(umobile_posts, now_str=now_str)
    except Exception as e:
        _log(f'❌ 유모바일 직영 수집 실패: {e}')

    # ── 1.5) KT엠모바일 직영 이벤트 수집 ─────────────────────────
    print('[1.5/3] KT엠모바일 직영 이벤트 수집...')
    _log('🏪 KT엠모바일 직영 이벤트 수집 시작...')
    ktm_posts         = []
    ktm_direct_band_max = {}
    ktm_direct_dk_max = {}
    try:
        ktm_posts = scrape_ktm_with_cache(db, max_posts=22, gift_only=True)
        cached    = sum(1 for p in ktm_posts if p.get('from_cache'))
        vision    = len(ktm_posts) - cached
        _log(f'✅ KT엠모바일 수집 완료: {len(ktm_posts)}건 (캐시 {cached} / Vision {vision})')
        _, _, ktm_direct_band_max, ktm_direct_dk_max = format_ktm_telegram_message(ktm_posts, now_str=now_str)
    except Exception as e:
        _log(f'❌ KT엠모바일 직영 수집 실패: {e}')

    # ── 2) 모요 수집 ─────────────────────────────────────────────
    print('[2/3] 모요 자회사 사은품 수집...')
    try:
        moyo_plans = scrape_moyo_gifts()
        by_prov    = {}
        for p in moyo_plans:
            by_prov[p['provider']] = by_prov.get(p['provider'], 0) + 1
        prov_log = ' | '.join(f'{k} {v}건' for k, v in sorted(by_prov.items()))
        _log(f'✅ 모요 수집 완료: 총 {len(moyo_plans)}건\n{prov_log}')
    except Exception as e:
        _log(f'❌ 모요 수집 실패: {e}')
        raise

    # ── 3) 저장 + 발송 ───────────────────────────────────────────
    print('[3/3] 저장 + 텔레그램 발송...')

    # 전일 스냅샷 로드 (구간 단위는 7일 추이 기능용, 데이터제공량 단위는 요약 리포트용)
    prev_snapshot = _load_prev_tier_snapshot(today)
    prev_datakey_snapshot = _load_prev_datakey_snapshot(today)

    # Firestore 저장
    try:
        _save_moyo_reports(moyo_plans, today)
        _save_daily_tier(moyo_plans, direct_band_max, today,
                          ktm_direct_band_max=ktm_direct_band_max)
        _save_daily_datakey(moyo_plans, today,
                            direct_dk_max=direct_dk_max, ktm_direct_dk_max=ktm_direct_dk_max)
        _log(f'✅ Firestore 저장 완료')
    except Exception as e:
        _log(f'❌ Firestore 저장 실패: {e}')

    # 요약 메시지 + 버튼 (상세 4개 + 추이 버튼)
    summary = format_summary_report(moyo_plans, prev_snapshot=prev_datakey_snapshot)
    moyo_keyboard = {
        'inline_keyboard': [
            [
                {'text': '📱 U+유모바일',    'callback_data': f'gift_{today}_umobile'},
                {'text': '📱 LG헬로모바일',  'callback_data': f'gift_{today}_hello'},
            ],
            [
                {'text': '📱 KT스카이라이프', 'callback_data': f'gift_{today}_skylife'},
                {'text': '📱 KT엠모바일',    'callback_data': f'gift_{today}_ktm'},
            ],
            [
                {'text': '📈 LG 7일 추이',  'callback_data': 'gift_trend_umobile'},
                {'text': '📈 KT 7일 추이',  'callback_data': 'gift_trend_ktm'},
            ],
        ]
    }
    _send_telegram(summary, reply_markup=moyo_keyboard)
    _log('✅ 모요 요약 메시지 발송 완료')

    # 유모바일 직영 이벤트 메시지
    try:
        _save_umobile_detail(umobile_posts, today)
        text, buttons, _, _ = format_telegram_message(umobile_posts, now_str=now_str)
        text = text.replace('  U+유모바일: ', '  ')
        event_btns = [{'text': b['text'], 'url': b['url']}
                      for b in buttons if b.get('url')][:3]
        umobile_keyboard = {
            'inline_keyboard': (
                [[{'text': '📋 상세보기',
                   'callback_data': f'gift_{today}_umobile_direct'}]]
                + [[b] for b in event_btns]
            )
        }
        _send_telegram(text, reply_markup=umobile_keyboard)
        _log('✅ 유모바일 이벤트 메시지 발송 완료')
    except Exception as e:
        _log(f'❌ 유모바일 발송 실패: {e}')

    # KT엠모바일 직영 이벤트 메시지
    try:
        _save_ktm_detail(ktm_posts, today)
        ktm_text, ktm_buttons, _, _ = format_ktm_telegram_message(ktm_posts, now_str=now_str)
        ktm_event_btns = [{'text': b['text'], 'url': b['url']}
                           for b in ktm_buttons if b.get('url')][:3]
        ktm_keyboard = {
            'inline_keyboard': (
                [[{'text': '📋 상세보기',
                   'callback_data': f'gift_{today}_ktm_direct'}]]
                + [[b] for b in ktm_event_btns]
            )
        }
        _send_telegram(ktm_text, reply_markup=ktm_keyboard)
        _log('✅ KT엠모바일 이벤트 메시지 발송 완료')
    except Exception as e:
        _log(f'❌ KT엠모바일 발송 실패: {e}')

    # 모요 vs 직영 비교 (사업자별로 메시지 분리, 각자 추이 버튼 2개)
    if direct_dk_max:
        try:
            umobile_vs_msg = format_moyo_vs_direct(
                moyo_plans, direct_dk_max,
                provider='U+유모바일', direct_label='유모바일직영')
            umobile_vs_keyboard = {
                'inline_keyboard': [[
                    {'text': '📈 모요(유모바일) 추이', 'callback_data': 'gift_trend_umobile'},
                    {'text': '📈 유모바일 직영 추이', 'callback_data': 'gift_trend_umobile_direct'},
                ]]
            }
            _send_telegram(umobile_vs_msg, reply_markup=umobile_vs_keyboard)
            _log('✅ 모요 vs 유모바일직영 비교 발송 완료')
        except Exception as e:
            _log(f'❌ 유모바일 비교 메시지 실패: {e}')

    if ktm_direct_dk_max:
        try:
            ktm_vs_msg = format_moyo_vs_direct(
                moyo_plans, ktm_direct_dk_max,
                provider='KT엠모바일', direct_label='엠모바일직영')
            ktm_vs_keyboard = {
                'inline_keyboard': [[
                    {'text': '📈 모요(엠모바일) 추이', 'callback_data': 'gift_trend_ktm'},
                    {'text': '📈 엠모바일 직영 추이', 'callback_data': 'gift_trend_ktm_direct'},
                ]]
            }
            _send_telegram(ktm_vs_msg, reply_markup=ktm_vs_keyboard)
            _log('✅ 모요 vs 엠모바일직영 비교 발송 완료')
        except Exception as e:
            _log(f'❌ 엠모바일 비교 메시지 실패: {e}')


    # K CUP 경품 편차 위반 특이사항
    # [수정 20260925] 건별로 전체 상세를 따로 발송하던 방식 → 요약 1건(단계별 건수 +
    # GB:금액 목록) + 상세는 "상세보기" 버튼으로 분리 (사장님 요청: "상세메시지는
    # 링크나 버튼으로 구현"). 상세 본문은 _save_kcup_details()가 Firestore에 미리
    # 저장해두고, 버튼 클릭 시 gift_callback_handler.py가 조회해서 보여줌.
    try:
        kcup_run_time = start_time.strftime('%-m/%-d %H시')
        records_by_provider = {
            'KT엠모바일': build_kcup_records(
                moyo_plans, ktm_posts,
                moyo_provider='KT엠모바일', direct_label='KT엠모바일 직영'),
            'U+유모바일': build_kcup_records(
                moyo_plans, umobile_posts,
                moyo_provider='U+유모바일', direct_label='U+유모바일 직영'),
        }
        kcup_summary  = format_kcup_summary(records_by_provider, run_time=kcup_run_time)
        kcup_total    = sum(len(r) for r in records_by_provider.values())
        if kcup_total:
            _save_kcup_details(records_by_provider, today, run_time=kcup_run_time)
            kcup_keyboard = {'inline_keyboard': build_kcup_buttons(records_by_provider, today)}
            _send_telegram(kcup_summary, reply_markup=kcup_keyboard)
        else:
            _send_telegram(kcup_summary)
        _log(f'✅ K CUP 특이사항 발송 완료 ({kcup_total}건)')
    except Exception as e:
        _log(f'❌ K CUP 비교 실패: {e}')

    elapsed = (datetime.now(KST) - start_time).seconds
    _log(f'🏁 gift-sensing-job 완료 (소요 {elapsed}초)')
    print('완료')


if __name__ == '__main__':
    run()