"use client";

import { useState } from "react";
import type { ConversationSummary, FeaturedPhotoSpot } from "@/lib/conversation-api";
import { AppShell } from "./app-shell";
import { ChatComposer } from "./chat-composer";
import { WelcomePanel } from "./welcome-panel";

const suggestions = [
  { label: "首次到访 · 经典路线", value: "第一次去北京，想走经典路线，每天别太赶。" },
  { label: "带父母 · 轻松游", value: "带父母去北京，希望少走路，节奏轻松。" },
  { label: "周末 · 胡同夜景", value: "周末去北京，喜欢胡同、展览和城市夜景。" },
] as const;

type TravelWorkspaceProps = {
  initialDraft?: string;
  conversations?: ConversationSummary[];
  featuredSpots?: FeaturedPhotoSpot[];
  onSubmit?: (value: string) => boolean | void | Promise<boolean | void>;
  submitting?: boolean;
  error?: string | null;
};

export function TravelWorkspace({
  initialDraft = "",
  conversations,
  featuredSpots = [],
  onSubmit = () => undefined,
  submitting = false,
  error,
}: TravelWorkspaceProps) {
  const [draft, setDraft] = useState(initialDraft);

  return (
    <AppShell conversations={conversations} home>
      <section className="welcome-workspace" aria-label="创建旅行计划">
        <div className="welcome-content">
          <WelcomePanel />
          <div className="composer-wrap">
            <ChatComposer
              value={draft}
              onValueChange={setDraft}
              onSubmit={onSubmit}
              disabled={submitting}
              animatePlaceholder
            />
            <div className="composer-meta" aria-live="polite">
              {error ? (
                <div className="form-error" role="alert">
                  <strong>发送失败</strong>
                  <span>{error} 输入内容已保留，请重新发送。</span>
                </div>
              ) : null}
              {submitting ? <p className="submitting-copy">正在创建你的旅行对话，请稍候…</p> : null}
            </div>
          </div>
          <div className="suggestions" aria-label="旅行需求示例">
            {suggestions.map((suggestion) => (
              <button type="button" key={suggestion.label} onClick={() => setDraft(suggestion.value)}>
                {suggestion.label}
              </button>
            ))}
          </div>
          <section className="inspiration" aria-label="北京热门出片点">
            <div className="inspiration-head">
              <div><h2>北京 · 出片灵感</h2><p>先从具体机位找灵感</p></div>
              <span>悬停卡片，查看位置线索</span>
            </div>
            <div className="photo-wall">
              {featuredSpots.map((item) => (
                <article className="photo-card" key={item.spot_id}>
                  {item.cover_image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={item.cover_image.thumbnail_url ?? item.cover_image.storage_url}
                      alt={`${item.poi_name} · ${item.spot_name}参考照片`}
                      referrerPolicy="no-referrer"
                    />
                  ) : null}
                  <div>
                    <strong>{item.poi_name} · {item.spot_name}</strong>
                    <span>{item.location_description}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </section>
    </AppShell>
  );
}
