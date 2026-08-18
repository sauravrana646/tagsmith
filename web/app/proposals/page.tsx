"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { api } from "@/lib/api";
import { useApplyPreference } from "@/components/Shell";

type Label = { key: string; description: string };
type Proposal = {
  id: number;
  gmail_id: string;
  suggested_key: string;
  description: string;
  rationale: string;
  why_no_existing_fit: string;
  subject: string;
  sender: string;
  body_excerpt: string;
};

export default function ProposalsPage() {
  const apply = useApplyPreference();
  const [items, setItems] = useState<Proposal[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [rows, labs] = await Promise.all([
      api<Proposal[]>("/api/review/proposals"),
      api<Label[]>("/api/taxonomy/labels"),
    ]);
    setItems(rows);
    setLabels(labs);
    const init: Record<number, string> = {};
    for (const row of rows) init[row.id] = labs[0]?.key || "";
    setSelected(init);
  }

  useEffect(() => {
    void load().catch((e: Error) => setError(e.message));
  }, []);

  async function approve(id: number) {
    setBusy(id);
    setError(null);
    try {
      await api(`/api/review/proposals/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ apply }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    } finally {
      setBusy(null);
    }
  }

  async function reject(id: number) {
    setBusy(id);
    setError(null);
    try {
      await api(`/api/review/proposals/${id}/reject`, { method: "POST", body: "{}" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusy(null);
    }
  }

  async function assignExisting(id: number) {
    setBusy(id);
    setError(null);
    try {
      await api(`/api/review/proposals/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ label_key: selected[id], apply }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assign failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        New category proposals. Approve creates the Gmail label and reclassifies remaining held
        mail.
      </p>
      {error && <div className="error">{error}</div>}
      {items.length === 0 && (
        <EmptyState
          title="No pending proposals"
          body="Proposals appear after sync when the model suggests a new category. Run a sync from Overview first."
        />
      )}
      {items.map((item) => (
        <article className="item" key={item.id}>
          <div className="item-head">
            <div>
              <h3 className="item-title">{item.subject || "(no subject)"}</h3>
              <div className="muted tiny">{item.sender}</div>
            </div>
            <div className="meta">
              <span className="chip accent">#{item.id}</span>
              <span className="chip accent">{item.suggested_key}</span>
            </div>
          </div>
          <div className="muted tiny">{item.description}</div>
          <div className="muted tiny">{item.body_excerpt || item.rationale}</div>
          <div className="actions">
            <button
              className="btn ok"
              disabled={busy === item.id}
              onClick={() => void approve(item.id)}
            >
              Approve new category
            </button>
            <select
              className="select"
              value={selected[item.id] || ""}
              onChange={(e) => setSelected((s) => ({ ...s, [item.id]: e.target.value }))}
            >
              {labels.map((l) => (
                <option key={l.key} value={l.key}>
                  {l.key}
                </option>
              ))}
            </select>
            <button
              className="btn ghost"
              disabled={busy === item.id}
              onClick={() => void assignExisting(item.id)}
            >
              Use existing instead
            </button>
            <button
              className="btn danger"
              disabled={busy === item.id}
              onClick={() => void reject(item.id)}
            >
              Reject
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
