"use client";

import Link from "next/link";

export function EmptyState({
  title,
  body,
  actionHref = "/",
  actionLabel = "Go to Overview & sync",
}: {
  title: string;
  body: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      <p className="empty-body">{body}</p>
      <Link className="btn" href={actionHref}>
        {actionLabel}
      </Link>
    </div>
  );
}
