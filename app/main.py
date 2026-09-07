from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import get_settings
from .rewrite import (
    clean_transcript,
    generate_article_bundle,
    list_templates,
    normalize_template_key,
)
from .storage import (
    create_job,
    delete_job,
    fail_interrupted_jobs,
    get_job,
    init_db,
    list_jobs,
    update_job,
)
from .transcribe import extract_audio, transcribe_audio


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    fail_interrupted_jobs()
    yield


app = FastAPI(title="视频转 X 文章工作台", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=settings.root_dir / "static"), name="static")


class FinalArticleRequest(BaseModel):
    content: str


@app.get("/")
def index():
    html = (settings.root_dir / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "api_configured": bool(settings.openai_api_key),
        "text_model": settings.text_model,
        "transcription_model": settings.transcription_model,
    }


@app.get("/api/templates")
def api_list_templates():
    return {"templates": list_templates(), "default": "market"}


@app.get("/api/jobs")
def api_list_jobs():
    return {"jobs": list_jobs()}


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@app.get("/api/jobs/{job_id}/content")
def api_get_job_content(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job": job,
        "content": {
            "raw": read_text_path(job.get("raw_transcript_path")),
            "cleaned": read_text_path(job.get("cleaned_transcript_path")),
            "article": read_text_path(job.get("article_path")),
            "final": read_text_path(job.get("final_article_path")),
        },
    }


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for base_dir in (settings.uploads_dir, settings.outputs_dir):
        base_path = base_dir.resolve()
        target_path = (base_path / job_id).resolve()
        if base_path not in target_path.parents:
            raise HTTPException(status_code=400, detail="Invalid job path")
        if target_path.exists():
            shutil.rmtree(target_path)

    delete_job(job_id)
    return {"ok": True}


@app.post("/api/jobs")
async def api_create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    template_key: str = Form("market"),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择视频文件")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
        raise HTTPException(status_code=400, detail="仅支持常见视频格式")

    normalized_template = normalize_template_key(template_key)
    job_id = uuid4().hex
    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / f"original{suffix}"
    max_upload_bytes = settings.max_upload_mb * 1024 * 1024
    uploaded_bytes = 0

    try:
        with video_path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                uploaded_bytes += len(chunk)
                if uploaded_bytes > max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"视频不能超过 {settings.max_upload_mb} MB",
                    )
                target.write(chunk)
        if uploaded_bytes == 0:
            raise HTTPException(status_code=400, detail="视频文件不能为空")
    except Exception:
        video_path.unlink(missing_ok=True)
        job_dir.rmdir()
        raise
    finally:
        await file.close()

    create_job(job_id, file.filename, video_path, normalized_template)
    background_tasks.add_task(process_job, job_id)
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/final")
def api_save_final_article(job_id: str, payload: FinalArticleRequest):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = settings.outputs_dir / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "final_article.md"
    final_path.write_text(payload.content, encoding="utf-8")
    update_job(job_id, final_article_path=str(final_path))
    return {"ok": True, "final_article_path": str(final_path)}


@app.get("/api/jobs/{job_id}/download/{kind}")
def download_job_file(job_id: str, kind: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    path_by_kind = {
        "raw": job.get("raw_transcript_path"),
        "cleaned": job.get("cleaned_transcript_path"),
        "article": job.get("article_path"),
        "final": job.get("final_article_path"),
    }
    file_path = path_by_kind.get(kind)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, filename=Path(file_path).name)


def process_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return

    output_dir = settings.outputs_dir / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = Path(job["video_path"])
    template_key = normalize_template_key(job.get("template_key"))
    audio_path = output_dir / "audio.mp3"
    chunks_dir = output_dir / "chunks"
    raw_path = output_dir / "raw_transcript.txt"
    cleaned_path = output_dir / "cleaned_transcript.md"
    article_path = output_dir / "x_article_bundle.md"

    try:
        update_job(job_id, status="extracting", error=None)
        extract_audio(video_path, audio_path)
        update_job(job_id, audio_path=str(audio_path), status="transcribing")

        transcript = transcribe_audio(audio_path, chunks_dir)
        raw_path.write_text(transcript, encoding="utf-8")
        update_job(job_id, raw_transcript_path=str(raw_path), status="cleaning")

        cleaned = clean_transcript(transcript, template_key)
        cleaned_path.write_text(cleaned, encoding="utf-8")
        update_job(
            job_id,
            cleaned_transcript_path=str(cleaned_path),
            status="rewriting",
        )

        article = generate_article_bundle(cleaned, template_key)
        article_path.write_text(article, encoding="utf-8")
        update_job(job_id, article_path=str(article_path), status="completed")
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))


def read_text_path(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
