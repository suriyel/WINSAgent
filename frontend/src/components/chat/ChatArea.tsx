import { useChatStore } from "../../stores/chatStore";
import MessageList from "./MessageList";
import ChatInputBar from "./ChatInputBar";

export default function ChatArea() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const pendingTemplate = useChatStore((s) => s.pendingTemplate);

  // 话术模板等待选择时也禁用输入
  const inputDisabled = isStreaming || !!pendingTemplate;

  return (
    <div className="flex flex-col h-full">
      <MessageList messages={messages} />
      <ChatInputBar onSend={sendMessage} disabled={inputDisabled} />
    </div>
  );
}
