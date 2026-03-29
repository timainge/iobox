# Roadmap: iobox

- **Updated**: 2026-03-18
- **Current state**: v1.0.0 complete — all planned milestones shipped

---

## What was built

Iobox expanded from a Gmail-only email tool to a **multi-provider personal workspace context tool** — a single interface for searching, retrieving, and exporting email messages, calendar events, and files across Google and Microsoft 365 accounts.

### Core infrastructure
- **Provider ABCs** (`providers/base.py`): `EmailProvider`, `CalendarProvider`, `FileProvider` with full read + write method signatures; `Resource`, `Email`, `Event`, `File` type hierarchy; `EmailQuery`, `EventQuery`, `FileQuery` dataclasses
- **Workspace compositor** (`workspace.py`): `Workspace`, `ProviderSlot`, `WorkspaceSession` — fans out queries across all registered providers with partial-failure tolerance
- **Space config** (`space_config.py`): TOML-based workspace configs at `~/.iobox/workspaces/NAME.toml`; `load_space()`, `save_space()`, `list_spaces()`, `set_active_space()`

### Provider subpackages (restructured 2026-03-18)
```
providers/
  google/        auth.py, email.py, calendar.py, files.py, _retrieval.py, _search.py, _sender.py
  o365/          auth.py, email.py, calendar.py, files.py
  base.py        ABCs and type hierarchy
  __init__.py    get_provider() factory
```

- **`GmailProvider`** — Gmail API, full read + write (search, get, send, draft, label, trash, sync)
- **`OutlookProvider`** — Microsoft Graph via O365 library, full read + write, ImmutableId, batch ops
- **`GoogleCalendarProvider`** — Google Calendar API v3, read + write (create, update, delete, RSVP)
- **`OutlookCalendarProvider`** — O365 calendar, read + write
- **`GoogleDriveProvider`** — Google Drive API v3, read + write (upload, delete, mkdir)
- **`OneDriveProvider`** — O365 file storage, read + write
- **`GoogleAuth`** — shared credential manager, one token per (account, scope-tier), legacy token migration
- **`MicrosoftAuth`** — shared credential manager, one token per (account, scopes)

### Processing layer (`processing/`)
- **`markdown.py`** — unified `Resource → Markdown` converter for Email, Event, and File
- **`markdown_converter.py`** — HTML→Markdown and YAML frontmatter
- **`file_manager.py`** — save resources to disk, dedup, attachment handling
- **`summarize.py`** — Claude-powered resource summarization (`pip install 'iobox[ai]'`)
- **`embed.py`** — embedding backends (OpenAI, Voyage, local) + `ResourceIndex` (sqlite-vec) + `semantic_search()` (`pip install 'iobox[semantic]'`)

### CLI & MCP
- **`iobox space`** command group — create/add/list/status/use/login/logout
- **`iobox events`** command group — list, get, save, create, delete, rsvp
- **`iobox files`** command group — list, get, save, upload, delete, mkdir
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

## What's next

No planned tasks. Possible future directions:

- **Real O365 live testing** — set up M365 dev sandbox (see `.dev/testing-o365.md`)
- **Docs site** — MkDocs at `timainge.github.io/iobox`
- **PyPI publish** — tag `v1.0.0`, CI publishes (task-020 is done but may need a real run)
- **Semantic search improvements** — hybrid keyword + embedding ranking

---

## Autonomous execution hook

`.claude/hooks/roadmap-checker.py` — scans `.dev/task-*.md` for `status: ready` tasks and queues the next one when Claude finishes a session. Currently idle (no task files).
