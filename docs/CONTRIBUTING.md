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

Pull requests targeting `main` run `.github/workflows/ci.yml` (no push-to-`main` workflow runs):

| Job | What it checks |
| --- | --- |
| `secret-scan` | Gitleaks + credential filename guard (runs first) |
| `lint-test` | Ruff, Mypy, Pytest (3.11 / 3.12) |
| `security` | pip-audit + Bandit |
| `quality-gate` | Aggregates the above; **this** is the merge gate |

### Secret detection: Gitleaks vs GitGuardian

**Use Gitleaks as the required merge gate.** Keep GitGuardian optional for monitoring.

| | Gitleaks | GitGuardian |
| --- | --- | --- |
| Cost for CI gate | Free / OSS | Paid for reliable org policies |
| Runs in our workflow | Yes (`gitleaks-action` + `.gitleaks.toml`) | GitHub App / SaaS (outside our YAML) |
| Can be a required check | Yes — fails `secret-scan` → fails `quality-gate` | Only if the App check is required separately |
| Offline / local | `gitleaks detect` locally | Needs cloud API |
| Strength | Deterministic, repo-owned config, PR annotations | Historical digests, multi-repo dashboards, incident workflow |

Recommendation for Tagsmith:

1. **Required:** Gitleaks in CI (`secret-scan` job) → blocks via `quality-gate`.
2. **Optional:** GitGuardian GitHub App for inbox/alerts (nice to have; do **not** rely on it alone to block merges).
3. **Also enable** on GitHub: Settings → Code security → **Secret scanning** + **Push protection** (native GitHub, complementary).

Do not treat GitGuardian as a substitute for Gitleaks here: App checks can be flaky/skipped on forks, and we cannot version-control their rules next to the code the way we do `.gitleaks.toml`.

### Require the quality gate on `main` (branch protection)

CI alone does not block merges until branch protection requires the check. A repo admin must:

1. GitHub → **Settings** → **Branches** → **Add/Edit branch protection rule** for `main`.
2. Enable **Require a pull request before merging**.
3. Enable **Require status checks to pass before merging**.
4. Search and select **`quality-gate`** (and optionally also `secret-scan` if you want it listed separately).
5. Prefer **Do not allow bypassing the above settings** for admins on a solo/small repo if you want the gate to always apply.
6. Optionally enable **Require branches to be up to date before merging**.

Until that rule exists, a red `quality-gate` is advisory only. After the first CI run on this workflow, the `quality-gate` check name appears in the status-check picker.

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
- Ensure CI is green — especially **`quality-gate`** (includes Gitleaks).
- Never commit `.env`, OAuth client JSON, tokens, or mailbox databases.
- Run `gitleaks detect --source . -v` locally if you have the CLI installed before opening a PR.

## Useful docs

- [SETUP.md](SETUP.md) — running against real Gmail
- [USAGE.md](USAGE.md) — CLI / review
- [PLAN.md](PLAN.md) — roadmap
