# Policies (Phase 6 drafts)

**Status: DRAFT — not legal advice.** These pages are for Google OAuth
verification and the hosted Tagsmith site. A lawyer in India (and, if you take
EU users, someone who knows GDPR) must review them before you publish or submit
verification.

Customer product: **hosted web app only** (see [docs/PHASE6.md](../docs/PHASE6.md)).
Users do not install the CLI.

## Fill before publish

Edit every `[BRACKET]` placeholder. Keep the same values across files.

| Placeholder | Meaning |
|-------------|---------|
| `[LEGAL_NAME]` | Your legal name (or sole-prop trade name) |
| `[SITE_URL]` | Public HTTPS origin, e.g. `https://tagsmith.example` |
| `[PRIVACY_EMAIL]` | e.g. `privacy@` on that domain |
| `[SUPPORT_EMAIL]` | Billing / product help |
| `[POSTAL_ADDRESS]` | India address for notices |
| `[LLM_PROCESSOR]` | e.g. OpenRouter / the model host you actually use |
| `[HOSTING_PROCESSOR]` | e.g. the cloud that runs API + DB |
| `[PAYMENTS_PROCESSOR]` | PayPal (v1) |

## Publish on the domain

Google expects these **on `[SITE_URL]`**, linked from the homepage and the
OAuth consent screen:

| File | Public URL (suggested) |
|------|------------------------|
| [privacy-policy.md](privacy-policy.md) | `/privacy` |
| [terms-of-service.md](terms-of-service.md) | `/terms` |
| [google-limited-use.md](google-limited-use.md) | `/limited-use` |
| [sub-processors.md](sub-processors.md) | `/subprocessors` |
| [cookie-notice.md](cookie-notice.md) | `/cookies` |
| [refund-policy.md](refund-policy.md) | `/refunds` (also linked from pay) |
| [dpa.md](dpa.md) | `/dpa` (EU / B2B) |

Gmail data use must appear **separately** in the privacy policy (already a
dedicated section) and on Limited Use.

## In-product (engineering, not this folder)

- Connect Gmail / Disconnect & delete my data
- Link privacy + terms next to Sign in
- Export of labels applied (not a full mailbox dump)
