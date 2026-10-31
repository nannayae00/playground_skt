"""
[수정 이력]
- v1.10 (2026-10-29): 07:30 재수집 확인 메시지에 망별 실사업자 수(MNO 제외, IN>0)와
  망 통합 사업자 수(같은 회사 여러 망 = 1개) 추가 (사용자 요청).
- v1.9 (2026-10-29): 07:30 실행은 대상일이 00시대에 이미 발송됐으면 재수집 후 변경 여부만
  확인하고 "🔎 07:30 재수집 확인" 메시지 1건(run_morning_verify). 리포트 재발송 없음 (사용자 요청).
- v1.8 (2026-10-28): 실행 시점을 07:20 → 00:31 신규일자 확인 직후로 변경(사용자 요청).
  check_new_data.py가 신규일자를 확인하면 이 job을 바로 실행 → 사업자별 실적 → 선불 실적 →
  "✅ 최신일자 업데이트" 메시지. 대상일별 완료 플래그(ktoa_daily_report_flags)로 07:20
  스케줄은 못 끝낸 부분만 보완(선불 데이터가 00시대에 아직 없을 때 등).
- v1.7 (2026-10-16): 매월 2일 아침(대상일=1일) 선불 전월 한 달 재수집 추가
  (_recollect_prev_month) - 7일보다 오래된 KTOA 정정값 반영.
- v1.6 (2026-10-16): 일일/주간 분기 뒤에 선불 리포트(run_prepaid) 추가 -
  KTOA 선불 등록현황 최근 7일 재수집 → ktoa_prepaid_summary → 선불 010/MNP
  사업자별 실적·망별 M/S 4종을 같은 방으로 발송. 실패해도 job 결과에 영향 없음.
- v1.5 (2026-08-07): RUN_INSIGHTS_PIPELINE 환경변수 지원 추가 - 있으면
  월간/주간 요약 재집계(2016~2026 전체) → build_brand_insights.py →
  import_brand_profiles.py → build_brand_insights_v2.py를 순서대로 실행하고
  단계별 성공/실패를 텔레그램으로 요약 발송. Cloud Run Job으로 실행하면
  Cloud Shell/노트북 꺼도 GCP 서버에서 계속 진행됨(BACKFILL_YEAR 모드와
  동일 이유 - 사용자가 "지난번처럼 콘솔 꺼도 돌아가게" 요청). 한 단계가
  실패해도 나머지 단계는 계속 진행(부분 실패 허용).
- v1.4 (2026-08-07): BACKFILL_YEAR 환경변수 지원 추가 - 있으면(단일연도
  "2022" 또는 범위 "2016-2022") 평소 로직(스크래핑+리포트) 대신
  ktoa_mvno_scraper.backfill_year()를 연도별로 순차 실행하고 종료. Cloud
  Shell에 계속 붙어있지 않아도 Cloud Run Job 실행(gcloud run jobs execute
  --update-env-vars)만으로 과거 연도들을 백그라운드에서 순차 처리하기
  위함(사용자 요청 - 노트북 닫아도 안 끊기게). 실행 시간이 길어서(연도당
  1.5~2시간) task-timeout을 기본값(10분)보다 늘려야 함 - 코드 내 주석 참고.
- v1.0 (2026-07-29): 최초 작성. ktoa_mvno_scraper 실행 -> 성공 시에만
  ktoa_mvno_report 실행(텔레그램 3종 발송)하는 Cloud Run Job 진입점.
- v1.1 (2026-07-29): ktoa_mvno_scraper.py 실제 인터페이스 확인 후 재작성.
  scraper는 CLI 인자를 받지 않고(run(test_limit=None) 형태), 날짜 지정 없이
  실행 시점 기준 "당월(YYYY-MM) 전체"를 매번 새로 수집해 Firestore에
  덮어쓰는 구조(KTOA 사이트 자체가 사업자별로 당월 전체 일자를 한 번에
  보여주는 화면이라 부분 조회가 불가능 - 사용자 확인). 이에 맞춰 scraper는
  서브프로세스 CLI 호출이 아닌 run() 함수 직접 import 호출로 변경.
  report(ktoa_mvno_report.py)는 날짜 인자가 필요하므로 대상일(어제, KST
  기준)을 계산해 그대로 전달.
- v1.3 (2026-08-03): ktoa_mvno_period_report.py v1.1(메시지2 특이사항 추가)
  반영. build_weekly_report()/build_monthly_report()가 특이점 판정을 위해
  과거 요약 기간을 Firestore에서 직접 조회해야 해서 db 인자가 추가됨 -
  호출부(run_weekly_summary/run_monthly_summary)에 db 전달만 반영, 로직
  변경 없음.
- v1.2 (2026-08-03): 주간/월간 요약 트리거 로직 추가 (설계문서
  주간월간_리포트_설계_20260803.md 1번 그대로 구현).
  (1) 대상일(어제)이 일요일이거나 실적 합계 0이면 일일 리포트 3종 대신
      지난주(월~토) 주간요약을 발송 - 실질적으로 월요일에만 참이 됨.
      일요일이 아닌데 실적 0인 경우(공휴일 등)도 안전하게 커버하기 위해
      일요일 여부와 별개로 실제 실적 합계도 조회해서 판단.
  (2) 대상일이 월마감(mvno_period_utils.is_month_end)이면, 일일/주간 리포트와
      별개로 월간요약도 추가 발송 - 매월 1일에는 일일 리포트 + 월마감 리포트가
      함께(총 6개) 나가는 것이 의도된 동작으로 확정된 사항(억제 로직 불필요).
  (3) 실적 합계 조회나 월마감 판단 중 예외가 나도 기존 일일/주간 리포트
      흐름 자체는 막지 않고 로그만 남김(월마감 체크는 부가 기능이므로).

MVNO 사업자별 리포트 Job 진입점 (Cloud Run Job).
실행 순서: ① ktoa_mvno_scraper.run() (KTOA 사이트 -> 당월 전체 재수집 ->
              Firestore 덮어쓰기, 수집 완료 요약은 scraper 내부에서 개인방
              텔레그램으로 별도 발송)
          ② 트리거 판단 후 다음 중 하나:
             - 대상일이 일요일 또는 실적0 -> 지난주 주간요약 발송
             - 그 외 -> 기존 일일 리포트 3종 발송
          ③ 대상일이 월마감이면 위와 별개로 월간요약도 추가 발송
scraper 실행 중 예외 발생 시 ②/③ 모두 건너뛴다 - 불완전한 데이터로
리포트가 발송되는 것을 방지하기 위함.
"""

import sys
import os
import subprocess
from calendar import monthrange
from datetime import date, timedelta, timezone, datetime

KST = timezone(timedelta(hours=9))
PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"


def get_yesterday_kst() -> str:
    """KST 기준 오늘에서 하루를 뺀 날짜(어제)를 YYYY-MM-DD로 반환. report 스크립트 인자용."""
    now_kst = datetime.now(KST)
    yesterday = now_kst.date() - timedelta(days=1)
    return yesterday.isoformat()


def run_scraper() -> bool:
    """
    ktoa_mvno_scraper.run()을 직접 호출(CLI 인자 없음 - 날짜 지정 불가,
    당월 전체를 매번 재수집하는 스크립트 자체 동작 방식).
    반환값 True=성공, False=예외 발생(실패).
    """
    print("[1/2] 수집 시작: ktoa_mvno_scraper.run() (당월 전체 재수집)", flush=True)
    try:
        import ktoa_mvno_scraper
        ktoa_mvno_scraper.run()
    except Exception as e:
        print(f"[1/2] 수집 실패 (예외 발생): {e}", flush=True)
        return False
    print("[1/2] 수집 완료", flush=True)
    return True


def run_report(target_date: str) -> bool:
    """ktoa_mvno_report.py 실행(텔레그램 3종 발송 포함). 반환값 True=성공, False=실패."""
    print(f"[2/2] 일일 리포트 발송 시작: ktoa_mvno_report.py {target_date} --telegram", flush=True)
    result = subprocess.run(
        [sys.executable, "ktoa_mvno_report.py", target_date, "--telegram"],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"[2/2] 일일 리포트 발송 실패 (exit code {result.returncode})", flush=True)
        return False
    print("[2/2] 일일 리포트 발송 완료", flush=True)
    return True


def get_total_in_performance(target_date_obj: date) -> int:
    """
    대상일의 ktoa_mvno_brand_in 전체 total_in 합계. 트리거 판단(실적0 여부)용.
    일요일이 아니더라도(예: 데이터 미반영 등 예외 상황) 안전하게 0 여부를 판단하기 위함.
    """
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    date_str = target_date_obj.isoformat()
    docs = db.collection("ktoa_mvno_brand_in").where("date", "==", date_str).stream()
    return sum((d.to_dict().get("total_in") or 0) for d in docs)


def run_weekly_summary(target_date_obj: date) -> bool:
    """
    target_date_obj(=어제, 주간요약 트리거 판단에 쓰인 날짜) 기준 "이번 주"(월~토,
    어제가 일요일이면 방금 끝난 지난주) 요약을 집계+저장+발송.

    [버그수정, Claude] 기존엔 today_kst(=실행일)를 받아 last_week_range()로
    "오늘 기준 지난주"를 구했는데, 이 함수는 "실행일=월요일"만 가정하고 있어서
    실적0 폴백 트리거(공휴일 등, 실행일이 월요일이 아닐 수 있음)에서 엉뚱하게
    2주 전 리포트가 나가는 문제가 있었음. target_date_obj를
    current_business_week_range()에 넘기면 두 트리거 케이스 모두 올바른 주를
    반환함(mvno_period_utils.py 주석 참고).
    """
    from mvno_period_utils import current_business_week_range, week_of_month
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period, save_weekly_summary
    from ktoa_mvno_period_report import build_weekly_report, send_telegram_report

    print("[분기] 주간요약 시작", flush=True)
    try:
        last_mon, last_sat = current_business_week_range(target_date_obj)
        year, month, week, _, _ = week_of_month(last_mon)

        db = _get_db()
        agg = aggregate_period(db, last_mon, last_sat)
        save_weekly_summary(db, agg, year, month, week, last_mon, last_sat)

        messages = build_weekly_report(db, agg, year, month, week, last_mon, last_sat)
        send_telegram_report(messages)
        print(f"[분기] 주간요약 완료: {year}-{month:02d}W{week} ({last_mon}~{last_sat})", flush=True)
        return True
    except Exception as e:
        print(f"[분기] 주간요약 실패: {e}", flush=True)
        return False


def run_monthly_summary(target_date_obj: date) -> bool:
    """target_date_obj(=어제=지난달 마지막날)가 속한 달의 요약을 집계+저장+발송."""
    from ktoa_mvno_period_aggregator import _get_db, aggregate_period, save_monthly_summary
    from ktoa_mvno_period_report import build_monthly_report, send_telegram_report

    print("[월마감] 월간요약 시작", flush=True)
    try:
        year, month = target_date_obj.year, target_date_obj.month
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])

        db = _get_db()
        agg = aggregate_period(db, period_start, period_end)
        save_monthly_summary(db, agg, year, month, period_start, period_end)

        messages = build_monthly_report(db, agg, year, month, period_start, period_end)
        send_telegram_report(messages)
        print(f"[월마감] 월간요약 완료: {year}-{month:02d}", flush=True)
        return True
    except Exception as e:
        print(f"[월마감] 월간요약 실패: {e}", flush=True)
        return False


def _run_backfill_years(spec: str) -> None:
    """
    BACKFILL_YEAR="2022" (단일) 또는 "2016-2022"(범위, 내림차순/오름차순 무관)를
    받아서 ktoa_mvno_scraper.backfill_year()를 연도별로 순차 호출.
    각 연도가 끝날 때마다 텔레그램 완료 알림이 오므로 진행상황 확인 가능
    (backfill_year 자체가 이미 그렇게 되어 있음).
    """
    from ktoa_mvno_scraper import backfill_year

    if "-" in spec:
        start_s, end_s = spec.split("-", 1)
        start, end = int(start_s), int(end_s)
    else:
        start = end = int(spec)

    years = range(start, end - 1, -1) if start >= end else range(start, end + 1)

    for year in years:
        print(f"=== BACKFILL_YEAR 모드: {year}년 시작 ===", flush=True)
        try:
            backfill_year(year)
        except Exception as e:
            print(f"{year}년 백필 중 예외 발생(다음 연도로 계속 진행): {e}", flush=True)
        print(f"=== BACKFILL_YEAR 모드: {year}년 종료 ===", flush=True)


def _run_insights_pipeline() -> None:
    """
    RUN_INSIGHTS_PIPELINE=1 이면 실행되는 모드. 아래 4단계를 순서대로 실행:
      1) 월간/주간 요약 재집계(2016-01~2026-07 전체 범위)
      2) build_brand_insights.py: 특이사항 DB 기본 골격
      3) import_brand_profiles.py: 조사한 회사정보(brand_profiles_merged.json) 병합
      4) build_brand_insights_v2.py: 역대기록/YoY/변동성/계절성/망이동/유입유출top5
    각 단계 실패해도 다음 단계로 계속 진행(부분 실패해도 나머지는 살리기 위함).
    끝나면 텔레그램으로 단계별 성공/실패 요약 발송.
    ⚠️ brand_profiles_merged.json이 이 폴더(브랜드-report/)에 같이 있어야
    3단계가 동작함 - 배포 시 같이 포함되도록 확인할 것.
    """
    from ktoa_mvno_period_aggregator import _get_db, backfill_monthly, backfill_weekly

    now_kst = datetime.now(KST)
    log_lines = []

    def step(name, fn):
        print(f"=== {name} 시작 ===", flush=True)
        try:
            result = fn()
            msg = f"✅ {name} 완료" + (f" ({result})" if result is not None else "")
            print(msg, flush=True)
            log_lines.append(msg)
        except Exception as e:
            msg = f"❌ {name} 실패: {e}"
            print(msg, flush=True)
            log_lines.append(msg)

    db = _get_db()

    step("1. 월간요약 재집계(2016-01~2026-07)", lambda: backfill_monthly(2016, 1, 2026, 7))
    step("2. 주간요약 재집계(2016-01-01~2026-07-31)",
         lambda: backfill_weekly(date(2016, 1, 1), date(2026, 7, 31)))

    def _step_insights_v1():
        from build_brand_insights import build as build_v1
        return build_v1(db)
    step("3. 특이사항 DB 기본 골격", _step_insights_v1)

    def _step_import_profiles():
        import os as _os
        json_path = "brand_profiles_merged.json"
        if not _os.path.exists(json_path):
            raise FileNotFoundError(f"{json_path}가 없음 - 배포 시 이 파일이 같이 포함됐는지 확인 필요")
        from import_brand_profiles import run as import_run
        import_run(json_path)
        return None
    step("4. 조사한 회사정보 병합", _step_import_profiles)

    def _step_insights_v2():
        from build_brand_insights_v2 import build as build_v2
        return build_v2(db)
    step("5. 종합분석(역대기록/YoY/변동성/유입유출top5)", _step_insights_v2)

    try:
        from ktoa_mvno_scraper import tg_send_personal
        summary = f"📊 인사이트 파이프라인 완료 ({now_kst.strftime('%Y-%m-%d %H:%M')})\n\n" + "\n".join(log_lines)
        tg_send_personal(summary)
    except Exception as e:
        print(f"텔레그램 알림 실패(무시): {e}", flush=True)

    print("=== 인사이트 파이프라인 전체 종료 ===", flush=True)


def _recollect_prev_month(target_date_obj: date) -> None:
    """
    매월 초(대상일이 1일인 실행 = 매월 2일 아침) 전월 한 달을 다시 받아 덮어씀 (v1.7).
    일일 수집은 최근 7일만 다시 받으므로, KTOA가 그보다 오래된 날짜를 나중에 고친 값
    (팀 엑셀 대조에서 확인: 와이드모바일KT 등 1~24건)을 월 단위로 반영하기 위함.
    실패해도 일일 리포트는 계속 진행.
    """
    if target_date_obj.day != 1:
        return
    prev_ym = (target_date_obj - timedelta(days=1)).strftime("%Y-%m")
    try:
        from ktoa_prepaid_scraper import run_backfill
        ok, ng = run_backfill(prev_ym, prev_ym, dry_run=False, notify=False)
        print(f"[선불] 전월({prev_ym}) 재수집 {'완료' if ok else '실패'}", flush=True)
    except Exception as e:
        print(f"[선불] 전월({prev_ym}) 재수집 실패 (무시하고 계속): {e}", flush=True)


def run_prepaid(target_date_obj: date) -> bool:
    """
    KTOA 선불 등록현황 최근 7일 재수집(ktoa_prepaid_daily + summary) 후
    선불 리포트 6종(일 실적·M/S·월누적 × 010/MNP)을 같은 방으로 발송 (v1.6). 대상일 데이터가 아직 없으면
    발송하지 않음. 예외는 로그만 남기고 삼킴 - 부가 리포트라 MNP 리포트 흐름을 막지 않음.
    """
    print("[선불] 수집 시작: ktoa_prepaid_scraper.run_daily(7)", flush=True)
    try:
        from ktoa_prepaid_scraper import run_daily
        from ktoa_prepaid_report import build_prepaid_reports, save_context
        from ktoa_mvno_report import send_telegram
        from ktoa_mvno_firestore import _get_db

        latest = run_daily(7, dry_run=False, notify=False)
        _recollect_prev_month(target_date_obj)
        if latest < target_date_obj.isoformat():
            print(f"[선불] 대상일({target_date_obj}) 데이터 미반영 (최신 {latest}) - 리포트 생략", flush=True)
            return False
        db = _get_db()
        msgs = build_prepaid_reports(target_date_obj, db)
        if not msgs:
            return False
        send_telegram(msgs)
        save_context(db, target_date_obj, msgs)
        print(f"[선불] 리포트 {len(msgs)}건 발송 완료", flush=True)
        return True
    except Exception as e:
        print(f"[선불] 실패 (무시하고 계속): {e}", flush=True)
        return False


def main():
    # ── 인사이트 파이프라인 모드: RUN_INSIGHTS_PIPELINE=1 이면 이것만 실행하고 종료 ──
    # 실행 시간이 김(원본 10년치 훑는 단계 포함) - task-timeout 넉넉히:
    #   gcloud run jobs update mvno-brand-report-job --region asia-northeast3 \
    #     --project mvno-484509 --task-timeout=86400
    #   gcloud run jobs execute mvno-brand-report-job --region asia-northeast3 \
    #     --project mvno-484509 --update-env-vars="^@^RUN_INSIGHTS_PIPELINE=1"
    if os.environ.get("RUN_INSIGHTS_PIPELINE"):
        _run_insights_pipeline()
        return

    # ── 백필 모드: BACKFILL_YEAR 있으면 평소 로직(스크래핑+리포트) 대신 이것만 실행 ──
    # 값 예시: "2022" (한 해) 또는 "2016-2022"(범위, 순서 무관 - 내림차순으로 줘도 됨).
    # Cloud Run Job으로 실행할 때는 실행 시간이 김(연도당 1.5~2시간) - 아래 명령으로
    # task-timeout을 미리 넉넉히 늘려두고 실행할 것(기본 10분이라 그냥 두면 중간에 끊김):
    #   gcloud run jobs update mvno-brand-report-job --region asia-northeast3 \
    #     --project mvno-484509 --task-timeout=86400
    backfill_year_env = os.environ.get("BACKFILL_YEAR")
    if backfill_year_env:
        _run_backfill_years(backfill_year_env)
        return

    print("=== MVNO 사업자별 리포트 Job 시작 ===", flush=True)

    target_date = get_yesterday_kst()
    target_date_obj = date.fromisoformat(target_date)

    # ── v1.8: 00:31 신규일자 확인 직후(check_new_data.py가 이 job을 실행) 돌고, 07:20 스케줄은
    #    보완용. 대상일별로 "사업자별 실적"/"선불 실적" 완료 플래그를 두고 이미 끝난 부분은 건너뜀 ──
    flags = _get_report_flags(target_date)
    if flags.get("brand_done") and flags.get("prepaid_done"):
        # v1.9: 00시대에 이미 발송 완료 → 07:30에는 다시 수집해서 값이 바뀌었는지만 확인하고 알림
        run_morning_verify(target_date, target_date_obj)
        return

    brand_status = "완료(이전 실행)" if flags.get("brand_done") else None
    if brand_status is None:
        if not run_scraper():
            from ktoa_mvno_scraper import tg_send_personal
            tg_send_personal(f"⚠️ 사업자별 실적 수집 실패 ({target_date}) - 07:30 재시도")
            sys.exit(1)  # Cloud Run Job이 실패로 기록되도록 non-zero exit
        run_brand_reports(target_date, target_date_obj)
        _set_report_flag(target_date, "brand_done")
        brand_status = "완료"

    if flags.get("prepaid_done"):
        prepaid_status = "완료(이전 실행)"
    elif run_prepaid(target_date_obj):
        _set_report_flag(target_date, "prepaid_done")
        prepaid_status = "완료"
    else:
        retry = datetime.now(KST).hour < 7
        prepaid_status = "미반영" + (" (07:30 재시도)" if retry else "")

    from ktoa_mvno_scraper import tg_send_personal
    tg_send_personal(f"✅ 최신일자 업데이트 ({target_date})\n"
                     f"· 사업자별 MNP 실적 : {brand_status}\n"
                     f"· 선불 실적 : {prepaid_status}")
    print("=== 전체 완료 ===", flush=True)


def run_brand_reports(target_date: str, target_date_obj: date) -> None:
    """사업자별 MNP 리포트: 일일(또는 주간요약) + 월마감. 실패 시 exit(1)."""
    # ── 트리거 판단: 어제가 일요일이거나 실적 합계 0이면 주간요약, 아니면 일일 리포트 ──
    is_sunday = target_date_obj.weekday() == 6
    total_perf = None
    if not is_sunday:
        try:
            total_perf = get_total_in_performance(target_date_obj)
        except Exception as e:
            print(f"실적 합계 조회 실패 (일일 리포트로 진행): {e}", flush=True)

    if is_sunday or total_perf == 0:
        print(f"[분기판단] 대상일({target_date}) 일요일={is_sunday}, 실적합계={total_perf} → 주간요약", flush=True)
        if not run_weekly_summary(target_date_obj):
            sys.exit(1)
    else:
        if not run_report(target_date):
            sys.exit(1)

    # ── 월마감 판단: 위 분기와 별개로 항상 체크. 매월 1일엔 의도적으로 겹쳐서 발송 ──
    try:
        from mvno_period_utils import is_month_end
        if is_month_end(target_date_obj):
            run_monthly_summary(target_date_obj)
    except Exception as e:
        print(f"월마감 판단/처리 실패 (무시하고 계속): {e}", flush=True)


def _snapshot(target_date: str) -> dict:
    """대상일 값 스냅샷: 사업자별 MNP(IN/OUT)와 선불(망 합계·사업자×망의 신규/해지/IN/OUT)."""
    from google.cloud import firestore
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    mnp, prepaid, mnp_net = {}, {}, {}
    for coll, field, idx in (("ktoa_mvno_brand_in", "total_in", 0), ("ktoa_mvno_brand_out", "total_out", 1)):
        for d in db.collection(coll).where("date", "==", target_date).stream():
            x = d.to_dict()
            v = mnp.setdefault(f"{x.get('brand')}", [0, 0])
            v[idx] = x.get(field) or 0
            if x.get("network"):
                mnp_net[x.get("brand")] = x["network"]
    doc = db.collection("ktoa_prepaid_summary").document(target_date).get()
    if doc.exists:
        s = doc.to_dict()
        keys = ("reg", "term", "pin", "pout")
        for n, m in s.get("networks", {}).items():
            prepaid[n] = [m.get(k, 0) for k in keys]
        for b in s.get("brands", {}).values():
            for n in ("S", "K", "L"):
                if n in b:
                    prepaid[f"{b['short']}({n})"] = [b[n].get(k, 0) for k in keys]
    return {"mnp": {k: tuple(v) for k, v in mnp.items()}, "prepaid": {k: tuple(v) for k, v in prepaid.items()},
            "mnp_net": mnp_net}


def _active_operator_line(snap: dict) -> str:
    """MNO(SKT/KT/LGU+) 제외, 당일 IN>0인 알뜰폰 사업자 수를 망별로 (v1.10)."""
    from ktoa_mvno_report import is_mno_brand, clean_brand_name
    from ktoa_prepaid_summary import ALIASES
    cnt = {"SKT": 0, "KT": 0, "LGU": 0}
    merged = set()   # 망 통합: 망 표시를 뗀 이름 기준 (프리텔레콤SKT/KT + 프리티LG = 1개)
    for brand, (tin, _) in snap["mnp"].items():
        net = snap["mnp_net"].get(brand)
        if tin > 0 and net in cnt and not is_mno_brand(brand):
            cnt[net] += 1
            name, prev = brand, None
            while name != prev:
                prev, name = name, clean_brand_name(name)
            merged.add(ALIASES.get(name, name))
    return (f"  실사업자 SM {cnt['SKT']}개, KM {cnt['KT']}개, LM {cnt['LGU']}개 (IN>0)\n"
            f"  실사업자(망 통합) : {len(merged)}개")


def _diff_lines(before: dict, after: dict, cols: tuple, limit: int = 10) -> list[str]:
    diffs = []
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k, (0,) * len(cols)), after.get(k, (0,) * len(cols))
        if b != a:
            parts = [f"{c} {x:,}→{y:,}" for c, x, y in zip(cols, b, a) if x != y]
            diffs.append(f"  - {k} : " + ", ".join(parts))
    return diffs[:limit] + ([f"  - 외 {len(diffs) - limit}건"] if len(diffs) > limit else []), len(diffs)


def run_morning_verify(target_date: str, target_date_obj: date) -> None:
    """
    07:30 재확인 (v1.9, 사용자 요청): 00시대에 발송한 대상일 데이터를 다시 수집해서
    값이 바뀌었는지만 확인하고 결과 메시지 1건. 리포트는 다시 보내지 않음.
    """
    from ktoa_mvno_scraper import tg_send_personal
    print(f"[재확인] 대상일({target_date}) 00시대 발송 완료 → 재수집 후 변경 여부 확인", flush=True)
    before = _snapshot(target_date)

    lines = [f"🔎 07:30 재수집 확인 ({target_date})"]
    if run_scraper():
        after = _snapshot(target_date)
        d, n = _diff_lines(before["mnp"], after["mnp"], ("IN", "OUT"))
        lines.append(f"· 사업자별 MNP : {'이상 없음' if not n else f'변경 {n}건'} (사업자 {len(after['mnp'])}개)")
        lines.append(_active_operator_line(after))
        lines += d
    else:
        lines.append("· 사업자별 MNP : ⚠️ 재수집 실패 (00시 값 유지)")

    try:
        from ktoa_prepaid_scraper import run_daily
        run_daily(7, dry_run=False, notify=False)
        after_pp = _snapshot(target_date)["prepaid"]
        d, n = _diff_lines(before["prepaid"], after_pp, ("신규", "해지", "IN", "OUT"))
        lines.append(f"· 선불 : {'이상 없음' if not n else f'변경 {n}건'}")
        lines += d
    except Exception as e:
        lines.append(f"· 선불 : ⚠️ 재수집 실패 ({e})")

    if any(l.startswith("· ") and "변경" in l for l in lines):
        lines.append("(DB는 재수집 값으로 갱신됨, 리포트는 재발송 안 함)")
    tg_send_personal("\n".join(lines))
    print("\n".join(lines), flush=True)


REPORT_FLAG_COLLECTION = "ktoa_daily_report_flags"   # {대상일}: {brand_done, prepaid_done}


def _get_report_flags(target_date: str) -> dict:
    try:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
        doc = db.collection(REPORT_FLAG_COLLECTION).document(target_date).get()
        return doc.to_dict() or {}
    except Exception as e:
        print(f"완료 플래그 조회 실패 (처음부터 진행): {e}", flush=True)
        return {}


def _set_report_flag(target_date: str, key: str) -> None:
    try:
        from google.cloud import firestore
        db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
        db.collection(REPORT_FLAG_COLLECTION).document(target_date).set(
            {key: True, f"{key}_at": datetime.now(KST).isoformat()}, merge=True)
    except Exception as e:
        print(f"완료 플래그 저장 실패 ({key}): {e}", flush=True)


if __name__ == "__main__":
    main()