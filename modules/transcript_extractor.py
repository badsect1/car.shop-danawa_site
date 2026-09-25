import re
import os
import sys
import subprocess
import tempfile
from typing import Optional
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript
)

# cookies.txt 파일 경로 (프로젝트 루트 기준)
COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")


def _extract_via_yt_dlp(video_id: str) -> Optional[str]:
    """
    yt-dlp를 이용해 cookies.txt 파일로 자막을 추출합니다.
    youtube-transcript-api가 IP 차단될 때의 폴백(fallback) 방법입니다.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", "ko,ko-KR,en",
            "--sub-format", "vtt",
            "--output", output_template,
            "--quiet",
            "--no-warnings",
        ]

        # cookies.txt가 있으면 우선 사용, 없으면 브라우저 쿠키 시도
        if os.path.exists(COOKIES_FILE):
            cmd += ["--cookies", COOKIES_FILE]
        else:
            # 폴백: Edge → Chrome 순으로 브라우저 쿠키 시도
            for browser in ["edge", "chrome"]:
                cmd_try = cmd + ["--cookies-from-browser", browser, url]
                try:
                    result = subprocess.run(
                        cmd_try, capture_output=True, text=True,
                        timeout=60, encoding="utf-8", errors="replace"
                    )
                    stderr_text = result.stderr or ""
                    if "Could not copy" in stderr_text:
                        continue
                    # 성공 시 vtt 파일 읽기
                    text = _read_vtt_from_dir(tmpdir, video_id)
                    if text:
                        return text
                except Exception:
                    continue
            return None

        cmd.append(url)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=60, encoding="utf-8", errors="replace"
            )
        except subprocess.TimeoutExpired:
            print(f"  [경고] yt-dlp 자막 추출 타임아웃 (video_id: {video_id})")
            return None
        except Exception as e:
            print(f"  [경고] yt-dlp 실행 오류: {e}")
            return None

        return _read_vtt_from_dir(tmpdir, video_id)


def _read_vtt_from_dir(tmpdir: str, video_id: str) -> Optional[str]:
    """tmpdir 안에서 vtt 파일을 찾아 텍스트로 파싱합니다."""
    for lang in ["ko", "ko-KR", "en"]:
        vtt_file = os.path.join(tmpdir, f"{video_id}.{lang}.vtt")
        if not os.path.exists(vtt_file):
            # 자동생성 자막은 파일명이 다를 수 있음 (예: videoID.ko.vtt, videoID.ko-KR.vtt 등)
            for f in os.listdir(tmpdir):
                if f.endswith(".vtt") and ("ko" in f or "en" in f):
                    vtt_file = os.path.join(tmpdir, f)
                    break
            else:
                continue

        text = _parse_vtt(vtt_file)
        if text:
            return text
    return None


def _parse_vtt(vtt_path: str) -> Optional[str]:
    """VTT 자막 파일을 파싱하여 순수 텍스트만 추출합니다."""
    try:
        with open(vtt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        lines = content.splitlines()
        text_parts = []
        seen = set()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and clean not in seen:
                seen.add(clean)
                text_parts.append(clean)

        return " ".join(text_parts) if text_parts else None
    except Exception:
        return None


def extract_transcript(video_id: str, preferred_languages: list = None) -> Optional[str]:
    """
    유튜브 영상의 자막(대본)을 추출합니다.
    1순위: youtube-transcript-api (빠름, API 할당량 없음)
    2순위: yt-dlp + cookies.txt (IP 차단 우회, 가장 안정적)
    """
    if preferred_languages is None:
        preferred_languages = ["ko", "ko-KR", "en", "en-US"]

    # ── 1순위: youtube-transcript-api ──────────────────────────────
    ytt = None
    try:
        ytt = YouTubeTranscriptApi()
    except Exception:
        pass

    try:
        transcript_list = None
        if ytt and hasattr(ytt, "list"):
            transcript_list = ytt.list(video_id)
        elif hasattr(YouTubeTranscriptApi, "list_transcripts"):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        if transcript_list:
            transcript = None
            for finder in [
                lambda: transcript_list.find_manually_created_transcript(["ko", "ko-KR"]),
                lambda: transcript_list.find_generated_transcript(["ko", "ko-KR"]),
                lambda: transcript_list.find_transcript(preferred_languages),
            ]:
                try:
                    transcript = finder()
                    break
                except Exception:
                    pass

            if not transcript:
                try:
                    for t in transcript_list:
                        transcript = t
                        break
                except Exception:
                    pass

            if transcript:
                data = transcript.fetch()
                text_parts = []
                for item in data:
                    t_text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                    if t_text:
                        text_parts.append(t_text)
                full_text = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
                if full_text:
                    return full_text

        # fetch 직접 시도
        if ytt and hasattr(ytt, "fetch"):
            fetched = ytt.fetch(video_id, languages=preferred_languages)
            text_parts = [
                getattr(i, "text", "") if hasattr(i, "text") else i.get("text", "")
                for i in fetched
            ]
            result = " ".join([t for t in text_parts if t]).strip()
            if result:
                return result

    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"  [안내] 자막 없음 또는 비활성화 (video_id: {video_id})")
        return None
    except CouldNotRetrieveTranscript:
        print(f"  [!] IP 차단 감지 → yt-dlp + cookies.txt 방식으로 재시도 중...")
    except Exception as e:
        print(f"  [!] 자막 추출 오류 → yt-dlp로 재시도 중... ({type(e).__name__})")

    # ── 2순위: yt-dlp + cookies.txt ────────────────────────────────
    cookies_info = f"cookies.txt {'[있음]' if os.path.exists(COOKIES_FILE) else '[없음, 브라우저 쿠키 시도]'}"
    print(f"  [yt-dlp] {cookies_info} 자막 추출 시도 중...")
    result = _extract_via_yt_dlp(video_id)
    if result:
        print(f"  [yt-dlp] 자막 추출 성공!")
        return result

    print(f"  [!] 자막 추출 최종 실패 (video_id: {video_id})")
    return None
