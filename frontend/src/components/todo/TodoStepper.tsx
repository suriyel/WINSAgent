import type { TodoStep } from "../../types";
import StepItem from "./StepItem";
import { useState } from "react";

interface Props {
  steps: TodoStep[];
}

export default function TodoStepper({ steps }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  const completedCount = steps.filter((s) => s.status === "completed").length;

  return (
    <div className="rounded-lg border border-gray-100 bg-surface overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-50 transition-colors"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-2">
          <svg
            className={`w-4 h-4 text-text-weak transition-transform ${collapsed ? "" : "rotate-90"}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-xs font-medium text-text-primary">任务步骤</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Progress bar */}
          <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-success rounded-full transition-all duration-300"
              style={{ width: `${steps.length > 0 ? (completedCount / steps.length) * 100 : 0}%` }}
            />
          </div>
          <span className="text-xs text-text-weak">
            {completedCount}/{steps.length}
          </span>
        </div>
      </button>

      {/* Steps list */}
      {!collapsed && (
        <div className="px-3 pb-3 space-y-1">
          {steps.map((step, i) => (
            <StepItem key={i} step={step} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
