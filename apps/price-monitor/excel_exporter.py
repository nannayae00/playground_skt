"""
excel_exporter.py
──────────────────────────────────────────────────────────────────────────────
텔레그램 "엑셀 확인" 명령어 처리 모듈
- Firebase에서 뽐뿌/디씨인사이드/유튜브 데이터 조회
- 4개 Sheet 엑셀 파일 생성 후 텔레그램 전송

[수정 이력]
v1.0 | 2026-04-13 | 최초 작성
v1.1 | 2026-04-13 | 수정1: 뽐뿌 content_summary에서 망 정보 정규식 추출
v1.2 | 2026-06-02 | _NETWORK_PATTERNS에 URL 패턴 추가 (uplusmvno.com, sktmvno.com 등)
                  | 수정2: 유튜브 Sheet1 - search_keyword 없는 영상 제외
                  | 수정3: 디씨 Firestore order_by direction 상수 오류 수정
v1.2 | 2026-04-15 | 이슈1: 망 패턴 확장 (유플러스망, sk망 등 비표준 표현 추가)
                  | 이슈2: 디씨 order_by 완전 제거 → Python 필터/정렬로 대체
                  | 이슈3: 유튜브 fetch 단계에서 search_keyword 없는 영상 제외
                  |        (Sheet1 + Sheet4 동시 해결)
v1.3 | 2026-04-23 | 유튜브 video_id 기준 중복 제거
                  | 유튜브 화이트리스트 확인 (커뮤니티 동향 등 무관 키워드 자동 제외)
──────────────────────────────────────────────────────────────────────────────
"""

import os
import io
import requests
from datetime import datetime, timedelta
import pytz

KOREA_TZ = pytz.timezone('Asia/Seoul')

import re

# 망 정보 추출 패턴 (비표준 표현 포함)
_NETWORK_PATTERNS = [
    (re.compile(
        r'SKT\s*망|SK\s*텔레콤\s*망|에스케이\s*망|sk망|SK망|스케이망'
        r'|sktmvno\.com|sktelink\.com',
        re.I), 'SKT'),
    (re.compile(
        r'KT\s*망|케이티\s*망|kt망'
        r'|ktmvno\.com|mvno\.kt\.com',
        re.I), 'KT'),
    (re.compile(
        r'LGU\+\s*망|LG\s*유플\s*망|유플러스\s*망|유플\s*망|엘지\s*망|U\+\s*망'
        r'|lgu\+망|lg망|LG망|유플망|유플러스망'
        r'|uplusmvno\.com|uplus\.co\.kr',
        re.I), 'LGU+'),
]

def _extract_network(text):
    """텍스트에서 통신망 정보 추출 (SKT/KT/LGU+)"""
    if not text:
        return ''
    for pattern, network in _NETWORK_PATTERNS:
        if pattern.search(text):
            return network
    return ''


# ── 별점 변환 ─────────────────────────────────────────────────────────────────
def star_rating(score):
    score = int(score) if score else 0
    if score >= 7:   return "⭐⭐⭐"
    elif score >= 4: return "★★☆"
    elif score >= 2: return "★☆☆"
    else:            return "☆☆☆"


# ── Firebase 데이터 조회 ──────────────────────────────────────────────────────
def fetch_ppomppu_posts(db, days=30, limit=500):
    """뽐뿌 전체 게시글 조회 (최근 N일)"""
    try:
        from google.cloud.firestore_v1 import Query
        cutoff = datetime.now(KOREA_TZ) - timedelta(days=days)
        try:
            docs = db.collection('ppomppu_monitor') \
                .document('posts').collection('all_posts') \
                .order_by('posted_at', direction=Query.DESCENDING) \
                .limit(limit).stream()
        except Exception:
            docs = db.collection('ppomppu_monitor') \
                .document('posts').collection('all_posts') \
                .limit(limit).stream()

        posts = []
        for doc in docs:
            d = doc.to_dict()
            posted_at = d.get('posted_at')
            if posted_at and hasattr(posted_at, 'tzinfo'):
                if posted_at.tzinfo is None:
                    posted_at = KOREA_TZ.localize(posted_at)
                if posted_at < cutoff:
                    continue
            posts.append(d)

        posts.sort(key=lambda x: str(x.get('posted_at', '')), reverse=True)
        print(f"✅ 뽐뿌 조회: {len(posts)}개")
        return posts
    except Exception as e:
        print(f"❌ 뽐뿌 조회 실패: {e}")
        return []


def fetch_dcinside_posts(db, days=30, limit=1000):
    """디씨인사이드 전체 게시글 조회 (최근 N일)"""
    try:
        from google.cloud.firestore_v1 import Query
        cutoff = datetime.now(KOREA_TZ) - timedelta(days=days)

        # [v1.4] order_by 없이 limit()만 걸면 컬렉션이 limit 이상으로 커졌을 때
        # Firestore가 임의 순서(대략 문서ID순)로 반환 → 최신글이 안 걸려서 0건이 되는
        # 버그 확인됨 (dcinside_monitor: 전체 58,683건, order_by 없인 앞쪽 1000건이
        # 죄다 옛날 글). 뽐뿌와 동일하게 order_by(내림차순) + limit, 실패 시 fallback.
        try:
            docs = db.collection('dcinside_monitor') \
                .document('posts').collection('all_posts') \
                .order_by('posted_at', direction=Query.DESCENDING) \
                .limit(limit).stream()
        except Exception:
            docs = db.collection('dcinside_monitor') \
                .document('posts').collection('all_posts') \
                .limit(limit).stream()

        posts = []
        for doc in docs:
            d = doc.to_dict()
            posted_at = d.get('posted_at')
            if posted_at and hasattr(posted_at, 'tzinfo'):
                if posted_at.tzinfo is None:
                    posted_at = KOREA_TZ.localize(posted_at)
                if posted_at < cutoff:
                    continue
            posts.append(d)

        # Python 정렬 (posted_at 내림차순)
        def sort_key(x):
            pa = x.get('posted_at')
            if pa and hasattr(pa, 'timestamp'):
                return pa.timestamp()
            return 0
        posts.sort(key=sort_key, reverse=True)
        print(f"✅ 디씨 조회: {len(posts)}개")
        return posts
    except Exception as e:
        print(f"❌ 디씨 조회 실패: {e}")
        return []


def fetch_youtube_videos(db, days=30, limit=200):
    """
    유튜브 영상 조회 (최근 N일)

    컬렉션: youtube_analyses
    문서 구조:
      video_id: str
      video_info:
        channel: str
        title: str
        url: str
        view_count: int
        published_at: str  (예: "2026-04-06")
        search_keyword: str
        like_count: int
        comment_count: int
        description: str
      categories: list[str]
      lines: list[str]      # 요약 라인
    """
    # 유튜브 봇 수집 키워드 화이트리스트
    YOUTUBE_KEYWORDS = {'알뜰폰', 'MVNO 유심', '유심 요금제'}

    COLLECTION_NAME = 'youtube_analyses'
    cutoff = datetime.now(KOREA_TZ) - timedelta(days=days)
    cutoff_date = cutoff.date()

    try:
        # [v1.4] dcinside와 동일한 구조적 버그(순서 없는 limit) 방지 차원에서
        # published_at 내림차순 order_by 추가, 실패 시 fallback
        try:
            from google.cloud.firestore_v1 import Query
            all_docs = db.collection(COLLECTION_NAME) \
                .order_by('video_info.published_at', direction=Query.DESCENDING) \
                .limit(limit).stream()
        except Exception:
            all_docs = db.collection(COLLECTION_NAME).limit(limit).stream()

        videos = []
        seen_video_ids = set()  # 중복 제거용

        for doc in all_docs:
            d = doc.to_dict()
            info = d.get('video_info', {})

            # published_at은 "2026-04-06" 문자열 형식
            published_at_raw = info.get('published_at', '')
            try:
                pub_date = datetime.strptime(published_at_raw, '%Y-%m-%d').date()
                if pub_date < cutoff_date:
                    continue
            except Exception:
                pass  # 날짜 파싱 실패 시 포함

            # search_keyword가 수집 키워드 화이트리스트에 없으면 제외
            keyword = info.get('search_keyword', '') or ''
            if keyword.strip() not in YOUTUBE_KEYWORDS:
                continue

            # video_id 기준 중복 제거
            video_id = d.get('video_id') or info.get('video_id', '')
            if video_id and video_id in seen_video_ids:
                continue
            if video_id:
                seen_video_ids.add(video_id)

            # lines 배열을 요약 텍스트로 합치기 (요약 생성 실패 제외)
            lines = d.get('lines', [])
            summary = ' | '.join(l for l in lines if l and l != '요약 생성 실패')

            videos.append({
                'channel':        info.get('channel', ''),
                'title':          info.get('title', ''),
                'url':            info.get('url', ''),
                'view_count':     info.get('view_count', 0),
                'like_count':     info.get('like_count', 0),
                'comment_count':  info.get('comment_count', 0),
                'published_at':   published_at_raw,
                'search_keyword': keyword,
                'categories':     ', '.join(d.get('categories', [])),
                'summary':        summary,
            })

        # published_at 내림차순 정렬
        videos.sort(key=lambda v: v.get('published_at', ''), reverse=True)
        print(f"✅ 유튜브 조회 ({COLLECTION_NAME}): {len(videos)}개")
        return videos

    except Exception as e:
        print(f"❌ 유튜브 조회 실패: {e}")
        return []


# ── 엑셀 생성 ─────────────────────────────────────────────────────────────────
def build_excel(ppomppu_posts, dcinside_posts, youtube_videos):
    """
    4개 Sheet 엑셀 생성 → bytes 반환

    Sheet1: 요금 주요 이슈 (뽐뿌 조회수 1만↑ OR relevance_score 7↑)
    Sheet2: 뽐뿌 전체
    Sheet3: 디씨갤 전체
    Sheet4: 유튜브
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ImportError("openpyxl 설치 필요: pip install openpyxl")

    wb = openpyxl.Workbook()

    # ── 스타일 정의 ────────────────────────────────────────────────────────
    # 헤더 스타일
    HEADER_FILL_BLUE   = PatternFill("solid", fgColor="1F4E79")   # Sheet1 (진파랑)
    HEADER_FILL_ORANGE = PatternFill("solid", fgColor="C55A11")   # Sheet2 (주황)
    HEADER_FILL_GREEN  = PatternFill("solid", fgColor="375623")   # Sheet3 (녹색)
    HEADER_FILL_PURPLE = PatternFill("solid", fgColor="4B1E75")   # Sheet4 (보라)
    HEADER_FONT        = Font(name='맑은 고딕', bold=True, color="FFFFFF", size=10)
    CELL_FONT          = Font(name='맑은 고딕', size=9)
    CELL_FONT_BOLD     = Font(name='맑은 고딕', bold=True, size=9)

    # 별점별 배경색
    FILL_3STAR = PatternFill("solid", fgColor="FFF2CC")  # 노랑 (⭐⭐⭐)
    FILL_2STAR = PatternFill("solid", fgColor="DDEEFF")  # 연파랑
    FILL_WHITE = PatternFill("solid", fgColor="FFFFFF")

    # 셀 테두리
    thin = Side(style='thin', color='BFBFBF')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
    LEFT   = Alignment(horizontal='left',   vertical='center', wrap_text=True)

    def style_header_row(ws, row_num, fill):
        for cell in ws[row_num]:
            if cell.value is not None:
                cell.fill   = fill
                cell.font   = HEADER_FONT
                cell.border = border
                cell.alignment = CENTER

    def style_data_row(ws, row_num, row_fill=None):
        for cell in ws[row_num]:
            cell.font      = CELL_FONT
            cell.border    = border
            cell.alignment = LEFT
            if row_fill:
                cell.fill = row_fill

    def fmt_date(dt):
        if dt is None:
            return ''
        if hasattr(dt, 'strftime'):
            if hasattr(dt, 'tzinfo') and dt.tzinfo:
                dt = dt.astimezone(KOREA_TZ)
            return dt.strftime('%m-%d %H:%M')
        return str(dt)

    def fmt_views(v):
        try:
            return int(v)
        except:
            return 0

    # ── Sheet1: 주요 이슈 요약 (3개 소스 통합) ───────────────────────────
    ws1 = wb.active
    ws1.title = "주요 이슈 요약"

    # 출처별 배경색
    FILL_PPOMPPU  = PatternFill("solid", fgColor="FFF2CC")  # 노랑 (뽐뿌)
    FILL_DC       = PatternFill("solid", fgColor="E2EFDA")  # 연초록 (디씨)
    FILL_YOUTUBE  = PatternFill("solid", fgColor="F0E6FF")  # 연보라 (유튜브)

    headers1 = ["일자", "출처", "제목", "주요내용", "사업자", "통신망", "클러스터/키워드", "반응(조회/댓글)", "링크"]
    col_widths1 = [10, 8, 38, 45, 12, 8, 18, 14, 45]

    ws1.append(headers1)
    style_header_row(ws1, 1, HEADER_FILL_BLUE)

    summary_rows = []  # (date_sort_key, row_data, fill)

    # ① 뽐뿌: 조회수 1만↑ OR relevance_score 7↑
    for p in ppomppu_posts:
        if fmt_views(p.get('views', 0)) >= 10000 or int(p.get('relevance_score', 0) or 0) >= 7:
            posted_at = p.get('posted_at')
            date_str  = fmt_date(posted_at)
            views     = fmt_views(p.get('views', 0))
            comments  = int(p.get('comments', 0) or 0)
            score     = int(p.get('relevance_score', 0) or 0)

            # network: Firestore 저장값 우선 → 없으면 텍스트 정규식 추출 fallback
            network = p.get('network') or _extract_network(
                (p.get('content_summary', '') or '') + ' ' + (p.get('title', '') or '')
            )

            summary_rows.append((
                posted_at or '',
                [
                    date_str,
                    f"뽐뿌 {star_rating(score)}",
                    p.get('title', ''),
                    p.get('content_summary', ''),
                    p.get('provider', ''),
                    network,
                    '',
                    f"👁 {views:,} / 💬 {comments}",
                    p.get('url', ''),
                ],
                FILL_PPOMPPU
            ))

    # ② 디씨: topic 필드가 있는 것 (클러스터 top3 글)
    # topic이 비어있지 않은 글 = 클러스터링 시 top3으로 선정된 글
    dc_top = [p for p in dcinside_posts if p.get('topic', '').strip()]
    # 클러스터(topic)별로 조회수 상위 1개만 대표로 올리기
    seen_topics = {}
    for p in sorted(dc_top, key=lambda x: fmt_views(x.get('views', 0)), reverse=True):
        topic = p.get('topic', '').strip()
        if topic not in seen_topics:
            seen_topics[topic] = p

    for topic, p in seen_topics.items():
        posted_at = p.get('posted_at')
        date_str  = fmt_date(posted_at)
        views     = fmt_views(p.get('views', 0))
        comments  = int(p.get('comments', 0) or 0)
        sentiment = p.get('sentiment', '중립') or '중립'
        sentiment_icon = {'불만': '😡', '긍정': '👍', '문의': '❓', '중립': '😐'}.get(sentiment, '')
        summary_rows.append((
            posted_at or '',
            [
                date_str,
                f"디씨 {sentiment_icon}",
                p.get('title', ''),
                '',   # 디씨는 content_summary 없음
                p.get('provider', ''),
                p.get('network', ''),
                topic,
                f"👁 {views:,} / 💬 {comments}",
                p.get('url', ''),
            ],
            FILL_DC
        ))

    # ③ 유튜브: view_count 5000↑ + search_keyword 있는 것만 (알뜰폰 관련 영상)
    for v in youtube_videos:
        if fmt_views(v.get('view_count', 0)) >= 5000 and v.get('search_keyword', ''):
            pub      = v.get('published_at', '')
            views    = fmt_views(v.get('view_count', 0))
            likes    = fmt_views(v.get('like_count', 0))
            summary_rows.append((
                pub,
                [
                    pub,
                    '유튜브 ▶',
                    v.get('title', ''),
                    v.get('summary', ''),
                    '',
                    '',
                    v.get('search_keyword', ''),
                    f"👁 {views:,} / 👍 {likes}",
                    v.get('url', ''),
                ],
                FILL_YOUTUBE
            ))

    # 날짜 내림차순 정렬
    summary_rows.sort(key=lambda x: str(x[0]), reverse=True)

    for _, row_data, fill in summary_rows:
        ws1.append(row_data)
        style_data_row(ws1, ws1.max_row, fill)

    # 링크 컬럼 (9번째) 하이퍼링크
    for row in ws1.iter_rows(min_row=2, min_col=9, max_col=9):
        for cell in row:
            if cell.value and str(cell.value).startswith('http'):
                cell.hyperlink = cell.value
                cell.font = Font(name='맑은 고딕', size=9, color='0563C1', underline='single')

    for i, w in enumerate(col_widths1, 1):
        ws1.column_dimensions[get_column_letter(i)].width = w
    ws1.row_dimensions[1].height = 20
    ws1.freeze_panes = 'A2'

    # ── Sheet2: 뽐뿌 전체 ────────────────────────────────────────────────
    ws2 = wb.create_sheet("뽐뿌 전체")
    headers2 = ["별점", "제목", "사업자", "통신망", "조회수", "댓글", "날짜", "주요내용", "링크"]
    col_widths2 = [8, 40, 12, 8, 8, 6, 12, 50, 45]

    ws2.append(headers2)
    style_header_row(ws2, 1, HEADER_FILL_ORANGE)

    ppomppu_sorted = sorted(ppomppu_posts,
        key=lambda p: int(p.get('relevance_score', 0) or 0), reverse=True)

    for p in ppomppu_sorted:
        score = int(p.get('relevance_score', 0) or 0)
        star  = star_rating(score)
        fill  = FILL_3STAR if score >= 7 else FILL_WHITE
        # network: Firestore 저장값 우선 → 없으면 텍스트 정규식 fallback
        network2 = p.get('network') or _extract_network(
            (p.get('content_summary', '') or '') + ' ' + (p.get('title', '') or '')
        )
        row = [
            star,
            p.get('title', ''),
            p.get('provider', ''),
            network2,
            fmt_views(p.get('views', 0)),
            int(p.get('comments', 0) or 0),
            fmt_date(p.get('posted_at')),
            p.get('content_summary', ''),
            p.get('url', ''),
        ]
        ws2.append(row)
        style_data_row(ws2, ws2.max_row, fill)
        ws2.cell(ws2.max_row, 1).alignment = CENTER

    for row in ws2.iter_rows(min_row=2, min_col=9, max_col=9):
        for cell in row:
            if cell.value and cell.value.startswith('http'):
                cell.hyperlink = cell.value
                cell.font = Font(name='맑은 고딕', size=9, color='0563C1', underline='single')

    for i, w in enumerate(col_widths2, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.row_dimensions[1].height = 20
    ws2.freeze_panes = 'A2'

    # ── Sheet3: 디씨갤 전체 ───────────────────────────────────────────────
    ws3 = wb.create_sheet("디씨갤 전체")
    headers3 = ["사업자", "망", "제목", "조회수", "댓글", "날짜", "sentiment", "클러스터", "링크"]
    col_widths3 = [12, 10, 40, 8, 6, 12, 8, 20, 45]

    ws3.append(headers3)
    style_header_row(ws3, 1, HEADER_FILL_GREEN)

    # sentiment별 배경색
    SENTIMENT_FILLS = {
        '불만': PatternFill("solid", fgColor="FFD7D7"),  # 연빨강
        '긍정': PatternFill("solid", fgColor="D7F0D7"),  # 연초록
        '문의': PatternFill("solid", fgColor="FFF2CC"),  # 연노랑
        '중립': FILL_WHITE,
    }

    dc_sorted = sorted(dcinside_posts,
        key=lambda p: fmt_views(p.get('views', 0)), reverse=True)

    for p in dc_sorted:
        sentiment = p.get('sentiment', '중립') or '중립'
        fill = SENTIMENT_FILLS.get(sentiment, FILL_WHITE)
        row = [
            p.get('provider', ''),
            p.get('network', ''),
            p.get('title', ''),
            fmt_views(p.get('views', 0)),
            int(p.get('comments', 0) or 0),
            fmt_date(p.get('posted_at')),
            sentiment,
            p.get('topic', ''),
            p.get('url', ''),
        ]
        ws3.append(row)
        style_data_row(ws3, ws3.max_row, fill)

    for row in ws3.iter_rows(min_row=2, min_col=9, max_col=9):
        for cell in row:
            if cell.value and cell.value.startswith('http'):
                cell.hyperlink = cell.value
                cell.font = Font(name='맑은 고딕', size=9, color='0563C1', underline='single')

    for i, w in enumerate(col_widths3, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w
    ws3.row_dimensions[1].height = 20
    ws3.freeze_panes = 'A2'

    # ── Sheet4: 유튜브 ────────────────────────────────────────────────────
    ws4 = wb.create_sheet("유튜브")
    headers4 = ["채널", "제목", "조회수", "좋아요", "날짜", "키워드", "카테고리", "주요내용", "링크"]
    col_widths4 = [20, 40, 8, 7, 10, 12, 20, 45, 45]

    ws4.append(headers4)
    style_header_row(ws4, 1, HEADER_FILL_PURPLE)

    # view_count 내림차순 정렬
    yt_sorted = sorted(youtube_videos,
        key=lambda v: fmt_views(v.get('view_count', 0)), reverse=True)

    for v in yt_sorted:
        # published_at: "2026-04-06" 문자열 그대로 표시
        pub = v.get('published_at', '')
        row = [
            v.get('channel', ''),
            v.get('title', ''),
            fmt_views(v.get('view_count', 0)),
            fmt_views(v.get('like_count', 0)),
            pub,
            v.get('search_keyword', ''),
            v.get('categories', ''),
            v.get('summary', ''),
            v.get('url', ''),
        ]
        ws4.append(row)
        style_data_row(ws4, ws4.max_row)

    # 링크 컬럼 (9번째)
    for row in ws4.iter_rows(min_row=2, min_col=9, max_col=9):
        for cell in row:
            if cell.value and str(cell.value).startswith('http'):
                cell.hyperlink = cell.value
                cell.font = Font(name='맑은 고딕', size=9, color='0563C1', underline='single')

    for i, w in enumerate(col_widths4, 1):
        ws4.column_dimensions[get_column_letter(i)].width = w
    ws4.row_dimensions[1].height = 20
    ws4.freeze_panes = 'A2'

    # ── 메타 정보 주석 ────────────────────────────────────────────────────
    now_str = datetime.now(KOREA_TZ).strftime('%Y-%m-%d %H:%M')
    ws1['A1'].comment = None  # 기존 주석 클리어 (있다면)
    try:
        from openpyxl.comments import Comment
        comment = Comment(
            f"생성: {now_str}\n"
            f"뽐뿌: {len(ppomppu_posts)}건 / 디씨: {len(dcinside_posts)}건 / 유튜브: {len(youtube_videos)}건",
            "MVNO AX Agent"
        )
        ws1['A1'].comment = comment
    except Exception:
        pass

    # ── 바이트 반환 ──────────────────────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ── 텔레그램 파일 전송 ────────────────────────────────────────────────────────
def send_excel_telegram(bot_token, chat_id, excel_bytes, caption=''):
    """텔레그램에 엑셀 파일 전송"""
    now_str = datetime.now(KOREA_TZ).strftime('%y%m%d')
    filename = f"MVNO 고객동향_{now_str}.xlsx"

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
            files={'document': (filename, excel_bytes,
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
            timeout=60
        )
        if r.status_code == 200:
            print(f"✅ 엑셀 전송 완료: {filename}")
            return True
        else:
            print(f"❌ 텔레그램 전송 실패: {r.status_code} {r.text}")
            return False
    except Exception as e:
        print(f"❌ 텔레그램 전송 에러: {e}")
        return False


# ── 메인 함수 (텔레그램 핸들러에서 호출) ─────────────────────────────────────
def run_excel_export(bot_token, chat_id, days=30):
    """
    텔레그램 "엑셀 확인" 명령어 진입점

    Usage in main.py:
        from excel_exporter import run_excel_export
        run_excel_export(BOT_TOKEN, chat_id)
    """
    import requests as req

    def send_msg(text):
        try:
            req.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
                timeout=10
            )
        except Exception:
            pass

    send_msg("📊 엑셀 파일 생성 중... (잠시만 기다려주세요)")

    # Firebase 연결
    try:
        from core.firebase_handler import FirebaseHandler
        fb = FirebaseHandler()
        if not fb.db:
            send_msg("❌ Firebase 연결 실패")
            return
    except Exception as e:
        send_msg(f"❌ Firebase 초기화 실패: {e}")
        return

    # 데이터 조회
    send_msg("🔍 데이터 조회 중...")
    ppomppu  = fetch_ppomppu_posts(fb.db,  days=days)
    dcinside = fetch_dcinside_posts(fb.db, days=days)
    youtube  = fetch_youtube_videos(fb.db, days=days)

    # 엑셀 생성
    try:
        excel_bytes = build_excel(ppomppu, dcinside, youtube)
    except Exception as e:
        send_msg(f"❌ 엑셀 생성 실패: {e}")
        return

    now_str = datetime.now(KOREA_TZ).strftime('%m/%d %H:%M')
    caption = (
        f"📋 <b>MVNO 모니터링 현황</b> ({now_str} 기준)\n\n"
        f"📌 요금 주요 이슈: 조회1만↑ or ⭐⭐⭐\n"
        f"📊 뽐뿌 {len(ppomppu)}건 | 디씨 {len(dcinside)}건 | 유튜브 {len(youtube)}건\n"
        f"📅 최근 {days}일 데이터"
    )

    send_excel_telegram(bot_token, chat_id, excel_bytes, caption)


# ── 로컬 테스트용 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    """
    로컬 테스트: 더미 데이터로 엑셀 구조 확인
    실행: python excel_exporter.py
    """
    from datetime import datetime, timedelta

    now = datetime.now(KOREA_TZ)

    dummy_ppomppu = [
        {
            'title': '[KT엠모바일] 5G 15G 월 9900원 특가!!',
            'provider': 'KT엠모바일',
            'views': 15000,
            'comments': 32,
            'posted_at': now - timedelta(hours=3),
            'relevance_score': 9,
            'content_summary': '5G 15G 요금제 특가 이벤트, 3개월 한정',
            'url': 'https://www.ppomppu.co.kr/test1',
        },
        {
            'title': '알뜰폰 요금제 비교 정리 (2026년 4월)',
            'provider': '다수',
            'views': 8200,
            'comments': 15,
            'posted_at': now - timedelta(hours=10),
            'relevance_score': 6,
            'content_summary': '사업자별 최저가 요금제 비교표',
            'url': 'https://www.ppomppu.co.kr/test2',
        },
        {
            'title': '헬로모바일 해지 후기',
            'provider': '헬로모바일',
            'views': 1200,
            'comments': 5,
            'posted_at': now - timedelta(days=2),
            'relevance_score': 3,
            'content_summary': '해지 과정에서 위약금 문의',
            'url': 'https://www.ppomppu.co.kr/test3',
        },
    ]

    dummy_dc = [
        {
            'title': '핀다 2970 요금제 아직 살아있나요?',
            'provider': '핀다',
            'network': '3사공통',
            'views': 950,
            'comments': 8,
            'posted_at': now - timedelta(hours=5),
            'sentiment': '문의',
            'topic': '핀다 2970 이슈',
            'url': 'https://m.dcinside.com/test1',
        },
        {
            'title': 'SKT망 품질 요즘 왜이래',
            'provider': '',
            'network': 'SKT',
            'views': 430,
            'comments': 12,
            'posted_at': now - timedelta(hours=8),
            'sentiment': '불만',
            'topic': '통신사 망 이슈',
            'url': 'https://m.dcinside.com/test2',
        },
    ]

    dummy_yt = [
        {
            'channel_name': '알뜰폰 연구소',
            'title': '2026년 4월 알뜰폰 요금제 TOP5',
            'view_count': 42000,
            'published_at': now - timedelta(days=1),
            'summary': '이달의 추천 요금제 5종 비교',
            'url': 'https://youtube.com/test1',
        },
    ]

    print("🔧 더미 데이터로 엑셀 생성 테스트...")
    excel_bytes = build_excel(dummy_ppomppu, dummy_dc, dummy_yt)

    output_path = '/tmp/MVNO_test.xlsx'
    with open(output_path, 'wb') as f:
        f.write(excel_bytes)
    print(f"✅ 엑셀 저장 완료: {output_path}")
    print(f"   Sheet1(주요이슈): {len([p for p in dummy_ppomppu if p['views']>=10000 or p['relevance_score']>=7])}건")
    print(f"   Sheet2(뽐뿌): {len(dummy_ppomppu)}건")
    print(f"   Sheet3(디씨): {len(dummy_dc)}건")
    print(f"   Sheet4(유튜브): {len(dummy_yt)}건")