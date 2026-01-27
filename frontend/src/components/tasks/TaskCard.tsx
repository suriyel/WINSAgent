import type { TodoStep } from "../../types";

interface Props {
  taskId: string;
  steps: TodoStep[];
}

export default function TaskCard({ taskId, steps }: Props) {
  const completedCount = steps.filter((s) => s.status === "completed").length;
  const inProgressCount = steps.filter((s) => s.status === "in_progress").length;
  const progress = steps.length > 0 ? (completedCount / steps.length) * 100 : 0;

  // Determine overall status color
  const statusColor =
    inProgressCount > 0
      ? "bg-secondary"    // running
      : completedCount === steps.length && steps.length > 0
      ? "bg-success"      // all done
      : "bg-gray-300";    // pending

  return (
    <div className="card p-3 flex gap-3">
      {/* Status bar */}
      <div className={`w-1 rounded-full ${statusColor} shrink-0`} />

      <div className="flex-1 min-w-0">
        {/* Task ID */}
        <div className="text-xs font-medium text-text-primary truncate">
          任务 {taskId.slice(0, 8)}
        </div>

        {/* Progress bar */}
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-success rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-xs text-text-weak shrink-0">
            {completedCount}/{steps.length}
          </span>
        </div>

        {/* Step summary */}
        <div className="mt-2 space-y-0.5">
          {steps.slice(0, 4).map((step, i) => (
            <div key={i} className="flex items-center gap-1.5 text-xs">
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  step.status === "completed"
                    ? "bg-success"
                    : step.status === "in_progress"
                    ? "bg-secondary"
                    : "bg-gray-300"
                }`}
              />
              <span
                className={`truncate ${
                  step.status === "completed"
                    ? "text-text-weak line-through"
                    : step.status === "in_progress"
                    ? "text-text-primary font-medium"
                    : "text-text-weak"
                }`}
              >
                {step.content}
              </span>
            </div>
          ))}
          {steps.length > 4 && (
            <span className="text-xs text-text-weak">...还有 {steps.length - 4} 个步骤</span>
          )}
        </div>
      </div>
    </div>
  );
}
