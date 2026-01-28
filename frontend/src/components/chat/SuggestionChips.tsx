import { useState } from "react";
import type { SuggestionGroup } from "../../types";
import { useChatStore } from "../../stores/chatStore";

interface Props {
  suggestionGroup: SuggestionGroup;
}

/**
 * SuggestionChips - 可点击的建议选项组件
 *
 * 支持单选和多选模式：
 * - 单选：点击即发送
 * - 多选：先选择，再点击"发送"按钮
 */
export default function SuggestionChips({ suggestionGroup }: Props) {
  const { suggestions, multiSelect, prompt } = suggestionGroup;
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);

  // 多选模式下的已选项
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const handleClick = (id: string, text: string, value?: string) => {
    if (isStreaming) return;

    if (multiSelect) {
      // 多选模式：切换选中状态
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    } else {
      // 单选模式：直接发送
      sendMessage(value ?? text);
    }
  };

  const handleSendMultiple = () => {
    if (selected.size === 0 || isStreaming) return;

    // 收集所有选中项的文本
    const selectedTexts = suggestions
      .filter((s) => selected.has(s.id))
      .map((s) => s.value ?? s.text);

    // 发送组合消息
    sendMessage(selectedTexts.join("、"));
    setSelected(new Set());
  };

  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {/* 可选的提示文本 */}
      {prompt && (
        <p className="text-xs text-text-secondary mb-2">{prompt}</p>
      )}

      {/* 建议选项按钮组 */}
      <div className="flex flex-wrap gap-2">
        {suggestions.map((suggestion) => {
          const isSelected = selected.has(suggestion.id);
          return (
            <button
              key={suggestion.id}
              onClick={() => handleClick(suggestion.id, suggestion.text, suggestion.value)}
              disabled={isStreaming}
              className={`
                px-3 py-1.5 text-sm rounded-lg border transition-all
                ${
                  isSelected
                    ? "bg-primary text-white border-primary"
                    : "bg-primary/5 border-primary/20 text-primary hover:bg-primary/10 hover:border-primary/40"
                }
                ${isStreaming ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                active:scale-95
              `}
            >
              {multiSelect && (
                <span className="mr-1.5">
                  {isSelected ? "✓" : "○"}
                </span>
              )}
              {suggestion.text}
            </button>
          );
        })}
      </div>

      {/* 多选模式下的发送按钮 */}
      {multiSelect && (
        <div className="flex justify-end mt-2">
          <button
            onClick={handleSendMultiple}
            disabled={selected.size === 0 || isStreaming}
            className={`
              px-4 py-1.5 text-sm rounded-lg font-medium transition-all
              ${
                selected.size > 0 && !isStreaming
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed"
              }
            `}
          >
            发送已选 ({selected.size})
          </button>
        </div>
      )}
    </div>
  );
}
