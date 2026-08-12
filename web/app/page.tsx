"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApplyPreference } from "@/components/Shell";

type Summary = { proposals: number; needs_review: number; held: number };
type SyncResult = {
  run_id: number | null;
  dry_run: boolean;
  counts: Record<string, number>;
};

export default function OverviewPage() {
  const apply = useApplyPreference();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [limit, setLimit] = useState(25);
  const [incremental, setIncremental] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setSummary(await api<Summary>("/api/review/summary"));
  }

  useEffect(() => {
    void refresh().catch((e: Error) => setError(e.message));
  }, []);

  async function runSync(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api<SyncResult>("/api/sync/run", {
        method: "POST",
        body: JSON.stringify({
          limit,
          apply,
          incremental,
          reprocess: false,
        }),
      });
      setMessage(
        `${result.dry_run ? "Dry-run" : "Applied"} sync #${result.run_id ?? "—"} · ` +
          Object.entries(result.counts)
            .filter(([, v]) => v)
            .map(([k, v]) => `${k}=${v}`)
            .join(" · "),
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="grid">
        <div className="card">
          <h2>Held</h2>
          <div className="n">{summary?.held ?? "—"}</div>
        </div>
        <div className="card">
          <h2>Needs review</h2>
          <div className="n">{summary?.needs_review ?? "—"}</div>
        </div>
        <div className="card">
          <h2>Proposals</h2>
          <div className="n">{summary?.proposals ?? "—"}</div>
        </div>
      </div>

      <form className="panel" onSubmit={runSync}>
        <strong>Sync unread mail</strong>
        <p className="muted tiny">
          Pulls from Gmail using your desktop token, classifies, and{" "}
          {apply ? "applies labels" : "dry-runs only"}. Toggle Apply in the sidebar.
        </p>
        <div className="row">
          <label className="muted tiny">
            Limit{" "}
            <input
              className="input"
              type="number"
              min={1}
              max={200}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
          </label>
          <label className="apply-toggle" style={{ padding: "0.45rem 0.7rem" }}>
            <input
              type="checkbox"
              checked={incremental}
              onChange={(e) => setIncremental(e.target.checked)}
            />
            Incremental (historyId)
          </label>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Running…" : apply ? "Sync & apply" : "Sync dry-run"}
          </button>
        </div>
        {message && <div className="success">{message}</div>}
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}
