"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { api } from "@/lib/api";
import { useApplyPreference } from "@/components/Shell";

type Label = { key: string; description: string };
type Held = {
  gmail_id: string;
  subject: string;
  sender: string;
  predicted_key: string | null;
  proposed_key: string | null;
  proposed_description: string | null;
  rationale: string;
  body_excerpt: string;
};

export default function HeldPage() {
  const apply = useApplyPreference();
  const [items, setItems] = useState<Held[]>([]);
  const [labels, setLabels] = useState<Label[]>([]);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [held, labs] = await Promise.all([
      api<Held[]>("/api/review/held"),
      api<Label[]>("/api/taxonomy/labels"),
    ]);
    setItems(held);
    setLabels(labs);
    const init: Record<string, string> = {};
    for (const h of held) {
      init[h.gmail_id] = h.proposed_key || h.predicted_key || labs[0]?.key || "";
    }
    setSelected(init);
  }

  useEffect(() => {
    void load().catch((e: Error) => setError(e.message));
  }, []);

  async function assign(gmailId: string) {
    setBusy(gmailId);
    setError(null);
    try {
      await api(`/api/review/held/${gmailId}/assign`, {
        method: "POST",
        body: JSON.stringify({ label_key: selected[gmailId], apply }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assign failed");
    } finally {
      setBusy(null);
    }
  }

  async function proposeNew(item: Held) {
    const key = window.prompt("New label key (kebab-case)", item.proposed_key || "new-category");
    if (!key) return;
    const description =
      window.prompt("Description", item.proposed_description || item.rationale || key) || key;
    setBusy(item.gmail_id);
    setError(null);
    try {
      await api(`/api/review/held/${item.gmail_id}/propose`, {
        method: "POST",
        body: JSON.stringify({
          suggested_key: key,
          description,
          why: item.rationale || description,
          apply,
        }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Propose failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        Held messages had no confident existing label. File under an existing category or create a
        new one. Apply is {apply ? "ON" : "OFF"}.
      </p>
      {error && <div className="error">{error}</div>}
      {items.length === 0 && (
        <EmptyState
          title="No held messages"
          body="Held items show up after sync when nothing in the taxonomy fits confidently. Sync unread mail from Overview."
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
              {item.proposed_key && <span className="chip accent">proposed {item.proposed_key}</span>}
              <span className="chip">{item.gmail_id.slice(0, 10)}…</span>
            </div>
          </div>
          <div className="muted tiny">{item.body_excerpt || item.rationale}</div>
          <div className="actions">
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
              className="btn ok"
              disabled={busy === item.gmail_id}
              onClick={() => void assign(item.gmail_id)}
            >
              File under existing
            </button>
            <button
              className="btn ghost"
              disabled={busy === item.gmail_id}
              onClick={() => void proposeNew(item)}
            >
              Create new category
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
