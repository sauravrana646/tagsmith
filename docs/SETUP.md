# Setup guide

This guide gets Tagsmith running against **your** Gmail account on a local machine.

## Prerequisites

- macOS, Linux, or Windows (WSL recommended on Windows)
- Python **3.11+** (3.12 recommended)
- [uv](https://docs.astral.sh/uv/)
- Ability to create a Google Cloud project
- An LLM provider account **or** local [Ollama](https://ollama.com/)

## 1. Clone and install

```bash
git clone https://github.com/sauravrana646/tagsmith.git
cd tagsmith
uv sync --group dev
cp .env.example .env
uv run tagsmith --help
```

Console script: `tagsmith` (via `uv run tagsmith …`).

## 2. Google Cloud / Gmail OAuth

Tagsmith uses **Desktop** OAuth with sensitive (not restricted) scopes:

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.labels`

Do **not** enable `https://mail.google.com/` — that restricted scope requires a paid annual security assessment.

### Steps

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create (or select) a project.
3. Enable **Gmail API**.
4. **APIs & Services → OAuth consent screen**
   - User type: **External**
   - App name: **Tagsmith** (do not put “Gmail” in the app name)
   - Publishing status: leave in **Testing**
   - Add your Google account under **Test users**
5. **Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON
6. Save the file as:

```text
~/.config/tagsmith/credentials.json
```

On macOS that is typically:

```text
/Users/<you>/Library/Application Support/tagsmith/credentials.json
```

`platformdirs` is used; override with `TAGSMITH_GOOGLE_CLIENT_SECRET_PATH` if needed.

7. Authenticate:

```bash
uv run tagsmith auth
```

A browser window opens. Sign in, grant access. Tagsmith stores `token.json` next to the credentials path (same config dir by default).

**Never commit** `credentials.json` or `token.json`. Both patterns are in `.gitignore`.

### Verify Gmail plumbing

```bash
uv run tagsmith labels list
uv run tagsmith fetch --unread --limit 5
```

## 3. LLM provider

Tagsmith passes `TAGSMITH_LLM_MODEL` straight to [Pydantic AI](https://ai.pydantic.dev) (`provider:model` string). Provider API keys must be in the process environment (loaded from `.env` automatically).

### OpenRouter (recommended for cheap multi-model access)

```bash
TAGSMITH_LLM_MODEL=openrouter:deepseek/deepseek-v4-flash-0731
OPENROUTER_API_KEY=sk-or-v1-...
```

Get a key: https://openrouter.ai/keys  
Pick models: https://openrouter.ai/models  

### OpenAI

```bash
TAGSMITH_LLM_MODEL=openai:gpt-4.1-mini
OPENAI_API_KEY=sk-...
```

### Google Gemini

```bash
TAGSMITH_LLM_MODEL=google-gla:gemini-2.0-flash
GOOGLE_API_KEY=...
```

### Anthropic

```bash
TAGSMITH_LLM_MODEL=anthropic:claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...
```

### Ollama (local)

```bash
TAGSMITH_LLM_MODEL=ollama:llama3.1
# ollama serve  # in another terminal
```

No API key required.

## 4. Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `TAGSMITH_LLM_MODEL` | `openai:gpt-4.1-mini` | Pydantic AI model string |
| `TAGSMITH_GOOGLE_CLIENT_SECRET_PATH` | `~/.config/tagsmith/credentials.json` | OAuth client JSON |
| `TAGSMITH_TOKEN_PATH` | config dir `token.json` | Refresh token store |
| `TAGSMITH_DATABASE_URL` | SQLite under user data dir | e.g. `sqlite:////abs/path/tagsmith.db` |
| `TAGSMITH_RULES_PATH` | `~/.config/tagsmith/rules.yaml` | User rules overlay |
| `TAGSMITH_CONFIDENCE_APPLY` | `0.75` | Apply without review |
| `TAGSMITH_CONFIDENCE_REVIEW` | `0.5` | Apply + needs-review band floor |
| `TAGSMITH_LABEL_PARENT` | `AI` | Gmail label parent |
| `TAGSMITH_BODY_CHAR_LIMIT` | `2000` | Max body chars to LLM |
| `TAGSMITH_LOG_LEVEL` | `INFO` | structlog level |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / … | — | Provider credentials (not `TAGSMITH_`-prefixed) |

Copy from [`.env.example`](../.env.example).

## 5. Important local paths

| Artifact | Typical location (macOS) |
|----------|---------------------------|
| OAuth client JSON | `~/Library/Application Support/tagsmith/credentials.json` |
| Token | `~/Library/Application Support/tagsmith/token.json` |
| SQLite DB | `~/Library/Application Support/tagsmith/tagsmith.db` |
| User rules | `~/Library/Application Support/tagsmith/rules.yaml` |
| Project `.env` | `<repo>/.env` |

Confirm DB URL:

```bash
uv run python -c "from tagsmith.config import get_settings; print(get_settings().database_url)"
```

## 6. Optional user rules

Create `~/.config/tagsmith/rules.yaml` (same schema as builtin rules). User rules **win** on name conflict.

Builtin pack lives in the package: `src/tagsmith/classify/builtin_rules.yaml`.

Every rule `label_key` must reference an **active** taxonomy key or startup fails loudly.

## 7. Smoke checklist

```bash
uv run tagsmith auth
uv run tagsmith taxonomy list
uv run tagsmith sync --limit 10          # dry-run
uv run tagsmith sync --limit 10 --apply
uv run tagsmith review list
uv run tagsmith review
```

If OpenRouter/OpenAI auth fails, confirm the key is in `.env` **and** you restarted from the repo root so `load_dotenv()` can find it.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OPENROUTER_API_KEY` / provider key missing | Put key in `.env`; pull latest (dotenv is loaded into process env) |
| `OAuth client secret not found` | Place Desktop JSON at config path or set `TAGSMITH_GOOGLE_CLIENT_SECRET_PATH` |
| Consent screen blocked | App in Testing? Is your account a test user? |
| Sync skips everything | Prior SQLite decisions — omit `--reprocess` for new mail only |
| Labels created but mail still unread | Expected — Tagsmith never marks read |
