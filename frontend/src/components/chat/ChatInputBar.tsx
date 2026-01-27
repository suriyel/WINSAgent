import { useState, type KeyboardEvent } from "react";

interface Props {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export default function ChatInputBar({ onSend, disabled }: Props) {
  const [input, setInput] = useState("");

  const handleSend = () => {
    const text = input.trim();
    if (!text || disabled) return;
    onSend(text);
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-100 bg-card px-6 py-4">
      <div className="flex items-end gap-3 max-w-3xl mx-auto">
        <textarea
          className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm
                     text-text-primary placeholder:text-text-weak
                     focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary
                     transition-shadow min-h-[44px] max-h-32"
          rows={1}
          placeholder="输入消息..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          className="btn-primary shrink-0 h-[44px] px-5"
          onClick={handleSend}
          disabled={disabled || !input.trim()}
        >
          {disabled ? "处理中..." : "发送"}
        </button>
      </div>
    </div>
  );
}
