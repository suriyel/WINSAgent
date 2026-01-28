/** REST API calls to the FastAPI backend. */

import type { SSEEventType } from "../types";

const BASE = "/api";

export async function fetchConversations() {
  const res = await fetch(`${BASE}/conversations`);
  return res.json();
}

export async function fetchConversation(id: string) {
  const res = await fetch(`${BASE}/conversations/${id}`);
  return res.json();
}

export async function fetchTodos(taskId: string) {
  const res = await fetch(`${BASE}/tasks/${taskId}/todos`);
  return res.json();
}

export async function fetchTools() {
  const res = await fetch(`${BASE}/tools`);
  return res.json();
}

type SSECallback = (eventType: SSEEventType, data: Record<string, unknown>) => void;

/**
 * Submit HITL decision and handle SSE stream response.
 * Returns an AbortController to cancel the stream if needed.
 */
export function submitHITLDecision(
  executionId: string,
  tool_name: string,
  action: "approve" | "edit" | "reject",
  editedParams: Record<string, unknown> = {},
  onEvent: SSECallback,
  onDone: () => void,
  onError: (err: Event) => void
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/hitl/${executionId}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, tool_name, edited_params: editedParams }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        onError(new Event("fetch_error"));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE frames: "event: <type>\ndata: <json>\n\n"
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          if (!frame.trim()) continue;

          let eventType: SSEEventType = "message";
          let dataStr = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim() as SSEEventType;
            } else if (line.startsWith("data: ")) {
              dataStr = line.slice(6);
            }
          }

          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);

            if (eventType === "done") {
              onDone();
              return;
            }

            onEvent(eventType, data);
          } catch {
            // Skip malformed JSON
          }
        }
      }

      onDone();
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      onError(new Event("connection_error"));
    }
  })();

  return controller;
}

export async function rebuildKnowledge(knowledgeType?: string) {
  const res = await fetch(`${BASE}/knowledge/rebuild`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ knowledge_type: knowledgeType ?? null }),
  });
  return res.json();
}
