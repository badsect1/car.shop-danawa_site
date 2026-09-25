import time
import requests
import feedparser
from typing import List, Dict, Any

RSS_BASE_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

def is_shorts(video_id: str, title: str = "") -> bool:
    """
    영상 ID와 제목을 기반으로 쇼츠(Shorts) 여부를 판별합니다.
    1. 제목에 '#shorts' 또는 '#쇼츠'가 포함되어 있으면 즉시 True 반환
    2. https://www.youtube.com/shorts/{video_id} 로 HEAD 요청을 보내 리다이렉트 여부 확인
       - 200 OK: 쇼츠 영상
       - 301/302/303 Redirect to /watch?v=...: 일반 롱폼 영상
    """
    lower_title = title.lower()
    if "#shorts" in lower_title or "#쇼츠" in lower_title or "#short" in lower_title:
        return True

    url = f"https://www.youtube.com/shorts/{video_id}"
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.head(url, headers=headers, allow_redirects=False, timeout=6)
        
        # 쇼츠인 경우 리다이렉트 없이 200 반환
        if response.status_code == 200:
            return True
        
        # 일반 롱폼 영상인 경우 유튜브가 /watch?v= 로 리다이렉트 (303 See Other 등)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            if "/watch?v=" in location or "watch" in location:
                return False
            # 쇼츠 페이지 내 리다이렉트인 경우
            return True

        # 상태 코드가 404나 기타인 경우 일반 영상으로 간주
        return False
    except Exception as e:
        print(f"  [경고] 쇼츠 여부 확인 중 오류 발생 (video_id: {video_id}): {e}")
        # 오류 시 제목 기반으로만 판단
        return False

def get_channel_videos(channel_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    지정된 채널의 RSS 피드를 조회하여 최근 영상 목록을 반환합니다.
    """
    rss_url = RSS_BASE_URL.format(channel_id=channel_id)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        return []

    videos = []
    for entry in feed.entries[:limit]:
        video_id = entry.get("yt_videoid")
        if not video_id and "link" in entry:
            # link에서 v= 파라미터 추출
            link = entry.link
            if "v=" in link:
                video_id = link.split("v=")[1].split("&")[0]

        if not video_id:
            continue

        title = entry.get("title", "")
        published = entry.get("published", "")
        link = entry.get("link", f"https://www.youtube.com/watch?v={video_id}")
        author = entry.get("author", "")

        videos.append({
            "video_id": video_id,
            "title": title,
            "published": published,
            "link": link,
            "author": author
        })

    return videos
