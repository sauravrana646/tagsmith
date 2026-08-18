"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, api } from "@/lib/api";

type Status = {
  gmail_authenticated: boolean;
  gmail_detail: string;
  hint: string;
  enable_rag?: boolean;
  rag_example_count?: number;
  background_sync?: boolean;
};

type Summary = { proposals: number; needs_review: number; held: number };

type Me = {
  authenticated: boolean;
  tenant_id?: number;
  email?: string;
  name?: string;
  picture_url?: string | null;
  plan?: string;
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/held", label: "Held" },
  { href: "/needs-review", label: "Needs review" },
  { href: "/proposals", label: "Proposals" },
  { href: "/taxonomy", label: "Labels" },
];

function initials(name?: string, email?: string): string {
  const src = (name || email || "?").trim();
  const parts = src.split(/[\s]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

function displayName(me: Me): string {
  const local = me.email?.split("@")[0];
  if (me.name && me.name !== local && !me.name.includes("@")) return me.name;
  return me.email || "Signed in";
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<Status | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [apply, setApply] = useState(true);
  const [busyAuth, setBusyAuth] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  const title = useMemo(() => {
    return NAV.find((n) => n.href === pathname)?.label || "Overview";
  }, [pathname]);

  const subtitle = useMemo(() => {
    switch (pathname) {
      case "/held":
        return "Messages with no confident existing label";
      case "/needs-review":
        return "Medium-confidence predictions to confirm or change";
      case "/proposals":
        return "Suggested new categories awaiting approval";
      case "/taxonomy":
        return "Active labels used by the classifier";
      default:
        return "Sync mail and clear your review queues";
    }
  }, [pathname]);

  const refresh = useCallback(async () => {
    const [st, sum, who] = await Promise.all([
      api<Status>("/api/status").catch(() => null),
      api<Summary>("/api/review/summary").catch(() => null),
      api<Me>("/auth/me").catch(() => ({ authenticated: false })),
    ]);
    setStatus(st);
    setSummary(sum);
    setMe(who);
    setImgFailed(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [pathname, refresh]);

  async function signIn() {
    setBusyAuth(true);
    window.location.href = `${API_BASE}/auth/login`;
  }

  async function signOut() {
    setBusyAuth(true);
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
      setMe({ authenticated: false });
    } finally {
      setBusyAuth(false);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            TS
          </div>
          <div>
            <div className="brand-text">Tagsmith</div>
            <div className="brand-sub">Mail review</div>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          <div className="nav-label">Workspace</div>
          {NAV.map((item) => {
            const active = pathname === item.href;
            const badge =
              item.href === "/held"
                ? summary?.held
                : item.href === "/needs-review"
                  ? summary?.needs_review
                  : item.href === "/proposals"
                    ? summary?.proposals
                    : undefined;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-item active" : "nav-item"}
                aria-current={active ? "page" : undefined}
              >
                <span>{item.label}</span>
                {typeof badge === "number" && badge > 0 ? (
                  <span className="badge">{badge}</span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <label className="apply-row">
            <span>Write to Gmail</span>
            <input
              type="checkbox"
              checked={apply}
              onChange={(e) => setApply(e.target.checked)}
              aria-label="Write labels to Gmail"
            />
          </label>

          <div className={`pill ${status?.gmail_authenticated ? "ok" : "warn"}`}>
            <span className="dot" />
            {status?.gmail_authenticated ? "Gmail connected" : "Gmail token needed"}
          </div>
          {status?.enable_rag ? (
            <div className="pill">
              RAG {status.rag_example_count ?? 0} examples
              {status.background_sync ? " · auto" : ""}
            </div>
          ) : null}

          {me?.authenticated ? (
            <div className="account">
              <div className="account-row">
                <div className="avatar" aria-hidden>
                  {me.picture_url && !imgFailed ? (
                    <img
                      src={me.picture_url}
                      alt=""
                      referrerPolicy="no-referrer"
                      onError={() => setImgFailed(true)}
                    />
                  ) : (
                    initials(me.name, me.email)
                  )}
                </div>
                <div className="account-meta">
                  <div className="account-name">{displayName(me)}</div>
                  {displayName(me) !== me.email ? (
                    <div className="account-email" title={me.email}>
                      {me.email}
                    </div>
                  ) : (
                    <div className="account-email">{me.plan ? `${me.plan} plan` : "Signed in"}</div>
                  )}
                </div>
              </div>
              <button
                className="btn ghost block"
                type="button"
                onClick={() => void signOut()}
                disabled={busyAuth}
              >
                Sign out
              </button>
            </div>
          ) : (
            <button className="btn block" type="button" onClick={() => void signIn()} disabled={busyAuth}>
              Sign in with Google
            </button>
          )}
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1 className="page-title">{title}</h1>
            <p className="page-sub">{subtitle}</p>
          </div>
        </header>

        {!status?.gmail_authenticated && (
          <div className="banner warn" role="status">
            Run <code>uv run tagsmith auth</code> once so “Write to Gmail” can apply labels.
          </div>
        )}

        <div className="content">
          <ApplyBridge apply={apply} />
          {children}
        </div>
      </div>
    </div>
  );
}

function ApplyBridge({ apply }: { apply: boolean }) {
  useEffect(() => {
    window.localStorage.setItem("tagsmith_apply", apply ? "1" : "0");
    window.dispatchEvent(new CustomEvent("tagsmith-apply", { detail: apply }));
  }, [apply]);
  return null;
}

export function useApplyPreference(): boolean {
  const [apply, setApply] = useState(true);
  useEffect(() => {
    const read = () => setApply(window.localStorage.getItem("tagsmith_apply") !== "0");
    read();
    const onChange = (e: Event) => setApply(Boolean((e as CustomEvent).detail));
    window.addEventListener("tagsmith-apply", onChange);
    return () => window.removeEventListener("tagsmith-apply", onChange);
  }, []);
  return apply;
}
