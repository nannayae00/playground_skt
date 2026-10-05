"""
ktoa_mvno_scraper.py  v1.0
작성일: 2026-07-27

[수정 이력]
v1.0 | 2026-07-27 | 최초 작성
  - 사업자(130개+) 순회하며 MNP 등록현황(사업자 기준) 엑셀 다운로드
  - li.menuPup 클릭(menuClick) → 화면 자동 갱신 → 엑셀 다운로드
  - 실패 사업자 재시도(2차 패스) + 텔레그램 요약 알림
  - Firestore: ktoa_mvno_flow (to 기준) + ktoa_mvno_flow_pivot (from 기준, 후처리)

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
from ktoa_mvno_firestore import save_brand_in_batch, build_brand_out, build_carrier_summary

try:
    from ktoa_telegram import _send as tg_send
except Exception as _e:  # TELEGRAM_TOKEN 등 환경변수 미설정 시에도 스크립트가 죽지 않도록
    def tg_send(msg: str) -> None:
        logging.getLogger(__name__).warning(f"[텔레그램 비활성 - 미전송] {msg}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SITE_URL = "https://comstat.ktoa.or.kr/main.do"
USER_ID = os.environ["KTOA_USER_ID"]
USER_PW = os.environ["KTOA_USER_PW"]
DOWNLOAD_DIR = "/tmp/ktoa_mvno_downloads"
KST = timezone(timedelta(hours=9))

MAX_RETRY_PASS = 2  # 실패 시 재시도 횟수
DEBUG_DIR = "/tmp/ktoa_mvno_debug"


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
    log.info("로그인 시도... (SITE_URL 접속)")
    driver.get(SITE_URL)
    log.info(f"페이지 접속 완료, 현재 URL: {driver.current_url}")
    _debug_screenshot(driver, "01_after_get")

    wait = WebDriverWait(driver, 15)
    wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(USER_ID)
    driver.find_element(By.ID, "pass").send_keys(USER_PW)
    _debug_screenshot(driver, "02_before_login_click")

    driver.find_element(By.XPATH, "//img[@alt='보내기']").click()
    time.sleep(4)
    _debug_screenshot(driver, "03_after_login_click")

    try:
        driver.find_element(By.XPATH, '//*[@id="myPopup"]/div/span[1]').click()
        time.sleep(1)
        log.info("로그인 후 팝업 닫기 완료")
    except Exception:
        log.info("로그인 후 팝업 없음 (또는 닫기 실패, 무시)")
    _debug_screenshot(driver, "04_after_popup_close")
    log.info("로그인 완료")


def navigate_to_mnp_operator_view(driver: webdriver.Chrome) -> None:
    """번호현황 조회 > MNP 등록현황 > 사업자 화면으로 이동"""
    log.info("메뉴 이동: 번호현황 조회 > MNP 등록현황")
    wait = WebDriverWait(driver, 15)

    # 실측 확인: 상단 메뉴는 li.menuPartOn3에 onclick="pageBeforeDay('mnpReg.do?type=8','MNP 등록현황')"
    # hover로 열리는 드롭다운이라 클릭이 불안정 → JS 함수 직접 호출이 안정적
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
def run(test_limit: int | None = None) -> None:
    """
    test_limit: 테스트 시 사업자 N개만 돌리고 싶을 때 지정 (None이면 전체)
    """
    now_kst = datetime.now(KST)
    ym = now_kst.strftime("%Y-%m")
    log.info(f"=== KTOA MVNO 상세 수집 시작: {now_kst.strftime('%Y-%m-%d %H:%M KST')} ===")

    driver = None
    results = {}       # code -> parsed dict
    failed = []        # [{code, name, network}, ...]

    try:
        driver = get_driver()
        log.info("Chrome 드라이버 생성 완료")
        login(driver)
        navigate_to_mnp_operator_view(driver)

        operators = get_operator_list(driver)

        if os.environ.get("TEST_ONLY_MNO") == "1":
            operators = [op for op in operators if op["code"] in ("SKT", "KTF", "LGT")]
            log.info(f"TEST_ONLY_MNO: 원조3사만 테스트 ({len(operators)}개)")
        elif os.environ.get("TEST_ONLY_EXTRA") == "1":
            operators = [op for op in operators if op["code"] in ("KCT", "SKL", "CJM", "ONS")]
            log.info(f"TEST_ONLY_EXTRA: 신규 추가 4개만 테스트 ({len(operators)}개)")
        elif test_limit:
            operators = operators[:test_limit]
            log.info(f"TEST MODE: 사업자 {test_limit}개만 실행")

        set_query_month(driver, ym)

        pending = operators
        for attempt in range(1, MAX_RETRY_PASS + 1):
            log.info(f"=== {attempt}차 패스: 대상 {len(pending)}개 ===")
            still_failed = []

            for op in pending:
                code, name, network = op["code"], op["name"], op["network"]
                try:
                    select_operator(driver, code, name)

                    excel_path = download_excel(driver, tag=name)
                    parsed = parse_ktoa_mvno_excel(excel_path, to_name=name, to_code=code, to_network=network)
                    results[code] = parsed
                    log.info(f"[{name}] 파싱 완료 ({len(parsed.get('days', {}))}일치)")
                except Exception as e:
                    log.error(f"[{name}] 실패: {e}")
                    still_failed.append(op)

            pending = still_failed
            if not pending:
                break

        failed = pending

    finally:
        if driver:
            driver.quit()

    log.info(f"=== 수집 종료: 성공 {len(results)} / 실패 {len(failed)} ===")

    # ── Firestore 저장 ──────────────────────────────────────
    if results:
        brand_registry = {}
        try:
            brand_registry = save_brand_in_batch(results)
            log.info("ktoa_mvno_brand_in 저장 완료")
        except Exception as e:
            log.error(f"Firestore 저장 실패: {e}")

        try:
            build_brand_out(ym)
            log.info("ktoa_mvno_brand_out 생성 완료")
        except Exception as e:
            log.error(f"brand_out 생성 실패: {e}")

        try:
            build_carrier_summary(ym, brand_registry)
            log.info("ktoa_carrier_summary 생성 완료")
        except Exception as e:
            log.error(f"carrier_summary 생성 실패: {e}")

    # ── 텔레그램 요약 알림 ───────────────────────────────────
    # [테스트 단계] 공용 채팅방으로 전송되므로 임시 비활성화
    SEND_TELEGRAM = False
    if not SEND_TELEGRAM:
        log.info("[TEST] 텔레그램 알림 비활성화 상태 (전송 안 함)")
        return

    try:
        fail_names = ", ".join(f["name"] for f in failed[:10])
        msg = (
            f"📊 KTOA MVNO 상세 수집 완료 ({now_kst.strftime('%Y-%m-%d %H:%M')})\n"
            f"성공: {len(results)}건 / 실패: {len(failed)}건\n"
        )
        if failed:
            msg += f"실패 목록: {fail_names}{'...' if len(failed) > 10 else ''}"
        tg_send(msg)
    except Exception as e:
        log.warning(f"텔레그램 알림 실패 (무시): {e}")


if __name__ == "__main__":
    # 테스트 실행 시: TEST_LIMIT=3 python ktoa_mvno_scraper.py
    limit = os.environ.get("TEST_LIMIT")
    run(test_limit=int(limit) if limit else None)