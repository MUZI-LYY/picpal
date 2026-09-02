import type { Metadata } from "next";
import { HomeWorkspace } from "@/components/home-workspace";

export const metadata: Metadata = {
  title: "定制专属行程｜PicPal",
  description: "告诉 PicPal 你想怎样逛北京，通过对话生成按天安排的行程与沿途出片点。",
};

type PlanPageProps = {
  searchParams: Promise<{ prompt?: string | string[] }>;
};

export default async function PlanPage({ searchParams }: PlanPageProps) {
  const params = await searchParams;
  const promptValue = Array.isArray(params.prompt) ? params.prompt[0] : params.prompt;
  const initialDraft = promptValue?.trim().slice(0, 1000) ?? "";

  return <HomeWorkspace initialDraft={initialDraft} />;
}
