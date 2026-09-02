import type { Metadata } from "next";
import { ConversationWorkspace } from "@/components/conversation-workspace";

export const metadata: Metadata = {
  title: "旅行计划｜PicPal",
};

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  return <ConversationWorkspace conversationId={conversationId} />;
}
