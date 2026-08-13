# Sub-processors

**Draft. Last updated: 13 August 2026.**  
Replace bracketed vendor names with the **actual** legal entities you use
before going live. Notify customers of material additions where the DPA
requires it.

**Operator:** `[LEGAL_NAME]` · **Contact:** `[PRIVACY_EMAIL]`

These vendors process personal data (including Gmail-derived data where
noted) for Tagsmith hosted service at `[SITE_URL]`.

| Processor | Role | Gmail-derived data? | Region (typical) |
|-----------|------|---------------------|------------------|
| Google LLC / Google Ireland | OAuth, Gmail API | Yes (in Google’s systems; we call the API) | Global |
| `[LLM_PROCESSOR]` | Classification of truncated, redacted snippets | Yes (prompt payload) | `[LLM_REGION]` |
| `[HOSTING_PROCESSOR]` | App hosting, database, backups | Yes (our DB) | `[HOST_REGION]` |
| `[PAYMENTS_PROCESSOR]` (PayPal v1) | Subscriptions / invoices | No mail bodies; billing email and amounts | Global |
| `[EMAIL_TRANSACTIONAL]` (if any) | Passwordless notices, receipts | No Gmail bodies | `[EMAIL_REGION]` |
| `[ERROR_MONITORING]` (if any) | Crash reports | Must **not** include subjects/bodies by default | `[MONITOR_REGION]` |

## Rules we apply to processors

- Written contract (and DPA/SCCs where needed for EEA/UK).
- LLM: **zero retention / no training** on API content, or we do not use them
  for classify.
- No advertising use of Gmail data.
- We do not add a processor that puts data in a country on an Indian DPDP
  **negative list** if that restriction applies.

## Not sub-processors

- You (the customer) and Google acting as **your** mailbox provider
- Public DNS, certificate authorities, in the ordinary way

## Updates

We will date this page when the list changes. Material new processors that
handle Gmail-derived data will also be mentioned in the privacy policy.
