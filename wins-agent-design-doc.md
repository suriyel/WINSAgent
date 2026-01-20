# WINS Agent 软件设计文档

> 版本：1.0 | 作者：系统架构师 | 日期：2026-01-20

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统架构设计](#2-系统架构设计)
3. [Agent 工作流设计](#3-agent-工作流设计)
4. [数据模型设计](#4-数据模型设计)
5. [API 接口设计](#5-api-接口设计)
6. [前端架构设计](#6-前端架构设计)
7. [知识库与 RAG 设计](#7-知识库与-rag-设计)
8. [Tool 注册与编排设计](#8-tool-注册与编排设计)
9. [Human-in-the-Loop 设计](#9-human-in-the-loop-设计)
10. [部署架构设计](#10-部署架构设计)

---

## 1. 系统概述

### 1.1 系统定位

WINS Agent 是一个基于 LangGraph 1.0 的智能任务编排平台，专为领域知识密集型场景设计，支持复杂业务系统的自然语言交互与自动化任务执行。

### 1.2 核心能力矩阵

| 能力域 | 核心功能 | 技术支撑 |
|--------|----------|----------|
| **意图理解** | 自然语言解析、多轮对话、上下文保持 | LLM + Prompt Engineering |
| **知识检索** | 领域术语、系统文档、历史案例 | FAISS + RAG Pipeline |
| **任务编排** | 依赖分析、并行调度、失败重试 | LangGraph StateGraph |
| **参数填充** | 智能推断、知识增强、用户确认 | RAG + Human-in-the-Loop |
| **进度追踪** | 实时状态、步骤可视化、错误归因 | SSE + React State |

### 1.3 设计约束

```
┌─────────────────────────────────────────────────────────────┐
│                      设计约束矩阵                            │
├─────────────────┬───────────────────────────────────────────┤
│ 响应时间        │ 首字输出 < 2s，完整响应 < 30s             │
│ 并发能力        │ 单实例支持 100 并发会话                    │
│ 上下文窗口      │ 保留最近 4000 tokens                       │
│ 任务步骤        │ 单任务最大 20 步                           │
│ 重试策略        │ 单步最多 3 次重试                          │
│ Tool 超时       │ 单次调用 < 60s                             │
└─────────────────┴───────────────────────────────────────────┘
```

---

## 2. 系统架构设计

### 2.1 分层架构视图

```mermaid
graph TB
    subgraph "表现层 Presentation Layer"
        UI[React SPA]
        SSE[SSE Stream Handler]
    end
    
    subgraph "网关层 Gateway Layer"
        API[FastAPI Gateway]
        WS[WebSocket Handler]
        Auth[认证中间件]
    end
    
    subgraph "编排层 Orchestration Layer"
        SV[Supervisor Agent]
        PL[Planner Agent]
        EX[Executor Agent]
        VL[Validator Agent]
    end
    
    subgraph "能力层 Capability Layer"
        LLM[LLM Service<br/>Qwen3-72B]
        RAG[RAG Pipeline]
        TOOL[Tool Registry]
    end
    
    subgraph "数据层 Data Layer"
        CKP[Checkpointer<br/>Redis]
        VDB[Vector Store<br/>FAISS]
        RDB[关系数据库<br/>MySQL]
    end
    
    UI --> API
    SSE --> API
    API --> Auth
    Auth --> SV
    SV --> PL & EX & VL
    PL & EX & VL --> LLM & RAG & TOOL
    LLM --> CKP
    RAG --> VDB
    TOOL --> RDB
```

### 2.2 组件交互视图

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as 前端
    participant G as API Gateway
    participant S as Supervisor
    participant P as Planner
    participant E as Executor
    participant V as Validator
    participant T as Tool Registry
    participant K as Knowledge Base
    
    U->>F: 输入自然语言指令
    F->>G: POST /chat/stream
    G->>S: 创建/恢复 Thread
    
    S->>P: handoff_to_planner
    P->>K: 检索领域知识
    K-->>P: 相关文档
    P->>P: 意图解析 + 任务拆解
    P-->>S: TODO List
    
    loop 逐步执行
        S->>E: handoff_to_executor(step_id)
        E->>T: 获取 Tool Schema
        E->>K: 检索参数知识
        
        alt 需要用户输入
            E-->>F: interrupt(pending_config)
            F->>U: 显示配置表单
            U->>F: 提交配置
            F->>G: POST /chat/resume
            G->>E: Command(resume)
        end
        
        E->>T: 执行 Tool
        T-->>E: 执行结果
        E-->>S: 步骤完成
        S-->>F: SSE 状态更新
    end
    
    S->>V: handoff_to_validator
    V->>V: 校验执行结果
    V-->>S: 最终状态
    S-->>F: SSE 完成事件
    F-->>U: 展示结果
```

### 2.3 技术组件依赖图

```mermaid
graph LR
    subgraph "前端技术栈"
        React --> ReactRouter
        React --> TanStackQuery
        React --> Zustand
        React --> FramerMotion
        Vite --> React
        TailwindCSS --> React
    end
    
    subgraph "后端技术栈"
        FastAPI --> Pydantic
        FastAPI --> Uvicorn
        LangGraph --> LangChain
        LangChain --> LangChainOpenAI
        LangGraph --> Checkpointer
    end
    
    subgraph "数据技术栈"
        FAISS --> DashScopeEmbed[DashScope Embedding]
        Redis --> Checkpointer
        MySQL --> SQLAlchemy
    end
    
    subgraph "外部服务"
        DashScope[DashScope API]
        BusinessAPI[业务系统 API]
    end
    
    LangChainOpenAI --> DashScope
    Tool --> BusinessAPI
```

---

## 3. Agent 工作流设计

### 3.1 主状态机设计

```mermaid
stateDiagram-v2
    [*] --> Idle: 初始化
    
    Idle --> Supervising: 用户输入
    
    Supervising --> Planning: 无 TODO List
    Supervising --> Executing: 有待执行步骤
    Supervising --> Validating: 所有步骤完成
    Supervising --> Idle: 任务完成/失败
    
    Planning --> Supervising: 生成 TODO List
    
    Executing --> WaitingInput: 需要用户配置
    Executing --> Supervising: 步骤完成
    Executing --> Supervising: 步骤失败(重试耗尽)
    
    WaitingInput --> Executing: 用户提交配置
    WaitingInput --> Idle: 用户取消
    
    Validating --> Idle: 校验完成
    
    state Planning {
        [*] --> IntentParsing
        IntentParsing --> TaskDecomposition
        TaskDecomposition --> DependencyInference
        DependencyInference --> [*]
    }
    
    state Executing {
        [*] --> ToolSelection
        ToolSelection --> ParameterFilling
        ParameterFilling --> ToolInvocation
        ToolInvocation --> ResultProcessing
        ResultProcessing --> [*]
    }
```

### 3.2 Supervisor 路由决策树

```mermaid
graph TD
    START[开始路由决策] --> C1{pending_config<br/>存在?}
    C1 -->|是| END_WAIT[返回 end<br/>等待用户输入]
    C1 -->|否| C2{final_status<br/>= success/failed?}
    
    C2 -->|是| END_DONE[返回 end<br/>任务结束]
    C2 -->|否| C3{todo_list<br/>为空?}
    
    C3 -->|是| PLANNER[返回 planner<br/>需要规划]
    C3 -->|否| C4{所有步骤<br/>completed?}
    
    C4 -->|是| VALIDATOR[返回 validator<br/>需要校验]
    C4 -->|否| C5{存在<br/>failed 步骤?}
    
    C5 -->|是| C6{重试次数<br/>< 3?}
    C5 -->|否| EXECUTOR[返回 executor<br/>继续执行]
    
    C6 -->|是| EXECUTOR
    C6 -->|否| VALIDATOR
```

### 3.3 任务执行流程（带重试）

```mermaid
flowchart TD
    START[开始执行步骤] --> CHECK_DEP{检查依赖<br/>是否满足}
    CHECK_DEP -->|否| WAIT[等待依赖完成]
    WAIT --> CHECK_DEP
    
    CHECK_DEP -->|是| GET_TOOL[获取 Tool 定义]
    GET_TOOL --> FILL_PARAM[参数填充]
    
    FILL_PARAM --> NEED_INPUT{需要<br/>用户输入?}
    NEED_INPUT -->|是| INTERRUPT[触发中断<br/>生成配置表单]
    INTERRUPT --> WAIT_USER[等待用户响应]
    WAIT_USER --> MERGE_CONFIG[合并用户配置]
    MERGE_CONFIG --> INVOKE
    
    NEED_INPUT -->|否| INVOKE[调用 Tool]
    
    INVOKE --> RESULT{执行结果}
    RESULT -->|成功| UPDATE_SUCCESS[更新状态为 completed]
    RESULT -->|失败| RETRY_CHECK{重试次数<br/>< 3?}
    
    RETRY_CHECK -->|是| RETRY[递增重试计数]
    RETRY --> FILL_PARAM
    
    RETRY_CHECK -->|否| UPDATE_FAIL[更新状态为 failed]
    
    UPDATE_SUCCESS --> NEXT[返回 Supervisor]
    UPDATE_FAIL --> NEXT
```

### 3.4 SubGraph 嵌套结构

```mermaid
graph TB
    subgraph "Main Graph"
        M_START((START)) --> M_SV[Supervisor]
        M_SV --> M_ROUTE{路由}
        M_ROUTE -->|planner| M_PL[Planner SubGraph]
        M_ROUTE -->|executor| M_EX[Executor SubGraph]
        M_ROUTE -->|validator| M_VL[Validator SubGraph]
        M_ROUTE -->|end| M_END((END))
        M_PL & M_EX --> M_SV
        M_VL --> M_END
    end
    
    subgraph "Planner SubGraph"
        P_START((START)) --> P_INTENT[意图解析节点]
        P_INTENT --> P_DECOMP[任务拆解节点]
        P_DECOMP --> P_DEP[依赖推断节点]
        P_DEP --> P_END((END))
    end
    
    subgraph "Executor SubGraph"
        E_START((START)) --> E_SELECT[Tool选择节点]
        E_SELECT --> E_FILL[参数填充节点]
        E_FILL --> E_INVOKE[Tool调用节点]
        E_INVOKE --> E_PROC[结果处理节点]
        E_PROC --> E_CHECK{继续?}
        E_CHECK -->|是| E_SELECT
        E_CHECK -->|否| E_END((END))
    end
    
    subgraph "Validator SubGraph"
        V_START((START)) --> V_CHECK[结果校验节点]
        V_CHECK --> V_ATTR[错误归因节点]
        V_ATTR --> V_SUMM[摘要生成节点]
        V_SUMM --> V_END((END))
    end
```

---

## 4. 数据模型设计

### 4.1 核心实体关系图

```mermaid
erDiagram
    CONVERSATION ||--o{ MESSAGE : contains
    CONVERSATION ||--o{ TASK : creates
    TASK ||--o{ TODO_STEP : has
    TODO_STEP ||--o| TOOL_INVOCATION : executes
    TODO_STEP ||--o| PENDING_CONFIG : requires
    TOOL ||--o{ TOOL_INVOCATION : called_by
    KNOWLEDGE_DOC ||--o{ EMBEDDING_CHUNK : split_into
    
    CONVERSATION {
        string thread_id PK
        string title
        datetime created_at
        datetime updated_at
        json checkpoint_data
    }
    
    MESSAGE {
        string id PK
        string thread_id FK
        enum role "user|assistant|system"
        text content
        datetime timestamp
        json metadata
    }
    
    TASK {
        string task_id PK
        string thread_id FK
        string title
        enum status
        int progress
        datetime created_at
        datetime updated_at
    }
    
    TODO_STEP {
        string id PK
        string task_id FK
        string description
        string tool_name
        enum status
        int progress
        text result
        text error
        json depends_on
        int retry_count
    }
    
    TOOL {
        string name PK
        string description
        json args_schema
        json return_schema
        bool requires_approval
        int timeout_seconds
    }
    
    TOOL_INVOCATION {
        string id PK
        string step_id FK
        string tool_name FK
        json input_args
        json output
        int duration_ms
        datetime invoked_at
    }
    
    PENDING_CONFIG {
        string id PK
        string step_id FK
        string title
        text description
        json fields
        json values
        enum status "pending|submitted|cancelled"
    }
    
    KNOWLEDGE_DOC {
        string doc_id PK
        string title
        text content
        string source
        json metadata
        datetime indexed_at
    }
    
    EMBEDDING_CHUNK {
        string chunk_id PK
        string doc_id FK
        text content
        vector embedding
        int chunk_index
    }
```

### 4.2 Agent State 结构设计

```mermaid
classDiagram
    class AgentState {
        +List~BaseMessage~ messages
        +String parsed_intent
        +List~TodoStep~ todo_list
        +int current_step
        +FinalStatus final_status
        +PendingConfig pending_config
        +String error_info
        +AgentType current_agent
    }
    
    class TodoStep {
        +String id
        +String description
        +String tool_name
        +StepStatus status
        +String result
        +String error
        +List~String~ depends_on
        +int progress
        +int retry_count
    }
    
    class PendingConfig {
        +String step_id
        +String title
        +String description
        +List~ConfigFormField~ fields
        +Dict values
    }
    
    class ConfigFormField {
        +String name
        +String label
        +FieldType field_type
        +bool required
        +Any default
        +List~Option~ options
        +String placeholder
        +String description
    }
    
    class StepStatus {
        <<enumeration>>
        PENDING
        RUNNING
        COMPLETED
        FAILED
    }
    
    class FinalStatus {
        <<enumeration>>
        PENDING
        RUNNING
        SUCCESS
        FAILED
        WAITING_INPUT
    }
    
    class AgentType {
        <<enumeration>>
        SUPERVISOR
        PLANNER
        EXECUTOR
        VALIDATOR
    }
    
    AgentState "1" *-- "*" TodoStep
    AgentState "1" *-- "0..1" PendingConfig
    PendingConfig "1" *-- "*" ConfigFormField
    TodoStep --> StepStatus
    AgentState --> FinalStatus
    AgentState --> AgentType
```

### 4.3 Checkpoint 存储结构

```mermaid
graph LR
    subgraph "Thread 维度"
        T1[thread_001]
        T2[thread_002]
    end
    
    subgraph "Checkpoint 链"
        T1 --> C1_1[checkpoint_v1]
        C1_1 --> C1_2[checkpoint_v2]
        C1_2 --> C1_3[checkpoint_v3]
        
        T2 --> C2_1[checkpoint_v1]
        C2_1 --> C2_2[checkpoint_v2]
    end
    
    subgraph "Checkpoint 内容"
        direction TB
        C1_3 --> STATE[AgentState 快照]
        C1_3 --> META[元数据]
        C1_3 --> WRITES[pending_writes]
        
        STATE --> |包含| MSG[messages]
        STATE --> |包含| TODO[todo_list]
        STATE --> |包含| STATUS[final_status]
    end
```

---

## 5. API 接口设计

### 5.1 RESTful API 结构

```mermaid
graph LR
    subgraph "/api/v1"
        subgraph "/chat"
            POST_SEND[POST /send]
            POST_STREAM[POST /stream]
            GET_STATE[GET /state/:thread_id]
            POST_RESUME[POST /resume/:thread_id]
        end
        
        subgraph "/tasks"
            GET_TASKS[GET /]
            GET_TASK[GET /:task_id]
            POST_CREATE[POST /create]
            PUT_STATUS[PUT /:task_id/status]
            DELETE_TASK[DELETE /:task_id]
            GET_STEPS[GET /:task_id/steps]
        end
        
        subgraph "/conversations"
            GET_CONVS[GET /]
            GET_CONV[GET /:thread_id]
            POST_CONV[POST /create]
            PUT_CONV[PUT /:thread_id]
            DELETE_CONV[DELETE /:thread_id]
        end
        
        subgraph "/tools"
            GET_TOOLS[GET /]
            GET_TOOL[GET /:name]
            GET_SCHEMA[GET /:name/schema]
        end
        
        subgraph "/knowledge"
            POST_SEARCH[POST /search]
            POST_UPLOAD[POST /upload]
            DELETE_DOC[DELETE /:doc_id]
        end
    end
```

### 5.2 SSE 事件流设计

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    
    C->>S: POST /chat/stream
    Note over S: 建立 SSE 连接
    
    S-->>C: event: update<br/>data: {node: "supervisor", ...}
    S-->>C: event: update<br/>data: {node: "planner", todo_list: [...]}
    S-->>C: event: update<br/>data: {node: "executor", step: {...}}
    
    alt 需要用户输入
        S-->>C: event: interrupt<br/>data: {pending_config: {...}}
        Note over C: 用户填写表单
        C->>S: POST /chat/resume
        S-->>C: event: update<br/>data: {resumed: true}
    end
    
    S-->>C: event: update<br/>data: {node: "validator", ...}
    S-->>C: event: done<br/>data: {thread_id: "xxx"}
    
    Note over S: 关闭连接
```

### 5.3 核心接口契约

```yaml
# Chat Send Request
ChatRequest:
  message: string (required)
  thread_id: string (optional)
  config_response: object (optional)

# Chat Response
ChatResponse:
  thread_id: string
  message: ChatMessage
  todo_list: TodoStep[]
  pending_config: PendingConfig | null
  task_status: TaskStatus

# SSE Event Types
SSEEvent:
  type: "update" | "interrupt" | "error" | "done"
  thread_id: string
  data:
    node?: string
    content?: string
    todo_list?: TodoStep[]
    status?: string
    pending_config?: PendingConfig
    error?: string
```

---

## 6. 前端架构设计

### 6.1 组件层次结构

```mermaid
graph TD
    subgraph "App Shell"
        App[App.tsx]
        App --> Router[BrowserRouter]
        Router --> Workstation[Workstation Page]
    end
    
    subgraph "Page Layout"
        Workstation --> Sidebar[Left Sidebar]
        Workstation --> Main[Main Content]
        Workstation --> Panel[Right Panel]
        Workstation --> Modal[Config Modal]
    end
    
    subgraph "Sidebar Components"
        Sidebar --> Logo[Logo]
        Sidebar --> ConvList[ConversationList]
        ConvList --> ConvItem[ConversationItem]
    end
    
    subgraph "Main Components"
        Main --> Header[Chat Header]
        Main --> Messages[Message List]
        Main --> Input[Chat Input]
        Messages --> ChatMsg[ChatMessage]
        ChatMsg --> TodoList[TodoList]
        TodoList --> TodoItem[TodoItem]
    end
    
    subgraph "Panel Components"
        Panel --> TaskPanel[TaskPanel]
        TaskPanel --> TaskCard[TaskCard]
        TaskCard --> Progress[ProgressBar]
        TaskCard --> StepDots[StepIndicators]
    end
    
    subgraph "Modal Components"
        Modal --> ConfigModal[ConfigModal]
        ConfigModal --> FormField[FormField]
        FormField --> TextInput
        FormField --> Select
        FormField --> Switch
        FormField --> Chips
    end
```

### 6.2 状态管理架构

```mermaid
graph TB
    subgraph "Global State (Zustand)"
        ChatStore[ChatStore]
        ChatStore --> ThreadId[threadId]
        ChatStore --> Messages[messages]
        ChatStore --> TodoList[todoList]
        ChatStore --> TaskStatus[taskStatus]
        ChatStore --> PendingConfig[pendingConfig]
        ChatStore --> Conversations[conversations]
        ChatStore --> UIState[isLoading, inputValue]
    end
    
    subgraph "Server State (TanStack Query)"
        QueryClient[QueryClient]
        QueryClient --> ConvQuery[useConversations]
        QueryClient --> TaskQuery[useTasks]
        QueryClient --> ToolQuery[useTools]
    end
    
    subgraph "Local State (useState)"
        CompState[Component State]
        CompState --> FormValues[表单值]
        CompState --> Expanded[展开/折叠]
        CompState --> Hover[悬停状态]
    end
    
    subgraph "Derived State"
        Selectors[Selectors]
        ChatStore --> Selectors
        Selectors --> CompletedCount[completedCount]
        Selectors --> CurrentStep[currentStep]
        Selectors --> Progress[progress]
    end
```

### 6.3 数据流向图

```mermaid
flowchart LR
    subgraph "用户交互"
        USER[用户输入]
        CLICK[点击操作]
    end
    
    subgraph "Actions"
        SEND[sendMessage]
        SUBMIT[submitConfig]
        SELECT[selectConversation]
    end
    
    subgraph "API Layer"
        FETCH[fetch /api/...]
        SSE[EventSource]
    end
    
    subgraph "State Updates"
        STORE[Zustand Store]
        QUERY[Query Cache]
    end
    
    subgraph "UI Render"
        COMP[React Components]
    end
    
    USER --> SEND
    CLICK --> SUBMIT & SELECT
    SEND & SUBMIT --> FETCH
    FETCH --> SSE
    SSE --> |事件流| STORE
    FETCH --> |响应| STORE & QUERY
    STORE & QUERY --> COMP
    COMP --> |用户看到| USER
```

### 6.4 响应式布局断点

```
┌─────────────────────────────────────────────────────────────────┐
│                     Desktop (≥1280px)                           │
│  ┌──────────┬────────────────────────────────┬─────────────┐   │
│  │ Sidebar  │         Chat Area              │  TaskPanel  │   │
│  │  288px   │          flex-1                │    320px    │   │
│  └──────────┴────────────────────────────────┴─────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Tablet (768px-1279px)                       │
│  ┌──────────┬────────────────────────────────────────────┐     │
│  │ Sidebar  │              Chat Area                     │     │
│  │  240px   │              flex-1                        │     │
│  └──────────┴────────────────────────────────────────────┘     │
│  [TaskPanel 折叠为底部抽屉]                                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Mobile (<768px)                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Chat Area                            │   │
│  │                    full width                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│  [Sidebar 变为汉堡菜单] [TaskPanel 变为浮动按钮]                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 知识库与 RAG 设计

### 7.1 RAG Pipeline 架构

```mermaid
flowchart TB
    subgraph "文档摄入 Pipeline"
        DOC[原始文档] --> PARSE[文档解析]
        PARSE --> CHUNK[分块处理]
        CHUNK --> EMBED[向量化]
        EMBED --> INDEX[索引存储]
        
        PARSE --> |PDF/Word| EXTRACT[文本提取]
        PARSE --> |Markdown| SPLIT[标题分割]
        PARSE --> |API Doc| STRUCT[结构化解析]
        
        CHUNK --> |512 tokens| OVERLAP[重叠分块]
        OVERLAP --> |128 overlap| EMBED
    end
    
    subgraph "检索 Pipeline"
        QUERY[用户查询] --> Q_EMBED[查询向量化]
        Q_EMBED --> SEARCH[向量检索]
        SEARCH --> RERANK[重排序]
        RERANK --> FILTER[过滤去重]
        FILTER --> CONTEXT[上下文组装]
    end
    
    subgraph "增强生成"
        CONTEXT --> PROMPT[Prompt 构建]
        PROMPT --> LLM[LLM 推理]
        LLM --> RESPONSE[生成响应]
    end
    
    INDEX --> |FAISS Index| SEARCH
```

### 7.2 知识类型与检索策略

```mermaid
graph TB
    subgraph "知识类型"
        K1[专业术语表]
        K2[系统设计文档]
        K3[API 规范]
        K4[历史案例]
        K5[FAQ 问答对]
    end
    
    subgraph "检索策略"
        S1[精确匹配]
        S2[语义检索]
        S3[混合检索]
    end
    
    subgraph "应用场景"
        A1[意图理解]
        A2[参数填充]
        A3[错误诊断]
    end
    
    K1 --> S1 --> A1 & A2
    K2 & K3 --> S2 --> A2
    K4 & K5 --> S3 --> A3
    
    S3 --> |BM25 + Dense| FUSION[分数融合]
```

### 7.3 上下文窗口管理

```mermaid
graph LR
    subgraph "Token 预算分配 (4000 tokens)"
        SYS[System Prompt<br/>~500 tokens]
        KNOW[知识上下文<br/>~1500 tokens]
        HIST[对话历史<br/>~1500 tokens]
        RESP[响应空间<br/>~500 tokens]
    end
    
    subgraph "裁剪策略"
        KNOW --> |Top-K=5| TRIM_K[保留最相关]
        HIST --> |Last-N| TRIM_H[保留最近]
        HIST --> |Summarize| SUMM[摘要压缩]
    end
    
    SYS --> FINAL[最终 Prompt]
    TRIM_K --> FINAL
    TRIM_H --> FINAL
    SUMM -.-> FINAL
```

---

## 8. Tool 注册与编排设计

### 8.1 Tool 生命周期

```mermaid
stateDiagram-v2
    [*] --> Defining: @tool 装饰器
    Defining --> Registering: ToolRegistry.register()
    Registering --> Discovering: Agent 初始化
    Discovering --> Binding: llm.bind_tools()
    
    Binding --> Available: 可被调用
    Available --> Selecting: LLM 选择
    Selecting --> Validating: 参数校验
    Validating --> Invoking: 执行调用
    
    Invoking --> Success: 返回结果
    Invoking --> Failure: 抛出异常
    
    Failure --> Retrying: retry_count < 3
    Retrying --> Validating
    
    Failure --> Failed: retry_count >= 3
    Success --> [*]
    Failed --> [*]
```

### 8.2 Tool Schema 设计规范

```mermaid
classDiagram
    class Tool {
        <<interface>>
        +name: str
        +description: str
        +args_schema: Type[BaseModel]
        +invoke(input): str
    }
    
    class SimpleTool {
        @tool 装饰器
        +自动推断 schema
    }
    
    class ComplexTool {
        @tool(args_schema=...)
        +Pydantic 定义
    }
    
    class StatefulTool {
        +InjectedState 参数
        +运行时注入状态
    }
    
    class ApprovalTool {
        +requires_approval: True
        +触发 interrupt
    }
    
    Tool <|-- SimpleTool
    Tool <|-- ComplexTool
    Tool <|-- StatefulTool
    Tool <|-- ApprovalTool
```

### 8.3 依赖编排算法

```mermaid
flowchart TD
    START[开始编排] --> PARSE[解析任务步骤]
    PARSE --> BUILD[构建依赖图]
    
    BUILD --> TOPO[拓扑排序]
    TOPO --> VALID{有环?}
    
    VALID -->|是| ERROR[报告循环依赖]
    VALID -->|否| LEVEL[划分执行层级]
    
    LEVEL --> L0[Level 0: 无依赖步骤]
    LEVEL --> L1[Level 1: 依赖 L0]
    LEVEL --> LN[Level N: 依赖 LN_1]
    
    L0 --> PARALLEL[同层可并行]
    L1 --> PARALLEL
    LN --> PARALLEL
    
    PARALLEL --> SCHEDULE[调度执行]
```

```
示例依赖图:
┌─────────────────────────────────────────────────┐
│  Step1 ──┬──► Step3 ──► Step5                   │
│          │                                      │
│  Step2 ──┴──► Step4 ──┘                         │
│                                                 │
│  Level 0: [Step1, Step2]  (可并行)              │
│  Level 1: [Step3, Step4]  (可并行)              │
│  Level 2: [Step5]                               │
└─────────────────────────────────────────────────┘
```

### 8.4 参数填充策略

```mermaid
flowchart TD
    PARAM[待填充参数] --> SOURCE{参数来源}
    
    SOURCE -->|显式上下文| CTX[从对话/状态提取]
    SOURCE -->|知识检索| RAG[RAG 检索相关知识]
    SOURCE -->|前置步骤| PREV[从依赖步骤结果]
    SOURCE -->|用户配置| USER[触发配置表单]
    SOURCE -->|默认值| DEF[使用 Schema 默认]
    
    CTX --> MERGE[参数合并]
    RAG --> MERGE
    PREV --> MERGE
    USER --> MERGE
    DEF --> MERGE
    
    MERGE --> VALIDATE{校验完整性}
    VALIDATE -->|通过| READY[参数就绪]
    VALIDATE -->|缺失必填| USER
```

---

## 9. Human-in-the-Loop 设计

### 9.1 中断触发场景

```mermaid
graph TB
    subgraph "主动中断"
        A1[敏感操作审批]
        A2[必填参数缺失]
        A3[多选项确认]
        A4[执行前预览]
    end
    
    subgraph "被动中断"
        B1[Tool 执行失败]
        B2[超时重试]
        B3[资源不可用]
    end
    
    subgraph "中断处理"
        A1 & A2 & A3 & A4 --> INT[interrupt]
        B1 & B2 & B3 --> INT
        
        INT --> PEND[设置 pending_config]
        PEND --> SSE[发送 interrupt 事件]
        SSE --> UI[前端显示表单]
    end
    
    subgraph "恢复处理"
        UI --> SUBMIT[用户提交]
        SUBMIT --> RESUME[resume]
        RESUME --> CONTINUE[继续执行]
    end
```

### 9.2 配置表单动态生成

```mermaid
flowchart LR
    subgraph "Schema 解析"
        TOOL_SCHEMA[Tool Args Schema] --> PARSE[解析 Pydantic]
        PARSE --> FIELDS[提取字段]
    end
    
    subgraph "字段映射"
        FIELDS --> MAP{字段类型}
        MAP -->|str| TEXT[TextInput]
        MAP -->|int/float| NUM[NumberInput]
        MAP -->|bool| SWITCH[Switch]
        MAP -->|Literal| SELECT[Select]
        MAP -->|List| CHIPS[Chips]
        MAP -->|Optional| OPT[标记可选]
    end
    
    subgraph "表单渲染"
        TEXT & NUM & SWITCH & SELECT & CHIPS --> FORM[ConfigModal]
        OPT --> FORM
        FORM --> VALID[客户端校验]
        VALID --> SUBMIT[提交]
    end
```

### 9.3 审批工作流

```mermaid
sequenceDiagram
    participant E as Executor
    participant S as State
    participant F as Frontend
    participant U as User
    
    E->>E: 检测到敏感操作
    E->>S: interrupt({action, step_id, ...})
    S->>S: 保存 pending_writes
    S-->>F: SSE event: interrupt
    
    F->>F: 渲染审批界面
    F->>U: 显示操作详情
    
    alt 用户批准
        U->>F: 点击确认
        F->>S: POST /resume (approved: true)
        S->>E: Command(resume)
        E->>E: 继续执行 Tool
    else 用户拒绝
        U->>F: 点击取消
        F->>S: POST /resume (approved: false)
        S->>S: 更新状态为 cancelled
    else 用户修改
        U->>F: 修改参数
        F->>S: POST /resume (modified_args)
        S->>E: Command(resume, update)
        E->>E: 使用新参数执行
    end
```

---

## 10. 部署架构设计

### 10.1 容器化部署架构

```mermaid
graph TB
    subgraph "Kubernetes Cluster"
        subgraph "Ingress"
            ING[Nginx Ingress]
        end
        
        subgraph "Frontend Pods"
            FE1[React App]
            FE2[React App]
        end
        
        subgraph "Backend Pods"
            BE1[FastAPI]
            BE2[FastAPI]
            BE3[FastAPI]
        end
        
        subgraph "Data Layer"
            REDIS[(Redis Cluster)]
            MYSQL[(MySQL Primary)]
            MYSQL_R[(MySQL Replica)]
            FAISS[(FAISS Index<br/>PVC)]
        end
        
        subgraph "External"
            DASH[DashScope API]
            BIZ[业务系统 API]
        end
    end
    
    ING --> FE1 & FE2
    ING --> BE1 & BE2 & BE3
    BE1 & BE2 & BE3 --> REDIS
    BE1 & BE2 & BE3 --> MYSQL
    BE1 & BE2 & BE3 --> FAISS
    BE1 & BE2 & BE3 --> DASH
    BE1 & BE2 & BE3 --> BIZ
    MYSQL --> MYSQL_R
```

### 10.2 高可用设计

```mermaid
graph LR
    subgraph "负载均衡"
        LB[Load Balancer]
    end
    
    subgraph "应用层 HA"
        LB --> APP1[Instance 1]
        LB --> APP2[Instance 2]
        LB --> APP3[Instance 3]
    end
    
    subgraph "数据层 HA"
        APP1 & APP2 & APP3 --> REDIS_C[Redis Sentinel]
        REDIS_C --> REDIS_M[(Master)]
        REDIS_C --> REDIS_S1[(Slave 1)]
        REDIS_C --> REDIS_S2[(Slave 2)]
        
        APP1 & APP2 & APP3 --> MYSQL_P[(MySQL Primary)]
        MYSQL_P --> MYSQL_S[(MySQL Standby)]
    end
    
    subgraph "故障转移"
        REDIS_M -.->|自动切换| REDIS_S1
        MYSQL_P -.->|手动/自动切换| MYSQL_S
    end
```

### 10.3 监控与可观测性

```mermaid
graph TB
    subgraph "应用指标"
        APP[Application]
        APP --> PROM[Prometheus]
        APP --> TRACE[Jaeger Tracing]
        APP --> LOG[Loki Logs]
    end
    
    subgraph "业务指标"
        BIZ_M[业务埋点]
        BIZ_M --> |对话数| PROM
        BIZ_M --> |任务完成率| PROM
        BIZ_M --> |Tool 调用统计| PROM
        BIZ_M --> |LLM 延迟| PROM
    end
    
    subgraph "可视化"
        PROM --> GRAFANA[Grafana]
        TRACE --> GRAFANA
        LOG --> GRAFANA
    end
    
    subgraph "告警"
        GRAFANA --> ALERT[AlertManager]
        ALERT --> NOTIFY[通知渠道]
    end
```

---

## 附录 A: 设计决策记录 (ADR)

### ADR-001: 选择 LangGraph 而非 AutoGen

**状态**: 已采纳

**上下文**: 需要选择 Multi-Agent 框架

**决策**: 采用 LangGraph 1.0

**理由**:
1. 原生支持 Checkpoint 持久化
2. 与 LangChain 生态深度集成
3. StateGraph 提供细粒度控制
4. Human-in-the-Loop 原生支持

### ADR-002: 前端状态管理选择

**状态**: 已采纳

**上下文**: 需要管理复杂的聊天和任务状态

**决策**: Zustand + TanStack Query

**理由**:
1. Zustand 轻量且符合 React 习惯
2. TanStack Query 处理服务端状态缓存
3. 避免 Redux 的样板代码

### ADR-003: SSE vs WebSocket

**状态**: 已采纳

**上下文**: 实现流式输出

**决策**: 使用 SSE (Server-Sent Events)

**理由**:
1. 单向流满足需求
2. 原生 HTTP，无需额外协议
3. 自动重连机制
4. 更简单的服务端实现

---

## 附录 B: 术语表

| 术语 | 定义 |
|------|------|
| Thread | LangGraph 会话线程，关联一组 Checkpoint |
| Checkpoint | 状态快照，每个 super-step 后自动保存 |
| Super-step | 图执行的一个完整步骤（节点执行 + 状态更新） |
| Handoff | Agent 间任务交接机制 |
| Interrupt | Human-in-the-Loop 中断点 |
| Tool | 使用 @tool 装饰器封装的可调用函数 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |

---

*文档结束*
