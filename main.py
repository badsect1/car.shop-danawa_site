import os
import sys
import time
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

# 윈도우 콘솔 cp949 인코딩 오류 방지
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 콘솔 출력을 run.log 파일에도 동시에 기록
class _Tee:
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

_log_file = open("run.log", "w", encoding="utf-8")
sys.stdout = _Tee(sys.__stdout__, _log_file)
sys.stderr = _Tee(sys.__stderr__, _log_file)

# 내부 모듈 임포트
from modules.news_collector import fetch_rss_news, extract_article_details
from modules.ai_summarizer import generate_wp_car_post
from modules.wp_publisher import WpPublisher
from modules.sheet_manager import SheetManager

CONFIG_PATH = "config.json"

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"'{CONFIG_PATH}' 설정 파일이 존재하지 않습니다.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def run_pipeline(post_count: int = 1):
    """
    최신 자동차 뉴스를 수집하고, 이미지 없는 고품질 HTML 원고를 생성하여
    car.shop-danawa.co.kr 워드프레스에 자동 포스팅합니다.
    """
    load_dotenv()
    config = load_config()

    news_sources = config.get("news_sources", [])
    sheet_cfg = config.get("google_sheet", {})
    settings = config.get("settings", {})

    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = settings.get("gemini_model", "gemini-3.5-flash-lite")
    recent_limit = settings.get("check_recent_count", 5)

    print(f"\n=======================================================")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 자동차 뉴스 수집 & car.shop-danawa.co.kr 자동 포스팅 시작")
    print(f"[*] 목표 포스팅 수: {post_count}건 (이미지 제외 모드)")
    print(f"=======================================================")

    # 1. 워드프레스 발행자 및 구글 시트 매니저 초기화
    wp_publisher = WpPublisher()
    published_ids = wp_publisher.get_published_news_ids()
    print(f"[*] 기존 워드프레스 발행 완료 기사 수: {len(published_ids)}개")

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    sheet_manager = SheetManager(
        service_account_file=service_account_file,
        spreadsheet_name_or_id=sheet_cfg.get("spreadsheet_name_or_id", "1jZSjAFltM0g2d2dmQx8MIV7H4QF8sdJGMfGz--tQEp0"),
        worksheet_name=sheet_cfg.get("worksheet_name", "자동차_뉴스_블로그")
    )

    published_in_this_run = 0

    # 2. 뉴스 소스 순회하며 미발행 최신 기사 탐색
    for src in news_sources:
        if published_in_this_run >= post_count:
            break

        if not src.get("enabled", True):
            continue

        src_name = src.get("name", "알 수 없음")
        feed_url = src.get("feed_url")
        if not feed_url:
            continue

        print(f"\n▶ 소스 확인 중: {src_name}")
        items = fetch_rss_news(src_name, feed_url, limit=recent_limit)

        for item in items:
            if published_in_this_run >= post_count:
                break

            n_id = item["news_id"]
            n_title = item["title"]
            n_url = item["link"]
            n_summary_rss = item.get("summary", "")

            # 이미 워드프레스에 발행된 기사인지 체크
            if n_id in published_ids:
                continue

            print(f"\n  [새 기사 발견 - 포스팅 대상] {n_title}")
            print(f"  - 원문: {n_url}")

            # 3. 본문 텍스트 추출 (이미지는 배제)
            print("  - 기사 상세 본문 추출 중...")
            details = extract_article_details(n_url)
            content = details.get("content", "")

            if not content:
                content = n_summary_rss if len(n_summary_rss) > 80 else n_title
                print("  [!] 본문 추출 제한으로 RSS 요약 정보를 소스로 활용합니다.")
            else:
                print(f"  [V] 본문 추출 완료 ({len(content):,}자)")

            # 4. Gemini AI 워드프레스용 HTML 원고 생성 (이미지 없음)
            print(f"  - Gemini AI 워드프레스 원고 생성 중 (모델: {gemini_model}, 이미지 제외)...")
            try:
                ai_post = generate_wp_car_post(
                    news_title=n_title,
                    source_name=src_name,
                    article_content=content,
                    api_key=gemini_api_key,
                    model_name=gemini_model
                )
            except Exception as e:
                print(f"  [!] AI 원고 생성 실패: {e}")
                continue

            wp_title = ai_post.get("title", n_title)
            wp_slug = ai_post.get("slug", f"car-news-{int(time.time())}")
            wp_content_html = ai_post.get("content_html", "")
            wp_meta_desc = ai_post.get("meta_description", "")
            wp_summary = ai_post.get("summary", "")
            wp_tags = ai_post.get("tags", ["자동차", "신차출시"])

            # 5. 워드프레스에 자동 포스팅 (car.shop-danawa.co.kr)
            try:
                pub_res = wp_publisher.publish_post(
                    news_id=n_id,
                    title=wp_title,
                    slug=wp_slug,
                    content_html=wp_content_html,
                    tags=wp_tags,
                    meta_description=wp_meta_desc,
                    original_url=n_url
                )
                published_url = pub_res.get("post_url", "")
                published_ids.add(n_id)
                published_in_this_run += 1

                # 6. 구글 시트 및 CSV에도 저장 (상태: 발행완료)
                sheet_manager.append_news_record(
                    source_name=src_name,
                    news_title=wp_title,
                    news_url=published_url or n_url,
                    news_id=n_id,
                    summary=wp_summary,
                    blog_post=wp_content_html,
                    status="발행완료(워드프레스)"
                )

                time.sleep(2)

            except Exception as e:
                print(f"  [!] 워드프레스 자동 발행 실패: {e}")

    print(f"\n=======================================================")
    print(f"[*] 이번 실행 완료: 총 {published_in_this_run}개의 글이 car.shop-danawa.co.kr 에 자동 발행되었습니다.")
    print(f"=======================================================\n")

def main():
    parser = argparse.ArgumentParser(description="Automotive News Auto Publisher for car.shop-danawa.co.kr")
    parser.add_argument("--post-count", type=int, default=1, help="1회 실행 시 발행할 포스트 개수 (기본값: 1)")
    parser.add_argument("--watch", action="store_true", help="지정된 간격으로 계속 실행 (백그라운드 모니터링)")
    parser.add_argument("--interval", type=int, default=720, help="모니터링 반복 간격 (분 단위, 기본값: 720분 = 12시간 / 하루 2회)")
    args = parser.parse_args()

    if args.watch:
        print(f"[알림] {args.interval}분 간격으로 신규 자동차 뉴스를 자동 발행합니다. (종료: Ctrl+C)")
        while True:
            try:
                run_pipeline(post_count=args.post_count)
            except Exception as e:
                print(f"[치명적 오류] 파이프라인 실행 중 오류 발생: {e}")
            
            print(f"다음 검사까지 {args.interval}분 대기합니다...")
            time.sleep(args.interval * 60)
    else:
        run_pipeline(post_count=args.post_count)

if __name__ == "__main__":
    main()
