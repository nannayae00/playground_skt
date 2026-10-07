"""
ktoa_scraper.py  v3.16
작성일: 2026-03-16

[수정 이력]
v3.16 | 2026-09-20 | 일마감 메시지 중복발송 + 휴무일 오발송 버그 수정 (Claude)
  1) 중복발송: ktoa-collector-closing-main(20:01)/-backup(20:11) 스케줄러가
     10분 간격으로 같은 job을 트리거하는데 Selenium 스크래핑이 그보다 오래
     걸리면 두 실행이 겹쳐서 텔레그램 발송이 중복되던 문제 + maxRetries=3인
     Cloud Run Job이 발송 이후 단계 실패 시 스크립트를 처음부터 재시도하면서
     RECHECK(20:25)의 "수정 일마감" 메시지도 가드 없이 재발송되던 문제.
     _claim_once()/_claim_closing_send()/_claim_recheck_send() 원자적 claim
     추가해서 두 send_closing_message()/build_closing_message 호출 지점,
     RECHECK 두 곳(인라인 + _recheck_scrape_and_close) 전부 적용.
  2) 휴무일 오발송: "전일과 동일 데이터→공휴일/미갱신 스킵" 체크가 정시(else)
     경로에만 있어서, 일요일처럼 사이트가 ref_hour>=20으로 찍히면서 토요일
     데이터를 그대로 들고 있으면(site_date는 오늘로 나와 날짜체크 통과)
     일요일 마감 메시지가 토요일 실적으로 잘못 발송되던 문제 - 마감(if
     ref_hour>=20) 경로 최상단에도 동일 체크 추가.
v3.15 | 2026-08-07 | 로그인 비밀번호 후보 순차 시도로 변경. 비밀번호가
  3개월마다 사람이 수동으로 3개 값(ghkddbsrn1!/2!/3!) 중 하나로 바꾸는
  방식이라 날짜 기반 예측이 불가능함(brand-report/ktoa_mvno_scraper.py와
  동일 KTOA 계정 공유, 그쪽에서 먼저 발견/수정한 문제를 여기도 동일 적용).
  KTOA_USER_PW_CANDIDATES 환경변수(콤마구분, 3개 값 등록)를 두고 login()이
  순서대로 시도하다가 로그인 폼(#userid)이 사라지는 시점(=성공)에서 멈춤 -
  실패로 추정되면 다음 후보로 자동 재시도. 기존 KTOA_USER_PW 단일값도
  하위호환 유지.
  ⚠️ 이 파일을 쓰는 Cloud Run Job(ktoa-collector, brand-report와 별도 배포)의
  환경변수도 KTOA_USER_PW_CANDIDATES="ghkddbsrn1!,ghkddbsrn2!,ghkddbsrn3!"로
  갱신 필요(재배포 시 반영).
v3.11 | 2026-06-02 | _trio() avg_s 제거 → rolling_avg 통일
  - low/mid/high 모두 rolling_avg 사용, bw만 다르게
  - avg_s(단순평균) 제거 → 월초 과대계산 문제 해결
  - low ≤ mid ≤ high 자연 보장
v3.10 | 2026-06-01 | _save_all_fc_to_daily() 이중가중 avg 적용
  - _trio(): T-Out 비율 환산 제거 → 항목별 독립 이중가중 avg
    · hist_items: 항목별 [(val,bw),...] 오래된순 수집
    · forecast_engine._calc_weighted_avg() 호출 (bw정규화 × 일자감쇠 5→0.5)
  - SM_IN/KM_IN/LM_IN/SM_OUT/KM_OUT/LM_OUT 각 독립 avg 계산
v3.9 | 2026-05-20 | CONTEXT_BACKFILL 모드 추가
  - CONTEXT_BACKFILL=1: 스크래핑 없이 ktoa_context만 재생성
  - TARGET_DATE 환경변수로 날짜 지정 (기본: today_str)
  - 기존 모든 동작 완전 그대로 유지
v3.14 | 2026-06-12 | RECHECK 시간대별 역할 재분리 (20:25 vs 08:00)
  - 20:25 (당일, 실제 변경 발생 시점): fc재계산 + 수정 일마감 메시지 + 엑셀 전송
  - 08:00 (익일, 영업 전): 기존처럼 변경사항 체크/알림만 (fc재계산/엑셀 제거)
  - hour==20 (20:25) 일 때만 ⑤ 블록 실행, hour==8은 ③④만 수행
v3.13 | 2026-06-11 | 20:01/8:25 역할 분리 - 엑셀은 8:25에만 전송
  - 20:01: 패턴저장 → predict_monthly → _save_all_fc_to_daily → daily 재조회
           → 일마감 메시지 전송 (엑셀 전송 제거)
  - 8:25 RECHECK: 재수집 → predict_monthly + _save_all_fc_to_daily 재실행
           → 수정 일마감 메시지 전송 + 엑셀 전송 (이때 처음 전송)
v3.12 | 2026-06-11 | _trio() avg 4종(avg5/avg10 × rbw_ai/rbw_man) → sorted → low/mid/high
  - forecast_engine v2.7과 동일 로직 (cum 기준은 daily의 cum_* 그대로 사용)
  - _ravg(hist_item): avg5(max_w=5.0), avg10(max_w=10.0) 둘 다 반환
  - _trio(): p1=avg5×rbw_ai, p2=avg5×rbw_man, p3=avg10×rbw_ai, p4=avg10×rbw_man
            sorted([p1,p2,p3,p4]) → low=min, high=max, mid=중간2개 평균
v3.9 | 2026-06-10 | _save_all_fc_to_daily() rbw B방식으로 통일 (forecast_engine과 동일)
  - rbw: total - elapsed (last_biz 제거) → 월말 수렴 개선
  - rbw_ai = total_ai - elapsed / rbw_man = total_man - elapsed
  - rbw_w2 = (rbw_ai + rbw_man) / 2 (중간값)
  - _trio() 내부 정렬 보장: sorted([low, mid, high])
v3.8 | 2026-05-15 | _save_all_fc_to_daily() bw 계산 forecast_engine/엑셀과 통일
  - 경과bw: bw_ai_prev 고정 (w1~w3 미사용)
  - 잔여bw: total - elapsed + last_biz_bw (엑셀 방식, 오늘 포함)
  - avg: 단순평균(low) + 최근5일 가중평균(mid/high) 분리
v3.7 | 2026-05-14 | _trio() 경과bw 계산 우선순위 통일 (forecast_engine과 동일)
  - 경과bw: bw_ai_w3 > bw_ai_w2 > bw_ai_w1 > bw_ai_prev > bw_manual > get_bw_final()
v3.6 | 2026-05-13 | AI 컨텍스트 메시지 생성/저장 추가
  - _save_context_message(): ktoa_context/{date} 에 AI 질의응답용 컨텍스트 텍스트 저장
    · 영업일수/시장사이즈/T Out/SM순증감/MVNO IN·OUT/MNO Out/순증감 제로섬
    · 최근 4주 동일요일 bw보정 비교, 전월동기, 5영업일 트렌드, 목표현황, AI해석가이드
    · 모든 수치 Python 계산 완료 → AI는 해석만 수행
  - 일마감 흐름: _save_all_fc_to_daily() 후 fc 반영된 daily 재조회 → 컨텍스트 저장
v3.6 | 2026-05-13 | AI 컨텍스트 메시지 저장 연동
  - 일마감 흐름: _save_all_fc_to_daily() 후 save_context_message() 호출
  - 컨텍스트 생성 로직은 ktoa_context_builder.py로 분리
v3.6 | 2026-05-17 | _run_recheck 구조 변경 - site_date 기준으로 DB 조회
  - 스크래핑 먼저 → site_date 확인 → 해당 날짜 ktoa_daily 조회
  - 영업 안 하는 날/비영업일에도 정상 동작 (today_str 의존 제거)
  - _telegram_sent=False 시 전체방 재발송 대신 개인채널 알림만
  - _recheck_scrape_and_close() 호출 제거 (전체방 발송 방지)
v3.5 | 2026-05-09 | RECHECK_MODE 추가 (20:25 DB 재검증)
  - RECHECK_MODE=true: 일마감 미완료 재처리 + DB값 vs 재수집값 비교
  - RECHECK_MODE=false (기본): 기존 로직 완전 그대로
v3.4 | 2026-05-09 | 일마감 후 DB 재검증 (ktoa_morning_check.check_and_notify 호출)
  - 일마감 완료 후 check_and_notify(stats, daily, today_str) 호출
  - 스크래핑 값과 저장된 DB값 비교 → 차이 있으면 개인채널 알림
  - 실패해도 Job 크래시 방지 (try/except)
v3.4 | 2026-05-09 | 일마감 후 fc_ 전항목 Firestore 저장 + 마감 재처리 모드
  - _save_all_fc_to_daily(): MVNO IN/MNO Out/MVNO Out/순증감 Low/Mid/High 전항목 저장
    · 순증감 예측 = MVNO IN 예측 - MVNO OUT 예측
    · ktoa_daily에 fc_mvno_in/fc_mno_out/fc_mvno_out/fc_net 필드 추가
  - FORCE_CLOSING=1: 스크래핑 없이 DB 데이터로 일마감 재처리 (fc_ 저장 + 엑셀 전송)
v3.3 | 2026-04-21 | 엑셀 리포트 전송 분리 (REPORT_MODE=excel)
v3.2 | 2026-04-21 | 엑셀/패턴/예측 try 블록 분리
v3.1 | 2026-04-20 | 일마감 엑셀 그룹 채팅방 동시 전송
v3.0 | 2026-04-08 | 시간별 예측값 Firestore 저장 + 정확도 개선
v2.2 | 2026-04-03 | bw_ai_prev만 있는 ktoa_daily 문서 처리 개선
v2.1 | 2026-04-03 | send_closing_message 에러 시 Job 크래시 방지
v2.0 | 2026-04-03 | 20시 마감 텔레그램 미발송 버그 수정
v1.9 | 2026-04-01 | 일마감 시 예측 엑셀 리포트 생성 + 텔레그램 전송
v1.8 | 2026-03-21 | 전일 마감 total 비교로 공휴일/일요일 스킵 추가
v1.7 | 2026-03-21 | 중복 체크 방식 변경 (reference_time → total 값 비교)
v1.6 | 2026-03-19 | calc_streak 호출 파라미터 변경 (v3.2 대응)
v1.5 | 2026-03-19 | 전 시간 대비 화살표용 직전 데이터 전달
v1.4 | 2026-03-18 | 사이트 날짜 체크 + 스케줄 대응
v1.3 | 2026-03-16 | 20시 일마감 처리 추가
v1.2 | 2026-03-16 | 중복 방지 로직 추가
v1.1 | 2026-03-16 | navigate_to_stats 수정
v1.0 | 2026-03-16 | 최초 작성
"""

import os
import re
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ktoa_parser import parse_ktoa_excel
from ktoa_firestore import (
    save_ktoa_to_firestore,
    save_ktoa_daily,
    get_latest_total,
    get_previous_hourly,
    calc_streak,
    get_previous_daily_for_closing,
)
from ktoa_telegram import send_ktoa_message, send_closing_message, build_closing_message, _send as _tg_send
from ktoa_context_builder import save_context_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

SITE_URL     = "https://comstat.ktoa.or.kr/main.do"
USER_ID      = os.environ["KTOA_USER_ID"]
DOWNLOAD_DIR = "/tmp/ktoa_downloads"
KST          = timezone(timedelta(hours=9))


def _claim_once(date_str: str, sent_field: str, claim_field: str, ttl_seconds: int = 900) -> bool:
    """[버그수정, Claude] 텔레그램 메시지 중복발송 방지 - 원자적 claim (범용).

    두 가지 실제 중복발송 경로를 모두 이걸로 막음:
    1) ktoa-collector-closing-main(20:01)/-backup(20:11) 두 스케줄러가 같은
       job을 10분 간격으로 트리거하는데, Selenium 로그인+다운로드+파싱이
       10분을 넘기면 두 실행이 겹치면서 둘 다 "아직 발송 안 됨"으로 보고
       중복 발송 (calendar-bot에서 겪은 것과 동일한 TOCTOU 경합)
    2) Cloud Run Job maxRetries=3 - RECHECK(20:25)의 "수정 일마감" 메시지
       전송 뒤 같은 실행 안에서 나중 단계(fc 재계산 등)가 실패/타임아웃하면
       Cloud Run이 스크립트를 처음부터 재시도 → 이미 보낸 "수정 일마감"을
       가드 없이 또 보냄

    sent_field: 실제 발송 성공 후에만 세팅되는 필드 (RECHECK가 참조하는
    _telegram_sent와 혼동되지 않도록 메시지 종류별로 다른 필드명 사용).
    claim_field: 발송 "시도"를 원자적으로 선점하는 필드 - 두 번째 실행은
    시도조차 못 하게 막음. 크래시로 클레임만 찍히고 발송이 안 된 경우를
    대비해 ttl_seconds 지나면 클레임 만료로 재시도 허용.
    """
    import time as _time
    from google.cloud import firestore as _fs
    from ktoa_firestore import _get_db as _fdb_claim
    db = _fdb_claim()
    doc_ref = db.collection('ktoa_daily').document(date_str)

    @_fs.transactional
    def _txn(transaction, ref):
        snap = ref.get(transaction=transaction)
        data = snap.to_dict() if snap.exists else {}
        if data.get(sent_field):
            return False  # 이미 실제 발송 완료
        claimed_at = data.get(claim_field)
        now = _time.time()
        if claimed_at and (now - claimed_at) < ttl_seconds:
            return False  # 다른 실행이 방금(ttl 이내) 클레임 - 진행 중으로 간주
        transaction.set(ref, {claim_field: now}, merge=True)
        return True

    return _txn(db.transaction(), doc_ref)


def _claim_closing_send(date_str: str, ttl_seconds: int = 900) -> bool:
    """20:01/20:11 원래 일마감 메시지 발송 claim."""
    return _claim_once(date_str, '_telegram_sent', '_closing_send_claimed_at', ttl_seconds)


def _claim_recheck_send(date_str: str, ttl_seconds: int = 900) -> bool:
    """20:25 RECHECK "수정 일마감" 메시지 발송 claim (원래 일마감과 별개 플래그)."""
    return _claim_once(date_str, '_recheck_msg_sent', '_recheck_msg_claimed_at', ttl_seconds)


def _claim_recheck_excel(date_str: str, ttl_seconds: int = 900) -> bool:
    """[버그수정, Claude] 20:25 RECHECK 엑셀 전송 claim (텍스트 메시지와 별개 플래그).

    사이트가 연휴 등으로 여러 날 동일 site_date에 멈춰 있으면 RECHECK(20:25)가
    같은 날짜를 매일 다시 처리하는데, "수정 일마감" 텍스트는 _claim_recheck_send로
    막혀 있었지만 그 아래 엑셀 전송 코드엔 가드가 전혀 없어서 사이트가 멈춰
    있는 날마다 같은 날짜 엑셀이 계속 재전송되던 문제(사장님 지적: "일마감메시지는
    여전히 두번씩와"). 날짜당 최초 1회만 보내도록 별도 claim 추가.
    """
    return _claim_once(date_str, '_recheck_excel_sent', '_recheck_excel_claimed_at', ttl_seconds)


def _get_pw_candidates() -> list:
    """
    비밀번호가 3개월마다 사람이 수동으로 3개 값 중 하나로 바꾸는 방식이라
    (날짜 기반 패턴 없음 - 2026-08-07 확인, brand-report/ktoa_mvno_scraper.py와
    동일 계정 공유하므로 그쪽과 동일 로직 적용) 미리 계산해서 맞힐 수 없음.
    KTOA_USER_PW_CANDIDATES(콤마 구분 - 3개 값 다 등록)를 두고 로그인 시
    순서대로 시도하다가 성공하는 값을 씀. 없으면 기존 KTOA_USER_PW
    단일값(하위호환).
    """
    candidates_env = os.environ.get("KTOA_USER_PW_CANDIDATES")
    if candidates_env:
        return [p.strip() for p in candidates_env.split(",") if p.strip()]
    return [os.environ["KTOA_USER_PW"]]


def _extract_hour(ref_time: str) -> int:
    m = re.search(r'(\d+)시', ref_time)
    return int(m.group(1)) if m else -1


def get_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    })
    driver = webdriver.Chrome(options=options)
    # [수정 20261005] 페이지 로드 제한 60초 - KTOA 무응답 시 5분씩 매달리지 않도록
    driver.set_page_load_timeout(int(os.environ.get('KTOA_PAGE_LOAD_TIMEOUT', '60')))
    return driver


# [수정 20261005] 수집 장애 알림 - 연속 실패가 20분 이상 이어지면 개인채널로 1회 알림,
# 복구되면 복구 알림. 상태는 ktoa_health/collector 문서에 저장 (재시도 횟수와 무관하게 시간 기준)
_HEALTH_ALERT_AFTER_MIN = int(os.environ.get('KTOA_ALERT_AFTER_MIN', '20'))


def _health_ref():
    from ktoa_firestore import _get_db as _fdb_h
    return _fdb_h().collection('ktoa_health').document('collector')


def _health_alert(text: str) -> None:
    try:
        from ktoa_morning_check import _send as _h_send
        _h_send(text)
    except Exception as e:
        log.error(f"장애 알림 전송 실패: {e}")


def _record_scrape_failure(err: Exception) -> None:
    try:
        ref = _health_ref()
        now = datetime.now(KST)
        doc = ref.get()
        data = doc.to_dict() if doc.exists else {}
        first = data.get('first_fail_at') or now
        if hasattr(first, 'astimezone'):
            first = first.astimezone(KST)
        count = int(data.get('fail_count', 0)) + 1
        update = {'first_fail_at': first, 'last_fail_at': now, 'fail_count': count,
                  'last_error': f"{type(err).__name__}: {str(err)[:200]}"}
        mins = (now - first).total_seconds() / 60
        if not data.get('alerted') and mins >= _HEALTH_ALERT_AFTER_MIN:
            _health_alert(
                f"⚠️ KTOA 수집 장애\n"
                f"{first.strftime('%H:%M')}부터 {int(mins)}분째 실패 ({count}회)\n"
                f"원인: {type(err).__name__} (KTOA 사이트 응답 없음 가능성)\n"
                f"→ 실적 메시지 발송 중단 중, 복구되면 다시 알림")
            update['alerted'] = True
        ref.set(update, merge=True)
    except Exception as e:
        log.error(f"장애 상태 기록 실패: {e}")


def _record_scrape_success() -> None:
    try:
        ref = _health_ref()
        doc = ref.get()
        if not doc.exists or not doc.to_dict().get('fail_count'):
            return
        data = doc.to_dict()
        if data.get('alerted'):
            first = data['first_fail_at'].astimezone(KST)
            now = datetime.now(KST)
            _health_alert(
                f"✅ KTOA 수집 복구\n"
                f"장애 {first.strftime('%H:%M')} ~ {now.strftime('%H:%M')} "
                f"({int((now - first).total_seconds() // 60)}분, 실패 {data.get('fail_count')}회)")
        ref.set({'fail_count': 0, 'first_fail_at': None, 'alerted': False,
                 'recovered_at': datetime.now(KST)}, merge=True)
    except Exception as e:
        log.error(f"장애 상태 초기화 실패: {e}")


def login(driver: webdriver.Chrome) -> None:
    """
    비밀번호 후보(_get_pw_candidates())를 순서대로 시도 - 로그인 폼(#userid)이
    시도 후에도 여전히 남아있으면 실패로 간주하고 다음 후보로 넘어감.
    (brand-report/ktoa_mvno_scraper.py v1.9와 동일 로직 - 같은 KTOA 계정을
    공유하므로 비밀번호 회전 시 두 파일 다 이 방식으로 대응해야 함)
    """
    candidates = _get_pw_candidates()

    for i, pw in enumerate(candidates, 1):
        log.info(f"로그인 시도 {i}/{len(candidates)}번째 비밀번호 후보...")
        driver.get(SITE_URL)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.ID, "userid")))
        driver.find_element(By.ID, "userid").clear()
        driver.find_element(By.ID, "userid").send_keys(USER_ID)
        driver.find_element(By.ID, "pass").clear()
        driver.find_element(By.ID, "pass").send_keys(pw)
        driver.find_element(By.XPATH, "//img[@alt='보내기']").click()
        time.sleep(4)

        try:
            driver.find_element(By.ID, "userid")
            login_failed = True
        except Exception:
            login_failed = False

        if not login_failed:
            log.info(f"로그인 성공 ({i}번째 비밀번호 후보)")
            try:
                driver.find_element(By.XPATH, '//*[@id="myPopup"]/div/span[1]').click()
                log.info("팝업 닫기 완료")
                time.sleep(1)
            except Exception:
                pass
            log.info("로그인 완료")
            return

        log.warning(f"로그인 실패로 추정({i}번째 비밀번호 후보) - 다음 후보로 재시도")

    raise RuntimeError(
        f"비밀번호 후보 {len(candidates)}개 전부 로그인 실패 - "
        f"KTOA_USER_PW_CANDIDATES 최신값 확인 필요(3개월 주기 변경)"
    )


def navigate_to_stats(driver: webdriver.Chrome) -> None:
    log.info("메뉴 이동: 금일자통계 → 번호이동 현황")
    wait = WebDriverWait(driver, 15)
    driver.find_element(By.XPATH, '//*[@id="menuPart0"]/div').click()
    time.sleep(1)
    submenus = driver.find_elements(By.XPATH, '//*[@id="menuPart0"]//a')
    if submenus:
        submenus[0].click()
        log.info(f"하위 메뉴 클릭 완료 (총 {len(submenus)}개)")
    else:
        log.warning("하위 메뉴 못 찾음 — 이미 화면에 있을 수 있음")
    wait.until(EC.presence_of_element_located((By.ID, "excelBt")))
    log.info("번호이동 현황 화면 진입 완료")


def download_excel(driver: webdriver.Chrome) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    before = set(os.listdir(DOWNLOAD_DIR))
    log.info("엑셀 다운로드 버튼 클릭")
    driver.find_element(By.ID, "excelBt").click()
    for _ in range(30):
        time.sleep(1)
        after = set(os.listdir(DOWNLOAD_DIR))
        new_files = [
            f for f in (after - before)
            if (f.endswith(".xlsx") or f.endswith(".xls"))
            and not f.endswith(".crdownload")
        ]
        if new_files:
            path = os.path.join(DOWNLOAD_DIR, new_files[0])
            log.info(f"다운로드 완료: {new_files[0]}")
            return path
    raise TimeoutError("엑셀 다운로드 시간 초과 (30초)")


def run() -> None:
    now_kst   = datetime.now(KST)
    today_str = now_kst.strftime('%Y-%m-%d')
    log.info(f"=== KTOA 수집 시작: {now_kst.strftime('%Y-%m-%d %H:%M KST')} ===")

    # ── CONTEXT_BACKFILL=1: 스크래핑 없이 ktoa_context만 재생성
    if os.environ.get('CONTEXT_BACKFILL') == '1':
        target_date = os.environ.get('TARGET_DATE', today_str)
        log.info(f"=== CONTEXT_BACKFILL 모드: {target_date} ===")
        try:
            from ktoa_firestore import _get_db as _fdb_cb
            _db_cb = _fdb_cb()
            daily_doc = _db_cb.collection('ktoa_daily').document(target_date).get()
            if not daily_doc.exists or not daily_doc.to_dict().get('mvno_in'):
                log.error(f"CONTEXT_BACKFILL: {target_date} ktoa_daily 데이터 없음 → 스킵")
                return
            daily = daily_doc.to_dict()
            save_context_message(target_date, daily)
            log.info(f"=== CONTEXT_BACKFILL 완료: {target_date} ===")
        except Exception as e:
            log.error(f"CONTEXT_BACKFILL 실패: {e}")
            import traceback; traceback.print_exc()
        return

    # ── RECHECK_MODE=true: 20:25 재검증 모드
    if os.environ.get('RECHECK_MODE') == 'true':
        _run_recheck(now_kst, today_str)
        return

    # ── FORCE_CLOSING=1: 스크래핑 없이 DB 데이터로 일마감 처리 재실행
    if os.environ.get('FORCE_CLOSING') == '1':
        log.info("=== FORCE_CLOSING: 일마감 재처리 모드 ===")
        try:
            from ktoa_firestore import _get_db as _fdb_fc
            _db_fc = _fdb_fc()
            daily_doc = _db_fc.collection('ktoa_daily').document(today_str).get()
            if not daily_doc.exists or not daily_doc.to_dict().get('mvno_in'):
                log.error(f"FORCE_CLOSING: {today_str} ktoa_daily 데이터 없음")
                return
            daily = daily_doc.to_dict()
            prev_daily = get_previous_daily_for_closing(today_str)

            # fc_ 전항목 저장
            try:
                _hdocs_fc = list(
                    _db_fc.collection('ktoa_hourly')
                    .where('date', '==', today_str)
                    .stream()
                )
                _hdocs_fc = [d.to_dict() for d in _hdocs_fc]
                _save_all_fc_to_daily(today_str, daily, _hdocs_fc)
            except Exception as _fe_fc:
                log.warning(f"fc_ 저장 실패: {_fe_fc}")

            # 엑셀 생성 + 전송
            from forecast_excel import generate_daily_report, build_excel_caption
            excel_path = generate_daily_report(today_str, daily, output_dir='/tmp')
            if excel_path:
                caption = build_excel_caption(today_str, daily)
                _send_document(excel_path, today_str, caption=caption)
                log.info(f"FORCE_CLOSING: 엑셀 전송 완료")

            log.info("=== FORCE_CLOSING 완료 ===")
        except Exception as e:
            log.error(f"FORCE_CLOSING 실패: {e}")
        return

    # ── REPORT_MODE=excel: 스크래핑 없이 엑셀 생성+전송만 실행
    if os.environ.get('REPORT_MODE') == 'excel':
        log.info("=== 엑셀 리포트 전송 모드 ===")
        try:
            daily = get_previous_daily_for_closing(today_str) or {}
            date  = daily.get('date', today_str)
            from forecast_excel import generate_daily_report, build_excel_caption
            excel_path = generate_daily_report(date, daily, output_dir='/tmp')
            if excel_path:
                caption = build_excel_caption(date, daily)
                _send_document(excel_path, date, caption=caption)
                log.info(f"엑셀 전송 완료: {excel_path}")
            else:
                log.warning("엑셀 생성 실패 (경로 없음)")
        except Exception as e:
            log.error(f"엑셀 리포트 전송 실패: {e}")
        return

    # ── 스크래핑 ──────────────────────────────────────────────────────────────
    driver = None
    try:
        driver = get_driver()
        login(driver)
        navigate_to_stats(driver)
        excel_path = download_excel(driver)
    except Exception as e:
        _record_scrape_failure(e)
        raise
    finally:
        if driver:
            driver.quit()
    _record_scrape_success()

    # ── 파싱 ──────────────────────────────────────────────────────────────────
    log.info("엑셀 파싱 중...")
    stats = parse_ktoa_excel(excel_path, now_kst)
    new_ref_time = stats.get('reference_time', '')
    ref_hour     = _extract_hour(new_ref_time)
    log.info(f"파싱 완료 | 기준시각={new_ref_time} | 시간={ref_hour}")

    # ── 사이트 날짜 체크 ──────────────────────────────────────────────────────
    today_str = now_kst.strftime('%Y-%m-%d')
    site_date = stats.get('date', today_str)
    if site_date != today_str:
        log.info(f"사이트 날짜({site_date})가 오늘({today_str})이 아님 → 스킵")
        return

    # ── 중복 체크 (total 값 기반) ────────────────────────────────────────────
    current_total = stats.get('total', -1)

    if ref_hour >= 20:
        # [버그수정, Claude] "전일과 동일 데이터=공휴일/미갱신" 체크가 기존엔
        # else(정시) 경로에만 있어서, 일요일처럼 사이트가 ref_hour>=20으로
        # 나오면서 토요일 데이터를 그대로 들고 있으면(site_date는 오늘로
        # 찍혀서 위 날짜체크는 통과) 마감 메시지가 토요일 실적을 일요일치인
        # 것처럼 잘못 발송되던 문제. 마감 경로에도 동일 체크 적용.
        _prev_for_holiday_check = get_previous_daily_for_closing(today_str)
        if _prev_for_holiday_check and _prev_for_holiday_check.get('total') == current_total:
            log.info(f"전일 마감과 동일 데이터 → 공휴일/미갱신 스킵(마감): total={current_total}")
            return

        from ktoa_firestore import _get_db as _fdb
        _db = _fdb()
        daily_doc = _db.collection('ktoa_daily').document(today_str).get()

        if daily_doc.exists and daily_doc.to_dict().get('mvno_in'):
            _sent = daily_doc.to_dict().get('_telegram_sent', False)
            if _sent:
                log.info("20시 마감 데이터 저장 + 텔레그램 발송 완료 → 스킵")
                return
            else:
                log.warning("20시 마감 데이터 저장됨 but 텔레그램 미발송 → 재발송 시도")
                daily = daily_doc.to_dict()
                prev_daily = get_previous_daily_for_closing(today_str)
                if not _claim_closing_send(today_str):
                    log.info("다른 실행이 이미 발송 시도 중/완료(claim 실패) → 스킵")
                    return
                try:
                    send_closing_message(daily, prev_daily)
                    _db.collection('ktoa_daily').document(today_str).update({
                        '_telegram_sent': True
                    })
                    log.info("텔레그램 재발송 완료 + _telegram_sent=True 저장")
                except Exception as _re:
                    log.error(f"재발송 실패 (다음 Job에서 재시도): {_re}")
                return
        if daily_doc.exists:
            log.info("ktoa_daily 문서 있으나 실적 없음(bw_ai_prev만) → 신규 저장 진행")
    else:
        last_total = get_latest_total(today_str)
        if last_total is not None and last_total == current_total:
            log.info(f"동일 데이터 스킵: total={current_total}")
            return

        if last_total is None:
            prev_daily_check = get_previous_daily_for_closing(today_str)
            if prev_daily_check and prev_daily_check.get('total') == current_total:
                log.info(f"전일 마감과 동일 데이터 → 공휴일/미갱신 스킵: total={current_total}")
                return

        log.info(f"신규 데이터 감지: {last_total} → {current_total}")

    # ── 20시 마감 처리 ────────────────────────────────────────────────────────
    if ref_hour >= 20:
        log.info("=== 20시 일마감 처리 ===")

        try:
            from ktoa_firestore import _get_db as _fdb2
            _db2 = _fdb2()
            _hdocs = [
                doc.to_dict()
                for doc in _db2.collection('ktoa_hourly')
                              .where('date', '==', today_str)
                              .order_by('collected_at')
                              .stream()
            ]
            log.info(f"오늘 hourly 문서 {len(_hdocs)}개 수집")
        except Exception as _he:
            log.warning(f"hourly 문서 수집 실패: {_he}")
            _hdocs = []

        stats['_hourly_docs'] = _hdocs
        save_ktoa_to_firestore(stats)
        daily = save_ktoa_daily(stats)
        prev_daily = get_previous_daily_for_closing(today_str)

        # ── [v3.13] fc_ 계산을 메시지/엑셀보다 먼저 실행 → 최신 fc값 반영
        try:
            from predict_gemini import save_hourly_pattern as _sap
            _today_skt = daily.get('mno_out', {}).get('S', 0) or 0
            _sap(today_str, _hdocs, _today_skt)
        except Exception as _pe:
            log.warning(f"패턴 저장 실패 (무시): {_pe}")

        try:
            from forecast_engine import predict_monthly as _pm
            _today_skt = daily.get('mno_out', {}).get('S', 0) or 0
            _pm(today_str, _today_skt, hourly_docs=_hdocs, save_to_daily=True)
        except Exception as _fce:
            log.warning(f"predict_monthly 저장 실패 (무시): {_fce}")

        # ── 전항목 fc_ 값 Firestore 저장 (forecast_engine과 동일 로직)
        try:
            _save_all_fc_to_daily(today_str, daily, _hdocs)
        except Exception as _fce2:
            log.warning(f"전항목 fc_ 저장 실패 (무시): {_fce2}")

        # ── fc_ 갱신 반영된 daily 재조회 (메시지/엑셀에 최신 fc값 사용)
        try:
            from ktoa_firestore import _get_db as _fdb_re
            _refreshed = _fdb_re().collection('ktoa_daily').document(today_str).get().to_dict()
            if _refreshed:
                daily = _refreshed
        except Exception as _re:
            log.warning(f"daily 재조회 실패 (기존 daily 사용): {_re}")

        # ── [v3.13] 20:01: 일마감 메시지만 전송 (엑셀은 8:25 RECHECK에서 전송)
        # [버그수정, Claude] 여기는 원래 무조건 발송이라 main(20:01)/backup(20:11)
        # 실행이 겹치면(Selenium 스크래핑 지연 시) 둘 다 이 지점까지 와서 중복
        # 발송하던 진짜 원인. claim으로 원자적으로 선점한 실행만 실제 발송.
        if not _claim_closing_send(today_str):
            log.info("다른 실행이 이미 발송 시도 중/완료(claim 실패) → 스킵")
        else:
            try:
                send_closing_message(daily, prev_daily)
                from ktoa_firestore import _get_db as _fdb3
                _fdb3().collection('ktoa_daily').document(today_str).update({
                    '_telegram_sent': True
                })
                log.info("_telegram_sent=True 저장 완료")
            except Exception as _se:
                log.error(f"send_closing_message 실패 (daily 저장은 완료됨): {_se}")

        # ── [v3.6] AI 컨텍스트 메시지 저장 (ktoa_context_builder)
        try:
            from ktoa_firestore import _get_db as _fdb_ctx
            _daily_ctx = _fdb_ctx().collection('ktoa_daily').document(today_str).get().to_dict()
            save_context_message(today_str, _daily_ctx or daily)
        except Exception as _ctx_e:
            log.warning(f"컨텍스트 메시지 저장 실패 (무시): {_ctx_e}")

        # ── [v3.6] AI 컨텍스트 메시지 저장
        try:
            # fc_가 저장된 최신 daily 데이터 재조회 후 컨텍스트 생성
            from ktoa_firestore import _get_db as _fdb_ctx
            _daily_refreshed = _fdb_ctx().collection('ktoa_daily').document(today_str).get().to_dict()
            _save_context_message(today_str, _daily_refreshed or daily)
        except Exception as _ctx_e:
            log.warning(f"컨텍스트 메시지 저장 실패 (무시): {_ctx_e}")

        # ── [v3.7] period context 자동 생성 (주차/순기/월별)
        try:
            from ktoa_context_period_builder import (
                save_weekly_context, save_decade_context, save_monthly_context
            )
            from calendar import monthrange as _mr
            _dt_p  = datetime.strptime(today_str, '%Y-%m-%d')
            _day_p = _dt_p.day
            _last_p= _mr(_dt_p.year, _dt_p.month)[1]

            # 토요일 → 주차별
            if _dt_p.weekday() == 5:
                save_weekly_context(today_str)
                log.info(f'[period] 주차별 context 생성: {today_str}')

            # 10일/20일/말일 → 순기별
            if _day_p in [10, 20, _last_p]:
                save_decade_context(today_str)
                log.info(f'[period] 순기별 context 생성: {today_str}')

            # 말일 → 월별
            if _day_p == _last_p:
                save_monthly_context(_dt_p.year, _dt_p.month)
                log.info(f'[period] 월별 context 생성: {today_str}')

        except Exception as _period_e:
            log.warning(f'[period] period context 생성 실패 (무시): {_period_e}')

        _run_month_end_bw(today_str)

        log.info("=== 일마감 완료 ===")

    # ── 시간별 처리 ───────────────────────────────────────────────────────────
    else:
        collected_at = stats['collected_at']
        doc_id = collected_at.strftime('%Y-%m-%d_%H%M')

        prev_stats = get_previous_hourly(today_str, doc_id)
        streak = calc_streak(today_str, stats, doc_id) if prev_stats else {}
        if prev_stats:
            prev_stats['streak'] = streak

        save_ktoa_to_firestore(stats)

        _forecast = {}
        try:
            import re as _re_fc
            _ref = stats.get('reference_time', '')
            _fh = int(_re_fc.search(r'(\d+)시', _ref).group(1)) \
                  if _re_fc.search(r'(\d+)시', _ref) else 15
            _fm_m = _re_fc.search(r'\d+시\s*(\d+)분', _ref)
            _fm = int(_fm_m.group(1)) if _fm_m else 0
            # [수정 20261002] predict_hourly()(pattern 기반)가 10분 단위마다도
            # 무조건 재계산/저장돼서, 같은 날 안에서 forecast_mno_out.S가
            # 167→589→1008→1337→1513→(정시)2392→1862→1980→2021처럼 요동치는
            # 문제 발견(실무자 지적: "일마감 예측이 10분마다 계속 바뀌네").
            # 정시(completion_ratio_dow, Method D)와 10분단위(pattern)가 서로
            # 다른 방법이라 매 정시 경계마다 어긋나는 게 근본 원인 - 애초
            # v3.16에서 "정시에만 계산"하기로 했던 설계 의도와도 맞지 않아서,
            # 10분 단위에는 predict_hourly() 자체를 호출하지 않도록 변경(DB에도
            # forecast_* 필드를 안 남김). 정시(_fm==0)에만 계산/저장.
            if _fm == 0:
                from forecast_engine import predict_hourly as _ph
                from ktoa_telegram import calc_stats as _cs2
                _c = _cs2(stats.get('matrix', {}))
                _current_vals = {
                    'mvno_in':  _c.get('mvno_in',  {}),
                    'mno_out':  _c.get('mno_out',  {}),
                    'mvno_out': _c.get('mvno_out', {}),
                    'mno_in':      _c.get('mno_in', {}),
                    'mno_out_all': _c.get('mno_out_all', {}),
                }
                _forecast = _ph(today_str, _fh, _fm, _current_vals, doc_id)
        except Exception as _fe2:
            log.warning(f"predict_hourly 실패 (무시): {_fe2}")

        send_ktoa_message(stats, prev_stats, forecast=_forecast)

    log.info("=== 수집 완료 ===")


def _save_hourly_forecast(stats: dict, date_str: str, doc_id: str) -> dict:
    """
    [v3.2] 시간별 예측값 계산 → ktoa_hourly/{doc_id}에 저장 + 결과 반환
    """
    import re as _re3
    from ktoa_telegram import calc_stats as _cs
    from bw_engine import get_bw_final as _gbw
    from ktoa_firestore import _get_db as _fdb4

    matrix = stats.get('matrix', {})
    c = _cs(matrix)
    mi  = c.get('mvno_in',  {})
    mno = c.get('mno_out',  {})
    mo  = c.get('mvno_out', {})
    net = c.get('net',      {})

    _ref = stats.get('reference_time', '')
    _h_match = _re3.search(r'(\d+)시', _ref)
    _m_match = _re3.search(r'\d+시\s*(\d+)분', _ref)
    _hour_now   = int(_h_match.group(1)) if _h_match else 15
    _minute_now = int(_m_match.group(1)) if _m_match else 0
    # ★ 패턴 키용 bw: bw_manual 우선, 없으면 get_bw_final
    try:
        _dd_bw = _fdb4().collection('ktoa_daily').document(date_str).get().to_dict() or {}
        _m_bw = float(_dd_bw.get('bw_manual') or 0)
        _bw_now = _m_bw if _m_bw > 0 else _gbw(date_str)
    except Exception:
        _bw_now = _gbw(date_str)

    _est_mi  = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0}
    _est_mno = {'S': 0,  'K': 0,  'L': 0,  '계': 0}
    _est_mo  = {'SM': 0, 'KM': 0, 'LM': 0, '계': 0}
    _source  = 'none'

    try:
        from predict_gemini import get_hourly_pattern as _ghp
        _pat = _ghp(date_str, _hour_now, _bw_now, _minute_now)

        if _pat.get('available') and _pat.get('rate_at_hour', 0) > 0:
            _rates = _pat.get('rates', {})
            _r_skt    = _rates.get('skt')    or _pat['rate_at_hour']
            _r_sm     = _rates.get('sm')     or _r_skt
            _r_km     = _rates.get('km')     or _r_skt
            _r_lm     = _rates.get('lm')     or _r_skt
            _r_sm_out = _rates.get('sm_out') or _r_skt
            _r_km_out = _rates.get('km_out') or _r_skt
            _r_lm_out = _rates.get('lm_out') or _r_skt

            def _div(v, r): return int(v / r) if r and r > 0 else 0

            _est_mi  = {'SM': _div(mi['SM'], _r_sm),
                        'KM': _div(mi['KM'], _r_km),
                        'LM': _div(mi['LM'], _r_lm), '계': 0}
            _est_mi['계'] = sum(_est_mi[k] for k in ['SM','KM','LM'])

            _est_mno = {'S': _div(mno['S'], _r_skt),
                        'K': _div(mno['K'], _r_skt),
                        'L': _div(mno['L'], _r_skt), '계': 0}
            _est_mno['계'] = sum(_est_mno[k] for k in ['S','K','L'])

            _est_mo  = {'SM': _div(mo['SM'], _r_sm_out),
                        'KM': _div(mo['KM'], _r_km_out),
                        'LM': _div(mo['LM'], _r_lm_out), '계': 0}
            _est_mo['계'] = sum(_est_mo[k] for k in ['SM','KM','LM'])
            _interp = _pat.get('interpolated', False)
            _source = f'pattern(n={_pat["sample_count"]}{"_interp" if _interp else ""})'

        else:
            _db4 = _fdb4()
            _past_rates = _get_past_same_hour_rates(_db4, date_str, _hour_now)

            if _past_rates:
                _avg_rate = sum(_past_rates) / len(_past_rates)
                if _avg_rate > 0:
                    def _scale_v(v): return int(v / _avg_rate)
                    _est_mi  = {'SM': _scale_v(mi['SM']),  'KM': _scale_v(mi['KM']),
                                'LM': _scale_v(mi['LM']),  '계': 0}
                    _est_mi['계'] = sum(_est_mi[k] for k in ['SM','KM','LM'])
                    _est_mno = {'S': _scale_v(mno['S']),   'K': _scale_v(mno['K']),
                                'L': _scale_v(mno['L']),   '계': 0}
                    _est_mno['계'] = sum(_est_mno[k] for k in ['S','K','L'])
                    _est_mo  = {'SM': _scale_v(mo['SM']),  'KM': _scale_v(mo['KM']),
                                'LM': _scale_v(mo['LM']),  '계': 0}
                    _est_mo['계'] = sum(_est_mo[k] for k in ['SM','KM','LM'])
                    _source = f'past_hourly(n={len(_past_rates)})'
            else:
                _elapsed_h = max(1, _hour_now - 10)
                _scale = 10.0 / _elapsed_h
                for _k in ['SM', 'KM', 'LM']:
                    _est_mi[_k]  = int(mi[_k]  * _scale)
                    _est_mo[_k]  = int(mo[_k]  * _scale)
                for _k in ['S', 'K', 'L']:
                    _est_mno[_k] = int(mno[_k] * _scale)
                _est_mi['계']  = sum(_est_mi[k]  for k in ['SM','KM','LM'])
                _est_mno['계'] = sum(_est_mno[k] for k in ['S','K','L'])
                _est_mo['계']  = sum(_est_mo[k]  for k in ['SM','KM','LM'])
                _source = 'time_linear'

    except Exception as _e2:
        log.warning(f"예측값 계산 실패: {_e2}")
        return {}

    if _est_mi['계'] <= 0:
        return {}

    _est_net = {k: _est_mi.get(k, 0) - _est_mo.get(k, 0)
                for k in ['SM', 'KM', 'LM']}
    _est_net['계'] = sum(_est_net[k] for k in ['SM', 'KM', 'LM'])

    try:
        _fdb4().collection('ktoa_hourly').document(doc_id).set({
            'forecast_mvno_in':  _est_mi,
            'forecast_mno_out':  _est_mno,
            'forecast_mvno_out': _est_mo,
            'forecast_source':   _source,
            'forecast_hour':     _hour_now,
            'forecast_minute':   _minute_now,
        }, merge=True)
        log.info(f"시간별 예측값 저장: {doc_id} ({_source}, {_hour_now}:{_minute_now:02d})")
    except Exception as _e3:
        log.warning(f"예측값 Firestore 저장 실패 (메시지는 계속): {_e3}")

    return {
        'mvno_in':  _est_mi,
        'mno_out':  _est_mno,
        'mvno_out': _est_mo,
        'net':      _est_net,
        'source':   _source,
    }


def _get_past_same_hour_rates(db, date_str: str, hour: int) -> list:
    from datetime import datetime as _dt2, timedelta as _td2
    from bw_engine import is_zero_day as _izd

    d = _dt2.strptime(date_str, '%Y-%m-%d')
    rates = []

    try:
        for weeks_back in range(1, 9):
            past_d = d - _td2(days=7 * weeks_back)
            past_str = past_d.strftime('%Y-%m-%d')

            if _izd(past_str):
                continue

            past_hourly_id = f"{past_str}_{hour:02d}00"
            hourly_doc = db.collection('ktoa_hourly').document(past_hourly_id).get()
            if not hourly_doc.exists:
                for _min in ['10', '50']:
                    alt_id = f"{past_str}_{hour:02d}{_min}"
                    alt_doc = db.collection('ktoa_hourly').document(alt_id).get()
                    if alt_doc.exists:
                        hourly_doc = alt_doc
                        break

            if not hourly_doc.exists:
                continue

            h_data = hourly_doc.to_dict()
            h_mvno_in = h_data.get('mvno_in', {}).get('계', 0) or 0

            daily_doc = db.collection('ktoa_daily').document(past_str).get()
            if not daily_doc.exists:
                continue
            d_data = daily_doc.to_dict()
            d_mvno_in = d_data.get('mvno_in', {}).get('계', 0) or 0

            if h_mvno_in > 0 and d_mvno_in > 0:
                rate = h_mvno_in / d_mvno_in
                if 0.1 <= rate <= 1.0:
                    rates.append(rate)

    except Exception as e:
        log.warning(f"과거 동시간대 진행률 조회 실패: {e}")

    return rates


def _save_all_fc_to_daily(date_str: str, daily: dict, hourly_docs: list) -> None:
    """
    [v3.4] 일마감 후 전항목 월마감 예측값(fc_) Firestore ktoa_daily에 저장
    - MVNO IN(SM/KM/LM/계), MNO Out(S/K/L/계), 순증감(SM/KM/LM/계), MVNO Out(SM/KM/LM/계)
    - 순증감 예측 = MVNO IN 예측 - MVNO OUT 예측
    """
    from calendar import monthrange
    from bw_engine import get_bw_final, is_zero_day
    from ktoa_firestore import _get_db

    db = _get_db()
    if not db:
        return

    year  = int(date_str[:4])
    month = int(date_str[5:7])
    day   = int(date_str[8:10])
    last_day = monthrange(year, month)[1]

    # 누적값
    cum_mi  = daily.get('cum_mvno_in',  {}) or {}
    cum_mo  = daily.get('cum_mno_out',  {}) or {}
    cum_mout= daily.get('cum_mvno_out', {}) or {}
    cum_net = daily.get('cum_net',      {}) or {}

    # bw 계산 (forecast_engine + 엑셀과 동일)
    cum_bw = 0.0  # 경과bw: bw_ai_prev 고정
    hist_bw = []  # 가중평균용 히스토리
    _total_ai = _total_w2 = _total_man = 0.0
    _last_biz_ai = _last_biz_w2 = _last_biz_man = 0.0
    try:
        # 전체 bw 합산 (1~말일)
        for d in range(1, last_day + 1):
            ds = f'{year:04d}-{month:02d}-{d:02d}'
            _dd = (db.collection('ktoa_daily').document(ds).get().to_dict() or {})
            _total_ai  += float(_dd.get('bw_ai_prev') or 0)
            _total_w2  += float(_dd.get('bw_ai_w2') or _dd.get('bw_ai_prev') or 0)
            _total_man += float(_dd.get('bw_manual') or _dd.get('bw_ai_prev') or 0)

        # 경과bw + 항목별 history 수집 (이중가중 avg용, 오래된순)
        hist_items = {
            'S': [], 'SM_IN': [], 'KM_IN': [], 'LM_IN': [],
            'SM_OUT': [], 'KM_OUT': [], 'LM_OUT': [],
            'MI_계': [], 'MO_계': [], 'MOUT_계': [],
            'K': [], 'L': [],
        }
        for d in range(1, day + 1):
            ds = f'{year:04d}-{month:02d}-{d:02d}'
            _dd = (db.collection('ktoa_daily').document(ds).get().to_dict() or {})
            _bw = float(_dd.get('bw_ai_prev') or _dd.get('bw_manual') or 0)
            _skt = (_dd.get('mno_out') or {}).get('S')
            if _bw > 0 and _skt:
                cum_bw += _bw
                hist_bw.append((_skt, _bw))
                _last_biz_ai  = float(_dd.get('bw_ai_prev') or 0)
                _last_biz_w2  = float(_dd.get('bw_ai_w2') or _dd.get('bw_ai_prev') or 0)
                _last_biz_man = float(_dd.get('bw_manual') or _dd.get('bw_ai_prev') or 0)
                # 항목별 history
                _mi   = _dd.get('mvno_in',  {}) or {}
                _mo   = _dd.get('mno_out',  {}) or {}
                _mout = _dd.get('mvno_out', {}) or {}
                for k, v in [
                    ('S',      _mo.get('S')),   ('K',      _mo.get('K')),
                    ('L',      _mo.get('L')),   ('SM_IN',  _mi.get('SM')),
                    ('KM_IN',  _mi.get('KM')),  ('LM_IN',  _mi.get('LM')),
                    ('SM_OUT', _mout.get('SM')),('KM_OUT', _mout.get('KM')),
                    ('LM_OUT', _mout.get('LM')),('MI_계',  _mi.get('계')),
                    ('MO_계',  _mo.get('계')),  ('MOUT_계',_mout.get('계')),
                ]:
                    if v:
                        hist_items[k].append((int(v), _bw))

        # ── 당월 실적 10일 미만이면 전월로 채움 (rolling window)
        TOP_N = 10
        if len(hist_items['S']) < TOP_N:
            from datetime import timedelta, datetime as _dt
            from calendar import monthrange as _mr
            _prev_m = month - 1 if month > 1 else 12
            _prev_y = year if month > 1 else year - 1
            _prev_last = _mr(_prev_y, _prev_m)[1]
            _need = TOP_N - len(hist_items['S'])
            _filled = 0
            for _pd in range(_prev_last, 0, -1):
                if _filled >= _need:
                    break
                _pds = f'{_prev_y:04d}-{_prev_m:02d}-{_pd:02d}'
                _pdd = (db.collection('ktoa_daily').document(_pds).get().to_dict() or {})
                _pbw = float(_pdd.get('bw_ai_prev') or _pdd.get('bw_manual') or 0)
                _pskt = (_pdd.get('mno_out') or {}).get('S')
                if _pbw > 0 and _pskt:
                    _pmi   = _pdd.get('mvno_in',  {}) or {}
                    _pmo   = _pdd.get('mno_out',  {}) or {}
                    _pmout = _pdd.get('mvno_out', {}) or {}
                    for k, v in [
                        ('S',      _pmo.get('S')),   ('K',      _pmo.get('K')),
                        ('L',      _pmo.get('L')),   ('SM_IN',  _pmi.get('SM')),
                        ('KM_IN',  _pmi.get('KM')),  ('LM_IN',  _pmi.get('LM')),
                        ('SM_OUT', _pmout.get('SM')),('KM_OUT', _pmout.get('KM')),
                        ('LM_OUT', _pmout.get('LM')),('MI_계',  _pmi.get('계')),
                        ('MO_계',  _pmo.get('계')),  ('MOUT_계',_pmout.get('계')),
                    ]:
                        if v and len(hist_items[k]) < TOP_N:
                            hist_items[k].insert(0, (int(v), _pbw))  # 앞에 추가 (오래된순 유지)
                    _filled += 1

        # 잔여bw = total - elapsed (B방식, last_biz 제거 → forecast_engine과 동일)
        rem_bw_ai  = round(_total_ai  - cum_bw, 3)               # 보수적 (bw_ai_prev)
        rem_bw_man = round(_total_man - cum_bw, 3)               # 낙관적 (bw_manual)

    except Exception as _e:
        log.warning(f"bw 계산 실패: {_e}")
        return

    if cum_bw <= 0:
        log.warning("cum_bw=0, fc_ 계산 스킵")
        return

    def _trio(cum_val, avg5, avg10):
        """Low/Mid/High 예측 4값 → 정렬
        cum_val : 해당 항목 월 누적값
        avg5    : D-1 기준 최근 10 영업일 이중가중 avg (max_w=5.0, 기존)
        avg10   : 동일 but max_w=10.0 (최근일 가중 강화, 추세 빠른 반영)
        4값 = {avg5,avg10} × {rem_bw_ai, rem_bw_man} → sorted
        → fc_low=최소, fc_high=최대, fc_mid=중간 2개 평균
        """
        if not cum_val or cum_bw <= 0:
            return {'low': None, 'mid': None, 'high': None}
        a5  = avg5  if avg5  > 0 else round(cum_val / cum_bw, 1)
        a10 = avg10 if avg10 > 0 else a5
        _p1 = int(cum_val + a5  * rem_bw_ai)
        _p2 = int(cum_val + a5  * rem_bw_man)
        _p3 = int(cum_val + a10 * rem_bw_ai)
        _p4 = int(cum_val + a10 * rem_bw_man)
        _s = sorted([_p1, _p2, _p3, _p4])
        return {'low': _s[0], 'mid': int(round((_s[1]+_s[2])/2)), 'high': _s[3]}

    def _net_trio(fc_in, fc_out):
        """순증감 예측 = MVNO IN - MVNO OUT"""
        result = {}
        for k in ['low', 'mid', 'high']:
            vi = fc_in.get(k)
            vo = fc_out.get(k)
            result[k] = (vi - vo) if (vi is not None and vo is not None) else None
        if result['low'] is not None and result['high'] is not None and result['low'] > result['high']:
            result['low'], result['high'] = result['high'], result['low']
        return result

    # ── 항목별 rolling avg (D-1 기준 최근 10 영업일, 월 경계 자동 포함)
    from forecast_engine import _calc_weighted_avg
    def _ravg(hist_item):
        """hist_item: 오래된순 → reverse해서 최신순으로 이중가중
        Returns (avg5, avg10)"""
        if not hist_item:
            return 0.0, 0.0
        rev = list(reversed(hist_item))
        return _calc_weighted_avg(rev, max_w=5.0), _calc_weighted_avg(rev, max_w=10.0)

    # 각 항목 예측
    fc_sm    = _trio(cum_mi.get('SM'),   *_ravg(hist_items['SM_IN']))
    fc_km    = _trio(cum_mi.get('KM'),   *_ravg(hist_items['KM_IN']))
    fc_lm    = _trio(cum_mi.get('LM'),   *_ravg(hist_items['LM_IN']))
    fc_mi    = _trio(cum_mi.get('계'),   *_ravg(hist_items['MI_계']))
    fc_s     = _trio(cum_mo.get('S'),    *_ravg(hist_items['S']))
    fc_k     = _trio(cum_mo.get('K'),    *_ravg(hist_items['K']))
    fc_l     = _trio(cum_mo.get('L'),    *_ravg(hist_items['L']))
    fc_mo    = _trio(cum_mo.get('계'),   *_ravg(hist_items['MO_계']))
    fc_mo_sm = _trio(cum_mout.get('SM'), *_ravg(hist_items['SM_OUT']))
    fc_mo_km = _trio(cum_mout.get('KM'), *_ravg(hist_items['KM_OUT']))
    fc_mo_lm = _trio(cum_mout.get('LM'), *_ravg(hist_items['LM_OUT']))
    fc_mo_out= _trio(cum_mout.get('계'), *_ravg(hist_items['MOUT_계']))

    # [20261007] 전월 동일시점 잔여속도법으로 교체 (forecast_engine._get_prev_month_analog_pred
    # 설명 참고). 백테스트에서 12개 항목 모두 위 단순 avg 방식보다 정확. mid=혼합값,
    # low/high=전월흐름(pure)·이번달수준반영(scaled) 두 추정치 범위. 계산 불가 시 위 값 유지.
    from forecast_engine import _get_prev_month_analog_pred as _analog

    def _analog_trio(group, key, cum_val, fallback):
        if not cum_val:
            return fallback
        try:
            a = _analog(date_str, float(cum_val), include_today=True, group=group, key=key)
        except Exception as _ae:
            log.warning(f"전월 잔여속도법 실패 {group}.{key} (단순방식 유지): {_ae}")
            return fallback
        if not a:
            return fallback
        lo, hi = sorted([a['pred_pure'], a['pred_scaled']])
        return {'low': int(round(lo)), 'mid': int(round(a['pred'])), 'high': int(round(hi))}

    fc_sm     = _analog_trio('mvno_in',  'SM', cum_mi.get('SM'),   fc_sm)
    fc_km     = _analog_trio('mvno_in',  'KM', cum_mi.get('KM'),   fc_km)
    fc_lm     = _analog_trio('mvno_in',  'LM', cum_mi.get('LM'),   fc_lm)
    fc_k      = _analog_trio('mno_out',  'K',  cum_mo.get('K'),    fc_k)
    fc_l      = _analog_trio('mno_out',  'L',  cum_mo.get('L'),    fc_l)
    fc_mo_sm  = _analog_trio('mvno_out', 'SM', cum_mout.get('SM'), fc_mo_sm)
    fc_mo_km  = _analog_trio('mvno_out', 'KM', cum_mout.get('KM'), fc_mo_km)
    fc_mo_lm  = _analog_trio('mvno_out', 'LM', cum_mout.get('LM'), fc_mo_lm)

    # MNO 유입(mno_in)/MNO 전체이탈(mno_out_all) S/K/L - 기존엔 예측 자체가 없었음.
    # 백테스트: mno_in S/K/L 10.3/8.6/9.1%, mno_out_all 6.0/9.7/7.8% (단순avg 대비 모두 개선)
    _none = {'low': None, 'mid': None, 'high': None}
    cum_mni   = daily.get('cum_mno_in', {}) or {}
    cum_moall = daily.get('cum_mno_out_all', {}) or {}
    fc_mni    = {k: _analog_trio('mno_in',      k, cum_mni.get(k),   _none) for k in ('S', 'K', 'L')}
    fc_moall  = {k: _analog_trio('mno_out_all', k, cum_moall.get(k), _none) for k in ('S', 'K', 'L')}

    # SKT(S)는 predict_monthly()가 같은 날 먼저 저장한 공식 예측(fc_low/mid/high)과
    # 동일하게 저장 - 대시보드/엑셀/AI봇이 텔레그램과 같은 숫자를 보도록 (20261007)
    try:
        _off = (db.collection('ktoa_daily').document(date_str).get().to_dict() or {})
        if _off.get('fc_mid'):
            fc_s = {'low': _off.get('fc_low'), 'mid': _off.get('fc_mid'),
                    'high': _off.get('fc_high')}
        else:
            fc_s = _analog_trio('mno_out', 'S', cum_mo.get('S'), fc_s)
    except Exception as _se:
        log.warning(f"공식 fc_mid 조회 실패 (S 단순방식 유지): {_se}")

    def _sum_trio(*trios):
        """'계' = 세부 항목 합 (따로 예측하지 않음 - 세부합과 계가 어긋나지 않게, 20261007)"""
        out = {}
        for k in ('low', 'mid', 'high'):
            vals = [t.get(k) for t in trios]
            out[k] = None if any(v is None for v in vals) else sum(vals)
        return out

    fc_mi     = _sum_trio(fc_sm, fc_km, fc_lm)
    fc_mo     = _sum_trio(fc_s, fc_k, fc_l)
    fc_mo_out = _sum_trio(fc_mo_sm, fc_mo_km, fc_mo_lm)
    fc_mni['계']   = _sum_trio(*(fc_mni[k] for k in ('S', 'K', 'L')))
    fc_moall['계'] = _sum_trio(*(fc_moall[k] for k in ('S', 'K', 'L')))

    # 순증감 = IN - OUT (MVNO: mvno_in - mvno_out / MNO: mno_in - mno_out_all)
    fc_net_sm = _net_trio(fc_sm, fc_mo_sm)
    fc_net_km = _net_trio(fc_km, fc_mo_km)
    fc_net_lm = _net_trio(fc_lm, fc_mo_lm)
    fc_net    = _sum_trio(fc_net_sm, fc_net_km, fc_net_lm)
    # MNO 순증 계 = -(MVNO 순증 계)로 맞춤 - 중간값 기준 보정량을 low/high에도 같이 적용
    # (forecast_engine.reconcile_mno_to_mvno 설명 참고)
    from forecast_engine import reconcile_mno_to_mvno as _reconcile
    if fc_net.get('mid') is not None:
        _adj = _reconcile(fc_net['mid'], {k: fc_mni[k]['mid'] for k in ('S', 'K', 'L')},
                          {k: fc_moall[k]['mid'] for k in ('S', 'K', 'L')})
        for k, (d_in, d_out) in _adj.items():
            for lv in ('low', 'mid', 'high'):
                if fc_mni[k].get(lv) is not None:
                    fc_mni[k][lv] = int(round(fc_mni[k][lv] + d_in))
                if fc_moall[k].get(lv) is not None:
                    fc_moall[k][lv] = int(round(fc_moall[k][lv] + d_out))
        if _adj:
            # 반올림 잔차는 S 유입(mid)에 반영해 MNO계 mid = -(MVNO 계 mid)를 정확히 맞춤
            fc_mni['S']['mid'] += -fc_net['mid'] - sum(
                fc_mni[k]['mid'] - fc_moall[k]['mid'] for k in ('S', 'K', 'L'))
            fc_mni['계']   = _sum_trio(*(fc_mni[k] for k in ('S', 'K', 'L')))
            fc_moall['계'] = _sum_trio(*(fc_moall[k] for k in ('S', 'K', 'L')))
    fc_net_mno = {k: _net_trio(fc_mni[k], fc_moall[k]) for k in ('S', 'K', 'L')}
    fc_net_mno['MNO계'] = _sum_trio(*(fc_net_mno[k] for k in ('S', 'K', 'L')))

    fc_data = {
        'fc_mvno_in':  {'SM': fc_sm,  'KM': fc_km,  'LM': fc_lm,  '계': fc_mi},
        'fc_mno_out':  {'S':  fc_s,   'K':  fc_k,   'L':  fc_l,   '계': fc_mo},
        'fc_mvno_out': {'SM': fc_mo_sm,'KM': fc_mo_km,'LM': fc_mo_lm,'계': fc_mo_out},
        'fc_net':      {'SM': fc_net_sm,'KM': fc_net_km,'LM': fc_net_lm,'계': fc_net,
                        **fc_net_mno},
        'fc_mno_in':      fc_mni,
        'fc_mno_out_all': fc_moall,
        'fc_all_saved_at': date_str,
    }

    db.collection('ktoa_daily').document(date_str).update(fc_data)
    log.info(f"전항목 fc_ 저장 완료: {date_str} "
             f"(MVNO IN 계 mid={fc_mi.get('mid')}, T-Out mid={fc_s.get('mid')})")


def _send_document(file_path: str, date_str: str, caption: str = None) -> None:
    token         = os.environ.get('TELEGRAM_TOKEN', '')
    group_chat_id = os.environ.get('TELEGRAM_GROUP_CHAT_ID', '-1003814217559')

    if not token or not group_chat_id:
        log.warning("텔레그램 환경변수 없음 — 파일 전송 스킵")
        return

    if caption is None:
        caption = f'📊 일마감 리포트 {date_str}'

    try:
        with open(file_path, 'rb') as f:
            resp = requests.post(
                f'https://api.telegram.org/bot{token}/sendDocument',
                data={'chat_id': group_chat_id, 'caption': caption},
                files={'document': f},
                timeout=30,
            )
        if resp.json().get('ok'):
            log.info(f"텔레그램 파일 전송 성공 (chat_id={group_chat_id})")
        else:
            log.warning(f"텔레그램 파일 전송 실패: {resp.json()}")
    except Exception as e:
        log.error(f"파일 전송 오류: {e}")




def _run_recheck(now_kst, today_str: str) -> None:
    """
    [v3.6] RECHECK_MODE=true 전용 (20:25, 21:30 실행)
    ① 사이트 재수집 → site_date 확인
    ② site_date 기준으로 ktoa_daily 조회
    ③ 일마감 미완료 체크 → 재처리 (실적 없으면 스킵)
    ④ DB값 vs 사이트 재수집값 비교 → 차이 있으면 개인채널 알림
    기존 20:01/20:11 로직은 완전히 그대로 유지
    """
    log.info("=== RECHECK_MODE 시작 ===")

    # ── ① 사이트 재수집 (site_date 확인용) ───────────────────────────────────
    log.info("RECHECK: 사이트 재수집 시작")
    driver = None
    try:
        driver = get_driver()
        login(driver)
        navigate_to_stats(driver)
        excel_path = download_excel(driver)
    except Exception as _se:
        log.error(f"RECHECK: 스크래핑 실패: {_se}")
        return
    finally:
        if driver:
            driver.quit()

    try:
        stats = parse_ktoa_excel(excel_path, now_kst)
    except Exception as _pe:
        log.error(f"RECHECK: 파싱 실패: {_pe}")
        return

    # ── ② site_date 기준으로 DB 조회 ─────────────────────────────────────────
    site_date = stats.get('date', today_str)
    log.info(f"RECHECK: 사이트 날짜={site_date}")

    from ktoa_firestore import _get_db as _fdb_rc
    _db_rc = _fdb_rc()
    daily_doc = _db_rc.collection('ktoa_daily').document(site_date).get()

    # ── ③ 일마감 미완료 체크 ─────────────────────────────────────────────────
    if not daily_doc.exists or not daily_doc.to_dict().get('mvno_in'):
        # 실적 없으면 스킵 (영업 안 하는 날 등)
        log.info(f"RECHECK: {site_date} 실적 없음 → 스킵")
        return

    daily_data = daily_doc.to_dict()
    _sent = daily_data.get('_telegram_sent', False)

    if not _sent:
        log.warning(f"RECHECK: {site_date} _telegram_sent=False → 개인채널 알림만")
        try:
            from ktoa_morning_check import _send as _rc_send
            _rc_send(f"⚠️ RECHECK ({site_date})\n_telegram_sent=False 감지\n→ 20:01/20:11 발송 실패로 보임\n수동 확인 필요")
        except Exception as _e:
            log.error(f"RECHECK: 알림 실패: {_e}")
        # 재발송 후에도 ④ DB 비교 계속 진행

    # ── ④ DB 비교 + 알림 ─────────────────────────────────────────────────────
    try:
        from ktoa_morning_check import check_and_notify
        check_and_notify(stats, daily_data, site_date)
    except Exception as _mc:
        log.warning(f"RECHECK: check_and_notify 실패 (무시): {_mc}")

    # ── ⑤ [v3.14] 20:25 재검증(실제 변경 발생 시점)에만
    #     fc_ 재계산 + 수정 일마감 메시지 + 엑셀 재전송
    #     - 08:00 익일 RECHECK는 ③④(비교/알림)만 수행하고 이 블록은 스킵
    if now_kst.hour == 20:
        log.info("RECHECK(20:25): fc_ 재계산 + 수정 일마감 메시지 + 엑셀 전송 시작")
        try:
            _hdocs_rc = [
                d.to_dict() for d in
                _db_rc.collection('ktoa_hourly')
                      .where('date', '==', site_date)
                      .stream()
            ]

            from predict_gemini import save_hourly_pattern as _sap_rc
            _today_skt_rc = daily_data.get('mno_out', {}).get('S', 0) or 0
            _sap_rc(site_date, _hdocs_rc, _today_skt_rc)

            from forecast_engine import predict_monthly as _pm_rc
            _pm_rc(site_date, _today_skt_rc, hourly_docs=_hdocs_rc, save_to_daily=True)

            _save_all_fc_to_daily(site_date, daily_data, _hdocs_rc)

            # fc_ 갱신 반영된 daily 재조회
            _refreshed_rc = _db_rc.collection('ktoa_daily').document(site_date).get().to_dict()
            _daily_for_msg = _refreshed_rc or daily_data

            # 전일 daily (closing message용)
            _prev_daily_rc = get_previous_daily_for_closing(site_date)

            # ── 수정 일마감 메시지 전송
            # [버그수정, Claude] 여기는 무조건 발송이라, maxRetries=3인 Cloud Run
            # Job이 이 지점 이후(fc 재계산/엑셀 등)에서 실패해 스크립트를 처음부터
            # 재시도하면 이미 보낸 "수정 일마감"을 가드 없이 또 보내던 게 진짜 원인.
            if not _claim_recheck_send(site_date):
                log.info(f"RECHECK(20:25): 수정 일마감 이미 발송 시도/완료(claim 실패) → 스킵 ({site_date})")
            else:
                try:
                    _msg = build_closing_message(_daily_for_msg, _prev_daily_rc)
                    _tg_send(f"📋 수정 일마감 메시지 ({site_date})\n\n{_msg}")
                    from ktoa_firestore import _get_db as _fdb_rcmsg
                    _fdb_rcmsg().collection('ktoa_daily').document(site_date).update({
                        '_recheck_msg_sent': True
                    })
                    log.info(f"RECHECK(20:25): 수정 일마감 메시지 전송 완료 ({site_date})")
                except Exception as _msge:
                    log.warning(f"RECHECK(20:25): 수정 일마감 메시지 전송 실패 (무시): {_msge}")

            # ── 엑셀 전송 (날짜당 최초 1회만 - _claim_recheck_excel 가드)
            # [버그수정, Claude] 기존엔 가드 없이 무조건 전송이라, 사이트가 연휴 등으로
            # 여러 날 같은 site_date에 멈춰 있으면 RECHECK(20:25)가 실행될 때마다
            # 이미 보낸 엑셀을 계속 재전송했음.
            if not _claim_recheck_excel(site_date):
                log.info(f"RECHECK(20:25): 엑셀 이미 발송 시도/완료(claim 실패) → 스킵 ({site_date})")
            else:
                from forecast_excel import generate_daily_report, build_excel_caption
                excel_path = generate_daily_report(site_date, _daily_for_msg, output_dir='/tmp')
                if excel_path:
                    caption = build_excel_caption(site_date, _daily_for_msg)
                    _send_document(excel_path, site_date, caption=caption)
                    from ktoa_firestore import _get_db as _fdb_rcexcel
                    _fdb_rcexcel().collection('ktoa_daily').document(site_date).update({
                        '_recheck_excel_sent': True
                    })
                    log.info(f"RECHECK(20:25): 엑셀 전송 완료 ({site_date})")
                else:
                    log.warning("RECHECK(20:25): 엑셀 생성 실패 (경로 없음)")
        except Exception as _rce:
            log.warning(f"RECHECK(20:25): fc/메시지/엑셀 재계산 실패 (무시): {_rce}")

    log.info("=== RECHECK_MODE 완료 ===")


def _recheck_scrape_and_close(now_kst, today_str: str) -> None:
    """RECHECK 시 일마감 데이터가 없을 때 스크래핑 + 일마감 재처리"""
    driver = None
    try:
        driver = get_driver()
        login(driver)
        navigate_to_stats(driver)
        excel_path = download_excel(driver)
    except Exception as _se:
        log.error(f"RECHECK 재처리 스크래핑 실패: {_se}")
        return
    finally:
        if driver:
            driver.quit()

    try:
        stats    = parse_ktoa_excel(excel_path, now_kst)
        ref_hour = _extract_hour(stats.get('reference_time', ''))
        if ref_hour < 20:
            log.warning(f"RECHECK 재처리: ref_hour={ref_hour} < 20 → 마감 데이터 아님")
            return

        save_ktoa_to_firestore(stats)
        daily = save_ktoa_daily(stats)
        prev_daily = get_previous_daily_for_closing(today_str)

        if not _claim_closing_send(today_str):
            log.info("RECHECK 재처리: 이미 발송 시도/완료(claim 실패) → 스킵")
            return

        send_closing_message(daily, prev_daily)

        from ktoa_firestore import _get_db as _fdb_rc2
        _fdb_rc2().collection('ktoa_daily').document(today_str).update({
            '_telegram_sent': True
        })
        log.info("RECHECK 재처리: 일마감 완료")
    except Exception as _e:
        log.error(f"RECHECK 재처리 실패: {_e}")


def _run_month_end_bw(today_str: str) -> None:
    from calendar import monthrange
    from datetime import datetime, timedelta

    try:
        from bw_engine import is_zero_day, generate_month_bw_ai_prev
    except ImportError as e:
        log.warning(f"bw_engine import 실패: {e}")
        return

    try:
        dt       = datetime.strptime(today_str, '%Y-%m-%d')
        year     = dt.year
        month    = dt.month
        last_day = monthrange(year, month)[1]

        has_remaining = any(
            not is_zero_day(f"{year:04d}-{month:02d}-{d:02d}")
            for d in range(dt.day + 1, last_day + 1)
        )

        if has_remaining:
            log.info(f"월말 아님 ({today_str}) → bw_ai_prev 생성 스킵")
            return

        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        next_ym = f"{next_year:04d}-{next_month:02d}"

        try:
            from ktoa_firestore import _get_db as _fdb3
            _db3 = _fdb3()
            _check_doc = _db3.collection('ktoa_daily') \
                             .document(f"{next_ym}-01").get()
            if _check_doc.exists and _check_doc.to_dict().get('bw_ai_prev'):
                log.info(f"{next_ym} bw_ai_prev 이미 존재 → 스킵")
                return
        except Exception as _ce:
            log.warning(f"bw_ai_prev 존재 확인 실패 (계속 진행): {_ce}")

        log.info(f"=== {next_ym} bw_ai_prev 자동 생성 시작 ===")
        saved = generate_month_bw_ai_prev(next_year, next_month)
        log.info(f"=== {next_ym} bw_ai_prev {saved}일 저장 완료 ===")

        token   = os.environ.get('TELEGRAM_TOKEN', '')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        if token and chat_id:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id,
                      'text': f'✅ {next_ym} 영업일수(bw_ai_prev) 자동 생성 완료 ({saved}일)'},
                timeout=10,
            )

    except Exception as e:
        log.error(f"_run_month_end_bw 오류: {e}")

if __name__ == "__main__":
    run()