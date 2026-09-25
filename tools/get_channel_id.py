"""
유튜브 핸들(@아이디) 또는 URL을 입력하면 24자리 Channel ID(UC...)를 자동으로 찾아주는 도구입니다.
사용법:
    python tools/get_channel_id.py @motorian2585
    python tools/get_channel_id.py https://www.youtube.com/@HanSangKi
"""
import sys
import re
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

def resolve_channel_id(input_str: str) -> str:
    input_str = input_str.strip()
    if input_str.startswith("UC") and len(input_str) == 24:
        return input_str

    if not input_str.startswith("http"):
        if input_str.startswith("@"):
            url = f"https://www.youtube.com/{input_str}"
        else:
            url = f"https://www.youtube.com/@{input_str}"
    else:
        url = input_str

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        for pattern in [
            r'\"externalId\":\"(UC[a-zA-Z0-9_-]{22})\"',
            r'itemprop=\"channelId\" content=\"(UC[a-zA-Z0-9_-]{22})\"',
            r'\"browseId\":\"(UC[a-zA-Z0-9_-]{22})\"',
            r'channel/(UC[a-zA-Z0-9_-]{22})'
        ]:
            m = re.search(pattern, r.text)
            if m:
                return m.group(1)
    except Exception as e:
        print(f"오류 발생: {e}")

    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python tools/get_channel_id.py <핸들 또는 채널URL>")
        sys.exit(1)

    target = sys.argv[1]
    cid = resolve_channel_id(target)
    if cid:
        print(f"[성공] Channel ID: {cid}")
    else:
        print("[실패] 채널 ID를 찾지 못했습니다.")
