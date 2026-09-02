import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createConversationMessage: vi.fn(),
  getConversation: vi.fn(),
  listConversations: vi.fn(),
}));

vi.mock("@/lib/conversation-api", () => ({
  ApiClientError: class ApiClientError extends Error {},
  createConversationMessage: api.createConversationMessage,
  getConversation: api.getConversation,
  listConversations: api.listConversations,
}));

import { ConversationWorkspace } from "./conversation-workspace";

function snapshot(slot: "days" | "start_date") {
  return {
    conversation: {
      id: "conv_test",
      title: "新建旅行计划",
      status: "collecting_requirements",
      requirements: { days: slot === "start_date" ? 3 : null },
      latest_plan_id: null,
      active_run_id: null,
      created_at: "2026-08-21T00:00:00Z",
      updated_at: "2026-08-21T00:00:00Z",
    },
    messages: [
      {
        id: `msg_${slot}`,
        conversation_id: "conv_test",
        role: "assistant",
        content_type: "clarification",
        text: slot === "days"
          ? "这次准备在北京玩几天？"
          : "出发日期定了吗？也可以先选择日期待定。",
        structured_content: slot === "days"
          ? {
              kind: "clarification",
              slot: "days",
              control: "single_select",
              options: [
                { label: "1 天", value: 1 },
                { label: "2 天", value: 2 },
                { label: "3 天", value: 3 },
              ],
              allow_pending: false,
            }
          : {
              kind: "clarification",
              slot: "start_date",
              control: "date_or_pending",
              options: [],
              allow_pending: true,
            },
        reply_to_message_id: null,
        run_id: null,
        plan_id: null,
        created_at: "2026-08-21T00:00:00Z",
      },
    ],
    active_run: null,
    latest_plan: null,
  };
}

describe("ConversationWorkspace clarification controls", () => {
  beforeEach(() => {
    api.createConversationMessage.mockReset().mockResolvedValue({});
    api.getConversation.mockReset();
    api.listConversations.mockReset().mockResolvedValue([]);
  });

  it("submits the selected trip length as a structured answer", async () => {
    api.getConversation.mockResolvedValue(snapshot("days"));
    const user = userEvent.setup();
    render(<ConversationWorkspace conversationId="conv_test" />);

    await user.click(await screen.findByRole("button", { name: "3 天" }));

    await waitFor(() => expect(api.createConversationMessage).toHaveBeenCalledWith(
      "conv_test",
      "3 天",
      {
        replyToMessageId: "msg_days",
        structuredAnswer: { slot: "days", value: 3 },
      },
    ));
  });

  it("supports both the explicit date and pending-date branches", async () => {
    api.getConversation.mockResolvedValue(snapshot("start_date"));
    const user = userEvent.setup();
    render(<ConversationWorkspace conversationId="conv_test" />);

    await user.click(await screen.findByRole("button", { name: "选择日期" }));
    expect(screen.getByLabelText("出发日期")).toHaveValue("2026-10-02");

    await user.click(screen.getByRole("button", { name: "日期待定" }));
    await waitFor(() => expect(api.createConversationMessage).toHaveBeenCalledWith(
      "conv_test",
      "日期待定",
      {
        replyToMessageId: "msg_start_date",
        structuredAnswer: { slot: "start_date", value: "pending" },
      },
    ));
  });

  it("submits the selected calendar date in the backend contract format", async () => {
    api.getConversation.mockResolvedValue(snapshot("start_date"));
    const user = userEvent.setup();
    render(<ConversationWorkspace conversationId="conv_test" />);

    await user.click(await screen.findByRole("button", { name: "选择日期" }));
    fireEvent.change(screen.getByLabelText("出发日期"), { target: { value: "2026-10-05" } });
    await user.click(screen.getByRole("button", { name: "使用这个日期" }));

    await waitFor(() => expect(api.createConversationMessage).toHaveBeenCalledWith(
      "conv_test",
      "10 月 5 日",
      {
        replyToMessageId: "msg_start_date",
        structuredAnswer: { slot: "start_date", value: "2026-10-05" },
      },
    ));
  });
});
