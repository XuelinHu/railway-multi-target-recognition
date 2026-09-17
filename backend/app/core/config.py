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
    deepseek_vl2_model_path: str = "./models/deepseek-vl2-tiny"
    deepseek_vl2_prompt: str = "请用中文简要描述这张图片的主要内容，并列出可见目标。"
    device: str = "0"
    run_tasks_inline: bool = False
    task_worker_enabled: bool = True
    task_poll_interval_seconds: float = Field(default=1.0, gt=0)
    cors_origins: str = "http://localhost:4021,http://127.0.0.1:4021"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_default_model: str = "qwen3:14b"
    ollama_timeout_seconds: float = Field(default=15.0, gt=0)
    chat_system_prompt_zh: str = (
        "你是铁路巡检领域的智能助手，熟悉接触网、轨道、道岔、施工安全与设备运维。"
        "请用中文回答，回答简洁、专业、可执行。"
    )
    chat_system_prompt_en: str = (
        "You are an intelligent assistant for railway inspection, familiar with catenary, track, "
        "turnouts, construction safety and equipment maintenance. Answer in English, concisely and professionally."
    )
    tts_voice_zh: str = "zh_CN-huayan-medium"
    tts_voice_en: str = "en_US-lessac-medium"
    tts_voices_dir: Path = Path("./models/piper-voices")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "tts_cache"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tts_cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
