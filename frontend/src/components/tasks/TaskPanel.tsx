import { useChatStore } from "../../stores/chatStore";
import TaskCard from "./TaskCard";

export default function TaskPanel() {
  const todoSteps = useChatStore((s) => s.todoSteps);

  const taskEntries = Object.entries(todoSteps);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-text-primary">任务进度</h2>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto py-2 space-y-2 px-3">
        {taskEntries.length === 0 ? (
          <p className="text-xs text-text-weak px-1 py-2">暂无进行中的任务</p>
        ) : (
          taskEntries.map(([taskId, steps]) => (
            <TaskCard key={taskId} taskId={taskId} steps={steps} />
          ))
        )}
      </div>
    </div>
  );
}
