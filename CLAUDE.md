# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strategic Direction

Iobox is a **personal workspace context tool** — a single interface for searching, retrieving, and exporting email messages, calendar events, and files across multiple accounts and providers.

Key design decisions:
- **Workspace** is the primary user-facing abstraction — not the provider. Users operate against a named workspace (e.g. "personal", "work") that fans out across multiple configured providers.
- **Three independent provider ABCs**: `EmailProvider`, `CalendarProvider`, `FileProvider` — never a monolithic one. Mix-and-match across ecosystems is a valid use case (Gmail + OneDrive).
- **Google-first ordering**: Gmail → Google Calendar → Google Drive → Outlook → O365 Calendar → OneDrive.

## Current State

All provider types and the workspace compositor are implemented and tested (Google providers via live tests; O365 providers via unit tests only — not yet tested against a real M365 tenant).

- Provider ABCs: `EmailProvider`, `CalendarProvider`, `FileProvider` — all with full read + write methods
- `GmailProvider`, `OutlookProvider` — email, read + write
- `GoogleCalendarProvider`, `OutlookCalendarProvider` — calendar, read + write
- `GoogleDriveProvider`, `OneDriveProvider` — files, read + write
- `Workspace` compositor — fans out cross-type search; `space` CLI command group
- `processing/` package — Markdown conversion, Claude summarization, semantic embedding + search
- Full MCP server with workspace-aware tools; CI/CD; PyPI packaging

## Version Policy

**Current version: `0.5.0`** — will remain below `1.0.0` until O365 providers (Outlook email, calendar, OneDrive) are tested end-to-end against a real Microsoft 365 tenant. Do not bump to `1.0.0` or above until live O365 testing passes.

Set up an M365 dev sandbox for O365 testing: see `.dev/testing-o365.md` for instructions.

## Provider Architecture

Iobox uses an abstract provider layer so multiple backends share a single CLI and MCP surface.

- **`EmailProvider` ABC** — `src/iobox/providers/base.py` defines the interface (search, retrieve, send, label, trash, sync, etc.).
- **`GmailProvider`** — Google Gmail API (`src/iobox/providers/google/email.py`). Default provider.
- **`OutlookProvider`** — Microsoft 365 / Exchange Online via the `O365` library (`src/iobox/providers/o365/email.py`).

### Selecting a provider

```bash
iobox --provider outlook search -q "from:boss@example.com"
export IOBOX_PROVIDER=outlook
```

### Outlook setup

```bash
pip install 'iobox[outlook]'
```

Required env vars:
```
OUTLOOK_CLIENT_ID=<your Azure app client ID>
OUTLOOK_TENANT_ID=<your tenant ID or "common">
```

## Architecture

### Provider layer (primary abstraction)

```
src/iobox/providers/
  base.py                # Provider ABCs: EmailProvider, CalendarProvider, FileProvider
                         # Type hierarchy: Resource, Email, Event, File, AttendeeInfo
                         # Query types: EmailQuery, EventQuery, FileQuery
  __init__.py            # get_provider() factory + type re-exports

  google/
    __init__.py
    auth.py              # GoogleAuth — one token per (account, scope-tier), legacy migration
    email.py             # GmailProvider
    calendar.py          # GoogleCalendarProvider
    files.py             # GoogleDriveProvider
    _retrieval.py        # Gmail message retrieval and attachment download
    _search.py           # Gmail API search and query parsing
    _sender.py           # Gmail compose, send, forward, draft management

  o365/
    __init__.py
    auth.py              # MicrosoftAuth + get_outlook_account — one token per (account, scopes)
    email.py             # OutlookProvider — Microsoft Graph via O365 library; ImmutableId
    calendar.py          # OutlookCalendarProvider
    files.py             # OneDriveProvider
```

### Workspace layer

- **`src/iobox/workspace.py`**: `Workspace` compositor — fans out search across provider slots; `ProviderSlot`, `WorkspaceSession`
- **`src/iobox/space_config.py`**: Space config schema and I/O — `SpaceConfig`, `ServiceEntry`; `load_space()`, `save_space()`, `list_spaces()`, `get_active_space()`, `set_active_space()`. Space configs live at `~/.iobox/workspaces/NAME.toml`.

### Processing modules

- **`src/iobox/processing/markdown.py`**: Unified resource→Markdown converter for Event, File, and Email types (`convert_event_to_markdown`, `convert_file_to_markdown`)
- **`src/iobox/processing/markdown_converter.py`**: Email-specific Markdown conversion — HTML→Markdown, YAML frontmatter, thread formatting (`convert_email_to_markdown`, `convert_thread_to_markdown`)
- **`src/iobox/processing/file_manager.py`**: Save resources to disk, dedup, attachment handling, `SyncState`
- **`src/iobox/processing/summarize.py`**: Claude-powered resource summarization (`pip install 'iobox[ai]'`)
- **`src/iobox/processing/embed.py`**: Embedding backends (OpenAI, Voyage, local) + `ResourceIndex` (sqlite-vec) + `embed_resources()` + `semantic_search()` (`pip install 'iobox[semantic]'`)

### Shared modules

- **`src/iobox/cli.py`**: Typer CLI — all commands route through provider interface; includes `space`, `events`, `files`, and `workspace` command groups
- **`src/iobox/__main__.py`**: Package entry point — `python -m iobox` delegates to `cli.app()`
- **`src/iobox/modes.py`**: Access mode definitions (readonly/standard/dangerous); `get_google_scopes()`, `get_microsoft_scopes()`
- **`src/iobox/accounts.py`**: Active account name for token namespacing
- **`src/iobox/utils.py`**: Filename generation and text slugifying (`create_markdown_filename`, `slugify_text`)
- **`src/iobox/mcp_server.py`**: FastMCP server exposing iobox tools (workspace-aware)

### Key Dependencies

- **Google APIs**: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
- **Microsoft**: `O365` (optional, bundles MSAL) — `pip install 'iobox[outlook]'`
- **CLI**: `typer`
- **Content**: `html2text`, `PyYAML`
- **MCP**: `mcp` (optional) — `pip install 'iobox[mcp]'`
- **Config**: `python-dotenv`

## Development Commands

```bash
# Full pre-commit check (lint + type-check + tests)
make check

make lint        # ruff linting
make fmt         # ruff formatting
make type-check  # mypy type checking
make test        # unit + integration tests

# Testing
uv run pytest                          # all tests with coverage
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/unit/test_auth.py

# Install
uv sync
pip install -e .
```

## Authentication

### Gmail / Google APIs

1. Create a Google Cloud project with Gmail API enabled
2. Download OAuth credentials as `credentials.json` in project root (or `CREDENTIALS_DIR`)
3. First run triggers OAuth flow; subsequent runs use cached tokens

Tokens stored per account and per scope tier at `$CREDENTIALS_DIR/tokens/{account}/`:
- `token_readonly.json` — gmail.readonly scope
- `token_standard.json` — gmail.modify + gmail.compose scopes

Switching `--mode readonly` ↔ `--mode standard` never destroys an existing token. A broader token is accepted in readonly mode. Legacy `token.json` files are auto-migrated on first run.

If `GMAIL_TOKEN_FILE` is set to a non-default value, the legacy single-file behavior is used instead.

### Microsoft 365 / Outlook

Set `OUTLOOK_CLIENT_ID` and optionally `OUTLOOK_TENANT_ID` (defaults to `"common"`). Token stored at `$CREDENTIALS_DIR/tokens/{account}/microsoft_token.txt` (namespaced by account email). Legacy `o365_token.txt` files are auto-migrated on first use.

## Key Invariants

Knowing these prevents subtle bugs when working across providers or converters:

- **`EmailData["from_"]` vs `"from"`** — Providers store the sender under `from_` (underscore) to avoid the Python keyword `from`. However `markdown_converter.py` and `file_manager.py` expect `from` (no underscore). The `_email_data_to_dict()` helper in `cli.py` (≈ line 48–58) bridges this — do not change the key in `EmailData` or provider return values.
- **Outlook searches inbox only; Gmail searches all mail** — `OutlookProvider` queries `inbox_folder()` by default. Emails in Sent, Archive, or custom folders may not be returned.
- **Outlook message IDs use ImmutableId** — Stable across folder moves. Set via `Prefer: IdType="ImmutableId"` header on all Graph requests.
- **Write ops return `{"message_id": ..., "status": ...}` — not `"id"`** — All provider write methods return a dict with `message_id` as the ID key. CLI code must read `result.get("message_id", ...)`.
- **Partial failure in Workspace fan-out must not propagate as exceptions** — `Workspace.search()` and `list_events()`/`list_files()` catch per-slot exceptions, log them, and continue. Never let one provider bring down the whole query.

## Configuration

Environment variables (`.env` or shell):

| Variable | Default | Purpose |
|---|---|---|
| `IOBOX_PROVIDER` | `gmail` | Active provider (`gmail` or `outlook`) |
| `IOBOX_MODE` | `standard` | Access mode: `readonly`, `standard`, `dangerous` |
| `IOBOX_ACCOUNT` | `default` | Account profile name for token namespacing |
| `CREDENTIALS_DIR` | cwd | Directory for credential and token files |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | Path to Google OAuth credentials |
| `GMAIL_TOKEN_FILE` | `token.json` | Override token path (disables multi-profile) |
| `OUTLOOK_CLIENT_ID` | — | Azure app client ID (required for Outlook) |
| `OUTLOOK_TENANT_ID` | `common` | Azure tenant ID |

## CLI Commands

```bash
# Workspace / Space management
iobox space create personal
iobox space add google you@gmail.com --email --calendar --drive --read
iobox space add o365 corp@company.com --email --calendar
iobox space list
iobox space status
iobox space use NAME
iobox space login N|SLUG   # re-auth a service session
iobox space logout N|SLUG  # revoke token

# Email (legacy top-level)
iobox search -q "from:newsletter@example.com" -m 20 -d 3
iobox save --message-id MESSAGE_ID -o ./output
iobox save -q "label:important" --max 50 -d 14 -o ./emails
iobox send --to recipient@example.com --subject "Hello" --body "Message"
iobox forward --message-id MESSAGE_ID --to recipient@example.com

# Drafts
iobox draft-create --to recipient@example.com -s "Subject" -b "Body"
iobox draft-list --max 10
iobox draft-send --draft-id DRAFT_ID
iobox draft-delete --draft-id DRAFT_ID

# Label / Trash
iobox label --message-id MSG_ID --star
iobox label -q "from:x@y.com" --archive
iobox trash --message-id MSG_ID

# Calendar
iobox events list --after 2026-01-01 --before 2026-03-31
iobox events get EVENT_ID
iobox events save EVENT_ID -o ./output
iobox events create --title "Standup" --start "2026-04-01T09:00" --end "2026-04-01T09:30"
iobox events delete EVENT_ID
iobox events rsvp EVENT_ID --response accept

# Files
iobox files list --query "Q4 report" --provider my-drive
iobox files get FILE_ID
iobox files save FILE_ID -o ./output
iobox files upload ./report.pdf --folder-id FOLDER_ID
iobox files delete FILE_ID
iobox files mkdir "New Folder"

# Utility
iobox auth-status
iobox version
```

## Testing Strategy

- **Unit tests**: Mock provider/API responses with `pytest-mock` (`tests/unit/`)
- **Integration tests**: End-to-end workflow testing (`tests/integration/`)
- **Live tests**: CLI scenarios against a real Gmail account (`tests/live/`)
- **Coverage**: HTML reports in `htmlcov/` via `pyproject.toml` config
- **Fixtures**: Centralized mock responses in `tests/fixtures/mock_responses.py` and `tests/fixtures/mock_outlook_responses.py`
- **Test grouping**: Prefer `class Test<Feature>` within test files — see `tests/unit/test_outlook_provider.py` as the canonical style

```bash
# Live tests (requires authenticated Gmail)
python tests/live/run_tests.py
python tests/live/cleanup.py  # clean up test emails after a run
```

For Outlook live testing guidance (what mocks can't verify, M365 dev sandbox setup): see the Version Policy section above and set up an M365 dev sandbox.

## File Output Format

Emails saved as markdown files with:
- YAML frontmatter: `from`, `to`, `subject`, `date`, `message_id`, `labels`
- Markdown-converted body
- Attachments in `attachments/{email_id}/` subdirectories
