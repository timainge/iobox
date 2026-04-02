# Iobox

[![PyPI](https://img.shields.io/pypi/v/iobox)](https://pypi.org/project/iobox/)
[![Python](https://img.shields.io/pypi/pyversions/iobox)](https://pypi.org/project/iobox/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Your email is in one place. Your calendar is in another. Your files are somewhere else entirely.

**Iobox puts them in the same box.** One workspace fans out a single query across every account and service simultaneously — email, calendar events, and files — and returns clean Markdown. Use it from the CLI or wire it into Claude Desktop via MCP so your AI assistant can search your inbox directly.

> **Status (v0.5.0):** Google providers (Gmail, Calendar, Drive) are live-tested. Microsoft 365 providers (Outlook, OneDrive) are fully implemented but not yet tested against a real tenant — expect rough edges and please open issues.

## Why

Email inboxes, calendars, and file drives are full of valuable content but it's trapped in silos. Iobox unifies them under a single interface: search across all three resource types at once, save results as structured Markdown files, and expose everything to AI assistants via an MCP server.

## What's implemented

Iobox covers the full read + write surface for email, calendar, and files across Google and Microsoft 365.

### Providers

| Provider | Type | Read | Write |
|---|---|---|---|
| `GmailProvider` | Email | search, list, get, attachments | send, forward, draft, label, trash, sync |
| `OutlookProvider` | Email | search, list, get, attachments | send, forward, draft, label, trash |
| `GoogleCalendarProvider` | Calendar | list, get | create, update, delete, RSVP |
| `OutlookCalendarProvider` | Calendar | list, get | create, update, delete, RSVP |
| `GoogleDriveProvider` | Files | search, list, get, download | upload, delete, mkdir |
| `OneDriveProvider` | Files | search, list, get, download | upload, delete, mkdir |

### Workspace layer

- **Named workspaces** — configure multiple accounts in a `~/.iobox/workspaces/NAME.toml` file
- **Fan-out queries** — one search command queries all registered providers simultaneously; partial failures are logged and skipped
- **`iobox space`** command group — create, add, list, status, use, login, logout

### Processing layer

- **Markdown conversion** — any Email, Event, or File resource exports as structured Markdown with YAML frontmatter
- **File manager** — save resources to disk with deduplication and attachment handling
- **AI summarization** — Claude-powered summaries (`pip install 'iobox[ai]'`)
- **Semantic search** — embedding backends (OpenAI, Voyage, local) + sqlite-vec index (`pip install 'iobox[semantic]'`)

### Access modes

- **readonly** — search and retrieve only; no writes
- **standard** — adds draft creation, labels, calendar and file writes
- **dangerous** — adds send, forward, and trash

### MCP server

Exposes all workspace tools to Claude Desktop and other MCP clients via FastMCP.

## Installation

```bash
pip install iobox
```

### Optional extras

```bash
pip install 'iobox[outlook]'   # Microsoft 365 / Outlook support
pip install 'iobox[mcp]'       # MCP server for Claude Desktop
pip install 'iobox[ai]'        # AI summarization via Claude
pip install 'iobox[semantic]'  # Semantic search (OpenAI embeddings + sqlite-vec)
```

### Install from source

```bash
git clone https://github.com/basementlabs-com/iobox.git
cd iobox
uv sync
```

## Quick Start

### Gmail setup

1. Create a Google Cloud project with **Gmail API**, **Google Calendar API**, and **Google Drive API** enabled
2. Download OAuth credentials (Desktop app type) as `credentials.json` in the project root
3. Run your first command — a browser window opens for OAuth consent:

```bash
iobox search -q "from:boss@example.com" -d 7
```

### Workspace setup (multi-account)

```bash
# Create a workspace
iobox space create personal

# Add Gmail with messages, calendar, and drive access
iobox space add gmail you@gmail.com --messages --calendar --drive --read

# Check status
iobox space status

# Search across all resource types
iobox events list --after 2026-01-01
iobox files list --query "Q4 report"
```

### Outlook / Microsoft 365 setup

```bash
pip install 'iobox[outlook]'
export OUTLOOK_CLIENT_ID=<your Azure app client ID>
export OUTLOOK_TENANT_ID=<your tenant ID or "common">

iobox space add outlook you@company.com --messages --calendar --read
```

### MCP server (Claude Desktop)

```bash
pip install 'iobox[mcp]'
```

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "iobox": {
      "command": "iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly"
      }
    }
  }
}
```

## CLI Reference

### Email commands

```bash
# Search
iobox search -q "from:newsletter@example.com" -d 3

# Save emails
iobox save -q "label:important" --max 50 -d 14 -o ./emails

# Send
iobox send --to recipient@example.com --subject "Hello" --body "Message"

# Forward
iobox forward --message-id MESSAGE_ID --to recipient@example.com

# Drafts
iobox draft-create --to recipient@example.com -s "Subject" -b "Body"
iobox draft-list --max 10
iobox draft-send --draft-id DRAFT_ID
iobox draft-delete --draft-id DRAFT_ID

# Label / Trash
iobox label --message-id MSG_ID --star --mark-read
iobox trash --message-id MSG_ID
```

### Calendar commands

```bash
# List events
iobox events list --after 2026-01-01 --before 2026-04-01

# Get a single event
iobox events get EVENT_ID

# Save event as Markdown
iobox events save EVENT_ID -o ./events

# Create event (requires --mode standard)
iobox events create --title "Team meeting" --start "2026-04-01T10:00:00" \
    --end "2026-04-01T11:00:00" --attendee alice@company.com

# RSVP (requires --mode standard)
iobox events rsvp EVENT_ID --response accepted

# Delete (requires --mode standard)
iobox events delete EVENT_ID
```

### File commands

```bash
# List files
iobox files list --query "Q4 report"

# Get file metadata
iobox files get FILE_ID

# Save file info as Markdown
iobox files save FILE_ID -o ./files

# Upload (requires --mode standard)
iobox files upload ./report.pdf --name "Q4 Report.pdf"

# Delete to trash (requires --mode standard)
iobox files delete FILE_ID

# Create folder
iobox files mkdir "Q4 Reports"
```

### Workspace commands

```bash
# Create and manage workspaces
iobox space create NAME
iobox space list
iobox space use NAME
iobox space status

# Manage service sessions
iobox space add gmail you@gmail.com --messages --calendar --drive --read
iobox space add outlook you@company.com --messages --calendar
iobox space login 1        # re-authenticate by slot number
iobox space logout 1       # revoke token, keep config
iobox space remove 1       # remove slot entirely
```

### Access modes

```bash
# Readonly — search and retrieve only
iobox --mode readonly search -q "test"

# Standard — adds drafts, labels, calendar/file writes
iobox --mode standard events create --title "Meeting" ...

# Dangerous — adds send, forward, trash
iobox --mode dangerous send --to recipient@example.com --subject "Hi" --body "Hello"
```

Set via `--mode` flag or `IOBOX_MODE` environment variable.

## Output Format

Emails saved as Markdown with YAML frontmatter:

```markdown
---
date: Mon, 23 Mar 2026 10:00:00 +1100
from: sender@example.com
labels: [INBOX]
message_id: 123456789abcdef
saved_date: 2026-03-24T21:30:00.123456
subject: Your Newsletter Subject
to: recipient@example.com
---

# Your Newsletter Subject

[Email content in Markdown]
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `IOBOX_PROVIDER` | `gmail` | Active provider: `gmail` or `outlook` |
| `IOBOX_MODE` | `standard` | Access mode: `readonly`, `standard`, `dangerous` |
| `IOBOX_ACCOUNT` | `default` | Account profile for token storage |
| `CREDENTIALS_DIR` | `.` | Directory for credential and token files |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | Google OAuth credentials path |
| `OUTLOOK_CLIENT_ID` | — | Azure app client ID (required for Outlook) |
| `OUTLOOK_TENANT_ID` | `common` | Azure tenant ID |

## Development

```bash
uv sync
make check   # lint + type-check + tests
make test    # tests only
```

## Documentation

Full documentation: [timainge.github.io/iobox](https://timainge.github.io/iobox)

## License

MIT — see [LICENSE](LICENSE) for details.
