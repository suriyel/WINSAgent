"""
基础工具定义
使用 @tool 装饰器定义标准 LangChain Tools
"""

import random
from datetime import datetime
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


# ============== 知识检索工具 ==============


@tool
def search_knowledge(query: str) -> str:
    """从知识库中检索相关信息。当需要查找领域知识、文档内容或历史案例时使用此工具。

    Args:
        query: 检索查询语句，描述你需要查找的信息
    """
    from app.knowledge.retriever import get_retriever

    retriever = get_retriever()

    try:
        results = retriever.search_with_score(query, k=3)
        if not results:
            return f"未找到与 '{query}' 相关的知识库内容。"

        output = f"关于 '{query}' 的知识库检索结果：\n\n"
        for i, (doc, score) in enumerate(results, 1):
            title = doc.metadata.get("title", "未命名文档")
            output += f"{i}. [{title}] (相关度: {1-score:.2f})\n"
            output += f"   {doc.page_content[:200]}...\n\n"

        return output
    except Exception as e:
        return f"知识库检索失败: {str(e)}"


# ============== 系统状态工具 ==============


@tool
def get_system_status(system_name: str) -> str:
    """查询指定系统的运行状态。可以查询各个子系统的健康状态、资源使用情况等。

    Args:
        system_name: 系统名称，如 database, api, cache, worker 等
    """
    # 模拟不同系统的状态
    system_status = {
        "database": {
            "status": "healthy",
            "connections": random.randint(10, 50),
            "query_latency_ms": random.randint(5, 50),
        },
        "api": {
            "status": "healthy",
            "requests_per_minute": random.randint(100, 500),
            "avg_response_ms": random.randint(50, 200),
        },
        "cache": {
            "status": "healthy",
            "hit_rate": f"{random.uniform(0.85, 0.99):.2%}",
            "memory_usage": f"{random.randint(40, 80)}%",
        },
        "worker": {
            "status": "healthy",
            "active_jobs": random.randint(0, 10),
            "queue_size": random.randint(0, 100),
        },
    }

    name_lower = system_name.lower()
    if name_lower in system_status:
        info = system_status[name_lower]
        status_str = f"系统 '{system_name}' 状态: {info['status']}\n"
        for key, value in info.items():
            if key != "status":
                status_str += f"  - {key}: {value}\n"
        return status_str
    else:
        available = ", ".join(system_status.keys())
        return f"未找到系统 '{system_name}'。可用系统: {available}"


# ============== 任务管理工具 ==============


class TaskInput(BaseModel):
    """创建任务的输入参数"""

    task_name: str = Field(description="任务名称，简短描述任务内容")
    task_type: str = Field(description="任务类型，如 report, export, sync, analyze")
    priority: str = Field(default="normal", description="优先级: low, normal, high")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="任务特定参数"
    )


# 内存存储任务状态（生产环境应使用数据库）
_task_store: dict[str, dict] = {}


@tool(args_schema=TaskInput)
def create_task(
    task_name: str,
    task_type: str,
    priority: str = "normal",
    parameters: dict[str, Any] = None,
) -> str:
    """创建一个新的后台任务。用于执行耗时操作如生成报表、数据导出、数据同步等。

    创建成功后返回任务ID，可用于后续查询任务状态。
    """
    task_id = f"TASK_{task_type.upper()}_{random.randint(1000, 9999)}"

    _task_store[task_id] = {
        "id": task_id,
        "name": task_name,
        "type": task_type,
        "priority": priority,
        "parameters": parameters or {},
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "result": None,
    }

    return f"任务创建成功！\n任务ID: {task_id}\n任务名称: {task_name}\n类型: {task_type}\n优先级: {priority}"


@tool
def get_task_status(task_id: str) -> str:
    """查询任务执行状态和进度。

    Args:
        task_id: 任务ID，由 create_task 返回
    """
    if task_id in _task_store:
        task = _task_store[task_id]
        # 模拟进度更新
        if task["status"] == "pending":
            task["status"] = "running"
            task["progress"] = random.randint(10, 30)
        elif task["status"] == "running":
            task["progress"] = min(100, task["progress"] + random.randint(20, 40))
            if task["progress"] >= 100:
                task["status"] = "completed"
                task["result"] = f"{task['name']} 执行完成"

        return f"""任务状态查询结果:
- 任务ID: {task['id']}
- 名称: {task['name']}
- 状态: {task['status']}
- 进度: {task['progress']}%
- 创建时间: {task['created_at']}"""

    return f"未找到任务 '{task_id}'。请检查任务ID是否正确。"


@tool
def cancel_task(task_id: str) -> str:
    """取消指定的任务。只能取消处于 pending 或 running 状态的任务。

    Args:
        task_id: 要取消的任务ID
    """
    if task_id in _task_store:
        task = _task_store[task_id]
        if task["status"] in ["pending", "running"]:
            task["status"] = "cancelled"
            return f"任务 '{task_id}' 已成功取消。"
        else:
            return f"无法取消任务 '{task_id}'，当前状态为 {task['status']}。"

    return f"未找到任务 '{task_id}'。"


# ============== 配置查询工具 ==============


@tool
def get_user_config(config_key: str) -> str:
    """获取用户配置项。可查询用户的偏好设置、默认参数等。

    Args:
        config_key: 配置项名称，如 default_city, language, timezone, theme 等
    """
    default_configs = {
        "default_city": "北京市",
        "language": "zh-CN",
        "timezone": "Asia/Shanghai",
        "theme": "light",
        "notification_enabled": "true",
        "page_size": "20",
    }

    key_lower = config_key.lower()
    if key_lower in default_configs:
        return f"配置项 '{config_key}' 的值为: {default_configs[key_lower]}"
    else:
        available = ", ".join(default_configs.keys())
        return f"未找到配置项 '{config_key}'。可用配置项: {available}"


# ============== 数据计算工具 ==============


class CalculationInput(BaseModel):
    """计算输入参数"""
    expression: str = Field(description="数学表达式，如 '2 + 3 * 4'")


@tool(args_schema=CalculationInput)
def calculate(expression: str) -> str:
    """执行数学计算。支持基本的数学运算。

    Args:
        expression: 数学表达式，如 '2 + 3 * 4' 或 '(10 - 5) / 2'
    """
    # 安全的数学计算
    allowed_chars = set("0123456789+-*/(). ")
    if not all(c in allowed_chars for c in expression):
        return "表达式包含不允许的字符。只支持数字和 + - * / ( ) 运算符。"

    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"


# ============== 日期时间工具 ==============


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取当前日期和时间。

    Args:
        timezone: 时区，默认为 Asia/Shanghai
    """
    from datetime import datetime

    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (时区: {timezone})"


# ============== 工具注册函数 ==============


def get_default_tools() -> list[BaseTool]:
    """获取默认工具列表"""
    tools = [
        search_knowledge,
        get_system_status,
        create_task,
        get_task_status,
        cancel_task,
        get_user_config,
        calculate,
        get_current_time,
    ]

    # 注册到 Registry
    for t in tools:
        ToolRegistry.register(t)

    return tools
