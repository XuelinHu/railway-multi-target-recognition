from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Railway Multi-Target Recognition API"
    data_dir: Path = Path("./data")
    database_url: str = "postgresql+psycopg://deipss:CHANGE_ME@127.0.0.1:5432/railway_recognition"
    inference_backend: str = Field(default="mock", pattern="^(mock|ultralytics|tensorrt)$")
    model_path: str = ""
    device: str = "0"
    run_tasks_inline: bool = False
    task_worker_enabled: bool = True
    task_poll_interval_seconds: float = Field(default=1.0, gt=0)
    cors_origins: str = "http://localhost:4004,http://127.0.0.1:4004"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
