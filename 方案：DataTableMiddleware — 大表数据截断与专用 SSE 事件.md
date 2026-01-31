# 方案：DataTableMiddleware — 大表数据截断与专用 SSE 事件

## 核心思路

新增 `DataTableMiddleware`，使用 `wrap_tool_call` 钩子拦截工具返回结果：

- 解析 `[DATA_TABLE]` 块，提取完整结构化数据
- 截断 ToolMessage.content 至 top 5 行（减少 LLM 上下文）
- 将完整数据附在 `ToolMessage.additional_kwargs["table_data"]` 中
- event_mapper 检测到该字段后，额外发射 `table.data` SSE 事件
- 前端用专用 `DataTable` 组件展示全量分页数据

## 文件变更清单

### 新建（2 个文件）

| 文件                                         | 说明                                |
| -------------------------------------------- | ----------------------------------- |
| `backend/app/agent/middleware/data_table.py` | DataTableMiddleware 实现            |
| `frontend/src/components/chat/DataTable.tsx` | 全量表格展示组件（分页 + CSV 导出） |

### 修改（5 个文件）

| 文件                                             | 变更内容                                                     |
| ------------------------------------------------ | ------------------------------------------------------------ |
| `backend/app/agent/core.py`                      | 导入并注册 DataTableMiddleware 到 middleware 列表            |
| `backend/app/sse/event_mapper.py`                | ToolMessage 处理处增加 `table.data` SSE 事件发射             |
| `frontend/src/types/index.ts`                    | 新增 `TableData` 接口，`ToolCallInfo` 加 `tableData` 字段，`SSEEventType` 加 `"table.data"` |
| `frontend/src/stores/chatStore.ts`               | handleSSEEvent 新增 `"table.data"` case                      |
| `frontend/src/components/chat/MessageBubble.tsx` | 当 `tc.tableData` 存在时使用 DataTable 组件替代内联表格      |

------

## 实现步骤

### 1. 后端：创建 DataTableMiddleware

**文件**: `backend/app/agent/middleware/data_table.py`



```python
class DataTableMiddleware(AgentMiddleware[AgentState, ContextT]):
    name: str = "data_table"

    def wrap_tool_call(self, request, handler):
        result = handler(request)  # ToolMessage

        if not isinstance(result, ToolMessage) or "[DATA_TABLE]" not in str(result.content):
            return result

        # 正则匹配所有 [DATA_TABLE]...[/DATA_TABLE] 块
        # 每个块：解析 CSV → TableData(headers, rows, total_rows, truncated)
        # 在 content 中将每个块替换为 top 5 行版本 + "... 共N条记录，仅展示前5条"
        # 完整数据存入 additional_kwargs["table_data"]

        return ToolMessage(
            content=truncated_content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=getattr(result, "status", "success"),
            additional_kwargs={
                **result.additional_kwargs,
                "table_data": [td.model_dump() for td in tables],
            },
        )
```

关键逻辑：

- 使用 `re.compile(r"\[DATA_TABLE\](.*?)\[/DATA_TABLE\]", re.DOTALL)` 提取所有表格块
- CSV 解析：按 `\n` 分行，首行为 headers，其余为 data rows
- 截断：保留 header + 前 5 行 + 摘要行
- 小表（≤5 行）：不截断 content，但仍提取结构化数据给前端
- 多表：逐一处理，`table_data` 为数组

### 2. 后端：注册到 middleware 列表

**文件**: `backend/app/agent/core.py`

在 `SubAgentMiddleware` 之后、`SuggestionsMiddleware` 之前插入：



```python
from app.agent.middleware.data_table import DataTableMiddleware

middleware = [
    subagent_mw,
    DataTableMiddleware(),      # ← 新增
    SuggestionsMiddleware(),
    ContextEditingMiddleware(...),
]
```

### 3. 后端：event_mapper 发射 `table.data` 事件

**文件**: `backend/app/sse/event_mapper.py`

在 `tool.result` 事件发射后，检查 `additional_kwargs`：



```python
elif isinstance(msg, ToolMessage):
    # ... 现有 tool.result 发射逻辑 ...
    yield _sse("tool.result", {...})

    # 新增：检查是否有表格数据
    table_data = msg.additional_kwargs.get("table_data")
    if table_data:
        yield _sse("table.data", {
            "execution_id": getattr(msg, "tool_call_id", str(uuid.uuid4())),
            "tables": table_data,
        })
```

`table.data` SSE 事件格式：



```json
{
  "execution_id": "tc_123",
  "tables": [
    {
      "headers": ["小区id", "longitude", "latitude", "RSRP均值(dBm)"],
      "rows": [["460-00-100001", "116.4521", "39.9345", "-95.3"], ...],
      "total_rows": 15,
      "truncated": true
    }
  ]
}
```

### 4. 前端：类型定义更新

**文件**: `frontend/src/types/index.ts`



```typescript
// 新增
export interface TableData {
  headers: string[];
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

// 修改 ToolCallInfo
export interface ToolCallInfo {
  // ... 现有字段 ...
  tableData?: TableData[];  // 新增
}

// SSEEventType 加入 "table.data"
export type SSEEventType = ... | "table.data";
```

### 5. 前端：Store 处理 table.data 事件

**文件**: `frontend/src/stores/chatStore.ts`

在 `handleSSEEvent` switch 中 `tool.result` case 之后新增：



```typescript
case "table.data": {
  if (last && last.role === "assistant") {
    const execId = data.execution_id as string;
    const tables = data.tables as TableData[];
    last.toolCalls = (last.toolCalls ?? []).map((tc) =>
      tc.execution_id === execId ? { ...tc, tableData: tables } : tc
    );
    msgs[lastIdx] = last;
  }
  return { messages: msgs };
}
```

### 6. 前端：创建 DataTable 组件

**文件**: `frontend/src/components/chat/DataTable.tsx`

功能：

- 分页显示（每页 10 行），带 "上一页/下一页" 按钮
- 显示 "共 N 条记录" 元信息
- "导出 CSV" 按钮（Blob 下载）
- 沿用现有设计 token：`bg-primary/10` 表头、交替行色、`text-xs` 字号

### 7. 前端：MessageBubble 使用 DataTable

**文件**: `frontend/src/components/chat/MessageBubble.tsx`

修改工具结果渲染逻辑：



```tsx
{tc.tableData && tc.tableData.length > 0 ? (
  <div className="space-y-3">
    {/* 展示表格前的文本摘要 */}
    {tc.result && (() => {
      const textBefore = tc.result.split("[DATA_TABLE]")[0].trim();
      return textBefore ? (
        <pre className="text-xs text-text-secondary whitespace-pre-wrap">{textBefore}</pre>
      ) : null;
    })()}
    {/* 全量表格 */}
    {tc.tableData.map((table, idx) => (
      <DataTable key={idx} table={table} tableIndex={idx} />
    ))}
  </div>
) : (
  tc.result && renderToolResult(tc.result)  // 向后兼容
)}
```

- 有 `tableData` → 使用 DataTable 组件（结构化数据，分页）
- 无 `tableData` → 使用现有 `renderToolResult`（CSV 解析，向后兼容）

------

## 边界情况处理

| 场景                      | 处理方式                                   |
| ------------------------- | ------------------------------------------ |
| 工具结果无 `[DATA_TABLE]` | middleware 原样返回，不做任何处理          |
| 表格 ≤5 行                | content 不截断，但仍提取结构化数据发给前端 |
| 一个结果含多个表格块      | 逐一处理，`table_data` 为数组              |
| 空表（仅 header）         | 解析为 `rows=[], total_rows=0`             |
| CSV 格式错误              | 跳过该块，content 不做修改                 |
| 历史消息无 tableData      | 前端回退至 renderToolResult                |

## 验证方式

1. **后端单元测试**：在 `backend/tests/` 下新增测试，验证 middleware 截断逻辑和边界情况

2. 手动 E2E 测试

   ：启动前后端，执行查询工具（如

    

   ```
   query_root_cause_analysis
   ```

   ），确认：

   - 浏览器 SSE 收到 `tool.result`（截断）和 `table.data`（完整）两个事件
   - DataTable 组件正确分页展示全量数据
   - CSV 导出功能正常

3. **前端 TypeScript 类型检查**：`npm run build` 通过无错误