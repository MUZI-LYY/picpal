import { afterEach, describe, expect, it, vi } from "vitest";
import { createConversation, createConversationMessage } from "./conversation-api";

describe("conversation API contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends UUID values for the idempotency and client message identifiers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { conversation: { id: "conv_test" } } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createConversation("第一次去北京，想走经典路线");

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = request.headers as Record<string, string>;
    const body = JSON.parse(request.body as string) as { client_message_id: string };
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    expect(headers["Idempotency-Key"]).toMatch(uuidPattern);
    expect(body.client_message_id).toMatch(uuidPattern);
  });

  it("sends clarification answers with the message being answered", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { conversation: { id: "conv_test" } } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createConversationMessage("conv_test", "3 天", {
      replyToMessageId: "msg_days_question",
      structuredAnswer: { slot: "days", value: 3 },
    });

    const [path, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(request.body as string) as Record<string, unknown>;
    expect(path).toBe("/api/v1/conversations/conv_test/messages");
    expect(body).toMatchObject({
      text: "3 天",
      reply_to_message_id: "msg_days_question",
      structured_answer: { slot: "days", value: 3 },
    });
  });
});
