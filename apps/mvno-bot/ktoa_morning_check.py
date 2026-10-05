"""
ktoa_morning_check.py  v2.2
작성일: 2026-05-08

[수정 이력]
v2.2 | 2026-05-20 | 전송 채팅방 변경 → 팀 전체방(-1003814217559)
v2.1 | 2026-05-19 | 차이 건수 기준 제거 → 차이 있으면 무조건 DB 업데이트
  - DIFF_THRESHOLD 제거
  - 차이 있으면 항상 DB 업데이트 + 변동 내용 + 수정 일마감 메시지 → 전체방
  - 검증 결과: 재검증값(20:25)이 실무자 엑셀과 완전 일치 확인 (2026-05-18)
v2.0 | 2026-05-09 | 구조 전면 변경 - check_and_notify() 함수만 제공
v1.5 | 2026-05-08 | login() 후 팝업 추가 체크 로직 추가
v1.4 | 2026-05-08 | navigate_to_stats 로컬 구현으로 변경
v1.3 | 2026-05-08 | 날짜 로직 변경 - 사이트 날짜 기준으로 ktoa_daily 조회
v1.2 | 2026-05-08 | navigate_to_stats 실패 시 재시도 로직 추가
v1.1 | 2026-05-08 | 스크래핑 함수 ktoa_scraper.py에서 import로 변경
v1.0 | 2026-05-08 | 최초 작성
"""

import os
import logging
import requests
from datetime import datetime, timezone, timedelta

from ktoa_firestore import save_ktoa_daily, get_previous_daily_for_closing, _get_db
from ktoa_telegram import calc_stats, build_closing_message

log = logging.getLogger(__name__)

KST            = timezone(timedelta(hours=9))
PERSONAL_CHAT  = "-1003814217559"


def _already_notified_nochange(date_str: str) -> bool:
    """[버그수정, Claude] 사이트가 연휴 등으로 여러 날 같은 날짜에 멈춰 있으면
    check_and_notify()가 스케줄(08:00/20:25)마다 "재검증 완료 (날짜) 변경 없음"을
    계속 재전송해서 스팸이 되던 문제(사장님 지적: "영업일 없는날에 계속오네") -
    diff=0으로 이미 한 번 알린 날짜는 다시 알리지 않도록 가드."""
    try:
        doc = _get_db().collection('ktoa_daily').document(date_str).get()
        return bool(doc.exists and doc.to_dict().get('_recheck_nochange_notified'))
    except Exception as e:
        log.warning(f"_already_notified_nochange 조회 실패 (무시하고 진행): {e}")
        return False


def _mark_notified_nochange(date_str: str) -> None:
    try:
        _get_db().collection('ktoa_daily').document(date_str).set(
            {'_recheck_nochange_notified': True}, merge=True)
    except Exception as e:
        log.warning(f"_recheck_nochange_notified 마킹 실패: {e}")


def _send(text: str) -> None:
    """팀 전체방으로 전송"""
    token = os.environ.get('TELEGRAM_TOKEN', '')
    if not token:
        log.warning("TELEGRAM_TOKEN 없음 — 전송 스킵")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": PERSONAL_CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        log.info(f"텔레그램 응답: {resp.status_code} | {resp.json()}")
    except Exception as e:
        log.error(f"텔레그램 전송 실패: {e}")


def _fmt_diff(label: str, old: int, new: int) -> str:
    diff = new - old
    sign = "+" if diff >= 0 else ""
    return f"{label}: {old:,} → {new:,} ({sign}{diff:,})"


def check_and_notify(stats: dict, daily: dict, date_str: str) -> None:
    """
    스크랩한 stats와 저장된 daily(ktoa_daily) 비교.
    차이 있으면: DB 업데이트 + 변경 내용 + 수정 일마감 메시지 → 개인채널
    차이 없음: "재수집 결과 동일" 알림 → 개인채널
    """
    log.info(f"=== DB 재검증 시작: {date_str} ===")

    new_total = stats.get('total', 0)
    old_total = daily.get('total', 0)
    diff      = abs(new_total - old_total)

    log.info(f"DB total: {old_total:,} | 재수집 total: {new_total:,} | 차이: {diff:,}")

    # 변동 없음
    if diff == 0:
        if _already_notified_nochange(date_str):
            log.info(f"변동 없음 + 이미 알림 완료 ({date_str}) → 조용히 종료")
            return
        log.info("변동 없음 → 종료")
        _send(f"✅ *KTOA 재검증 완료* ({date_str})\n재수집 결과 동일 — 변경 없음")
        _mark_notified_nochange(date_str)
        return

    # 변동 항목 계산
    new_c   = calc_stats(stats.get('matrix', {}))
    old_mi  = daily.get('mvno_in',    {})
    old_mo  = daily.get('mvno_out',   {})
    old_mno = daily.get('mno_out',    {})
    old_net = daily.get('net_change', {})

    new_mi  = new_c['mvno_in']
    new_mo  = new_c['mvno_out']
    new_mno = new_c['mno_out']
    new_net = new_c['net']

    diff_lines = [f"*KTOA 일마감 재검증* ({date_str})\n"]
    diff_lines.append(f"총계: {old_total:,} → {new_total:,} (*{diff:+,}건*)\n")

    if any(old_mi.get(k, 0) != new_mi.get(k, 0) for k in ['SM', 'KM', 'LM']):
        diff_lines.append("◎ MVNO IN\n" + "\n".join([
            _fmt_diff("SM", old_mi.get('SM', 0), new_mi.get('SM', 0)),
            _fmt_diff("KM", old_mi.get('KM', 0), new_mi.get('KM', 0)),
            _fmt_diff("LM", old_mi.get('LM', 0), new_mi.get('LM', 0)),
        ]))

    if any(old_mno.get(k, 0) != new_mno.get(k, 0) for k in ['S', 'K', 'L']):
        diff_lines.append("\n◎ MNO Out\n" + "\n".join([
            _fmt_diff("S",  old_mno.get('S', 0), new_mno.get('S', 0)),
            _fmt_diff("K",  old_mno.get('K', 0), new_mno.get('K', 0)),
            _fmt_diff("L",  old_mno.get('L', 0), new_mno.get('L', 0)),
        ]))

    if any(old_net.get(k, 0) != new_net.get(k, 0) for k in ['SM', 'KM', 'LM', 'S', 'K', 'L']):
        diff_lines.append("\n◎ 순증감\n" + "\n".join([
            _fmt_diff("SM", old_net.get('SM', 0), new_net.get('SM', 0)),
            _fmt_diff("KM", old_net.get('KM', 0), new_net.get('KM', 0)),
            _fmt_diff("LM", old_net.get('LM', 0), new_net.get('LM', 0)),
            _fmt_diff("S",  old_net.get('S',  0), new_net.get('S',  0)),
            _fmt_diff("K",  old_net.get('K',  0), new_net.get('K',  0)),
            _fmt_diff("L",  old_net.get('L',  0), new_net.get('L',  0)),
        ]))

    # 차이 있으면 항상 DB 업데이트
    log.info(f"차이 {diff}건 → DB 업데이트 진행")

    stats['date'] = date_str
    try:
        updated_daily = save_ktoa_daily(stats)
        log.info(f"ktoa_daily 업데이트 완료: {date_str}")
    except Exception as e:
        log.error(f"ktoa_daily 업데이트 실패: {e}")
        diff_lines.append(f"\n❌ DB 업데이트 실패: {e}")
        _send("\n".join(diff_lines))
        return

    diff_lines.append("\n✅ DB 업데이트 완료 → 수정 일마감 메시지 재전송")
    _send("\n".join(diff_lines))

    # 수정된 일마감 메시지 재전송
    try:
        prev_daily = get_previous_daily_for_closing(date_str)
        msg_text   = build_closing_message(updated_daily, prev_daily)
        # 일마감 메시지는 parse_mode 없이 전송 (특수문자 파싱 오류 방지)
        token = os.environ.get('TELEGRAM_TOKEN', '')
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": PERSONAL_CHAT, "text": f"📋 수정 일마감 메시지 ({date_str})\n\n{msg_text}"},
            timeout=10,
        )
        log.info("수정 일마감 메시지 전송 완료")
    except Exception as e:
        log.error(f"일마감 메시지 재전송 실패: {e}")
        _send(f"⚠️ 일마감 메시지 재전송 실패: {e}")

    log.info(f"=== DB 재검증 완료: {date_str} ===")