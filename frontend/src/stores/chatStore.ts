/** Zustand store — central state management for the workstation. */

import { create } from "zustand";
import type {
  Conversation,
  HITLAction,
  HITLPending,
  Message,
  SSEEventType,
  TodoStep,
  ToolCallInfo,
} from "../types";
import { connectSSE } from "../services/sse";
import { submitHITLDecision } from "../services/api";

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

  // Active SSE controller
  _sseController: AbortController | null;

  // --- Actions ---
  setActiveConversation: (id: string) => void;
  sendMessage: (content: string) => void;
  handleSSEEvent: (eventType: SSEEventType, data: Record<string, unknown>) => void;
  submitHITL: (action: HITLAction, tool_name?: string, editedParams?: Record<string, unknown>) => void;
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
          return {
            pendingHITL: {
              execution_id: data.execution_id as string,
              tool_name: data.tool_name as string,
              params: data.params as Record<string, unknown>,
              schema: data.schema as Record<string, unknown>,
              description: data.description as string | undefined,
            },
          };
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

    // Clear pending HITL and set streaming state
    set({ pendingHITL: null, isStreaming: true });

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

  stopStreaming() {
    const ctrl = get()._sseController;
    if (ctrl) ctrl.abort();
    set({ isStreaming: false, _sseController: null });
  },
}));
