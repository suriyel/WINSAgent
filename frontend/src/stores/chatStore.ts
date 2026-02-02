/** Zustand store — central state management for the workstation. */

import { create } from "zustand";
import type {
  ChartData,
  ChartPending,
  Conversation,
  HITLAction,
  HITLPending,
  Message,
  ParamsAction,
  ParamsPending,
  SSEEventType,
  Suggestion,
  SuggestionGroup,
  TableData,
  TodoStep,
  ToolCallInfo,
} from "../types";
import { connectSSE } from "../services/sse";
import { submitHITLDecision, submitParamsDecision } from "../services/api";

interface ChatState {
  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;

  // Messages for the active conversation
  messages: Message[];

  // Streaming state
  isStreaming: boolean;
  thinkingBuffer: string;

  // TODO steps (keyed by task/thread id)
  todoSteps: Record<string, TodoStep[]>;

  // HITL pending decision
  pendingHITL: HITLPending | null;

  // Missing params pending (for MissingParamsMiddleware)
  pendingParams: ParamsPending | null;

  // Active SSE controller
  _sseController: AbortController | null;

  // --- Actions ---
  setActiveConversation: (id: string) => void;
  sendMessage: (content: string) => void;
  handleSSEEvent: (eventType: SSEEventType, data: Record<string, unknown>) => void;
  submitHITL: (action: HITLAction, tool_name?: string, editedParams?: Record<string, unknown>) => void;
  submitParams: (action: ParamsAction, editedParams?: Record<string, unknown>) => void;
  stopStreaming: () => void;
}

let messageIdCounter = 0;
function nextMsgId() {
  return `msg-${++messageIdCounter}-${Date.now()}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  thinkingBuffer: "",
  todoSteps: {},
  pendingHITL: null,
  pendingParams: null,
  _sseController: null,

  setActiveConversation(id: string) {
    set({ activeConversationId: id });
  },

  sendMessage(content: string) {
    const state = get();
    if (state.isStreaming) return;

    // Add user message
    const userMsg: Message = {
      id: nextMsgId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };

    // Placeholder for assistant streaming response
    const assistantMsg: Message = {
      id: nextMsgId(),
      role: "assistant",
      content: "",
      isStreaming: true,
      toolCalls: [],
      todoSteps: [],
      timestamp: Date.now(),
    };

    set({
      messages: [...state.messages, userMsg, assistantMsg],
      isStreaming: true,
      thinkingBuffer: "",
      pendingHITL: null,
    });

    const controller = connectSSE(
      content,
      state.activeConversationId,
      (eventType, data) => get().handleSSEEvent(eventType, data),
      () => {
        // Done — finalize the streaming message
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, isStreaming: false };
          }
          return { messages: msgs, isStreaming: false, _sseController: null };
        });
      },
      () => {
        set({ isStreaming: false, _sseController: null });
      }
    );

    set({ _sseController: controller });
  },

  handleSSEEvent(eventType: SSEEventType, data: Record<string, unknown>) {
    set((state) => {
      const msgs = [...state.messages];
      const lastIdx = msgs.length - 1;
      const last = lastIdx >= 0 ? { ...msgs[lastIdx] } : null;

      switch (eventType) {
        case "session": {
          const convId = data.conversation_id as string;
          return {
            activeConversationId: convId,
            conversations: state.conversations.some((c) => c.id === convId)
              ? state.conversations
              : [
                  ...state.conversations,
                  {
                    id: convId,
                    title: `会话 ${convId.slice(0, 8)}`,
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  },
                ],
          };
        }

        case "thinking": {
          if (last && last.role === "assistant") {
            const token = data.token as string;
            last.content += token;
            msgs[lastIdx] = last;
          }
          return { messages: msgs, thinkingBuffer: state.thinkingBuffer + (data.token as string) };
        }

        case "message": {
          if (last && last.role === "assistant") {
            last.content = data.content as string;
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "tool.call": {
          if (last && last.role === "assistant") {
            const execId = data.execution_id as string;
            const existingCalls = last.toolCalls ?? [];
            // Skip if tool call with same execution_id already exists (avoid duplicates on HITL resume)
            if (existingCalls.some((tc) => tc.execution_id === execId)) {
              return { messages: msgs };
            }
            const tc: ToolCallInfo = {
              tool_name: data.tool_name as string,
              params: data.params as Record<string, unknown>,
              execution_id: execId,
              status: "running",
            };
            last.toolCalls = [...existingCalls, tc];
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "tool.result": {
          if (last && last.role === "assistant") {
            const execId = data.execution_id as string;
            last.toolCalls = (last.toolCalls ?? []).map((tc) =>
              tc.execution_id === execId
                ? { ...tc, result: data.result as string, status: data.status as ToolCallInfo["status"] }
                : tc
            );
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "table.data": {
          if (last && last.role === "assistant") {
            const execId = data.execution_id as string;
            const tables = data.tables as TableData[];
            last.toolCalls = (last.toolCalls ?? []).map((tc) =>
              tc.execution_id === execId ? { ...tc, tableData: tables } : tc
            );
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "chart.data": {
          if (last && last.role === "assistant") {
            const chartData: ChartPending = {
              execution_id: data.execution_id as string,
              chart_type: data.chart_type as string,
              data: data.data as ChartData,
            };
            last.chartPending = chartData;
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "todo.state": {
          const taskId = data.task_id as string;
          const steps = data.steps as TodoStep[];
          // Also attach to last assistant message
          if (last && last.role === "assistant") {
            last.todoSteps = steps;
            msgs[lastIdx] = last;
          }
          return {
            messages: msgs,
            todoSteps: { ...state.todoSteps, [taskId]: steps },
          };
        }

        case "hitl.pending": {
          const hitlData: HITLPending = {
            execution_id: data.execution_id as string,
            tool_name: data.tool_name as string,
            params: data.params as Record<string, unknown>,
            schema: data.schema as Record<string, unknown>,
            description: data.description as string | undefined,
          };
          // Attach HITL info to the last assistant message for inline rendering
          if (last && last.role === "assistant") {
            last.hitlPending = hitlData;
            last.isStreaming = false; // Pause streaming while waiting for HITL
            msgs[lastIdx] = last;
          }
          return {
            messages: msgs,
            pendingHITL: hitlData,
            isStreaming: false, // Pause streaming while waiting for HITL decision
          };
        }

        case "params.pending": {
          const paramsData: ParamsPending = {
            execution_id: data.execution_id as string,
            tool_name: data.tool_name as string,
            tool_call_id: data.tool_call_id as string,
            description: data.description as string | undefined,
            current_params: data.current_params as Record<string, unknown>,
            missing_params: data.missing_params as string[],
            params_schema: data.params_schema as Record<string, import("../types").ParamSchema>,
          };
          // Attach params info to the last assistant message for inline rendering
          if (last && last.role === "assistant") {
            last.paramsPending = paramsData;
            last.isStreaming = false; // Pause streaming while waiting for params
            msgs[lastIdx] = last;
          }
          return {
            messages: msgs,
            pendingParams: paramsData,
            isStreaming: false, // Pause streaming while waiting for params input
          };
        }

        case "suggestions": {
          // Attach suggestions to the last assistant message
          if (last && last.role === "assistant") {
            const suggestionsData = data.suggestions as Suggestion[];
            const multiSelect = data.multi_select as boolean | undefined;
            const prompt = data.prompt as string | undefined;
            last.suggestions = {
              suggestions: suggestionsData,
              multiSelect: multiSelect ?? false,
              prompt,
            };
            msgs[lastIdx] = last;
          }
          return { messages: msgs };
        }

        case "error": {
          if (last && last.role === "assistant") {
            last.content += `\n\n[Error] ${data.message ?? "Unknown error"}`;
            last.isStreaming = false;
            msgs[lastIdx] = last;
          }
          return { messages: msgs, isStreaming: false };
        }

        default:
          return {};
      }
    });
  },

  submitHITL(action: HITLAction, tool_name?: string, editedParams?: Record<string, unknown>) {
    const pending = get().pendingHITL;
    if (!pending) return;

    const convId = get().activeConversationId;
    if (!convId) return;

    // Clear pending HITL from both global state and the message
    set((state) => {
      const msgs = [...state.messages];
      const lastIdx = msgs.length - 1;
      if (lastIdx >= 0 && msgs[lastIdx].role === "assistant") {
        msgs[lastIdx] = { ...msgs[lastIdx], hitlPending: undefined, isStreaming: true };
      }
      return { messages: msgs, pendingHITL: null, isStreaming: true };
    });

    const controller = submitHITLDecision(
      convId,
      tool_name ?? pending.tool_name ?? "unknown",
      action,
      editedParams ?? {},
      (eventType, data) => get().handleSSEEvent(eventType, data),
      () => {
        // Done — finalize the streaming message
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, isStreaming: false };
          }
          return { messages: msgs, isStreaming: false, _sseController: null };
        });
      },
      () => {
        set({ isStreaming: false, _sseController: null });
      }
    );

    set({ _sseController: controller });
  },

  submitParams(action: ParamsAction, editedParams?: Record<string, unknown>) {
    const pending = get().pendingParams;
    if (!pending) return;

    const convId = get().activeConversationId;
    if (!convId) return;

    // Clear pending params from both global state and the message
    set((state) => {
      const msgs = [...state.messages];
      const lastIdx = msgs.length - 1;
      if (lastIdx >= 0 && msgs[lastIdx].role === "assistant") {
        msgs[lastIdx] = { ...msgs[lastIdx], paramsPending: undefined, isStreaming: true };
      }
      return { messages: msgs, pendingParams: null, isStreaming: true };
    });

    // Submit params decision to dedicated params endpoint
    const controller = submitParamsDecision(
      convId,
      pending.tool_name,
      action,
      editedParams ?? {},
      (eventType, data) => get().handleSSEEvent(eventType, data),
      () => {
        // Done — finalize the streaming message
        set((s) => {
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, isStreaming: false };
          }
          return { messages: msgs, isStreaming: false, _sseController: null };
        });
      },
      () => {
        set({ isStreaming: false, _sseController: null });
      }
    );

    set({ _sseController: controller });
  },

  stopStreaming() {
    const ctrl = get()._sseController;
    if (ctrl) ctrl.abort();
    set({ isStreaming: false, _sseController: null });
  },
}));
