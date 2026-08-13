# Phase 6 — Decision: not a consumer product

Status: **dropped as an active goal.** Tagsmith stays a **local tool for people
who can follow [SETUP.md](SETUP.md)** (CLI, their Google OAuth client, their
LLM key). We are **not** building a product for “normal people.”

Related: [PRIVACY.md](PRIVACY.md), [PRODUCT.md](PRODUCT.md), [PLAN.md](PLAN.md).

## What we are *not* doing

These were explored and rejected as too much for non-technical users (and too
heavy for a solo operator):

| Dropped | Why |
|---------|-----|
| Public hosted SaaS (“Sign in with Google” on our servers) | We would hold mail-derived data, Google verification, DPDP/GDPR as a processor, payments, refunds |
| Desktop installer + wizard for non-tech | Still needs *our* OAuth client (Google verification) and a bundled LLM; installers/support are a real product org |
| Stripe / Link / worldwide card checkout | Invite-only business KYC; not a solo individual path |
| Selling to people who cannot create a GCP OAuth client and paste an API key | That customer needs Superhuman-class UX, not this repo |

“We only label mail” does not make GCP + Python + keys easy. Hiding that setup
turns the project into a consumer Gmail app. **Out of scope.**

## What Tagsmith *is*

- Local CLI + optional local dashboard on **the operator’s machine**
- **Their** `credentials.json` + `tagsmith auth`
- **Their** LLM key in `.env`
- Dry-run by default; labels under `AI/`
- Background RAG catch-up when *they* leave `tagsmith api` / `schedule` running

Audience: **you**, and other technical operators. Not a mass-market inbox app.

Charge for IP only if someone like that wants a license later (PayPal invoice,
no consumer refund theatre). Default: **don’t commercialize** until the local
product is something *you* use daily.

## What to do instead of Phase 6

1. Merge Phase 4+5 when ready ([PR](https://github.com/sauravrana646/tagsmith/pull/6) still draft).
2. Dogfood on **your** Mac: `tagsmith auth`, dashboard, Sync, review queues.
3. Improve the **technical** setup path (SETUP/USAGE), not a consumer wizard.
4. Leave hosted SaaS and desktop-for-everyone **parked** (appendix below).

No Google sensitive-scope verification, no PayPal subscriptions, no Pub/Sub
hosting, no “make it easy for my parents.”

---

## Appendix — parked hosted-SaaS notes (do not implement)

Kept so we don’t re-litigate if a future operator *with a company* wants SaaS.
Not a backlog.

- Operator in India, worldwide users, no Pvt Ltd was assumed for v1.
- Pricing sketch: CLI free; hosted Pro **$12/mo**; 7-day refund **only if we
  failed** (not after labels applied).
- Payments sketch: **PayPal** invoices first; Wise for bank invoices (weak
  refunds); Razorpay/Paddle later; **not** Stripe.
- Legal sketch: Google Limited Use + DPDP + GDPR if we hosted mail; body TTL;
  zero-retention LLM; disconnect/delete.
- Full write-up lived in git history on `docs/PHASE6.md` before this decision
  (commit before “not a consumer product”).
