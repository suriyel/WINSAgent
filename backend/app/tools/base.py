"""
基础工具定义
使用 @tool 装饰器定义标准 LangChain Tools
"""

from typing import Any
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field


class ToolRegistry:
    """工具注册中心"""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool_instance: BaseTool):
        """注册工具"""
        cls._tools[tool_instance.name] = tool_instance

    @classmethod
    def get(cls, name: str) -> BaseTool | None:
        """获取工具"""
        return cls._tools.get(name)

    @classmethod
    def get_all(cls) -> list[BaseTool]:
        """获取所有工具"""
        return list(cls._tools.values())

    @classmethod
    def clear(cls):
        """清空注册"""
        cls._tools.clear()


# ============== 示例工具定义 ==============


@tool
def search_knowledge(query: str) -> str:
    """从知识库中检索相关信息。

    Args:
        query: 检索查询语句
    """
    # TODO: 接入 FAISS 向量检索
    return f"知识库检索结果：关于 '{query}' 的相关信息..."


@tool
def get_system_status(system_name: str) -> str:
    """查询指定系统的运行状态。

    Args:
        system_name: 系统名称
    """
    # TODO: 接入实际系统 API
    return f"系统 '{system_name}' 运行正常，CPU: 45%, 内存: 60%"


class TaskInput(BaseModel):
    """创建任务的输入参数"""

    task_name: str = Field(description="任务名称")
    task_type: str = Field(description="任务类型")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="任务参数"
    )


@tool(args_schema=TaskInput)
def create_task(task_name: str, task_type: str, parameters: dict[str, Any]) -> str:
    """创建一个新的后台任务。

    创建指定类型的任务，返回任务ID用于后续查询。
    """
    # TODO: 接入任务调度系统
    task_id = f"TASK_{task_type.upper()}_{hash(task_name) % 10000:04d}"
    return f"任务创建成功，ID: {task_id}"


@tool
def get_task_status(task_id: str) -> str:
    """查询任务执行状态。

    Args:
        task_id: 任务ID，由 create_task 返回
    """
    # TODO: 接入任务调度系统
    return f"任务 {task_id} 执行中，进度 45%"


@tool
def get_user_config(config_key: str) -> str:
    """获取用户配置项。

    Args:
        config_key: 配置项名称
    """
    # TODO: 接入用户配置存储
    default_configs = {
        "default_city": "北京市",
        "language": "zh-CN",
        "timezone": "Asia/Shanghai",
    }
    return default_configs.get(config_key, "未设置")


def get_default_tools() -> list[BaseTool]:
    """获取默认工具列表"""
    tools = [
        search_knowledge,
        get_system_status,
        create_task,
        get_task_status,
        get_user_config,
    ]

    # 注册到 Registry
    for t in tools:
        ToolRegistry.register(t)

    return tools
