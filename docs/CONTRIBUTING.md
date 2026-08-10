# Contributing

Thanks for helping with Tagsmith. Phase 0/1 are in place; follow [DECISIONS.md](DECISIONS.md) and [DESIGN.md](DESIGN.md) so we don’t reopen settled product choices casually.

## Development setup

```bash
git clone https://github.com/sauravrana646/tagsmith.git
cd tagsmith
uv sync --group dev
cp .env.example .env   # optional for local Gmail dogfood
```

Python **3.11+** (CI runs 3.11 and 3.12). Packaging: uv + hatchling, `src/` layout.

## Checks before you push

```bash
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run pytest
uv export --frozen --no-emit-project --no-dev --no-hashes -o /tmp/requirements.txt
uv run pip-audit -r /tmp/requirements.txt --strict
uv run bandit -r src -ll -c pyproject.toml
```

### CI

PRs and pushes to `main` run `.github/workflows/ci.yml`:

- Ruff lint + format
- Mypy
- Pytest (3.11, 3.12)
- Gitleaks (secrets)
- pip-audit
- Bandit
- Guard against tracked credential filenames

## Project conventions

1. **No empty placeholder modules** for future phases. Use the two seams in DECISIONS (`examples=` on classify; logic in `services/`).
2. **CLI stays thin** — business logic in `services/`.
3. **Gmail access behind `GmailGateway`** — add fixtures/`FakeGmail` coverage for new behaviors.
4. **Rules:** validate against active taxonomy; rule confidence is `NULL`.
5. **Privacy:** don’t send attachment bodies; keep redaction/truncation intact.
6. **One primary label** per message in v1.

## Tests

- Live under `tests/` with real-shaped fixtures in `tests/fixtures/messages.py`.
- Do not require network, Gmail credentials, or LLM keys.
- Prefer stubbing `classify_email` / using FakeGmail over hitting providers.

## Pull requests

- Target `main`.
- Keep PRs focused; update docs when behavior or UX changes (`docs/USAGE.md`, `DESIGN.md`, `DECISIONS.md` as appropriate).
- Ensure CI is green.
- Never commit `.env`, OAuth client JSON, tokens, or mailbox databases.

## Useful docs

- [SETUP.md](SETUP.md) — running against real Gmail
- [USAGE.md](USAGE.md) — CLI / review
- [PLAN.md](PLAN.md) — roadmap
