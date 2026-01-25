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


# ============== 文件操作工具 ==============

@tool
def read_file(file_path: str) -> str:
    """读取文件内容。

    Args:
        file_path: 文件路径
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"文件 '{file_path}' 读取成功。内容长度: {len(content)} 字符。"
    except FileNotFoundError:
        return f"文件 '{file_path}' 不存在。"
    except Exception as e:
        return f"读取文件失败: {str(e)}"


@tool
def write_file(file_path: str, content: str, mode: str = "write") -> str:
    """写入文件内容。

    Args:
        file_path: 文件路径
        content: 要写入的内容
        mode: 写入模式 (write/append)
    """
    try:
        file_mode = 'w' if mode == "write" else 'a'
        with open(file_path, file_mode, encoding='utf-8') as f:
            f.write(content)
        return f"文件 '{file_path}' 写入成功。模式: {mode}。"
    except Exception as e:
        return f"写入文件失败: {str(e)}"


# ============== 数据转换工具 ==============

class JsonToYamlInput(BaseModel):
    """JSON 转 YAML 输入参数"""
    json_string: str = Field(description="要转换的 JSON 字符串")


@tool(args_schema=JsonToYamlInput)
def json_to_yaml(json_string: str) -> str:
    """将 JSON 字符串转换为 YAML 格式。

    Args:
        json_string: JSON 格式的字符串
    """
    try:
        import json
        data = json.loads(json_string)
        import yaml
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        return f"转换成功！\n\n{yaml_str}"
    except json.JSONDecodeError as e:
        return f"JSON 解析失败: {str(e)}"
    except Exception as e:
        return f"转换失败: {str(e)}"


class CsvToJsonInput(BaseModel):
    """CSV 转 JSON 输入参数"""
    csv_data: str = Field(description="CSV 格式的数据，使用逗号分隔")
    has_header: bool = Field(default=True, description="第一行是否为表头")


@tool(args_schema=CsvToJsonInput)
def csv_to_json(csv_data: str, has_header: bool = True) -> str:
    """将 CSV 数据转换为 JSON 格式。

    Args:
        csv_data: CSV 格式的字符串
        has_header: 第一行是否为表头
    """
    try:
        import json
        lines = csv_data.strip().split('\n')
        if not lines:
            return "CSV 数据为空。"

        result = []
        headers = []

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            values = line.split(',')

            if has_header and i == 0:
                headers = values
                continue

            if headers:
                result.append(dict(zip(headers, values)))
            else:
                result.append(values)

        return f"转换成功！\n\n{json.dumps(result, ensure_ascii=False, indent=2)}"
    except Exception as e:
        return f"转换失败: {str(e)}"


# ============== 数据分析工具 ==============

class StatisticsInput(BaseModel):
    """统计分析输入参数"""
    data: str = Field(description="要分析的数据，用逗号分隔的数字列表")


@tool(args_schema=StatisticsInput)
def calculate_statistics(data: str) -> str:
    """计算数据的统计信息。

    Args:
        data: 用逗号分隔的数字列表，如 "1,2,3,4,5"
    """
    try:
        numbers = [float(x.strip()) for x in data.split(',') if x.strip()]
        if not numbers:
            return "数据为空，无法计算统计信息。"

        count = len(numbers)
        total = sum(numbers)
        avg = total / count
        maximum = max(numbers)
        minimum = min(numbers)
        sorted_numbers = sorted(numbers)
        median = sorted_numbers[count // 2] if count % 2 == 1 else (sorted_numbers[count // 2 - 1] + sorted_numbers[count // 2]) / 2

        result = f"""统计结果：
- 数据个数: {count}
- 总和: {total}
- 平均值: {avg:.2f}
- 最大值: {maximum}
- 最小值: {minimum}
- 中位数: {median:.2f}"""

        if count > 1:
            variance = sum((x - avg) ** 2 for x in numbers) / count
            std_dev = variance ** 0.5
            result += f"- 标准差: {std_dev:.2f}"

        return result
    except ValueError as e:
        return f"数据格式错误: {str(e)}"
    except Exception as e:
        return f"计算失败: {str(e)}"


# ============== 网络请求工具 ==============

class HttpRequestInput(BaseModel):
    """HTTP 请求输入参数"""
    url: str = Field(description="目标 URL")
    method: str = Field(default="GET", description="HTTP 方法: GET, POST, PUT, DELETE")
    headers: str = Field(default="", description="请求头（JSON 格式）")
    body: str = Field(default="", description="请求体（仅 POST/PUT）")


@tool(args_schema=HttpRequestInput)
def http_request(url: str, method: str = "GET", headers: str = "", body: str = "") -> str:
    """发送 HTTP 请求。

    Args:
        url: 目标 URL
        method: HTTP 方法
        headers: 请求头（JSON 格式）
        body: 请求体
    """
    try:
        import httpx

        header_dict = {}
        if headers:
            import json
            header_dict = json.loads(headers)

        response = httpx.request(
            method=method,
            url=url,
            headers=header_dict,
            content=body.encode() if body else None,
            timeout=10.0
        )

        result = f"""HTTP 请求成功！
- 状态码: {response.status_code}
- 响应头: {dict(response.headers)}
- 响应内容: {response.text[:500] if len(response.text) > 500 else response.text}"""

        return result
    except httpx.TimeoutException:
        return "请求超时（10秒）。"
    except Exception as e:
        return f"请求失败: {str(e)}"


# ============== 邮件发送工具 ==============

class EmailInput(BaseModel):
    """邮件发送输入参数"""
    to_email: str = Field(description="收件人邮箱")
    subject: str = Field(description="邮件主题")
    body: str = Field(description="邮件正文")
    cc_emails: str = Field(default="", description="抄送邮箱（用逗号分隔）")


@tool(args_schema=EmailInput)
def send_email(to_email: str, subject: str, body: str, cc_emails: str = "") -> str:
    """发送邮件（模拟）。

    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
        cc_emails: 抄送邮箱
    """
    try:
        cc_list = [email.strip() for email in cc_emails.split(',') if email.strip()] if cc_emails else []

        result = f"""邮件发送成功（模拟）！
- 收件人: {to_email}
- 抄送: {', '.join(cc_list) if cc_list else '无'}
- 主题: {subject}
- 正文: {body[:100]}{'...' if len(body) > 100 else ''}"""

        return result
    except Exception as e:
        return f"发送失败: {str(e)}"


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
        read_file,
        write_file,
        json_to_yaml,
        csv_to_json,
        calculate_statistics,
        http_request,
        send_email,
    ]

    # 注册到 Registry
    for t in tools:
        ToolRegistry.register(t)

    return tools
