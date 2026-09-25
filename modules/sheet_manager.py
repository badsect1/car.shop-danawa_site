import os
import csv
from datetime import datetime
from typing import Set, List, Dict, Any, Optional
import gspread
from google.oauth2.service_account import Credentials

SHEET_HEADERS = [
    "등록일시",
    "출처/언론사",
    "뉴스 제목",
    "원문 URL",
    "뉴스 ID",
    "핵심 요약",
    "블로그 원고",
    "발행 상태"
]

FALLBACK_CSV = "results_backup.csv"

class SheetManager:
    def __init__(self, service_account_file: str, spreadsheet_name_or_id: str, worksheet_name: str = "자동차_뉴스_블로그"):
        self.service_account_file = service_account_file
        self.spreadsheet_name_or_id = spreadsheet_name_or_id
        self.worksheet_name = worksheet_name
        self.client = None
        self.sheet = None
        self.is_connected = False
        
        self._init_connection()

    def _init_connection(self):
        """구글 시트 연결을 시도하고, 실패 시 로컬 CSV 폴백 모드로 동작합니다."""
        if not os.path.exists(self.service_account_file):
            print(f"  [안내] 서비스 계정 파일({self.service_account_file})이 없습니다. 로컬 CSV({FALLBACK_CSV}) 모드로 동작합니다.")
            self._init_fallback_csv()
            return

        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(self.service_account_file, scopes=scopes)
            self.client = gspread.authorize(creds)

            # 스프레드시트 열기 (ID 또는 이름으로)
            try:
                if len(self.spreadsheet_name_or_id) > 30 and "/" not in self.spreadsheet_name_or_id:
                    spreadsheet = self.client.open_by_key(self.spreadsheet_name_or_id)
                elif "docs.google.com/spreadsheets" in self.spreadsheet_name_or_id:
                    spreadsheet = self.client.open_by_url(self.spreadsheet_name_or_id)
                else:
                    spreadsheet = self.client.open(self.spreadsheet_name_or_id)
            except gspread.exceptions.SpreadsheetNotFound:
                print(f"  [경고] 구글 시트 '{self.spreadsheet_name_or_id}'를 찾을 수 없습니다. 서비스 계정 이메일에 시트 공유(편집자)를 완료했는지 확인하세요.")
                self._init_fallback_csv()
                return

            # 워크시트 선택 (지정된 워크시트가 없으면 새로 생성)
            try:
                self.sheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                try:
                    self.sheet = spreadsheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=10)
                    self.sheet.append_row(SHEET_HEADERS)
                except Exception:
                    self.sheet = spreadsheet.sheet1

            # 첫 줄(헤더) 확인 및 없으면 생성
            existing_headers = self.sheet.row_values(1)
            if not existing_headers:
                self.sheet.append_row(SHEET_HEADERS)

            self.is_connected = True
            print("  [성공] 구글 스프레드시트에 정상 연결되었습니다.")
        except Exception as e:
            print(f"  [경고] 구글 시트 연결 실패 ({e}). 로컬 CSV로 백업 저장됩니다.")
            self._init_fallback_csv()

    def _init_fallback_csv(self):
        """로컬 CSV 파일이 없으면 헤더를 작성합니다."""
        if not os.path.exists(FALLBACK_CSV):
            with open(FALLBACK_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(SHEET_HEADERS)

    def get_existing_ids(self) -> Set[str]:
        """이미 시트 또는 CSV에 저장된 고유 ID(뉴스 ID 또는 Video ID) 목록을 가져옵니다."""
        ids = set()

        # 구글 시트에서 가져오기
        if self.is_connected and self.sheet:
            try:
                # 5번째 열 (col 5)
                col_values = self.sheet.col_values(5)
                for item_id in col_values[1:]:  # 헤더 제외
                    if item_id and item_id.strip():
                        ids.add(item_id.strip())
            except Exception as e:
                print(f"  [경고] 구글 시트 ID 목록 조회 실패: {e}")

        # 로컬 CSV에서도 가져오기
        if os.path.exists(FALLBACK_CSV):
            try:
                with open(FALLBACK_CSV, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    next(reader, None)  # 헤더 건너뛰기
                    for row in reader:
                        if len(row) >= 5 and row[4]:
                            ids.add(row[4].strip())
            except Exception:
                pass

        return ids

    # 하위 호환성 메서드
    def get_existing_video_ids(self) -> Set[str]:
        return self.get_existing_ids()

    def append_news_record(
        self,
        source_name: str,
        news_title: str,
        news_url: str,
        news_id: str,
        summary: str,
        blog_post: str,
        status: str = "대기"
    ):
        """새 뉴스 분석 및 블로그 원고를 구글 시트 및 로컬 CSV에 추가합니다."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [
            now_str,
            source_name,
            news_title,
            news_url,
            news_id,
            summary,
            blog_post,
            status
        ]

        # 1. 구글 시트에 추가
        if self.is_connected and self.sheet:
            try:
                self.sheet.append_row(row_data)
                print(f"  [시트 저장 완료] {news_title}")
            except Exception as e:
                print(f"  [오류] 구글 시트 행 추가 실패: {e}")

        # 2. 로컬 CSV에도 항상 백업 기록
        try:
            with open(FALLBACK_CSV, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(row_data)
            print(f"  [CSV 백업 완료] {FALLBACK_CSV} 기록")
        except Exception as e:
            print(f"  [오류] CSV 백업 쓰기 실패: {e}")

    # 하위 호환성 메서드
    def append_video_record(self, channel_name, video_title, video_url, video_id, summary, blog_post, status="대기"):
        self.append_news_record(
            source_name=channel_name,
            news_title=video_title,
            news_url=video_url,
            news_id=video_id,
            summary=summary,
            blog_post=blog_post,
            status=status
        )
