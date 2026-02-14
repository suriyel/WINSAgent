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

    # SubAgent
    subagent_model: str = ""  # 子 Agent 模型标识符，空则复用 llm_model

    # Embedding (远程 API，默认复用 LLM 配置)
    embedding_model: str = "text-embedding-v3"
    embedding_api_key: str = ""   # 空则复用 llm_api_key
    embedding_base_url: str = ""  # 空则复用 llm_base_url

    # Reranker (远程 API)
    reranker_model: str = "bge-reranker-v2-m3"
    reranker_base_url: str = ""
    reranker_api_key: str = ""
    reranker_threshold: float = 0.3  # 低于此分数拒答

    # Paths
    knowledge_dir: str = str(Path(__file__).resolve().parent.parent.parent / "knowledge")
    faiss_index_dir: str = str(Path(__file__).resolve().parent.parent / "faiss_indexes")
    skills_dir: str = str(Path(__file__).resolve().parent.parent.parent / "Skills")

    # Corpus (语料库)
    corpus_source_dir: str = str(Path(__file__).resolve().parent.parent.parent / "corpus_source")
    corpus_md_dir: str = str(Path(__file__).resolve().parent.parent.parent / "corpus_md")
    corpus_image_dir: str = str(Path(__file__).resolve().parent.parent.parent / "corpus_md" / "images")
    corpus_glossary_dir: str = str(Path(__file__).resolve().parent.parent.parent / "corpus_md" / "glossary")

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
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.llm_base_url

    @property
    def terminology_dir(self) -> str:
        return str(Path(self.knowledge_dir) / "terminology")

    @property
    def design_docs_dir(self) -> str:
        return str(Path(self.knowledge_dir) / "design_docs")


settings = Settings()
