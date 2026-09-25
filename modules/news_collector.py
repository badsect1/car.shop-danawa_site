import os
import re
import hashlib
import requests
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def clean_html_text(text: str) -> str:
    """HTML 엔티티 및 불필요한 공백을 정돈합니다."""
    if not text:
        return ""
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def make_news_id(url: str, title: str) -> str:
    """URL 또는 제목 기반의 고유 식별자 해시를 생성합니다."""
    # 만약 idxno가 포함된 URL이면 idxno를 활용
    match = re.search(r"idxno=(\d+)", url)
    if match:
        return f"idx_{match.group(1)}"
    # 없으면 URL 기반 MD5 해시 생성
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    return f"news_{h}"

def extract_article_details(url: str, timeout: int = 8) -> Dict[str, Any]:
    """
    기사 상세 페이지에서 본문 텍스트와 대표 이미지(og:image)를 추출합니다.
    """
    result = {
        "content": "",
        "image_url": "",
        "success": False
    }

    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return result

        # 인코딩 처리
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. 대표 이미지 추출 (og:image)
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            result["image_url"] = og_image["content"].strip()

        # 불필요한 태그 제거 (스크립트, 스타일, 광고, 주석 등)
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()

        # 2. 본문 컨테이너 탐색 (주요 언론사 표준 셀렉터 순서)
        selectors = [
            "#article-view-content-div",  # 모터그래프, 오토데일리 등 주요 전문지
            "#articleBody",               # 네이트, 동아 등
            "#dic_area",                  # 네이버 뉴스 기사 본문
            "#newsct_article",            # 네이버 뉴스 신규 레이아웃
            ".article_view",              # 다음 뉴스
            ".article-content",           # 범용
            ".news_cnt",                  # 범용
            "#article_body"               # 범용
        ]

        article_div = None
        for sel in selectors:
            found = soup.select_one(sel)
            if found and len(found.get_text(strip=True)) > 150:
                article_div = found
                break

        if article_div:
            # 본문 내부 추가 불필요 요소 제거 (기자 정보, 저작권, 관련 기사 등)
            for sub_tag in article_div.select(".byline, .copyright, .reporter_area, .sns_share, table, figure figcaption"):
                sub_tag.decompose()
            text = article_div.get_text(separator="\n", strip=True)
        else:
            # 셀렉터로 찾지 못한 경우 <p> 태그 수집 fallback
            paragraphs = []
            for p in soup.find_all("p"):
                p_text = p.get_text(strip=True)
                if len(p_text) > 40 and "저작권" not in p_text and "구독" not in p_text:
                    paragraphs.append(p_text)
            text = "\n\n".join(paragraphs)

        # 정돈
        cleaned_lines = []
        for line in text.split("\n"):
            line = line.strip()
            # 저작권, 이메일, 기자 서명 등 제외
            if not line or "@" in line or "무단 전재" in line or "기자 =" in line or "기자]" in line:
                continue
            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        if len(cleaned_text) >= 100:
            result["content"] = cleaned_text
            result["success"] = True

    except Exception as e:
        print(f"    [기사 본문 파싱 경고] {url} 추출 실패 ({e})")

    return result

def fetch_rss_news(source_name: str, feed_url: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    지정된 RSS 피드에서 최신 기사 목록을 수집합니다.
    """
    news_items = []
    try:
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            return news_items

        for entry in feed.entries[:limit]:
            title = clean_html_text(entry.get("title", ""))
            link = entry.get("link", "").strip()
            published = entry.get("published", "") or entry.get("updated", "")
            summary = clean_html_text(entry.get("summary", "") or entry.get("description", ""))

            if not title or not link:
                continue

            news_id = make_news_id(link, title)

            news_items.append({
                "news_id": news_id,
                "title": title,
                "link": link,
                "source": source_name,
                "published": published,
                "summary": summary
            })

    except Exception as e:
        print(f"  [오류] RSS 피드 파싱 실패 ({source_name}: {feed_url}): {e}")

    return news_items

def fetch_all_latest_news(sources: List[Dict[str, Any]], check_limit: int = 5) -> List[Dict[str, Any]]:
    """
    설정된 뉴스 소스 목록을 순회하며 최신 기사를 수집합니다.
    """
    all_news = []
    for src in sources:
        if not src.get("enabled", True):
            continue

        name = src.get("name", "알 수 없음")
        feed_url = src.get("feed_url")
        if not feed_url:
            continue

        print(f"▶ 뉴스 소스 확인 중: {name}")
        items = fetch_rss_news(name, feed_url, limit=check_limit)
        print(f"  - 최신 기사 {len(items)}개 확인됨")
        all_news.extend(items)

    return all_news
