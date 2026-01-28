import type { Message } from "../../types";
import ThinkingIndicator from "./ThinkingIndicator";
import TodoStepper from "../todo/TodoStepper";
import HITLInlineCard from "../hitl/HITLInlineCard";
import SuggestionChips from "./SuggestionChips";

interface Props {
  message: Message;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-bold ${
          isUser
            ? "bg-gray-200 text-text-secondary"
            : "bg-gradient-to-br from-primary to-secondary text-white"
        }`}
      >
        {isUser ? "U" : "W"}
      </div>

      {/* Bubble */}
      <div className={`max-w-[70%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`card px-4 py-3 ${
            isUser ? "bg-primary/10 border-primary/20" : "bg-card"
          }`}
        >
          {/* Tool call cards */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="space-y-2 mb-3">
              {message.toolCalls.map((tc) => (
                <div
                  key={tc.execution_id}
                  className="rounded-lg border border-gray-100 p-3 bg-surface text-sm"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        tc.status === "success"
                          ? "bg-success"
                          : tc.status === "failed"
                          ? "bg-error"
                          : "bg-secondary animate-pulse"
                      }`}
                    />
                    <span className="font-medium text-text-primary">{tc.tool_name}</span>
                    <span className="text-text-weak text-xs">
                      {tc.status === "running"
                        ? "执行中..."
                        : tc.status === "success"
                        ? "已完成"
                        : tc.status === "failed"
                        ? "失败"
                        : "待执行"}
                    </span>
                  </div>
                  {tc.result && (
                    <pre className="text-xs text-text-secondary whitespace-pre-wrap mt-1">
                      {tc.result}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* HITL inline card */}
          {message.hitlPending && (
            <div className="mb-3">
              <HITLInlineCard hitlPending={message.hitlPending} />
            </div>
          )}

          {/* TODO stepper */}
          {message.todoSteps && message.todoSteps.length > 0 && (
            <div className="mb-3">
              <TodoStepper steps={message.todoSteps} />
            </div>
          )}

          {/* Message text */}
          {message.content && (
            <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
              {message.content}
            </div>
          )}

          {/* Suggestion chips - 建议选项 */}
          {message.suggestions && !message.isStreaming && (
            <SuggestionChips suggestionGroup={message.suggestions} />
          )}

          {/* Streaming indicator */}
          {message.isStreaming && !message.content && <ThinkingIndicator />}
        </div>
      </div>
    </div>
  );
}
