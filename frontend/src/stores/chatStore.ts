import { create } from 'zustand'
import type { ChatMessage, TodoStep, PendingConfig, TaskStatus, Conversation } from '@/types'

interface ChatState {
  // 当前会话
  threadId: string | null
  messages: ChatMessage[]
  todoList: TodoStep[]
  taskStatus: TaskStatus
  pendingConfig: PendingConfig | null

  // 对话列表
  conversations: Conversation[]

  // 输入状态
  inputValue: string
  isLoading: boolean

  // 操作
  setThreadId: (id: string | null) => void
  addMessage: (message: ChatMessage) => void
  setMessages: (messages: ChatMessage[]) => void
  setTodoList: (list: TodoStep[]) => void
  updateTodoStep: (stepId: string, updates: Partial<TodoStep>) => void
  setTaskStatus: (status: TaskStatus) => void
  setPendingConfig: (config: PendingConfig | null) => void
  setInputValue: (value: string) => void
  setIsLoading: (loading: boolean) => void
  setConversations: (conversations: Conversation[]) => void
  addConversation: (conversation: Conversation) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  // 初始状态
  threadId: null,
  messages: [],
  todoList: [],
  taskStatus: 'pending',
  pendingConfig: null,
  conversations: [],
  inputValue: '',
  isLoading: false,

  // 操作实现
  setThreadId: (id) => set({ threadId: id }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  setMessages: (messages) => set({ messages }),

  setTodoList: (list) => set({ todoList: list }),

  updateTodoStep: (stepId, updates) =>
    set((state) => ({
      todoList: state.todoList.map((step) =>
        step.id === stepId ? { ...step, ...updates } : step
      ),
    })),

  setTaskStatus: (status) => set({ taskStatus: status }),

  setPendingConfig: (config) => set({ pendingConfig: config }),

  setInputValue: (value) => set({ inputValue: value }),

  setIsLoading: (loading) => set({ isLoading: loading }),

  setConversations: (conversations) => set({ conversations }),

  addConversation: (conversation) =>
    set((state) => ({ conversations: [conversation, ...state.conversations] })),

  reset: () =>
    set({
      threadId: null,
      messages: [],
      todoList: [],
      taskStatus: 'pending',
      pendingConfig: null,
      inputValue: '',
      isLoading: false,
    }),
}))
