# youtube_client.py
# YouTube Market Analyzer — YouTube Data API v3 클라이언트
#
# [수정 이력]
# v1.0 | 2025-03-22 | 최초 작성 — 검색, 영상 상세, 댓글 수집 기능
# v1.1 | 2025-03-31 | get_comments — 채널 운영자 댓글 자동 제외
# v1.2 | 2026-09-19 | get_comments — 답글(대댓글) 수집 추가 (commentThreads 응답에
#      | 이미 포함된 replies.comments를 사용 — 추가 API 쿼터 소비 없음)
# v1.3 | 2026-09-19 | search_videos — order 파라미터 추가 (relevance/date 선택 가능).
#      | 관련도순만으로는 방금 올라와 조회수/좋아요가 적은 신규 영상이 순위 밖으로
#      | 밀려 검색 결과에서 아예 누락될 수 있어, 호출 측에서 date 검색도 병행하도록 함
# v1.4 | 2026-09-19 | search_videos 결과에 description 추가 (이미 videos().list
#      | 응답에 들어있던 필드인데 누락되어 있었음 — 추가 쿼터 소비 없음).
#      | classify_post()가 제목만 보고 판별해왔는데, 이제 설명란까지 봐서
#      | 제목에 사업자명이 없어도 설명란에 있으면 잡히도록 함.
#      | 쿼터 초과 시 조용히 빈 결과를 반환하지 않고 QuotaExceededError를 던지도록
#      | 변경 — 호출 측(youtube_monitor.py)에서 텔레그램 알림을 보낼 수 있게
# v1.5 | 2026-09-20 | search_videos — type="video"로 필터링해도 드물게 videoId가
#      | 없는 항목이 섞여 KeyError로 죽는 경우가 있어(키워드가 늘며 처음 발견)
#      | videoId 없는 항목은 건너뛰도록 방어 코드 추가

import os
import re
import json
import logging
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """YouTube Data API 일일 쿼터(또는 요청 한도) 초과"""
    pass


def _is_quota_exceeded(e: HttpError) -> bool:
    if e.resp.status != 403:
        return False
    try:
        content = json.loads(e.content.decode("utf-8"))
        reasons = {err.get("reason") for err in content.get("error", {}).get("errors", [])}
    except Exception:
        return False
    return bool(reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"})

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def _build_client():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL에서 video_id 추출"""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"embed\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def search_videos(keyword: str, max_results: int = 5, order: str = "relevance") -> list[dict]:
    """
    키워드로 YouTube 영상 검색
    order: "relevance"(관련도순, 기본) 또는 "date"(최신순).
           관련도순만 쓰면 막 올라와 아직 조회수/좋아요가 적은 신규 영상이
           순위 밖으로 밀려 검색 결과에 아예 안 잡힐 수 있음 — 센싱 용도로는
           date 검색을 병행하는 것을 권장.
    반환: [{video_id, title, channel, published_at, view_count, ...}]
    """
    try:
        youtube = _build_client()

        # 검색 (100 units 소비)
        search_resp = youtube.search().list(
            q=keyword,
            part="snippet",
            type="video",
            order=order,
            relevanceLanguage="ko",
            regionCode="KR",
            maxResults=max_results,
        ).execute()

        # type="video"로 필터링해도 드물게 videoId가 없는 항목이 섞여 옴 (API 엣지
        # 케이스) — 없으면 통째로 죽던 걸 방어적으로 건너뛰도록 수정
        video_ids = [
            item["id"]["videoId"]
            for item in search_resp.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        # 상세 정보 (조회수, 댓글수 등) 추가 조회 (1 unit)
        detail_resp = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids),
        ).execute()

        results = []
        for item in detail_resp.get("items", []):
            stats = item.get("statistics", {})
            snippet = item["snippet"]
            results.append({
                "video_id": item["id"],
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                # [v1.4] 이미 응답에 들어있던 필드 — classify_post()가 제목만 보고
                # 판별하던 걸 설명란까지 보게 하려고 추가 (추가 쿼터 소비 없음)
                "description": snippet.get("description", "")[:500],
                "published_at": snippet["publishedAt"][:10],
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "thumbnail": snippet["thumbnails"].get("high", {}).get("url", ""),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            })

        # 조회수 기준 정렬
        results.sort(key=lambda x: x["view_count"], reverse=True)
        return results

    except HttpError as e:
        if _is_quota_exceeded(e):
            raise QuotaExceededError("YouTube API 쿼터 초과 (search)") from e
        logger.error(f"YouTube API 오류 (search): {e}")
        return []


def get_video_info(video_id: str) -> Optional[dict]:
    """단일 영상 상세 정보 조회"""
    try:
        youtube = _build_client()
        resp = youtube.videos().list(
            part="snippet,statistics",
            id=video_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            return None

        item = items[0]
        stats = item.get("statistics", {})
        snippet = item["snippet"]

        return {
            "video_id": video_id,
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "description": snippet.get("description", "")[:500],
            "published_at": snippet["publishedAt"][:10],
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "thumbnail": snippet["thumbnails"].get("high", {}).get("url", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    except HttpError as e:
        if _is_quota_exceeded(e):
            raise QuotaExceededError("YouTube API 쿼터 초과 (video info)") from e
        logger.error(f"YouTube API 오류 (video info): {e}")
        return None


def get_comments(video_id: str, max_count: int = 300, channel_title: str = "") -> list[dict]:
    """
    영상 댓글 수집 (상위 댓글 + 답글 기준)
    - 채널 운영자 본인 댓글 자동 제외
    - 답글은 commentThreads 응답에 이미 포함된 것만 사용 (추가 쿼터 소비 없음).
      영상에 답글이 매우 많아 API가 전체를 임베딩하지 못한 경우 일부만 반영될 수 있음.
    반환: [{text, like_count, reply_count, published_at, author, is_reply}]
    """

    def _is_owner_comment(author: str) -> bool:
        return bool(channel_title) and (
            author == channel_title or
            channel_title in author or
            author in channel_title
        )

    try:
        youtube = _build_client()
        comments = []
        next_page_token = None
        skipped = 0

        while len(comments) < max_count:
            resp = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                order="relevance",
                maxResults=min(100, max_count - len(comments) + 20),  # 필터 여유분
                pageToken=next_page_token,
                textFormat="plainText",
            ).execute()

            for item in resp.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                author = top.get("authorDisplayName", "").strip()

                if _is_owner_comment(author):
                    skipped += 1
                else:
                    comments.append({
                        "text": top["textDisplay"].strip(),
                        "like_count": top.get("likeCount", 0),
                        "reply_count": item["snippet"].get("totalReplyCount", 0),
                        "published_at": top["publishedAt"][:10],
                        "author": author,
                        "is_reply": False,
                    })

                # 답글 수집 (같은 응답에 이미 포함된 것만, 추가 API 호출 없음)
                for reply_item in item.get("replies", {}).get("comments", []):
                    reply = reply_item["snippet"]
                    reply_author = reply.get("authorDisplayName", "").strip()

                    if _is_owner_comment(reply_author):
                        skipped += 1
                        continue

                    comments.append({
                        "text": reply.get("textDisplay", "").strip(),
                        "like_count": reply.get("likeCount", 0),
                        "reply_count": 0,
                        "published_at": reply["publishedAt"][:10],
                        "author": reply_author,
                        "is_reply": True,
                    })

            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

        if skipped > 0:
            logger.info(f"운영자 댓글 {skipped}개 제외 (channel={channel_title})")

        comments.sort(key=lambda x: x["like_count"], reverse=True)
        return comments[:max_count]

    except HttpError as e:
        if _is_quota_exceeded(e):
            raise QuotaExceededError("YouTube API 쿼터 초과 (comments)") from e
        logger.warning(f"댓글 수집 불가 (video_id={video_id}): {e}")
        return []