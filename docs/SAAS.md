# Phase 6 — SaaS (final)

Status: **planned** — deferred until Phase 4+5 foundations merge and dogfood.

## Goal

Turn the local/API product into a **hosted multi-tenant SaaS**: always-on inbox
automation, public Google OAuth, paid plans, and isolated per-tenant RAG.

Phase 4+5 deliberately stop short of these so the learning path and local product
stay shippable without cloud spend or Google verification paperwork.

## In scope (final phase only)

| Item | What it unlocks |
|------|-----------------|
| **Hosted Pub/Sub push** | Near-real-time sync when Gmail changes (HTTPS push → incremental sync) |
| **Stripe Checkout UI + customer portal** | Self-serve upgrade/cancel; webhook already can update `tenants.plan` |
| **Google sensitive-scope verification** | Public users can OAuth without “unverified app” friction |
| **Postgres + pgvector multi-tenant RAG** | Scalable, isolated few-shots per customer (no cross-tenant leakage) |
| **Production deploy** | Hosted API + web + DB + secrets + privacy policy URL |

## Explicitly not Phase 4/5

| Phase | Owns instead |
|-------|----------------|
| 4 | Local `historyId` incremental sync, watch lease CLI, scheduler **polling**, MCP |
| 5 | FastAPI, web OAuth (test users), encrypted tokens, dashboard scaffold, billing **hooks** |

## Cost note

Mostly engineering/calendar time. Cash cost is low until you host infra or take
payments (Stripe fees on charges; Postgres hosting; optional embedding APIs).
Google sensitive-scope verification itself is **free** — do not add restricted
`mail.google.com` scope.

## Exit criteria

- [ ] Public HTTPS deploy with Pub/Sub push → `sync_incremental`
- [ ] Stripe Checkout + portal wired to plans
- [ ] Google OAuth verification approved (privacy policy, domain, demo video)
- [ ] Multi-tenant Postgres + pgvector RAG with tenant isolation
- [ ] Published data policy / PRIVACY updates for SaaS
