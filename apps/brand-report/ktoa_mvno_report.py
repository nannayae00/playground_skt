"""
[수정 이력]
- v3.20 (2026-08-27): Context DB 연동(사용자 확정, 최종 설계 - 사업자별
  구조화 저장 대신 기존 ktoa_context 패턴으로 단순화: 문서 1개=날짜 1개,
  text 필드에 메시지1~4 원문을 구분선으로 이어붙여 그대로 저장. 파싱/구조화는
  컨슈머 프로그램 책임). save_daily_context() 신규 추가, build_all_reports()
  에서 4개 메시지 생성 직후 호출해서 ktoa_brand_context_daily에 저장.
- v3.19 (2026-08-26): 자회사 판별을 이름만이 아니라 "망 단위"로 변경
  (사용자 확인) - SUBSIDIARY_DISPLAY_NAMES(이름만) 대신 SUBSIDIARY_BY_NETWORK
  ({"S-MVNO":{"텔링크"}, "K-MVNO":{"KT엠","스카이라이프"},
  "L-MVNO":{"헬로비전","미디어"}})로 교체. 이유: 헬로비전이 K망 헤더 계산과
  1건 안 맞는 걸 조사하다가, K망에도 "헬로비전"이라는 이름의 데이터가
  1건 있는 게 발견됨 - 이건 데이터 오류가 아니라 예전에 헬로비전이 K망
  에서도 소량 사업을 했다가 접은 실제 기록(사용자 확인). 메시지2 목적상
  이건 자회사로 취급할 필요가 없으므로, 자회사는 반드시 "그 망 안에서"만
  판별하도록 함 - 그 결과 K망의 이 데이터는 자연히 "K-MVNO 일반"의
  일반 사업자로 취급되고(IN=1이라 표시 임계값 미만이라 목록엔 안 뜨지만
  전체 카운트엔 포함), 자회사 섹션엔 진짜 L망 헬로비전만 남음.
- v3.18 (2026-08-26): 메시지2 헤더 계산 방식 변경(사용자 제안) - "일반"
  헤더의 (IN/OUT/순증감)을 merge된 항목들 재합산 대신 "메시지1과 동일한
  망 전체 합계 - 자회사 raw 브랜드 전체"로 직접 계산하도록 변경. IN=0인데
  OUT만 있는 raw 브랜드가 어느 쪽 합계에도 안 잡히고 조용히 누락될 수
  있는 경우(헬로비전 중복 조사 중 발견)까지 포함해서, 항상 메시지1
  총계와 정확히 맞아떨어지도록 산수를 단순화.
- v3.17 (2026-08-26): 메시지2 3건 추가 수정(사용자 요청).
  (1) 헬로비전이 두 줄로 중복 표시되는 버그 발견+수정 - 원본 브랜드가
      표시명 기준으로 쪼개진 경우(KCT 5분할과 동일 패턴) 합산하는
      _merge_network_by_display() 신설, 자회사/일반 양쪽에 다 적용.
      baseline/전일값도 쪼개진 원본 브랜드 전체 합산으로 계산되도록
      _row_parts()가 brand 1개 대신 raw_brands 리스트를 받게 변경.
  (2) "◎ {network} 일반" 순번을 "원래 순위 유지(결번)"에서 "자회사 제외
      하고 1부터 연속 번호"로 변경.
  (3) "◎ {network} 일반" 헤더의 (IN/OUT/순증감) 요약과 "전체 N개" 카운트를
      자회사 제외 기준으로 재계산.
- v3.16 (2026-08-26): 메시지2 재구성(사용자 요청) - 통신3사 자회사(SK텔링크/
  KT엠모바일/KT스카이라이프/LG헬로비전/미디어로그, SUBSIDIARY_DISPLAY_NAMES)를
  망 구분 없이 맨 위 "◎ 자회사" 섹션으로 먼저 모음(순번 없이 신호등만).
  그 아래 "◎ S/K/L-MVNO 일반" 섹션은 자회사를 뺀 나머지를 기존과 동일하게
  보여주되, 번호는 자회사 제외 전의 "원래 순위"를 그대로 유지(빠진 자리는
  결번으로 비워둠 - 매일 순번이 들쭉날쭉 안 바뀌게 하려는 목적). 중복 계산
  줄이려고 전주/전일 대비 계산부를 _row_parts()로 분리.
- v3.15 (2026-08-26): 버그 수정 - v3.14에서 메시지4 "개시" 라벨의 날짜
  출처를 first_in_date(개시일) → first_seen_date(등록일)로 잘못 바꿨던 것
  되돌림. 실행 결과 에넥스_S11('16.01~), KORO_L56('26.01~)처럼 실제 개시
  시점과 안 맞는 날짜가 찍히는 게 발견됨 - first_seen_at(등록일) 필드가
  옛날에 백필된 사업자 상당수에게 부정확한 값으로 들어있어서(예전 세션에서
  이미 알려진 이슈) 발생한 문제. "개시" 단어를 빼고 "~"만 쓰는 포맷은
  유지하되, 날짜 값 자체는 검증된 first_in_date로 복귀. 1년 만료 판정
  로직(개시되면 그 시점부터 1년 리셋)은 원래부터 first_in_date 기준이라
  이번 버그와 무관하게 안 바뀜(사용자 재확인 완료).
- v3.14 (2026-08-26): 2건 수정(사용자 요청).
  (1) 메시지4: v3.13에서 "개시"/"등록" 구분을 없애고 전부 "~"로 통일했던
      것을 부분 되돌림 - 개시(실적 있음)는 "~" 유지, 등록만 되고 미개시인
      경우("개시 전")는 기존처럼 "(YY.MM등록)"으로 복원.
  (2) 메시지2: ◎ network 헤더 옆에 메시지1과 동일한 (IN/OUT/순증감) 요약
      추가 - build_message2 시그니처에 out_totals 파라미터 신규 추가,
      build_all_reports 호출부도 같이 수정.
- v3.13 (2026-08-26): 3건 동시 수정(사용자 요청).
  (1) 메시지2 표시 대상을 메시지1과 통일 - K/L-MVNO도 top10 고정 대신
      "당일 IN≥30" 전부 표시(DAILY_IN_FLOOR 재사용), 메시지1과 동일한
      "전체 N개 중 당일 IN≥30 M개 사업자" 헤더 문구도 추가.
  (2) 신호등(🟢/🔴/🟡)은 IN≥30인 사업자에만 적용 - 소액 사업자(1~2건짜리가
      %는 수백%로 튀는 착시) 색상 오해 방지. 숫자 자체는 여전히 다 보여줌,
      색만 제외.
  (3) 메시지4(신규사업자): 천단위 축약(format_count_abbrev) 폐기, 누적/
      어제는 콤마 포맷 그대로 원래 숫자 표시. 월평균은 신규
      format_monthly_avg()로 - 기본 소수점 없이 반올림 정수, 단 반올림값의
      일의자리가 0이면 소수점 1자리로 표시(0.3처럼 원래 작은 값이 반올림시
      0으로 뭉개지는 것 방지 목적, 기존 로직 그대로 유지되는 효과).
      "개시"/"등록" 라벨 구분 폐기 - 개시 여부와 무관하게 등록일
      (first_seen_at) 하나로 통일해서 "(YY.MM~)" 형태로만 표시.
- v3.12 (2026-08-26): _spike_light()에 🟡(혼조) 추가(사용자 요청) - 전주
  대비/전일 대비가 방향이 엇갈려 상승(+50%↑)·하락(-50%↓) 조건을 동시에
  만족하는 경우 🟢 대신 🟡로 표시(기존 3색 체계 컨벤션과 통일). 한쪽
  방향만 만족하면 기존과 동일하게 🟢/🔴.
- v3.11 (2026-08-26): 메시지2 포맷을 메시지1과 통일(사용자 요청) - 제목
  변경("MNP 사업자별 IN 실적" → "MNP 사업자별 IN 증감 현황"), "사업자 | 실적 |
  전주 대비 | 전일 대비" 표 헤더(사업자 줄마다 반복)를 메시지1 방식인
  "[ 실적 / 전주 대비 / 전일 대비 ]" 한 줄(제목 바로 아래, 1회만)로 교체.
  전주/전일 대비 신호등 신설(_spike_light, SPIKE_LIGHT_THRESHOLD=0.5) -
  둘 중 하나라도 +50%↑면 🟢, -50%↓면 🔴 접두. 줄 포맷도 "이름 : a / b / c"
  → "이름 a / b / c"(콜론 제거, 사용자 예시 그대로).
- v3.10 (2026-08-26): 메시지1 K/L-MVNO 표시 기준 변경(사용자 요청) - 기존
  "월누적 IN≥100(또는 50) + 상위 10개만 표시"는 월초/월말에 누적치 기준선이
  달라지는 문제가 있어서 폐기. "해당일 IN≥30" 사업자를 개수 제한 없이
  전부 표시하는 방식으로 변경(신규 상수 DAILY_IN_FLOOR=30, 기존
  IN_FLOOR_FOR_COUNT/TOP_N 기반 K/L 절단 로직 제거). S-MVNO는 기존과
  동일하게 전체 표시. compute_month_cumulative_in()은 더 이상 메시지1에서
  안 쓰지만 향후 참고용으로 함수 자체는 남겨둠(호출부만 제거).
- v3.9 (2026-08-26): 메시지1 헤더의 "월누적 IN≥N M개 사업자" 카운트 기준
  IN_FLOOR_FOR_COUNT를 50 → 100으로 테스트 상향(사용자 요청 - K/L망
  사업자수가 얼마나 잡히는지 실측 확인 목적). 표시 개수(K/L 상위10)
  자체는 이 상수와 무관해서 안 바뀜, 헤더의 M 숫자만 영향받음.
- v3.8 (2026-08-26): 메시지2 재구성(사용자 요청) - v3.7의 "전체 network
  통합 top10" 방식은 같은 사업자명이 망마다 따로 있는 경우(프리텔/KCT/
  스테이지 등) 어느 망 소속인지 구분이 안 되고, 대형사업자 위주로만
  채워지는 문제가 있었음. 메시지1과 동일한 방식(◎ network 헤더, S-MVNO
  전체 / K·L 상위 10개)으로 재구성. 컬럼(사업자|실적|전주 대비|전일 대비)
  자체는 그대로 유지.
- v3.7 (2026-08-26): 메시지 길이 문제로 대폭 축소(사용자 요청).
  (1) build_message1: 특이사항 표시 전부 제거(색/IN·OUT·순증감 특이줄/
      사업자간 빈줄) - "N) 사업자 : IN / OUT / 순증감" 한 줄만 남김.
      사업자별 baseline 계산(compute_baseline/compute_net_baseline)도
      더 이상 안 씀 - Firestore 읽기량도 같이 줄어듦. 반환값이
      (텍스트, spike_records) 튜플에서 텍스트 단독으로 변경됨(spike_records
      폐기 - 메시지2가 더 이상 이걸 안 씀).
  (2) build_message2 전면 재작성: 기존 "전체 특이사항 나열" 방식 폐기,
      "오늘 IN 실적 상위 10개(전체 network 통합)"만 표로 표시(사용자
      확정). 컬럼: 사업자 | 실적 | 전주 대비 | 전일 대비. 전주 대비는
      기존 로직 그대로 재사용(최근 4주 같은요일/휴일 평균, compute_baseline).
      전일 대비는 신규 - target_date-1 값과 직접 비교(_pct_change 신설).
      [순증감]/[IN]/[OUT] 섹션 구분, 📌요약, 원인분석 등 전부 폐기.
  (3) build_new_operators_message(메시지4): 누적/월평균/어제 3개 숫자에
      천단위 축약 적용(신설 format_count_abbrev - 1000 이상이면
      "N.N천" 표기, 미만이면 기존대로). NAME_SUFFIX_PATTERN에 괄호형
      접미사(`(SKT)`/`(KT)`/`(LGU+)`/`(LG)`) 매칭 추가 - "KORO(LG)"가
      "KORO"로 정리 안 되던 사소한 버그 수정(남은작업 5번 항목과 동일 건,
      여기서 같이 처리). 기존 BRAND_SHORT_NAMES의 "세종텔레콤(KT)"/
      "우들모바일(LG)" 항목은 이제 clean_brand_name 단계에서 이미 괄호가
      제거되므로 사실상 미사용되지만, 다른 경로에서 원본명이 직접 들어올
      가능성에 대비해 그대로 둠(안전 목적, 제거 안 함).
  (4) build_all_reports: build_message1/build_message2 호출부 시그니처
      변경 반영(spike_records 인자 제거).
  ⚠️ 참고: build_message1 반환 형식이 바뀌었으므로, 혹시 다른 스크립트가
  build_message1()을 직접 호출해서 튜플 언패킹하고 있다면 같이 수정 필요
  (ktoa_mvno_period_report.py는 이 함수를 안 쓰므로 영향 없음 확인함).
- v3.6 (2026-08-18): 색이 너무 많아서 오히려 안 보인다는 피드백으로 대폭
  정리(사용자 요청).
  (1) 메시지1: IN/OUT 특이점 줄에서 색 이모지 제거, "-" 기호로 통일. 순증감
      줄만 색(🔴/🔵) 유지. 사업자 사이 빈 줄 추가로 가독성 개선.
  (2) 메시지2: 맨 위에 "요약" 블록 신설 - 망별로 헤드라인 색(🔴=3망 중
      순증감 최악/🟢=순증가/🟡=나머지, _network_headline_color) +
      (IN/OUT/순증감) 숫자 + 📌 한줄요약을 모아서 먼저 보여줌. 이후 망별
      상세 섹션에서는 📌 요약 중복 제거(요약 블록에 이미 있으므로). IN/OUT
      개별 항목 색 제거하고 "-" 기호로 통일(순증감만 색 유지 - 메시지1과
      동일 원칙). 원인분석 줄을 1줄(ㅡ...)에서 2줄(- IN/OUT 숫자, - 결론
      문장)로 분리. OUT 최대볼륨 코멘트를 같은 줄 trailing text에서 별도
      들여쓰기 줄로 이동.
  (3) 메시지4: 헤더를 "'26년 신규사업자"(고정 연도)에서
      "⚡신규사업자('25.08월~현재)"(현재 기준 1년 전~현재, 동적 계산)로
      변경 - 목록 자체가 "최근 1년 이내" 기준으로 필터링되고 있으니
      헤더도 그 기간을 명시하는 게 더 정확함.
- v3.5 (2026-08-18): 신규사업자 메시지 이슈 2건 발견+수정 - "등록"만 된
  것도 1년 지나면 제외, 사업자명 옆 KTOA 코드 표시 추가.
- v3.4 (2026-08-18): registry network 필드 코드값 불일치 버그 수정.
- v3.3 (2026-08-18): 📌 요약 줄 순증감 숫자 오류 수정.
- v3.2 (2026-08-18): 대화로 확정된 요구사항 대거 반영.
  (1) 색상 체계 신설: ⚡ 이모지 대신 5단계 신호등(🔴🟠🟡🟢🔵)으로 교체.
      IN처럼 "높을수록 좋은" 지표는 spike_color(higher_is_bad=False),
      OUT처럼 "높을수록 나쁜" 지표는 spike_color(higher_is_bad=True)로
      방향을 반대로 매핑 - 증가해도 그게 나쁜 신호(OUT 급증=이탈 확대)면
      차가운색(🔵), 좋은 신호(OUT 급감)면 따뜻한색(🔴)이 되도록.
  (2) classify_net_change() 판정 기준 재정의: 기존 "절대값 100건 이상 차이"
      대신 "부호 반전(무조건 특이) 또는 같은부호에서 절대값 2배 이상 확대"로
      변경(사용자 확정). net_change_color()로 개선(🔴)/악화(🔵) 2색만 사용.
  (3) build_message1: 헤더의 "전체N개 중 IN≥50 M개" 조건을 "월누적 IN≥50"
      기준으로 변경(compute_month_cumulative_in 신설 - 이번달 1일~대상일
      전체 daily 문서를 합산, fetch_brand_docs 캐시 재사용). 표시 개수는
      기존 그대로(S 전체/K·L 상위 10개) - 조건 카운트만 월누적 기준으로
      분리. 사업자별 줄에 IN뿐 아니라 OUT/순증감 특이점도 같은 색상으로
      추가 표시(기존엔 IN만 표시했음). 이후 build_message2가 쓸 수 있도록
      spike_records에 "all"(display_list 전체의 in/out 현재값+baseline)도
      같이 기록.
  (4) build_message2 전면 재작성:
      - 섹션 순서를 [순증감, IN, OUT]으로 변경(기존 IN/OUT/순증감).
      - "해당 없음" -> "특이사항 없음".
      - IN/OUT 각각을 "▲ 증가"/"▼ 감소" 하위 섹션으로 분리.
      - 정렬 기준을 사업자 랭킹 순서 대신 "오늘 값(절대 건수) 내림차순"으로
        변경 - 비율이 커도 건수가 작으면 아래로 밀리게.
      - "94건 → 163건" 형태의 "건" 중복 표기를 "94 → 163건"으로 정리,
        "+72%" 부호 표기로 통일(기존 "72% 증가" 문장형에서 전환).
      - 망(◎) 헤더 아래 📌 한 줄 요약 추가(_network_summary_line, 1차
        템플릿 - IN/OUT 최대 증가 사업자 + 순증감 방향으로 자동 조합).
      - 순증감 항목마다 원인분석 줄(ㅡ IN/OUT 각각 몇% 움직였는지, 어느
        쪽이 더 컸는지) 추가 - build_message1에서 넘겨준 spike_records
        ["all"]로 해당 사업자의 IN/OUT 현재·baseline을 조회해서 계산.
      - OUT 증가 목록에서 오늘 값이 가장 큰(=제일 나쁜 방향으로 볼륨이
        큰) 1건에만 짧은 인라인 코멘트(" — ...") 부착.
      - "오늘의 경계 신호" 별도 섹션은 폐기(코멘트를 본문에 녹이는
        방식으로 대체하기로 확정).
  (5) build_new_operators_message() 신설: ktoa_mvno_operator_registry
      기준 신규 사업자 목록. 개시(first_in_date 있음)면 "(개시 YY.MM)" +
      누적/월평균/어제 3개 숫자, 미개시(등록만)면 "(등록 YY.MM)" +
      "개시 전"만 표시. 개시된 건 개시일로부터 1년 지나면 목록에서 자동
      제외, 미개시(등록만)인 건 기간 제한 없이 계속 유지(사용자 확정).
      별도 메시지로 분리, 발송 순서상 맨 마지막(메시지4).
  (6) build_all_reports/main/send_telegram: 메시지 4종(msg1~msg4)으로
      확장. send_telegram이 리스트를 받으므로 호출부만 msg4 추가.
- v3.1 (2026-07-31): 메시지3 헤더를 "◎ 사업자명, 계 : N건"에서
  "◎ 사업자명 : 총 N건"으로 변경(사용자 확정).
- v3.0 (2026-07-31): 사업자명 단축 기능 추가(BRAND_SHORT_NAMES,
  shorten_brand_name()).
- v2.9 (2026-07-31): is_mno_brand() 필터 누락 버그 수정, 메시지3 구분자 변경.
- v2.8 (2026-07-31): 메시지3 전면 재작성 - 동적 3망 탐색 방식으로 전환.
- (이전 이력은 v2.7 이하 생략)

사업자별(브랜드) 텔레그램 리포트 생성 스크립트
- 대상 컬렉션: ktoa_mvno_brand_in, ktoa_mvno_brand_out, ktoa_mvno_operator_registry
- network 필드 값으로 S-MVNO / K-MVNO / L-MVNO 그룹핑

실행 환경: Cloud Shell(~/mvno-bot-cloudrun/mvno-bot-cloudrun/brand-report)에서 실행할 것.

사용법:
    python3 ktoa_mvno_report.py 2026-07-28
    python3 ktoa_mvno_report.py 2026-07-28 --telegram   # 텔레그램 발송(개인방)
"""

import re
import argparse
from datetime import date, timedelta
from collections import defaultdict

from google.cloud import firestore

from save_brand_context import build_full_text, save_context_text

# ── 설정 ──────────────────────────────────────────────────────────────
PROJECT_ID = "mvno-484509"
DATABASE_ID = "mvno-data"
NETWORKS = ["S-MVNO", "K-MVNO", "L-MVNO"]
NETWORK_DB_TO_LABEL = {"SKT": "S-MVNO", "KT": "K-MVNO", "LGU": "L-MVNO"}
LOOKBACK_WEEKS = 4
SPIKE_THRESHOLD = 0.20
MS_LOOKBACK_DAYS = 7
TOP_N = 10
DAILY_IN_FLOOR = 30  # 메시지1 K/L 표시기준: 해당일 IN≥30(v3.10) - 기존 월누적 기준 폐기
FIXED_BRAND_NETWORK_ALIASES = {
    "프리텔레콤": {"L-MVNO": "프리티"},
}
NEW_OPERATOR_EXPIRE_DAYS = 365  # 개시 후 이 일수 지나면 신규사업자 목록에서 자동 제외(등록만 된 건 무제한 유지)


KR_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 1), date(2026, 3, 2),
    date(2026, 5, 5),
    date(2026, 5, 24), date(2026, 5, 25),
    date(2026, 6, 6),
    date(2026, 8, 15), date(2026, 8, 17),
    date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26),
    date(2026, 10, 3),
    date(2026, 10, 9),
    date(2026, 12, 25),
}

NAME_SUFFIX_PATTERN = re.compile(
    r"(\(SKT\)|\(KT\)|\(LGU\+\)|\(LG\)|SKT|KT|LGU\+|LG|\(재판매\)|\(미사용\))$"
)

MNO_BRAND_NAMES = {"SKT", "KT", "LGU", "LGU+", "LG", "LG U+", "KTF", "LGT"}


def is_mno_brand(name: str) -> bool:
    return name in MNO_BRAND_NAMES


def format_signed(value: float, unit: str = "") -> str:
    if value >= 0:
        return f"+{value:,.0f}{unit}"
    return f"▲{abs(value):,.0f}{unit}"


def clean_brand_name(name: str) -> str:
    return NAME_SUFFIX_PATTERN.sub("", name).strip()


def format_count_abbrev(n) -> str:
    """1,000 이상이면 'N.N천' 축약, 미만이면 기존 표기 유지(정수는 콤마,
    소수는 소수점 1자리) - v3.7에서 메시지4용으로 만들었으나 v3.13에서
    메시지4가 천단위 축약을 안 쓰는 쪽으로 바뀌면서 현재 호출부 없음
    (다른 용도로 필요해질 수 있어 남겨둠)."""
    if n is None:
        return "-"
    if abs(n) >= 1000:
        return f"{n / 1000:.1f}천"
    if float(n).is_integer():
        return f"{int(n):,}"
    return f"{n:,.1f}"


def format_monthly_avg(v: float) -> str:
    """메시지4 월평균 표기(v3.13, 사용자 요청): 기본은 소수점 없이 반올림한
    정수. 단, 그 반올림값의 일의자리가 0이면(예: 2,040 / 100 / 0) 대신
    소수점 1자리로 표시(0이 실제 0인지 반올림 결과인지 구분하기 위함)."""
    rounded = round(v)
    if rounded % 10 == 0:
        return f"{v:,.1f}"
    return f"{rounded:,}"


BRAND_SHORT_NAMES = {
    "에넥스텔레콤": "에넥스", "프리텔레콤": "프리텔", "스테이지파이브": "스테이지",
    "큰사람커넥트": "큰사람", "KT엠모바일": "KT엠", "KT스카이라이프": "스카이라이프",
    "더원플랫폼": "더원", "코드모바일": "코드", "LG헬로비전": "헬로비전",
    "토스모바일": "토스", "시월텔레콤": "시월", "미디어로그": "미디어",
    "고고팩토리": "고고", "KB국민은행": "KB", "아이즈비전": "아이즈",
    "SK텔링크": "텔링크", "ACN코리아": "ACN", "CK커뮤스트리": "CK",
    "KDDI코리아": "KDDI", "KG모바일": "KG", "MTT텔레콤": "MTT",
    "니즈텔레콤": "니즈", "세종텔레콤": "세종", "세종텔레콤(KT)": "세종",
    "스피츠모바일": "스피츠", "씨엔커뮤니케이션": "씨엔", "아이디스파워텔": "아이디스",
    "앤알커뮤니케이션": "앤알", "엔티온텔레콤": "엔티온", "오파스넷": "오파스",
    "와이드모바일": "와이드", "우들모바일(LG)": "우들", "원텔레콤": "원텔",
    "인스코리아": "인스", "장성모바일한국": "장성", "제주방송": "제주",
    "찬스모바일": "찬스", "친구아이앤씨": "친구", "친구아이엔씨": "친구",
    "파인디지털": "파인", "한국이텔레콤": "한국이", "한패스모바일": "한패스",
    "화인통신": "화인", "마블프로듀스": "마블", "서경방송": "서경",
    "네이블": "네이블", "아정커뮤니케이션": "아정당",
    "GME모바일": "GME", "KORO": "KORO", "우들모바일": "우들",
    "한패스인터내셔널": "한패스",
}


def shorten_brand_name(name: str) -> str:
    return BRAND_SHORT_NAMES.get(name, name)


def is_holiday(d: date) -> bool:
    return d in KR_HOLIDAYS_2026 or d.weekday() >= 5


def get_comparison_dates(target_date: date, weeks: int = LOOKBACK_WEEKS) -> list[date]:
    results = []
    target_is_holiday = is_holiday(target_date)
    cursor = target_date - timedelta(days=1)
    for _ in range(200):
        if len(results) >= weeks:
            break
        if target_is_holiday:
            if is_holiday(cursor):
                results.append(cursor)
        else:
            if cursor.weekday() == target_date.weekday() and not is_holiday(cursor):
                results.append(cursor)
        cursor -= timedelta(days=1)
    return results


def get_recent_n_days(target_date: date, n: int = MS_LOOKBACK_DAYS) -> list[date]:
    return [target_date - timedelta(days=i) for i in range(1, n + 1)]


_doc_cache: dict[tuple[str, str], dict] = {}


def fetch_brand_docs(db, collection_name: str, target_date: date) -> dict:
    key = (collection_name, target_date.isoformat())
    if key in _doc_cache:
        return _doc_cache[key]
    date_str = target_date.strftime("%Y-%m-%d")
    docs = db.collection(collection_name).where("date", "==", date_str).stream()
    result = {d.get("brand"): d for d in (doc.to_dict() for doc in docs)}
    _doc_cache[key] = result
    return result


def build_network_totals(brand_docs: dict, value_field: str) -> dict:
    result = defaultdict(dict)
    for brand, doc in brand_docs.items():
        if is_mno_brand(brand):
            continue
        db_network = doc.get("network")
        network = NETWORK_DB_TO_LABEL.get(db_network)
        value = doc.get(value_field)
        if network is None or value is None:
            continue
        result[network][brand] = value
    return result


def compute_month_cumulative_in(db, target_date: date) -> dict:
    """
    target_date가 속한 달의 1일부터 target_date까지 IN 누적. {network: {brand: sum}}.
    build_message1 헤더의 "월누적 IN≥50 M개 사업자" 조건 계산용(사용자 요청,
    2026-08-18: 일별 리포트에서도 카운트 조건만은 월누적 기준으로).
    fetch_brand_docs 캐시를 그대로 재사용하므로 이미 조회된 날짜(오늘 등)는
    중복 쿼리하지 않음.
    """
    start = target_date.replace(day=1)
    result: dict = defaultdict(lambda: defaultdict(int))
    cursor = start
    while cursor <= target_date:
        docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", cursor)
        for brand, doc in docs.items():
            if is_mno_brand(brand):
                continue
            net = NETWORK_DB_TO_LABEL.get(doc.get("network"))
            val = doc.get("total_in")
            if net and val is not None:
                result[net][brand] += val
        cursor += timedelta(days=1)
    return result


def compute_baseline(db, collection_name: str, value_field: str,
                      target_date: date, brand: str) -> float | None:
    comp_dates = get_comparison_dates(target_date)
    values = []
    for d in comp_dates:
        docs = fetch_brand_docs(db, collection_name, d)
        doc = docs.get(brand)
        if doc and doc.get(value_field) is not None:
            values.append(doc[value_field])
    if not values:
        return None
    return sum(values) / len(values)


def compute_net_baseline(db, target_date: date, brand: str) -> float | None:
    comp_dates = get_comparison_dates(target_date)
    values = []
    for d in comp_dates:
        in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", d)
        out_docs = fetch_brand_docs(db, "ktoa_mvno_brand_out", d)
        in_doc = in_docs.get(brand)
        out_doc = out_docs.get(brand)
        if in_doc is None and out_doc is None:
            continue
        in_v = in_doc.get("total_in", 0) if in_doc else 0
        out_v = out_doc.get("total_out", 0) if out_doc else 0
        values.append(in_v - out_v)
    if not values:
        return None
    return sum(values) / len(values)


MIN_VALUE_FOR_SPIKE = 50


def classify_change(current: float, baseline: float | None,
                     min_value: float = MIN_VALUE_FOR_SPIKE) -> tuple[str, float | None]:
    if baseline is None:
        return "신규", None
    if current < min_value:
        change = None if baseline == 0 else (current - baseline) / baseline
        return "", change
    if baseline == 0:
        return ("특이", None) if current > 0 else ("", 0.0)
    change = (current - baseline) / baseline
    if abs(change) >= SPIKE_THRESHOLD:
        return "특이", change
    return "", change


def spike_color(pct: float | None, higher_is_bad: bool = False) -> str:
    """
    3색 체계(사용자 확정, 2026-08-18 재설계 - 기존 5단계가 "헷갈린다"는
    피드백 반영): 🟢좋음 / 🔴나쁨 / 🟡애매. pct는 소수(0.72=72%).
    - higher_is_bad=False(IN 등): +50%↑ 🟢 / -50%↓ 🔴 / 그 사이(±20~50%) 🟡
    - higher_is_bad=True(OUT 등): +50%↑ 🔴 / -50%↓ 🟢 / 그 사이 🟡
    ±20% 미만이거나 pct가 None이면 빈 문자열(색 없음, 애초에 특이점 아님).
    """
    if pct is None:
        return ""
    if higher_is_bad:
        if pct >= 0.5:
            return "🔴"  # OUT 등 증가 = 나쁨
        if pct <= -0.5:
            return "🟢"  # OUT 등 감소 = 좋음
    else:
        if pct >= 0.5:
            return "🟢"  # IN 등 증가 = 좋음
        if pct <= -0.5:
            return "🔴"  # IN 등 감소 = 나쁨
    return "🟡"


NET_CHANGE_RATIO_THRESHOLD = 2.0  # 같은 부호일 때 특이점 판정 배수(2배 이상)


def classify_net_change(current: float, baseline: float | None) -> tuple[str, float | None]:
    """
    순증감(IN-OUT) 전용 판정(사용자 확정, 2026-08-18 재정의).
    - baseline이 None -> ("신규", None)
    - 부호 반전(순증<->순감 전환) -> 무조건 "특이"
    - 같은 부호에서 |current| >= 2 * |baseline| (절대값 2배 이상 확대) -> "특이"
    - 그 외 -> ("", 차이값)
    """
    if baseline is None:
        return "신규", None
    diff = current - baseline
    if baseline == 0:
        return ("특이", diff) if current != 0 else ("", 0.0)
    sign_flip = (current >= 0) != (baseline >= 0)
    if sign_flip:
        return "특이", diff
    if abs(current) >= NET_CHANGE_RATIO_THRESHOLD * abs(baseline):
        return "특이", diff
    return "", diff


def net_change_color(current: float, baseline: float) -> str:
    """
    개선(🟢)/악화(🔴) 2색(사용자 지적, 2026-08-18 재수정: "2배 넘으면
    빨강이나 초록이 맞을듯, 노란색 기준이 뭐지?"). classify_net_change가
    이미 "부호반전 또는 2배 이상"만 걸러서 [순증감]에 올리므로, 그 안에서
    또 3배 기준으로 애매한 구간(🟡)을 나눌 필요가 없었음 - 애매함은 IN/OUT
    쪽의 낮은 진입기준(20%)에만 의미가 있는 개념. 이제 방향(개선/악화)만
    보고 바로 색 결정.
    """
    if baseline == 0:
        if current > 0:
            return "🟢"
        if current < 0:
            return "🔴"
        return "🟡"  # 이론상 도달 안 함(0->0은 classify_net_change에서 애초에 "특이" 아님)
    return "🟢" if current > baseline else "🔴"


def net_change_ratio_str(current: float, baseline: float) -> str:
    """'2.8배' 같은 배수 문구. baseline이 0이거나 부호반전이면 배수 대신 상태문구."""
    if baseline == 0:
        return "0에서 시작"
    if (current >= 0) != (baseline >= 0):
        return "부호 반전"
    ratio = abs(current) / abs(baseline)
    return f"{ratio:.1f}배"


# ── 메시지1: 사업자별 실적 (S 전체 / K·L top10) ─────────────────────────

def build_message1(db, target_date: date, in_totals: dict, out_totals: dict) -> str:
    """
    반환: 메시지 텍스트만. S-MVNO는 전체 표시, K/L-MVNO는 '해당일 IN≥30'
    사업자 전부 표시(v3.10, 사용자 요청 - 기존 월누적 기준+top10 고정은
    월초/월말에 기준선이 달라지는 문제가 있어서 폐기, 당일 실적 기준
    으로 단순화 + 개수 제한 없이 조건 맞는 사업자 다 보여주기로 변경).
    """
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [f"📊 MNP 주요 사업자별 실적 ({date_str})", "[ IN/OUT/순증감 ]"]

    for network in NETWORKS:
        in_by_brand = in_totals.get(network, {})
        out_by_brand = out_totals.get(network, {})
        all_brands = set(in_by_brand) | set(out_by_brand)

        if not all_brands:
            lines.append(f"\n◎ {network}: 데이터 없음")
            continue

        ranked = sorted(all_brands, key=lambda b: in_by_brand.get(b, 0), reverse=True)
        ranked = [b for b in ranked if in_by_brand.get(b, 0) > 0]

        total_count = len(all_brands)

        network_in_sum = sum(in_by_brand.values())
        network_out_sum = sum(out_by_brand.values())
        network_net_sum = network_in_sum - network_out_sum
        summary = f"{network_in_sum:,}/{network_out_sum:,}/{format_signed(network_net_sum)}"

        if network == "S-MVNO":
            header = f"\n◎ {network} ({summary})"
            display_list = ranked
        else:
            display_list = [b for b in ranked if in_by_brand.get(b, 0) >= DAILY_IN_FLOOR]
            floor_count = len(display_list)
            header = (f"\n◎ {network} ({summary})\n"
                      f"전체 {total_count}개 중 당일 IN≥{DAILY_IN_FLOOR} {floor_count}개 사업자")

        lines.append(header)
        for i, brand in enumerate(display_list, 1):
            in_v = in_by_brand.get(brand, 0)
            out_v = out_by_brand.get(brand, 0)
            net_v = in_v - out_v
            display_name = shorten_brand_name(clean_brand_name(brand))
            lines.append(f"{i}) {display_name} : {in_v:,} / {out_v:,} / {format_signed(net_v)}")

    return "\n".join(lines)


# ── 메시지2: 망별 IN 실적 (전주/전일 대비) ────────────────────────────

def _pct_change(current, baseline):
    """baseline 대비 증감률(소수). baseline이 None이거나 0이면 비교불가(None)."""
    if baseline is None or baseline == 0:
        return None
    return (current - baseline) / baseline


SPIKE_LIGHT_THRESHOLD = 0.5  # 전주/전일 대비 중 하나라도 이 이상이면 🟢, -이하면 🔴(v3.11)


def _spike_light(week_pct, day_pct, threshold: float = SPIKE_LIGHT_THRESHOLD) -> str:
    """전주 대비/전일 대비 각각 +threshold 이상(상승) / -threshold 이하(하락) 여부를
    보고 판정(v3.12): 상승만 있으면 🟢, 하락만 있으면 🔴, 방향이 엇갈려 둘 다
    있으면(예: 전주 +60%인데 전일 -60%) 🟡(혼조/애매) - 기존 3색 체계
    (🟢좋음/🔴나쁨/🟡애매) 컨벤션과 통일."""
    up = any(p is not None and p >= threshold for p in (week_pct, day_pct))
    down = any(p is not None and p <= -threshold for p in (week_pct, day_pct))
    if up and down:
        return "🟡 "
    if up:
        return "🟢 "
    if down:
        return "🔴 "
    return ""


SUBSIDIARY_BY_NETWORK = {
    "S-MVNO": {"텔링크"},
    "K-MVNO": {"KT엠", "스카이라이프"},
    "L-MVNO": {"헬로비전", "미디어"},
}
# 통신3사 자회사 MVNO(SK텔링크/KT엠모바일/KT스카이라이프/LG헬로비전/미디어로그)의
# shorten_brand_name() 결과값 - 망별로 매칭(v3.19). 이름만으로 매칭하면 다른
# 망에서 예전에 운영하다 접은 동명이인 데이터(예: 헬로비전이 한때 K망에서도
# 소량 사업을 했던 기록이 남아있음 - 실제 데이터, 오류 아님)까지 자회사로
# 잘못 묶이므로, 자회사 해당 여부는 반드시 "그 망 안에서" 판단해야 함
# (사용자 확인, 2026-08-26).


def _row_parts(db, target_date: date, raw_brands: list, in_v: int, yesterday_docs: dict, apply_color: bool):
    """전주/전일 대비 문자열 + (조건 만족시) 신호등을 계산. raw_brands는 보통
    브랜드 1개짜리 리스트지만, 같은 표시명으로 원본 브랜드가 여러 개로
    쪼개진 경우(v3.17에서 헬로비전 중복 발견 - KCT 5분할과 동일 패턴) 그
    원본 브랜드들 전부를 넘겨서 baseline/전일값도 합산되게 함."""
    week_baseline_sum, has_baseline = 0.0, False
    for b in raw_brands:
        wb = compute_baseline(db, "ktoa_mvno_brand_in", "total_in", target_date, b)
        if wb is not None:
            week_baseline_sum += wb
            has_baseline = True
    week_pct = _pct_change(in_v, week_baseline_sum if has_baseline else None)
    week_str = f"{format_signed(week_pct * 100)}%" if week_pct is not None else "-"

    y_sum, has_y = 0, False
    for b in raw_brands:
        y_doc = yesterday_docs.get(b)
        if y_doc:
            y_sum += y_doc.get("total_in") or 0
            has_y = True
    day_pct = _pct_change(in_v, y_sum if has_y else None)
    day_str = f"{format_signed(day_pct * 100)}%" if day_pct is not None else "-"

    color = _spike_light(week_pct, day_pct) if apply_color else ""
    return color, week_str, day_str


def _merge_network_by_display(in_by_brand: dict, out_by_brand: dict) -> dict:
    """망 하나의 raw brand -> IN/OUT 값을 표시명(shorten_brand_name(clean_brand_name))
    기준으로 합산. 같은 표시명인데 원본 브랜드 코드가 여러 개로 쪼개진 경우
    (v3.17 - 헬로비전이 중복으로 두 줄 나오는 게 발견됨, KCT 5분할과 동일
    패턴)를 하나로 합쳐서 보여주기 위함. 반환: {표시명: {"raw_brands": [...],
    "in": 합계, "out": 합계}}."""
    merged: dict = {}
    for brand in set(in_by_brand) | set(out_by_brand):
        name = shorten_brand_name(clean_brand_name(brand))
        slot = merged.setdefault(name, {"raw_brands": [], "in": 0, "out": 0})
        slot["raw_brands"].append(brand)
        slot["in"] += in_by_brand.get(brand, 0)
        slot["out"] += out_by_brand.get(brand, 0)
    return merged


def build_message2(db, target_date: date, in_totals: dict, out_totals: dict) -> str:
    """
    메시지2 v3.19(사용자 확인, 2026-08-26) - 자회사 판별을 이름만이 아니라
    "망 단위"로(SUBSIDIARY_BY_NETWORK) - 다른 망에서 예전에 운영하다 접은
    동명이인 데이터가 자회사로 잘못 묶이는 걸 방지.
    v3.18 헤더 요약 계산 방식 유지:
    "일반" 헤더의 (IN/OUT/순증감)을 merge된 general_all 합산이 아니라
    "메시지1과 동일한 망 전체 합계 - 자회사 raw 브랜드 전체"로 직접 계산.
    이렇게 하면 IN=0/OUT>0인 raw 브랜드가 어느 쪽에도 안 걸려 조용히
    누락되는 경우가 있어도(전날 헬로비전 중복 조사 중 발견) 항상 메시지1
    총계와 정확히 맞아떨어짐 - 산수가 절대 안 어긋나는 쪽으로 단순화.
    v3.16/v3.17 기존 사항 유지:
    - 통신3사 자회사(SK텔링크/KT엠모바일/KT스카이라이프/LG헬로비전/미디어로그)를
      맨 위 "◎ 자회사"로 모음(순번 없음), 그 아래 "◎ {network} 일반"은
      자회사 제외하고 1부터 연속 번호.
    - 같은 표시명으로 원본 브랜드가 쪼개진 경우 망 내에서 합산해서 한 줄로
      표시(_merge_network_by_display) - 단, 망을 넘나드는 동명이인(예:
      헬로비전이 서로 다른 망에 각각 존재하는 경우처럼 보이는 케이스)은
      원본 데이터 자체를 확인해야 함(사용자에게 진단 쿼리 별도 전달함).
    - 신호등은 자회사/일반 모두 IN≥30인 경우에만 적용.
    - 전주 대비: 최근 4주 같은요일/휴일 평균(compute_baseline) 대비.
    - 전일 대비: target_date-1 값과 직접 비교(_pct_change).
    """
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [
        f"📊 MNP 사업자별 IN 증감 현황 ({date_str})",
        "[ 실적 / 전주 대비 / 전일 대비 ]",
    ]

    yesterday_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", target_date - timedelta(days=1))

    per_network = {}
    for network in NETWORKS:
        by_brand = {b: v for b, v in in_totals.get(network, {}).items() if not is_mno_brand(b)}
        out_by_brand = {b: v for b, v in out_totals.get(network, {}).items() if not is_mno_brand(b)}
        merged = _merge_network_by_display(by_brand, out_by_brand)
        ranked = sorted(merged.items(), key=lambda kv: kv[1]["in"], reverse=True)
        ranked = [(name, info) for name, info in ranked if info["in"] > 0]

        subsidiary_names = SUBSIDIARY_BY_NETWORK.get(network, set())
        general_all = [(name, info) for name, info in ranked if name not in subsidiary_names]
        subsidiary_all = [(name, info) for name, info in ranked if name in subsidiary_names]

        # 헤더 요약(일반=자회사 제외)은 "전체(메시지1과 동일) - 자회사 raw 전체"로
        # 직접 계산(v3.18, 사용자 제안) - merge된 general_all을 그대로 합산하면
        # IN=0/OUT>0인 raw 브랜드가 어느 쪽에도 안 걸려 조용히 누락될 수 있어서
        # (전날 헬로비전 중복건 조사 중 발견), "전체 - 자회사"로 계산해 항상
        # 메시지1 총계와 정확히 맞아떨어지도록 함. raw_brands는 이미
        # SUBSIDIARY_DISPLAY_NAMES로 묶인 원본 브랜드 전부를 포함하고 있어서
        # IN=0짜리 자회사 raw 브랜드까지 빠짐없이 잡힘.
        subsidiary_raw_brands = {b for _, info in subsidiary_all for b in info["raw_brands"]}
        network_total_in = sum(by_brand.values())
        network_total_out = sum(out_by_brand.values())
        subsidiary_in_sum = sum(by_brand.get(b, 0) for b in subsidiary_raw_brands)
        subsidiary_out_sum = sum(out_by_brand.get(b, 0) for b in subsidiary_raw_brands)
        general_in_sum = network_total_in - subsidiary_in_sum
        general_out_sum = network_total_out - subsidiary_out_sum
        summary = f"{general_in_sum:,}/{general_out_sum:,}/{format_signed(general_in_sum - general_out_sum)}"

        general_floor = None if network == "S-MVNO" else DAILY_IN_FLOOR
        per_network[network] = {
            "general_all": general_all, "subsidiary_all": subsidiary_all,
            "summary": summary, "general_floor": general_floor,
        }

    # ── ◎ 자회사(망 구분 없이, 순번 없음) ──
    lines.append("\n◎ 자회사")
    subsidiary_lines = []
    for network in NETWORKS:
        for name, info in per_network[network]["subsidiary_all"]:
            in_v = info["in"]
            color, week_str, day_str = _row_parts(
                db, target_date, info["raw_brands"], in_v, yesterday_docs, apply_color=in_v >= DAILY_IN_FLOOR
            )
            subsidiary_lines.append(f"{color}{name} {in_v:,} / {week_str} / {day_str}")
    lines.extend(subsidiary_lines if subsidiary_lines else ["데이터 없음"])

    # ── ◎ {network} 일반(자회사 제외, 1부터 연속 번호) ──
    for network in NETWORKS:
        pn = per_network[network]
        general_all, summary, floor = pn["general_all"], pn["summary"], pn["general_floor"]

        display_list = general_all if floor is None else [(n, i) for n, i in general_all if i["in"] >= floor]

        lines.append(f"\n◎ {network} 일반 ({summary})")
        if floor is not None:
            lines.append(f"전체 {len(general_all)}개 중 당일 IN≥{floor} {len(display_list)}개 사업자")

        if not display_list:
            lines.append("데이터 없음")
            continue

        for i, (name, info) in enumerate(display_list, 1):
            in_v = info["in"]
            color, week_str, day_str = _row_parts(
                db, target_date, info["raw_brands"], in_v, yesterday_docs, apply_color=in_v >= DAILY_IN_FLOOR
            )
            lines.append(f"{i}) {color}{name} {in_v:,} / {week_str} / {day_str}")

    return "\n".join(lines)


# ── 메시지3: 사업자·망별 M/S (7일 가중평균 대비) ─────────────────────

MS_MIN_SM = 10


def build_message3(db, target_date: date) -> str:
    date_str = target_date.strftime("%Y-%m-%d")
    lines = [
        f"📊 MNP 사업자/망별 M/S ({date_str})",
        "(비교 값은 M/S 기준 최근 7일 평균 대비 %p 차이)",
    ]

    recent_days = get_recent_n_days(target_date, MS_LOOKBACK_DAYS)
    today_in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", target_date)

    recent_brand_totals = defaultdict(lambda: defaultdict(int))
    for d in recent_days:
        docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", d)
        for brand, doc in docs.items():
            net = NETWORK_DB_TO_LABEL.get(doc.get("network"))
            val = doc.get("total_in")
            if net and val is not None:
                recent_brand_totals[net][brand] += val

    grouped = defaultdict(dict)
    alias_lookup = {}
    for canonical, net_aliases in FIXED_BRAND_NETWORK_ALIASES.items():
        for network, alias_name in net_aliases.items():
            alias_lookup[(network, alias_name)] = canonical

    for brand, doc in today_in_docs.items():
        if is_mno_brand(brand):
            continue
        network = NETWORK_DB_TO_LABEL.get(doc.get("network"))
        if network is None or doc.get("total_in") is None:
            continue
        clean_name = clean_brand_name(brand)
        canonical_name = alias_lookup.get((network, clean_name), clean_name)
        grouped[canonical_name][network] = brand

    full_network_brands = {name: nets for name, nets in grouped.items() if len(nets) == 3}

    brand_rows = []
    for canonical_name, net_brands in full_network_brands.items():
        per_network_data = {}
        for net_label, network in [("S", "S-MVNO"), ("K", "K-MVNO"), ("L", "L-MVNO")]:
            matched_brand = net_brands[network]
            today_v = today_in_docs.get(matched_brand, {}).get("total_in", 0)
            recent_brand_sum = recent_brand_totals[network].get(matched_brand, 0)
            per_network_data[net_label] = (today_v, recent_brand_sum)

        sm_today = per_network_data["S"][0]
        if sm_today < MS_MIN_SM:
            continue

        brand_today_sum = sum(v[0] for v in per_network_data.values())
        brand_recent_sum = sum(v[1] for v in per_network_data.values())

        net_display = {}
        for net_label in ["S", "K", "L"]:
            today_v, recent_brand_sum = per_network_data[net_label]
            today_pct = (today_v / brand_today_sum * 100) if brand_today_sum else 0.0
            weighted_avg_pct = (recent_brand_sum / brand_recent_sum * 100) if brand_recent_sum else None

            if weighted_avg_pct is None:
                diff_str = "비교불가(최근 데이터 없음)"
            else:
                diff = today_pct - weighted_avg_pct
                diff_str = f"+{diff:.1f}%p" if diff >= 0 else f"▲{abs(diff):.1f}%p"

            net_display[net_label] = (today_v, today_pct, diff_str)

        brand_rows.append((canonical_name, brand_today_sum, net_display))

    brand_rows.sort(key=lambda row: row[1], reverse=True)

    for canonical_name, brand_today_sum, net_display in brand_rows:
        lines.append(f"\n◎ {shorten_brand_name(canonical_name)} : 총 {brand_today_sum:,}건 (100%)")
        for net_label in ["S", "K", "L"]:
            today_v, today_pct, diff_str = net_display[net_label]
            lines.append(f"  {net_label}: {today_v:,}건 ({today_pct:.0f}%) : {diff_str}")

    return "\n".join(lines)


# ── 메시지4: 신규사업자 ────────────────────────────────────────────

def _month_diff(d1: date, d2: date) -> int:
    """d1이 d2보다 몇 개월 전인지(달력월 기준, 최소 1)."""
    months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    return max(1, months + 1)


def build_new_operators_message(db, target_date: date):
    """
    ktoa_mvno_operator_registry 기준 신규사업자 목록.
    - 개시(first_in_date 있음): 날짜는 개시일(first_in_date) 기준
      "(YY.MM~)"만 표시("개시" 단어는 뺌) + 누적/월평균/어제 3개 숫자.
      ⚠️ v3.14에서 실수로 등록일(first_seen_at)로 바꿨다가 되돌림(v3.15,
      2026-08-26) - first_seen_at은 옛날에 백필된 사업자일수록 부정확한
      값(예: 에넥스_S11이 실제로는 '25.11 개시인데 등록일이 '16.01로
      찍혀있는 등)이 섞여있어서, 실무자 골드데이터로 검증된 first_in_date를
      계속 쓰는 게 맞음. 1년 만료 판정(아래 로직)은 원래부터 first_in_date
      기준이었고 안 바뀜 - "등록 기준 1년 유지, 개시되면 그 시점부터 1년
      리셋"이라는 기존 설계와 일치함(사용자 재확인, 2026-08-26).
      개시일로부터 NEW_OPERATOR_EXPIRE_DAYS(1년) 지나면 목록에서 제외.
    - 미개시(등록만): "(YY.MM등록)" + "개시 전"만(등록일=first_seen_at 기준,
      이 경우는 원래부터 문제없었음). 기간 제한 없이 계속 유지(사용자 확정,
      2026-08-18 - "왜 아직 시작 안 했는지" 계속 상기시키는 용도).
    사업자 자동탐지 자체는 기존 register_new_operators()/check_in_start()가
    매일 이미 하고 있으므로, 이 함수는 그 결과(registry)를 조회해서 새
    포맷으로 보여주기만 함 - 새로운 감지 로직 아님.
    반환: 표시할 사업자가 하나도 없으면 None(메시지 자체를 보내지 않음).
    """
    window_start = target_date - timedelta(days=NEW_OPERATOR_EXPIRE_DAYS)
    window_str = f"'{window_start.strftime('%y.%m')}월~현재"
    lines = [f"⚡신규사업자({window_str})"]
    lines.append("━" * 15)

    any_shown = False

    for db_network, label in NETWORK_DB_TO_LABEL.items():
        # registry의 network 필드는 표시용 라벨("S-MVNO" 등)이 아니라 원본
        # DB코드("SKT"/"KT"/"LGU")로 저장돼있음(한패스 디버깅 때 이미 확인했던
        # 스키마인데 여기서 놓쳐서 늘 0건으로 조회되던 버그, 2026-08-18 발견+수정 -
        # 실행 결과 신규사업자 메시지가 아무 에러 없이 계속 생략되고 있었음).
        docs = db.collection("ktoa_mvno_operator_registry") \
            .where("network", "==", db_network).stream()

        rows = []
        for doc in docs:
            d = doc.to_dict()
            first_seen = d.get("first_seen_at")
            first_in = d.get("first_in_date")
            if not first_seen:
                continue

            first_seen_date = date.fromisoformat(first_seen[:10]) if isinstance(first_seen, str) else (
                first_seen.date() if hasattr(first_seen, "date") else first_seen
            )
            name = shorten_brand_name(clean_brand_name(d.get("name", "")))
            code = d.get("code", "")
            name_with_code = f"{name}_{code}" if code else name

            if first_in:
                first_in_date = date.fromisoformat(first_in[:10]) if isinstance(first_in, str) else (
                    first_in.date() if hasattr(first_in, "date") else first_in
                )
                if (target_date - first_in_date).days > NEW_OPERATOR_EXPIRE_DAYS:
                    continue  # 개시 후 1년 지남 - 더 이상 "신규" 아님

                in_docs = db.collection("ktoa_mvno_brand_in") \
                    .where("brand_code", "==", d.get("code")) \
                    .where("date", ">=", first_in_date.isoformat()) \
                    .where("date", "<=", target_date.isoformat()).stream()
                cumulative = 0
                yesterday_v = 0
                for in_doc in in_docs:
                    dd = in_doc.to_dict()
                    v = dd.get("total_in") or 0
                    cumulative += v
                    if dd.get("date") == target_date.isoformat():
                        yesterday_v = v
                months = _month_diff(first_in_date, target_date)
                monthly_avg = cumulative / months
                rows.append(
                    f"  {name_with_code}('{first_in_date.strftime('%y.%m')}~) : "
                    f"{cumulative:,} / {format_monthly_avg(monthly_avg)} / {yesterday_v:,}건"
                )
            else:
                # 등록만 되고 개시 안 된 경우도 1년 지나면 목록에서 제외(사용자 확정,
                # 2026-08-18 재수정 - 원래는 무제한 유지였으나, 실행해보니 registry의
                # first_in_date가 옛날/종료된 사업자들한테 제대로 안 채워져있어서
                # "등록 24.12"짜리가 무더기로 쌓이는 노이즈 문제 발견 - 1년 소멸로
                # 통일하는 게 실용적).
                if (target_date - first_seen_date).days > NEW_OPERATOR_EXPIRE_DAYS:
                    continue
                rows.append(f"  {name_with_code}('{first_seen_date.strftime('%y.%m')}등록) : 개시 전")

        if rows:
            any_shown = True
            lines.append(f"\n◎ {label} (누적/월평균/어제)")
            lines.extend(rows)

    if not any_shown:
        return None
    return "\n".join(lines)


# ── 실행 ──────────────────────────────────────────────────────────────

def fill_missing_network(target_docs: dict, reference_docs: dict) -> dict:
    result = {}
    for brand, doc in target_docs.items():
        doc = dict(doc)
        if not doc.get("network"):
            ref_doc = reference_docs.get(brand)
            if ref_doc and ref_doc.get("network"):
                doc["network"] = ref_doc["network"]
        result[brand] = doc
    return result


def save_daily_context(db, target_date: date, msg1: str, msg2: str, msg3: str, msg4) -> None:
    """메시지1~4를 기존 콘솔출력과 동일한 구분선으로 이어붙여 text 필드 하나로
    저장(v3.20). doc_id는 date 문자열 - 재실행해도 같은 날짜면 덮어씀."""
    text = build_full_text([msg1, msg2, msg3, msg4])
    date_str = target_date.strftime("%Y-%m-%d")
    save_context_text(db, "ktoa_brand_context_daily", date_str, {"date": date_str, "text": text})


def build_all_reports(target_date: date):
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

    in_docs = fetch_brand_docs(db, "ktoa_mvno_brand_in", target_date)
    out_docs = fetch_brand_docs(db, "ktoa_mvno_brand_out", target_date)
    out_docs = fill_missing_network(out_docs, in_docs)

    in_totals = build_network_totals(in_docs, "total_in")
    out_totals = build_network_totals(out_docs, "total_out")

    msg1 = build_message1(db, target_date, in_totals, out_totals)
    msg2 = build_message2(db, target_date, in_totals, out_totals)
    msg3 = build_message3(db, target_date)
    msg4 = build_new_operators_message(db, target_date)

    save_daily_context(db, target_date, msg1, msg2, msg3, msg4)

    return msg1, msg2, msg3, msg4


def send_telegram(messages: list):
    import os
    import requests

    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = "-1003761301521"
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for msg in messages:
        if msg is None:
            continue
        if len(msg) <= 3800:
            resp = requests.post(url, json={"chat_id": chat_id, "text": msg})
            resp.raise_for_status()
        else:
            chunks, current = [], ""
            for section in msg.split("\n\n"):
                if len(current) + len(section) + 2 > 3800:
                    chunks.append(current)
                    current = section
                else:
                    current = f"{current}\n\n{section}" if current else section
            if current:
                chunks.append(current)
            for chunk in chunks:
                resp = requests.post(url, json={"chat_id": chat_id, "text": chunk})
                resp.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="KTOA 사업자별 텔레그램 리포트 (4종)")
    parser.add_argument("target_date", help="조회 날짜 (YYYY-MM-DD)")
    parser.add_argument("--telegram", action="store_true", help="개인 텔레그램 방으로 발송")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.target_date)
    msg1, msg2, msg3, msg4 = build_all_reports(target_date)

    print(msg1)
    print("\n" + "=" * 50 + "\n")
    print(msg2)
    print("\n" + "=" * 50 + "\n")
    print(msg3)
    if msg4:
        print("\n" + "=" * 50 + "\n")
        print(msg4)

    if args.telegram:
        send_telegram([msg1, msg2, msg3, msg4])
        sent_count = sum(1 for m in [msg1, msg2, msg3, msg4] if m is not None)
        print(f"\n[텔레그램 발송 완료 - 개인방, {sent_count}건]")


if __name__ == "__main__":
    main()