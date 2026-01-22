// 任务步骤状态
export type TodoStatus = 'pending' | 'running' | 'completed' | 'failed'

// 任务整体状态
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'waiting_input'

// Human-in-the-Loop 操作类型
export type HumanInputAction = 'approve' | 'edit' | 'reject'

// HITL 中断类型
export type InterruptType = 'param_required' | 'authorization'

// TODO 步骤
export interface TodoStep {
  id: string
  description: string
  tool_name?: string | null
  status: TodoStatus
  result?: string | null
  error?: string | null
  depends_on: string[]
  started_at?: string | null
  completed_at?: string | null
  progress: number
}

// 配置表单字段 - 支持嵌套和集合类型
export interface ConfigFormField {
  name: string
  label: string
  field_type: 'text' | 'number' | 'select' | 'switch' | 'chips' | 'textarea' | 'object' | 'array'
  required: boolean
  default?: unknown
  options?: Array<{ label: string; value: unknown }>
  placeholder?: string
  description?: string
  // 嵌套类型支持
  children?: ConfigFormField[]  // object 类型的子字段
  item_type?: ConfigFormField   // array 类型的元素定义
}

// 待配置项 - 支持两种中断场景
export interface PendingConfig {
  step_id: string
  title: string
  description?: string | null
  fields: ConfigFormField[]
  values: Record<string, unknown>
  // 中断类型
  interrupt_type: InterruptType
  // 授权场景专用
  tool_name?: string | null
  tool_args?: Record<string, unknown> | null
}

// 聊天消息
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}

// 聊天响应
export interface ChatResponse {
  thread_id: string
  message: ChatMessage
  todo_list: TodoStep[]
  pending_config?: PendingConfig | null
  task_status: TaskStatus
}

// 对话信息
export interface Conversation {
  thread_id: string
  title: string
  last_message?: string | null
  created_at: string
  updated_at: string
}

// 任务信息
export interface TaskInfo {
  task_id: string
  thread_id: string
  title: string
  status: TaskStatus
  progress: number
  todo_list: TodoStep[]
  created_at: string
  updated_at: string
}
