import { useChatStore } from "../../stores/chatStore";
import DynamicForm from "./DynamicForm";
import { useState } from "react";

export default function HITLConfigModal() {
  const pendingHITL = useChatStore((s) => s.pendingHITL);
  const submitHITL = useChatStore((s) => s.submitHITL);
  const [editedParams, setEditedParams] = useState<Record<string, unknown>>({});
  const [isEditing, setIsEditing] = useState(false);

  if (!pendingHITL) return null;

  const handleApprove = () => {
    submitHITL("approve");
  };

  const handleEdit = () => {
    if (!isEditing) {
      setEditedParams({ ...pendingHITL.params });
      setIsEditing(true);
      return;
    }
    submitHITL("edit", pendingHITL.tool_name, editedParams);
    setIsEditing(false);
  };

  const handleReject = () => {
    submitHITL("reject");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative bg-card rounded-2xl shadow-xl border border-gray-100 w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-base font-semibold text-text-primary">操作确认</h3>
          <p className="text-sm text-text-secondary mt-1">
            {pendingHITL.description || `即将执行 ${pendingHITL.tool_name}，请确认参数`}
          </p>
        </div>

        {/* Body: tool params */}
        <div className="px-6 py-4 max-h-80 overflow-y-auto">
          <div className="text-xs font-medium text-text-weak mb-3 uppercase tracking-wider">
            Tool: {pendingHITL.tool_name}
          </div>
          {isEditing ? (
            <DynamicForm
              params={editedParams}
              schema={pendingHITL.schema}
              onChange={setEditedParams}
            />
          ) : (
            <div className="space-y-2">
              {Object.entries(pendingHITL.params).map(([key, value]) => (
                <div key={key} className="flex gap-2 text-sm">
                  <span className="text-text-secondary font-medium min-w-[120px]">{key}:</span>
                  <span className="text-text-primary">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-3">
          <button className="btn-danger" onClick={handleReject}>
            拒绝
          </button>
          <button className="btn-ghost" onClick={handleEdit}>
            {isEditing ? "确认修改" : "编辑参数"}
          </button>
          {!isEditing && (
            <button className="btn-primary" onClick={handleApprove}>
              批准执行
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
