"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { ReactNode, useState } from "react";
import type { ConversationSummary } from "@/lib/conversation-api";
import { Sidebar } from "./sidebar";

type AppShellProps = {
  children: ReactNode;
  conversations?: ConversationSummary[];
  activeConversationId?: string;
  resultPanel?: ReactNode;
  home?: boolean;
};

export function AppShell({ children, conversations, activeConversationId, resultPanel, home = false }: AppShellProps) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  return (
    <div className={`app-shell ${home ? "is-home" : "is-chatting"} ${resultPanel ? "has-result" : ""} ${sidebarExpanded ? "sidebar-expanded" : ""}`}>
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <div className="ambient ambient-three" aria-hidden="true" />
      <button
        className={`sidebar-backdrop ${historyOpen ? "visible" : ""}`}
        type="button"
        aria-label="关闭历史对话"
        tabIndex={historyOpen ? 0 : -1}
        onClick={() => setHistoryOpen(false)}
      />
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        expanded={sidebarExpanded}
        onToggleExpand={() => setSidebarExpanded((value) => !value)}
      />
      <main className={`main-workspace ${home ? "" : "is-chatting"} ${resultPanel ? "is-result-layout" : ""}`}>
        <header className="mobile-header">
          <button
            type="button"
            aria-label="查看历史对话"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen(true)}
          >
            <Menu size={21} aria-hidden="true" />
          </button>
          <Link className="mobile-brand" href="/" aria-label="PicPal 首页">
            <Image
              className="mobile-brand-logo"
              src="/brand/picpal-logo.png"
              alt=""
              width={1200}
              height={370}
              sizes="96px"
              loading="eager"
              unoptimized
            />
          </Link>
          <span className="mobile-beta">Beta</span>
        </header>
        <div className="shell-topline"><span><i />北京试点 · 出片点持续更新</span></div>
        {children}
      </main>
      {resultPanel ? <aside className="result-panel">{resultPanel}</aside> : null}
    </div>
  );
}
