import { useState } from "react";
import type { HITLPending } from "../../types";
import { useChatStore } from "../../stores/chatStore";
import DynamicForm from "./DynamicForm";

interface Props {
  hitlPending: HITLPending;
}

export default function HITLInlineCard({ hitlPending }: Props) {
  const submitHITL = useChatStore((s) => s.submitHITL);
  const [editedParams, setEditedParams] = useState<Record<string, unknown>>({});
  const [isEditing, setIsEditing] = useState(false);

  const handleApprove = () => {
    submitHITL("approve");
  };

  const handleEdit = () => {
    if (!isEditing) {
      setEditedParams({ ...hitlPending.params });
      setIsEditing(true);
      return;
    }
    submitHITL("edit", hitlPending.tool_name, editedParams);
    setIsEditing(false);
  };

  const handleReject = () => {
    submitHITL("reject");
  };

  return (
    <div className="rounded-xl border-2 border-amber-200 bg-amber-50/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-amber-100/50 border-b border-amber-200">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
          <span className="text-sm font-semibold text-amber-800">
            操作确认
          </span>
        </div>
        <p className="text-xs text-amber-700 mt-1">
          {hitlPending.description || `即将执行 ${hitlPending.tool_name}，请确认参数`}
        </p>
      </div>

      {/* Body: tool params */}
      <div className="px-4 py-3">
        <div className="text-xs font-medium text-text-weak mb-2 uppercase tracking-wider">
          Tool: {hitlPending.tool_name}
        </div>
        {isEditing ? (
          <DynamicForm
            params={editedParams}
            schema={hitlPending.schema}
            onChange={setEditedParams}
          />
        ) : (
          <div className="space-y-1.5">
            {Object.entries(hitlPending.params).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-sm">
                <span className="text-text-secondary font-medium min-w-[100px]">
                  {key}:
                </span>
                <span className="text-text-primary break-all">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-amber-200 bg-amber-50/30 flex flex-wrap gap-2">
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-red-100 text-red-700 hover:bg-red-200
                     transition-colors"
          onClick={handleReject}
        >
          拒绝
        </button>
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-gray-100 text-gray-700 hover:bg-gray-200
                     transition-colors"
          onClick={handleEdit}
        >
          {isEditing ? "确认修改" : "编辑参数"}
        </button>
        {!isEditing && (
          <button
            className="px-3 py-1.5 text-sm font-medium rounded-lg
                       bg-green-100 text-green-700 hover:bg-green-200
                       transition-colors"
            onClick={handleApprove}
          >
            批准执行
          </button>
        )}
      </div>
    </div>
  );
}
