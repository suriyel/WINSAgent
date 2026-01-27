import type { TodoStep } from "../../types";

interface Props {
  step: TodoStep;
  index: number;
}

const statusConfig = {
  pending: {
    icon: (
      <div className="w-5 h-5 rounded-full border-2 border-gray-300 flex items-center justify-center">
        <span className="text-[10px] text-text-weak">{/* empty */}</span>
      </div>
    ),
    textClass: "text-text-weak",
  },
  in_progress: {
    icon: (
      <div className="w-5 h-5 rounded-full border-2 border-secondary flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
      </div>
    ),
    textClass: "text-text-primary font-medium",
  },
  completed: {
    icon: (
      <div className="w-5 h-5 rounded-full bg-success flex items-center justify-center">
        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
        </svg>
      </div>
    ),
    textClass: "text-success line-through",
  },
};

export default function StepItem({ step, index }: Props) {
  const config = statusConfig[step.status] ?? statusConfig.pending;

  return (
    <div className="flex items-start gap-2 py-1">
      <div className="shrink-0 mt-0.5">{config.icon}</div>
      <div className="flex-1 min-w-0">
        <span className={`text-xs ${config.textClass}`}>
          {index + 1}. {step.content}
        </span>
      </div>
    </div>
  );
}
