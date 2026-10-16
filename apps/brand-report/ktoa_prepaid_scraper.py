"""
ktoa_prepaid_scraper.py  v1.0
작성일: 2026-10-16

[수정 이력]
v1.0 | 2026-10-16 | 최초 작성
  - KTOA 번호현황 조회 > 선불 등록현황 > 일별 표를 엑셀로 내려받아
    ktoa_prepaid_daily/{YYYY-MM-DD}에 적재 (사업자 블록 137개 × 지표 13개)
  - 로그인/드라이버는 ktoa_mvno_scraper.py 것을 그대로 씀 (비밀번호 후보 순차 시도 포함)
  - 데일리: 최근 LOOKBACK_DAYS(기본 7)일을 다시 받아 덮어씀 → KTOA의 과거일 정정도 반영
  - 백필: BACKFILL_FROM / BACKFILL_TO (YYYY-MM) 월 단위로 받아 월마다 즉시 저장

⚠️ 사이트 화면을 직접 확인하지 못하고 작성함. MNP 등록현황 화면과 같은 구성이라고
   가정한 부분(아래)은 첫 실행을 DEBUG=1로 돌려 로그·HTML을 보고 확정할 것.
   - 메뉴: onclick에 '선불 등록현황'이 들어간 요소를 찾아 그 onclick을 그대로 실행
   - 일별 라디오: div.radioText 중 텍스트가 '일별'인 것
   - 조회일자 입력칸: #startDtVal / #endDtVal (YYYY-MM-DD)
   - 조회 버튼: 아래 SEARCH_XPATHS 후보 중 처음 찾은 것, 엑셀: #excelBt
   받은 엑셀의 날짜 범위가 요청 범위와 다르면 저장하지 않고 실패 처리함
   (조회일자가 반영되지 않은 채 엑셀이 받아지는 경우를 막기 위함).

사용법:
    python3 ktoa_prepaid_scraper.py                         # 데일리 (최근 7일)
    LOOKBACK_DAYS=31 python3 ktoa_prepaid_scraper.py        # 최근 31일
    BACKFILL_FROM=2017-01 BACKFILL_TO=2025-12 python3 ktoa_prepaid_scraper.py
    DRY_RUN=1 python3 ktoa_prepaid_scraper.py               # Firestore/텔레그램 없이 JSON만
    DEBUG=1 ...                                             # 단계별 스크린샷·HTML 저장
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timedelta, date

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ktoa_mvno_scraper import (
    get_driver, login, tg_send_personal, _debug_screenshot, DOWNLOAD_DIR, KST,
)
from ktoa_prepaid_parser import parse_prepaid_file, check_consistency

log = logging.getLogger(__name__)

MENU_LABEL = "선불 등록현황"
DRY_RUN_DIR = "/tmp/ktoa_prepaid_out"
SEARCH_XPATHS = [
    "//*[@id='searchBt']", "//*[@id='searchBtn']", "//*[@id='btnSearch']",
    "//img[@alt='조회']", "//input[@type='image' and @alt='조회']",
    "//a[normalize-space()='조회']", "//button[normalize-space()='조회']",
]


# ─────────────────────────────────────────────────────────────
# 화면 조작
# ─────────────────────────────────────────────────────────────
def navigate_to_prepaid_view(driver) -> str | None:
    """번호현황 조회 > 선불 등록현황 > 일별 화면으로 이동. 메뉴의 type 값을 반환."""
    wait = WebDriverWait(driver, 15)
    wait.until(lambda d: d.execute_script("return typeof pageBeforeDay === 'function';"))

    onclick = os.environ.get("PREPAID_MENU_JS") or driver.execute_script(
        "const el = [...document.querySelectorAll('[onclick]')]"
        "  .find(e => e.getAttribute('onclick').includes(arguments[0]));"
        "return el ? el.getAttribute('onclick') : null;",
        MENU_LABEL,
    )
    if not onclick:
        _debug_screenshot(driver, "prepaid_menu_not_found")
        raise RuntimeError(f"'{MENU_LABEL}' 메뉴를 찾지 못함 - DEBUG=1로 HTML 확인 후 PREPAID_MENU_JS 지정")
    log.info(f"메뉴 이동: {onclick}")
    driver.execute_script(onclick)
    time.sleep(1.5)
    _debug_screenshot(driver, "prepaid_10_after_menu")

    m = re.search(r"type=(\w+)", onclick)
    menu_type = m.group(1) if m else None

    daily = (By.XPATH, "//div[contains(@class,'radioText') and "
                       "contains(translate(normalize-space(.),' ',''),'일별')]")
    wait.until(EC.presence_of_element_located(daily))
    driver.find_element(*daily).click()
    time.sleep(1)
    _debug_screenshot(driver, "prepaid_11_after_daily_radio")

    wait.until(EC.presence_of_element_located((By.ID, "excelBt")))
    log.info(f"{MENU_LABEL}(일별) 화면 진입 완료 (type={menu_type})")
    return menu_type


def set_query_range(driver, start: str, end: str) -> None:
    driver.execute_script(
        "document.getElementById('startDtVal').value = arguments[0];"
        "document.getElementById('endDtVal').value = arguments[1];",
        start, end,
    )
    for xp in SEARCH_XPATHS:
        els = driver.find_elements(By.XPATH, xp)
        if els:
            driver.execute_script("arguments[0].click();", els[0])
            log.info(f"조회일자 {start} ~ {end} 조회 ({xp})")
            time.sleep(2)
            _debug_screenshot(driver, f"prepaid_20_after_search_{start}")
            return
    log.warning(f"조회 버튼을 찾지 못함 - 입력값만 바꾸고 엑셀 다운로드 ({start} ~ {end})")


def download_excel(driver, menu_type: str | None, tag: str) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    before = set(os.listdir(DOWNLOAD_DIR))
    btn = driver.find_elements(By.ID, "excelBt")
    if btn:
        driver.execute_script("arguments[0].click();", btn[0])
    elif menu_type:
        driver.execute_script(f"excelDownLoad('{menu_type}');")
    else:
        raise RuntimeError("엑셀 버튼(#excelBt)도 메뉴 type도 없음")

    for _ in range(60):
        time.sleep(1)
        new = [f for f in set(os.listdir(DOWNLOAD_DIR)) - before
               if f.endswith((".xls", ".xlsx")) and not f.endswith(".crdownload")]
        if new:
            log.info(f"[{tag}] 다운로드 완료: {new[0]}")
            return os.path.join(DOWNLOAD_DIR, new[0])
    _debug_screenshot(driver, f"prepaid_fail_download_{tag}")
    raise TimeoutError(f"[{tag}] 엑셀 다운로드 시간 초과 (60초)")


# ─────────────────────────────────────────────────────────────
# 수집 단위
# ─────────────────────────────────────────────────────────────
class Session:
    """드라이버 하나로 여러 구간을 받는다. 실패하면 드라이버를 새로 만들어 한 번 더 시도."""

    def __init__(self):
        self.driver = None
        self.menu_type = None

    def _open(self):
        self.close()
        self.driver = get_driver()
        login(self.driver)
        self.menu_type = navigate_to_prepaid_view(self.driver)

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None

    def fetch(self, start: str, end: str) -> dict:
        for attempt in (1, 2):
            try:
                if self.driver is None:
                    self._open()
                set_query_range(self.driver, start, end)
                path = download_excel(self.driver, self.menu_type, tag=f"{start}_{end}")
                parsed = parse_prepaid_file(path)
                _check_range(parsed, start, end)
                return parsed
            except Exception as e:
                log.error(f"[{start}~{end}] {attempt}차 실패: {e}")
                self.close()
                if attempt == 2:
                    raise


def _check_range(parsed: dict, start: str, end: str) -> None:
    days = sorted(parsed["days"])
    if not days:
        raise ValueError("엑셀에 일자 행이 없음")
    outside = [d for d in days if d < start or d > end]
    if outside:
        raise ValueError(f"요청 범위({start}~{end}) 밖 일자 포함: {outside[:3]} - 조회일자 미반영 의심")


def _store(parsed: dict, dry_run: bool) -> int:
    issues = check_consistency(parsed)
    if issues:
        log.warning(f"표 정합성 이상 {len(issues)}건 (저장은 진행): {issues[:5]}")
    if dry_run:
        os.makedirs(DRY_RUN_DIR, exist_ok=True)
        days = sorted(parsed["days"])
        path = os.path.join(DRY_RUN_DIR, f"prepaid_{days[0]}_{days[-1]}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False)
        log.info(f"[DRY_RUN] {path} 저장 ({len(days)}일)")
        return len(days)
    from ktoa_prepaid_firestore import save_prepaid_days
    return save_prepaid_days(parsed)


def _month_ranges(from_ym: str, to_ym: str, cap: date) -> list[tuple[str, str]]:
    y, m = map(int, from_ym.split("-"))
    ty, tm = map(int, to_ym.split("-"))
    out = []
    while (y, m) <= (ty, tm):
        first = date(y, m, 1)
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        last = min(last, cap)
        if first <= cap:
            out.append((first.isoformat(), last.isoformat()))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────
def run_daily(lookback_days: int, dry_run: bool) -> None:
    now = datetime.now(KST)
    end = (now.date() - timedelta(days=1))
    start = end - timedelta(days=lookback_days - 1)
    s = Session()
    try:
        parsed = s.fetch(start.isoformat(), end.isoformat())
        n = _store(parsed, dry_run)
    except Exception as e:
        if not dry_run:
            tg_send_personal(f"⚠️ KTOA 선불 등록현황 수집 실패 ({now:%Y-%m-%d %H:%M})\n{e}")
        raise
    finally:
        s.close()

    latest = max(parsed["days"])
    t = parsed["days"][latest].get("TOTAL", {})
    msg = (f"📱 KTOA 선불 등록현황 수집 완료 ({now:%Y-%m-%d %H:%M})\n"
           f"구간 {start} ~ {end}, {n}일 저장 / 최신 {latest}\n"
           f"{latest} 총계 순증 {t.get('subtotal', 0):,} "
           f"(신규 {t.get('new_net', 0):,} / 이동 {t.get('port_net', 0):,} / "
           f"전환 {t.get('conv_net', 0):,} / 예비 {t.get('spare_net', 0):,})")
    log.info(msg)
    if not dry_run:
        tg_send_personal(msg)


def run_backfill(from_ym: str, to_ym: str, dry_run: bool) -> None:
    now = datetime.now(KST)
    ranges = _month_ranges(from_ym, to_ym, cap=now.date() - timedelta(days=1))
    log.info(f"=== 선불 등록현황 백필 {from_ym} ~ {to_ym} ({len(ranges)}개월) ===")
    s = Session()
    lines, ok, ng = [], 0, 0
    try:
        for start, end in ranges:
            try:
                n = _store(s.fetch(start, end), dry_run)
                lines.append(f"{start[:7]}: {n}일")
                ok += 1
            except Exception as e:
                lines.append(f"{start[:7]}: 실패({e})")
                ng += 1
    finally:
        s.close()
    msg = (f"📱 KTOA 선불 등록현황 백필 {from_ym}~{to_ym} 완료: 성공 {ok} / 실패 {ng}\n"
           + "\n".join(lines))
    log.info(msg)
    if not dry_run:
        tg_send_personal(msg[:3900])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    dry = os.environ.get("DRY_RUN") == "1"
    bf_from, bf_to = os.environ.get("BACKFILL_FROM"), os.environ.get("BACKFILL_TO")
    if bf_from:
        run_backfill(bf_from, bf_to or datetime.now(KST).strftime("%Y-%m"), dry)
    else:
        run_daily(int(os.environ.get("LOOKBACK_DAYS", "7")), dry)
