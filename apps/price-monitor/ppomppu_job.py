"""
ppomppu_job.py
──────────────────────────────────────────────────────────────────────────────
뽐뿌 MVNO 모니터링 전용 Cloud Run Job
- main.py의 _run_ppomppu_task 로직을 독립 Job으로 분리
- Cloud Run Job은 완료 후 자동 종료 → 컨테이너 강제종료 문제 없음

[수정 이력]
v2.6 | 2026-09-20 | post_block()/T다이렉트 묶음요약의 제목을 URL 하이퍼링크로 변경하고
      | 하단 별도 URL 줄 제거 - 모바일에서 긴 URL이 2~3줄씩 차지해 메시지가
      | 쓸데없이 길어지던 문제. esc() 헬퍼 추가해 제목/사업자명/요약에 HTML
      | 이스케이프 적용 (제목에 &,<,> 있으면 파싱 실패로 메시지 전송이
      | 조용히 실패하던 잠재 버그도 같이 해결)
v2.5 | 2026-09-20 | MNO_DIRECT에 "요고"(KT 요고모바일) 추가 - core/mvno_classifier.py
      | v3.6과 함께 적용해야 MNO 직영 온라인 섹션으로 정상 분류됨
v2.4 | 2026-09-01 | _sort_key 스코프 버그 수정
      | - mvno_general 비어있을 때 _sort_key 미정의 → mvno_affiliated 정렬 에러
      | - _sort_key를 if 블록 밖으로 이동 (항상 정의되도록)
      | - 발생 조건: 자회사 글은 있고 일반 MVNO 글이 없는 경우
v2.3 | 2026-07-06 | MVNO 섹션 복합정렬 + T다이렉트 묶음 키워드 필터
      | - MVNO일반/자회사 섹션: relevance_score×3000 + views 복합 정렬
      | - T다이렉트 묶음: 정보성(후기/기록/완료 등) 글은 제목 표시, 단순 질문은 건수만
      | - T다이렉트 묶음 기준: 1000 → 2000 이하로 상향
      | - 묶음 안에 제목 목록 표시 (최대 10개, 나머지는 N건 더 있음)
v2.2b | 2026-06-30 | T다이렉트 저조회수 글 텔레그램 묶음요약 처리
      | - T다이렉트만 대상 (너겟/SKT에어는 기존처럼 개별 표시 유지)
      | - 조회수 LOW_VIEW_THRESHOLD(1000) 이하 T다이렉트 글은
      |   개별 블록 대신 "묶음 요약" 1줄로 압축 표시 (텔레그램 메시지만 해당)
      | - raw data 엑셀(Firebase 저장)은 영향 없음 - 모든 글 그대로 저장됨
      | - 1000 초과 T다이렉트 글은 기존처럼 개별 상세 표시 유지
v2.2 | 2026-06-11 | 망 표시 개선 + 자회사/금융 섹션 분리
      | - 단일망 사업자는 점수/별3개 무관하게 항상 망 표시
      | - 제목에서 망 센싱된 경우도 항상 표시
      | - MNO 직영(너겟/T다이렉트/SKT에어)도 망 표시
      | - is_financial 플래그 추가 (토스/리브엠/우리WON 금융계열)
v2.1 | 2026-06-07 | 4섹션 분리 (MVNO / 자회사금융 / MNO직영온라인 / 통신사핫글)
      | - 너겟/T다이렉트/SKT에어 → 📶 MNO 직영 온라인 섹션
      | - 기존 통신사 핫글 → 📡 통신사 핫글 (4번째)
v2.0 | 2026-06-06 | 통신망 제목 룰베이스 추출 + 급등 시 망 재확인 추가
      | - post_block(): extract_network_from_title()로 제목에서 망 즉시 추출
      |   AI 결과보다 제목 추출 우선 적용 (더 신뢰도 높음)
      | - 급등 판정 시: 망 미확인 + score<7 글에 _needs_network_check 플래그
      |   → send_ppomppu_summary에서 플래그 있는 글 망 표시에 "(재확인필요)" 표기
v1.9 | 2026-06-05 | NON_MVNO_BOARDS에 ppomppu/pmarket 추가 (급등 오탐 방지)
v1.8 | 2026-06-02 | 급등 체크 시 NON_MVNO_BOARDS 제외
      | - freeboard/coupon 게시판 글은 급등에서도 제외
v1.7 | 2026-06-02 | 텔레그램 메시지에 통신망 표시 추가
      | - 별3개(7점+): 항상 표시 (미확인 포함)
      | - 별2개 이하: 망 파악된 경우만 표시
v1.6 | 2026-05-21 | community_context 빌더 추가
v1.5 | 2026-03-24 | 7점 이상 ★★★ → ⭐⭐⭐ 강조 (시인성 개선)
v1.4 | 2026-03-20 | 중요도 표시 🔥 → 별표(★) 방식으로 변경 (시인성 개선)
v1.3 | 2026-03-08 | send_telegram source_type 기준 분기 수정 (수동 시 자동결과방 발송 차단)
v1.2 | 2026-03-05 | 채팅방 분리, auto/manual/morning 3모드, 급등감지, 3분류 발송, DB저장 수동제외
v1.1 | 2026-03-03 | SCRAPE_DAYS 환경변수로 날짜 동적 적용 (텔레그램 대화 입력 연동)
v1.0 | 2026-03-01 | 최초 작성 (main.py에서 분리)
──────────────────────────────────────────────────────────────────────────────
"""

import os
import gc
import re
import html
import traceback
import requests
from datetime import datetime
import pytz
from core.mvno_classifier import extract_network_from_title, PROVIDER_NETWORKS, PROVIDER_NETWORKS

KOREA_TZ      = pytz.timezone('Asia/Seoul')

BOT_TOKEN     = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_LOG      = os.getenv('TELEGRAM_CHAT_ID', '')      # 로그방 (진행상황 + 결과)
CHAT_PPOMPPU  = '-1003823332421'                        # 뽐뿌 자동결과방 (auto 시에만)
REQUESTER_ID  = os.getenv('REQUESTER_CHAT_ID', '')     # 요청한 방 (결과만)


def log(msg):
    print(f"[{datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def esc(text) -> str:
    """parse_mode="HTML"로 보내는 메시지에 동적 텍스트(제목/사업자명/요약 등) 끼워넣을 때
    반드시 거쳐야 함. 제목에 &, <, > 있으면 이스케이프 없이는 HTML 파싱 실패로
    메시지 전송이 조용히 실패함."""
    return html.escape(str(text)) if text else ""


def send_to(chat_id, text):
    """특정 채팅방에 발송"""
    if not BOT_TOKEN or not chat_id:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=60
        )
        if r.status_code != 200:
            log(f"⚠️ Telegram 발송 실패 ({chat_id}): {r.status_code}")
    except Exception as e:
        log(f"❌ Telegram 에러: {e}")


def send_log(text):
    """로그방에만 전송 (진행상황)"""
    send_to(CHAT_LOG, text)


def send_telegram(text):
    """로그방 + 요청방 or 자동결과방 전송 (결과)"""
    send_to(CHAT_LOG, text)
    source_type = os.getenv('SCRAPE_SOURCE_TYPE', 'manual')
    requester   = os.getenv('REQUESTER_CHAT_ID', '')
    if source_type == 'manual':
        # 수동 요청 → 요청한 방에만
        if requester and requester != CHAT_LOG:
            send_to(requester, text)
    elif CHAT_PPOMPPU and CHAT_PPOMPPU != CHAT_LOG:
        # auto / morning → 자동결과방
        send_to(CHAT_PPOMPPU, text)


def send_ppomppu_summary(mvno_list, mno_list, days=2, label=""):
    """MVNO 일반 + MVNO 자회사&금융 + MNO 직영 온라인 + 통신사 핫글 4분류 발송"""
    if not mvno_list and not mno_list:
        return

    # MVNO 일반 / 자회사&금융 분리 (mvno_classifier의 is_affiliated 플래그 기준)
    MNO_DIRECT = {"너겟", "T다이렉트", "SKT에어", "요고"}

    mvno_affiliated = [p for p in mvno_list
                       if (p.get('filter_result', {}).get('is_affiliated', False) or
                           p.get('filter_result', {}).get('is_financial', False))
                       and p.get('filter_result', {}).get('provider', '') not in MNO_DIRECT]
    mvno_general    = [p for p in mvno_list
                       if not p.get('filter_result', {}).get('is_affiliated', False)
                       and not p.get('filter_result', {}).get('is_financial', False)
                       and p.get('filter_result', {}).get('provider', '') not in MNO_DIRECT]
    # MNO 직영 온라인 (너겟/T다이렉트/SKT에어) - mvno_list + mno_list 모두에서 추출
    mno_direct      = [p for p in mvno_list + mno_list
                       if p.get('filter_result', {}).get('provider', '') in MNO_DIRECT]
    # mno_list에서 직영 제외한 순수 통신사 핫글
    mno_pure        = [p for p in mno_list
                       if p.get('filter_result', {}).get('provider', '') not in MNO_DIRECT]

    from datetime import timedelta
    now = datetime.now(KOREA_TZ)
    start = now - timedelta(days=days)
    time_range = f"{start.strftime('%-m/%-d %H시')}~{now.strftime('%-m/%-d %H시')}"

    def post_block(post, show_score=True):
        result = post.get('filter_result', {})
        posted_at = post.get('posted_at', datetime.now())
        date_str = posted_at.strftime('%m-%d %H:%M') if hasattr(posted_at, 'strftime') else '날짜 없음'
        provider = result.get('provider', '')
        score = result.get('relevance_score', 0)
        content_summary = result.get('content_summary', '')

        def star_rating(s):
            if s >= 7:   return "⭐⭐⭐"
            elif s >= 4: return "★★☆"
            elif s >= 2: return "★☆☆"
            else:        return "☆☆☆"
        # [v2.2] 통신망 결정 우선순위: 제목센싱 > 단일망확정 > AI결과 > 미확인
        network = extract_network_from_title(post.get('title', '')) or result.get('network') or ''
        if network and network not in ('None', 'null', ''):
            network_str = 'LGU+' if 'LGU' in network or 'U+' in network else network
        else:
            # 단일망 사업자 → PROVIDER_NETWORKS로 확정
            candidates = PROVIDER_NETWORKS.get(provider, [])
            network_str = candidates[0] if len(candidates) == 1 else '미확인'

        # 제목센싱 or 단일망 확정 → 점수 무관 항상 표시
        title_network = extract_network_from_title(post.get('title', ''))
        single_network = len(PROVIDER_NETWORKS.get(provider, [])) == 1
        show_network_always = bool(title_network) or single_network

        score_str = f"{star_rating(score)} 중요도: {score}/10 | " if show_score else ""
        block = f"{'─'*30}\n"
        block += f"{score_str}📅 {date_str}\n"
        if provider and provider not in ('None', '통신사'):
            block += f" 📱 {esc(provider)}\n"
        # [v2.6] 제목을 URL 하이퍼링크로 바꿔서 본문 아래 별도 URL 줄 제거 -
        # 특히 모바일에서 긴 URL이 2~3줄 차지해서 메시지가 쓸데없이 길어지던 문제
        block += f" 📝 <a href='{esc(post['url'])}'>{esc(post['title'])}</a>\n"
        if content_summary:
            block += f" 본문: {esc(content_summary)}\n"
        # [v2.2] 통신망 표시: 제목센싱/단일망/별3개 → 항상, 나머지 → 확정시만
        needs_check = post.get('_needs_network_check', False)
        if show_network_always or score >= 7:
            net_display = f"{network_str} ⚠️재확인필요" if needs_check and network_str == '미확인' else network_str
            block += f" 🌐 통신망: {esc(net_display)}\n"
        elif network_str != '미확인':
            block += f" 🌐 통신망: {esc(network_str)}\n"
        elif needs_check:
            block += f" 🌐 통신망: 미확인 ⚠️재확인필요\n"
        block += f" 👁 {post.get('views', 0):,} | 💬 {post.get('comments', 0)}"
        return block

    def send_chunked(header, blocks, max_len=3800):
        current = header
        for block in blocks:
            if len(current) + len(block) + 2 > max_len:
                send_telegram(current)
                current = block + "\n\n"
            else:
                current += block + "\n\n"
        if current.strip():
            send_telegram(current)

    # [bugfix] _sort_key를 if 블록 밖으로 이동
    # mvno_general이 비어있으면 _sort_key 미정의 → mvno_affiliated 정렬 시 에러
    def _sort_key(p):
        score = p.get('filter_result', {}).get('relevance_score', 0)
        views = p.get('views', 0)
        return score * 3000 + views

    if mvno_general:
        mvno_general_sorted = sorted(mvno_general, key=_sort_key, reverse=True)
        header = f"🔔 <b>뽐뿌 MVNO {label} ({len(mvno_general_sorted)}개)</b>\n{time_range}\n\n"
        send_chunked(header, [post_block(p, show_score=True) for p in mvno_general_sorted])

    if mvno_affiliated:
        # [v2.3] 복합 정렬 동일 적용
        mvno_affiliated_sorted = sorted(mvno_affiliated, key=_sort_key, reverse=True)
        header = f"🏢 <b>뽐뿌 MVNO 자회사&금융 {label} ({len(mvno_affiliated_sorted)}개)</b>\n{time_range}\n\n"
        send_chunked(header, [post_block(p, show_score=True) for p in mvno_affiliated_sorted])

    if mno_direct:
        # [v2.2] 기준 2000으로 상향
        LOW_VIEW_THRESHOLD = 2000
        TDIRECT_PROVIDER = "T다이렉트"
        header = f"📶 <b>MNO 직영 온라인 {label} ({len(mno_direct)}개)</b>\n{time_range}\n\n"

        # T다이렉트만 저조회수 묶음 처리 (너겟/SKT에어는 기존처럼 개별 표시)
        tdirect_low  = [p for p in mno_direct
                        if p.get('filter_result', {}).get('provider', '') == TDIRECT_PROVIDER
                        and p.get('views', 0) <= LOW_VIEW_THRESHOLD]
        # 조회수 내림차순 정렬
        tdirect_low  = sorted(tdirect_low, key=lambda p: p.get('views', 0), reverse=True)
        normal_posts = [p for p in mno_direct if p not in tdirect_low]
        normal_posts = sorted(normal_posts, key=lambda p: p.get('views', 0), reverse=True)

        blocks = [post_block(p, show_score=True) for p in normal_posts]

        if tdirect_low:
            total_views = sum(p.get('views', 0) for p in tdirect_low)
            total_comments = sum(p.get('comments', 0) for p in tdirect_low)

            # [v2.3] 키워드 기반 정보성 글 분리
            # 정보성: 후기/기록/완료/공유/정리/탑승/졸업 등 → 제목 표시
            # 단순질문: 문의/가능한가요/어떤가요 등 → 건수만 집계
            INFO_KW = ["기록", "후기", "완료", "공유", "정리", "탑승", "졸업",
                       "받았", "왔네", "됐네", "했네", "합니다", "했어요",
                       "구매기", "개통기", "사용기", "체험기", "안내",
                       "날렸", "했습", "샀", "구입", "주문", "도착", "배송",
                       "탔습", "개통했", "신청했", "결제했"]
            SKIP_KW = ["문의", "질문", "가능한가요", "어떤가요", "될까요",
                       "맞나요", "있나요", "어떻게", "인가요", "할까요",
                       "되나요", "건가요", "드려요", "부탁드"]

            info_posts = []
            skip_count = 0
            for p in tdirect_low:
                title = p.get('title', '')
                is_info = any(kw in title for kw in INFO_KW)
                is_skip = any(kw in title for kw in SKIP_KW)
                if is_info and not is_skip:
                    info_posts.append(p)
                else:
                    skip_count += 1

            title_lines = ""
            if info_posts:
                title_lines += "📌 주요글\n"
                for p in info_posts[:8]:
                    title_lines += f"  👁{p.get('views',0):,} <a href='{esc(p.get('url',''))}'>{esc(p['title'][:35])}</a>\n"
            if skip_count > 0:
                title_lines += f"  단순문의 {skip_count}건 생략"

            summary_block = (
                f"{'─'*30}\n"
                f"📦 {TDIRECT_PROVIDER} {len(tdirect_low)}건 묶음 "
                f"(조회수 {LOW_VIEW_THRESHOLD:,} 이하)\n"
                f" 총 👁 {total_views:,} · 💬 {total_comments}\n"
                + title_lines.rstrip()
            )
            blocks.append(summary_block)

        send_chunked(header, blocks)

    if mno_pure:
        header = f"📡 <b>통신사 핫글 {label} ({len(mno_pure)}개)</b>\n{time_range}\n\n"
        send_chunked(header, [post_block(p, show_score=False) for p in mno_pure])


def save_community_context(mvno_posts, source="ppomppu", date_str=None):
    try:
        from google.cloud import firestore as _fs
        import firebase_admin
        from firebase_admin import credentials as _cred
        from datetime import datetime, timezone, timedelta
        _KST = timezone(timedelta(hours=9))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(_cred.ApplicationDefault())
        _db = _fs.Client(project="mvno-484509", database="mvno-data")
        _now = datetime.now(_KST)
        date_str = date_str or _now.strftime("%Y-%m-%d")
        hour_key = _now.strftime("%H")
        checked  = _now.strftime("%m/%d %H:%M")
        SEP = chr(9473) * 28
        target = [p for p in mvno_posts
                  if not p.get("filter_result", {}).get("is_mno_high_traffic", False)]
        target.sort(key=lambda p: p.get("filter_result", {}).get("relevance_score", 0), reverse=True)
        top3 = target[:3]
        hot  = [p for p in target if p.get("filter_result", {}).get("relevance_score", 0) >= 7]
        high_t = [p for p in target if p.get("views", 0) >= 10000
                  or p.get("filter_result", {}).get("high_traffic_boost", False)]
        alerts, normals = [], []
        if hot:
            titles = " / ".join(p["title"][:20] + "..." for p in hot[:2])
            alerts.append("고중요도 게시글 " + str(len(hot)) + "개 -- " + titles)
        else:
            normals.append("고중요도 게시글 없음 -- 평이한 동향")
        if high_t:
            alerts.append("고조회수 게시글 " + str(len(high_t)) + "개")
        normals.append("MVNO 관련 게시글 총 " + str(len(target)) + "개 수집")
        prov_count = {}
        for p in target:
            pv = p.get("filter_result", {}).get("provider", "")
            if pv and pv not in ("None", "", "통신사"):
                prov_count[pv] = prov_count.get(pv, 0) + 1
        L = []
        L.append("[MVNO 커뮤니티 AI컨텍스트 | " + date_str + " | " + checked + " 뽐뿌 기준]")
        L.append("※ 커뮤니티 반응 데이터. 재계산 금지. 해석만 할 것.")
        L.append("")
        L.append(SEP)
        L.append("■ SUMMARY (AI 해석 우선순위)")
        L.append(SEP)
        for a in alerts:  L.append("  ALERT: " + a)
        for n in normals: L.append("  NORMAL: " + n)
        L.append("※ 상세 내용은 하단 각 섹션 참조")
        L.append("")
        L.append(SEP)
        L.append("■ 1. 주요 게시글 Top 3 [뽐뿌]")
        L.append(SEP)
        if top3:
            for i, p in enumerate(top3, 1):
                res   = p.get("filter_result", {})
                score = res.get("relevance_score", 0)
                stars = "3star" if score >= 7 else ("2star" if score >= 4 else "1star")
                prov  = res.get("provider", "")
                summ  = res.get("content_summary", "")
                posted = p.get("posted_at", _now)
                dlabel = posted.strftime("%m/%d %H:%M") if hasattr(posted, "strftime") else ""
                L.append("[" + str(i) + "] " + stars + " 중요도 " + str(score) + "/10 | " + dlabel)
                if prov and prov not in ("None", "통신사"):
                    L.append("  사업자: " + prov)
                L.append("  제목: " + p.get("title", ""))
                if summ: L.append("  요약: " + summ)
                L.append("  조회 " + str(p.get("views", 0)) + " | 댓글 " + str(p.get("comments", 0)))
                L.append("  URL: " + p.get("url", ""))
                if i < len(top3): L.append("")
        else:
            L.append("해당 없음")
        L.append("")
        L.append(SEP)
        L.append("■ 2. 사업자별 언급 현황")
        L.append(SEP)
        if prov_count:
            for pv, cnt in sorted(prov_count.items(), key=lambda x: -x[1]):
                L.append("  " + pv + ": " + str(cnt) + "건")
        else:
            L.append("  사업자 특정 게시글 없음")
        L.append("")
        L.append(SEP)
        L.append("■ 3. 수집 현황")
        L.append(SEP)
        L.append("전체: " + str(len(mvno_posts)) + "개 (MVNO " + str(len(target)) + "개 / MNO핫글 " + str(len(mvno_posts)-len(target)) + "개)")
        L.append("고중요도: " + str(len(hot)) + "개 / 고조회수(10k+): " + str(len(high_t)) + "개")
        new_text = chr(10).join(L)
        doc_ref  = _db.collection("community_context").document(date_str)
        existing = doc_ref.get()
        ex_dict  = existing.to_dict() if existing.exists else {}

        # 시간대별 merge: text_ppomppu_08 / text_ppomppu_11 / ...
        time_field = "text_ppomppu_" + hour_key
        ex_dict[time_field] = new_text
        ex_dict["date"]     = date_str
        ex_dict["saved_at"] = _now
        ex_dict["version"]  = "v1.0"

        # 최종 text = 뽐뿌 전 시간대 합산 + 디씨
        ppomppu_keys = sorted([k for k in ex_dict if k.startswith("text_ppomppu_")])
        ppomppu_parts = [ex_dict[k] for k in ppomppu_keys if ex_dict.get(k)]
        ppomppu_merged = (chr(10)*2 + "── " + chr(10)*2).join(ppomppu_parts)
        if ppomppu_merged:
            ex_dict["text_ppomppu"] = ppomppu_merged  # 합산본도 저장

        all_parts = []
        if ppomppu_merged: all_parts.append(ppomppu_merged)
        if ex_dict.get("text_dcinside"): all_parts.append(ex_dict["text_dcinside"])
        ex_dict["text"] = (chr(10)*2 + chr(9473)*28 + chr(10)*2).join(all_parts)

        doc_ref.set(ex_dict)
        log("community_context merge 저장: " + date_str + " / ppomppu_" + hour_key + " (" + str(len(new_text)) + "자)")
    except Exception as e:
        log("community_context 저장 실패: " + str(e))
        import traceback as _tb; log(_tb.format_exc()[-300:])


def main():
    log("🚀 뽐뿌 Job 시작")
    send_log("🔍 뽐뿌 MVNO 모니터링 시작...")

    try:
        from scrapers.ppomppu_scraper import PpomppuScraper, filter_mvno_posts, filter_new_posts
        from core.firebase_handler import FirebaseHandler

        # Step 1: 크롤링 (1일치)
        def progress_callback(msg):
            if "페이지 완료" in msg:
                match = re.search(r'(\d+)페이지', msg)
                if match and int(match.group(1)) % 10 == 0:
                    send_log(f"📊 {msg}")

        scraper = PpomppuScraper(progress_callback=progress_callback)
        days = float(os.getenv('SCRAPE_DAYS', '2'))
        all_posts = scraper.scrape(days=days)
        del scraper
        gc.collect()

        send_log(f"✅ 수집 완료: {len(all_posts)}개")

        if not all_posts:
            send_log("⚠️ 수집된 게시글 없음")
            return

        # Step 2: Firebase 초기화
        firebase = FirebaseHandler()
        source_type = os.getenv('SCRAPE_SOURCE_TYPE', 'manual')

        # Step 3: 기존 글 조회
        # auto/morning: Firebase 기존 글 비교, manual: 비교 안 함
        if source_type in ('auto', 'morning'):
            existing_posts = firebase.get_existing_ppomppu_posts(limit=5000)
            existing_ids   = set(existing_posts.keys())
            send_log(f"📊 전체 {len(all_posts)}개 수집 (기존 {len(existing_ids)}개 비교)")
        else:
            existing_posts = {}
            existing_ids   = set()
            send_log(f"📊 분석 대상: {len(all_posts)}개 (manual - 시간기준 전체)")

        new_posts = all_posts
        del all_posts
        gc.collect()

        # Step 4: MVNO 필터링 (전체 분석)
        send_log(f"🤖 AI 분석 시작 ({len(new_posts)}개)...")
        mvno_posts = filter_mvno_posts(
            new_posts,
            use_ai=True,
            top_n=None,
            progress_telegram=send_log
        )
        del new_posts
        gc.collect()

        if not mvno_posts:
            send_telegram("✅ MVNO 관련 게시글 없음")
            return

        # Step 5: 신규 / 급등 / 일반 분류
        SURGE_VIEWS    = 5000  # 조회수 급증 기준
        SURGE_COMMENTS = 5     # 댓글 급증 기준

        new_mvno   = []
        surge_mvno = []
        new_mno    = []
        surge_mno  = []

        for post in mvno_posts:
            pid    = post.get('post_id') or post.get('id', '')
            is_mno = post.get('filter_result', {}).get('is_mno_high_traffic', False)
            is_new = pid not in existing_ids

            if is_new:
                (new_mno if is_mno else new_mvno).append(post)
            elif source_type == 'auto':
                # 비MVNO 게시판은 급등에서도 제외
                NON_MVNO_BOARDS = {'freeboard', 'coupon', 'computer', 'issue', 'ppomppu', 'ppomppu2', 'pmarket', 'pmarket2', 'pmarket3'}
                if post.get('board') in NON_MVNO_BOARDS:
                    continue
                prev       = existing_posts.get(pid, {})
                view_diff  = post.get('views', 0)    - prev.get('views', 0)
                cmt_diff   = post.get('comments', 0) - prev.get('comments', 0)
                if view_diff >= SURGE_VIEWS or cmt_diff >= SURGE_COMMENTS:
                    post['_surge'] = {'views_diff': view_diff, 'comments_diff': cmt_diff}
                    # 급등 승격 시 망 미확인 글 → 재확인 플래그
                    fr = post.get('filter_result', {})
                    title_network = extract_network_from_title(post.get('title', ''))
                    if not title_network and not fr.get('network') and fr.get('relevance_score', 0) < 7:
                        post['_needs_network_check'] = True
                    (surge_mno if is_mno else surge_mvno).append(post)

        new_mno.sort(key=lambda p: p.get('views', 0), reverse=True)
        surge_mno.sort(key=lambda p: p.get('views', 0), reverse=True)

        # Step 6: Firebase 저장 (auto/morning만 저장, manual은 저장 안 함)
        saved_count = 0
        if source_type in ('auto', 'morning'):
            for post in (new_mvno + new_mno):
                if firebase.save_ppomppu_post(post):
                    saved_count += 1
            for post in (surge_mvno + surge_mno):
                firebase.save_ppomppu_post(post)  # 조회수/댓글 업데이트
            send_log(
                f"💾 신규저장 {saved_count}개 | "
                f"급등: MVNO {len(surge_mvno)}개 + MNO {len(surge_mno)}개"
            )
        else:
            send_log("💾 수동 요청 - DB 저장 생략")

        # Step 7: Telegram 알림
        if source_type in ('manual', 'morning'):
            # 수동/모닝: 전체 결과 발송
            all_mvno = [p for p in mvno_posts if not p.get('filter_result', {}).get('is_mno_high_traffic')]
            all_mno  = [p for p in mvno_posts if p.get('filter_result', {}).get('is_mno_high_traffic')]
            all_mno.sort(key=lambda p: p.get('views', 0), reverse=True)
            if all_mvno or all_mno:
                send_ppomppu_summary(all_mvno, all_mno, days=days, label="")
            else:
                send_telegram("✅ MVNO 관련 게시글 없음")
        else:
            # auto: 신규 + 급등만 알림
            if new_mvno or new_mno:
                send_ppomppu_summary(new_mvno, new_mno, days=days, label="🆕 신규")
            if surge_mvno or surge_mno:
                send_ppomppu_summary(surge_mvno, surge_mno, days=days, label="🔺 급등")
            if not (new_mvno or new_mno or surge_mvno or surge_mno):
                send_telegram("✅ 신규/급등 게시글 없음")

        # 완료 메시지는 로그방에만
        send_log(
            f"✅ 뽐뿌 모니터링 완료\n\n"
            f"🆕 신규: MVNO {len(new_mvno)}개 + MNO {len(new_mno)}개\n"
            f"🔺 급등: MVNO {len(surge_mvno)}개 + MNO {len(surge_mno)}개\n"
            f"💾 저장: {saved_count}개"
        )
        log("✅ 뽐뿌 Job 정상 완료")

        # Step 8: community_context 저장 (auto/morning만)
        if source_type in ("auto", "morning"):
            save_community_context(mvno_posts, source="ppomppu")

    except Exception as e:
        error_msg = f"❌ 뽐뿌 Job 에러: {e}"
        log(error_msg)
        log(traceback.format_exc())
        send_telegram(error_msg)
        raise  # Job 실패로 표시되도록 re-raise


if __name__ == '__main__':
    main()