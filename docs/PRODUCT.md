# Phase 5 — Product foundation (API & dashboard)

Status: **in progress on branch `feature/phase-4-5-ops-product`** (not merged until approved).

## Goal

Wrap the existing service layer with a FastAPI backend, web OAuth for the
operator, encrypted refresh tokens, a Next.js review dashboard, and billing
**hooks** — without rewriting classify/sync/review logic.

This is the **operator dogfood API** (local). The **customer product** is hosted
SaaS in Phase 6 — see [PHASE6.md](PHASE6.md). Customers will not install this.

## What’s included in this pass

| Area | Implementation |
|------|----------------|
| API | `tagsmith api` / `python -m tagsmith.api` |
| Review UI | SaaS-style console: Overview, Held, Needs review, Proposals, Taxonomy |
| Review API | summary/list + assign/propose/confirm/change/approve/reject |
| Sync UI/API | Run incremental/full sync from Overview (`Apply to Gmail` toggle) |
| Status | `/api/status` — desktop Gmail token, RAG example count, background sync |
| Taxonomy | `/api/taxonomy/labels` |
| Web OAuth | `/auth/login`, `/auth/callback`, `/auth/me` (optional for local UI) |
| Token crypto | Fernet via `TAGSMITH_TOKEN_ENCRYPTION_KEY` |
| Tenants | `tenants` table (`email`, encrypted refresh token, `plan`) |
| Billing hooks | `/api/billing/plans` + Stripe webhook receiver |
| Dashboard | `web/` Next.js app |
| DB | SQLite default; optional Postgres URL for experiments |

## Local run

```bash
# one-time Gmail desktop auth (needed for Apply / Sync from UI)
uv run tagsmith auth

# API
uv sync --group product   # optional: stripe + psycopg
export TAGSMITH_TOKEN_ENCRYPTION_KEY='dev-only-change-me'
export TAGSMITH_WEB_APP_URL=http://127.0.0.1:3000
uv run tagsmith api

# Dashboard (separate terminal)
cd web && npm install && npm run dev
# open http://127.0.0.1:3000
# if port 3000 is busy: npm run dev:3001  and set TAGSMITH_WEB_APP_URL=http://127.0.0.1:3001
```

After Google login, the API redirects to `TAGSMITH_WEB_APP_URL` (default `http://127.0.0.1:3000`), not the API root.

**UI Apply toggle defaults ON** — mutations write Gmail labels using your desktop token from `tagsmith auth`. Turn it off for dry-run.

Dry-run remains the default on mutating endpoints (`apply=false`).

## Phase 6 (customer product)

The **customer** product is hosted SaaS (browser, our Google OAuth, our LLM).
Local CLI is **not** shipped to customers. Plan: [PHASE6.md](PHASE6.md).

Desktop installers and BYOK “run it on their PC” are **dropped**.

## Privacy reminder

Email bodies are sensitive. Prefer zero-retention LLM providers. See
[PRIVACY.md](PRIVACY.md).
