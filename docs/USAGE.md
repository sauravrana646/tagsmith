# Usage guide

## Mental model

1. **`sync`** reads unread Gmail, classifies (rules → LLM), writes SQLite.  
   With **`--apply`**, also creates/applies `AI/...` labels.
2. **`review`** is the human loop for:
   - medium-confidence labels (`needs_review`)
   - held messages (`AI/needs-review` in Gmail, no confident category)
   - new-category proposals
3. Tagsmith **never** marks messages read and **never** archives.

Default sync limit: **50** unread messages (`--limit` / `-n`, max 500).

---

## CLI reference

```bash
uv run tagsmith --help
uv run tagsmith --version
```

### `auth`

Run desktop OAuth; save refresh token.

```bash
uv run tagsmith auth
```

### `labels list`

List Gmail labels (sanity check after auth).

```bash
uv run tagsmith labels list
```

### `fetch`

Print normalized unread (or all) messages — Phase 0 plumbing check. **Read-only.**

```bash
uv run tagsmith fetch --unread --limit 5
uv run tagsmith fetch --all --limit 5
```

### `taxonomy list`

Show active local taxonomy (seeded from `seed.yaml`, plus approved categories).

```bash
uv run tagsmith taxonomy list
```

### `sync`

Classify unread mail.

```bash
# Dry-run (default): SQLite + console only
uv run tagsmith sync
uv run tagsmith sync --limit 20

# Write labels to Gmail
uv run tagsmith sync --limit 20 --apply

# Re-classify messages that already have SQLite decisions
uv run tagsmith sync --limit 20 --apply --reprocess
```

#### Sync semantics

| Situation | Without `--reprocess` | With `--reprocess` |
|-----------|------------------------|--------------------|
| Unread, no SQLite decision | Classify | Classify |
| Unread, already labeled/held/needs-review in SQLite | **Skip** (`skipped_prior`) | Classify again |
| User removed Tagsmith label in Gmail | Record negative example; skip re-apply | Same |
| Read mail | Not fetched (`is:unread`) | Not fetched |

`--apply` is **not** “replay last dry-run from DB.” Each run classifies unless skipped. Dry-run then later `--apply` without `--reprocess` will mostly `skipped_prior`. Prefer either:

```bash
uv run tagsmith sync --limit 20 --apply
```

or dry-run then force:

```bash
uv run tagsmith sync --limit 20
uv run tagsmith sync --limit 20 --apply --reprocess
```

#### Confidence routing

| Result | Action |
|--------|--------|
| `label_key` set, confidence `≥ 0.75` | Apply `AI/<key>` |
| `label_key` set, confidence `0.5–0.75` | Apply + `AI/needs-review` |
| `label_key` null or confidence `< 0.5` | Hold; require LLM `proposed_new`; apply `AI/needs-review` for visibility |
| Rule hit | Apply; `confidence` stored as `NULL`, `source=rule` |

Thresholds: `TAGSMITH_CONFIDENCE_APPLY`, `TAGSMITH_CONFIDENCE_REVIEW`.

### `review` / `review list`

```bash
uv run tagsmith review list   # counts + ids
uv run tagsmith review        # interactive
```

#### Review sections (in order)

1. **Needs review** — medium-confidence applied labels  
   Actions: `[c]onfirm` · `[p]ick another` · `[n]ew category` · `[s]kip`
2. **Held / needs decision** — no confident category (often still under `AI/needs-review` in Gmail)  
   Actions: `[e]xisting label` · `[n]ew category` · `[s]kip`  
   Shows:
   - suggested **existing** label (heuristic from subject/rationale), if any
   - **LLM proposed new category** (`proposed_key` / description / why), if stored
3. **Proposals** — approve brand-new taxonomy keys (skips messages already resolved)  
   Actions: `[e]xisting label` · `[a]pprove new` · `[r]eject` · `[s]kip`

#### Picking an existing label

Labels print with indexes:

```text
Active labels:
   1. account-statement
  ...
  11. payment-sent ←
Label number (or key) [11]:
```

Enter `11` (or the kebab-case key).

#### Guidance

- Prefer **existing** labels when the mail clearly fits the seed taxonomy.
- Use **new category** only for recurring patterns you’ll see again.
- Reject placeholder proposals; rename if you approve.
- Human corrections store `predicted_key` + `final_key` for future evals/RAG.

---

## Inspecting SQLite

```bash
DB="$HOME/Library/Application Support/tagsmith/tagsmith.db"   # macOS typical
sqlite3 "$DB"
```

Useful queries:

```sql
SELECT id, dry_run, counts_json FROM runs ORDER BY id DESC LIMIT 5;

SELECT subject, state, applied_label_key FROM messages ORDER BY updated_at DESC LIMIT 20;

SELECT m.subject, c.source, c.label_key, c.predicted_key, c.final_key,
       c.confidence, c.proposed_key, c.rationale
FROM classifications c
JOIN messages m ON m.gmail_id = c.gmail_id
ORDER BY c.id DESC
LIMIT 20;

SELECT id, suggested_key, status FROM proposals;
```

Confirm path:

```bash
uv run python -c "from tagsmith.config import get_settings; print(get_settings().database_url)"
```

---

## Typical daily loop

```bash
uv run tagsmith sync --apply          # up to 50 new unread
uv run tagsmith review                # clear holds / proposals
```

Check Gmail left sidebar under **`AI/`**.

---

## Custom rules

Edit `~/.config/tagsmith/rules.yaml` (see builtin schema in
`src/tagsmith/classify/builtin_rules.yaml`). User rules override builtin by `name`.

After changing rules, reprocess if you want old unread decisions recomputed:

```bash
uv run tagsmith sync --apply --reprocess --limit 50
```
