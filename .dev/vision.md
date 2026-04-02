# Vision: Going Public — Portfolio Launch

- **Context**: Conference week of 2026-04-07. Goal is a public GitHub repo + live docs site you can hand someone a URL to.
- **Current state**: Private repo at `timainge/iobox`, v0.5.0, docs site scaffolded but not deployed, PyPI not yet published.

---

## What "done" looks like

- `github.com/timainge/iobox` is public
- `timainge.github.io/iobox` loads and looks good
- `pip install iobox` works
- README pitch is tight — someone who doesn't know you can understand it in 60 seconds
- You have a 2-minute live demo you can run from your laptop

---

## Step 1 — Secrets audit (30 min) — do this first

The repo must have zero secrets before going public. Gitignore already covers `credentials.json`, `token.json`, `.env` — but verify nothing slipped through in the git history.

```bash
# Check for secrets in current tracked files
git ls-files | xargs grep -l "client_secret\|client_id\|AIza\|ya29\." 2>/dev/null

# Scan git history for credential patterns
git log --all --full-history -- "*.json" | head -20
git log -p --all -- credentials.json token.json .env 2>/dev/null | grep -E "client_secret|access_token" | head -20
```

If anything surfaces, use `git filter-repo` to scrub it before going public. Do not skip this step.

Also double-check `pyproject.toml` and any `.github/workflows/*.yml` for hardcoded values.

---

## Step 2 — README tightening (1 hr)

The README is already solid. Three targeted improvements:

**a) Sharpen the opening hook**

The current opener ("A personal workspace context tool — search, retrieve, and export...") is accurate but passive. Lead with the problem and the MCP angle, since that's what's interesting in 2026:

> Your email, calendar, and files live in five different places. Iobox wires them into a single workspace — searchable from the CLI, or directly from Claude via MCP.

**b) Add a "demo" GIF or screenshot**

A 30-second terminal recording of `iobox space status` + `iobox search -q "project proposal"` returning results does more than any paragraph. Use `vhs` or `asciinema` to record it, embed in README.

**c) Add a "Status" badge row with honest caveats**

```markdown
> **Status**: Google providers (Gmail, Calendar, Drive) are live-tested. Microsoft 365 providers are implemented but not yet tested against a real tenant — O365 users should expect rough edges.
```

This is honest without being apologetic. It signals engineering maturity.

---

## Step 3 — Docs site deploy (2 hr)

The mkdocs config is in place and the content is largely written. Steps to get it live:

**a) Verify local build is clean**

```bash
mkdocs serve -f docs/mkdocs.yml
# walk through every page, check for broken links and placeholder content
```

**b) Add GitHub Pages workflow**

Create `.github/workflows/docs.yml`:

```yaml
name: Deploy docs

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mkdocs mkdocs-material
      - run: mkdocs build -f docs/mkdocs.yml
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site/
      - uses: actions/deploy-pages@v4
```

**c) Enable GitHub Pages in repo settings**
- Settings → Pages → Source: GitHub Actions
- First deploy will populate `timainge.github.io/iobox`

**d) Minimum viable content check** — every linked page must exist and not be empty:
- `index.md` ✓ (looks good)
- `getting-started/installation.md` — verify OAuth steps are accurate for a new user
- `getting-started/quickstart.md` — must have a real working example end-to-end
- `workspace-guide.md` — the fan-out concept needs a concrete example
- `mcp/index.md` — Claude Desktop config snippet is the hook; make it copy-pasteable

---

## Step 4 — PyPI publish (1 hr)

```bash
# Build
uv build

# Check the dist
twine check dist/*

# Publish (needs PyPI API token in PYPI_API_TOKEN env var)
twine upload dist/*
```

Add a publish workflow to `.github/workflows/publish.yml` triggered on version tags (`v*`). Then:

```bash
git tag v0.5.0
git push origin v0.5.0
```

This lets CI auto-publish on future releases.

**Verify after publish:**
```bash
pip install iobox==0.5.0
iobox --version
```

---

## Step 5 — Make repo public

GitHub → Settings → Danger Zone → Change visibility → Public.

After making public:
- Watch for any GitHub secret scanning alerts (will email you if secrets detected)
- Pin the repo to your profile
- Add topics: `gmail`, `mcp`, `llm-tools`, `python`, `calendar`, `email`, `productivity`

---

## Step 6 — Conference prep (1 hr)

**The 60-second pitch:**
> "I built a tool called iobox — it's a workspace layer over email, calendar, and files across Google and Microsoft 365. One query fans out across all of them. The interesting part is the MCP server: you wire it into Claude Desktop and your AI assistant can search your inbox, read your calendar, browse Drive — all from the chat window. It's on PyPI if you want to try it."

**The 2-minute live demo (practice this):**
```bash
iobox space status                         # show configured workspace
iobox search -q "project proposal" -m 5   # cross-provider search
iobox events list --after 2026-04-07       # pull upcoming calendar events
```

If wifi is flaky, have a `--help` walkthrough ready as fallback — the command surface alone is impressive.

**The URL to drop:**
- `github.com/timainge/iobox` — primary
- `timainge.github.io/iobox` — if they want the docs

---

## Priority order if time is short

| Step | Time | Skip if rushed? |
|------|------|-----------------|
| 1. Secrets audit | 30 min | **Never skip** |
| 2. README tightening | 1 hr | Do the status callout at minimum |
| 3. Docs deploy | 2 hr | Skip if docs content has gaps — a 404 is worse than no link |
| 4. PyPI publish | 1 hr | Skip if blocked; GitHub URL is enough for a conference |
| 5. Make repo public | 5 min | This is the goal |
| 6. Demo prep | 1 hr | Don't skip — fumbling a live demo is worse than no demo |

**Minimum viable launch**: Steps 1 + 5 + 6. Everything else is polish.
