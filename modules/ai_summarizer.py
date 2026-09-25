import os
import re
import json
import time
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types

# 안정적인 모델 우선순위 리스트
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash"
]

WP_HTML_SYSTEM_PROMPT = """당신은 10년 차 자동차 전문 웹진 수석 에디터이자 SEO(검색 최적화) 전문가입니다.
제공된 자동차 최신 뉴스를 바탕으로, 워드프레스에 즉시 발행 가능한 '이미지 없는 고품질 완성형 HTML 칼럼 원고'를 작성해야 합니다.

[🚨 엄격한 제약 사항: 이미지 절대 금지]
1. <img> 태그, figure, 사진 설명, 이미지 플레이스홀더, 또는 사진 URL을 일체 포함하지 마세요. 오직 깔끔하고 정돈된 텍스트와 타이포그래피, 스타일 태그만으로 시각적 완성도를 높여야 합니다.
2. 기사 원문을 단순 복사하거나 짜깁기하지 말고, 100% 당신만의 친절하고 전문적인 블로그/매거진 경어체(~했는데요, ~살펴보겠습니다, ~알려졌습니다)로 전면 재작성(Rewriting)하세요.

[HTML 본문(content_html) 작성 가이드라인]
- 도입부에 핵심 요약 박스 포함:
  <div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 18px 20px; border-radius: 6px; margin-bottom: 25px;">
    <h3 style="margin-top: 0; margin-bottom: 10px; color: #1e293b; font-size: 1.1rem;">⚡ 이번 소식 핵심 3줄 요약</h3>
    <ul style="margin: 0; padding-left: 20px; line-height: 1.8; color: #334155;">
      <li>...</li>
      <li>...</li>
      <li>...</li>
    </ul>
  </div>
- 섹션 구성:
  - <h2>...</h2> 및 <h3>...</h3> 태그로 주제별 문단 구분
  - <p style="line-height: 1.85; margin-bottom: 18px; color: #334155;">...</p> 문단 구성
  - 핵심 제원 및 스펙은 <ul><li>...</li></ul> 또는 깔끔한 표 활용
  - 말미에 "💡 에디터 구매 가이드 & 총평" 섹션 및 추천 대상자 박스 구성

반드시 다음 JSON 형식으로만 정확하게 응답하세요 (JSON 외에 다른 잡담은 일체 출력하지 마세요):
{
  "title": "클릭률(CTR)과 검색(SEO) 모두 잡는 매력적인 메인 제목",
  "slug": "url-friendly-english-slug-like-bentley-torcal-ev-suv",
  "meta_description": "검색엔진 결과에 표시될 140자 내외의 흥미로운 본문 요약",
  "summary": "핵심 3줄 요약 (텍스트)",
  "content_html": "<p>완성된 HTML 본문 전체...</p>",
  "tags": ["자동차", "신차출시", "차량명", "전기차"]
}
"""

def _clean_json_response(raw_text: str) -> str:
    """마크다운 백틱 등 JSON 파싱을 방해하는 텍스트를 정돈합니다."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

def _robust_parse_json(text: str) -> Dict[str, Any]:
    """표준 json.loads 시도 후 실패 시 정규식 기반으로 필드를 안전하게 추출합니다."""
    cleaned = _clean_json_response(text)
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    data = {}
    
    # 1. title
    title_m = re.search(r'"title"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)
    data["title"] = title_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore") if title_m else "자동차 최신 뉴스"

    # 2. slug
    slug_m = re.search(r'"slug"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)
    if slug_m:
        raw_slug = slug_m.group(1).strip().lower()
        data["slug"] = re.sub(r"[^a-z0-9\-]", "-", raw_slug).strip("-")
    else:
        data["slug"] = f"car-news-{int(time.time())}"

    # 3. meta_description
    meta_m = re.search(r'"meta_description"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)
    data["meta_description"] = meta_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore") if meta_m else ""

    # 4. summary
    sum_m = re.search(r'"summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)
    data["summary"] = sum_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore") if sum_m else ""

    # 5. content_html
    content_m = re.search(r'"content_html"\s*:\s*"(.*?)",?\s*"tags"', cleaned, re.DOTALL)
    if content_m:
        c_str = content_m.group(1)
        c_str = c_str.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
        data["content_html"] = c_str
    else:
        data["content_html"] = f"<p>{cleaned}</p>"

    # 6. tags
    tags_m = re.search(r'"tags"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
    if tags_m:
        raw_tags = re.findall(r'"([^"]*(?:\\.[^"]*)*)"', tags_m.group(1))
        data["tags"] = [t.encode("utf-8").decode("unicode_escape", errors="ignore") for t in raw_tags]
    else:
        data["tags"] = ["자동차", "신차출시", "자동차뉴스"]

    return data

def generate_wp_car_post(
    news_title: str,
    source_name: str,
    article_content: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    워드프레스(car.shop-danawa.co.kr) 자동 포스팅용 HTML 원고를 생성합니다 (이미지 없음).
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

    truncated_content = article_content[:30000] if article_content else "기사 본문이 없습니다."

    user_content = f"""[뉴스 기사 정보]
- 출처/언론사: {source_name}
- 기사 원제: {news_title}

[기사 본문]
{truncated_content}

위 뉴스의 팩트를 바탕으로, 이미지 없이 텍스트와 타이포그래피만으로 가독성을 극대화한 워드프레스 완성형 HTML 포스트를 작성해 주세요."""

    client = genai.Client(api_key=key)

    candidate_models = []
    if model_name:
        candidate_models.append(model_name)
    for m in FALLBACK_MODELS:
        if m not in candidate_models:
            candidate_models.append(m)

    last_error = None

    for target_model in candidate_models:
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=WP_HTML_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.7,
                )
            )

            raw_text = response.text.strip()
            data = _robust_parse_json(raw_text)

            # 슬러그 검증 및 중복 방지 타임스탬프 보정
            slug = data.get("slug", "car-news")
            slug = re.sub(r"[^a-zA-Z0-9\-]", "-", slug).strip("-").lower()
            if not slug or len(slug) < 3:
                slug = f"car-news-{int(time.time())}"
            data["slug"] = slug

            return data

        except Exception as e:
            err_msg = str(e)
            last_error = e
            if "503" in err_msg or "404" in err_msg or "UNAVAILABLE" in err_msg:
                print(f"    [모델 전환] {target_model} 일시적 사용 불가 -> 다음 모델로 전환 시도 중...")
                time.sleep(1)
                continue
            else:
                print(f"  [오류] Gemini AI 워드프레스 원고 생성 중 예외 ({target_model}): {e}")
                time.sleep(1)
                continue

    raise RuntimeError(f"모든 AI 모델에서 원고 생성 실패: {last_error}")

# 기존 구글 시트용 함수 호환 유지
def summarize_news_and_create_blog_post(
    news_title: str,
    source_name: str,
    article_content: str,
    image_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> Dict[str, str]:
    data = generate_wp_car_post(
        news_title=news_title,
        source_name=source_name,
        article_content=article_content,
        api_key=api_key,
        model_name=model_name
    )
    return {
        "summary": data.get("summary", ""),
        "blog_post": f"제목: {data.get('title')}\n\n{data.get('content_html')}"
    }

def summarize_and_create_blog_post(
    video_title: str,
    channel_name: str,
    transcript_text: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> Dict[str, str]:
    return summarize_news_and_create_blog_post(
        news_title=video_title,
        source_name=channel_name,
        article_content=transcript_text,
        api_key=api_key,
        model_name=model_name
    )
