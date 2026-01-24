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

    # Redis 配置 (用于 Checkpoint 持久化)
    redis_url: str = "redis://localhost:6379"

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

    # Human-in-the-Loop 配置
    # 需要用户授权的工具列表（工具名），空列表表示所有工具都需要授权
    tools_require_approval: list[str] = []
    # 是否对所有工具都要求授权
    require_approval_for_all_tools: bool = False

    # 动态重规划配置
    replan_enabled: bool = True  # 是否启用重规划功能
    max_replans: int = 3  # 最大重规划次数
    goal_evaluation_enabled: bool = True  # 是否启用目标提前达成检测
    replan_on_max_retries: bool = True  # 达到最大重试次数时是否触发重规划

    @property
    def mysql_url(self) -> str:
        """同步 MySQL URL"""
        return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    @property
    def mysql_async_url(self) -> str:
        """异步 MySQL URL"""
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
