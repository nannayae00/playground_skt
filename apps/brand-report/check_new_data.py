"""
[수정 이력]
- v1.0 (2026-07-29): 최초 작성. MNP 마감(20:20경) 이후 KTOA 사이트에
  당일 데이터가 실제로 언제 올라오는지 확인하기 위한 경량 모니터링 스크립트.
  전체 130개 사업자를 도는 ktoa_mvno_scraper.run()은 무거워서, SKT 원조
  1개만 가볍게 로그인->선택->다운로드->파싱해 최신 날짜를 확인.
  - 목표 날짜(스케줄 실행일 당일, KST)가 확인되면: 텔레그램 알림 +
    Firestore에 "오늘 확인 완료" 플래그 저장 -> 이후 시간대는 조용히 스킵.
  - 확인 안 되면: "미진행" 알림.
  - 확인 과정 자체가 실패(로그인/다운로드 오류 등)해도 텔레그램으로 알림.
  - 스케줄: 21시~익일 7시, 매시간(Cloud Scheduler에서 개별 등록).
- v1.1 (2026-07-29): 실사용 테스트 중 "close_b3 is not defined" JS 오류 확인
  및 수정. select_operator()가 호출하는 사이트 JS(menuClick)가 close_b3()
  등 팝업 관련 함수를 참조하는데, 이 함수들은 사업자 목록 팝업을 한 번
  열어야(getComp() 호출로 관련 스크립트가 로드되어야) 정의됨 - 팝업을
  연 적 없이 바로 select_operator를 호출해서 발생. get_operator_list()를
  select_operator 호출 전에 먼저 실행해 팝업을 한 번 열었다 닫도록 수정
  (반환값인 전체 사업자 목록은 여기서는 사용하지 않고 버림).
- v1.2 (2026-07-29): 실사용 확인 결과 "최신 2026-07-29"로 표시되면서도
  "미진행"으로 분기되는 오류 확인(값은 같아 보이는데 비교가 실패) - 정확한
  원인은 미확정이나 today_str(str)과 latest_date(parse_ktoa_mvno_excel의
  days.keys()에서 나온 값, 타입/형식이 다를 가능성)의 불일치로 추정.
  normalize_date_str() 헬퍼 신설 - str/datetime/Timestamp 등 어떤 타입이
  와도 'YYYY-MM-DD' 문자열로 통일한 뒤 비교하도록 근본적으로 수정. 디버그
  로그도 정규화 전/후 값을 함께 남기도록 갱신.
- v1.3 (2026-08-01): 월 경계(자정+월초) 버그 확인 및 수정. ym을
  now_kst.strftime("%Y-%m")로만 계산해서, 자정을 넘겨 새 달로 바뀌는
  순간 아직 지난 달 시트에 남아있는 최신 데이터를 "데이터 없음"으로
  잘못 읽던 문제(실측 확인: 8/1 00:00 실행 시 KTOA 사이트에는 7/31
  데이터가 존재했으나 스크립트는 8월 시트만 조회해 데이터없음으로 오판,
  사용자가 KTOA 사이트 캡처로 직접 확인). get_months_to_check() 신설 -
  매월 1~2일에는 이번 달과 지난 달을 모두 조회해서 합친 뒤 최댓값을
  구하도록 check_once()를 재작성.
- v1.4 (2026-08-02): 확인 대상 날짜를 "오늘"에서 "어제"로 변경. KTOA
  사이트의 실제 반영이 하루 지연되는 패턴(예: 8/1 데이터가 8/2 새벽에야
  반영)이 실측으로 재확인됨 - target을 달력상 오늘로 계산하던 기존
  로직은 이미 반영된 어제자 데이터를 보고도 "미진행"으로 잘못 표시했음
  (사용자가 8/2 00시대에 "최신 2026-08-01"이 계속 찍히는데도 확인 처리가
  안 되는 것을 보고 지적). main()에서 today_str -> target_str(어제)로
  전면 변경, 플래그 저장/조회도 target_str 기준으로 통일.

사용법:
    python3 check_new_data.py
(인자 없음 - 항상 "어제(KST) 날짜가 데이터에 올라왔는지"를 확인)
"""

import os
import logging
from datetime import datetime, timezone, timedelta

from google.cloud import firestore

from ktoa_mvno_scraper import (
    get_driver, login, navigate_to_mnp_operator_view,
    set_query_month, select_operator, download_excel,
    get_operator_list, tg_send_personal, DOWNLOAD_DIR,
)
from ktoa_mvno_parser import parse_ktoa_mvno_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
FLAG_COLLECTION = "ktoa_mvno_check_flags"  # {date: "2026-07-29"} 형태로 "오늘 확인 완료" 기록

# 가볍게 확인할 대표 사업자 (SKT 원조). ktoa_mvno_scraper.py의 MNO_CODES 참고.
CHECK_CODE = "SKT"
CHECK_NAME = "SKT"
CHECK_NETWORK = "SKT"


def normalize_date_str(value) -> str | None:
    """
    다양한 타입(str/datetime/date/pandas Timestamp 등)의 날짜값을
    'YYYY-MM-DD' 문자열로 통일. today_str/latest_date 비교가 겉보기엔
    같은 날짜인데도 실패하던 문제(실측 확인, 원인은 타입/형식 불일치로
    추정)를 근본적으로 막기 위해, 비교 직전 양쪽 다 이 함수를 거친다.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()[:10]  # 혹시 시간(hh:mm:ss)이나 공백이 붙어 있어도 날짜부분만
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def already_confirmed_today(db, today_str: str) -> bool:
    """오늘자 신규데이터 확인이 이미 완료됐는지(Firestore 플래그) 체크."""
    doc = db.collection(FLAG_COLLECTION).document(today_str).get()
    return doc.exists


def mark_confirmed(db, today_str: str, latest_date: str) -> None:
    """오늘자 확인 완료 플래그 기록 - 이후 시간대 스킵용."""
    db.collection(FLAG_COLLECTION).document(today_str).set({
        "confirmed_at": datetime.now(KST).isoformat(),
        "latest_date": latest_date,
    })


def get_months_to_check(now_kst: datetime) -> list[str]:
    """
    조회 대상 월 목록. 평소엔 이번 달 하나만.
    월초(1~2일)엔 지난 달도 같이 조회 - 자정을 넘으면 ym이 새 달로 바뀌어
    버려서, 아직 지난 달 시트에 남아있는 최신 데이터(예: 7/31자)를
    "데이터 없음"으로 잘못 읽던 문제(실측 확인: 8/1 00시 확인에서
    "데이터 없음"으로 표시됐으나 실제로는 KTOA 사이트에 7/31 데이터가
    있었음)를 막기 위함.
    """
    months = [now_kst.strftime("%Y-%m")]
    if now_kst.day <= 2:
        first_of_month = now_kst.date().replace(day=1)
        prev_month_last_day = first_of_month - timedelta(days=1)
        months.append(prev_month_last_day.strftime("%Y-%m"))
    return months


def check_once() -> tuple[bool, str | None]:
    """
    SKT 원조 1개만 로그인->선택->다운로드->파싱해 최신 날짜 확인.
    월초(1~2일)엔 이번 달과 지난 달을 모두 조회해서 합친다(get_months_to_check 참고).
    반환: (성공여부, 최신날짜 또는 None)
    """
    now_kst = datetime.now(KST)
    months = get_months_to_check(now_kst)
    driver = None
    all_days: dict = {}
    try:
        driver = get_driver()
        login(driver)
        navigate_to_mnp_operator_view(driver)
        # select_operator()가 내부적으로 호출하는 사이트 JS(menuClick)가 close_b3() 등
        # 팝업 관련 함수를 참조하는데, 이 함수들은 사업자 목록 팝업을 한 번 열어야
        # (getComp() 호출로 관련 스크립트가 로드되어야) 정의됨. 팝업을 연 적 없이
        # 바로 select_operator를 호출하면 "close_b3 is not defined" 오류 발생(실측 확인).
        # get_operator_list()로 팝업을 한 번 열었다 닫아서 이 문제를 우회 - 반환값(전체
        # 사업자 목록)은 여기서는 필요 없으므로 버림.
        get_operator_list(driver)

        for ym in months:
            set_query_month(driver, ym)
            select_operator(driver, CHECK_CODE, CHECK_NAME)
            excel_path = download_excel(driver, tag=f"{CHECK_NAME}_{ym}")
            parsed = parse_ktoa_mvno_excel(excel_path, to_name=CHECK_NAME, to_code=CHECK_CODE, to_network=CHECK_NETWORK)
            all_days.update(parsed.get("days", {}))

        latest_date = max(all_days.keys()) if all_days else None
        return True, latest_date
    finally:
        if driver:
            driver.quit()


def main():
    now_kst = datetime.now(KST)
    # 확인 대상은 "오늘"이 아니라 "어제" - KTOA 사이트 반영이 하루 지연되는
    # 실측 패턴(예: 8/1 데이터가 8/2 새벽에 반영)에 맞춤. 예전엔 target을
    # 달력상 오늘로 계산해서, 이미 반영된 어제자 데이터를 보고도 계속
    # "미진행"으로 잘못 표시하던 문제가 있었음(사용자 실측 확인).
    target_date = now_kst.date() - timedelta(days=1)
    target_str = target_date.strftime("%Y-%m-%d")
    hour_label = now_kst.strftime("%H시")

    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

    if already_confirmed_today(db, target_str):
        log.info(f"대상일({target_str}) 이미 확인 완료 - 스킵")
        return  # 조용히 종료, 텔레그램 알림 없음(반복 알림 방지)

    try:
        success, latest_date = check_once()
    except Exception as e:
        log.error(f"확인 과정 실패: {e}")
        tg_send_personal(f"⚠️ {hour_label} 확인 : 오류 발생 ({e})")
        return

    if not success or latest_date is None:
        log.warning("파싱 결과에 날짜 데이터 없음")
        tg_send_personal(f"{hour_label} 확인 : 최신업데이트 미진행 (데이터 없음)")
        return

    # target_str/latest_date 둘 다 명시적으로 정규화 후 비교 (타입/형식 불일치 방지)
    target_norm = normalize_date_str(target_str)
    latest_norm = normalize_date_str(latest_date)
    log.info(f"[디버그] target_norm={target_norm!r}, latest_norm={latest_norm!r}, "
             f"동일여부={latest_norm == target_norm} "
             f"(원본 latest_date={latest_date!r}, type={type(latest_date).__name__})")

    if latest_norm == target_norm:
        log.info(f"신규일자 확인됨: {latest_norm}")
        tg_send_personal(f"{hour_label} 확인 : 신규일자 확인 ({latest_norm})")
        mark_confirmed(db, target_str, latest_norm)
    else:
        log.info(f"아직 확인 안됨 (대상 {target_norm}, 최신 {latest_norm})")
        tg_send_personal(f"{hour_label} 확인 : 최신업데이트 미진행 (최신 {latest_norm})")


if __name__ == "__main__":
    main()