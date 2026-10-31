# Changelog

## 0.7.0

The hardening release. A full code review (six parallel reviewers, ~75 findings plus follow-ups) and fixes across every layer — security, data correctness, sync, workspaces, and a rewrite of the Microsoft 365 providers against the real python-o365 API. The docs site was reorganised into Get Started / MCP / CLI / SDK / Reference. The issue register is in `.dev/issues.md`.

**Breaking / behaviour changes**
- **Sending mail always needs `dangerous` mode.** `draft-send` (CLI) and `send_gmail_draft` (MCP) moved from `standard` to `dangerous`.
- **MCP file access is confined** to `IOBOX_MCP_ROOT` (default `~/iobox`). Every `output_dir`, `output_path`, `attachments` and `local_path` must resolve inside it; `~/.iobox` is always refused; downloads never overwrite.
- **CLI `--mode` gates `events`/`files` subcommands** like the MCP server (`events delete` → `dangerous`; create/rsvp/upload/mkdir/delete → `standard`).
- **Gmail write methods return `{"message_id", "status", ...}`** (draft id for drafts) instead of raw API dicts.
- **Microsoft 365 tokens are per tier**: `~/.iobox/tokens/<account>/microsoft_token_{readonly|standard}.txt`. Legacy files migrate to `standard`; readonly sessions re-consent with read-only scopes.
- **`save --sync` / `save_emails_by_query(sync=True)`** re-run the query from the day before the last complete run and skip saved IDs (previously: every new mailbox message, ignoring the query). Changing the query starts a full sync.
- **Email `--end-date` is inclusive**; calendar date-only `before` is inclusive and interpreted in local time.
- **Fan-out results carry `slot`**; failed slots are reported (`Workspace.last_errors`, MCP `{"slot", "error"}` entries, CLI warnings); unknown `--provider`/`provider` slots are errors; `max_results` caps the merged total.
- **MCP batch tools** require a non-empty query and `days >= 1`, cap `max_results` at 100, and report per-item `succeeded`/`failed`.
- **A misspelled or broken workspace is an error** in MCP instead of silently using legacy single-account Gmail.
- **Removed:** `Workspace.auth_status()`, `_check_write_mode()`, `WorkspaceSession`; MCP `save_email(include_spam_trash)` and `save_thread(prefer_html, include_spam_trash)`; `check_auth` no longer returns live mailbox counts.
- **Email frontmatter** is emitted with `yaml.safe_dump` (values may now be quoted).

**Security**
- Token files written 0600 (dirs 0700), atomically; workspace names and account strings validated before use in paths.
- The MCP server never starts an interactive OAuth flow (`iobox.auth_policy`).
- Drive query values fully escaped; attachment paths and filenames sanitised and contained.

**Correctness**
- Email frontmatter is valid YAML for any subject (`Re: …` previously broke parsers).
- Results sorted by parsed dates (were sorted as text); cross-type search sorts events by start, files by modified time.
- Gmail: per-account label cache with refresh; bodies decoded by charset; multipart bodies joined; non-ASCII headers/filenames encoded correctly; HTML mail gets a real text/plain alternative; scope coverage checked on cached tokens; revoked refresh tokens recovered.
- Google Calendar: local-time bounds, no hard-coded UTC on create, `update_event` field mapping, paged sync tokens.
- Microsoft 365: rewritten against python-o365 2.1.9 — ImmutableId on every request, real query builder and KQL `$search`, correct calendar/RSVP/OneDrive APIs, requested scopes actually honoured, attachments downloaded, delta 410 handling, `$batch` per-item errors and 429 retries, large-attachment upload sessions, Deleted Items/Junk excluded unless asked.
- Filenames use the message date; unique, id-suffixed event/file exports; duplicate detection reads frontmatter `message_id`.
- Slugs are unique per space; config file name is authoritative; malformed configs give clean errors; atomic config writes.
- Embedding index records backend/model/dimensions and refuses mismatches; local backend fixed; consistent cosine scores. (Building an index from the CLI/MCP is not yet available — see `.dev/specs/indexed-search.md`.)
- No more `logging.basicConfig` at import.

**Developer**
- O365 tests drive the real python-o365 classes with a fake Graph HTTP layer; O365 and MCP are dev dependencies and installed in CI.
- pytest live logging disabled (it closed click's CliRunner output in CLI tests).

---

## 0.6.0

The pluggable-storage release. iobox's OAuth tokens are no longer hard-coded
to live as JSON files on disk — embedders can inject any backend that
implements the new `TokenStore` protocol. The CLI is unchanged; the default
is the same on-disk layout as 0.5.0.

**TokenStore protocol**
- New `iobox.providers.token_store.TokenStore` Protocol with `load` / `save` / `delete`.
- New `FilesystemTokenStore(credentials_dir)` — preserves the historical
  `<credentials_dir>/tokens/<account>/token_<tier>.json` layout. Default for
  `GoogleAuth` and `MicrosoftAuth`.
- `GoogleAuth.__init__` accepts an optional `token_store` argument; when
  omitted, falls back to `FilesystemTokenStore(credentials_dir)`.
- `MicrosoftAuth.__init__` accepts an optional `token_store`; when set,
  routes O365's token cache through a `TokenStoreTokenBackend` adapter
  (BaseTokenBackend → TokenStore). When omitted, falls back to O365's
  built-in `FileSystemTokenBackend` so existing on-disk tokens keep
  working.
- Server embedders (e.g. Nexus) implement `PostgresTokenStore` to scope
  tokens per authenticated user with at-rest encryption.

**Compatibility**
- Existing on-disk tokens load unchanged.
- `GMAIL_TOKEN_FILE` legacy override still applies for the default
  filesystem store; custom stores see all reads/writes flow through them.

---

## 0.5.0

The workspace release. iobox is no longer a single-provider tool — it's a multi-account, multi-service workspace that fans out queries across everything you've configured.

**Workspace layer**
- `Workspace` compositor fans out search across all registered provider slots simultaneously; per-slot failures are caught and logged, never fatal
- Named spaces configured in `~/.iobox/workspaces/NAME.toml`; `iobox space` command group to create, add, list, use, login, logout, and remove service sessions
- `WorkspaceSession` and `ProviderSlot` model the active configuration at runtime

**Calendar providers**
- `GoogleCalendarProvider` — list, get, create, update, delete, RSVP
- `OutlookCalendarProvider` — list, get, create, update, delete, RSVP
- `iobox events` CLI command group

**File providers**
- `GoogleDriveProvider` — search, list, get, download, upload, delete, mkdir
- `OneDriveProvider` — search, list, get, download, upload, delete, mkdir
- `iobox files` CLI command group

**Processing layer**
- Unified `Resource → Markdown` converter for Email, Event, and File types
- `FileManager` — save resources to disk with deduplication and attachment handling
- AI summarization via Claude (`pip install 'iobox[ai]'`)
- Semantic search — embedding backends (OpenAI, Voyage, local) + `ResourceIndex` backed by sqlite-vec (`pip install 'iobox[semantic]'`)

**MCP server**
- All workspace tools exposed via FastMCP; workspace-aware context
- `iobox-mcp` CLI entry point for Claude Desktop integration

---

## 0.4.0

Provider abstraction and Microsoft 365 email support.

- Introduced `EmailProvider`, `CalendarProvider`, and `FileProvider` ABCs in `providers/base.py` with a shared `Resource` → `Email` / `Event` / `File` type hierarchy and `EmailQuery`, `EventQuery`, `FileQuery` dataclasses
- `OutlookProvider` — Microsoft 365 / Exchange Online email via the `O365` library; ImmutableId for stable message IDs across folder moves; inbox search, full read + write parity with Gmail
- `GoogleAuth` — per-account, per-scope-tier token storage with legacy `token.json` migration
- `MicrosoftAuth` — per-account MSAL token storage with legacy `o365_token.txt` migration
- `get_provider()` factory in `providers/__init__.py`
- Multi-account token namespacing via `IOBOX_ACCOUNT` / `--account` flag

---

## 0.3.0

MCP server and packaging.

- MCP server built on FastMCP — all Gmail operations exposed as tools for Claude Desktop, Cursor, and other MCP clients
- Full CLI parity in MCP: search, get, save, send, forward, draft management, label management, trash operations, auth check
- Batch MCP tools for forward and trash operations
- `pip install 'iobox[mcp]'` optional extra
- Replaced `setup.py` with `pyproject.toml` (hatchling); added optional extras for `outlook`, `mcp`, `ai`, `semantic`, `dev`
- GitHub Actions CI — lint (ruff), type-check (mypy), tests (pytest + coverage)
- GitHub Actions release workflow — trusted publishing to PyPI on `v*` tags

---

## 0.2.0

Full Gmail read + write surface.

- `send` — plain text and HTML email with attachments
- `forward` — forward a message with an optional note; batch forward by query
- `draft-create`, `draft-list`, `draft-send`, `draft-delete`
- `label` — add/remove labels, star, archive; batch label operations by query
- `trash` — move to trash / restore; batch trash by query
- Thread export — save an entire thread as a single Markdown file
- Batch message fetching via Gmail's `batchGet` API
- Incremental sync via Gmail history API (`--sync` flag on `save`)
- HTML email rendering — inline styles stripped, links and tables preserved
- Attachment sending from local file paths
- Search pagination fix for result sets larger than one page

---

## 0.1.0

Initial release.

- Gmail search with flexible query syntax and date filtering
- Email to Markdown conversion with YAML frontmatter
- HTML to Markdown conversion (links, tables, lists, formatting)
- Attachment downloads with type filtering
- Duplicate detection to avoid re-downloading emails
- CLI with `search`, `save`, `auth-status`, and `version` commands
