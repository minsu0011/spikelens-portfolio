from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://spikelens@127.0.0.1:55440/spikelens"
    redis_url: str = "redis://127.0.0.1:56380/0"
    upload_dir: Path = Path("../storage/uploads")
    cors_origins: str = "http://localhost:3200,http://127.0.0.1:3200"
    cookie_secure: bool = False
    session_ttl_seconds: int = 86400
    max_upload_bytes: int = 10 * 1024 * 1024
    max_upload_rows: int = 20000
    job_lease_seconds: int = 120
    max_job_attempts: int = 3
    summary_cache_ttl: int = 60

    @property
    def allowed_origins(self) -> list[str]:
        return [
            value.strip().rstrip("/") for value in self.cors_origins.split(",") if value.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
