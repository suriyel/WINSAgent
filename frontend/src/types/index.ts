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
  | "error"
  | "done";

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
