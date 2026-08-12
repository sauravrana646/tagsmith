"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { API_BASE, api } from "@/lib/api";

type Status = {
  gmail_authenticated: boolean;
  gmail_detail: string;
  hint: string;
};

type Summary = { proposals: number; needs_review: number; held: number };

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/held", label: "Held" },
  { href: "/needs-review", label: "Needs review" },
  { href: "/proposals", label: "Proposals" },
  { href: "/taxonomy", label: "Taxonomy" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [status, setStatus] = useState<Status | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [apply, setApply] = useState(true);

  useEffect(() => {
    void api<Status>("/api/status").then(setStatus).catch(() => setStatus(null));
    void api<Summary>("/api/review/summary").then(setSummary).catch(() => setSummary(null));
  }, [pathname]);

  return (
    <div className="shell" data-apply={apply ? "on" : "off"}>
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">TS</div>
          <div>
            <strong>Tagsmith</strong>
            <div className="muted tiny">Review console</div>
          </div>
        </div>
        <nav className="nav">
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
              <Link key={item.href} href={item.href} className={active ? "nav-item active" : "nav-item"}>
                <span>{item.label}</span>
                {typeof badge === "number" ? <span className="badge">{badge}</span> : null}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <label className="apply-toggle">
            <input
              type="checkbox"
              checked={apply}
              onChange={(e) => setApply(e.target.checked)}
            />
            <span>Apply to Gmail</span>
          </label>
          <div className={`pill ${status?.gmail_authenticated ? "ok" : "warn"}`}>
            {status?.gmail_authenticated ? "Gmail ready" : "Gmail auth needed"}
          </div>
          <a className="muted tiny" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">
            API docs
          </a>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>
            <h1 className="page-title">Mailbox review</h1>
            <p className="muted tiny">
              {status?.hint || "Confirm, change, and approve labels without the CLI."}
            </p>
          </div>
          <div className="top-actions">
            <a className="btn ghost" href={`${API_BASE}/auth/debug`} target="_blank" rel="noreferrer">
              Auth debug
            </a>
            <a className="btn" href={`${API_BASE}/auth/login`}>
              Sign in
            </a>
          </div>
        </header>
        {!status?.gmail_authenticated && (
          <div className="banner warn">
            Desktop Gmail token missing. Run <code>uv run tagsmith auth</code> once so Apply
            can write labels. You can still browse queues without it.
          </div>
        )}
        <div className="content" data-apply={apply ? "true" : "false"}>
          {/* expose apply preference to child pages via DOM + localStorage */}
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
