"use client";

import { FormEvent, ReactNode, useEffect, useState } from "react";
import { ApiClientError, verifyInvite } from "@/lib/conversation-api";

const INVITED_KEY = "picpal_invited";

type InviteGateProps = {
  children: ReactNode;
};

export function InviteGate({ children }: InviteGateProps) {
  const [invited, setInvited] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    // 一次性读取 localStorage，避免 SSR 水合不一致；同步 setState 是必要的一次性初始化。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInvited(window.localStorage.getItem(INVITED_KEY) === "1");
    setChecking(false);
  }, []);

  if (checking) return null;

  if (invited) return <>{children}</>;

  return (
    <InviteGateScreen
      onVerified={() => {
        window.localStorage.setItem(INVITED_KEY, "1");
        setInvited(true);
      }}
    />
  );
}

function InviteGateScreen({ onVerified }: { onVerified: () => void }) {
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!code.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await verifyInvite(code.trim());
      onVerified();
    } catch (reason) {
      setError(
        reason instanceof ApiClientError ? reason.message : "验证失败，请稍后重试",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="invite-gate">
      <div className="invite-gate-card">
        <span className="panel-kicker">PICPAL 内测</span>
        <h1>输入邀请码</h1>
        <p>首期仅限内测用户，请输入你的邀请码进入。</p>
        <form onSubmit={handleSubmit}>
          <input
            className="invite-input"
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="请输入邀请码"
            autoFocus
            maxLength={64}
            autoComplete="off"
          />
          <button
            className="invite-submit"
            type="submit"
            disabled={!code.trim() || submitting}
          >
            {submitting ? "验证中…" : "进入"}
          </button>
        </form>
        {error ? <p className="invite-error" role="alert">{error}</p> : null}
      </div>
    </div>
  );
}
