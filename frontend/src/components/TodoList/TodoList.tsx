import { useState } from 'react'
import { ChevronDown, ChevronUp, CheckCircle2, Circle, Loader2, XCircle, SkipForward } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/cn'
import type { TodoStep, TodoStatus } from '@/types'

interface TodoListProps {
  steps: TodoStep[]
  className?: string
}

const statusConfig: Record<
  TodoStatus,
  { icon: React.ReactNode; color: string; bg: string }
> = {
  pending: {
    icon: <Circle className="w-5 h-5" />,
    color: 'text-gray-400',
    bg: 'bg-gray-100',
  },
  running: {
    icon: <Loader2 className="w-5 h-5 animate-spin" />,
    color: 'text-secondary-400',
    bg: 'bg-secondary-50',
  },
  completed: {
    icon: <CheckCircle2 className="w-5 h-5" />,
    color: 'text-success-400',
    bg: 'bg-success-50',
  },
  failed: {
    icon: <XCircle className="w-5 h-5" />,
    color: 'text-error-400',
    bg: 'bg-error-50',
  },
  skipped: {
    icon: <SkipForward className="w-5 h-5" />,
    color: 'text-amber-400',
    bg: 'bg-amber-50',
  },
}

export function TodoList({ steps, className }: TodoListProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  // completed + skipped = finished
  const completedCount = steps.filter((s) => s.status === 'completed').length
  const skippedCount = steps.filter((s) => s.status === 'skipped').length
  const finishedCount = completedCount + skippedCount
  const totalCount = steps.length

  return (
    <div className={cn('bg-gray-50 rounded-2xl overflow-hidden', className)}>
      {/* 头部 - 可折叠 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="font-medium text-text-primary">TODO task list</span>
          <span className="text-sm text-text-muted">
            {finishedCount}/{totalCount}
            {skippedCount > 0 && <span className="text-amber-500 ml-1">({skippedCount} skipped)</span>}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-text-muted" />
        ) : (
          <ChevronDown className="w-5 h-5 text-text-muted" />
        )}
      </button>

      {/* 步骤列表 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 space-y-2">
              {steps.map((step, index) => {
                const config = statusConfig[step.status]
                return (
                  <div
                    key={step.id}
                    className={cn(
                      'flex items-start gap-3 p-3 rounded-xl transition-colors',
                      config.bg
                    )}
                  >
                    {/* 状态图标 */}
                    <div className={cn('flex-shrink-0 mt-0.5', config.color)}>
                      {config.icon}
                    </div>

                    {/* 内容 */}
                    <div className="flex-1 min-w-0">
                      <p className="text-text-primary">{step.description}</p>
                      {step.tool_name && (
                        <p className="text-sm text-text-muted mt-1">
                          Tool: {step.tool_name}
                        </p>
                      )}
                      {step.error && (
                        <p className="text-sm text-error-500 mt-1">
                          {step.error}
                        </p>
                      )}
                    </div>

                    {/* 进度 */}
                    {step.status === 'running' && step.progress > 0 && (
                      <span className="text-sm text-secondary-500 font-medium">
                        {step.progress}%
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
