import { Bot, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/utils/cn'
import type { ChatMessage as ChatMessageType } from '@/types'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 animate-fade-in',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* 头像 */}
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
          isUser
            ? 'bg-primary-100'
            : 'bg-gradient-to-br from-primary-400 to-secondary-400'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-primary-600" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* 消息内容 */}
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3',
          isUser
            ? 'bg-primary-400 text-white rounded-tr-md'
            : 'bg-white shadow-soft rounded-tl-md'
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className={cn(
            'prose prose-sm max-w-none',
            'prose-p:m-0 prose-p:my-2',
            'prose-h1:m-0 prose-h1:text-lg prose-h1:font-bold prose-h1:my-2',
            'prose-h2:m-0 prose-h2:text-base prose-h2:font-bold prose-h2:my-2',
            'prose-h3:m-0 prose-h3:text-sm prose-h3:font-bold prose-h3:my-1',
            'prose-ul:m-0 prose-ul:my-2 prose-ul:pl-4',
            'prose-ol:m-0 prose-ol:my-2 prose-ol:pl-4',
            'prose-li:m-0 prose-li:my-1',
            'prose-code:text-primary-600 prose-code:bg-gray-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded',
            'prose-pre:m-0 prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:p-3 prose-pre:rounded',
            'prose-pre code:text-white prose-pre code:bg-transparent prose-pre code:p-0',
            'prose-blockquote:m-0 prose-blockquote:my-2 prose-blockquote:border-l-4 prose-blockquote:border-gray-300 prose-blockquote:pl-3 prose-blockquote:italic prose-blockquote:text-gray-600',
            'prose-a:text-primary-600 prose-a:underline hover:prose-a:text-primary-700',
            'prose-strong:font-bold',
            'prose-em:italic'
          )}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ inline, ...props }: any) {
                  return inline ? (
                    <code {...props} className="bg-gray-100 text-primary-600 px-1.5 py-0.5 rounded text-sm" />
                  ) : (
                    <code {...props} className="block bg-gray-900 text-gray-100 p-3 rounded my-2 overflow-x-auto" />
                  )
                },
                table({ children }: any) {
                  return (
                    <table className="my-2 border-collapse border border-gray-300 w-full">
                      {children}
                    </table>
                  )
                },
                th({ children }: any) {
                  return <th className="border border-gray-300 px-3 py-2 bg-gray-100 font-bold">{children}</th>
                },
                td({ children }: any) {
                  return <td className="border border-gray-300 px-3 py-2">{children}</td>
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
