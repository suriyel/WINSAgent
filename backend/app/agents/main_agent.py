"""
主 Agent 模块

系统核心入口，基于 LangGraph create_react_agent 构建。
集成所有工具、中间件和 SubAgent。
"""

from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.config import get_settings
from app.agents.llm import get_llm
from app.agents.middleware import create_context_middleware, ContextConfig
from app.agents.tools import get_todo_tools, get_hitl_tools, get_business_tools
from app.agents.subagents import get_subagent_tools


# ============== 系统提示词 ==============


SYSTEM_PROMPT = """你是 WINS Agent，一个智能任务编排助手。

## 核心能力

1. **任务规划**: 使用 write_todos 将复杂任务分解为步骤
2. **工具调用**: 调用各类工具完成具体任务
3. **人机协作**: 敏感操作前请求用户授权
4. **专家咨询**: 调用专家 SubAgent 处理复杂问题

## 工作流程

1. 理解用户意图
2. 对于复杂任务，先调用 write_todos 制定计划
3. 按步骤执行，每完成一步调用 update_todo_step 更新状态
4. 敏感操作 (写文件、网络请求、发邮件) 先请求授权
5. 遇到不确定的问题，调用 request_human_input 询问用户
6. 任务完成后，可调用 validator_expert 验证结果

## 可用工具类别

### 系统工具
- write_todos / read_todos / update_todo_step: 任务计划管理
- request_human_approval / request_human_input: 人机交互

### 业务工具
- search_knowledge: 知识库检索
- create_task / get_task_status / cancel_task: 后台任务管理
- calculate / calculate_statistics: 数据计算
- read_file / write_file: 文件操作
- http_request: 网络请求
- send_email: 邮件发送
- 等等...

### 专家 SubAgent
- planner_expert: 复杂任务规划
- validator_expert: 结果验证
- research_expert: 深度研究

## 注意事项

- 始终保持友好、专业的态度
- 对于不确定的事情，主动询问而非猜测
- 执行敏感操作前必须获得用户授权
- 任务执行过程中保持进度更新
- 遇到错误时，分析原因并提供解决方案
"""


# ============== Agent 构建 ==============


def create_main_agent(
    tools: list[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    include_subagents: bool = True,
    context_config: ContextConfig | None = None,
) -> CompiledStateGraph:
    """
    创建主 Agent

    Args:
        tools: 额外的自定义工具列表
        checkpointer: 状态持久化器 (默认 InMemorySaver)
        store: 长期存储 (默认 InMemoryStore)
        include_subagents: 是否包含 SubAgent 工具
        context_config: 上下文管理配置

    Returns:
        编译后的 Agent Graph
    """
    settings = get_settings()
    model = get_llm()

    # 组装所有工具
    all_tools = []

    # 1. 系统工具 (todos, hitl)
    all_tools.extend(get_todo_tools())
    all_tools.extend(get_hitl_tools())

    # 2. 业务工具
    all_tools.extend(get_business_tools())

    # 3. SubAgent 工具 (可选)
    if include_subagents:
        all_tools.extend(get_subagent_tools(model))

    # 4. 自定义工具
    if tools:
        all_tools.extend(tools)

    # 上下文管理中间件
    if context_config is None:
        context_config = ContextConfig(
            max_tokens=settings.message_token_limit,
        )
    context_middleware = create_context_middleware(context_config)

    # 默认 checkpointer 和 store
    if checkpointer is None:
        checkpointer = InMemorySaver()

    if store is None:
        store = InMemoryStore()

    # 创建 Agent
    agent = create_react_agent(
        model=model,
        tools=all_tools,
        prompt=SYSTEM_PROMPT,
        pre_model_hook=context_middleware,
        checkpointer=checkpointer,
        store=store,
    )

    return agent


# ============== 全局实例管理 ==============


_agent_instance: CompiledStateGraph | None = None
_checkpointer_instance: BaseCheckpointSaver | None = None
_store_instance: BaseStore | None = None


def get_checkpointer() -> BaseCheckpointSaver:
    """
    获取 Checkpointer 实例

    - 开发环境: InMemorySaver
    - 生产环境: RedisSaver
    """
    global _checkpointer_instance

    if _checkpointer_instance is None:
        settings = get_settings()

        if settings.debug:
            _checkpointer_instance = InMemorySaver()
        else:
            try:
                from langgraph.checkpoint.redis import RedisSaver
                _checkpointer_instance = RedisSaver.from_conn_string(settings.redis_url)
            except ImportError:
                _checkpointer_instance = InMemorySaver()

    return _checkpointer_instance


def get_store() -> BaseStore:
    """获取 Store 实例"""
    global _store_instance

    if _store_instance is None:
        _store_instance = InMemoryStore()

    return _store_instance


def get_agent() -> CompiledStateGraph:
    """
    获取 Agent 单例

    Returns:
        编译后的 Agent Graph
    """
    global _agent_instance

    if _agent_instance is None:
        _agent_instance = create_main_agent(
            checkpointer=get_checkpointer(),
            store=get_store(),
        )

    return _agent_instance


def reset_agent() -> None:
    """重置 Agent 实例 (用于测试)"""
    global _agent_instance, _checkpointer_instance, _store_instance
    _agent_instance = None
    _checkpointer_instance = None
    _store_instance = None


# ============== 便捷方法 ==============


async def invoke_agent(
    message: str,
    thread_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    同步调用 Agent

    Args:
        message: 用户消息
        thread_id: 会话 ID
        user_id: 用户 ID

    Returns:
        Agent 响应
    """
    agent = get_agent()

    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id or "default",
        }
    }

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config=config,
    )

    return result


async def stream_agent(
    message: str,
    thread_id: str,
    user_id: str | None = None,
):
    """
    流式调用 Agent

    Args:
        message: 用户消息
        thread_id: 会话 ID
        user_id: 用户 ID

    Yields:
        Agent 事件流
    """
    agent = get_agent()

    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id or "default",
        }
    }

    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": message}]},
        config=config,
        version="v2",
    ):
        yield event


def get_agent_state(thread_id: str) -> dict[str, Any] | None:
    """
    获取 Agent 状态

    Args:
        thread_id: 会话 ID

    Returns:
        当前状态，如果不存在则返回 None
    """
    agent = get_agent()

    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = agent.get_state(config)
        return state.values if state else None
    except Exception:
        return None
