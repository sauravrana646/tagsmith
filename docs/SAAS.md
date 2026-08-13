# Phase 6 — SaaS (pointer)

Status: **planned**. The full plan (product slices, India/solo operator, PayPal
not Stripe, refunds, $12 Pro, DPDP/GDPR/Google, retention) lives in:

**[PHASE6.md](PHASE6.md)**

Do not start until Phase 4+5 merge and dogfood. Short summary:

| Item | v1 choice |
|------|-----------|
| Hosted always-on + verified OAuth | Yes |
| Payments | PayPal invoices first — **not** Stripe/Link |
| Price | CLI free; hosted Pro **$12/mo**; 7-day **conditional** refund |
| Entity | No Pvt Ltd required for v1 (solo / sole prop) |
| Scopes | `gmail.modify` + `gmail.labels` only (no CASA) |
