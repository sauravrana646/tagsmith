"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, api } from "@/lib/api";

type Status = {
  gmail_authenticated: boolean;
  gmail_detail: string;
  hint: string;
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
  const parts = src.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<Status | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [apply, setApply] = useState(true);
  const [busyAuth, setBusyAuth] = useState(false);

  const title = useMemo(() => {
    return NAV.find((n) => n.href === pathname)?.label || "Overview";
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
  }, []);

  useEffect(() => {
    void refresh();
  }, [pathname, refresh]);

  async function signIn() {
    setBusyAuth(true);
    // /auth/login skips Google when a valid session cookie already exists.
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
          <div className="brand-mark">TS</div>
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
                {typeof badge === "number" ? <span className="badge">{badge}</span> : null}
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

          {me?.authenticated ? (
            <div className="account" title={me.email}>
              <div className="avatar" aria-hidden>
                {me.picture_url ? (
                  <img src={me.picture_url} alt="" referrerPolicy="no-referrer" />
                ) : (
                  initials(me.name, me.email)
                )}
              </div>
              <div className="account-meta">
                <div className="account-name">{me.name || "Signed in"}</div>
                <div className="account-email">{me.email}</div>
              </div>
              <div className="account-actions">
                <button className="btn linkish" type="button" onClick={() => void signOut()} disabled={busyAuth}>
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <button className="btn" type="button" onClick={() => void signIn()} disabled={busyAuth}>
              Sign in with Google
            </button>
          )}
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1 className="page-title">{title}</h1>
            <p className="page-sub">
              {me?.authenticated
                ? `Signed in as ${me.email}`
                : "Review and apply labels without the CLI"}
            </p>
          </div>
          <div className="top-actions">
            {!me?.authenticated && (
              <button className="btn ghost" type="button" onClick={() => void signIn()} disabled={busyAuth}>
                Sign in
              </button>
            )}
          </div>
        </header>

        {!status?.gmail_authenticated && (
          <div className="banner warn" role="status">
            Run <code>uv run tagsmith auth</code> once so “Write to Gmail” can apply labels. Browsing
            queues still works.
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
