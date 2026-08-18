"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { api } from "@/lib/api";
import { useApplyPreference } from "@/components/Shell";

type Label = { key: string; description: string };
type Item = {
  gmail_id: string;
  subject: string;
  sender: string;
  predicted_key: string | null;
  confidence: number | null;
  rationale: string;
  body_excerpt: string;
};

export default function NeedsReviewPage() {
  const apply = useApplyPreference();
  const [items, setItems] = useState<Item[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [rows, labs] = await Promise.all([
      api<Item[]>("/api/review/needs-review"),
      api<Label[]>("/api/taxonomy/labels"),
    ]);
    setItems(rows);
    setLabels(labs);
    const init: Record<string, string> = {};
    for (const row of rows) init[row.gmail_id] = row.predicted_key || labs[0]?.key || "";
    setSelected(init);
  }

  useEffect(() => {
    void load().catch((e: Error) => setError(e.message));
  }, []);

  async function confirm(gmailId: string) {
    setBusy(gmailId);
    setError(null);
    try {
      await api(`/api/review/needs-review/${gmailId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ apply }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Confirm failed");
    } finally {
      setBusy(null);
    }
  }

  async function change(gmailId: string) {
    setBusy(gmailId);
    setError(null);
    try {
      await api(`/api/review/needs-review/${gmailId}/change`, {
        method: "POST",
        body: JSON.stringify({ label_key: selected[gmailId], apply }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Change failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        Medium-confidence labels. Confirm the prediction or change to another taxonomy key.
      </p>
      {error && <div className="error">{error}</div>}
      {items.length === 0 && (
        <EmptyState
          title="Nothing needs review"
          body="Medium-confidence labels land here after sync. Go to Overview and run Sync to classify unread mail."
        />
      )}
      {items.map((item) => (
        <article className="item" key={item.gmail_id}>
          <div className="item-head">
            <div>
              <h3 className="item-title">{item.subject || "(no subject)"}</h3>
              <div className="muted tiny">{item.sender}</div>
            </div>
            <div className="meta">
              <span className="chip accent">{item.predicted_key || "—"}</span>
              <span className="chip">
                conf {item.confidence == null ? "n/a" : item.confidence.toFixed(2)}
              </span>
            </div>
          </div>
          <div className="muted tiny">{item.body_excerpt || item.rationale}</div>
          <div className="actions">
            <button
              className="btn ok"
              disabled={busy === item.gmail_id}
              onClick={() => void confirm(item.gmail_id)}
            >
              Confirm
            </button>
            <select
              className="select"
              value={selected[item.gmail_id] || ""}
              onChange={(e) => setSelected((s) => ({ ...s, [item.gmail_id]: e.target.value }))}
            >
              {labels.map((l) => (
                <option key={l.key} value={l.key}>
                  {l.key}
                </option>
              ))}
            </select>
            <button
              className="btn ghost"
              disabled={busy === item.gmail_id}
              onClick={() => void change(item.gmail_id)}
            >
              Change label
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
