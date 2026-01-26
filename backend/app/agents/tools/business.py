"""
业务工具集合

包含各类业务功能工具:
- 知识检索
- 系统状态查询
- 任务管理
- 数据计算
- 文件操作
- 网络请求
- 邮件发送
"""

import json
import random
from datetime import datetime
from typing import Any, Literal

from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field


# ============== 知识检索工具 ==============


@tool
def search_knowledge(query: str) -> str:
    """
    从知识库中检索相关信息。

    使用场景:
    - 需要查找领域知识时
    - 需要参考文档内容时
    - 需要了解历史案例时

    Args:
        query: 检索查询语句，描述你需要查找的信息
    """
    try:
        from app.knowledge.retriever import get_retriever

        retriever = get_retriever()
        results = retriever.search_with_score(query, k=3)

        if not results:
            return f"未找到与 '{query}' 相关的知识库内容。"

        output = f"关于 '{query}' 的知识库检索结果：\n\n"
        for i, (doc, score) in enumerate(results, 1):
            title = doc.metadata.get("title", "未命名文档")
            output += f"{i}. [{title}] (相关度: {1 - score:.2f})\n"
            output += f"   {doc.page_content[:200]}...\n\n"

        return output
    except Exception as e:
        return f"知识库检索失败: {str(e)}"


# ============== 系统状态工具 ==============


@tool
def get_system_status(system_name: str) -> str:
    """
    查询指定系统的运行状态。

    可查询的系统:
    - database: 数据库状态
    - api: API 服务状态
    - cache: 缓存状态
    - worker: 后台任务状态

    Args:
        system_name: 系统名称
    """
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


# ============== 后台任务工具 ==============

# 内存存储任务状态
_task_store: dict[str, dict] = {}


class CreateTaskInput(BaseModel):
    """创建任务输入参数"""

    task_name: str = Field(description="任务名称，简短描述任务内容")
    task_type: str = Field(
        description="任务类型，如 report, export, sync, analyze"
    )
    priority: Literal["low", "normal", "high"] = Field(
        default="normal", description="优先级"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="任务特定参数"
    )


@tool(args_schema=CreateTaskInput)
def create_task(
    task_name: str,
    task_type: str,
    priority: str = "normal",
    parameters: dict[str, Any] = None,
) -> str:
    """
    创建一个新的后台任务。

    用于执行耗时操作:
    - 生成报表
    - 数据导出
    - 数据同步
    - 数据分析

    Args:
        task_name: 任务名称
        task_type: 任务类型
        priority: 优先级
        parameters: 任务参数

    Returns:
        任务ID和创建信息
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

    return f"""任务创建成功！
- 任务ID: {task_id}
- 名称: {task_name}
- 类型: {task_type}
- 优先级: {priority}"""


@tool
def get_task_status(task_id: str) -> str:
    """
    查询任务执行状态和进度。

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

        return f"""任务状态:
- ID: {task['id']}
- 名称: {task['name']}
- 状态: {task['status']}
- 进度: {task['progress']}%
- 创建时间: {task['created_at']}"""

    return f"未找到任务 '{task_id}'。请检查任务ID是否正确。"


@tool
def cancel_task(task_id: str) -> str:
    """
    取消指定的任务。只能取消 pending 或 running 状态的任务。

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
    """
    获取用户配置项。

    可用配置:
    - default_city: 默认城市
    - language: 语言设置
    - timezone: 时区
    - theme: 主题
    - notification_enabled: 通知开关
    - page_size: 分页大小

    Args:
        config_key: 配置项名称
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


class CalculateInput(BaseModel):
    """计算输入参数"""

    expression: str = Field(description="数学表达式，如 '2 + 3 * 4'")


@tool(args_schema=CalculateInput)
def calculate(expression: str) -> str:
    """
    执行数学计算。支持基本的四则运算。

    Args:
        expression: 数学表达式，如 '2 + 3 * 4' 或 '(10 - 5) / 2'
    """
    allowed_chars = set("0123456789+-*/(). ")
    if not all(c in allowed_chars for c in expression):
        return "表达式包含不允许的字符。只支持数字和 + - * / ( ) 运算符。"

    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"


class StatisticsInput(BaseModel):
    """统计分析输入参数"""

    data: str = Field(description="用逗号分隔的数字列表，如 '1,2,3,4,5'")


@tool(args_schema=StatisticsInput)
def calculate_statistics(data: str) -> str:
    """
    计算数据的统计信息。

    返回: 个数、总和、平均值、最大/最小值、中位数、标准差

    Args:
        data: 用逗号分隔的数字列表
    """
    try:
        numbers = [float(x.strip()) for x in data.split(",") if x.strip()]
        if not numbers:
            return "数据为空，无法计算统计信息。"

        count = len(numbers)
        total = sum(numbers)
        avg = total / count
        maximum = max(numbers)
        minimum = min(numbers)
        sorted_numbers = sorted(numbers)
        median = (
            sorted_numbers[count // 2]
            if count % 2 == 1
            else (sorted_numbers[count // 2 - 1] + sorted_numbers[count // 2]) / 2
        )

        result = f"""统计结果:
- 数据个数: {count}
- 总和: {total}
- 平均值: {avg:.2f}
- 最大值: {maximum}
- 最小值: {minimum}
- 中位数: {median:.2f}"""

        if count > 1:
            variance = sum((x - avg) ** 2 for x in numbers) / count
            std_dev = variance**0.5
            result += f"\n- 标准差: {std_dev:.2f}"

        return result
    except ValueError as e:
        return f"数据格式错误: {str(e)}"
    except Exception as e:
        return f"计算失败: {str(e)}"


# ============== 时间工具 ==============


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """
    获取当前日期和时间。

    Args:
        timezone: 时区，默认为 Asia/Shanghai
    """
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (时区: {timezone})"


# ============== 文件操作工具 ==============


@tool
def read_file(file_path: str) -> str:
    """
    读取文件内容。

    Args:
        file_path: 文件路径
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 限制返回长度
        if len(content) > 2000:
            return f"文件 '{file_path}' 内容 (前2000字符):\n\n{content[:2000]}\n\n... [共 {len(content)} 字符]"

        return f"文件 '{file_path}' 内容:\n\n{content}"
    except FileNotFoundError:
        return f"文件 '{file_path}' 不存在。"
    except Exception as e:
        return f"读取文件失败: {str(e)}"


class WriteFileInput(BaseModel):
    """写入文件输入参数"""

    file_path: str = Field(description="文件路径")
    content: str = Field(description="要写入的内容")
    mode: Literal["write", "append"] = Field(
        default="write", description="写入模式: write(覆盖), append(追加)"
    )


@tool(args_schema=WriteFileInput)
def write_file(file_path: str, content: str, mode: str = "write") -> str:
    """
    写入文件内容。

    Args:
        file_path: 文件路径
        content: 要写入的内容
        mode: 写入模式 (write/append)
    """
    try:
        file_mode = "w" if mode == "write" else "a"
        with open(file_path, file_mode, encoding="utf-8") as f:
            f.write(content)
        return f"文件 '{file_path}' 写入成功。模式: {mode}，写入 {len(content)} 字符。"
    except Exception as e:
        return f"写入文件失败: {str(e)}"


# ============== 数据转换工具 ==============


class JsonToYamlInput(BaseModel):
    """JSON 转 YAML 输入参数"""

    json_string: str = Field(description="要转换的 JSON 字符串")


@tool(args_schema=JsonToYamlInput)
def json_to_yaml(json_string: str) -> str:
    """
    将 JSON 字符串转换为 YAML 格式。

    Args:
        json_string: JSON 格式的字符串
    """
    try:
        import yaml

        data = json.loads(json_string)
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        return f"转换成功！\n\n{yaml_str}"
    except json.JSONDecodeError as e:
        return f"JSON 解析失败: {str(e)}"
    except ImportError:
        return "YAML 库未安装，请安装 PyYAML。"
    except Exception as e:
        return f"转换失败: {str(e)}"


class CsvToJsonInput(BaseModel):
    """CSV 转 JSON 输入参数"""

    csv_data: str = Field(description="CSV 格式的数据")
    has_header: bool = Field(default=True, description="第一行是否为表头")


@tool(args_schema=CsvToJsonInput)
def csv_to_json(csv_data: str, has_header: bool = True) -> str:
    """
    将 CSV 数据转换为 JSON 格式。

    Args:
        csv_data: CSV 格式的字符串
        has_header: 第一行是否为表头
    """
    try:
        lines = csv_data.strip().split("\n")
        if not lines:
            return "CSV 数据为空。"

        result = []
        headers = []

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            values = line.split(",")

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


# ============== 网络请求工具 ==============


class HttpRequestInput(BaseModel):
    """HTTP 请求输入参数"""

    url: str = Field(description="目标 URL")
    method: Literal["GET", "POST", "PUT", "DELETE"] = Field(
        default="GET", description="HTTP 方法"
    )
    headers: str = Field(default="", description="请求头（JSON 格式）")
    body: str = Field(default="", description="请求体（仅 POST/PUT）")


@tool(args_schema=HttpRequestInput)
def http_request(
    url: str, method: str = "GET", headers: str = "", body: str = ""
) -> str:
    """
    发送 HTTP 请求。

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
            header_dict = json.loads(headers)

        response = httpx.request(
            method=method,
            url=url,
            headers=header_dict,
            content=body.encode() if body else None,
            timeout=10.0,
        )

        response_text = response.text
        if len(response_text) > 500:
            response_text = response_text[:500] + "... [已截断]"

        return f"""HTTP 请求成功！
- 状态码: {response.status_code}
- 响应内容: {response_text}"""

    except Exception as e:
        return f"请求失败: {str(e)}"


# ============== 邮件工具 ==============


class SendEmailInput(BaseModel):
    """邮件发送输入参数"""

    to_email: str = Field(description="收件人邮箱")
    subject: str = Field(description="邮件主题")
    body: str = Field(description="邮件正文")
    cc_emails: str = Field(default="", description="抄送邮箱（逗号分隔）")


@tool(args_schema=SendEmailInput)
def send_email(
    to_email: str, subject: str, body: str, cc_emails: str = ""
) -> str:
    """
    发送邮件（模拟）。

    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
        cc_emails: 抄送邮箱
    """
    try:
        cc_list = (
            [email.strip() for email in cc_emails.split(",") if email.strip()]
            if cc_emails
            else []
        )

        body_preview = body[:100] + "..." if len(body) > 100 else body

        return f"""邮件发送成功（模拟）！
- 收件人: {to_email}
- 抄送: {', '.join(cc_list) if cc_list else '无'}
- 主题: {subject}
- 正文: {body_preview}"""
    except Exception as e:
        return f"发送失败: {str(e)}"


# ============== 工具聚合 ==============


def get_business_tools() -> list[BaseTool]:
    """获取所有业务工具"""
    return [
        # 知识检索
        search_knowledge,
        # 系统状态
        get_system_status,
        # 任务管理
        create_task,
        get_task_status,
        cancel_task,
        # 配置
        get_user_config,
        # 计算
        calculate,
        calculate_statistics,
        # 时间
        get_current_time,
        # 文件
        read_file,
        write_file,
        # 数据转换
        json_to_yaml,
        csv_to_json,
        # 网络
        http_request,
        # 邮件
        send_email,
    ]


# 需要授权的工具列表 (敏感操作)
TOOLS_REQUIRE_APPROVAL = [
    "write_file",
    "http_request",
    "send_email",
]
