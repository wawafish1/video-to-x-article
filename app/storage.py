from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from .config import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    db_path = get_settings().db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                template_key TEXT,
                video_path TEXT NOT NULL,
                audio_path TEXT,
                raw_transcript_path TEXT,
                cleaned_transcript_path TEXT,
                article_path TEXT,
                final_article_path TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_column(conn, "jobs", "template_key", "TEXT")
        ensure_column(conn, "jobs", "cleaned_transcript_path", "TEXT")
        ensure_column(conn, "jobs", "final_article_path", "TEXT")


def fail_interrupted_jobs() -> int:
    now = utc_now()
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                error = '应用重启导致任务中断，请重新上传视频。',
                updated_at = ?
            WHERE status IN ('queued', 'extracting', 'transcribing', 'cleaning', 'rewriting')
            """,
            (now,),
        )
    return cursor.rowcount


def ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_job(
    job_id: str, original_filename: str, video_path: Path, template_key: str
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, original_filename, template_key, video_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, "queued", original_filename, template_key, str(video_path), now, now),
        )


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return

    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]

    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def delete_job(job_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cursor.rowcount > 0


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]
