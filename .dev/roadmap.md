# Roadmap: iobox

- **Updated**: 2026-03-19
- **Version**: 0.5.0 — will reach 1.0.0 once O365 providers are live-tested

---

## What was built (v0.5.0)

Iobox is a **multi-provider personal workspace context tool** — a single interface for searching, retrieving, and exporting email, calendar events, and files across Google and Microsoft 365 accounts.

### Core infrastructure
- **Provider ABCs** (`providers/base.py`): `EmailProvider`, `CalendarProvider`, `FileProvider` with full read + write signatures; `Resource`, `Email`, `Event`, `File` type hierarchy; `EmailQuery`, `EventQuery`, `FileQuery` dataclasses
- **Workspace compositor** (`workspace.py`): `Workspace`, `ProviderSlot`, `WorkspaceSession` — fans out queries across all registered providers with partial-failure tolerance
- **Space config** (`space_config.py`): TOML-based workspace configs at `~/.iobox/workspaces/NAME.toml`

### Provider subpackages
```
providers/
  google/        auth.py, email.py, calendar.py, files.py, _retrieval.py, _search.py, _sender.py
  o365/          auth.py, email.py, calendar.py, files.py
  base.py        ABCs and type hierarchy
  __init__.py    get_provider() factory
```

- **`GmailProvider`** — full read + write (search, get, send, draft, label, trash, sync)
- **`OutlookProvider`** — Microsoft Graph via O365 library, full read + write, ImmutableId, batch ops
- **`GoogleCalendarProvider`** — read + write (create, update, delete, RSVP)
- **`OutlookCalendarProvider`** — read + write
- **`GoogleDriveProvider`** — read + write (upload, delete, mkdir)
- **`OneDriveProvider`** — read + write
- **`GoogleAuth`** — one token per (account, scope-tier), legacy migration
- **`MicrosoftAuth`** — one token per (account, scopes), legacy migration

### Processing layer (`processing/`)
- **`markdown.py`** — unified `Resource → Markdown` converter for Email, Event, and File
- **`markdown_converter.py`** — HTML→Markdown and YAML frontmatter
- **`file_manager.py`** — save resources to disk, dedup, attachment handling
- **`summarize.py`** — Claude-powered summarization (`pip install 'iobox[ai]'`)
- **`embed.py`** — embedding backends (OpenAI, Voyage, local) + `ResourceIndex` (sqlite-vec) + `semantic_search()` (`pip install 'iobox[semantic]'`)

### CLI & MCP
- **`iobox space`** — create/add/list/status/use/login/logout
- **`iobox events`** — list, get, save, create, delete, rsvp
- **`iobox files`** — list, get, save, upload, delete, mkdir
- **`iobox search`** — workspace-level cross-type search
- **MCP server** — all workspace tools exposed via FastMCP; workspace-aware

---

## Architecture invariants

- **`EmailData["from_"]`** (underscore) in provider return values — never change
- **Outlook searches inbox only; Gmail searches all mail** — documented on `EmailQuery`
- **Write ops return `{"message_id": ..., "status": ...}`** — not `"id"`
- **Partial failure in Workspace fan-out must not propagate** — catch per-slot, log, continue
- **Three independent provider ABCs** — never a monolithic one; mix-and-match is a valid use case
- **Google-first ordering**: Gmail → GCal → GDrive → Outlook → O365Cal → OneDrive


---

### TASK-B: Docs site (multi-sprint, mkdocs-shadcn)

**Goal**: Publish a docs site at `timainge.github.io/iobox` using the mkdocs-shadcn pattern.

Use the `/mkdocs-shadcn` skill for setup and theming guidance.

**Sprint 1 — scaffold and deploy**:
1. `pip install mkdocs mkdocs-material` (or shadcn theme if available)
2. Create `docs/` with at minimum: `index.md`, `quickstart.md`, `workspace-guide.md`, `providers.md`, `cli-reference.md`, `mcp-server.md`
3. Configure `mkdocs.yml` with nav, theme, and GitHub Pages settings
4. Add `docs` job to `.github/workflows/` to deploy on push to `main`
5. Verify site builds locally with `mkdocs serve`

**Sprint 2 — content**:
- `workspace-guide.md` — full workspace setup, multi-account, fan-out search
- `providers.md` — per-provider setup, OAuth flows, scope tiers
- `cli-reference.md` — complete command reference (copy from CLAUDE.md, expand)
- `mcp-server.md` — Claude Desktop config, available tools, workspace-aware mode

**Sprint 3 — polish**:
- Landing page hero, card grid for feature overview
- Dark mode toggle
- Search integration

---


## Autonomous execution hook

`.claude/hooks/roadmap-checker.py` — scans `.dev/task-*.md` for `status: ready` tasks and queues the next one when Claude finishes a session. Currently idle (no task files). See `.claude/hooks/README.md` for operating instructions.
