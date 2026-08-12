"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Label = {
  key: string;
  description: string;
  gmail_label: string;
  gmail_label_id: string | null;
};

export default function TaxonomyPage() {
  const [labels, setLabels] = useState<Label[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api<Label[]>("/api/taxonomy/labels")
      .then(setLabels)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="stack">
      <p className="muted">Active taxonomy keys used by the classifier and review UI.</p>
      {error && <div className="error">{error}</div>}
      <div className="stack">
        {labels.map((label) => (
          <article className="item" key={label.key}>
            <div className="item-head">
              <h3 className="item-title">{label.key}</h3>
              <span className="chip">{label.gmail_label}</span>
            </div>
            <div className="muted tiny">{label.description}</div>
          </article>
        ))}
      </div>
    </div>
  );
}
