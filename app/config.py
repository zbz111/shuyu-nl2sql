"""全局配置：环境变量 / .env，代码中不出现硬编码密钥。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "数语 · 自然语言数据分析"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8010

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 8 * 60
    admin_username: str = "admin"
    admin_password: str = "admin123"

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    upload_dir: Path = BASE_DIR / "data" / "datasources"

    # 模型
    llm_provider: str = "ollama"  # ollama | openai
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    openai_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_chat_model: str = "deepseek-chat"
    temperature: float = 0.0
    max_tokens: int = 800

    # 查询安全
    max_rows: int = 500
    query_timeout_seconds: int = 20
    max_retry: int = 2
    schema_sample_rows: int = 3

    # 数据源
    allow_local_sqlite_upload: bool = True
    allow_remote_datasource: bool = True


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
