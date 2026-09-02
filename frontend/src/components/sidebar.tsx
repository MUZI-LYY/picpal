import { ChevronsLeft, ChevronsRight, History, MessageCircleMore, Plus, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ConversationSummary } from "@/lib/conversation-api";

type SidebarProps = {
  conversations?: ConversationSummary[];
  activeConversationId?: string;
  open?: boolean;
  onClose?: () => void;
  expanded?: boolean;
  onToggleExpand?: () => void;
};

export function Sidebar({
  conversations = [],
  activeConversationId,
  open = false,
  onClose,
  expanded = false,
  onToggleExpand,
}: SidebarProps) {
  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""} ${expanded ? "sidebar-expanded" : ""}`} aria-label="旅行计划导航">
      <div className="sidebar-brand-row">
        <Link className="brand" href="/" aria-label="PicPal 首页">
          <span className="brand-full-logo" aria-hidden="true">
            <Image
              src="/brand/picpal-logo.png"
              alt=""
              width={1200}
              height={370}
              sizes="112px"
              loading="eager"
              unoptimized
            />
          </span>
          <span className="brand-mark" aria-hidden="true">
            <Image
              src="/brand/picpal-mark.png"
              alt=""
              width={512}
              height={512}
              sizes="34px"
              loading="eager"
              unoptimized
            />
          </span>
        </Link>
        <button className="sidebar-close" type="button" onClick={onClose} aria-label="关闭历史对话">
          <X size={20} aria-hidden="true" />
        </button>
      </div>

      <Link className="new-plan-link" href="/plan" onClick={onClose}>
        <Plus size={18} aria-hidden="true" />
        <span>新建旅行计划</span>
      </Link>

      <section className="history-section" aria-labelledby="history-title">
        <div className="section-title-row">
          <h2 id="history-title">
            <History size={15} aria-hidden="true" />
            历史对话
          </h2>
          {conversations.length > 0 ? <span>{conversations.length}</span> : null}
        </div>

        {conversations.length === 0 ? (
          <div className="history-empty">
            <MessageCircleMore size={20} aria-hidden="true" />
            <p>还没有旅行计划</p>
            <span>完成第一次对话后，会保存在这里。</span>
          </div>
        ) : (
          <nav className="conversation-list" aria-label="历史对话列表">
            {conversations.map((conversation) => (
              <Link
                className={conversation.id === activeConversationId ? "conversation-link active" : "conversation-link"}
                href={`/chat/${conversation.id}`}
                key={conversation.id}
                onClick={onClose}
                aria-current={conversation.id === activeConversationId ? "page" : undefined}
              >
                <strong>{conversation.title}</strong>
              </Link>
            ))}
          </nav>
        )}
      </section>

      <div className="sidebar-note">
        <span className="sidebar-avatar" aria-hidden="true">旅</span>
        <span>我的旅行计划</span>
      </div>

      <button
        className="sidebar-expand-toggle"
        type="button"
        onClick={onToggleExpand}
        aria-label={expanded ? "收起侧边栏" : "展开侧边栏"}
        aria-expanded={expanded}
      >
        {expanded ? <ChevronsLeft size={18} aria-hidden="true" /> : <ChevronsRight size={18} aria-hidden="true" />}
      </button>
    </aside>
  );
}
