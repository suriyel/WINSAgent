import { MessageSquare, Plus, Trash2 } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { Conversation } from '@/types'

interface ConversationListProps {
  conversations: Conversation[]
  activeThreadId: string | null
  onSelect: (threadId: string) => void
  onNew: () => void
  onDelete?: (threadId: string) => void
}

export function ConversationList({
  conversations,
  activeThreadId,
  onSelect,
  onNew,
  onDelete,
}: ConversationListProps) {
  return (
    <div className="flex flex-col h-full">
      {/* 标题 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h2 className="font-semibold text-text-primary">Conversations</h2>
        <button
          onClick={onNew}
          className="p-1.5 rounded-lg hover:bg-white/50 transition-colors"
        >
          <Plus className="w-5 h-5 text-text-secondary" />
        </button>
      </div>

      {/* 对话列表 */}
      <div className="flex-1 overflow-y-auto scrollbar-thin py-2">
        {conversations.length === 0 ? (
          <div className="px-4 py-8 text-center text-text-muted text-sm">
            No conversations yet
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.thread_id}
              className={cn(
                'px-4 py-3 flex items-start gap-3 transition-colors',
                activeThreadId === conv.thread_id
                  ? 'bg-white/80'
                  : 'hover:bg-white/50'
              )}
            >
              <button
                onClick={() => onSelect(conv.thread_id)}
                className="flex-1 flex items-start gap-3 text-left"
              >
                <MessageSquare
                  className={cn(
                    'w-5 h-5 mt-0.5 flex-shrink-0',
                    activeThreadId === conv.thread_id
                      ? 'text-primary-400'
                      : 'text-text-muted'
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      'font-medium truncate',
                      activeThreadId === conv.thread_id
                        ? 'text-primary-600'
                        : 'text-text-primary'
                    )}
                  >
                    {conv.title}
                  </p>
                  {conv.last_message && (
                    <p className="text-sm text-text-muted truncate mt-0.5" title={conv.last_message}>
                      {conv.last_message.length > 40
                        ? `${conv.last_message.slice(0, 40)}...`
                        : conv.last_message}
                    </p>
                  )}
                </div>
              </button>
              {onDelete && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(conv.thread_id)
                  }}
                  className="p-1 rounded hover:bg-red-100 text-text-muted hover:text-red-500 transition-colors flex-shrink-0"
                  title="Delete conversation"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
