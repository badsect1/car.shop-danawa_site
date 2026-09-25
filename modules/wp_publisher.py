import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Set
import paramiko

class WpPublisher:
    def __init__(
        self,
        ssh_host: Optional[str] = None,
        ssh_port: Optional[int] = None,
        ssh_user: Optional[str] = None,
        ssh_pass: Optional[str] = None,
        wp_path: Optional[str] = None,
        site_url: Optional[str] = None,
        category_id: int = 212  # "자동차 뉴스" 카테고리 ID
    ):
        self.ssh_host = ssh_host or os.getenv("SSH_HOST", "145.79.25.99")
        self.ssh_port = int(ssh_port or os.getenv("SSH_PORT", 65002))
        self.ssh_user = ssh_user or os.getenv("SSH_USER", "u687833262")
        self.ssh_pass = ssh_pass or os.getenv("SSH_PASS", "")
        self.wp_path = wp_path or os.getenv("REMOTE_WP_PATH", "domains/shop-danawa.co.kr/public_html/car")
        self.site_url = (site_url or os.getenv("SITE_URL", "https://car.shop-danawa.co.kr")).rstrip("/")
        self.category_id = category_id
        
        # 히스토리 파일 경로
        self.history_file = Path("published_history.json")
        self.history = self._load_history()

    def _load_history(self) -> Dict[str, Any]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"published_ids": [], "posts": []}

    def _save_history(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [경고] 히스토리 파일 저장 실패: {e}")

    def get_published_news_ids(self) -> Set[str]:
        """이미 발행된 기사 ID 세트를 반환합니다."""
        return set(self.history.get("published_ids", []))

    def publish_post(
        self,
        news_id: str,
        title: str,
        slug: str,
        content_html: str,
        tags: list,
        meta_description: str = "",
        original_url: str = ""
    ) -> Dict[str, Any]:
        """
        car.shop-danawa.co.kr 워드프레스에 포스트를 자동 발행합니다.
        """
        if not self.ssh_pass:
            raise ValueError("SSH_PASS 비밀번호가 설정되지 않았습니다.")

        print(f"\n🚀 워드프레스 자동 발행 시작: {title}")
        print(f"📡 서버: {self.ssh_host}:{self.ssh_port} ({self.site_url})")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_pass,
                timeout=25
            )
            print("  [V] SSH 연결 성공!")

            # 1. 임시 HTML 파일 업로드 via SFTP
            sftp = ssh.open_sftp()
            timestamp = int(time.time())
            remote_tmp_file = f"/tmp/wp_car_{timestamp}.html"
            with sftp.file(remote_tmp_file, "w") as f:
                f.write(content_html.strip())
            sftp.close()
            print(f"  [V] 원격 본문 임시 파일 생성 완료: {remote_tmp_file}")

            # 2. WP-CLI 명령어 실행
            def run_remote_cmd(cmd_str):
                full_cmd = f"export LC_ALL=en_US.UTF-8; export LANG=en_US.UTF-8; {cmd_str}"
                stdin, stdout, stderr = ssh.exec_command(full_cmd)
                return (
                    stdout.read().decode("utf-8", errors="replace") +
                    stderr.read().decode("utf-8", errors="replace")
                )

            wp_cmd_base = f"wp --path={self.wp_path} "

            # Yoast SEO 등 메타 정보 (작은따옴표 탈출)
            meta_dict = {
                "_yoast_wpseo_metadesc": meta_description,
                "_yoast_wpseo_title": f"{title} | 다나와 자동차 뉴스"
            }
            meta_json = json.dumps(meta_dict)
            import shlex

            quoted_title = shlex.quote(title)
            quoted_slug = shlex.quote(slug)
            quoted_tags = shlex.quote(",".join(tags))
            quoted_meta = shlex.quote(meta_json)

            create_cmd = (
                f"{wp_cmd_base} post create {remote_tmp_file} "
                f"--post_title={quoted_title} "
                f"--post_name={quoted_slug} "
                f"--post_category={self.category_id} "
                f"--tags_input={quoted_tags} "
                f"--post_status=publish "
                f"--meta_input={quoted_meta} "
                f"--porcelain"
            )

            out = run_remote_cmd(create_cmd).strip()

            # post_id 파싱
            post_id = None
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    post_id = int(line)
                    break

            if not post_id:
                raise RuntimeError(f"포스트 생성 실패. WP-CLI 출력: {out}")

            post_url = f"{self.site_url}/?p={post_id}"
            print(f"  🎉 워드프레스 발행 완료! (Post ID: {post_id})")
            print(f"  🔗 발행 URL: {post_url}")

            # 3. 캐시 비우기 및 임시 파일 삭제
            run_remote_cmd(f"{wp_cmd_base} litespeed-purge all; {wp_cmd_base} cache flush; rm -f {remote_tmp_file}")
            print("  [V] 캐시 초기화 및 임시 파일 정리 완료")

            # 4. 히스토리 기록
            entry = {
                "post_id": post_id,
                "news_id": news_id,
                "title": title,
                "slug": slug,
                "url": post_url,
                "original_url": original_url,
                "published_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.history["published_ids"].append(news_id)
            self.history["posts"].insert(0, entry)
            self._save_history()

            ssh.close()
            return {
                "success": True,
                "post_id": post_id,
                "post_url": post_url
            }

        except Exception as e:
            try:
                ssh.close()
            except Exception:
                pass
            print(f"  ❌ 워드프레스 발행 중 오류 발생: {e}")
            raise e
