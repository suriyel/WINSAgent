import type { Message } from "../../types";
import ThinkingIndicator from "./ThinkingIndicator";
import TodoStepper from "../todo/TodoStepper";
import HITLInlineCard from "../hitl/HITLInlineCard";
import ParamsInlineCard from "../hitl/ParamsInlineCard";
import SuggestionChips from "./SuggestionChips";

interface Props {
  message: Message;
}

/** Max number of data rows to display in a table (excluding the header). */
const TABLE_MAX_ROWS = 10;

/**
 * Parse a tool result string and render [DATA_TABLE] blocks as HTML tables.
 * Non-table text is rendered as plain preformatted text.
 */
function renderToolResult(result: string) {
  const parts: { type: "text" | "table"; content: string }[] = [];
  let remaining = result;

  while (remaining.length > 0) {
    const startTag = "[DATA_TABLE]";
    const endTag = "[/DATA_TABLE]";
    const startIdx = remaining.indexOf(startTag);

    if (startIdx === -1) {
      // No more tables
      parts.push({ type: "text", content: remaining });
      break;
    }

    // Text before the table
    if (startIdx > 0) {
      parts.push({ type: "text", content: remaining.slice(0, startIdx) });
    }

    const endIdx = remaining.indexOf(endTag, startIdx);
    if (endIdx === -1) {
      // Malformed — treat remaining as text
      parts.push({ type: "text", content: remaining.slice(startIdx) });
      break;
    }

    const tableContent = remaining.slice(startIdx + startTag.length, endIdx).trim();
    parts.push({ type: "table", content: tableContent });
    remaining = remaining.slice(endIdx + endTag.length);
  }

  return (
    <div className="mt-1 space-y-2">
      {parts.map((part, idx) => {
        if (part.type === "text") {
          const trimmed = part.content.trim();
          if (!trimmed) return null;
          return (
            <pre key={idx} className="text-xs text-text-secondary whitespace-pre-wrap">
              {trimmed}
            </pre>
          );
        }

        // Parse CSV table
        const lines = part.content.split("\n").filter((l) => l.trim() !== "");
        if (lines.length === 0) return null;

        const headers = lines[0].split(",");
        const dataRows = lines.slice(1, TABLE_MAX_ROWS + 1);
        const totalRows = lines.length - 1;
        const truncated = totalRows > TABLE_MAX_ROWS;

        return (
          <div key={idx} className="overflow-x-auto">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="bg-primary/10">
                  {headers.map((h, hi) => (
                    <th
                      key={hi}
                      className="px-2 py-1.5 text-left font-semibold text-text-primary border border-gray-200 whitespace-nowrap"
                    >
                      {h.trim()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, ri) => {
                  const cells = row.split(",");
                  return (
                    <tr
                      key={ri}
                      className={ri % 2 === 0 ? "bg-white" : "bg-gray-50"}
                    >
                      {cells.map((cell, ci) => (
                        <td
                          key={ci}
                          className="px-2 py-1 text-text-secondary border border-gray-200 whitespace-nowrap"
                        >
                          {cell.trim()}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {truncated && (
              <p className="text-xs text-text-weak mt-1">
                &#x2026; 共 {totalRows} 条记录，仅展示前 {TABLE_MAX_ROWS} 条
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
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
                  {tc.result && renderToolResult(tc.result)}
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

          {/* Missing params inline card */}
          {message.paramsPending && (
            <div className="mb-3">
              <ParamsInlineCard paramsPending={message.paramsPending} />
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
