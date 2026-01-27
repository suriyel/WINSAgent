import type { Conversation } from "../../types";

interface Props {
  conversation: Conversation;
  isActive: boolean;
  onClick: () => void;
}

export default function ConversationItem({ conversation, isActive, onClick }: Props) {
  return (
    <button
      className={`w-full text-left px-4 py-2.5 transition-colors ${
        isActive
          ? "bg-primary/10 border-r-2 border-primary"
          : "hover:bg-gray-50"
      }`}
      onClick={onClick}
    >
      <div className="text-sm font-medium text-text-primary truncate">
        {conversation.title}
      </div>
      <div className="text-xs text-text-weak mt-0.5">
        {new Date(conversation.updated_at).toLocaleDateString("zh-CN")}
      </div>
    </button>
  );
}
