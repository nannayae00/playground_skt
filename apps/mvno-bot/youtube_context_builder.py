"""
youtube_context_builder.py  v1.0
작성일: 2026-05-20

[수정 이력]
v1.0 | 2026-05-20 | 최초 작성
  - 당일 youtube_analyses 컬렉션에서 신규 감지 영상 집계
  - youtube_seen_videos에서 당일 급상승 영상 집계
  - SUMMARY(ALERT/NORMAL) + 신규영상 + 급상승 + 수집현황 텍스트 생성
  - Firestore youtube_context/{YYYY-MM-DD} 저장
  - Cloud Run Job으로 매일 20:10 KST 실행

저장 구조:
  youtube_context/{YYYY-MM-DD} → {date, text, saved_at, version}

실행 방법:
  python3 youtube_context_builder.py              # 당일 기준
  python3 youtube_context_builder.py 2026-05-19  # 특정 날짜 테스트
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta

import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

KST = pytz.timezone('Asia/Seoul')


def _get_db():
    from google.cloud import firestore as _fs
    import firebase_admin
    from firebase_admin import credentials as _cred
    if not firebase_admin._apps:
        firebase_admin.initialize_app(_cred.ApplicationDefault())
    return _fs.Client(project='mvno-484509', database='mvno-data')


def build_youtube_context(date_str: str = None) -> str:
    """
    당일 youtube_analyses + youtube_seen_videos 읽어서 context 텍스트 생성.
    텔레그램 발송 내용 기반으로 AI가 읽기 좋은 구조화 텍스트 반환.
    """
    db = _get_db()

    _now     = datetime.now(KST)
    date_str = date_str or _now.strftime('%Y-%m-%d')
    checked  = _now.strftime('%m/%d %H:%M')
    SEP      = '━' * 28

    # 당일 날짜 범위 (KST 기준 00:00 ~ 23:59)
    day_start = KST.localize(datetime.strptime(date_str, '%Y-%m-%d'))
    day_end   = day_start + timedelta(days=1)
    day_start_utc = day_start.astimezone(timezone.utc)
    day_end_utc   = day_end.astimezone(timezone.utc)

    # ── 당일 신규 감지 영상 수집 ──────────────────────────────
    # youtube_analyses/{video_id}_{YYYYMMDD} 형식
    date_suffix = date_str.replace('-', '')
    new_videos  = []

    try:
        docs = db.collection('youtube_analyses').stream()
        for doc in docs:
            if doc.id.endswith(f'_{date_suffix}'):
                d = doc.to_dict()
                new_videos.append(d)
        log.info(f"신규 영상 {len(new_videos)}개 조회 (youtube_analyses)")
    except Exception as e:
        log.warning(f"youtube_analyses 조회 실패: {e}")

    # 조회수 내림차순 정렬
    new_videos.sort(
        key=lambda x: x.get('video_info', {}).get('view_count', 0),
        reverse=True
    )

    # ── 당일 급상승 영상 수집 ─────────────────────────────────
    viral_videos = []
    try:
        docs = db.collection('youtube_seen_videos').stream()
        for doc in docs:
            d = doc.to_dict()
            last_checked = d.get('last_checked_at', '')
            # last_checked_at이 오늘이고 조회수 이력에서 급상승 감지
            if last_checked and last_checked[:10] == date_str:
                history = d.get('view_count_history', [])
                if len(history) >= 2:
                    prev_v = history[-2]
                    curr_v = history[-1]
                    if prev_v > 1000 and curr_v > prev_v:
                        pct = (curr_v - prev_v) / prev_v * 100
                        if pct >= 50:
                            d['_viral_pct'] = round(pct, 1)
                            d['_prev_view'] = prev_v
                            viral_videos.append(d)
        viral_videos.sort(key=lambda x: x.get('_viral_pct', 0), reverse=True)
        log.info(f"급상승 영상 {len(viral_videos)}개 조회 (youtube_seen_videos)")
    except Exception as e:
        log.warning(f"youtube_seen_videos 조회 실패: {e}")

    # ── 당일 실행 로그 (수집 현황) ────────────────────────────
    total_searched = 0
    run_count      = 0
    try:
        logs = db.collection('youtube_monitor_logs') \
                 .where('logged_at', '>=', day_start_utc.isoformat()) \
                 .where('logged_at', '<',  day_end_utc.isoformat()) \
                 .stream()
        for doc in logs:
            d = doc.to_dict()
            total_searched += d.get('total_searched', 0)
            run_count += 1
    except Exception as e:
        log.warning(f"youtube_monitor_logs 조회 실패: {e}")

    # ── SUMMARY 판별 ─────────────────────────────────────────
    alerts  = []
    normals = []

    if new_videos:
        titles = ' / '.join(
            v.get('video_info', {}).get('title', '')[:20] + '…'
            for v in new_videos[:2]
        )
        alerts.append(f"신규 MVNO 영상 {len(new_videos)}개 감지 — {titles}")
    else:
        normals.append("당일 신규 MVNO 영상 없음")

    if viral_videos:
        v0    = viral_videos[0]
        title = v0.get('title', '')[:25]
        pct   = v0.get('_viral_pct', 0)
        alerts.append(f"급상승 영상 {len(viral_videos)}개 — \"{title}\" +{pct:.0f}%↑")
    else:
        normals.append("급상승 영상 없음")

    # 감성 경향 체크 (신규 영상 평균)
    neg_dominant = []
    for v in new_videos:
        ca  = v.get('comment_analysis', {})
        rat = ca.get('sentiment_ratio', {})
        neg = rat.get('부정', 0)
        pos = rat.get('긍정', 0)
        if neg > pos and neg > 40:
            t = v.get('video_info', {}).get('title', '')[:20]
            neg_dominant.append(t)
    if neg_dominant:
        alerts.append(f"부정 여론 우세 영상: {', '.join(neg_dominant[:2])}")

    # ── 텍스트 조립 ──────────────────────────────────────────
    L = []
    L.append(f"[MVNO YouTube AI컨텍스트 | {date_str} | {checked} 기준]")
    L.append("※ YouTube MVNO 당일 수집 분석값. 재계산 금지. 해석만 할 것.")
    L.append("")
    L.append(SEP)
    L.append("■ SUMMARY (AI 해석 우선순위)")
    L.append(SEP)
    for a in alerts:
        L.append(f"  ⚠️ ALERT: {a}")
    for n in normals:
        L.append(f"  ✅ NORMAL: {n}")
    L.append("※ 상세 내용은 하단 각 섹션 참조")

    # ── 섹션 1: 신규 감지 영상 ───────────────────────────────
    L.append(f"\n{SEP}")
    L.append(f"■ 1. 당일 신규 감지 영상 ({len(new_videos)}개)")
    L.append(SEP)

    if new_videos:
        for i, v in enumerate(new_videos[:5], 1):  # 최대 5개
            vi  = v.get('video_info', {})
            ca  = v.get('comment_analysis', {})
            sm  = v.get('summary', {})
            rat = ca.get('sentiment_ratio', {})

            title   = vi.get('title', '')
            channel = vi.get('channel', '')
            views   = vi.get('view_count', 0)
            pub     = vi.get('published_at', '')
            url     = vi.get('url', '')
            keyword = v.get('search_keywords', '')

            # 조회수 포맷
            def _fmt(n):
                if n >= 10000: return f"{n/10000:.1f}만"
                if n >= 1000:  return f"{n/1000:.1f}천"
                return str(n)

            # 요약 라인
            summary_lines = sm.get('lines', [])
            insight       = sm.get('insight', '')

            # 댓글 감성
            total_cmt = ca.get('total', 0)
            pos = rat.get('긍정', 0)
            neg = rat.get('부정', 0)
            neu = rat.get('중립', 0)

            # 주요 클러스터
            clusters = ca.get('clusters', [])

            # 핵심 이슈
            key_issue = ca.get('key_issue', '')
            overall   = ca.get('overall_summary', '')

            L.append(f"[{i}] {title}")
            L.append(f"  채널: {channel} | 조회 {_fmt(views)} | {pub}")
            if keyword:
                L.append(f"  검색어: {keyword}")
            L.append(f"  URL: {url}")

            if summary_lines:
                L.append(f"  📝 요약:")
                for line in summary_lines[:3]:
                    L.append(f"    • {line}")
            if insight:
                L.append(f"  💡 {insight}")

            if total_cmt > 0:
                L.append(f"  💬 댓글 {total_cmt}개 | 긍정 {pos}% / 부정 {neg}% / 중립 {neu}%")
                if overall:
                    L.append(f"  여론: {overall}")
                if key_issue:
                    L.append(f"  핵심이슈: {key_issue}")
                if clusters:
                    L.append(f"  주요여론:")
                    for c in clusters[:3]:
                        label = c.get('label', '')
                        rep   = c.get('representative', '')[:50]
                        cnt   = c.get('count', 0)
                        sent  = c.get('dominant_sentiment', '')
                        L.append(f"    - {label}({cnt}건/{sent}): {rep}…")
            else:
                L.append(f"  💬 댓글 없음")

            if i < len(new_videos[:5]):
                L.append("")
    else:
        L.append("당일 신규 감지 영상 없음")

    # ── 섹션 2: 급상승 영상 ──────────────────────────────────
    L.append(f"\n{SEP}")
    L.append(f"■ 2. 급상승 영상 (전일 대비 +50%↑)")
    L.append(SEP)

    if viral_videos:
        for i, v in enumerate(viral_videos[:3], 1):
            title    = v.get('title', '')
            url      = v.get('url', '')
            channel  = v.get('channel', '')
            curr_v   = v.get('view_count', 0)
            prev_v   = v.get('_prev_view', 0)
            pct      = v.get('_viral_pct', 0)
            provider = v.get('provider', '')

            def _fmt(n):
                if n >= 10000: return f"{n/10000:.1f}만"
                if n >= 1000:  return f"{n/1000:.1f}천"
                return str(n)

            L.append(f"[{i}] {title}")
            L.append(f"  채널: {channel}" + (f" | 사업자: {provider}" if provider else ""))
            L.append(f"  조회: {_fmt(prev_v)} → {_fmt(curr_v)} (+{pct:.0f}%↑)")
            L.append(f"  URL: {url}")
            if i < len(viral_videos[:3]):
                L.append("")
    else:
        L.append("급상승 영상 없음")

    # ── 섹션 3: 수집 현황 ────────────────────────────────────
    L.append(f"\n{SEP}")
    L.append("■ 3. 수집 현황")
    L.append(SEP)
    L.append(f"당일 실행 횟수: {run_count}회")
    L.append(f"총 검색 결과: {total_searched}개")
    L.append(f"신규 감지: {len(new_videos)}개 / 급상승: {len(viral_videos)}개")
    L.append(f"모니터링 키워드: 알뜰폰 / MVNO 유심 / 유심 요금제")

    return '\n'.join(L)


def save_youtube_context(date_str: str = None) -> bool:
    """
    youtube_context 생성 → Firestore youtube_context/{date_str} 저장
    Cloud Run Job에서 호출하는 메인 함수
    """
    db = _get_db()
    _now     = datetime.now(KST)
    date_str = date_str or _now.strftime('%Y-%m-%d')

    try:
        text = build_youtube_context(date_str)
        db.collection('youtube_context').document(date_str).set({
            'date'    : date_str,
            'text'    : text,
            'saved_at': _now,
            'version' : 'v1.0',
        })
        log.info(f"youtube_context 저장 완료: {date_str} ({len(text):,}자)")
        return True
    except Exception as e:
        log.error(f"youtube_context 저장 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    ok = save_youtube_context(date_arg)
    sys.exit(0 if ok else 1)