from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings:
    def __init__(self) -> None:
        load_dotenv(ROOT_DIR / ".env", override=True, encoding="utf-8-sig")

        self.root_dir = ROOT_DIR
        self.uploads_dir = ROOT_DIR / "uploads"
        self.outputs_dir = ROOT_DIR / "outputs"
        self.db_path = ROOT_DIR / "jobs.db"

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "")
        self.transcription_model = os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL", "whisper-1"
        )
        self.text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-mini")
        self.max_transcription_mb = int(os.getenv("MAX_TRANSCRIPTION_MB", "23"))
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "1024"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
