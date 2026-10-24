from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    database_schema: str = "public"
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "vmerger"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    embedding_model: str = "gemini-embedding-001"
    ai_config_file: Path | None = Path("config/ai.toml")
    app_token: str
    app_origin: str = "http://127.0.0.1:8000"
    cookie_secure: bool = False
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    scratch_dir: Path = Path(".local/scratch")
    max_upload_mb: int = 500
    max_asset_seconds: int = 600
    max_project_assets: int = 30
    max_output_seconds: int = 300
    lease_seconds: int = 120

@lru_cache
def settings() -> Settings:
    return Settings()
