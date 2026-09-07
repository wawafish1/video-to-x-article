from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from openai import OpenAI

from .config import get_settings


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "未找到 ffmpeg。请先安装 ffmpeg，并确保 ffmpeg 已加入系统 PATH。"
        )
    return ffmpeg


def run_ffmpeg(args: list[str]) -> None:
    ffmpeg = require_ffmpeg()
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or "ffmpeg 执行失败"
        raise RuntimeError(message)


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(audio_path),
        ]
    )
    return audio_path


def split_audio_if_needed(audio_path: Path, chunks_dir: Path) -> list[Path]:
    settings = get_settings()
    max_bytes = settings.max_transcription_mb * 1024 * 1024
    if audio_path.stat().st_size <= max_bytes:
        return [audio_path]

    chunks_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunks_dir / "chunk_%03d.mp3"
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            "600",
            "-c",
            "copy",
            str(pattern),
        ]
    )

    chunks = sorted(chunks_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("音频文件过大，自动切分失败。")
    return chunks


def _extract_text(transcription: object) -> str:
    if isinstance(transcription, str):
        return transcription
    text = getattr(transcription, "text", None)
    if isinstance(text, str):
        return text
    return str(transcription)


def transcribe_audio(audio_path: Path, chunks_dir: Path) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY。请复制 .env.example 为 .env 并填写。")

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)
    chunks = split_audio_if_needed(audio_path, chunks_dir)
    pieces: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        with chunk.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=settings.transcription_model,
                file=audio_file,
            )
        text = _extract_text(transcription).strip()
        pieces.append(f"[片段 {index}]\n{text}" if len(chunks) > 1 else text)

    return "\n\n".join(pieces).strip()
