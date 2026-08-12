# Phase 5 — Product API & dashboard

Status: **in progress on branch `feature/phase-4-5-ops-product`** (not merged until approved).

## Goal

Wrap the existing service layer with a FastAPI backend, web OAuth, encrypted
tenant refresh tokens, a Next.js review dashboard, and billing hooks — without
rewriting classify/sync/review logic.

## What’s included in this pass

| Area | Implementation |
|------|----------------|
| API | `tagsmith api` / `python -m tagsmith.api` |
| Review | `/api/review/*` (summary, held, proposals, assign/approve) |
| Sync | `/api/sync/run`, `/api/sync/state`, `/api/sync/watch/*` |
| Web OAuth | `/auth/login`, `/auth/callback`, `/auth/me` |
| Token crypto | Fernet via `TAGSMITH_TOKEN_ENCRYPTION_KEY` |
| Tenants | `tenants` table (`email`, encrypted refresh token, `plan`) |
| Billing | `/api/billing/plans` + Stripe webhook receiver |
| Dashboard | `web/` Next.js static export (optional `web/out`) |
| Postgres | `TAGSMITH_DATABASE_URL=postgresql+psycopg://...` (+ `uv sync --group product`) |

## Local run

```bash
# API
uv sync --group product   # optional: stripe + psycopg
export TAGSMITH_TOKEN_ENCRYPTION_KEY='dev-only-change-me'
uv run tagsmith api

# Dashboard (separate terminal)
cd web && npm install && npm run dev
# open http://127.0.0.1:3000
```

Dry-run remains the default on mutating endpoints (`apply=false`).

## Still open (post-merge hardening)

- [ ] Google OAuth **sensitive-scope verification** (privacy policy, domain, demo video)
- [ ] Stripe Checkout UI + customer portal
- [ ] Per-tenant DB isolation / pgvector RAG migration
- [ ] Production Pub/Sub push → incremental sync
- [ ] Hosted deploy (API + web + Postgres)

## Privacy reminder

Email bodies are sensitive. Prefer zero-retention LLM providers for SaaS,
encrypt tokens at rest, and publish a plain-language data policy before inviting
external users. See [PRIVACY.md](PRIVACY.md).
