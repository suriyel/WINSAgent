/** REST API calls to the FastAPI backend. */

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

export async function submitHITLDecision(
  executionId: string,
  tool_name:string,
  action: "approve" | "edit" | "reject",
  editedParams: Record<string, unknown> = {}
) {
  const res = await fetch(`${BASE}/hitl/${executionId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({action, tool_name, edited_params: editedParams}),
  });
  return res.json();
}

export async function rebuildKnowledge(knowledgeType?: string) {
  const res = await fetch(`${BASE}/knowledge/rebuild`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ knowledge_type: knowledgeType ?? null }),
  });
  return res.json();
}
