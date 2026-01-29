/** SSE (Server-Sent Events) connection manager. */

import type { SSEEventType } from "../types";

type SSECallback = (eventType: SSEEventType, data: Record<string, unknown>) => void;

const SSE_EVENT_TYPES: SSEEventType[] = [
  "session",
  "thinking",
  "tool.call",
  "tool.result",
  "hitl.pending",
  "params.pending",
  "todo.state",
  "message",
  "suggestions",
  "error",
  "done",
];

export function connectSSE(
  message: string,
  conversationId: string | null,
  onEvent: SSECallback,
  onDone: () => void,
  onError: (err: Event) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          message,
        }),
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
