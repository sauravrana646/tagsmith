# Tagsmith

**Tagsmith** is a local Python CLI that classifies unread Gmail into a managed taxonomy
(`payment-sent`, `shipping-update`, `security-alert`, …), applies nested `AI/...` labels,
and queues **category proposals** when nothing fits — so humans grow the taxonomy on purpose.

It is both:

1. a **usable mailbox assistant** you can run today, and  
2. a **learning path** through structured LLM output, evals, RAG, and (later) MCP/SaaS.

Phase **0–2** are on `main` (Gmail plumbing, rules, classifier, review, evals).  
**Phase 3 (RAG few-shots)** is in progress on `feature/phase-3-rag` — see [docs/RAG.md](docs/RAG.md).  
Later phases (continuous sync/MCP, product UI) remain planned — see [docs](docs/README.md).

---

## Why Tagsmith

| Problem | Tagsmith approach |
|---------|-------------------|
| LLM invents random labels | Closed-set `label_key` from active taxonomy; new categories only via `proposed_new` |
| Agent ruins inbox trust | Labels only under `AI/` — never marks read, never archives |
| LLM cost on every bank alert | Deterministic rules first; LLM handles the tail |
| Silent category sprawl | Human review before new Gmail labels are created |
| Re-runs double-bill / double-label | SQLite decisions keyed by Gmail message id |

---

## Features (v0.1)

- Desktop OAuth with **`gmail.modify` + `gmail.labels`** only (not restricted `mail.google.com`)
- MIME normalizer: headers + plaintext, 2000-char cap, ≥9 digit redaction, attachment **filenames** only
- Builtin + user rule engine before the LLM
- Pydantic AI classifier (OpenAI / Google / Anthropic / OpenRouter / Ollama via one model string)
- Confidence routing: apply / apply+needs-review / hold+propose
- Dry-run by default; `--apply` writes to Gmail
- `tagsmith review` for held mail, medium-confidence confirm/change, and new-category proposals
- Numeric existing-label picker; LLM `proposed_new` shown when nothing fits
- Idempotent sync; `--reprocess` escape hatch; negative examples if you remove an agent label
- Offline tests + CI (lint, types, tests, Gitleaks secret scan, dependency audit, Bandit) with a `quality-gate` merge check
- Phase 2: golden-set eval harness (`tagsmith eval`) + optional Logfire tracing
- Phase 3 (branch): RAG few-shot retrieval over labeled examples (`tagsmith eval --rag`)

---

## Quick start

### Requirements

- Python **3.11+** (3.12 recommended)
- [uv](https://github.com/astral-sh/uv)
- A Google Cloud project with Gmail API + Desktop OAuth client
- An LLM API key (OpenRouter, OpenAI, Google, Anthropic, or local Ollama)

### Install

```bash
git clone https://github.com/sauravrana646/tagsmith.git
cd tagsmith
uv sync --group dev
cp .env.example .env
```

### Configure `.env`

Minimum for OpenRouter (example used in dogfooding):

```bash
TAGSMITH_LLM_MODEL=openrouter:deepseek/deepseek-v4-flash-0731
OPENROUTER_API_KEY=sk-or-v1-...
```

Other examples:

```bash
TAGSMITH_LLM_MODEL=openai:gpt-4.1-mini
OPENAI_API_KEY=sk-...

TAGSMITH_LLM_MODEL=google-gla:gemini-2.0-flash
GOOGLE_API_KEY=...

TAGSMITH_LLM_MODEL=ollama:llama3.1
# no key needed if Ollama is running locally
```

Full variable reference: [docs/SETUP.md](docs/SETUP.md#environment-variables).

### Google OAuth (once)

1. GCP project → enable **Gmail API**
2. OAuth consent screen: **External**, **Testing**, add yourself as test user
3. Create OAuth client → type **Desktop app** → download JSON
4. Save as `~/.config/tagsmith/credentials.json`  
   (never commit this or `token.json`)

```bash
uv run tagsmith auth
uv run tagsmith fetch --unread --limit 5
```

Detailed steps: [docs/SETUP.md](docs/SETUP.md).

### First real run

```bash
# Dry-run — classify + write SQLite, do not touch Gmail labels
uv run tagsmith sync --limit 20

# Apply labels in Gmail
uv run tagsmith sync --limit 20 --apply

# Review holds / proposals / medium-confidence items
uv run tagsmith review
```

CLI reference and review guide: [docs/USAGE.md](docs/USAGE.md).

---

## How it works (short)

```text
Gmail unread
  → normalize (headers + clean text, redact, truncate)
  → rules (sender/subject fast path)
  → LLM closed-set classify (optional future RAG examples)
  → route by confidence
       ≥0.75           apply AI/<label>
       0.5–0.75        apply + AI/needs-review
       <0.5 or None    hold + propose new category
  → SQLite audit
  → tagsmith review (human)
```

Design deep-dive: [docs/DESIGN.md](docs/DESIGN.md).

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/SETUP.md](docs/SETUP.md) | Install, GCP, OAuth, LLM providers, config paths |
| [docs/USAGE.md](docs/USAGE.md) | CLI commands, review workflow, sync semantics |
| [docs/DESIGN.md](docs/DESIGN.md) | Architecture, data model, routing, seams |
| [docs/PRIVACY.md](docs/PRIVACY.md) | Privacy, scopes, redaction, trust boundaries |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Dev setup, tests, CI, PR expectations |
| [docs/PLAN.md](docs/PLAN.md) | Full product/phase plan |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Locked Phase 0/1 decisions |

---

## Project layout

```text
tagsmith/
  src/tagsmith/
    cli.py                 # Typer CLI (thin)
    config.py              # pydantic-settings
    gmail/                 # auth, client, parser, FakeGmail
    classify/              # rules, Pydantic AI agent, routing
    taxonomy/              # seed.yaml + registry
    review/                # queues, display, suggestions
    services/              # SyncService, ReviewOps (business logic)
    db/                    # SQLModel models + SQLite
  tests/                   # offline fixtures + FakeGmail
  docs/                    # design, setup, usage, plan
  .github/workflows/ci.yml # lint, test, security
```

---

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

CI on PRs to `main`: lint, format, mypy, pytest (3.11/3.12), Gitleaks, pip-audit, Bandit.  
See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## Privacy & trust (read this)

- Tagsmith **never** marks mail read and **never** removes `INBOX`.
- Only nested labels under `AI/` (one click undoes the agent’s footprint in Gmail).
- Bodies sent to the LLM are truncated and digit-runs of length ≥ 9 are redacted.
- Attachment **contents** are never sent — filenames only.
- OAuth tokens live in your OS config dir, not the repo.

Details: [docs/PRIVACY.md](docs/PRIVACY.md).

---

## Roadmap (high level)

| Phase | Status | Focus |
|-------|--------|--------|
| 0 Foundations | Done | Auth, fetch, normalize |
| 1 Skeleton | Done | Rules, LLM, apply, review, SQLite |
| 2 Evals | Planned | Golden set, precision/recall, tracing |
| 3 RAG | Planned | Few-shot from prior labels via `examples=` |
| 4 Continuous + MCP | Planned | History/watch, MCP tools over services |
| 5 Product | Planned | FastAPI, multi-tenant, dashboard |

Full plan: [docs/PLAN.md](docs/PLAN.md).

---

## License

[MIT](LICENSE)
