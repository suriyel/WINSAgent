/** Shared TypeScript type definitions */

// --- Enums ---

export type TodoStatus = "pending" | "in_progress" | "completed";

export type TaskStatus = "pending" | "in_progress" | "completed" | "failed";

export type HITLAction = "approve" | "edit" | "reject";

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
  suggestions?: SuggestionGroup;  // 建议回复选项
  isStreaming?: boolean;
  timestamp: number;
}

export interface ToolCallInfo {
  tool_name: string;
  params: Record<string, unknown>;
  execution_id: string;
  result?: string;
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
  | "hitl.pending"
  | "todo.state"
  | "message"
  | "suggestions"
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
