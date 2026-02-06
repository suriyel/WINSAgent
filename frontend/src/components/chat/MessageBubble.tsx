import type { Message } from "../../types";
import { useState, lazy, Suspense } from "react";
import ThinkingIndicator from "./ThinkingIndicator";
import DataTable from "./DataTable";
import TodoStepper from "../todo/TodoStepper";
import HITLInlineCard from "../hitl/HITLInlineCard";
import ParamsInlineCard from "../hitl/ParamsInlineCard";
import SuggestionChips from "./SuggestionChips";

const AutoChart = lazy(() => import("../chart/AutoChart"));

interface Props {
  message: Message;
}

/** Max number of data rows to display in a table (excluding the header). */
const TABLE_MAX_ROWS = 10;

/** Strip ```suggestions {...}```, ```template {...}```, and <suggestions>...</suggestions> blocks from display content. */
function stripSuggestionsBlock(content: string): string {
  return content
    .replace(/```suggestions\s*\{[\s\S]*?\}\s*```/gi, "")
    .replace(/```template\s*\{[\s\S]*?\}\s*```/gi, "")
    .replace(/<suggestions>[\s\S]*?<\/suggestions>/gi, "")
    .trim();
}

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
  const [collapsedToolCallIds, setCollapsedToolCallIds] = useState<Set<string>>(new Set());

  const toggleToolCollapse = (executionId: string) => {
    const newCollapsed = new Set(collapsedToolCallIds);
    if (newCollapsed.has(executionId)) {
      newCollapsed.delete(executionId);
    } else {
      newCollapsed.add(executionId);
    }
    setCollapsedToolCallIds(newCollapsed);
  };

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
              {message.toolCalls.map((tc) => {
                const isCollapsed = collapsedToolCallIds.has(tc.execution_id);
                return (
                  <div
                    key={tc.execution_id}
                    className="rounded-lg border border-gray-100 bg-surface text-sm"
                  >
                    {/* Tool header with collapse button */}
                    <div
                      className="flex items-center gap-2 p-3 cursor-pointer hover:bg-gray-50 rounded-t-lg"
                      onClick={() => toggleToolCollapse(tc.execution_id)}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          tc.status === "success"
                            ? "bg-success"
                            : tc.status === "failed"
                            ? "bg-error"
                            : "bg-secondary animate-pulse"
                        }`}
                      />
                      <span className="font-medium text-text-primary flex-1">{tc.tool_name}</span>
                      <span className="text-text-weak text-xs">
                        {tc.status === "running"
                          ? "执行中..."
                          : tc.status === "success"
                          ? "已完成"
                          : tc.status === "failed"
                          ? "失败"
                          : "待执行"}
                      </span>
                      {/* Collapse/expand icon */}
                      <svg
                        className={`w-4 h-4 text-text-secondary transition-transform ${
                          isCollapsed ? "rotate-0" : "rotate-180"
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </div>
                    {/* Tool content */}
                    {!isCollapsed && (
                      <div className="px-3 pb-3">
                        {tc.tableData && tc.tableData.length > 0 ? (
                          <div className="space-y-3">
                            {tc.result && (() => {
                              const textBefore = tc.result.split("[DATA_TABLE]")[0].trim();
                              return textBefore ? (
                                <pre className="text-xs text-text-secondary whitespace-pre-wrap">
                                  {textBefore}
                                </pre>
                              ) : null;
                            })()}
                            {tc.tableData.map((table, idx) => (
                              <DataTable key={idx} table={table} tableIndex={idx} />
                            ))}
                          </div>
                        ) : (
                          tc.result && renderToolResult(tc.result)
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
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

          {/* Chart */}
          {message.chartPending && (
            <div className="mb-3">
              <Suspense fallback={<div className="h-40 flex items-center justify-center text-sm text-text-weak">加载图表组件...</div>}>
                <AutoChart chartPending={message.chartPending} />
              </Suspense>
            </div>
          )}

          {/* Message text */}
          {message.content && (() => {
            const displayContent = stripSuggestionsBlock(message.content);
            return displayContent ? (
              <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
                {displayContent}
              </div>
            ) : null;
          })()}

          {/* Template pending - 话术模板（暂停对话等待选择） */}
          {message.templatePending && !message.isStreaming && (
            <SuggestionChips
              suggestionGroup={{
                suggestions: message.templatePending.options,
                multiSelect: false,
                prompt: message.templatePending.prompt,
              }}
              isTemplate={true}
            />
          )}

          {/* Suggestion chips - 建议选项 */}
          {message.suggestions && !message.isStreaming && !message.templatePending && (
            <SuggestionChips suggestionGroup={message.suggestions} />
          )}

          {/* Streaming indicator */}
          {message.isStreaming && !message.content && <ThinkingIndicator />}
        </div>
      </div>
    </div>
  );
}
