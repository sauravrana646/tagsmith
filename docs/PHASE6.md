# Phase 6 — Hosted SaaS plan

Status: **planned**. Do not start until Phase 4+5 are merged to `main` and dogfooded
on a real inbox. This document is the Phase 6 product, legal, payments, and
privacy plan.

**Not legal, tax, or FEMA advice.** Use a CA for GST/inward remittance and a
lawyer for privacy policies and Google verification. Laws and processor rules
change; re-check Stripe/PayPal/Wise/Razorpay/Paddle and DPDP dates before launch.

Related: [PRIVACY.md](PRIVACY.md), [PRODUCT.md](PRODUCT.md), [OPS.md](OPS.md),
[PLAN.md](PLAN.md). Short pointer: [SAAS.md](SAAS.md).

## Goal

Turn the local CLI + dashboard into an optional **hosted product**: always-on
labeling, public Google sign-in (verified), paid Pro, tenant-isolated data.

The **local CLI stays free**. Hosting, Google verification, and payments are
what Phase 6 sells.

“We only apply labels and do not read full mail” is the **product story**. It
does **not** mean we are outside privacy law. We still access Gmail, send a
truncated body to an LLM, and store decisions.

## Operator assumptions (locked for this plan)

| Assumption | Choice |
|------------|--------|
| Operator location | **India** |
| Customers | **Worldwide** (self-serve + invoiced) |
| Company form | **No Pvt Ltd** for v1. Solo / sole proprietor / freelancer |
| Local product | Free forever (`tagsmith` CLI on the user’s machine) |
| Paid product | **Hosted** mailbox automation only |

A Pvt Ltd is **not required** to label mail or to invoice a few foreign
clients. It **is** required (or strongly expected) for Stripe India and for
many bank/enterprise contracts. This plan does **not** depend on Stripe or a
Pvt Ltd for the first paid slice.

## What Phase 4/5 already own (do not rebuild)

| Phase | Owns |
|-------|------|
| 4 | `historyId` incremental sync, watch helpers, scheduler **polling**, MCP, RAG catch-up |
| 5 | FastAPI, web OAuth (test users), Fernet tokens, dashboard, `/api/billing/plans` hooks |

Phase 6 adds **public HTTPS**, **verified OAuth**, **real payments + refunds**,
**Pub/Sub push**, **Postgres + isolated RAG**, and **published legal pages**.

## In scope

| Item | Unlocks |
|------|---------|
| Production deploy | Users are not on `127.0.0.1` |
| Google sensitive-scope verification | Strangers can sign in without “unverified app” |
| Payments (PayPal first, not Stripe) | Charge Pro; issue refunds |
| Hosted Pub/Sub push | Sync when Gmail changes without a laptop process |
| Postgres + per-tenant RAG | No cross-customer few-shots |
| Data TTL, delete/disconnect | DPDP / GDPR / Google Limited Use |
| Privacy, terms, Limited Use pages | Verification + worldwide users |

## Out of scope (v1)

- Restricted Gmail scope `https://mail.google.com/` (triggers **paid CASA**)
- Claiming HIPAA, “bank-grade”, or “GDPR certified”
- Children / under-18 product
- Stripe Checkout / Stripe Link (India: invite-only, **not** a plain individual)
- SOC 2, ISO 27001 (later, if an enterprise deal requires them)
- Fine-tuning a shared model on customer mail

---

## 1. Product slices (build order)

Do **not** start with Stripe or Pub/Sub.

1. Merge/dogfood Phase 4+5.
2. Domain + HTTPS + privacy / terms / Limited Use.
3. Stop long-term full-body storage; zero-retention LLM; delete/disconnect.
4. Tenant-isolated Postgres (even if still hashing embedder).
5. Google OAuth verification packet (policy + demo video).
6. PayPal invoicing + 7-day conditional refund + Pro entitlements.
7. Pub/Sub push → existing `sync_incremental`.
8. Optional later: Razorpay or Paddle for a subscribe button; pgvector if hashing
   is not enough.

### Hosted vs local

| | Local CLI | Hosted Pro |
|--|-----------|------------|
| Price | $0 | **$12 / month** (see pricing) |
| Auth | `tagsmith auth` desktop token | Web OAuth |
| Sync | User’s machine / `schedule` | Server + Pub/Sub |
| Data | User’s SQLite | Our Postgres, TTL’d |

---

## 2. Pricing

Charge **per mailbox**, not per label. One **USD** price worldwide in v1
(no INR storefront unless Indian UPI volume appears).

| Plan | Price | Limits |
|------|--------|--------|
| Local CLI | $0 | Unlimited on their machine |
| Hosted Free | $0 | **50** classified messages / day (trial dashboard) |
| **Pro** | **$12 / month** | Always-on, **2,000** / day, background sync, RAG |
| Pro annual (optional) | **$99 / year** | Same as Pro (~2 months free) |

Do **not** offer lifetime. Do **not** start at $4 (support + disputes eat it)
or $29+ (unverified solo Gmail app). Raise later if people stay.

Matches current `/api/billing/plans` stub (`free` 50/day, `pro` $12 / 2000 day).

**Unit economics (sanity):** rules should catch most mail; LLM (e.g. DeepSeek)
on the tail is cheap vs $12. PayPal takes ~5–8%. Keep headroom.

---

## 3. Refunds

**Offer a refund.** “No refunds” on a Gmail product pushes **PayPal disputes**,
which cost more than a 7-day refund. Do **not** offer a no-questions 30-day
refund: labels are delivered on first successful sync.

### Policy (publish in terms + pay page)

- **7 days from first payment**, **once**, if **we** failed: could not connect,
  did not apply labels, or the product was broken.
- After a **successful sync that applied labels**, refund is **none**
  (service already performed). Cancel anytime = no further charges.
- Refund includes **disconnect Google** and **delete hosted data**.
- PayPal **does not return** their fee; operator absorbs it.
- Indian customers who paid UPI/bank: refund on the **same rail**.

### Operations

- Keep a **7-day cash buffer** (India rails auto-convert to INR immediately).
- Refund **only** via the original processor (PayPal refund button, etc.).
  Never “I’ll UPI a US customer.”
- Chargebacks: worse than voluntary refunds; policy helps little. Still refund
  promptly if the product failed.

EU-style cooling-off for digital services is typically **lost** once the user
agrees to start immediately — connecting Gmail is that start. State that in
terms.

If we **never charge** (CLI / test users only), skip refunds entirely.

---

## 4. Payments (no Stripe v1)

**Stripe Link / Checkout** needs a Stripe **business** account. Stripe India is
**invite-only** and **not for a plain individual**. Out of v1.

### v1: PayPal

- PAN + Indian bank + purpose code (IT / software services).
- Invoice or PayPal request/link for **foreign** customers.
- India→India PayPal **does not work** (since 2021). Indian customers: **UPI /
  bank transfer** on a GST/invoice.
- Auto-withdraw to INR; weekly digital FIRA (batch, not always per-invoice).
- **Refunds work** in the PayPal dashboard (original method).

### Also available, not default

| Rail | Use when | Refunds |
|------|----------|---------|
| **Wise freelancer** | A company pays an **invoice** (ACH/SWIFT to Wise details) | **Weak** from India (outbound often paused). Do not promise card-like refunds. |
| **Razorpay** international / payment links | Want cards + e-FIRC; usually **sole prop / GST / Udyam** | Dashboard refund. Closest Stripe-like UX without Stripe. |
| **Paddle** (Merchant of Record) | Real worldwide **Subscribe** button; they handle VAT | They refund; they are the seller. Higher cut. Best next step after PayPal. |

**Do not use:** personal GPay/UPI for foreigners; Wise as the only rail if the
site advertises refunds.

### India tax still applies if we earn

- Income tax on receipts (freelancer / professional income).
- **GST** if turnover crosses the threshold (~₹20 lakh; lower in some states):
  **18%** on Indian clients; **LUT** + zero-rated **export of services** for
  foreign clients **only if** supplier in India, recipient outside India, place
  of supply outside, **payment in convertible forex**, not merely an Indian
  establishment of the same entity.
- A US client paying **INR from an Indian account** is **not** an export.
- IEC: optional for many service exports; get it if using Amex or FTP benefits.
- Keep invoices + FIRA/FIRC; CA reconciles PayPal weekly FIRA vs invoices.

Wise/PayPal inbound for Indian residents typically **auto-converts to INR**
(no holding USD). Per-transfer Wise inbound cap is on the order of **₹25 lakh**.

---

## 5. Legal entity (no Pvt Ltd)

| Path | What it allows | What it blocks |
|------|----------------|----------------|
| **Personal / test users only** | CLI + Google Testing mode (~100 test users). No GST, no PayPal needed | No public OAuth, no strangers, no ads |
| **Solo + PayPal invoices** | Charge a few foreign clients | No Stripe; Google still needs verification for public sign-in |
| **Sole prop (Udyam / GST)** | Razorpay, LUT, cleaner FIRC | Still not a Pvt Ltd; some enterprises will refuse |
| **Pvt Ltd** | Stripe invite, banks, Google “who we are”, contracts | Explicitly **out of v1** by operator choice |

Public **worldwide self-serve cards** without any registered business is how
accounts get frozen. v1 stays **invoiced PayPal + test users** until
verification + a processor that accepts the operator’s KYC.

Governing law in terms: **India**. Large EU/US buyers may demand their law
later.

---

## 6. Privacy, retention, masking

Existing local hard rules stay ([PRIVACY.md](PRIVACY.md)):

- Never mark read; never archive / strip `INBOX`.
- Labels only, nested under `AI/`.
- Scopes: `gmail.modify` + `gmail.labels` only.
- Body cap **2000** chars; digit runs **≥ 9** → `[REDACTED]`.
- No attachment **bytes** (filenames only).
- App name **Tagsmith** (no “Gmail” in the name).

### Hosted retention

| Data | Keep? | Retention |
|------|--------|-----------|
| Encrypted refresh token | While connected | Delete on disconnect / account delete |
| Gmail id, label, confidence, rationale | Audit | 30–90 days default, or until user deletes |
| Subject / sender | Minimize | Same as audit; hash in logs |
| Body / `payload_json` | **No long-term** | Review excerpt TTL **7–14 days**, then drop |
| RAG | Embedding + hash preferred; short excerpt if needed | Delete with tenant; **never** mix tenants |
| Full MIME / HTML / attachments | Never | Already forbidden |
| LLM prompts | Provider **zero retention / no training** | Do not log raw prompts |
| Billing email, PayPal txn ids | Yes | Account life + tax records (CA: often ~7 years) |
| Server logs | Metadata only | 14–30 days |

### Masking / logs

- Keep digit redaction + truncation.
- Redact emails, `Authorization`, tokens in logs.
- No subjects/bodies in Sentry/Logfire by default.
- Review UI: short excerpt only after TTL.

**LLM:** only vendors with contractual **zero-retention / no-training**. If they
train on API data, do not use them in Phase 6.

---

## 7. Security (before first public user)

- HTTPS; cookies `Secure` + `HttpOnly` + `SameSite` (no local HTTP exception).
- Encrypt refresh tokens per tenant (Fernet is a start; KMS/envelope later).
- Postgres: encryption at rest; **`tenant_id` on every mail/RAG row**.
- Secrets in a vault; Gitleaks `quality-gate` stays required.
- Separate prod vs staging OAuth clients.
- Pub/Sub push: verify Google/OIDC; do not trust raw POST bodies.
- Auth + rate limits on mutating routes.
- Encrypted backups; TTL aligned with retention; restore tested.
- Admin: 2FA; no casual prod DB from laptops.
- Incident: revoke Google tokens, rotate keys; if EU personal data involved,
  think **72 hours**. DPDP expects Board **and** user notice on breach
  (stricter than GDPR’s risk-based 72h).

---

## 8. International + Indian compliance

Design once to the **strictest overlap**: **Google Limited Use ∩ DPDP ∩ GDPR**.
That usually covers CCPA if we do not sell/share data.

### Google (blocks public sign-in)

`gmail.modify` is **sensitive** (verification **free**). Restricted
`mail.google.com` is **paid CASA** — never add it.

Publish on a **domain we own**:

- Homepage (what the app does)
- Privacy policy (Gmail data **called out separately**)
- Terms (label-only, refunds, liability, governing law India)
- YouTube **demo**: consent screen, scopes, label-only, disconnect
- Limited Use: Gmail data only to classify/label **that user**; no ads; no
  sale; no training a **shared** model; no transfer except processors
  (LLM, host, payments); humans only for security/support with cause;
  user can disconnect and we **delete** Gmail-derived data

Until verified: **Testing** + test users only.

### India — DPDP Act 2023 + Rules 2025

Operator is in India and processes digital personal data → **Data Fiduciary**.

- Standalone privacy **notice** (not buried in ToS)
- Consent specific (Gmail connect ≠ marketing email)
- Processors under contract
- Delete when purpose ends + on request
- Grievance contact
- Cross-border allowed except a government **negative list** (watch
  notifications)
- Build during 2026; heavy duties phasing toward **May 2027**; Consent
  Manager registration framework ~**Nov 2026** (we are **not** a Consent
  Manager)
- Unlikely **Significant Data Fiduciary** at v1 volume

### EU/UK — GDPR (the moment an EU/UK person connects)

- Lawful basis: **contract** to label their mailbox; OAuth is Google permission
- DPA + **SCCs** if a US LLM/host processes the data
- Access / export / delete / disconnect
- Sub-processors page: Google, LLM, host, PayPal/Paddle

### US — CCPA/CPRA (California residents)

- Do not sell/share; honor delete/know
- Email **contents** are sensitive — use only to provide the service

### Not required at v1

SOC 2, ISO, DPO, HIPAA, PCI-DSS (PayPal/Paddle hold cards; we never store PAN).

---

## 9. Documents to publish before first paid foreign user

| Doc | Must include |
|-----|----------------|
| Privacy policy | Collect / use / processors / Limited Use / retention / deletion / no ads |
| Terms | Label-only, 7-day conditional refund, cancel, liability, India law |
| Sub-processors | Google, LLM, host, PayPal (or Paddle) |
| DPA | If EU or serious B2B |
| Pay / invoice | Price, what Pro includes, refund rule |

In-product: **Connect Gmail**, **Disconnect & delete my data**.

Contact: `privacy@` on the same domain.

---

## 10. User rights (must ship)

- Disconnect Google (revoke + delete tokens)
- Delete account → wipe payloads, RAG, classifications, tokens
- Export: labels applied + dates (not a full mailbox dump)
- Honor user-removed `AI/…` labels (already: negative examples, no re-apply)
- On refund: same delete path as disconnect

---

## 11. Suggested money + product flow (solo v1)

```
Foreign customer
  → PayPal invoice $12/mo
  → Entitlement plan=pro
  → Connect Gmail (verified OAuth)
  → Pub/Sub / poll → classify → labels under AI/
  → If broken within 7 days → PayPal refund + delete data
  → Else cancel anytime (stop next charge)

Indian customer
  → UPI/bank invoice + 18% GST if registered
  → Same product
```

---

## 12. Exit criteria

- [ ] Phase 4+5 merged and dogfooded
- [ ] HTTPS app + privacy + terms + Limited Use on our domain
- [ ] Bodies not stored long-term; zero-retention LLM; tenant isolation
- [ ] Disconnect + delete + export
- [ ] Google sensitive-scope verification **approved** (or stay in Testing)
- [ ] PayPal (or Paddle) live with **7-day conditional refund** and Pro $12
- [ ] GST/LUT/FIRA process documented with a CA **if** charging
- [ ] Pub/Sub push → `sync_incremental` (or documented poll-only v1)
- [ ] Postgres per-tenant RAG (pgvector optional if hashing still holds)
- [ ] [PRIVACY.md](PRIVACY.md) updated for hosted mode

## Cost note

Verification is **free** if scopes stay sensitive. Cash: domain, HTTPS host,
Postgres, LLM tokens, PayPal fees. No CASA if we never add restricted Gmail
scope.
