# Changelog

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
