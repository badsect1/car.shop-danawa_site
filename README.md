# 🚗 car.shop-danawa.co.kr 자동 포스팅 봇

최신 자동차 전문 뉴스(모터그래프, 오토데일리 등)를 크롤링하여, **이미지 없이 텍스트 중심의 고품질 칼럼형 HTML 원고**를 Google Gemini AI로 생성한 뒤, **`car.shop-danawa.co.kr` 워드프레스에 GitHub Actions를 통해 하루 2회(오전 9시 / 오후 6시) 자동으로 포스팅**하는 완전 자동화 솔루션입니다.

---

## 🌟 주요 특징

1. **이미지 제외 모드**:
   - `<img>` 태그나 사진 없이, 타이포그래피/핵심 3줄 요약 박스/소제목/스펙 리스트/에디터 총평 박스만으로 시각적으로 정갈하게 구성된 완성형 HTML 아티클을 생성합니다.
2. **하루 2회 자동 발행 (GitHub Actions)**:
   - 🌅 **오전 09:00 (KST)**: 최신 기사 1개 자동 포스팅
   - 🌇 **오후 18:00 (KST)**: 최신 기사 1개 자동 포스팅
   - 하루 총 **정확히 2개**의 글이 규칙적으로 발행됩니다.
3. **중복 발행 방지**:
   - 이미 발행된 기사는 `published_history.json`에 기록되어 중복 포스팅을 방지합니다.
4. **WP-CLI & 캐시 퍼지 연동**:
   - SSH/SFTP를 통해 워드프레스에 직접 글을 등록하고, LiteSpeed 캐시를 자동으로 비워 방문자에게 즉시 새 글이 노출됩니다.

---

## 📂 프로젝트 구조

```text
e:/youtube_summary_bot/
├── .github/workflows/
│   └── auto_car_news_post.yml  # 하루 2회 GitHub Actions 자동 실행 워크플로우
├── modules/
│   ├── news_collector.py       # 최신 자동차 뉴스 크롤러
│   ├── ai_summarizer.py        # Gemini AI 이미지 없는 HTML 원고 생성기
│   ├── wp_publisher.py         # WP-CLI over SSH 워드프레스 자동 발행기
│   └── sheet_manager.py        # 구글 시트 백업 매니저
├── .env                        # 로컬 실행용 보안 설정 (.gitignore 적용)
├── .env.example                # 설정 템플릿
├── config.json                 # 뉴스 소스 및 설정
├── published_history.json      # 발행 완료 히스토리 및 중복 방지 데이터
├── requirements.txt            # 필수 파이썬 패키지
└── main.py                     # 파이프라인 진입점
```

---

## ⚙️ GitHub Secrets 등록 가이드 (필수)

GitHub 저장소의 **[Settings] ➡️ [Secrets and variables] ➡️ [Actions] ➡️ [New repository secret]**에 아래 항목을 등록해 주세요:

| Secret 이름 | 값 | 설명 |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `AQ.Ab8RN6...` | Google Gemini API 키 (필수) |
| `SSH_PASS` | `Mega9317!@` | Hostinger SSH 비밀번호 (필수) |
| `SSH_HOST` | `145.79.25.99` | (기본값 내장되어 있어 생략 가능) |
| `SSH_PORT` | `65002` | (기본값 내장되어 있어 생략 가능) |
| `SSH_USER` | `u687833262` | (기본값 내장되어 있어 생략 가능) |
| `REMOTE_WP_PATH` | `domains/shop-danawa.co.kr/public_html/car` | (기본값 내장되어 있어 생략 가능) |
| `SITE_URL` | `https://car.shop-danawa.co.kr` | (기본값 내장되어 있어 생략 가능) |

---

## 🚀 로컬 수동 실행 방법

```powershell
# 1개 즉시 포스팅
python main.py --post-count 1

# 2개 즉시 포스팅
python main.py --post-count 2
```
