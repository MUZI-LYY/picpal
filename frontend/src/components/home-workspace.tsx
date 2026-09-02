"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiClientError,
  createConversation,
  listFeaturedPhotoSpots,
  listConversations,
  type ConversationSummary,
  type FeaturedPhotoSpot,
} from "@/lib/conversation-api";
import { TravelWorkspace } from "./travel-workspace";

type HomeWorkspaceProps = {
  initialDraft?: string;
};

export function HomeWorkspace({ initialDraft = "" }: HomeWorkspaceProps) {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [featuredSpots, setFeaturedSpots] = useState<FeaturedPhotoSpot[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (window.localStorage.getItem("picpal_has_session") !== "1") return;
    let active = true;
    void listConversations()
      .then((items) => {
        if (active) setConversations(items);
      })
      .catch(() => {
        // A first-time visitor may not have an anonymous session yet.
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void listFeaturedPhotoSpots(8)
      .then((items) => {
        if (active) setFeaturedSpots(items);
      })
      .catch(() => {
        // 精选区只展示已准入的真实采集数据；接口异常时不回退到虚构卡片。
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(text: string) {
    setSubmitting(true);
    setError(null);
    try {
      const turn = await createConversation(text);
      window.localStorage.setItem("picpal_has_session", "1");
      router.push(`/chat/${turn.conversation.id}`);
    } catch (reason) {
      setError(
        reason instanceof ApiClientError
          ? reason.message
          : "暂时无法连接旅行助手，请检查后端服务后重试。",
      );
      setSubmitting(false);
      return false;
    }
  }

  return (
    <TravelWorkspace
      initialDraft={initialDraft}
      conversations={conversations}
      onSubmit={handleSubmit}
      submitting={submitting}
      error={error}
      featuredSpots={featuredSpots}
    />
  );
}
