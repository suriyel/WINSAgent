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

  // 发送消息（使用 SSE 流式传输）
  const sendMessage = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return

    const userMessage = {
      role: 'user' as const,
      content: inputValue,
      timestamp: new Date().toISOString(),
    }

    const messageToSend = inputValue

    // 添加用户消息
    addMessage(userMessage)
    setInputValue('')
    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageToSend,
          thread_id: threadId,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to send message')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response stream')
      }

      let buffer = ''
      let currentThreadId = threadId
      let streamingContent = ''

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim() || !line.startsWith('data: ')) continue

          const data = line.slice(6)
          if (data === '[DONE]') continue

          try {
            const event = JSON.parse(data)

            // 保存 thread_id
            if (event.thread_id && !currentThreadId) {
              currentThreadId = event.thread_id
              setThreadId(currentThreadId)
            }

            switch (event.type) {
              case 'update':
                // 更新消息内容
                if (event.data?.content) {
                  streamingContent = event.data.content
                }
                // 更新 todo_list
                if (event.data?.todo_list) {
                  setTodoList(event.data.todo_list)
                }
                // 更新状态
                if (event.data?.status) {
                  setTaskStatus(event.data.status)
                }
                break

              case 'interrupt':
                // 处理中断
                if (event.data?.pending_config) {
                  setPendingConfig(event.data.pending_config)
                  setTaskStatus('waiting_input')
                }
                break

              case 'done':
                // 完成，添加助手消息
                if (streamingContent) {
                  addMessage({
                    role: 'assistant',
                    content: streamingContent,
                    timestamp: new Date().toISOString(),
                  })
                }
                break

              case 'error':
                console.error('Stream error:', event.error)
                addMessage({
                  role: 'assistant',
                  content: `Error: ${event.error}`,
                  timestamp: new Date().toISOString(),
                })
                break
            }
          } catch (parseError) {
            console.error('Failed to parse SSE event:', parseError)
          }
        }
      }
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
        const response = await fetch(`${API_BASE}/chat/resume/${threadId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
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
