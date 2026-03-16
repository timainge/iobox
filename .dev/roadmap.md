# Roadmap: iobox

- **Updated**: 2026-03-16
- **Immediate target**: E-discovery PoC demo — Gmail + Google Calendar + Google Drive, read-only, across multiple accounts
- **Strategic target**: Multi-provider personal workspace context tool (emails, calendar events, files) usable as CLI, Python library, and MCP server

---

## Autonomous Execution

This roadmap is wired to a Claude Code Stop hook (`.claude/hooks/roadmap-checker.py`) that automatically queues the next unblocked task when Claude finishes a session. To run:

```bash
# Start Claude in the repo — the hook drives sequential task completion
claude

# Limit to N autonomous sessions (default: unlimited)
ROADMAP_MAX_BLOCKS=20 claude

# Check progress at any time
grep "^status:" .dev/task-*.md
```

The hook selects tasks by: `status: ready` → all `depends_on` marked `done` → highest priority / lowest milestone first.

**To pause**: set `status: in-progress` on the active task. The hook won't pick up `in-progress` tasks, but also won't mark them done — you resume manually.

---

## Definition of Done

Every task must satisfy all of the following before its frontmatter is updated to `status: done`:

### Implementation
- [ ] All files listed in the task's **Files** table exist and match the spec
- [ ] All abstract methods / ABCs have concrete implementations
- [ ] No `NotImplementedError` stubs left in shipped code (stubs in `get_sync_state` / `get_new_events` are acceptable for MVP)

### Tests
- [ ] `make test` passes with **zero failures** — no skips on newly added tests
- [ ] Unit tests cover all normalizer functions (`_google_event_to_event`, `_drive_file_to_file`, etc.)
- [ ] Partial-failure / error paths are tested (not just happy path)
- [ ] Contract tests added for new provider ABCs in `test_provider_contract.py`
- [ ] No real API calls in unit or integration tests — all external calls mocked via `_fn=None` injection

### Quality
- [ ] `make type-check` passes with **no new mypy errors**
- [ ] `make lint` passes (ruff, no warnings)
- [ ] `make check` (all three combined) passes clean

### Backward compatibility
- [ ] All pre-existing tests still pass — zero regressions
- [ ] `EmailProvider`, `EmailData`, `EmailQuery` signatures unchanged (unless task explicitly modifies them)

### Documentation
- [ ] `CLAUDE.md` updated if the task adds a new module, changes architecture, or introduces a new invariant
- [ ] `README.md` updated if the task adds user-facing CLI commands or changes install instructions
- [ ] A doc page added/updated in `docs/` if the task adds a new provider or major feature
- [ ] Task frontmatter set to `status: done`

### Milestone 0 additional gate (PoC demo readiness)
When all milestone 0 tasks are `done`, verify the demo script works end-to-end:
```bash
# Authenticate a Gmail account with messages + calendar + drive
iobox space create personal
iobox space add gmail YOUR@GMAIL.COM --messages --calendar --drive --read

# Cross-type search
iobox search "Q4 planning" --workspace
# Expected: returns emails + events + files in one response
```

---

## Strategic Direction

Iobox is expanding from an email-only tool to a **personal workspace context tool** — a single interface for searching, retrieving, and exporting email messages, calendar events, and files across multiple accounts and providers.

### Why this matters

The killer use case is aggregate, cross-type queries:
> "Show me everything related to the Q4 planning project" → returns the email thread, the calendar invite, and the shared document in one call.

This is especially powerful as an MCP server: one context provider that understands your full workspace, not three separate tools requiring orchestration above them.

### Design principles agreed

1. **Workspace is the primary abstraction** — not the provider. Users think in workspaces ("personal", "work"), not provider instances.
2. **Three independent provider ABCs** — `MessageProvider`, `CalendarProvider`, `FileProvider`. Never a monolithic `WorkspaceProvider`. Mix-and-match across ecosystems is a valid and common use case (Gmail email + OneDrive files).
3. **Read-only first for calendar and files** — mutations are where providers diverge most (calendar invite semantics, file conflict resolution). Ship read fast, add write later behind `--mode standard`.
4. **Google-first, O365 second** — for the demo MVP and because Google shares auth across all three resource types cleanly (one credential, three services).
5. **Auth reuse within an ecosystem** — `GmailProvider`, `GoogleCalendarProvider`, and `GoogleDriveProvider` share one `GoogleAuth` object. Same for Microsoft.
6. **Partial failure is not total failure** — if one account's auth expires, other providers/accounts still return results.

---

## Architecture

### Resource type hierarchy

```
Resource (base TypedDict)
├── id: str
├── provider_id: str        # "gmail" | "google_calendar" | "google_drive" | "outlook" | ...
├── resource_type: Literal["message", "event", "file"]
├── title: str              # subject / event name / filename
├── created_at: str         # ISO 8601
├── modified_at: str
└── url: str | None         # web link to item

Message(Resource)           Event(Resource)             File(Resource)
├── from_: str              ├── start: str              ├── name: str
├── to: list[str]           ├── end: str                ├── mime_type: str
├── cc: list[str]           ├── all_day: bool           ├── size: int
├── thread_id: str          ├── organizer: str          ├── path: str | None
├── snippet: str            ├── attendees: list[...]    ├── parent_id: str | None
├── labels: list[str]       ├── location: str | None    ├── is_folder: bool
├── body: str | None        ├── description: str | None ├── download_url: str | None
├── content_type: str | None├── meeting_url: str | None └── content: str | None
└── attachments: list[...]  ├── status: str
                            └── recurrence: str | None
```

### Provider ABCs

Three independent ABCs in `src/iobox/providers/base.py`:

- **`MessageProvider`** — search, get, batch_get, get_thread, download_attachment; mutations (send, draft, mark_read, archive, trash, tag) behind write-mode gate
- **`CalendarProvider`** — list_events, get_event (readonly initially)
- **`FileProvider`** — list_files, get_file, get_file_content, download_file (readonly initially)

`EmailProvider` → aliased to `MessageProvider` for backward compatibility during migration.

### Query types

```
ResourceQuery (base dataclass)      # text, after, before, max_results
├── MessageQuery(ResourceQuery)     # from_addr, subject, label, has_attachment, raw_query
├── EventQuery(ResourceQuery)       # calendar_id
└── FileQuery(ResourceQuery)        # mime_type, folder_id, shared_with_me
```

### Workspace

```python
@dataclass
class ProviderSlot:
    name: str                   # "gmail-personal", "gmail-work"
    provider: MessageProvider | CalendarProvider | FileProvider
    tags: list[str]             # ["primary", "work"] — for filtering

@dataclass
class WorkspaceSession:
    providers: dict[str, ProviderSession]   # auth state, scopes, sync tokens, last_sync, errors
    active_filter: list[str] | None         # None=all, ["work"]=tagged work only

@dataclass
class Workspace:
    name: str
    message_providers:  list[ProviderSlot]
    calendar_providers: list[ProviderSlot]
    file_providers:     list[ProviderSlot]
    session: WorkspaceSession

    # Aggregate operations — fan out, merge, sort, partial-failure tolerant
    def search_messages(self, query, providers=None, tags=None) -> list[Message]: ...
    def list_events(self, query, providers=None, tags=None) -> list[Event]: ...
    def list_files(self, query, providers=None, tags=None) -> list[File]: ...
    def search(self, query, types=None) -> list[Resource]: ...   # cross-type, MCP killer feature
    def auth_status(self) -> dict[str, ProviderSession]: ...
```

### Config (TOML, per workspace)

```toml
# ~/.iobox/workspaces/personal.toml
[workspace]
name = "personal"

[[messages]]
name = "gmail-personal"
provider = "gmail"
account = "tim@gmail.com"
tags = ["primary"]

[[messages]]
name = "gmail-work"
provider = "gmail"
account = "tim@work.com"
tags = ["work"]

[[calendar]]
name = "gcal-personal"
provider = "google_calendar"
account = "tim@gmail.com"     # reuses gmail auth

[[files]]
name = "gdrive-personal"
provider = "google_drive"
account = "tim@gmail.com"     # reuses gmail auth
```

### Module layout (target)

```
src/iobox/
  providers/
    base.py               # Resource, Message, Event, File, *Query, *Provider ABCs
    gmail.py              # GmailProvider(MessageProvider)
    outlook.py            # OutlookProvider(MessageProvider)
    google_calendar.py    # GoogleCalendarProvider(CalendarProvider)
    outlook_calendar.py   # OutlookCalendarProvider(CalendarProvider)
    google_drive.py       # GoogleDriveProvider(FileProvider)
    onedrive.py           # OneDriveProvider(FileProvider)
  workspace.py            # Workspace, ProviderSlot, WorkspaceSession, ProviderSession
  workspace_config.py     # TOML load/save, workspace discovery
  processing/
    markdown.py           # resource → markdown (Message already done, extend to Event/File)
    summarize.py          # resource → summary str (via Claude)
    embed.py              # resource → float[] (for RAG / semantic search)
  cli.py                  # updated commands (see below)
  auth.py                 # GoogleAuth, MicrosoftAuth shared auth objects
  mcp_server.py           # workspace.search() as primary MCP tool
```

---

## Task Files

Implementation is broken into discrete task files in `.dev/`. Each carries YAML frontmatter (status, priority, dependencies, effort) and full prose for sub-agent execution.

| Task | Title | Milestone | Status |
|------|-------|-----------|--------|
| [task-001](task-001.md) | Space config schema + directory structure | 0 | ready |
| [task-002](task-002.md) | New type hierarchy in providers/base.py | 0 | ready |
| [task-003](task-003.md) | GoogleAuth shared object + scope aggregation | 0 | ready |
| [task-004](task-004.md) | `iobox space` command group | 0 | ready (needs 001+003) |
| [task-005](task-005.md) | GoogleCalendarProvider (read-only) | 0 | ready (needs 002+003) |
| [task-006](task-006.md) | GoogleDriveProvider (read-only) | 0 | ready (needs 002+003) |
| [task-007](task-007.md) | Workspace + WorkspaceSession compositor | 0 | blocked (needs 001+002) |
| [task-008](task-008.md) | processing/ — markdown for Event + File | 0 | ready (needs 002) |
| [task-010](task-010.md) | Workspace-centric CLI commands | 1 | blocked (needs 007) |
| [task-011](task-011.md) | MCP server update with workspace.search() | 1 | blocked (needs 007) |
| [task-012](task-012.md) | OutlookCalendarProvider (read-only) | 2 | ready (needs 002) |
| [task-013](task-013.md) | OneDriveProvider (read-only) | 2 | ready (needs 002) |
| [task-014](task-014.md) | MicrosoftAuth shared object | 2 | blocked (needs 012+013) |
| [task-015](task-015.md) | processing/summarize.py | 3 | ready (needs 002) |
| [task-016](task-016.md) | processing/embed.py + semantic search | 3 | needs-research |
| [task-017](task-017.md) | Email write ops under Workspace | 4 | blocked (needs 010) |
| [task-018](task-018.md) | CalendarProvider write methods | 5 | blocked (needs 005+012) |
| [task-019](task-019.md) | FileProvider write methods | 5 | blocked (needs 006+013) |
| [task-020](task-020.md) | PyPI v1.0.0 release + docs update | deferred | ready |

**Parallel execution waves**: 001+002+003 → 004+005+006+008+012+013 → 007 → 010+011+014 → 015+017 → 018+019

---

## Milestones

### Milestone 0: E-discovery PoC demo ⚡ URGENT
**Goal**: Impressive demo across Gmail + Google Calendar + Google Drive. Read-only. Multi-account aware.

Tasks: [001](task-001.md), [002](task-002.md), [003](task-003.md), [004](task-004.md), [005](task-005.md), [006](task-006.md), [007](task-007.md), [008](task-008.md)

- [ ] Define new type hierarchy in `providers/base.py` — `Resource`, `Email`, `Event`, `File`, query dataclasses, three ABCs (task-002)
- [ ] `GoogleAuth` shared object — one token per Google account, shared across Gmail/GCal/GDrive (task-003)
- [ ] `iobox space` command group — create spaces, add service sessions, OAuth (task-004)
- [ ] Implement `GoogleCalendarProvider` — list_events, get_event (task-005)
- [ ] Implement `GoogleDriveProvider` — list_files, get_file, get_file_content (task-006)
- [ ] Implement `Workspace` + `WorkspaceSession` in `workspace.py` — fan-out search, partial failure (task-007)
- [ ] Space TOML config loader in `space_config.py` (task-001)
- [ ] Extend markdown output to `Event` and `File` in `processing/markdown.py` (task-008)
- [ ] Update `mcp_server.py` — expose `workspace.search()` as a unified cross-type tool
- [ ] CLI: `iobox workspace status`, `iobox events list`, `iobox files list`, `iobox files get`
- [ ] Demo script: authenticate three Gmail accounts + GCal + GDrive, run a cross-type search, output results as markdown

**Demo must show**: Search returning messages + events + files in one call, across at least two Gmail accounts, with markdown output.

### Milestone 1: Architecture cleanup
**Goal**: Tidy the existing email codebase to fit the new abstractions cleanly.

- [ ] Rename `EmailProvider` → `MessageProvider` throughout (remove alias)
- [ ] Move `email_search.py`, `email_retrieval.py`, `email_sender.py` logic fully into provider classes — remove legacy module split
- [ ] Migrate `accounts.py` token storage into `WorkspaceSession` / `workspace_config.py`
- [ ] Update CLI to workspace-centric commands: `iobox messages search`, `iobox messages save`, `iobox workspace auth`, etc.
- [ ] Update `CLAUDE.md` key invariants for new type names
- [ ] Unit tests for `Workspace` fan-out and partial failure behaviour

### Milestone 2: O365 calendar + OneDrive (read-only)
**Goal**: Demo parity with Microsoft stack.

- [ ] Implement `OutlookCalendarProvider` — Graph API `/me/events`, `EventQuery` → OData filter
- [ ] Implement `OneDriveProvider` — Graph API `/me/drive/items`, search via `/me/drive/search`
- [ ] `MicrosoftAuth` shared auth object (reuse across Outlook, OCalendar, OneDrive)
- [ ] Workspace config supports mixing Google and Microsoft providers in one workspace
- [ ] Integration tests with mocked Graph API responses
- [ ] Demo: same e-discovery query running against Outlook + OCalendar + OneDrive

### Milestone 3: Cross-cutting intelligence layer
**Goal**: Make the tool genuinely useful for e-discovery and knowledge work beyond raw retrieval.

- [ ] `processing/summarize.py` — summarize any `Resource` using Claude (claude-haiku-4-5 for speed/cost)
- [ ] `processing/embed.py` — embed resources for semantic search; index to local vector store (sqlite-vec or similar)
- [ ] `workspace.semantic_search()` — query by meaning, not just keyword
- [ ] MCP: expose summarize and semantic_search as tools
- [ ] `iobox save` extended to Event and File (save to markdown with frontmatter)

### Milestone 4: Write operations (messages)
**Goal**: Restore and harden existing write ops under new abstractions (already implemented, needs migration).

- [ ] Message mutations fully working under new `MessageProvider` ABC: send, draft, forward, mark_read, archive, trash, tag
- [ ] Batch operations (already implemented in OutlookProvider, verify in GmailProvider)
- [ ] Mode gate (`--mode standard`) enforced at Workspace level, not just CLI level

### Milestone 5: Write operations (calendar + files)
**Goal**: Round-trip calendar and file management.

- [ ] `CalendarProvider` write methods: create_event, update_event, delete_event, rsvp
- [ ] `FileProvider` write methods: upload_file, update_file, delete_file, create_folder
- [ ] Google and Microsoft implementations
- [ ] Mode gate enforcement

### Deferred: PyPI release & docs
*Was the previous roadmap target — still valid but lower priority than the PoC.*

- [ ] Dry-run: `uv build && twine check dist/*`
- [ ] Tag `v1.0.0`, push — CI publishes to PyPI
- [ ] Update README: PyPI badge, `pip install iobox`, MCP setup snippet
- [ ] MkDocs site live at `timainge.github.io/iobox`

---

## CLI command surface (target)

```bash
# Workspace management
iobox workspace use personal
iobox workspace status
iobox workspace auth [--provider gmail-personal]

# Messages (existing commands, renamed namespace)
iobox messages search -q "from:boss@example.com" [--provider gmail-work] [--tag work]
iobox messages save -q "label:important" -o ./emails
iobox messages send --to x@y.com --subject "Hi" --body "..."

# Events (new, read-only initially)
iobox events list [--after 2026-03-01] [--before 2026-03-31] [--provider gcal-personal]
iobox events get EVENT_ID
iobox events save EVENT_ID -o ./events

# Files (new, read-only initially)
iobox files list [--query "Q4 report"] [--provider gdrive-personal]
iobox files get FILE_ID
iobox files save FILE_ID -o ./docs

# Cross-type (workspace-level)
iobox search "Q4 planning" [--type message] [--type event] [--type file]
```

---

## Key API invariants to preserve

- `Message["from_"]` (underscore) in provider return values; `_email_data_to_dict()` in `cli.py` bridges to `"from"` for markdown/file_manager — do not collapse
- Write ops return `{"message_id": ..., "status": ...}` — not `"id"`
- Outlook searches inbox only; Gmail searches all mail — document this on `MessageQuery`
- Partial failure in `Workspace` aggregate methods must not propagate as exceptions — log and continue
