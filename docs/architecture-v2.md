# WINS Agent v2 架构设计

## 设计理念

**Agent First** - 以 LangGraph `create_react_agent` 为核心，所有能力通过 Tool 扩展，subAgent 通过 `agent.as_tool()` 模式实现。丢弃当前手写的 planner/executor/validator/supervisor 节点，全面拥抱 LangGraph 原生能力。

## 核心依赖

```
langgraph >= 1.0.6          # Agent 运行时
langchain >= 1.2.6          # 工具和模型集成
langmem >= 0.0.14           # 短期记忆管理 (SummarizationNode)
deepagents >= 0.3.7         # 参考架构 (可选直接使用)
```

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI Layer                                   │
│  POST /chat/stream (SSE) │ POST /chat/resume │ GET /chat/state              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Main Agent (ReAct)                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        create_react_agent()                            │ │
│  │  • model: Qwen3-72B via DashScope                                      │ │
│  │  • tools: [业务工具] + [系统工具] + [SubAgent Tools]                   │ │
│  │  • pre_model_hook: ContextMiddleware (裁剪/摘要)                       │ │
│  │  • checkpointer: Redis/InMemorySaver                                   │ │
│  │  • store: InMemoryStore (长期记忆/知识库)                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│   Business Tools  │    │   System Tools    │    │  SubAgent Tools   │
│                   │    │                   │    │                   │
│ • search_knowledge│    │ • write_todos     │    │ • planner_agent   │
│ • create_task     │    │ • read_todos      │    │   .as_tool()      │
│ • http_request    │    │ • request_human   │    │                   │
│ • send_email      │    │   _approval       │    │ • validator_agent │
│ • calculate       │    │ • spawn_subagent  │    │   .as_tool()      │
│ • read_file       │    │                   │    │                   │
│ • write_file      │    │                   │    │ • research_agent  │
│ • ...             │    │                   │    │   .as_tool()      │
└───────────────────┘    └───────────────────┘    └───────────────────┘
```

## 核心组件设计

### 1. Main Agent (核心)

```python
# backend/app/agents/main_agent.py

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langmem.short_term import SummarizationNode

def create_main_agent(
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
) -> CompiledGraph:
    """创建主 Agent - 系统唯一入口"""

    model = get_llm()

    # 上下文管理 Hook (替代原 context_manager.py)
    context_middleware = create_context_middleware(
        max_tokens=4000,
        summarization_model=model.bind(max_tokens=256),
    )

    # 组装所有工具
    all_tools = [
        *tools,                    # 业务工具
        *get_system_tools(),       # 系统工具 (todos, hitl, subagent)
        *get_subagent_tools(),     # SubAgent as Tools
    ]

    return create_react_agent(
        model=model,
        tools=all_tools,
        pre_model_hook=context_middleware,
        checkpointer=checkpointer or InMemorySaver(),
        store=store or InMemoryStore(),
        prompt=SYSTEM_PROMPT,
    )
```

### 2. Context Middleware (上下文裁剪)

基于 `pre_model_hook` 实现，替代原有的 `context_manager.py`。

```python
# backend/app/agents/middleware/context.py

from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langmem.short_term import SummarizationNode

def create_context_middleware(
    max_tokens: int = 4000,
    summarization_model: BaseChatModel = None,
) -> Callable:
    """
    上下文管理中间件

    功能:
    1. Token 预算控制 - 裁剪超长历史
    2. 自动摘要 - 压缩已完成的工具调用
    3. 保留关键信息 - 首条消息 + 最近消息
    """

    # 可选：使用 langmem 的 SummarizationNode
    summarization_node = None
    if summarization_model:
        summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=summarization_model,
            max_tokens=max_tokens,
            max_tokens_before_summary=max_tokens * 2,
            max_summary_tokens=512,
        )

    def middleware(state: AgentState) -> dict:
        messages = state.get("messages", [])

        # 策略1: 使用 SummarizationNode (如果配置)
        if summarization_node:
            return summarization_node(state)

        # 策略2: 简单裁剪 (默认)
        trimmed = trim_messages(
            messages,
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=max_tokens,
            start_on="human",
            end_on=("human", "tool"),
            include_system=True,
        )

        return {"llm_input_messages": trimmed}

    return middleware
```

### 3. Human-in-the-Loop (HITL) 工具

基于 LangGraph 原生 `interrupt()` 实现，替代原有的 `hitl.py`。

```python
# backend/app/agents/tools/hitl.py

from langgraph.types import interrupt, Command
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class ApprovalRequest(BaseModel):
    """授权请求参数"""
    action: str = Field(description="需要授权的操作描述")
    tool_name: str = Field(description="工具名称")
    params: dict = Field(default_factory=dict, description="工具参数")

@tool(args_schema=ApprovalRequest)
def request_human_approval(action: str, tool_name: str, params: dict) -> str:
    """
    请求人工授权。当执行敏感操作时调用此工具暂停执行，等待用户确认。

    用户可以:
    - approve: 批准执行
    - reject: 拒绝执行
    - edit: 修改参数后执行
    """
    # interrupt() 会暂停图执行，返回给客户端
    human_response = interrupt({
        "type": "authorization",
        "action": action,
        "tool_name": tool_name,
        "params": params,
        "options": ["approve", "reject", "edit"],
    })

    # 用户通过 Command(resume=...) 恢复执行后，这里继续
    if human_response.get("action") == "approve":
        return f"用户已批准执行 {tool_name}"
    elif human_response.get("action") == "reject":
        return f"用户拒绝执行 {tool_name}，原因: {human_response.get('reason', '未说明')}"
    elif human_response.get("action") == "edit":
        return f"用户修改了参数: {human_response.get('params', {})}"

    return "未知的用户响应"


@tool
def request_human_input(question: str, context: str = "") -> str:
    """
    请求人工输入。当需要用户提供额外信息时调用。

    Args:
        question: 需要用户回答的问题
        context: 上下文信息，帮助用户理解
    """
    human_response = interrupt({
        "type": "input_required",
        "question": question,
        "context": context,
    })

    return human_response.get("input", "")
```

### 4. Todo 管理工具

参考 deepagents 的 `write_todos` 模式，替代原有的 `planner.py`。

```python
# backend/app/agents/tools/todos.py

from langgraph.config import get_store
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime
import uuid

class TodoStep(BaseModel):
    """任务步骤"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    result: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class TodoList(BaseModel):
    """任务列表"""
    goal: str
    steps: list[TodoStep] = Field(default_factory=list)
    current_step: int = 0

@tool
def write_todos(
    goal: str,
    steps: list[str],
    config: RunnableConfig,
) -> str:
    """
    创建或更新任务计划。将复杂任务分解为可执行的步骤。

    Args:
        goal: 最终目标描述
        steps: 步骤列表，每个步骤是一个简短描述

    Returns:
        创建的任务计划摘要
    """
    store = get_store()
    thread_id = config["configurable"].get("thread_id")

    todo_list = TodoList(
        goal=goal,
        steps=[TodoStep(description=s) for s in steps],
    )

    # 存储到 Store
    store.put(("todos",), thread_id, todo_list.model_dump())

    steps_text = "\n".join(
        f"  {i+1}. [{s.status}] {s.description}"
        for i, s in enumerate(todo_list.steps)
    )
    return f"任务计划已创建:\n目标: {goal}\n步骤:\n{steps_text}"


@tool
def read_todos(config: RunnableConfig) -> str:
    """读取当前任务计划和进度。"""
    store = get_store()
    thread_id = config["configurable"].get("thread_id")

    result = store.get(("todos",), thread_id)
    if not result:
        return "当前没有任务计划。"

    todo_list = TodoList(**result.value)

    completed = sum(1 for s in todo_list.steps if s.status == "completed")
    total = len(todo_list.steps)

    steps_text = "\n".join(
        f"  {i+1}. [{s.status}] {s.description}" +
        (f" -> {s.result[:50]}..." if s.result else "")
        for i, s in enumerate(todo_list.steps)
    )

    return f"任务进度: {completed}/{total}\n目标: {todo_list.goal}\n步骤:\n{steps_text}"


@tool
def update_todo_step(
    step_index: int,
    status: Literal["pending", "running", "completed", "failed", "skipped"],
    result: str = None,
    config: RunnableConfig = None,
) -> str:
    """
    更新任务步骤状态。

    Args:
        step_index: 步骤索引 (从0开始)
        status: 新状态
        result: 执行结果描述
    """
    store = get_store()
    thread_id = config["configurable"].get("thread_id")

    data = store.get(("todos",), thread_id)
    if not data:
        return "没有找到任务计划。"

    todo_list = TodoList(**data.value)

    if step_index < 0 or step_index >= len(todo_list.steps):
        return f"无效的步骤索引: {step_index}"

    todo_list.steps[step_index].status = status
    if result:
        todo_list.steps[step_index].result = result

    store.put(("todos",), thread_id, todo_list.model_dump())

    return f"步骤 {step_index + 1} 已更新为 {status}"
```

### 5. SubAgent as Tool (子代理)

使用 `agent.as_tool()` 模式实现专业化子代理。

```python
# backend/app/agents/subagents/__init__.py

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool
from typing import TypedDict, List

class SubAgentMessage(TypedDict):
    role: str
    content: str

def create_subagent_tools(model: BaseChatModel) -> list[BaseTool]:
    """创建所有 SubAgent 工具"""

    # ===== 规划专家 =====
    planner_agent = create_react_agent(
        model=model,
        tools=[],  # 规划不需要工具
        prompt="""你是一个任务规划专家。

分析用户意图，将复杂任务分解为清晰、可执行的步骤。
输出格式:
1. 目标理解: ...
2. 步骤分解:
   - 步骤1: ...
   - 步骤2: ...
3. 依赖关系: ...
4. 风险评估: ...""",
    )

    planner_tool = planner_agent.as_tool(
        name="planner_expert",
        description="规划专家。当需要分析复杂任务、制定执行计划时调用。输入任务描述，返回详细的执行计划。",
        arg_types={"messages": List[SubAgentMessage]},
    )

    # ===== 验证专家 =====
    validator_agent = create_react_agent(
        model=model,
        tools=[],
        prompt="""你是一个结果验证专家。

评估任务执行结果是否达成目标:
1. 完整性检查: 是否所有步骤都已完成
2. 正确性验证: 结果是否符合预期
3. 质量评估: 输出质量如何
4. 改进建议: 如有不足，如何改进

输出: 验证报告 + 最终判定 (成功/部分成功/失败)""",
    )

    validator_tool = validator_agent.as_tool(
        name="validator_expert",
        description="验证专家。当需要评估任务执行结果、验证输出质量时调用。",
        arg_types={"messages": List[SubAgentMessage]},
    )

    # ===== 研究专家 =====
    research_agent = create_react_agent(
        model=model,
        tools=[search_knowledge],  # 可以使用知识库搜索
        prompt="""你是一个研究专家。

深入调研问题，从知识库中检索相关信息，综合分析后给出研究报告。""",
    )

    research_tool = research_agent.as_tool(
        name="research_expert",
        description="研究专家。当需要深入调研某个主题、整合多方信息时调用。",
        arg_types={"messages": List[SubAgentMessage]},
    )

    return [planner_tool, validator_tool, research_tool]
```

### 6. 动态工具选择

基于运行时上下文动态配置可用工具。

```python
# backend/app/agents/tool_selector.py

from dataclasses import dataclass
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.runtime import Runtime

@dataclass
class AgentContext:
    """运行时上下文"""
    user_id: str
    thread_id: str
    available_tools: list[str]  # 允许使用的工具列表
    require_approval: list[str]  # 需要授权的工具列表

def configure_model_with_tools(
    state: AgentState,
    runtime: Runtime[AgentContext]
) -> BaseChatModel:
    """根据上下文动态选择工具"""

    context = runtime.context
    all_tools = get_all_tools()

    # 过滤允许的工具
    available = [
        t for t in all_tools
        if t.name in context.available_tools
    ]

    # 对需要授权的工具包装 HITL
    wrapped_tools = []
    for tool in available:
        if tool.name in context.require_approval:
            wrapped_tools.append(wrap_with_approval(tool))
        else:
            wrapped_tools.append(tool)

    return get_llm().bind_tools(wrapped_tools)
```

## API 层设计

```python
# backend/app/api/chat.py

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langgraph.types import Command

router = APIRouter(prefix="/chat")

@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式对话"""
    agent = get_main_agent()
    config = {
        "configurable": {
            "thread_id": request.thread_id,
            "user_id": request.user_id,
        }
    }

    async def event_generator():
        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": request.message}]},
            config=config,
            version="v2",
        ):
            # 处理不同事件类型
            if event["event"] == "on_chat_model_stream":
                yield format_sse("update", {"content": event["data"]["chunk"].content})

            elif event["event"] == "on_tool_start":
                yield format_sse("tool_start", {
                    "tool": event["name"],
                    "input": event["data"]["input"],
                })

            elif event["event"] == "on_tool_end":
                yield format_sse("tool_end", {
                    "tool": event["name"],
                    "output": event["data"]["output"],
                })

        # 检查是否有中断
        state = agent.get_state(config)
        if state.tasks:  # 有待处理的 interrupt
            interrupt_data = state.tasks[0].interrupts[0].value
            yield format_sse("interrupt", interrupt_data)
        else:
            yield format_sse("done", {"status": "completed"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.post("/resume/{thread_id}")
async def resume_chat(thread_id: str, request: ResumeRequest):
    """恢复中断的对话"""
    agent = get_main_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # 使用 Command 恢复执行
    async def event_generator():
        async for event in agent.astream_events(
            Command(resume=request.response),
            config=config,
            version="v2",
        ):
            # ... 同上
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## 目录结构

```
backend/
├── app/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── main_agent.py          # 主 Agent 入口
│   │   ├── llm.py                 # LLM 配置
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   └── context.py         # 上下文管理 (pre_model_hook)
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── business.py        # 业务工具
│   │   │   ├── todos.py           # 任务管理工具
│   │   │   └── hitl.py            # 人机交互工具
│   │   └── subagents/
│   │       ├── __init__.py
│   │       ├── planner.py         # 规划 SubAgent
│   │       ├── validator.py       # 验证 SubAgent
│   │       └── research.py        # 研究 SubAgent
│   ├── api/
│   │   ├── __init__.py
│   │   ├── chat.py                # 对话 API
│   │   ├── conversations.py       # 会话管理
│   │   └── tools.py               # 工具列表
│   ├── models/
│   │   └── schemas.py             # Pydantic 模型
│   ├── config.py                  # 配置管理
│   └── main.py                    # FastAPI 入口
├── requirements.txt
└── run.py
```

## 与原架构对比

| 原架构 | 新架构 | 说明 |
|--------|--------|------|
| `supervisor.py` | 移除 | 由 `create_react_agent` 内部处理 |
| `planner.py` | `tools/todos.py` + `subagents/planner.py` | Todo 工具 + 可选规划 SubAgent |
| `executor.py` | 移除 | ReAct Agent 自动执行工具 |
| `validator.py` | `subagents/validator.py` | 作为 SubAgent Tool |
| `replanner.py` | 移除 | Agent 自主决定何时重新规划 |
| `goal_evaluator.py` | Agent 自主判断 | 通过 prompt 引导 |
| `context_manager.py` | `middleware/context.py` | 使用 `pre_model_hook` |
| `hitl.py` | `tools/hitl.py` | 使用原生 `interrupt()` |
| `state.py` | 使用 LangGraph 内置 State | `AgentState` from prebuilt |
| `graph.py` | `main_agent.py` | 简化为单一入口 |

## 关键优势

1. **代码量大幅减少** - 从 ~2000 行减少到 ~500 行
2. **原生能力复用** - 使用 LangGraph 内置的中断、恢复、流式处理
3. **更好的可扩展性** - 添加 SubAgent 只需 `agent.as_tool()`
4. **标准化** - 符合 LangChain 生态最佳实践
5. **易于调试** - 使用 LangSmith 可追踪完整执行链路

## 参考资料

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Deep Agents GitHub](https://github.com/langchain-ai/deepagents)
- [LangMem Short-term Memory](https://langchain-ai.github.io/langmem/guides/summarization)
- [create_react_agent Reference](https://langchain-ai.github.io/langgraph/reference/agents)
