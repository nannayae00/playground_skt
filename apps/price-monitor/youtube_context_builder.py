"""
youtube_context_builder.py  v1.1
작성일: 2026-05-20

[수정 이력]
v1.1 | 2026-05-20 | pytz 의존성 제거 (datetime.timezone으로 교체)
v1.0 | 2026-05-20 | 최초 작성
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _get_db():
    from google.cloud import firestore as _fs
    import firebase_admin
    from firebase_admin import credentials as _cred
    if not firebase_admin._apps:
        firebase_admin.initialize_app(_cred.ApplicationDefault())
    return _fs.Client(project='mvno-484509', database='mvno-data')


def _fmt(n):
    if n >= 10000: return f"{n/10000:.1f}만"
    if n >= 1000:  return f"{n/1000:.1f}천"
    return str(n)


def build_youtube_context(date_str=None):
    db = _get_db()
    _now     = datetime.now(KST)
    date_str = date_str or _now.strftime('%Y-%m-%d')
    checked  = _now.strftime('%m/%d %H:%M')
    SEP      = '━' * 28

    date_suffix   = date_str.replace('-', '')
    day_start_utc = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc) - timedelta(hours=-9)
    day_end_utc   = day_start_utc + timedelta(days=1)

    # ── 신규 영상 (youtube_analyses) ──────────────────────────
    new_videos = []
    try:
        for doc in db.collection('youtube_analyses').stream():
            if doc.id.endswith(f'_{date_suffix}'):
                new_videos.append(doc.to_dict())
        new_videos.sort(key=lambda x: x.get('video_info', {}).get('view_count', 0), reverse=True)
        log.info(f"신규 영상 {len(new_videos)}개")
    except Exception as e:
        log.warning(f"youtube_analyses 조회 실패: {e}")

    # ── 급상승 영상 (youtube_seen_videos) ────────────────────
    viral_videos = []
    try:
        for doc in db.collection('youtube_seen_videos').stream():
            d = doc.to_dict()
            if (d.get('last_checked_at', '') or '')[:10] == date_str:
                history = d.get('view_count_history', [])
                if len(history) >= 2 and history[-2] > 1000:
                    pct = (history[-1] - history[-2]) / history[-2] * 100
                    if pct >= 50:
                        d['_viral_pct'] = round(pct, 1)
                        d['_prev_view'] = history[-2]
                        viral_videos.append(d)
        viral_videos.sort(key=lambda x: x.get('_viral_pct', 0), reverse=True)
        log.info(f"급상승 영상 {len(viral_videos)}개")
    except Exception as e:
        log.warning(f"youtube_seen_videos 조회 실패: {e}")

    # ── 실행 로그 ─────────────────────────────────────────────
    total_searched, run_count = 0, 0
    try:
        for doc in db.collection('youtube_monitor_logs').stream():
            d = doc.to_dict()
            logged = (d.get('logged_at') or '')[:10]
            if logged == date_str:
                total_searched += d.get('total_searched', 0)
                run_count += 1
    except Exception as e:
        log.warning(f"youtube_monitor_logs 조회 실패: {e}")

    # ── SUMMARY ───────────────────────────────────────────────
    alerts, normals = [], []
    if new_videos:
        titles = ' / '.join(
            v.get('video_info', {}).get('title', '')[:20] + '…' for v in new_videos[:2])
        alerts.append(f"신규 MVNO 영상 {len(new_videos)}개 감지 — {titles}")
    else:
        normals.append("당일 신규 MVNO 영상 없음")

    if viral_videos:
        v0 = viral_videos[0]
        alerts.append(f"급상승 영상 {len(viral_videos)}개 — \"{v0.get('title','')[:25]}\" +{v0.get('_viral_pct',0):.0f}%↑")
    else:
        normals.append("급상승 영상 없음")

    # 부정 여론 우세 체크
    neg_dom = []
    for v in new_videos:
        rat = v.get('comment_analysis', {}).get('sentiment_ratio', {})
        if rat.get('부정', 0) > rat.get('긍정', 0) and rat.get('부정', 0) > 40:
            neg_dom.append(v.get('video_info', {}).get('title', '')[:20])
    if neg_dom:
        alerts.append(f"부정 여론 우세 영상: {', '.join(neg_dom[:2])}")

    # ── 텍스트 조립 ───────────────────────────────────────────
    L = []
    L.append(f"[MVNO YouTube AI컨텍스트 | {date_str} | {checked} 기준]")
    L.append("※ YouTube MVNO 당일 수집 분석값. 재계산 금지. 해석만 할 것.")
    L.append("")
    L.append(SEP)
    L.append("■ SUMMARY (AI 해석 우선순위)")
    L.append(SEP)
    for a in alerts:  L.append(f"  ⚠️ ALERT: {a}")
    for n in normals: L.append(f"  ✅ NORMAL: {n}")
    L.append("※ 상세 내용은 하단 각 섹션 참조")

    # 섹션 1: 신규 영상
    L.append(f"\n{SEP}")
    L.append(f"■ 1. 당일 신규 감지 영상 ({len(new_videos)}개)")
    L.append(SEP)
    if new_videos:
        for i, v in enumerate(new_videos[:5], 1):
            vi  = v.get('video_info', {})
            ca  = v.get('comment_analysis', {})
            sm  = v.get('summary', {})
            rat = ca.get('sentiment_ratio', {})
            L.append(f"[{i}] {vi.get('title','')}")
            L.append(f"  채널: {vi.get('channel','')} | 조회 {_fmt(vi.get('view_count',0))} | {vi.get('published_at','')}")
            L.append(f"  URL: {vi.get('url','')}")
            lines = sm.get('lines', [])
            if lines:
                L.append(f"  📝 요약:")
                for line in lines[:3]: L.append(f"    • {line}")
            if sm.get('insight'): L.append(f"  💡 {sm['insight']}")
            total_cmt = ca.get('total', 0)
            if total_cmt > 0:
                L.append(f"  💬 댓글 {total_cmt}개 | 긍정 {rat.get('긍정',0)}% / 부정 {rat.get('부정',0)}% / 중립 {rat.get('중립',0)}%")
                if ca.get('overall_summary'): L.append(f"  여론: {ca['overall_summary']}")
                if ca.get('key_issue'):       L.append(f"  핵심이슈: {ca['key_issue']}")
                for c in ca.get('clusters', [])[:3]:
                    L.append(f"    - {c.get('label','')}({c.get('count',0)}건): {c.get('representative','')[:50]}…")
            else:
                L.append(f"  💬 댓글 없음")
            if i < len(new_videos[:5]): L.append("")
    else:
        L.append("당일 신규 감지 영상 없음")

    # 섹션 2: 급상승
    L.append(f"\n{SEP}")
    L.append(f"■ 2. 급상승 영상 (전일 대비 +50%↑)")
    L.append(SEP)
    if viral_videos:
        for i, v in enumerate(viral_videos[:3], 1):
            L.append(f"[{i}] {v.get('title','')}")
            L.append(f"  채널: {v.get('channel','')} | 조회: {_fmt(v.get('_prev_view',0))} → {_fmt(v.get('view_count',0))} (+{v.get('_viral_pct',0):.0f}%↑)")
            L.append(f"  URL: {v.get('url','')}")
            if i < len(viral_videos[:3]): L.append("")
    else:
        L.append("급상승 영상 없음")

    # 섹션 3: 수집 현황
    L.append(f"\n{SEP}")
    L.append("■ 3. 수집 현황")
    L.append(SEP)
    L.append(f"당일 실행: {run_count}회 / 총 검색: {total_searched}개")
    L.append(f"신규: {len(new_videos)}개 / 급상승: {len(viral_videos)}개")
    L.append("모니터링 키워드: 알뜰폰 / MVNO 유심 / 유심 요금제")

    return '\n'.join(L)


def save_youtube_context(date_str=None):
    db = _get_db()
    _now     = datetime.now(KST)
    date_str = date_str or _now.strftime('%Y-%m-%d')
    try:
        text = build_youtube_context(date_str)
        db.collection('youtube_context').document(date_str).set({
            'date': date_str, 'text': text,
            'saved_at': _now, 'version': 'v1.1',
        })
        log.info(f"youtube_context 저장 완료: {date_str} ({len(text):,}자)")
        return True
    except Exception as e:
        log.error(f"youtube_context 저장 실패: {e}")
        return False


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if save_youtube_context(date_arg) else 1)