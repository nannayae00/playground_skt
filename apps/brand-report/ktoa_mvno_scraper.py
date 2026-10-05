"""
ktoa_mvno_scraper.py  v1.10
작성일: 2026-07-27

[수정 이력]
v1.10 | 2026-09-10 | navigate_to_mnp_operator_view()의 "pageBeforeDay is not
  defined" 간헐 오류 수정. 로그인 직후 고정 sleep(1초)만 믿고 바로
  execute_script로 pageBeforeDay()를 호출했는데, 이 함수는 리다이렉트된
  메인 페이지 JS가 완전히 로드돼야 정의됨. 낮 시간엔 항상 충분했지만
  자정 전후(KTOA 야간 마감배치로 서버 응답 느려지는 시간대로 추정)에만
  간헐적으로 로드가 안 끝난 상태에서 호출되어 오류 발생(check_new_data.py
  00시 확인 job에서만 반복 발생, 낮 시간 mvno-brand-report-job은 항상
  정상이었던 것과 일치). 고정 sleep 대신 WebDriverWait로 pageBeforeDay
  함수가 실제로 window에 정의될 때까지(최대 15초) 명시적으로 대기하도록
  변경 - 로드가 그 안에 끝나면 즉시 진행, 15초 넘으면 TimeoutException으로
  명확히 실패해서 원인 추적도 쉬워짐.
v1.9 | 2026-08-07 | 로그인 비밀번호 후보 순차 시도로 변경. 사용자 확인:
  비밀번호가 3개월마다 사람이 수동으로 3개 값(ghkddbsrn1!/2!/3!) 중 하나로
  바꾸는 방식이라 날짜 기반 예측이 불가능함. KTOA_USER_PW_CANDIDATES
  환경변수(콤마구분, 3개 값 등록)를 두고 login()이 순서대로 시도하다가
  로그인 폼(#userid)이 사라지는 시점(=성공)에서 멈추도록 변경 - 실패로
  추정되면 다음 후보로 자동 재시도. 기존 KTOA_USER_PW 단일값도 하위호환
  유지(_get_pw_candidates()가 CANDIDATES 없으면 그걸로 폴백).
  ⚠️ Cloud Run Job 환경변수도 KTOA_USER_PW_CANDIDATES="ghkddbsrn1!,ghkddbsrn2!,ghkddbsrn3!"
  로 갱신 필요(재배포 시 반영).
v1.8 | 2026-08-07 | backfill_year() 신설 - 2016~2023 등 과거 다년치 백필을
  연 단위로 진행하기 위함(사용자 확정: "1년씩 끊어서"). 월이 끝날 때마다
  즉시 Firestore 저장(run()처럼 전체 달을 다 모았다가 마지막에 한 번에
  저장하지 않음 - 12개월치를 한 실행에서 몰아서 하면 중간에 실패 시 이전
  달들까지 다 날아가는 위험이 있어서, 월 단위로 저장 지점을 나눔). CLI에서
  BACKFILL_YEAR=2016 환경변수로 실행. 신규 사업자 감지는 target_ym 백필과
  동일하게 스킵(과거 데이터라 의미 없음).
v1.7 | 2026-08-07 | 신규 사업자 2단계 감지+알림 추가 (ktoa_mvno_firestore.py v2.1과
  연동). get_operator_list()는 이미 매번 KTOA 사이트에서 실시간 목록을 긁어와서
  데이터 수집은 자동으로 되고 있었지만, "새로 생겼다"는 알림이 없었음(사용자 요청).
  등록 시점(코드가 목록에 처음 나타난 날)과 실적 시작 시점(IN>0이 처음 나온 날)이
  다를 수 있어서(사용자 지적 - 등록만 되고 서비스는 나중에 시작하는 경우 있음)
  두 시점에 각각 별도 텔레그램 알림 발송. _collect_one_month()가 operators
  목록도 반환하도록 변경, run()에서 첫 번째(이번달) 수집의 operators로
  register_new_operators()/check_in_start() 호출. target_ym 지정된 백필
  실행에서는 신규 감지 로직 자체를 스킵(과거 시점 기준 신규 판단은 무의미).
v1.1 | 2026-07-29 | 자동화(Cloud Run Job) 전환 준비
  - ktoa_telegram 모듈 import 완전 제거. 기존 tg_send(ktoa_telegram._send)는
    모듈 전역 CHAT_ID(공용방) 고정이고, 실제로는 어디서도 호출되지 않는
    죽은 코드였음. tg_send_personal() 신설 - requests로 직접 구현,
    PERSONAL_CHAT_ID(개인방, ktoa_mvno_report.py와 동일 채팅방)로 고정
    전송. 이 변경으로 ktoa_telegram.py를 배포 폴더에 포함할 필요가 없어짐
    (brand-report/ 서브폴더가 원본 폴더와 파일을 공유하지 않게 됨).
  - 안정성 확인(사용자 실측: 부분 실행 결과 안정적) 후 자동화 반영.
v1.2 | 2026-07-29 | 실제 자동화 실행(129개 성공/0실패) 확인 후 피드백 반영
  - 수집 완료 텔레그램 메시지에 "최신수집일" 라인 추가. 스크래핑된 모든
    사업자의 parsed["days"] 키(날짜) 중 최댓값을 사용 - KTOA 사이트가
    당일 오전엔 아직 전날 마감 데이터가 안 올라와 있을 수 있어 "오늘/어제"
    로 가정하지 않고 실제 파싱 결과에서 직접 확인.
v1.3 | 2026-07-31 | 실사용 중 대량 실패("tab crashed" + 컨테이너 OOM) 확인
  및 수정. 22:20 실행에서 130개 사업자를 하나의 Chrome 드라이버로 계속
  순회하다 메모리가 누적되어 뒷부분(L-MVNO 다수)에서 연속 12개 크래시
  발생(실측 확인, S/K-MVNO는 영향 없었음 - 크래시가 뒤쪽 사업자에서
  집중 발생). 매 N개마다 무조건 드라이버를 재시작하는 방식도 검토했으나
  정상 동작 중에도 불필요한 재로그인 비용이 들어 비효율적이라는 피드백에
  따라, 실패가 실제로 발생했을 때만 반응적으로 드라이버를 재시작하고
  같은 사업자를 그 자리에서 즉시 한 번 더 시도하는 방식으로 변경
  (_fresh_driver() 헬퍼 신설 - 로그인/화면진입/조회월설정을 한 번에 처리).
v1.4 | 2026-07-31 | v1.3 배포 후 실사용 확인 결과 재발 버그 2건 확인 및 수정.
  (1) _fresh_driver()에 get_operator_list() 호출이 누락되어, 재시작 직후
      select_operator에서 "close_b3 is not defined" 오류가 재발함(v1.1에서
      이미 한 번 고쳤던 문제가 재시작 경로에서는 반영이 안 됐던 것 - 실측
      확인: 04:16 실행에서 GMELG/친구아이앤씨LG/찬스모바일LG 등 재시도
      시도 자체가 이 오류로 실패). get_operator_list() 호출을 추가하고,
      run()에서 이미 사업자 목록을 다시 조회하던 중복 호출도 제거 -
      _fresh_driver()가 (driver, operators) 튜플을 반환하도록 변경.
  (2) OOM으로 인한 tab crashed가 재시작 로직 도입 후에도 일부 재발
      (실측: Out-of-memory event detected in container) - 코드만으로는
      완전히 막을 수 없어 Cloud Run Job 메모리를 2Gi -> 4Gi로 증설 병행.
v1.5 | 2026-08-01 | 월 경계(자정+월초) 버그 확인 및 수정. run()이
  ym = now_kst.strftime("%Y-%m")로 "당월"만 계산해서, 월초(1~2일)에
  실행되면 리포트가 필요로 하는 "어제" 데이터가 지난 달에 속하는데도
  지난 달 시트를 전혀 조회하지 않아 통째로 누락됨(실측 확인: 8/1 07:20
  실행에서 7/31 데이터가 전혀 수집되지 않아 리포트 3개 섹션 모두
  "데이터 없음"으로 발송 - check_new_data.py와 동일한 근본 원인).
  get_months_to_check() 신설(check_new_data.py와 동일 로직) - 매월
  1~2일에는 이번 달/지난 달 모두에 대해 전체 사업자를 수집하도록
  run()을 재구성(_collect_one_month()로 단일 월 수집 로직 분리, run()은
  months를 순회하며 각 사업자의 days를 병합). build_brand_out/
  build_carrier_summary도 기존엔 마지막 ym 하나만 참조하던 버그가 있어
  months 전체에 대해 호출하도록 수정.
v1.6 | 2026-08-02 | 과거 데이터 백필 지원. run()에 target_ym 파라미터
  추가 - 지정하면 get_months_to_check()의 자동 계산(이번달/지난달)을
  건너뛰고 지정한 달 하나만 수집. CLI 실행 시 TARGET_YM 환경변수로
  지정 가능(예: TARGET_YM=2026-01 python ktoa_mvno_scraper.py). 2026년
  1~6월 등 과거 월을 한 달씩 수동으로 여러 번 실행해서 백필하는 용도
  (사용자 확정 - 자동 순차 실행 아닌 수동 단발 실행 방식).

⚠️ 테스트 단계 스크립트입니다. 아래 SELECTOR/함수명은 개발자도구로 확인된 값 기준이며,
   실제 실행 시 로그를 보고 조정이 필요할 수 있습니다.
   - 사업자 팝업 여는 트리거(라디오/입력창 클릭)의 정확한 selector는 미확인 → TODO 표시
   - 조회일자가 사업자 변경 시 유지되는지 여부는 최초 실행 로그로 확인 필요
"""

import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ktoa_mvno_parser import parse_ktoa_mvno_excel
from ktoa_mvno_firestore import (
    save_brand_in_batch, build_brand_out, build_carrier_summary,
    register_new_operators, check_in_start,
)

# 수집 완료 알림: 개인방(ktoa_mvno_report.py와 동일 채팅방)으로 직접 전송.
# ktoa_telegram.py는 이 파이프라인에서 사용하지 않음(공용방 고정이라 부적합) - import 제거.
PERSONAL_CHAT_ID = "-1003761301521"


def tg_send_personal(msg: str) -> None:
    import requests
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        log.warning("[텔레그램 비활성 - 미전송] TELEGRAM_TOKEN 미설정")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": PERSONAL_CHAT_ID, "text": msg}, timeout=10)
        result = resp.json()
        if result.get("ok"):
            log.info("텔레그램 전송 완료 (개인방)")
        else:
            log.error(f"텔레그램 전송 실패: {result}")
    except Exception as e:
        log.error(f"텔레그램 전송 오류: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SITE_URL = "https://comstat.ktoa.or.kr/main.do"
USER_ID = os.environ["KTOA_USER_ID"]
DOWNLOAD_DIR = "/tmp/ktoa_mvno_downloads"
KST = timezone(timedelta(hours=9))

MAX_RETRY_PASS = 2  # 실패 시 재시도 횟수
DEBUG_DIR = "/tmp/ktoa_mvno_debug"


def _get_pw_candidates() -> list:
    """
    비밀번호가 3개월마다 사람이 수동으로 3개 값 중 하나로 바꾸는 방식이라
    (날짜 기반 패턴 없음 - 사용자 확인, 2026-08-07) 미리 계산해서 맞힐 수
    없음. 대신 KTOA_USER_PW_CANDIDATES(콤마 구분 - 3개 값 다 등록)를 두고
    로그인 시 순서대로 시도하다가 성공하는 값을 씀. 없으면 기존
    KTOA_USER_PW 단일값(하위호환).
    """
    candidates_env = os.environ.get("KTOA_USER_PW_CANDIDATES")
    if candidates_env:
        return [p.strip() for p in candidates_env.split(",") if p.strip()]
    return [os.environ["KTOA_USER_PW"]]


def _debug_screenshot(driver: webdriver.Chrome, tag: str) -> None:
    """디버깅용 스크린샷 저장 (DEBUG=1 환경변수일 때만 동작)"""
    if os.environ.get("DEBUG") != "1":
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{tag}.png")
        driver.save_screenshot(path)
        log.info(f"[DEBUG] 스크린샷 저장: {path}")
        html_path = os.path.join(DEBUG_DIR, f"{tag}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log.info(f"[DEBUG] HTML 저장: {html_path}")
    except Exception as e:
        log.warning(f"[DEBUG] 스크린샷 저장 실패: {e}")


def _debug_console_log(driver: webdriver.Chrome, tag: str) -> None:
    """브라우저 콘솔 로그(JS 에러 포함) 캡처 (DEBUG=1일 때만)"""
    if os.environ.get("DEBUG") != "1":
        return
    try:
        logs = driver.get_log("browser")
        if not logs:
            log.info(f"[DEBUG:{tag}] 콘솔 로그 없음")
            return
        for entry in logs:
            log.info(f"[DEBUG:{tag}] 콘솔[{entry['level']}] {entry['message']}")
    except Exception as e:
        log.warning(f"[DEBUG] 콘솔 로그 조회 실패 (브라우저 옵션 미설정 가능): {e}")


# ─────────────────────────────────────────────────────────────
# 드라이버 / 로그인 (기존 ktoa_scraper.py 재활용)
# ─────────────────────────────────────────────────────────────
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
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_settings.popups": 0,
    })
    options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    driver = webdriver.Chrome(options=options)

    # headless Chrome은 다운로드 동작이 기본 차단될 수 있어 CDP로 명시적 허용
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": DOWNLOAD_DIR,
    })
    return driver


def login(driver: webdriver.Chrome) -> None:
    """
    비밀번호 후보(_get_pw_candidates())를 순서대로 시도 - 로그인 폼(#userid)이
    시도 후에도 여전히 남아있으면 실패로 간주하고 다음 후보로 넘어감.
    전부 실패하면 RuntimeError(비밀번호 3개 다 확인 필요하다는 신호).
    """
    candidates = _get_pw_candidates()

    for i, pw in enumerate(candidates, 1):
        log.info(f"로그인 시도 {i}/{len(candidates)}번째 비밀번호 후보... (SITE_URL 접속)")
        driver.get(SITE_URL)
        _debug_screenshot(driver, f"01_after_get_try{i}")

        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.ID, "userid")))
        driver.find_element(By.ID, "userid").clear()
        driver.find_element(By.ID, "userid").send_keys(USER_ID)
        driver.find_element(By.ID, "pass").clear()
        driver.find_element(By.ID, "pass").send_keys(pw)
        _debug_screenshot(driver, f"02_before_login_click_try{i}")

        driver.find_element(By.XPATH, "//img[@alt='보내기']").click()
        time.sleep(4)
        _debug_screenshot(driver, f"03_after_login_click_try{i}")

        # 로그인 성공 여부: 로그인 폼(#userid)이 여전히 있으면 실패로 간주
        try:
            driver.find_element(By.ID, "userid")
            login_failed = True
        except Exception:
            login_failed = False

        if not login_failed:
            log.info(f"로그인 성공 ({i}번째 비밀번호 후보)")
            try:
                driver.find_element(By.XPATH, '//*[@id="myPopup"]/div/span[1]').click()
                time.sleep(1)
                log.info("로그인 후 팝업 닫기 완료")
            except Exception:
                log.info("로그인 후 팝업 없음 (또는 닫기 실패, 무시)")
            _debug_screenshot(driver, "04_after_popup_close")
            log.info("로그인 완료")
            return

        log.warning(f"로그인 실패로 추정({i}번째 비밀번호 후보) - 다음 후보로 재시도")

    raise RuntimeError(
        f"비밀번호 후보 {len(candidates)}개 전부 로그인 실패 - "
        f"KTOA_USER_PW_CANDIDATES 최신값 확인 필요(3개월 주기 변경)"
    )


def navigate_to_mnp_operator_view(driver: webdriver.Chrome) -> None:
    """번호현황 조회 > MNP 등록현황 > 사업자 화면으로 이동"""
    log.info("메뉴 이동: 번호현황 조회 > MNP 등록현황")
    wait = WebDriverWait(driver, 15)

    # 실측 확인: 상단 메뉴는 li.menuPartOn3에 onclick="pageBeforeDay('mnpReg.do?type=8','MNP 등록현황')"
    # hover로 열리는 드롭다운이라 클릭이 불안정 → JS 함수 직접 호출이 안정적

    # pageBeforeDay()는 로그인 후 리다이렉트된 메인 페이지 JS가 완전히 로드돼야
    # 정의됨. 고정 sleep으로는 자정 전후 서버 응답이 느려질 때 부족해서
    # "pageBeforeDay is not defined" 오류가 간헐 발생(실측 확인) - 함수가 실제로
    # window에 정의될 때까지 명시적으로 대기.
    wait.until(lambda d: d.execute_script(
        "return typeof pageBeforeDay === 'function';"
    ))

    driver.execute_script("pageBeforeDay('mnpReg.do?type=8','MNP 등록현황');")
    time.sleep(1.5)
    _debug_screenshot(driver, "10_after_menu_click")

    # '사업자' 라디오 선택 (실측 확인: div.radioText 텍스트 클릭 방식, onclick="radioChecked(this)")
    wait.until(EC.presence_of_element_located(
        (By.XPATH, "//div[contains(@class,'radioText') and contains(text(),'사업자')]")
    ))
    driver.find_element(By.XPATH, "//div[contains(@class,'radioText') and contains(text(),'사업자')]").click()
    time.sleep(1)
    _debug_screenshot(driver, "12_after_radio_click")

    wait.until(EC.presence_of_element_located((By.ID, "excelBt")))
    log.info("MNP 등록현황(사업자) 화면 진입 완료")


def get_operator_list(driver: webdriver.Chrome) -> list[dict]:
    """
    사업자 선택 팝업에서 전체 사업자 (code, name, network) 추출.
    li.menuPup 구조: <li class="menuPup" value="S01">아이즈비전SKT</li>
    """
    log.info("사업자 목록 팝업 열기 시도...")
    _debug_screenshot(driver, "05_before_popup_trigger")
    # 실측 확인: <input id="mvnos" ... onclick="getComp()"> 클릭 시 팝업(#poptbody) 오픈
    driver.find_element(By.ID, "mvnos").click()
    time.sleep(1)

    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "poptbody")))
    # poptbody 컨테이너 존재만으론 부족 — 실제 li.menuPup 항목이 채워질 때까지 대기
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#poptbody li.menuPup")) > 0)
    time.sleep(0.5)
    _debug_screenshot(driver, "06_popup_opened")

    items = driver.find_elements(By.CSS_SELECTOR, "#poptbody li.menuPup")
    log.info(f"팝업 내 li.menuPup 요소 개수: {len(items)}")
    if items:
        # 첫 항목의 실제 속성값들을 로그로 남겨 진단 (value/attr 정확한 이름 확인용)
        first = items[0]
        log.info(
            f"[DEBUG] 첫 항목 text={first.text!r} "
            f"value={first.get_attribute('value')!r} "
            f"outerHTML={driver.execute_script('return arguments[0].outerHTML;', first)!r}"
        )
    operators = []
    skipped = []

    # MVNO 코드는 S01~S19 / K01~K48 / L01~L57 형태 (엑셀 컬럼 헤더와 동일 패턴).
    code_pattern = re.compile(r"^[SKL]\d{2}$")
    # 원조 3사는 팝업 코드가 "SKT"/"KTF"/"LGT" (엑셀 컬럼 헤더와 동일) →
    # carrier_summary의 total_in을 채우려면 이들도 to로 스크래핑해야 하므로 명시적으로 포함.
    MNO_CODES = {"SKT": "SKT", "KTF": "KT", "LGT": "LGU"}
    # 코드 패턴(S01~/K01~/L01~)에 안 걸리지만 실제 실적이 있는 MVNO 4개.
    # 이름 기준으로 소속 network 판별: SK텔링크→SKT망, LG헬로비전KT/세종텔레콤(KT)→KT망,
    # KCT는 원조사 제휴코드라 실적 유무 확인 후 K망으로 잠정 분류 (엑셀 헤더 KCT 위치가 KT 다음이라 K망 추정).
    # 실무자 원본 데이터(Raw_당월)로 검증된 정확한 network 소속.
    # KCT는 KT가 아니라 SKT 소속(S-MVNO)임을 골드 스탠다드 대조로 확인함(2026-07-28).
    EXTRA_CODES = {"KCT": "SKT", "SKL": "SKT", "CJM": "KT", "ONS": "KT"}

    for item in items:
        # Selenium get_attribute('value')가 <li>의 DOM 프로퍼티(value=0)와 충돌할 수 있어
        # JS getAttribute()로 HTML 속성값을 명시적으로 읽음
        code = (driver.execute_script("return arguments[0].getAttribute('value');", item) or "").strip()
        name = item.text.strip()
        if not code or not name:
            continue

        if code in MNO_CODES:
            operators.append({"code": code, "name": name, "network": MNO_CODES[code]})
            continue

        if code in EXTRA_CODES:
            operators.append({"code": code, "name": name, "network": EXTRA_CODES[code]})
            continue

        if not code_pattern.match(code):
            skipped.append(f"{code}:{name}")
            continue

        net = {"S": "SKT", "K": "KT", "L": "LGU"}[code[0]]
        operators.append({"code": code, "name": name, "network": net})

    log.info(f"사업자 목록 추출 완료: {len(operators)}개 (제외 {len(skipped)}개: {', '.join(skipped[:10])}{'...' if len(skipped) > 10 else ''})")

    # 팝업 닫기 (바깥 클릭 or X 버튼)
    # 목록 추출용으로만 열었으므로, 사이트 자체 닫기 함수로 정리
    try:
        driver.execute_script("close_b3();")
    except Exception:
        driver.execute_script("document.body.click();")
    time.sleep(0.5)

    return operators


def set_query_month(driver: webdriver.Chrome, ym: str) -> None:
    """조회일자 시작~종료를 동일 월(YYYY-MM)로 세팅 (당월 전체 조회)"""
    driver.execute_script(f"""
        document.getElementById('startDtVal').value = '{ym}';
        document.getElementById('endDtVal').value = '{ym}';
    """)
    log.info(f"조회일자 세팅: {ym} ~ {ym}")


def select_operator(driver: webdriver.Chrome, code: str, name: str) -> None:
    """사업자 선택 (menuClick 직접 호출 → 화면 자동 갱신)"""
    driver.execute_script(f"menuClick('{name}', '{code}');")

    # menuClick이 실제로 끝났다는 가장 확실한 증거: #mvnos 값이 방금 선택한 사업자명으로 바뀜.
    # staleness_of처럼 간접 신호를 기다리지 않고 이 조건 자체를 폴링 → 끝나는 즉시 통과.
    wait = WebDriverWait(driver, 10, poll_frequency=0.2)
    wait.until(lambda d: d.execute_script("return document.getElementById('mvnos').value;") == name)

    if os.environ.get("DEBUG") == "1":
        _debug_console_log(driver, f"select_{name}")


def download_excel(driver: webdriver.Chrome, tag: str) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    before = set(os.listdir(DOWNLOAD_DIR))
    driver.execute_script("excelDownLoad('8');")
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
            log.info(f"[{tag}] 다운로드 완료: {new_files[0]}")
            return path

    _debug_screenshot(driver, f"fail_download_{tag}")
    # 브라우저 콘솔 로그 캡처 (JS 에러 확인용)
    try:
        logs = driver.get_log("browser")
        for entry in logs[-20:]:
            log.warning(f"[{tag}] 콘솔로그: {entry.get('level')} {entry.get('message')}")
    except Exception as e:
        log.warning(f"[{tag}] 콘솔로그 조회 실패: {e}")

    # 다운로드 폴더 현재 상태도 남김 (crdownload로 걸려있는지 등)
    log.warning(f"[{tag}] 다운로드 폴더 현재 파일: {sorted(os.listdir(DOWNLOAD_DIR))}")

    raise TimeoutError(f"[{tag}] 엑셀 다운로드 시간 초과 (30초)")


# ─────────────────────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────────────────────
# 실패(예: tab crashed) 발생 시에만 드라이버를 재시작한다. 매 N개마다 무조건
# 재시작하면 정상 동작 중에도 불필요하게 재로그인 비용이 들어 비효율적 -
# 문제가 실제로 생겼을 때만 반응적으로 대응.


def _fresh_driver(ym: str) -> tuple["webdriver.Chrome", list]:
    """
    새 Chrome 드라이버를 만들고 로그인->조회화면 진입->조회월 설정->사업자 목록
    조회까지 완료해서 (driver, operators) 튜플로 반환.
    get_operator_list()로 사업자 목록 팝업을 한 번 열었다 닫아야 사이트 JS(menuClick이
    참조하는 close_b3 등)가 정의됨 - 이 호출이 빠지면 재시작 직후 select_operator에서
    "close_b3 is not defined" 오류가 재발함(실측 확인: 재시작 로직 최초 도입 시 누락).
    """
    driver = get_driver()
    login(driver)
    navigate_to_mnp_operator_view(driver)
    set_query_month(driver, ym)
    operators = get_operator_list(driver)
    return driver, operators


def get_months_to_check(now_kst: datetime) -> list[str]:
    """
    수집 대상 월 목록. 평소엔 이번 달 하나만.
    매월 1~2일에는 지난 달도 같이 수집 - run_mvno_brand_job.py가 리포트
    대상일로 "어제"를 쓰는데, 월초에 실행되면 어제는 지난 달에 속함.
    ym을 "당월"로만 계산하면 지난 달 시트를 아예 조회하지 않아 어제자
    데이터가 ktoa_mvno_brand_in에 통째로 누락됨(실측 확인: 8/1 07:20
    실행에서 7/31 데이터가 전혀 수집되지 않아 리포트 3개 섹션이 모두
    "데이터 없음"으로 발송됨 - check_new_data.py와 동일한 근본 원인).
    """
    months = [now_kst.strftime("%Y-%m")]
    if now_kst.day <= 2:
        first_of_month = now_kst.date().replace(day=1)
        prev_month_last_day = first_of_month - timedelta(days=1)
        months.append(prev_month_last_day.strftime("%Y-%m"))
    return months


def _collect_one_month(ym: str, test_limit: int | None) -> tuple[dict, list, list]:
    """
    지정한 월(ym) 하나에 대해 전체 사업자(또는 test_limit개)를 수집.
    반환: (results, failed, operators) - results는 {code: parsed}, failed는
    실패한 operator 목록, operators는 이번 실행에서 실제 대상으로 삼은 사업자
    전체 목록(신규 사업자 감지용으로 run()에 그대로 전달됨).
    """
    driver = None
    results = {}
    failed = []
    operators = []

    try:
        driver, operators = _fresh_driver(ym)
        log.info(f"[{ym}] Chrome 드라이버 생성 완료")

        if os.environ.get("TEST_ONLY_MNO") == "1":
            operators = [op for op in operators if op["code"] in ("SKT", "KTF", "LGT")]
            log.info(f"TEST_ONLY_MNO: 원조3사만 테스트 ({len(operators)}개)")
        elif os.environ.get("TEST_ONLY_EXTRA") == "1":
            operators = [op for op in operators if op["code"] in ("KCT", "SKL", "CJM", "ONS")]
            log.info(f"TEST_ONLY_EXTRA: 신규 추가 4개만 테스트 ({len(operators)}개)")
        elif test_limit:
            operators = operators[:test_limit]
            log.info(f"TEST MODE: 사업자 {test_limit}개만 실행")

        pending = operators
        for attempt in range(1, MAX_RETRY_PASS + 1):
            log.info(f"=== [{ym}] {attempt}차 패스: 대상 {len(pending)}개 ===")
            still_failed = []

            for op in pending:
                code, name, network = op["code"], op["name"], op["network"]

                try:
                    select_operator(driver, code, name)
                    excel_path = download_excel(driver, tag=f"{name}_{ym}")
                    parsed = parse_ktoa_mvno_excel(excel_path, to_name=name, to_code=code, to_network=network)
                    results[code] = parsed
                    log.info(f"[{name}] 파싱 완료 ({len(parsed.get('days', {}))}일치)")
                    continue
                except Exception as e:
                    log.error(f"[{name}] 실패: {e} - 드라이버 재시작 후 즉시 재시도")

                # 실패 시(예: tab crashed)에만 드라이버를 재시작하고 같은 항목을
                # 그 자리에서 한 번 더 시도한다 - 정상 동작 중엔 재로그인 비용을
                # 전혀 들이지 않기 위함.
                try:
                    driver.quit()
                except Exception:
                    pass
                driver, _ = _fresh_driver(ym)

                try:
                    select_operator(driver, code, name)
                    excel_path = download_excel(driver, tag=f"{name}_{ym}")
                    parsed = parse_ktoa_mvno_excel(excel_path, to_name=name, to_code=code, to_network=network)
                    results[code] = parsed
                    log.info(f"[{name}] 재시작 후 재시도 성공 ({len(parsed.get('days', {}))}일치)")
                except Exception as e2:
                    log.error(f"[{name}] 재시도 후에도 실패: {e2}")
                    still_failed.append(op)

            pending = still_failed
            if not pending:
                break

        failed = pending

    finally:
        if driver:
            driver.quit()

    return results, failed, operators


def run(test_limit: int | None = None, target_ym: str | None = None) -> None:
    """
    test_limit: 테스트 시 사업자 N개만 돌리고 싶을 때 지정 (None이면 전체)
    target_ym: 특정 월(예: "2026-01")만 수집하고 싶을 때 지정 - 과거 데이터
        백필용. 지정하면 get_months_to_check()의 자동 계산(이번달/지난달)을
        건너뛰고 이 달 하나만 수집한다. None이면 기존과 동일하게 자동 계산.
    매월 1~2일에는 이번 달/지난 달을 모두 수집해서 병합(get_months_to_check 참고,
    target_ym 미지정 시).
    """
    now_kst = datetime.now(KST)
    months = [target_ym] if target_ym else get_months_to_check(now_kst)
    log.info(f"=== KTOA MVNO 상세 수집 시작: {now_kst.strftime('%Y-%m-%d %H:%M KST')} (대상월: {months}) ===")

    results: dict = {}   # code -> parsed dict (여러 달의 days를 병합)
    failed_by_code: dict = {}  # code -> operator dict (마지막으로 실패한 시도 기준)
    primary_operators: list = []  # 첫 번째(=이번달) 수집에서 얻은 사업자 전체 목록 - 신규 감지용

    for i, ym in enumerate(months):
        month_results, month_failed, operators = _collect_one_month(ym, test_limit)
        if i == 0:
            primary_operators = operators

        for code, parsed in month_results.items():
            if code not in results:
                results[code] = parsed
            else:
                results[code]["days"].update(parsed.get("days", {}))
                # to/to_code/to_network는 달마다 동일해야 정상이므로 최초 값 유지
            failed_by_code.pop(code, None)  # 이번 달엔 성공했으므로 실패 목록에서 제거

        for op in month_failed:
            failed_by_code.setdefault(op["code"], op)

    failed = list(failed_by_code.values())

    log.info(f"=== 수집 종료: 성공 {len(results)} / 실패 {len(failed)} ===")

    # ── 신규 사업자 2단계 감지 ───────────────────────────────
    # target_ym이 지정된 경우(백필/과거월 수동 조회)는 스킵 - 과거 시점 기준으로
    # "신규"를 판단하면 의미가 없고, 이미 다 아는 사업자들이 전부 "신규"로
    # 오탐될 수 있음. 평소 자동 실행(target_ym=None)에서만 동작.
    if target_ym is None:
        try:
            new_registrations = register_new_operators(
                primary_operators, now_kst.strftime("%Y-%m-%d")
            )
            if new_registrations:
                lines = "\n".join(
                    f"- {op['name']} ({op['code']}, {op['network']})" for op in new_registrations
                )
                tg_send_personal(f"🆕 신규 사업자 등록 감지\n{lines}\n\n(실적은 아직 0일 수 있음 - 실적 시작 시 별도 알림)")
        except Exception as e:
            log.warning(f"신규 사업자 등록 감지 실패(무시): {e}")

        try:
            started = check_in_start(results)
            if started:
                lines = "\n".join(
                    f"- {op['name']} ({op['code']}, {op['network']}) 최초실적일: {op['date']}"
                    for op in started
                )
                tg_send_personal(f"📈 신규 사업자 실적 시작\n{lines}")
        except Exception as e:
            log.warning(f"실적 시작 감지 실패(무시): {e}")

    # ── Firestore 저장 ──────────────────────────────────────
    if results:
        brand_registry = {}
        try:
            brand_registry = save_brand_in_batch(results)
            log.info("ktoa_mvno_brand_in 저장 완료")
        except Exception as e:
            log.error(f"Firestore 저장 실패: {e}")

        # months에 포함된 모든 달에 대해 brand_out/carrier_summary를 갱신.
        # (기존엔 단일 ym만 참조했으나, 월초 2일간은 이번달/지난달 둘 다
        # 갱신해야 지난달 마지막 날짜 데이터의 out/summary도 정확해짐)
        for month_ym in months:
            try:
                build_brand_out(month_ym)
                log.info(f"[{month_ym}] ktoa_mvno_brand_out 생성 완료")
            except Exception as e:
                log.error(f"[{month_ym}] brand_out 생성 실패: {e}")

            try:
                build_carrier_summary(month_ym, brand_registry)
                log.info(f"[{month_ym}] ktoa_carrier_summary 생성 완료")
            except Exception as e:
                log.error(f"[{month_ym}] carrier_summary 생성 실패: {e}")

    # ── 텔레그램 요약 알림 ───────────────────────────────────
    # 개인방으로 전송 (공용방 tg_send 아님 - 자동화 전환 시 개인방으로 확정)
    SEND_TELEGRAM = True
    if not SEND_TELEGRAM:
        log.info("[TEST] 텔레그램 알림 비활성화 상태 (전송 안 함)")
        return

    # 최신수집일: 스크래핑된 모든 사업자의 days 키(날짜) 중 가장 최근 날짜.
    # KTOA 사이트가 당일 오전엔 아직 전날 마감 데이터가 안 올라와 있을 수 있어
    # "오늘/어제"로 가정하지 않고 실제 파싱 결과에서 직접 확인.
    all_dates = set()
    for parsed in results.values():
        all_dates.update(parsed.get("days", {}).keys())
    latest_date = max(all_dates) if all_dates else "확인불가"

    try:
        fail_names = ", ".join(f["name"] for f in failed[:10])
        msg = (
            f"📊 KTOA MVNO 상세 수집 완료 ({now_kst.strftime('%Y-%m-%d %H:%M')})\n"
            f"최신수집일: {latest_date}\n"
            f"성공: {len(results)}건 / 실패: {len(failed)}건\n"
        )
        if failed:
            msg += f"실패 목록: {fail_names}{'...' if len(failed) > 10 else ''}"
        tg_send_personal(msg)
    except Exception as e:
        log.warning(f"텔레그램 알림 실패 (무시): {e}")


def backfill_year(year: int, test_limit: int | None = None) -> None:
    """
    특정 연도(1~12월) 전체를 순차 수집 - 월이 끝날 때마다 즉시 저장(월별
    save_brand_in_batch/build_brand_out/build_carrier_summary 즉시 호출).
    run()처럼 전체 달을 다 모았다가 마지막에 한 번에 저장하지 않는 이유:
    12개월치를 한 실행에서 몰아서 돌리면 중간(예: 10번째 달)에 예외나 타임아웃이
    나면 앞서 수집한 9개월치까지 통째로 날아감 - 한 해 단위 백필은 실행 시간이
    길어서(월별 130개 사업자 × 12) 이 위험이 실제로 큼. 월 단위 즉시저장으로
    바꿔서 어디까지 성공했는지 최소한 그 지점까지는 남도록 함.
    신규 사업자 감지(register_new_operators/check_in_start)는 과거 백필이므로
    호출하지 않음(run()의 target_ym 분기와 동일한 이유).
    """
    now_kst = datetime.now(KST)
    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    log.info(f"=== {year}년 전체 백필 시작 ({months[0]}~{months[-1]}) ===")

    total_success = 0
    total_failed = 0
    month_summaries = []

    for ym in months:
        try:
            month_results, month_failed, _operators = _collect_one_month(ym, test_limit)
        except Exception as e:
            log.error(f"[{ym}] 수집 자체가 실패(건너뜀): {e}")
            month_summaries.append(f"{ym}: 수집 실패({e})")
            continue

        if month_results:
            try:
                brand_registry = save_brand_in_batch(month_results)
                build_brand_out(ym)
                build_carrier_summary(ym, brand_registry)
            except Exception as e:
                log.error(f"[{ym}] Firestore 저장 실패: {e}")
                month_summaries.append(f"{ym}: 저장 실패({e})")
                continue

        total_success += len(month_results)
        total_failed += len(month_failed)
        month_summaries.append(f"{ym}: 성공 {len(month_results)} / 실패 {len(month_failed)}")
        log.info(f"[{ym}] 완료 및 저장: 성공 {len(month_results)} / 실패 {len(month_failed)}")

    log.info(f"=== {year}년 전체 백필 종료: 총 성공 {total_success} / 총 실패 {total_failed} ===")

    try:
        lines = "\n".join(month_summaries)
        msg = (
            f"📊 {year}년 전체 백필 완료 ({now_kst.strftime('%Y-%m-%d %H:%M')})\n"
            f"총 성공: {total_success} / 총 실패: {total_failed}\n\n{lines}"
        )
        tg_send_personal(msg)
    except Exception as e:
        log.warning(f"텔레그램 알림 실패 (무시): {e}")


if __name__ == "__main__":
    # 테스트 실행 시: TEST_LIMIT=3 python ktoa_mvno_scraper.py
    # 특정 월 백필 시: TARGET_YM=2026-01 python ktoa_mvno_scraper.py
    # 특정 연도 전체 백필 시: BACKFILL_YEAR=2016 python ktoa_mvno_scraper.py
    limit = os.environ.get("TEST_LIMIT")
    ym_override = os.environ.get("TARGET_YM")
    year_override = os.environ.get("BACKFILL_YEAR")

    if year_override:
        backfill_year(int(year_override), test_limit=int(limit) if limit else None)
    else:
        run(test_limit=int(limit) if limit else None, target_ym=ym_override or None)