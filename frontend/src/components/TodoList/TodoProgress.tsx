import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { TodoStep, TodoStatus } from '@/types'

interface TodoProgressProps {
  steps: TodoStep[]
  currentStep: number
}

const statusConfig: Record<
  TodoStatus,
  { icon: React.ReactNode; color: string; lineColor: string }
> = {
  pending: {
    icon: <Circle className="w-6 h-6" />,
    color: 'text-gray-300',
    lineColor: 'bg-gray-200',
  },
  running: {
    icon: <Loader2 className="w-6 h-6 animate-spin" />,
    color: 'text-secondary-400',
    lineColor: 'bg-secondary-200',
  },
  completed: {
    icon: <CheckCircle2 className="w-6 h-6" />,
    color: 'text-success-400',
    lineColor: 'bg-success-400',
  },
  failed: {
    icon: <XCircle className="w-6 h-6" />,
    color: 'text-error-400',
    lineColor: 'bg-error-400',
  },
}

export function TodoProgress({ steps, currentStep }: TodoProgressProps) {
  const completedCount = steps.filter((s) => s.status === 'completed').length
  const totalCount = steps.length

  return (
    <div className="bg-white rounded-2xl shadow-soft p-4">
      {/* 进度标题 */}
      <div className="flex items-center justify-between mb-4">
        <span className="font-medium text-text-primary">Step {currentStep + 1}/{totalCount}</span>
        <span className="text-sm text-text-muted">
          {Math.round((completedCount / totalCount) * 100)}%
        </span>
      </div>

      {/* 进度条 */}
      <div className="h-1 bg-gray-100 rounded-full mb-6 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-primary-400 to-secondary-400 rounded-full transition-all duration-500"
          style={{ width: `${(completedCount / totalCount) * 100}%` }}
        />
      </div>

      {/* 时间线 */}
      <div className="space-y-4">
        {steps.map((step, index) => {
          const config = statusConfig[step.status]
          const isLast = index === steps.length - 1

          return (
            <div key={step.id} className="flex gap-3">
              {/* 图标和连接线 */}
              <div className="flex flex-col items-center">
                <div className={cn('flex-shrink-0', config.color)}>
                  {config.icon}
                </div>
                {!isLast && (
                  <div
                    className={cn(
                      'w-0.5 flex-1 my-1 min-h-[20px]',
                      config.lineColor
                    )}
                  />
                )}
              </div>

              {/* 内容 */}
              <div className="flex-1 pb-4">
                <p
                  className={cn(
                    'font-medium',
                    step.status === 'completed'
                      ? 'text-text-primary'
                      : step.status === 'running'
                      ? 'text-secondary-600'
                      : step.status === 'failed'
                      ? 'text-error-600'
                      : 'text-text-muted'
                  )}
                >
                  {step.description}
                </p>
                {step.result && (
                  <p className="text-sm text-text-muted mt-1">{step.result}</p>
                )}
                {step.error && (
                  <p className="text-sm text-error-500 mt-1">{step.error}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
