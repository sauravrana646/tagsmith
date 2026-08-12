"use client";

import { useEffect, useState } from "react";

type Summary = { proposals: number; needs_review: number; held: number };
type Held = {
  gmail_id: string;
  subject: string;
  sender: string;
  predicted_key: string | null;
  proposed_key: string | null;
  rationale: string;
};

const API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8080";

export default function HomePage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [held, setHeld] = useState<Held[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [s, h] = await Promise.all([
          fetch(`${API}/api/review/summary`, { credentials: "include" }).then((r) => {
            if (!r.ok) throw new Error(`summary ${r.status}`);
            return r.json();
          }),
          fetch(`${API}/api/review/held`, { credentials: "include" }).then((r) => {
            if (!r.ok) throw new Error(`held ${r.status}`);
            return r.json();
          }),
        ]);
        setSummary(s);
        setHeld(h);
      } catch (err) {
        setError(
          err instanceof Error
            ? `${err.message}. Start the API with \`uv run tagsmith api\` and allow CORS/local access.`
            : "failed to load",
        );
      }
    }
    void load();
  }, []);

  return (
    <>
      <h1>Review queue</h1>
      <p className="muted">
        Human gate for held messages and proposals. Mutations stay dry-run unless the API is
        called with <code>apply=true</code>.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="grid">
        <div className="card">
          <h2>Proposals</h2>
          <div className="n">{summary?.proposals ?? "—"}</div>
        </div>
        <div className="card">
          <h2>Needs review</h2>
          <div className="n">{summary?.needs_review ?? "—"}</div>
        </div>
        <div className="card">
          <h2>Held</h2>
          <div className="n">{summary?.held ?? "—"}</div>
        </div>
      </div>
      <section className="list">
        <h2>Held messages</h2>
        {held.length === 0 && <p className="muted">No held messages (or API offline).</p>}
        {held.map((item) => (
          <article className="item" key={item.gmail_id}>
            <div>
              <strong>{item.subject || "(no subject)"}</strong>
            </div>
            <div className="muted">{item.sender}</div>
            <div>
              predicted <code>{item.predicted_key ?? "null"}</code>
              {item.proposed_key ? (
                <>
                  {" "}
                  · proposed <code>{item.proposed_key}</code>
                </>
              ) : null}
            </div>
            <div className="muted">{item.rationale}</div>
          </article>
        ))}
      </section>
    </>
  );
}
