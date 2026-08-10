# Tagsmith

Classify unread Gmail into a managed taxonomy (`payment-sent`, `security-alert`, …),
apply nested `AI/...` labels, and file **category proposals** when nothing fits.
Humans approve new categories in the terminal; the taxonomy grows.

Phase 0 + Phase 1 are implemented. See [`docs/PLAN.md`](docs/PLAN.md) and
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Features (v0.1)

- Desktop OAuth with `gmail.modify` + `gmail.labels` (not the restricted `mail.google.com` scope)
- MIME normalizer: headers + plaintext, 2000-char cap, digit-run redaction, attachment filenames only
- Deterministic rule engine (builtin + `~/.config/tagsmith/rules.yaml`) before the LLM
- Pydantic AI closed-set classifier with confidence routing
- Dry-run by default; `--apply` writes labels
- SQLite audit trail with `predicted_key` / `final_key` for human corrections
- `tagsmith review` for medium-confidence confirm/change/propose-new and proposal approve/reject
- Idempotent sync with `--reprocess`, plus negative examples when a user removes an applied label

## Install

Requires Python 3.11+ (3.12 recommended) and [uv](https://github.com/astral-sh/uv).

```bash
uv sync --all-extras
uv run tagsmith --help
```

## Google Cloud setup (local)

1. Create a GCP project and enable the **Gmail API**.
2. Configure the OAuth consent screen as **External**, leave it in **Testing**,
   and add your address as a test user.
3. Create an OAuth client ID of type **Desktop app** and download the JSON.
4. Save it as `~/.config/tagsmith/credentials.json`
   (or set `TAGSMITH_GOOGLE_CLIENT_SECRET_PATH`).
5. Never commit `credentials.json` or `token.json`.

```bash
uv run tagsmith auth
uv run tagsmith labels list
uv run tagsmith fetch --unread --limit 5
```

## Configure

Copy [`.env.example`](.env.example) and set at least:

```bash
export TAGSMITH_LLM_MODEL=openai:gpt-4.1-mini   # or google-gla:gemini-2.0-flash, ollama:llama3.1
export OPENAI_API_KEY=...
```

## Usage

```bash
# Dry-run classification (default — no mailbox writes)
uv run tagsmith sync --limit 20

# Apply labels
uv run tagsmith sync --limit 20 --apply

# Review medium-confidence + proposals
uv run tagsmith review

# Taxonomy
uv run tagsmith taxonomy list
```

## Tests

Tests use a fake Gmail gateway and recorded fixtures — no credentials required.

```bash
uv sync --group dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pip-audit -r <(uv export --frozen --no-emit-project --no-dev --no-hashes)
uv run bandit -r src -ll -c pyproject.toml
```

CI runs the same checks on pull requests to `main` (lint, types, tests, secret scan, dependency audit, Bandit).

## Privacy notes

- Bodies are truncated and digit runs of length ≥ 9 are redacted before LLM calls.
- Attachment *contents* are never sent — filenames only.
- Tagsmith never marks messages read and never archives / removes `INBOX`.
