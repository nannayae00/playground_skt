"""
뽐뿌 필터링 감사 스크립트 - 전체 수집글 vs 규칙단계 통과글 비교.
use_ai=False로 실행: AI 단계는 이미 통과한 후보를 "제거"만 할 수 있고
"추가"는 못 하므로, 규칙단계(rule-base) 결과가 실제 운영에서 잡을 수 있는
최대 상한선. 여기서 빠진 글은 AI를 켜도 절대 못 잡음 - 이게 진짜
"잡혀야 하는데 안 잡힌" 후보를 찾는 지점.
"""
import sys
import os
import io
import contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.ppomppu_scraper import PpomppuScraper, filter_mvno_posts
from core.mvno_classifier import classify_post

DAYS = float(os.environ.get("AUDIT_DAYS", "1"))
NON_MVNO_BOARDS = {'freeboard', 'coupon', 'computer', 'issue', 'ppomppu', 'ppomppu2', 'pmarket', 'pmarket2', 'pmarket3'}
MNO_EVENT_KW = ['골드번호', '선호번호', '번호세탁']
DEALER_AD_PATTERNS = ['공식인증대리점', 'T매장 내방', '대리점 내방', '성지 내방',
                      '번이기변/유심', 'SK번이기변', 'KT번이기변', 'LG번이기변']

print(f"=== 뽐뿌 스크래핑 시작 (최근 {DAYS}일) ===", file=sys.stderr)
scraper = PpomppuScraper()
all_posts = scraper.scrape(days=DAYS)
print(f"=== 스크래핑 완료: {len(all_posts)}개 ===", file=sys.stderr)

# 원본 title[:30] 기준 중복 제거는 filter_mvno_posts 내부에서도 하지만,
# 여기서는 raw 전체를 기준으로 "silent drop"을 우리가 직접 재현해서 찾는다.
silent_dropped = []
for post in all_posts:
    board = post.get('board', '')
    result = classify_post(post['title'], '', use_ai=False, board=board)
    if result:
        continue  # classify_post가 뭔가 잡았으면 여기 해당 없음 (로그 있음)
    is_dealer_ad = any(p in post['title'] for p in DEALER_AD_PATTERNS)
    is_mno_event = any(kw in post['title'] for kw in MNO_EVENT_KW) and not is_dealer_ad
    if board in NON_MVNO_BOARDS and not is_mno_event:
        silent_dropped.append(post)

print(f"=== 무로그 탈락(board 필터, 로그 없음): {len(silent_dropped)}개 ===", file=sys.stderr)

# 실제 필터링 파이프라인 (use_ai=False = 규칙단계 상한선)
log_buf = io.StringIO()
with contextlib.redirect_stdout(log_buf):
    final = filter_mvno_posts(list(all_posts), use_ai=False, top_n=None, progress_telegram=None)

final_ids = {p.get('post_id') or p.get('id') or p.get('url') for p in final}
final_titles = {p['title'] for p in final}

with open("/tmp/claude-0/-home-user-playground-skt/5bfa3b09-0961-5b98-a99b-1ffe5e8b79cd/scratchpad/ppomppu_pipeline_log.txt", "w") as f:
    f.write(log_buf.getvalue())

print(f"=== 최종(규칙단계) 통과: {len(final)}개 / 전체 {len(all_posts)}개 ===", file=sys.stderr)

# MVNO 관련성 있어 보이는데 최종 통과 못한 글 - 사람이 눈으로 볼 후보 목록
LOOSE_MVNO_HINT = ['알뜰폰', 'mvno', '유심', '번호이동', '요금제', '통신사',
                    '개통', 'esim', 'usim', '공기계', '자급제']

candidates_for_review = []
for post in all_posts:
    title = post['title']
    if title in final_titles:
        continue
    if any(kw.lower() in title.lower() for kw in LOOSE_MVNO_HINT):
        candidates_for_review.append(post)

print(f"=== 통과 못했지만 MVNO 힌트 키워드 있는 글: {len(candidates_for_review)}개 ===", file=sys.stderr)

with open("/tmp/claude-0/-home-user-playground-skt/5bfa3b09-0961-5b98-a99b-1ffe5e8b79cd/scratchpad/ppomppu_audit_report.txt", "w") as f:
    f.write(f"전체 수집: {len(all_posts)}개\n")
    f.write(f"규칙단계 최종 통과(=AI 켜도 얻을 수 있는 최대치): {len(final)}개\n")
    f.write(f"무로그 board 필터 탈락: {len(silent_dropped)}개\n")
    f.write(f"통과 못했지만 MVNO 힌트 키워드 포함: {len(candidates_for_review)}개\n\n")

    f.write("="*80 + "\n")
    f.write("[검토 필요] 통과 못했지만 MVNO 힌트 키워드가 제목에 있는 글\n")
    f.write("="*80 + "\n")
    for p in sorted(candidates_for_review, key=lambda x: -x.get('views', 0)):
        f.write(f"👁{p.get('views',0):>6,} [{p.get('board','')}] {p['title']}\n")
        f.write(f"    {p.get('url','')}\n")

    f.write("\n" + "="*80 + "\n")
    f.write("[참고] 무로그 board 필터 탈락 전체 목록 (조회수 상위 40개만)\n")
    f.write("="*80 + "\n")
    for p in sorted(silent_dropped, key=lambda x: -x.get('views', 0))[:40]:
        f.write(f"👁{p.get('views',0):>6,} [{p.get('board','')}] {p['title']}\n")

print("=== 리포트 저장 완료 ===", file=sys.stderr)
