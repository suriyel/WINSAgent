# 通用 Agent 工作台 PRD（专业修订版）

> 版本：2.0 | 更新日期：2025-01 | 基于 LangGraph 1.0 / LangChain 1.2

---

## 修订说明

本版本基于 LangChain/LangGraph 2025年最新文档进行专业修正，主要变更：

| 原方案 | 修订后 | 原因 |
|--------|--------|------|
| 自定义 Supervisor Agent | `create_agent()` + Tool-based Handoff | LangGraph 1.0 推荐模式 |
| AgentExecutor | `create_react_agent()` / `StateGraph` | AgentExecutor 已标记为 Legacy |
| 自研状态持久化 | LangGraph Checkpointer | 内置生产级持久化机制 |
| YAML Tool Schema | `@tool` 装饰器 + Pydantic | 官方标准 Tool 定义方式 |
| 手动 Token 管理 | LangGraph `trim_messages` | 内置消息裁剪工具 |

---

## 1. 产品概述

### 1.1 产品定位

**通用 Agent 工作台**是一个基于 LangGraph 1.0 的智能任务编排平台，面向需要对接复杂业务系统的企业用户。平台通过自然语言交互，将用户意图转化为可执行的多步骤任务，并提供完整的任务可视化与状态追踪能力。

### 1.2 核心价值

| 维度 | 价值 |
|------|------|
| **降低使用门槛** | 用户无需了解底层 API 细节，通过自然语言即可完成复杂操作 |
| **提升执行效率** | Agent 自动编排任务依赖，减少人工协调成本 |
| **增强可控性** | 全流程状态可视化，支持 Human-in-the-Loop 审批 |
| **快速扩展** | 标准化 `@tool` 接入规范，支持快速对接新业务系统 |

---

## 2. 技术架构

### 2.1 技术栈

| 层级 | 组件 | 技术选型 | 版本 |
|------|------|----------|------|
| **前端** | 框架 | React | 18.3.1 |
| **Agent 层** | 编排框架 | LangGraph | 1.0.6 |
| | 基础框架 | LangChain | 1.2.5 |
| **LLM** | 在线服务 | Qwen3-72B-Instruct | API |
| **数据层** | 向量库 | FAISS | 1.10.0 |
| | Checkpoint存储 | Redis / PostgreSQL | - |
| | 业务持久化 | MySQL | 8.0.44 |
| **后端** | API 框架 | FastAPI | 0.128.0 |
| | 数据验证 | Pydantic | 2.6.3 |

### 2.2 Agent 架构（LangGraph 1.0 标准模式）

```
┌─────────────────────────────────────────────────────────────────┐
│                      Supervisor Agent                            │
│            create_react_agent() + Handoff Tools                  │
│     ┌──────────────┬──────────────┬──────────────┐              │
│     │ handoff_to_  │ handoff_to_  │ handoff_to_  │              │
│     │   planner    │   executor   │   validator  │              │
│     └──────────────┴──────────────┴──────────────┘              │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Planner Agent  │  │ Executor Agent  │  │ Validator Agent │
│  (SubGraph)     │  │  (SubGraph)     │  │  (SubGraph)     │
│                 │  │                 │  │                 │
│ • 意图解析       │  │ • Tool 调用     │  │ • 结果校验      │
│ • 任务拆解       │  │ • 参数填充      │  │ • 错误归因      │
│ • 依赖推断       │  │ • 重试处理      │  │ • 状态判定      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
              ┌───────────────────────────────────┐
              │        LangGraph State            │
              │  ┌───────────┐  ┌─────────────┐  │
              │  │ messages  │  │ todo_list   │  │
              │  │ (对话历史) │  │ (任务步骤)  │  │
              │  └───────────┘  └─────────────┘  │
              │  ┌───────────┐  ┌─────────────┐  │
              │  │ Checkpoint│  │   Store     │  │
              │  │ (短期记忆) │  │ (长期记忆)  │  │
              │  └───────────┘  └─────────────┘  │
              └───────────────────────────────────┘
```

### 2.3 核心概念映射

| PRD 概念 | LangGraph 实现 | 说明 |
|----------|----------------|------|
| 对话历史 | `messages` channel | 使用 `add_messages` reducer 自动合并 |
| 任务步骤 | 自定义 `todo_list` channel | TypedDict 定义状态结构 |
| 状态持久化 | Checkpointer | 每个 super-step 自动保存 |
| 会话隔离 | Thread (`thread_id`) | 每个用户会话独立 thread |
| 跨会话记忆 | Store | 用户偏好、历史知识等 |
| 用户审批 | `interrupt_before` | Human-in-the-Loop 原生支持 |
| 失败恢复 | `pending_writes` | 断点续执行 |

---

## 3. 功能需求（修订版）

### 3.1 对话交互模块

| 功能 | 描述 | LangGraph 实现 | 优先级 |
|------|------|----------------|--------|
| 自然语言输入 | 支持用户通过自然语言描述任务意图 | `messages` state | P0 |
| 多轮对话 | 支持上下文连续的多轮交互 | `add_messages` reducer | P0 |
| 对话历史 | 永久保存，支持查看历史对话 | Checkpointer + Thread | P0 |
| 流式输出 | 实时展示 Agent 思考过程 | `stream_mode="updates"` | P0 |
| 多任务创建 | 单次对话可创建多个独立任务 | 多 Thread 并行 | P1 |

### 3.2 任务规划模块（Planner SubGraph）

| 功能 | 描述 | 实现方式 | 优先级 |
|------|------|----------|--------|
| 意图识别 | 解析用户自然语言，提取结构化目标 | LLM + Structured Output | P0 |
| 任务拆解 | 将复杂目标拆解为 TODO 步骤列表 | `response_format=ToolStrategy(TodoList)` | P0 |
| 依赖推断 | 自动识别步骤间的执行依赖关系 | 状态中维护 `dependencies` | P0 |
| 动态调整 | 根据执行结果动态调整后续计划 | `Command` 控制流 | P1 |

### 3.3 任务执行模块（Executor SubGraph）

| 功能 | 描述 | 实现方式 | 优先级 |
|------|------|----------|--------|
| Tool 选择 | 根据任务需求选择合适的 Tool | `create_react_agent()` | P0 |
| 参数填充 | 结合知识库与上下文，自动填充 Tool 参数 | RAG + `InjectedState` | P0 |
| 执行调度 | 按依赖顺序执行 Tool 调用 | 条件边 + `Command` | P0 |
| 重试机制 | 失败后自动重试（最多 3 次） | `@wrap_tool_call` 中间件 | P0 |
| 用户确认 | 敏感操作前暂停等待用户审批 | `interrupt_before` | P0 |

### 3.4 结果校验模块（Validator SubGraph）

| 功能 | 描述 | 实现方式 | 优先级 |
|------|------|----------|--------|
| 结果判定 | 判定任务执行结果：成功/失败 | Structured Output | P0 |
| 错误归因 | 识别失败原因并定位到具体步骤 | 状态中记录 `error_info` | P0 |
| 状态说明 | 使用业务语言描述执行状态 | LLM 生成自然语言摘要 | P0 |

---

## 4. State Schema 设计

### 4.1 核心状态定义

```python
from typing import Annotated, TypedDict, Literal
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

class TodoStep(TypedDict):
    """单个任务步骤"""
    id: str
    description: str
    tool_name: str | None
    status: Literal["pending", "running", "completed", "failed"]
    result: str | None
    error: str | None
    depends_on: list[str]  # 依赖的步骤 ID

class AgentState(TypedDict):
    """Agent 工作台核心状态"""
    # 对话消息 - 使用 add_messages reducer 自动合并
    messages: Annotated[list[BaseMessage], add_messages]
    
    # 解析后的用户意图
    parsed_intent: str | None
    
    # 任务步骤列表
    todo_list: list[TodoStep]
    
    # 当前执行步骤索引
    current_step: int
    
    # 最终状态
    final_status: Literal["pending", "running", "success", "failed"] | None
    
    # 需要用户输入的配置项
    pending_config: dict | None
```

### 4.2 Reducer 说明

| 字段 | Reducer | 说明 |
|------|---------|------|
| `messages` | `add_messages` | 自动追加新消息，处理消息去重 |
| `todo_list` | 覆盖写入 | Planner 生成后整体替换 |
| `current_step` | 覆盖写入 | Executor 逐步推进 |
| `pending_config` | 覆盖写入 | 需要用户填充时设置 |

---

## 5. Tool 接入规范（LangChain 标准）

### 5.1 使用 `@tool` 装饰器定义

```python
from langchain.tools import tool
from pydantic import BaseModel, Field
from typing import Literal

# 方式一：简单工具（自动推断 schema）
@tool
def get_task_status(task_id: str) -> str:
    """查询仿真任务的执行状态。
    
    Args:
        task_id: 任务ID，由 create_simulation_task 返回
    
    Returns:
        任务状态描述，包含进度百分比
    """
    # 实际实现调用业务 API
    return f"任务 {task_id} 执行中，进度 45%"


# 方式二：复杂工具（Pydantic schema）
class SimulationTaskInput(BaseModel):
    """创建仿真任务的输入参数"""
    city_name: str = Field(description="目标城市名称，如'北京市'")
    polygon: list[tuple[float, float]] = Field(
        description="仿真区域边界坐标点列表，格式 [(lng, lat), ...]"
    )
    config: dict | None = Field(
        default=None, 
        description="工参配置（可选），包含天线参数等"
    )

@tool(args_schema=SimulationTaskInput)
def create_simulation_task(
    city_name: str, 
    polygon: list[tuple[float, float]], 
    config: dict | None = None
) -> str:
    """创建覆盖仿真任务。
    
    需要提供城市名称和仿真区域边界坐标。
    返回任务ID，可用于后续查询任务状态。
    """
    # 实际实现调用业务 API
    task_id = "TASK_" + city_name[:2] + "_001"
    return f"任务创建成功，ID: {task_id}"
```

### 5.2 带状态注入的工具

```python
from langgraph.prebuilt import InjectedState
from typing import Annotated

@tool
def get_user_preference(
    pref_name: str,
    # 运行时注入，不暴露给 LLM
    state: Annotated[AgentState, InjectedState]
) -> str:
    """获取用户偏好设置。
    
    Args:
        pref_name: 偏好项名称
    """
    # 从状态中获取上下文
    user_context = state.get("user_context", {})
    return user_context.get(pref_name, "未设置")
```

### 5.3 接入方职责

| 职责 | 说明 |
|------|------|
| 定义 Tool 函数 | 使用 `@tool` 装饰器，提供清晰的 docstring |
| 定义 args_schema | 复杂参数使用 Pydantic BaseModel |
| 错误处理 | 工具内部捕获异常，返回结构化错误信息 |
| 提供知识文档 | 上传领域知识用于 RAG 检索辅助参数填充 |

---

## 6. Multi-Agent 实现

### 6.1 Supervisor + Handoff 模式

```python
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

# 定义 Handoff 工具
@tool
def handoff_to_planner(task_description: str) -> str:
    """将任务交给规划Agent进行任务拆解。"""
    # 返回 Command 触发路由
    return Command(goto="planner", update={"task": task_description})

@tool  
def handoff_to_executor(step_id: str) -> str:
    """将具体步骤交给执行Agent执行。"""
    return Command(goto="executor", update={"current_step_id": step_id})

@tool
def handoff_to_validator(results: dict) -> str:
    """将执行结果交给校验Agent进行验证。"""
    return Command(goto="validator", update={"results": results})

# 创建 Supervisor Agent
supervisor = create_agent(
    model="qwen3-72b-instruct",
    tools=[handoff_to_planner, handoff_to_executor, handoff_to_validator],
    system_prompt="""你是一个任务协调supervisor，负责：
    1. 分析用户意图，将任务交给planner拆解
    2. 协调executor逐步执行任务
    3. 将执行结果交给validator校验
    不要自己执行具体任务，只做协调调度。
    """,
    name="supervisor"
)
```

### 6.2 SubGraph 定义

```python
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent

# Planner SubGraph
planner_agent = create_react_agent(
    model="qwen3-72b-instruct",
    tools=[analyze_intent, generate_todo_list],
    system_prompt="你是任务规划专家，负责将用户需求拆解为可执行步骤。",
    name="planner"
)

# Executor SubGraph  
executor_agent = create_react_agent(
    model="qwen3-72b-instruct",
    tools=[create_simulation_task, get_task_status, ...],  # 业务工具
    system_prompt="你是任务执行专家，负责调用工具完成具体步骤。",
    name="executor"
)

# Validator SubGraph
validator_agent = create_react_agent(
    model="qwen3-72b-instruct", 
    tools=[validate_result, generate_report],
    system_prompt="你是结果校验专家，负责验证执行结果是否符合预期。",
    name="validator"
)

# 组装主图
def build_main_graph():
    builder = StateGraph(AgentState)
    
    builder.add_node("supervisor", supervisor)
    builder.add_node("planner", planner_agent)
    builder.add_node("executor", executor_agent)
    builder.add_node("validator", validator_agent)
    
    builder.add_edge(START, "supervisor")
    # 使用 Command 实现动态路由
    
    return builder.compile(
        checkpointer=checkpointer,  # 持久化
        interrupt_before=["executor"]  # 执行前可中断
    )
```

---

## 7. Checkpoint 与持久化

### 7.1 Checkpointer 配置

```python
# 开发环境 - 内存
from langgraph.checkpoint.memory import InMemorySaver
checkpointer = InMemorySaver()

# 生产环境 - PostgreSQL（推荐）
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/langgraph"
)

# 生产环境 - Redis（高性能场景）
from langgraph.checkpoint.redis import RedisSaver
checkpointer = RedisSaver(redis_url="redis://localhost:6379")
```

### 7.2 Thread 管理

```python
# 每个用户会话使用独立 thread_id
config = {
    "configurable": {
        "thread_id": f"user_{user_id}_session_{session_id}"
    }
}

# 调用 Agent
result = graph.invoke(
    {"messages": [{"role": "user", "content": user_input}]},
    config=config
)

# 恢复历史会话
history = list(checkpointer.list(config))
```

### 7.3 Human-in-the-Loop

```python
# 编译时指定中断点
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["executor"]  # 执行前暂停等待审批
)

# 获取待审批状态
state = graph.get_state(config)
if state.next == ["executor"]:
    # 展示待执行内容给用户
    pending_action = state.values["pending_config"]
    
# 用户审批后继续
graph.invoke(Command(resume=True), config)

# 或用户修改后继续
graph.update_state(config, {"pending_config": modified_config})
graph.invoke(None, config)
```

---

## 8. Token 管理

### 8.1 使用 LangGraph 内置消息裁剪

```python
from langchain_core.messages import trim_messages

# 在 Agent 节点中裁剪消息
def agent_node(state: AgentState):
    trimmed = trim_messages(
        state["messages"],
        max_tokens=4000,
        strategy="last",  # 保留最近的消息
        token_counter=model,  # 使用模型计算 token
        include_system=True,  # 始终保留 system message
    )
    response = model.invoke(trimmed)
    return {"messages": [response]}
```

### 8.2 关键信息保留策略

| 消息类型 | 策略 |
|----------|------|
| System Prompt | 始终保留 |
| 用户原始输入 | 始终保留 |
| 关键决策点 | 标记 `important=True` 保留 |
| Tool 调用结果 | 超长时 LLM 摘要压缩 |
| 中间推理过程 | 超出限制时优先裁剪 |

---

## 9. 约束与限制

### 9.1 系统限制

| 限制项 | 默认值 | 配置方式 |
|--------|--------|----------|
| 单任务最大步骤数 | 20 | State 校验 |
| SubGraph 嵌套深度 | 3 层 | `recursion_limit` |
| 单步重试次数 | 3 次 | Tool 中间件 |
| Tool 执行超时 | 60s | `asyncio.timeout` |
| 消息历史 Token 限制 | 4000 | `trim_messages` |

### 9.2 LangGraph 1.0 行为变更

| 项目 | 说明 |
|------|------|
| `langgraph.prebuilt` | 已废弃，迁移至 `langchain.agents` |
| 默认 `recursion_limit` | 从 25 改为更合理的默认值 |
| Checkpoint 版本 | v4 格式，不兼容旧版本 |

---

## 10. 验收标准

### 10.1 MVP 验收项

| 验收项 | 验收标准 | 实现依赖 |
|--------|----------|----------|
| Tool 动态加载 | `@tool` 装饰器定义的工具可被 Agent 识别调用 | LangChain Tools |
| 多步骤编排 | Supervisor 正确路由，SubGraph 按序执行 | LangGraph StateGraph |
| TODO 可视化 | 步骤状态实时更新，支持折叠 | SSE Stream |
| 参数动态表单 | 根据 Pydantic Schema 自动生成配置界面 | `args_schema` |
| 任务持久化 | 刷新/重开浏览器后可恢复 | Checkpointer |
| 用户审批 | 敏感操作前暂停等待确认 | `interrupt_before` |
| 多任务并行 | 支持同时运行多个任务 | 多 Thread |
| 知识检索 | RAG 检索结果辅助参数填充 | FAISS + InjectedState |
| 失败处理 | 显示具体失败步骤 + 错误原因 | State `error_info` |

### 10.2 验收场景示例

**场景：创建仿真任务（含用户审批）**

```
1. 用户输入："帮我创建一个北京市的覆盖仿真任务"

2. Supervisor → Planner:
   - 解析意图，生成 TODO 列表
   - 返回步骤列表到状态

3. 前端展示 TODO:
   ☐ 步骤1：获取用户配置偏好
   ☐ 步骤2：确认仿真区域（polygon）
   ☐ 步骤3：确认工参配置
   ☐ 步骤4：创建仿真任务
   ☐ 步骤5：返回任务ID

4. Supervisor → Executor（步骤2）:
   - 需要用户输入 polygon
   - 触发 interrupt_before
   - 前端弹出地图选区界面

5. 用户在地图上圈选区域 → 点击确认

6. 继续执行 → Executor 调用 create_simulation_task

7. Supervisor → Validator:
   - 校验任务创建结果
   - 返回成功状态

8. 前端展示:
   ✅ 任务创建成功，ID: TASK_BJ_001
```

---

## 11. 附录

### 11.1 术语表（更新）

| 术语 | 定义 |
|------|------|
| Tool | 使用 `@tool` 装饰器封装的可调用函数 |
| Agent | 基于 `create_agent()` 或 `create_react_agent()` 创建的智能决策单元 |
| Checkpoint | LangGraph 状态快照，每个 super-step 自动保存 |
| Thread | 会话线程，由 `thread_id` 标识，关联一组 Checkpoint |
| Super-step | 图执行的一个完整步骤（节点执行 + 状态更新） |
| Command | LangGraph 控制流对象，用于路由和状态更新 |
| Handoff | Agent 间任务交接，通过 Tool 返回 Command 实现 |
| Store | 跨 Thread 的长期记忆存储 |

### 11.2 依赖清单

```txt
# requirements.txt
langchain>=1.2.5
langgraph>=1.0.6
langchain-openai>=0.3.0
langgraph-checkpoint>=4.0.0
langgraph-checkpoint-postgres>=1.0.0  # 生产环境
faiss-cpu>=1.10.0
fastapi[standard]>=0.128.0
pydantic>=2.6.3
redis>=5.0.0
sqlalchemy>=2.0.0
pymysql>=1.1.0
```

### 11.3 参考文档

- [LangGraph 1.0 官方文档](https://docs.langchain.com/oss/python/langgraph)
- [LangChain Agents 文档](https://docs.langchain.com/oss/python/langchain/agents)
- [Multi-Agent Supervisor 教程](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant)
- [Checkpointing 最佳实践](https://docs.langchain.com/oss/python/langgraph/persistence)
