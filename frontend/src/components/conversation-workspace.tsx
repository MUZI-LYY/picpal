"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiClientError,
  createConversationMessage,
  getConversation,
  getRun,
  listConversations,
  type ClarificationContent,
  type Message,
  type Run,
  type ConversationSnapshot,
  type ConversationSummary,
  type StructuredAnswer,
} from "@/lib/conversation-api";
import { AppShell } from "./app-shell";
import { ChatComposer } from "./chat-composer";
import { ItineraryPanel } from "./itinerary-panel";
import { PROGRESS_STAGE_KEYS, RunProgress } from "./run-progress";

type ConversationWorkspaceProps = {
  conversationId: string;
};

function isClarificationMessage(
  message: Message,
): message is Message & { structured_content: ClarificationContent } {
  return message.content_type === "clarification" && message.structured_content?.kind === "clarification";
}

export function ConversationWorkspace({ conversationId }: ConversationWorkspaceProps) {
  const [snapshot, setSnapshot] = useState<ConversationSnapshot | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [answeringMessageId, setAnsweringMessageId] = useState<string | null>(null);
  const [openDateMessageId, setOpenDateMessageId] = useState<string | null>(null);
  const [dateValue, setDateValue] = useState("2026-10-02");
  const [error, setError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const loadConversation = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const [nextSnapshot, history] = await Promise.all([
        getConversation(conversationId),
        listConversations(),
      ]);
      setSnapshot(nextSnapshot);
      setConversations(history);
    } catch (reason) {
      setError(
        reason instanceof ApiClientError
          ? reason.message
          : "无法恢复这段旅行对话，请确认后端服务正在运行。",
      );
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    let active = true;
    void Promise.all([getConversation(conversationId), listConversations()])
      .then(([nextSnapshot, history]) => {
        if (!active) return;
        setSnapshot(nextSnapshot);
        setConversations(history);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof ApiClientError
            ? reason.message
            : "无法恢复这段旅行对话，请确认后端服务正在运行。",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [conversationId]);

  // 自动定位到最新对话内容（消息更新 / 行程生成时滚动到底部）。
  useEffect(() => {
    const thread = threadRef.current;
    if (thread) {
      thread.scrollTop = thread.scrollHeight;
    }
  }, [snapshot?.messages.length, snapshot?.latest_plan?.id, snapshot?.active_run?.status]);

  // 轮询 Run 进度：queued/running 时每 2 秒拉取一次，终态后刷新快照。
  useEffect(() => {
    const runId = snapshot?.active_run?.id;
    const status = snapshot?.active_run?.status;
    if (!runId || (status !== "queued" && status !== "running")) {
      return;
    }

    let stopped = false;
    const poll = async () => {
      if (stopped) return;
      try {
        const run = await getRun(runId);
        if (stopped) return;
        setSnapshot((prev) => (prev ? { ...prev, active_run: run } : prev));
        if (run.status === "succeeded" || run.status === "failed") {
          await loadConversation();
        }
      } catch {
        // 断网或临时错误：保持轮询，等待下一轮重试
      }
    };

    const timer = window.setInterval(() => {
      void poll();
    }, 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [snapshot?.active_run?.id, snapshot?.active_run?.status, loadConversation]);

  async function handleSubmit(text: string) {
    setSubmitting(true);
    setError(null);
    try {
      await createConversationMessage(conversationId, text);
      await loadConversation();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "消息发送失败，请稍后重试。");
      return false;
    } finally {
      setSubmitting(false);
    }
  }

  async function handleClarification(
    message: Message & { structured_content: ClarificationContent },
    text: string,
    answer: StructuredAnswer,
  ) {
    setAnsweringMessageId(message.id);
    setError(null);
    try {
      await createConversationMessage(conversationId, text, {
        replyToMessageId: message.id,
        structuredAnswer: answer,
      });
      setOpenDateMessageId(null);
      await loadConversation();
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "选项提交失败，请稍后重试。");
    } finally {
      setAnsweringMessageId(null);
    }
  }

  const resultPanel = snapshot?.latest_plan ? (
    <ItineraryPanel planVersion={snapshot.latest_plan} />
  ) : undefined;

  const completedRun: Run | null = snapshot?.latest_plan
    ? {
        id: "completed",
        conversation_id: conversationId,
        kind: "initial_plan",
        status: "succeeded",
        trigger_message_id: "",
        base_plan_id: null,
        result_plan_id: snapshot.latest_plan.id,
        current_stage: "validating",
        stages: PROGRESS_STAGE_KEYS.map((key) => ({
          key,
          label: "",
          status: "succeeded" as const,
          started_at: null,
          completed_at: null,
        })),
        error: null,
        created_at: "",
        started_at: null,
        finished_at: null,
      }
    : null;

  const answeredClarificationIds = new Set(
    snapshot?.messages
      .filter((message) => message.role === "user" && message.reply_to_message_id)
      .map((message) => message.reply_to_message_id as string) ?? [],
  );

  return (
    <AppShell
      conversations={conversations}
      activeConversationId={conversationId}
      resultPanel={resultPanel}
    >
      <section className="conversation-workspace" aria-label="旅行规划对话">
        {loading ? (
          <div className="loading-state" role="status">
            <span className="loading-orbit" aria-hidden="true" />
            <h1>正在恢复旅行对话</h1>
            <p>同步历史消息和最新规划状态…</p>
          </div>
        ) : null}

        {!loading && error && !snapshot ? (
          <div className="error-state" role="alert">
            <h1>暂时没能打开这段对话</h1>
            <p>{error}</p>
            <button type="button" onClick={() => void loadConversation(true)}>
              <RefreshCw size={17} aria-hidden="true" /> 重新连接
            </button>
          </div>
        ) : null}

        {snapshot ? (
          <>
            <header className="conversation-header">
              <h1 className="conversation-title">新建旅行计划</h1>
              <span className="conversation-status">
                {snapshot.conversation.status === "collecting_requirements" ? "AI 正在补全行程条件" : null}
                {snapshot.conversation.status === "generating" ? "AI 正在生成行程" : null}
                {snapshot.conversation.status === "completed" ? "行程已生成 · 可继续调整" : null}
                {snapshot.conversation.status === "failed" ? "行程生成遇到问题" : null}
                {snapshot.conversation.status === "archived" ? "旅行计划已归档" : null}
              </span>
            </header>

            <div className="message-thread" aria-live="polite" ref={threadRef}>
              {snapshot.messages.map((message) => {
                if (message.role === "user") {
                  return (
                    <article className="message message-user" key={message.id}>
                      <div className="user-bubble">{message.text}</div>
                    </article>
                  );
                }

                const clarification = isClarificationMessage(message) ? message : null;
                const answered = answeredClarificationIds.has(message.id);
                const answering = answeringMessageId === message.id;
                return (
                  <article className="message message-assistant" key={message.id}>
                    <div className="assistant-content">
                      {clarification ? (
                        <p className="message-understood">
                          {clarification.structured_content.slot === "days"
                            ? "可以，我先帮你把最关键的信息补齐。"
                            : `收到，我会规划一份北京 ${snapshot.conversation.requirements.days ?? ""} 天游。`}
                        </p>
                      ) : null}
                      <p className={clarification ? "message-question" : undefined}>{message.text}</p>

                      {clarification?.structured_content.slot === "days" ? (
                        <div className="clarification-options" aria-label="选择游玩天数">
                          {clarification.structured_content.options.map((option) => (
                            <button
                              className="clarification-option"
                              type="button"
                              key={String(option.value)}
                              disabled={answered || answering}
                              onClick={() => {
                                const value = Number(option.value) as 1 | 2 | 3 | 4 | 5;
                                void handleClarification(
                                  clarification,
                                  option.label,
                                  { slot: "days", value },
                                );
                              }}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      ) : null}

                      {clarification?.structured_content.slot === "start_date" ? (
                        <>
                          <div className="clarification-options" aria-label="选择日期状态">
                            <button
                              className="clarification-option"
                              type="button"
                              disabled={answered || answering}
                              onClick={() => setOpenDateMessageId(message.id)}
                            >
                              选择日期
                            </button>
                            <button
                              className="clarification-option"
                              type="button"
                              disabled={answered || answering}
                              onClick={() => void handleClarification(
                                clarification,
                                "日期待定",
                                { slot: "start_date", value: "pending" },
                              )}
                            >
                              日期待定
                            </button>
                          </div>
                          <div className={`clarification-date-box ${openDateMessageId === message.id ? "is-open" : ""}`}>
                            <label>
                              <span className="sr-only">出发日期</span>
                              <input
                                className="clarification-date-input"
                                type="date"
                                value={dateValue}
                                disabled={answered || answering}
                                onChange={(event) => setDateValue(event.target.value)}
                              />
                            </label>
                            <button
                              className="clarification-date-confirm"
                              type="button"
                              disabled={!dateValue || answered || answering}
                              onClick={() => void handleClarification(
                                clarification,
                                `${Number(dateValue.slice(5, 7))} 月 ${Number(dateValue.slice(8, 10))} 日`,
                                { slot: "start_date", value: dateValue },
                              )}
                            >
                              使用这个日期
                            </button>
                          </div>
                        </>
                      ) : null}

                      {clarification?.structured_content.slot === "pace" ? (
                        <div className="clarification-options" aria-label="选择旅行节奏">
                          {clarification.structured_content.options.map((option) => (
                            <button
                              className="clarification-option"
                              type="button"
                              key={String(option.value)}
                              disabled={answered || answering}
                              onClick={() => {
                                const value = option.value as "轻松" | "适中" | "紧凑";
                                void handleClarification(
                                  clarification,
                                  option.label,
                                  { slot: "pace", value },
                                );
                              }}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </article>
                );
              })}

              {snapshot.active_run && !snapshot.latest_plan ? (
                <article className="message message-progress">
                  <RunProgress run={snapshot.active_run} />
                </article>
              ) : null}

              {snapshot.latest_plan && !snapshot.active_run && completedRun ? (
                <>
                  <article className="message message-progress">
                    <RunProgress run={completedRun} />
                  </article>
                  <article className="message message-assistant">
                    <div className="assistant-content">
                      <p>
                        行程已经生成，完整的路线图
                        <span className="result-location-desktop">在右侧</span>
                        <span className="result-location-mobile">在下方</span>
                        ，你可以继续告诉我想调整哪一天、哪个景点或旅行节奏。
                      </p>
                    </div>
                  </article>
                </>
              ) : null}
            </div>

            {snapshot.latest_plan ? (
              <div className="mobile-result-copy">
                <ItineraryPanel planVersion={snapshot.latest_plan} />
              </div>
            ) : null}

            <div className="thread-composer">
              <ChatComposer
                onSubmit={handleSubmit}
                disabled={submitting}
                placeholder="继续补充需求，或告诉我你想调整什么…"
              />
              {error ? <p className="form-error">{error}</p> : null}
            </div>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
