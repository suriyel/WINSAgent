"""
应用配置管理
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # LLM 配置
    dashscope_api_key: str = ""
    llm_model: str = "qwen3-72b-instruct"

    # MySQL 配置
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "wins_agent"

    # Redis 配置
    redis_url: str = "redis://localhost:6379"

    # PostgreSQL 配置 (Checkpoint)
    postgres_url: str = "postgresql://user:password@localhost:5432/langgraph"

    # FAISS 配置
    faiss_index_path: str = "./data/faiss_index"

    # 服务器配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # Agent 配置
    max_steps: int = 20
    max_retries: int = 3
    tool_timeout: int = 60
    message_token_limit: int = 4000
    recursion_limit: int = 25

    @property
    def mysql_url(self) -> str:
        return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
