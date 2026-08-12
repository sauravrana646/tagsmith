# Phase 5 — Product foundation (API & dashboard)

Status: **in progress on branch `feature/phase-4-5-ops-product`** (not merged until approved).

## Goal

Wrap the existing service layer with a FastAPI backend, web OAuth for the
operator, encrypted refresh tokens, a Next.js review dashboard, and billing
**hooks** — without rewriting classify/sync/review logic.

This is the **local / single-user product API**, not the public SaaS launch.
Hosted multi-tenant work lives in **Phase 6** — see [SAAS.md](SAAS.md).

## What’s included in this pass

| Area | Implementation |
|------|----------------|
| API | `tagsmith api` / `python -m tagsmith.api` |
| Review | `/api/review/*` (summary, held, proposals, assign/approve) |
| Sync | `/api/sync/run`, `/api/sync/state`, `/api/sync/watch/*` |
| Web OAuth | `/auth/login`, `/auth/callback`, `/auth/me` |
| Token crypto | Fernet via `TAGSMITH_TOKEN_ENCRYPTION_KEY` |
| Tenants | `tenants` table (`email`, encrypted refresh token, `plan`) |
| Billing hooks | `/api/billing/plans` + Stripe webhook receiver |
| Dashboard | `web/` Next.js scaffold |
| DB | SQLite default; optional Postgres URL for experiments |

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

## Deferred to Phase 6 (SaaS final)

- [ ] Google OAuth **sensitive-scope verification** (privacy policy, domain, demo video)
- [ ] Stripe Checkout UI + customer portal
- [ ] Per-tenant DB isolation / pgvector RAG migration
- [ ] Production Pub/Sub push → incremental sync
- [ ] Hosted deploy (API + web + Postgres)

## Privacy reminder

Email bodies are sensitive. Prefer zero-retention LLM providers before inviting
external users in Phase 6. See [PRIVACY.md](PRIVACY.md) and [SAAS.md](SAAS.md).
