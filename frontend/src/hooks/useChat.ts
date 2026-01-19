import { useCallback } from 'react'
import { useChatStore } from '@/stores/chatStore'
import type { ChatResponse } from '@/types'

const API_BASE = '/api/v1'

export function useChat() {
  const {
    threadId,
    messages,
    todoList,
    taskStatus,
    pendingConfig,
    inputValue,
    isLoading,
    setThreadId,
    addMessage,
    setMessages,
    setTodoList,
    setTaskStatus,
    setPendingConfig,
    setInputValue,
    setIsLoading,
    reset,
  } = useChatStore()

  // 发送消息
  const sendMessage = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage = {
      role: 'user' as const,
      content: inputValue,
      timestamp: new Date().toISOString(),
    }

    // 添加用户消息
    addMessage(userMessage)
    setInputValue('')
    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: inputValue,
          thread_id: threadId,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to send message')
      }

      const data: ChatResponse = await response.json()

      // 更新状态
      setThreadId(data.thread_id)
      addMessage(data.message)
      setTodoList(data.todo_list)
      setTaskStatus(data.task_status)
      setPendingConfig(data.pending_config || null)
    } catch (error) {
      console.error('Send message error:', error)
      addMessage({
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        timestamp: new Date().toISOString(),
      })
    } finally {
      setIsLoading(false)
    }
  }, [
    inputValue,
    isLoading,
    threadId,
    addMessage,
    setInputValue,
    setIsLoading,
    setThreadId,
    setTodoList,
    setTaskStatus,
    setPendingConfig,
  ])

  // 提交配置
  const submitConfig = useCallback(
    async (values: Record<string, unknown>) => {
      if (!threadId) return

      setIsLoading(true)
      setPendingConfig(null)

      try {
        const response = await fetch(`${API_BASE}/chat/send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: '',
            thread_id: threadId,
            config_response: values,
          }),
        })

        if (!response.ok) {
          throw new Error('Failed to submit config')
        }

        const data: ChatResponse = await response.json()

        addMessage(data.message)
        setTodoList(data.todo_list)
        setTaskStatus(data.task_status)
        setPendingConfig(data.pending_config || null)
      } catch (error) {
        console.error('Submit config error:', error)
      } finally {
        setIsLoading(false)
      }
    },
    [threadId, addMessage, setTodoList, setTaskStatus, setPendingConfig, setIsLoading]
  )

  // 新建对话
  const newConversation = useCallback(() => {
    reset()
  }, [reset])

  // 加载对话
  const loadConversation = useCallback(
    async (id: string) => {
      setIsLoading(true)
      try {
        const response = await fetch(`${API_BASE}/chat/state/${id}`)
        if (response.ok) {
          const data: ChatResponse = await response.json()
          setThreadId(data.thread_id)
          // Note: messages 需要从其他地方获取
          setTodoList(data.todo_list)
          setTaskStatus(data.task_status)
          setPendingConfig(data.pending_config || null)
        }
      } catch (error) {
        console.error('Load conversation error:', error)
      } finally {
        setIsLoading(false)
      }
    },
    [setThreadId, setTodoList, setTaskStatus, setPendingConfig, setIsLoading]
  )

  return {
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
    newConversation,
    loadConversation,
  }
}
