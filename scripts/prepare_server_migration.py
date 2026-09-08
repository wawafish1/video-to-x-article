"""Build a private migration archive for the server deployment.

The archive contains .env plus runtime data, so it is deliberately Git-ignored
and must never be uploaded to a public repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import zipfile


ROOT_DIR = Path(__file__).resolve().parents[1]
PATH_COLUMNS = {
    "video_path": "uploads",
    "audio_path": "outputs",
    "raw_transcript_path": "outputs",
    "cleaned_transcript_path": "outputs",
    "article_path": "outputs",
    "final_article_path": "outputs",
}


def rewrite_job_paths(db_path: Path) -> int:
    """Make saved Windows paths resolve inside the Docker data volume."""
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, " + ", ".join(PATH_COLUMNS) + " FROM jobs"
        ).fetchall()
        for row in rows:
            updates: dict[str, str] = {}
            for column, section in PATH_COLUMNS.items():
                old_path = row[column]
                if old_path:
                    updates[column] = str(
                        PurePosixPath("/app/data")
                        / section
                        / row["id"]
                        / Path(old_path).name
                    )
            if updates:
                assignments = ", ".join(f"{column} = ?" for column in updates)
                conn.execute(
                    f"UPDATE jobs SET {assignments} WHERE id = ?",
                    [*updates.values(), row["id"]],
                )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def copy_if_present(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_archive(destination: Path) -> Path:
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        raise SystemExit("未找到 .env，无法打包 API 配置。")

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video-to-x-migration-") as temp_dir:
        staging = Path(temp_dir) / "video-to-x-article-private-migration"
        data_dir = staging / "data"
        copy_if_present(env_file, staging / ".env")
        copy_if_present(ROOT_DIR / "jobs.db", data_dir / "jobs.db")
        copy_if_present(ROOT_DIR / "uploads", data_dir / "uploads")
        copy_if_present(ROOT_DIR / "outputs", data_dir / "outputs")

        migrated_jobs = rewrite_job_paths(data_dir / "jobs.db")
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in staging.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(staging))

    print(f"已创建私有迁移包：{destination}")
    print(f"已迁移任务记录：{migrated_jobs}")
    print("此文件含 API Key 和内容数据，请勿提交 GitHub 或发给他人。")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="创建视频转 X 文章的服务器迁移包")
    parser.add_argument(
        "--output",
        default=str(ROOT_DIR.parent / "video-to-x-article-private-migration.zip"),
        help="迁移 zip 的输出路径",
    )
    args = parser.parse_args()
    build_archive(Path(args.output))


if __name__ == "__main__":
    main()
