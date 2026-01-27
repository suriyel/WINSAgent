# Product Requirement Specification (Spec)

## 1. 业务目标 (Objective)

### 解决的问题
构建一个基于LangChain 1.2.5的AI Agent工作台，实现：
- 自动理解用户意图，精准调用存量系统API
- 按需获取领域知识（专业术语表、设计文档），支持动态更新
- 通过SubAgent分发复杂任务，可视化TODO步骤进度
- 提供精美UI设计，支持动态配置表单和流式输出
- 支持Human-in-the-Loop交互，用户可approve/edit/reject Tool调用配置

### 成功指标
- Agent能正确识别并调用100个以内预封装的Tool
- 领域知识检索准确率≥90%
- TODO步骤状态实时更新，支持replan
- SSE流式输出延迟≤100ms
- 用户配置面板响应时间≤1s

---

## 2. 功能清单 (Features)

| 模块 | 功能描述 | 验收标准 (AC) | 优先级 |
| :--- | :------- | :------------ | :----- |
| **领域知识管理** | Markdown文档的FAISS向量存储与检索 | 术语表和设计文档分库存储，支持定时增量更新，检索触发时机为识别专业术语时 | P0 |
| **Tool编排** | 100以内Tool的预封装与依赖关系管理 | 依赖关系在Tool的description中描述，支持静态+动态结合的依赖推断 | P0 |
| **Agent-as-Tool** | SubAgent封装为主Agent的Tool | 使用@tool装饰器包装Agent的invoke方法，独立上下文，可配置state共享 | P0 |
| **TODO管理** | TodoListMiddleware集成 | 支持pending/in_progress/completed/failed/replan状态，每轮自动check状态 | P0 |
| **动态配置UI** | Tool调用参数的可折叠配置卡片 | LLM推断默认值，用户可approve/edit/reject，reject导致整体任务失败 | P0 |
| **Human-in-the-Loop** | HumanInTheLoopMiddleware集成 | Tool调用前阻塞等待用户确认，支持approve/edit/reject三种决策 | P0 |
| **流式输出** | SSE实时推送Agent执行状态 | Token级流式输出，事件类型包括thinking/tool.call/tool.result/todo.state | P0 |
| **进度可视化** | 步骤分解进度条 | 同一任务的步骤分解进度，不支持并行Tool调用 | P1 |
| **UI设计** | 新瑞士主义风格工作台 | 配色方案完全采用UCD设计规范，React + Tailwind CSS | P1 |

---

## 3. 技术约束与集成 (Technical Constraints)

### 数据流向
```
用户输入 → Agent主入口 → LLM → Tool选择 → SubAgent分发(可选) → Tool调用
                         ↓                  ↑
                    FAISS检索 ← Markdown文档(本地)
                         ↓
                    TodoListMiddleware检查
                         ↓
                    HumanInTheLoop确认(阻塞)
                         ↓
                    SSE流式输出 → 前端React
```

### 第三方接口
- **LangChain 1.2.5**：提供`create_agent`、`middleware`、`TodoListMiddleware`、`HumanInTheLoopMiddleware`、`stream` API
- **FAISS**：向量检索引擎（`langchain-community` + `faiss-cpu`）
- **LLM提供商**：待定（需支持tool binding和streaming）
- **MySQL**：FAISS Index持久化存储（BLOB字段），验证阶段使用InMemorySaver

### 异常处理逻辑
- Tool调用失败 → 整个任务失败
- HumanInTheLoop reject → 整个任务失败
- TODO步骤失败 → 整个任务失败（不重试、不跳过、不回滚）
- FAISS检索失败 → 降级为无检索模式继续执行
- SSE连接断开 → 前端自动重连

---

## 4. 非功能性需求

### 性能要求
- FAISS检索响应时间 ≤ 500ms
- SSE流式输出延迟 ≤ 100ms
- 用户配置面板响应时间 ≤ 1s
- 支持并发用户数：待定

### 安全性/权限控制
- HumanInTheLoop确保敏感Tool调用需用户确认
- FAISS Index存储于MySQL，访问需认证
- 前后端独立部署，API需鉴权

### 可维护性
- 代码遵循LangChain 1.2.5规范
- 中间件可插拔设计（TodoListMiddleware、HumanInTheLoopMiddleware）
- UI组件化，支持主题定制

---

## 5. 未决/待定事项 (TBD)

1. **LLM提供商选型**：待确定具体使用的LLM（需支持tool binding和streaming）
2. **并发用户数**：性能基准待确定
3. **FAISS定时更新频率**：具体时间间隔待定（天/小时级）
4. **SubAgent预定义规则**：Tool标签分类标准待细化（耗时/复杂/外部调用）
5. **部署环境**：生产环境部署架构待定

---

## 6. UI设计规范（基于UCD设计.md）

| 元素 | 色值 | 用途 |
|-----|------|-----|
| 主色-薰衣草紫 | `#A78BFA` | 交互高亮、确认按钮 |
| 辅色-天空蓝 | `#60A5FA` | 运行中状态 |
| 成功-薄荷绿 | `#34D399` | 完成状态 |
| 错误-珊瑚红 | `#F87171` | 失败状态 |
| 背景色 | `#FAFAFA` | 页面背景 |
| 卡片色 | `#FFFFFF` | 组件卡片 |
| 主文字 | `#1F2937` | 标题、正文 |
| 次文字 | `#6B7280` | 辅助说明 |
| 弱文字 | `#9CA3AF` | 占位符、禁用状态 |
