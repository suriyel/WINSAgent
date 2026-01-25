import { useRef, useEffect } from 'react'
import { Send, Paperclip } from 'lucide-react'
import { cn } from '@/utils/cn'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = 'Type a message...',
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // 自动调整高度
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
    }
  }, [value])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) {
        onSend()
      }
    }
  }

  return (
    <div className="flex items-end gap-3 p-4 bg-white rounded-2xl shadow-soft">
      {/* 附件按钮 */}
      <button
        className="p-2 rounded-xl hover:bg-gray-100 transition-colors text-text-muted"
        disabled={disabled}
      >
        <Paperclip className="w-5 h-5" />
      </button>

      {/* 输入框 */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        className={cn(
          'flex-1 resize-none bg-transparent outline-none',
          'placeholder:text-text-muted text-text-primary',
          'disabled:opacity-50'
        )}
      />

      {/* 发送按钮 */}
      <button
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className={cn(
          'p-2.5 rounded-xl transition-all duration-200',
          value.trim() && !disabled
            ? 'bg-primary-400 text-white hover:bg-primary-500'
            : 'bg-gray-100 text-text-muted cursor-not-allowed'
        )}
      >
        <Send className="w-5 h-5" />
      </button>
    </div>
  )
}
