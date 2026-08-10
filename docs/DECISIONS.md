# Tagsmith decisions (Phase 0 + Phase 1)

These are decisions, not options. Implement against them directly.

For narrative architecture see [DESIGN.md](DESIGN.md). For the full roadmap see [PLAN.md](PLAN.md). Docs index: [README.md](README.md).

## Scope

Phase 0 + Phase 1 in one pass. No stubs and no empty modules for later phases.

Two future seams only:

1. The classifier function accepts an optional `examples: list[LabeledEmail]` parameter (unused in Phase 1; injection point for RAG in Phase 3).
2. All business logic lives in a service layer that the CLI merely calls (so Phase 4 MCP and Phase 5 FastAPI can wrap the same functions).

Dry-run is the default; `--apply` is the only thing that writes to Gmail.

## Runtime shape

- Hosted small model first via a single Pydantic AI model string in config (e.g. `openai:gpt-4.1-mini` / `google-gla:gemini-2.0-flash`). Ollama is an env-var switch, not a code change.
- Local CLI, SQLite, desktop OAuth.
- Approvals via `tagsmith review` in the terminal — no Slack/email channel yet.
- Exactly one primary label per message.
- Python 3.12+ (3.11 floor), uv, hatchling, `src/` layout, ruff, mypy, pytest.

## Labeling / mailbox trust

- Always **leave unread**. Never modify read state; do not add a flag for it.
- Never remove `INBOX` / archive. Label-only.
- Nested labels under parent `AI/`, plus `AI/needs-review`.

## Seed taxonomy (16)

`payment-sent`, `payment-received`, `bill-due`, `subscription-renewal`, `security-alert`, `otp-verification`, `order-confirmation`, `shipping-update`, `travel-booking`, `newsletter`, `promotion`, `job-application`, `support-ticket`, `account-statement`, `tax-document`, `refund`.

In `seed.yaml`, each entry has: `key`, one-line `description` (prompt disambiguation), and 2–3 exemplar subject lines.

## Confidence routing

Both signals matter:

- `label_key is None` is authoritative no-fit.
- `confidence` is coarse triage (not a calibrated probability).

Defaults (configurable, logged):

- `>= 0.75` → apply
- `0.5–0.75` → apply plus `AI/needs-review`
- `< 0.5` or `None` → hold and propose

### Medium-band review (distinct from proposal review)

For `AI/needs-review` messages the actions are:

1. **confirm** the predicted label
2. **change** to a different existing label
3. **reject and propose** a new category

Store corrections with `predicted_key` retained alongside `final_key` so Phase 2 can measure drift and Phase 3 can harvest labeled examples. UI: print the email, offer confirm / pick-another / propose-new.

## Rules

- Built-in pack shipped in-package + user file `~/.config/tagsmith/rules.yaml` (identical schema; user rules win on conflict).
- Rules bypass the LLM and never open proposals.
- Record `confidence=NULL` with `source='rule'` — **not** 1.0 (avoids contaminating Phase 2 calibration).
- At startup, validate every rule targets an active taxonomy key; fail loudly if not.

## Approval / proposal semantics

On approve: create Gmail label, insert taxonomy row, apply to the triggering message, and re-run classification over messages currently in `held` state inside `approve` (not a separate command). Re-classify properly; do not blind-apply the new label.

## Idempotency / sync

- Skip on prior SQLite decision keyed by Gmail message id.
- Provide `--reprocess` escape hatch.
- When fetching, compare current Gmail labels against what was applied. If the user manually removed the Tagsmith label, record a **negative example** and never re-apply that label to that message.

## Privacy / payload

- Headers + plaintext only: From, To, Subject, Date, List-Unsubscribe.
- Body from `text/plain`, else HTML→text.
- Never send attachment contents — filenames only.
- Default body cap **2000** characters (configurable), truncate from the end.
- Regex-redact digit runs of **nine or more** before the payload leaves the process.

## Testing / credentials

- Keep the Gmail client behind a thin interface.
- Tests use recorded, real-shaped API JSON fixtures (payment alert, security alert, OTP, newsletter, multipart HTML-only, attachment).
- Do **not** put real credentials in an agent environment.
- `credentials.json` and `token.json` in platform config dir; both patterns in `.gitignore` from the first commit.
- First real e2e: run `tagsmith auth` locally after creating a Desktop OAuth client (consent screen External + Testing mode with your address as test user).

## Explicit non-goals for this pass

No LangGraph, no web UI, no vector DB, no MCP, and no empty placeholder modules for them.
