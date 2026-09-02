import type { components } from "@/types/api.generated";

export type ConversationSummary = components["schemas"]["ConversationSummary"];
export type ConversationSnapshot = components["schemas"]["ConversationSnapshotData"];
export type ConversationTurn = components["schemas"]["ConversationTurnData"];
export type Message = components["schemas"]["Message"];
export type ClarificationContent = components["schemas"]["ClarificationContent"];
export type PlanVersion = components["schemas"]["PlanVersion"];
export type Run = components["schemas"]["Run"];
export type StructuredAnswer = components["schemas"]["StructuredAnswer"];
export type FeaturedPhotoSpot = components["schemas"]["FeaturedPhotoSpot"];

type ApiErrorResponse = components["schemas"]["ApiErrorResponse"];
type ConversationListResponse = components["schemas"]["ConversationListResponse"];
type ConversationSnapshotResponse = components["schemas"]["ConversationSnapshotResponse"];
type ConversationTurnResponse = components["schemas"]["ConversationTurnResponse"];
type FeaturedPhotoSpotListResponse = components["schemas"]["FeaturedPhotoSpotListResponse"];
type RunResponse = components["schemas"]["RunResponse"];

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let payload: ApiErrorResponse | undefined;
    try {
      payload = (await response.json()) as ApiErrorResponse;
    } catch {
      payload = undefined;
    }

    throw new ApiClientError(
      payload?.error.message ?? "服务暂时不可用，请稍后再试。",
      response.status,
      payload?.error.code,
    );
  }

  return (await response.json()) as T;
}

function requestId(): string {
  return crypto.randomUUID();
}

export async function createConversation(text: string): Promise<ConversationTurn> {
  const clientMessageId = requestId();
  const response = await requestJson<ConversationTurnResponse>("/api/v1/conversations", {
    method: "POST",
    headers: { "Idempotency-Key": requestId() },
    body: JSON.stringify({ client_message_id: clientMessageId, text }),
  });
  return response.data;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await requestJson<ConversationListResponse>("/api/v1/conversations?limit=30");
  return response.data;
}

export async function listFeaturedPhotoSpots(limit = 5): Promise<FeaturedPhotoSpot[]> {
  const response = await requestJson<FeaturedPhotoSpotListResponse>(
    `/api/v1/photo-spots/featured?city=${encodeURIComponent("北京")}&limit=${limit}`,
  );
  return response.data;
}

export async function getConversation(conversationId: string): Promise<ConversationSnapshot> {
  const response = await requestJson<ConversationSnapshotResponse>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
  );
  return response.data;
}

export async function verifyInvite(code: string): Promise<boolean> {
  await requestJson<{ data: { invited: boolean } }>("/api/v1/invites/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  return true;
}

export async function getRun(runId: string): Promise<Run> {
  const response = await requestJson<RunResponse>(
    `/api/v1/runs/${encodeURIComponent(runId)}`,
  );
  return response.data;
}

export async function createConversationMessage(
  conversationId: string,
  text: string,
  options?: {
    replyToMessageId?: string;
    structuredAnswer?: StructuredAnswer;
    basePlanId?: string;
  },
): Promise<ConversationTurn> {
  const response = await requestJson<ConversationTurnResponse>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      headers: { "Idempotency-Key": requestId() },
      body: JSON.stringify({
        client_message_id: requestId(),
        text,
        reply_to_message_id: options?.replyToMessageId ?? null,
        structured_answer: options?.structuredAnswer ?? null,
        base_plan_id: options?.basePlanId ?? null,
      }),
    },
  );
  return response.data;
}
