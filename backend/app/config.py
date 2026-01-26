"""
应用配置管理 (v2)

简化后的配置，适配新的 Agent 架构
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ============== LLM 配置 ==============
    dashscope_api_key: str = ""
    llm_model: str = "qwen3-72b-instruct"

    # ============== 数据库配置 ==============
    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "wins_agent"

    # Redis (用于 Checkpoint 持久化)
    redis_url: str = "redis://localhost:6379"

    # FAISS 向量存储
    faiss_index_path: str = "./data/faiss_index"

    # ============== 服务器配置 ==============
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # ============== Agent 配置 ==============
    # 上下文管理
    message_token_limit: int = 4000
    """上下文最大 token 数"""

    # Agent 执行限制
    recursion_limit: int = 50
    """LangGraph 递归限制"""

    # Human-in-the-Loop
    tools_require_approval: list[str] = [
        "write_file",
        "http_request",
        "send_email",
    ]
    """需要用户授权的工具列表"""

    require_approval_for_all_tools: bool = False
    """是否对所有工具都要求授权"""

    # ============== 数据库 URL 属性 ==============

    @property
    def mysql_url(self) -> str:
        """同步 MySQL URL"""
        return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    @property
    def mysql_async_url(self) -> str:
        """异步 MySQL URL"""
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
