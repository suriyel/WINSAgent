import { useState } from "react";
import type { ParamsPending } from "../../types";
import { useChatStore } from "../../stores/chatStore";
import DynamicForm from "./DynamicForm";

interface Props {
  paramsPending: ParamsPending;
}

export default function ParamsInlineCard({ paramsPending }: Props) {
  const submitParams = useChatStore((s) => s.submitParams);
  const [editedParams, setEditedParams] = useState<Record<string, unknown>>(
    () => ({ ...paramsPending.current_params })
  );

  const handleSubmit = () => {
    submitParams("submit", editedParams);
  };

  const handleCancel = () => {
    submitParams("cancel");
  };

  return (
    <div className="rounded-xl border-2 border-blue-200 bg-blue-50/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-blue-100/50 border-b border-blue-200">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-semibold text-blue-800">
            参数填写
          </span>
        </div>
        <p className="text-xs text-blue-700 mt-1">
          {paramsPending.description || `请补充 ${paramsPending.tool_name} 所需的参数`}
        </p>
      </div>

      {/* Body: param form */}
      <div className="px-4 py-3">
        <div className="text-xs font-medium text-text-weak mb-2 uppercase tracking-wider">
          Tool: {paramsPending.tool_name}
        </div>

        {/* Missing params hint */}
        {paramsPending.missing_params.length > 0 && (
          <div className="mb-3 text-xs text-blue-600">
            需要填写: {paramsPending.missing_params.join(", ")}
          </div>
        )}

        <DynamicForm
          params={editedParams}
          schema={paramsPending.params_schema as Record<string, unknown>}
          onChange={setEditedParams}
        />
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-blue-200 bg-blue-50/30 flex flex-wrap gap-2">
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-gray-100 text-gray-700 hover:bg-gray-200
                     transition-colors"
          onClick={handleCancel}
        >
          取消
        </button>
        <button
          className="px-3 py-1.5 text-sm font-medium rounded-lg
                     bg-blue-100 text-blue-700 hover:bg-blue-200
                     transition-colors"
          onClick={handleSubmit}
        >
          提交参数
        </button>
      </div>
    </div>
  );
}
