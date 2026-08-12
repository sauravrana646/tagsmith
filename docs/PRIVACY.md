# Privacy and trust

Email is sensitive. Tagsmith is designed so the agent’s footprint is visible, reversible, and minimal.

## Hard rules (v0.1)

1. **Never mark messages read.** There is no flag for this.
2. **Never archive / remove `INBOX`.** Label-only.
3. **All agent labels nest under `AI/`** (configurable parent) plus `AI/needs-review`.  
   In Gmail, deleting or hiding the parent undoes the agent’s taxonomy footprint.
4. **Dry-run by default.** `--apply` is required to write labels.
5. **OAuth scopes stay sensitive, not restricted:**
   - `gmail.modify`
   - `gmail.labels`  
   Never `https://mail.google.com/`.

## What leaves your machine on classify

When a message misses the rule engine and hits the LLM, Tagsmith sends:

- From, To, Subject, Date
- List-Unsubscribe (if present)
- Attachment **filenames** (not file bytes)
- Body text truncated to `TAGSMITH_BODY_CHAR_LIMIT` (default **2000**)
- Digit runs of length **≥ 9** replaced with `[REDACTED]` (cards/accounts; amounts like `$12.50` survive)

Raw MIME, full HTML, and attachment contents are not uploaded by Tagsmith.

Provider retention policies are **outside** Tagsmith’s control — prefer providers with zero-retention options for production/SaaS (**Phase 6**).

## What is stored locally

| Data | Where |
|------|--------|
| OAuth refresh token | Config dir `token.json` |
| SQLite audit (subjects, hashes, rationales, decisions) | User data dir `tagsmith.db` |
| Optional body snapshot in `messages.payload_json` | Same DB (for review UI) |

Do not commit `.env`, `credentials.json`, `token.json`, or DB files. CI fails if sensitive filenames are tracked.

## Human corrections

Review stores `predicted_key` and `final_key` so later evals can measure model drift without re-annotating from scratch. Treat the DB as sensitive if it contains mail subjects/snippets.

## Product naming

OAuth consent screen app name must remain **Tagsmith**. Google rejects names that include their product trademarks as the app name. “Gmail” may appear only descriptively in a tagline if needed.

## Incident / undo

| Mistake | Recovery |
|---------|----------|
| Wrong label applied | Remove label in Gmail UI, or change via `tagsmith review` / reprocess after fix |
| Agent labels unwanted | Delete/hide parent `AI` label in Gmail |
| Token compromised | Revoke app access in Google Account settings; delete local `token.json`; re-`auth` |
| Bad new category approved | Mark rejected in taxonomy / delete Gmail label; stop using key |

## Future SaaS (Phase 6) expectations

Not implemented yet. Final phase calls for hosted Pub/Sub push, Stripe Checkout,
Google sensitive-scope verification, encrypted per-tenant tokens at scale,
hash/embedding-first storage with pgvector isolation, and a published data
policy. Phase 5 already lands local API + token encryption foundations.
See [SAAS.md](SAAS.md) and [PLAN.md](PLAN.md).
