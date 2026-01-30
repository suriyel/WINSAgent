"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取项目根目录（backend/）
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    # LLM
    llm_model: str = "openai:gpt-4o"
    llm_api_key: str = ""
    llm_base_url: str = ""

    # Paths
    knowledge_dir: str = str(Path(__file__).resolve().parent.parent.parent / "knowledge")
    faiss_index_dir: str = str(Path(__file__).resolve().parent.parent / "faiss_indexes")

    # MySQL (production stage)
    mysql_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def terminology_dir(self) -> str:
        return str(Path(self.knowledge_dir) / "terminology")

    @property
    def design_docs_dir(self) -> str:
        return str(Path(self.knowledge_dir) / "design_docs")


settings = Settings()
