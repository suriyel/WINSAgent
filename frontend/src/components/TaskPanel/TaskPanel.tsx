import { Clock, CheckCircle2, XCircle, Loader2, Pause } from 'lucide-react'
import { cn } from '@/utils/cn'
import type { TaskInfo, TaskStatus } from '@/types'

interface TaskPanelProps {
  tasks: TaskInfo[]
  className?: string
}

const statusConfig: Record<
  TaskStatus,
  { icon: React.ReactNode; label: string; color: string; barColor: string }
> = {
  pending: {
    icon: <Clock className="w-4 h-4" />,
    label: 'Pending',
    color: 'text-gray-500',
    barColor: 'bg-gray-300',
  },
  running: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    label: 'Running',
    color: 'text-secondary-500',
    barColor: 'bg-secondary-400',
  },
  success: {
    icon: <CheckCircle2 className="w-4 h-4" />,
    label: 'Completed',
    color: 'text-success-500',
    barColor: 'bg-success-400',
  },
  failed: {
    icon: <XCircle className="w-4 h-4" />,
    label: 'Failed',
    color: 'text-error-500',
    barColor: 'bg-error-400',
  },
  waiting_input: {
    icon: <Pause className="w-4 h-4" />,
    label: 'Waiting',
    color: 'text-primary-500',
    barColor: 'bg-primary-400',
  },
}

export function TaskPanel({ tasks, className }: TaskPanelProps) {
  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* 标题 */}
      <div className="px-4 py-3 border-b border-gray-100">
        <h2 className="font-semibold text-text-primary">Task progress</h2>
      </div>

      {/* 任务列表 */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-3">
        {tasks.length === 0 ? (
          <div className="text-center text-text-muted text-sm py-8">
            No tasks yet
          </div>
        ) : (
          tasks.map((task) => {
            const config = statusConfig[task.status]
            return (
              <div
                key={task.task_id}
                className="bg-white rounded-xl p-4 shadow-soft"
              >
                {/* 状态条 */}
                <div
                  className={cn(
                    'h-1 rounded-full mb-3 -mt-1 -mx-1',
                    config.barColor
                  )}
                  style={{ width: `${task.progress}%` }}
                />

                {/* 任务信息 */}
                <div className="flex items-start gap-3">
                  <div className={cn('flex-shrink-0', config.color)}>
                    {config.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-text-primary truncate">
                      {task.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={cn('text-xs', config.color)}>
                        {config.label}
                      </span>
                      {task.progress > 0 && task.progress < 100 && (
                        <span className="text-xs text-text-muted">
                          {task.progress}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* 步骤预览 */}
                {task.todo_list.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <div className="flex items-center gap-1">
                      {task.todo_list.slice(0, 5).map((step) => (
                        <div
                          key={step.id}
                          className={cn(
                            'w-2 h-2 rounded-full',
                            step.status === 'completed'
                              ? 'bg-success-400'
                              : step.status === 'running'
                              ? 'bg-secondary-400'
                              : step.status === 'failed'
                              ? 'bg-error-400'
                              : step.status === 'skipped'
                              ? 'bg-amber-400'
                              : 'bg-gray-200'
                          )}
                        />
                      ))}
                      {task.todo_list.length > 5 && (
                        <span className="text-xs text-text-muted ml-1">
                          +{task.todo_list.length - 5}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
