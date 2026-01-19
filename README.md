# WINS Agent - 智能任务编排平台

基于 LangGraph 1.0 的 AI Agent 工作台，用于复杂业务系统的自然语言任务编排。

## 技术栈

| 层级 | 组件 | 版本 |
|------|------|------|
| 前端 | React | 18.3.1 |
| 前端 | Vite | 5.1.0 |
| 前端 | TailwindCSS | 3.4.1 |
| Agent | LangGraph | 1.0.6 |
| Agent | LangChain | 1.2.5 |
| LLM | Qwen3-72B-Instruct | API |
| 向量库 | FAISS | 1.10.0 |
| 后端 | FastAPI | 0.128.0 |
| 验证 | Pydantic | 2.6.3 |

## 项目结构

```
WINSAgent/
├── backend/                    # 后端 FastAPI
│   ├── app/
│   │   ├── agents/            # LangGraph Agent
│   │   │   ├── state.py       # Agent State 定义
│   │   │   ├── supervisor.py  # Supervisor Agent
│   │   │   ├── planner.py     # Planner SubGraph
│   │   │   ├── executor.py    # Executor SubGraph
│   │   │   ├── validator.py   # Validator SubGraph
│   │   │   └── graph.py       # 主图组装
│   │   ├── tools/             # Tool 定义
│   │   ├── knowledge/         # RAG 知识库
│   │   ├── api/               # API 路由
│   │   ├── models/            # Pydantic 模型
│   │   ├── config.py          # 配置管理
│   │   └── main.py            # FastAPI 入口
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # 前端 React
│   ├── src/
│   │   ├── components/        # UI 组件
│   │   ├── pages/             # 页面
│   │   ├── hooks/             # 自定义 Hooks
│   │   ├── stores/            # 状态管理
│   │   ├── styles/            # 样式
│   │   ├── types/             # TypeScript 类型
│   │   └── utils/             # 工具函数
│   ├── package.json
│   └── vite.config.ts
├── scripts/                    # 启动脚本
└── docs/                       # 设计文档
```

## 快速开始

### 1. 后端设置

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 启动服务
python run.py
```

### 2. 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 3. 访问应用

- 前端: http://localhost:3000
- API 文档: http://localhost:8000/docs

## Agent 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Supervisor Agent                            │
│                    (协调调度中心)                                 │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Planner Agent  │  │ Executor Agent  │  │ Validator Agent │
│  (任务规划)     │  │  (任务执行)     │  │  (结果校验)     │
│                 │  │                 │  │                 │
│ • 意图解析      │  │ • Tool 调用     │  │ • 结果判定      │
│ • 任务拆解      │  │ • 参数填充      │  │ • 错误归因      │
│ • 依赖推断      │  │ • 重试处理      │  │ • 状态说明      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## 主要功能

- **对话交互**: 自然语言输入，多轮对话支持
- **任务规划**: 自动拆解复杂任务为可执行步骤
- **TODO 可视化**: 实时显示任务进度，支持折叠
- **Human-in-the-Loop**: 敏感操作前暂停等待用户审批
- **动态配置表单**: 根据 Tool Schema 自动生成配置界面
- **流式输出**: 实时展示 Agent 思考过程

## 设计风格

采用**新瑞士主义 (Neo-Swiss)** 设计风格：

- 配色: 薰衣草紫 (#A78BFA) / 天空蓝 (#60A5FA) / 薄荷绿 (#34D399)
- 大量留白，严格网格布局
- 功能性极简美学

## License

MIT
