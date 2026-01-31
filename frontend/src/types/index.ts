/** Shared TypeScript type definitions */

// --- Enums ---

export type TodoStatus = "pending" | "in_progress" | "completed";

export type TaskStatus = "pending" | "in_progress" | "completed" | "failed";

export type HITLAction = "approve" | "edit" | "reject";

export type ParamsAction = "submit" | "cancel";

// --- Data models ---

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls?: ToolCallInfo[];
  todoSteps?: TodoStep[];
  hitlPending?: HITLPending;
  paramsPending?: ParamsPending;  // 缺省参数待填写
  suggestions?: SuggestionGroup;  // 建议回复选项
  isStreaming?: boolean;
  timestamp: number;
}

/** 从后端 DataTableMiddleware 提取的结构化表格数据 */
export interface TableData {
  headers: string[];
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

export interface ToolCallInfo {
  tool_name: string;
  params: Record<string, unknown>;
  execution_id: string;
  result?: string;
  tableData?: TableData[];
  status?: "pending" | "running" | "success" | "failed";
}

export interface TodoStep {
  content: string;
  status: TodoStatus;
}

export interface Task {
  id: string;
  description: string;
  status: TaskStatus;
  steps: TodoStep[];
}

export interface HITLPending {
  execution_id: string;
  tool_name: string;
  params: Record<string, unknown>;
  schema: Record<string, unknown>;
  description?: string;
}

/** 参数 Schema 定义 - 兼容 JSON Schema 和 Airflow Params */
export interface ParamSchema {
  // 基础信息
  type: string | string[];
  title?: string;
  description?: string;

  // 默认值
  default?: unknown;

  // 约束 - 字符串
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: "date" | "date-time" | "time" | "email" | "uri" | "multiline" | string;

  // 约束 - 数值
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  multipleOf?: number;

  // 约束 - 枚举/选项
  enum?: unknown[];
  examples?: unknown[];
  values_display?: Record<string, string>;

  // 约束 - 数组
  items?: Record<string, unknown>;
  minItems?: number;
  maxItems?: number;
  uniqueItems?: boolean;

  // UI 相关
  section?: string;
  const?: unknown;
  placeholder?: string;
}

/** 缺省参数待填写 - 由 MissingParamsMiddleware 触发 */
export interface ParamsPending {
  execution_id: string;
  tool_name: string;
  tool_call_id: string;
  description?: string;
  current_params: Record<string, unknown>;
  missing_params: string[];
  params_schema: Record<string, ParamSchema>;
}

/** 建议选项 - 用于快速回复 */
export interface Suggestion {
  id: string;
  text: string;           // 显示文本
  value?: string;         // 发送的值（可选，默认使用 text）
}

/** 建议选项组 - 支持单选/多选 */
export interface SuggestionGroup {
  suggestions: Suggestion[];
  multiSelect?: boolean;  // 是否多选，默认单选
  prompt?: string;        // 可选的提示文本
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters_schema: Record<string, unknown>;
  category: string;
  requires_hitl: boolean;
}

// --- SSE Events ---

export type SSEEventType =
  | "session"
  | "thinking"
  | "tool.call"
  | "tool.result"
  | "table.data"
  | "hitl.pending"
  | "params.pending"
  | "todo.state"
  | "message"
  | "suggestions"
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
