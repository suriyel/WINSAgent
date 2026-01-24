import { useRef, useEffect, useState, useCallback } from 'react'
import { Bot, GripVertical } from 'lucide-react'
import { cn } from '@/utils/cn'
import {
  ConversationList,
  ChatMessage,
  ChatInput,
  TodoList,
  TaskPanel,
  InlineHumanInput,
} from '@/components'
import { useChat } from '@/hooks/useChat'
import { useChatStore } from '@/stores/chatStore'

const DEFAULT_SIDEBAR_WIDTH = 288
const MIN_SIDEBAR_WIDTH = 200
const MAX_SIDEBAR_WIDTH = 500

export function Workstation() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const resizeHandleRef = useRef<HTMLDivElement>(null)

  // 侧边栏宽度状态（持久化到 localStorage）
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('sidebarWidth')
    return saved ? Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, parseInt(saved, 10))) : DEFAULT_SIDEBAR_WIDTH
  })
  const [isResizing, setIsResizing] = useState(false)

  const {
    threadId,
    messages,
    todoList,
    taskStatus,
    pendingConfig,
    inputValue,
    isLoading,
    setInputValue,
    sendMessage,
    submitConfig,
    approveConfig,
    rejectConfig,
    newConversation,
    loadConversation,
    fetchConversations,
    deleteConversation,
  } = useChat()

  const { conversations } = useChatStore()

  // 保存侧边栏宽度到 localStorage
  useEffect(() => {
    localStorage.setItem('sidebarWidth', sidebarWidth.toString())
  }, [sidebarWidth])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 获取对话列表
  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  // 调整侧边栏宽度的处理函数
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)

    const startX = e.clientX
    const startWidth = sidebarWidth

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX
      const newWidth = Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, startWidth + deltaX))
      setSidebarWidth(newWidth)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [sidebarWidth])

  // 模拟任务数据
  const mockTasks = todoList.length > 0
    ? [
        {
          task_id: '1',
          thread_id: threadId || '',
          title: messages[0]?.content.slice(0, 30) || 'New Task',
          status: taskStatus,
          progress: Math.round(
            (todoList.filter((s) => s.status === 'completed').length /
              todoList.length) *
              100
          ),
          todo_list: todoList,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]
    : []

  return (
    <div className="h-screen flex bg-background">
      {/* 左侧边栏 - 对话历史 */}
      <aside
        className="bg-gradient-to-b from-primary-50 to-secondary-50 border-r border-gray-100 flex flex-col"
        style={{ width: `${sidebarWidth}px`, minWidth: `${MIN_SIDEBAR_WIDTH}px`, maxWidth: `${MAX_SIDEBAR_WIDTH}px` }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-gray-100/50">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-400 to-secondary-400 flex items-center justify-center">
            <Bot className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-text-primary">Neo-Swiss</h1>
            <p className="text-xs text-text-muted">AI Agent</p>
          </div>
        </div>

        {/* 对话列表 */}
        <div className="flex-1 overflow-hidden">
          <ConversationList
            conversations={conversations}
            activeThreadId={threadId}
            onSelect={loadConversation}
            onNew={newConversation}
            onDelete={deleteConversation}
          />
        </div>
      </aside>

      {/* 调整宽度的手柄 */}
      <div
        ref={resizeHandleRef}
        onMouseDown={handleMouseDown}
        className={cn(
          'w-1 cursor-col-resize hover:bg-primary-300 transition-colors',
          isResizing && 'bg-primary-400'
        )}
      />

      {/* 中间 - 聊天区域 */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* 头部 */}
        <header className="h-14 px-6 flex items-center border-b border-gray-100 bg-white">
          <h2 className="font-semibold text-text-primary">AI Agent</h2>
        </header>

        {/* 消息区域 */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-100 to-secondary-100 flex items-center justify-center mb-4">
                <Bot className="w-8 h-8 text-primary-400" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary mb-2">
                Hello! I'm your AI Agent
              </h3>
              <p className="text-text-muted max-w-md">
                Tell me what you need, and I'll help you break it down into
                actionable steps and execute them.
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg, idx) => (
                <div key={idx}>
                  <ChatMessage message={msg} />
                  {/* 在 AI 消息后显示 TODO 列表 */}
                  {msg.role === 'assistant' &&
                    idx === messages.length - 1 &&
                    todoList.length > 0 && (
                      <div className="mt-4 ml-11">
                        <TodoList steps={todoList} />
                      </div>
                    )}
                </div>
              ))}
              {/* Human-in-the-Loop 内嵌输入组件 */}
              {pendingConfig && (
                <div className="mt-4">
                  <InlineHumanInput
                    config={pendingConfig}
                    onApprove={approveConfig}
                    onSubmit={submitConfig}
                    onReject={rejectConfig}
                  />
                </div>
              )}
              {isLoading && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-400 to-secondary-400 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <div className="bg-white shadow-soft rounded-2xl rounded-tl-md px-4 py-3">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" />
                      <span
                        className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                        style={{ animationDelay: '0.1s' }}
                      />
                      <span
                        className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                        style={{ animationDelay: '0.2s' }}
                      />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* 输入区域 */}
        <div className="p-4 border-t border-gray-100 bg-gray-50">
          <ChatInput
            value={inputValue}
            onChange={setInputValue}
            onSend={sendMessage}
            disabled={isLoading}
            placeholder="Type a message..."
          />
        </div>
      </main>

      {/* 右侧边栏 - 任务进度 */}
      <aside className="w-80 bg-white border-l border-gray-100">
        <TaskPanel tasks={mockTasks} />
      </aside>
    </div>
  )
}
