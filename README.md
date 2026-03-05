# Iobox

A Gmail to Markdown converter. Extract emails from Gmail and save them as structured markdown files with YAML frontmatter.

## Why

Email inboxes are full of valuable content — newsletters, reports, project updates — but it's trapped in a format that's hard to search, process, or archive. Iobox pulls emails out of Gmail and turns them into clean markdown files you can version-control, feed into LLMs, or drop into your note-taking system.

## Features

- **Gmail API integration** with OAuth 2.0 authentication
- **Flexible search** using Gmail's native query syntax
- **HTML to Markdown conversion** — preserves formatting, links, tables, and lists
- **YAML frontmatter** with full email metadata (from, to, subject, date, labels, message ID)
- **Attachment downloads** with optional type filtering
- **Duplicate prevention** — won't re-download emails you already have
- **Send, forward, and draft** emails from the CLI
- **Label and trash management** — star, archive, mark read/unread, trash/restore
- **Incremental sync** — only fetch new emails since last run

## Installation

### Prerequisites

- Python 3.10+
- A Google Cloud project with the Gmail API enabled
- OAuth 2.0 credentials (Desktop app type)

### Install with uv

```bash
git clone https://github.com/timainge/iobox.git
cd iobox
uv sync
```

### Install with pip

```bash
git clone https://github.com/timainge/iobox.git
cd iobox
pip install -e .
```

### Set up Google OAuth credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Gmail API**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID** (Desktop app type)
6. Download the JSON file and save it as `credentials.json` in the project root
7. Optionally configure paths via `.env` (see `.env.example`)

The first time you run a command, a browser window will open for OAuth consent. After that, credentials are cached in `token.json`.

## Usage

```bash
# Check authentication status
iobox auth-status

# Search for emails from the last 3 days
iobox search -q "from:newsletter@example.com" -d 3

# Save a specific email by message ID
iobox save --message-id MESSAGE_ID -o ./output

# Batch save emails matching a query
iobox save -q "label:important" --max 50 -d 14 -o ./emails

# Save emails with attachments (only PDFs and spreadsheets)
iobox save -q "has:attachment" --download-attachments --attachment-types pdf,xlsx -o ./reports

# Show version
iobox version
```

### Search options

| Flag | Description |
|---|---|
| `-q, --query` | Gmail search query (required) |
| `-m, --max-results` | Max results to return (default: 10) |
| `-d, --days` | Days back to search (default: 7) |
| `-s, --start-date` | Start date in `YYYY/MM/DD` format |
| `-e, --end-date` | End date in `YYYY/MM/DD` format |
| `-v, --verbose` | Show detailed info per result |
| `--debug` | Show raw API response fields |

### Save options

| Flag | Description |
|---|---|
| `-m, --message-id` | Save a single email by ID |
| `-q, --query` | Save emails matching a search query |
| `--max` | Max emails to save in batch mode (default: 10) |
| `-d, --days` | Days back to search (default: 7) |
| `-s, --start-date` | Start date in `YYYY/MM/DD` format |
| `-e, --end-date` | End date in `YYYY/MM/DD` format |
| `-o, --output-dir` | Output directory (default: `.`) |
| `--html-preferred` | Prefer HTML content (default: true) |
| `--download-attachments` | Download attachments |
| `--attachment-types` | Filter by extension, e.g. `pdf,docx` |
| `--sync` | Incremental sync — only fetch new emails |

### Send command

```bash
# Send with inline body
iobox send --to recipient@example.com --subject "Hello" --body "Message body"

# Send with body from file
iobox send --to recipient@example.com --subject "Report" --body-file ./report.txt

# Send with CC and BCC
iobox send --to recipient@example.com --subject "Update" --body "Content" --cc team@example.com --bcc manager@example.com
```

### Forward command

```bash
# Forward a single email
iobox forward --message-id MESSAGE_ID --to recipient@example.com

# Forward with a note
iobox forward --message-id MESSAGE_ID --to recipient@example.com --note "FYI - see below"

# Forward multiple emails matching a query
iobox forward --query "from:reports@example.com" --to team@example.com --days 7
```

### Draft commands

```bash
# Create a draft
iobox draft-create --to recipient@example.com -s "Subject" -b "Draft body"

# List drafts
iobox draft-list --max 10

# Send a draft
iobox draft-send --draft-id DRAFT_ID

# Delete a draft
iobox draft-delete --draft-id DRAFT_ID
```

### Label command

```bash
# Star a message
iobox label --message-id MSG_ID --star

# Mark as read
iobox label --message-id MSG_ID --mark-read

# Batch archive messages matching a query
iobox label -q "from:notifications@example.com" --archive
```

Options: `--mark-read`, `--mark-unread`, `--star`, `--unstar`, `--archive`, `--add LABEL`, `--remove LABEL`

### Trash command

```bash
# Trash a message
iobox trash --message-id MSG_ID

# Restore from trash
iobox trash --message-id MSG_ID --untrash

# Batch trash with confirmation
iobox trash -q "from:spam@example.com" -d 30
```

## Output format

Each email is saved as a markdown file with YAML frontmatter:

```markdown
---
date: Mon, 23 Mar 2025 10:00:00 +1100
from: sender@example.com
labels:
  - INBOX
  - CATEGORY_UPDATES
message_id: 123456789abcdef
saved_date: 2025-03-24T21:30:00.123456
subject: Your Newsletter Subject
thread_id: thread123456
to: recipient@example.com
attachments:
  - filename: report.pdf
    mime_type: application/pdf
---

# Your Newsletter Subject

[Email content in Markdown format]
```

Attachments are saved to `attachments/{email_id}/` within the output directory.

## Configuration

Environment variables (set in `.env` or your shell):

| Variable | Default | Description |
|---|---|---|
| `CREDENTIALS_DIR` | `.` | Directory containing credential files |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | Path to OAuth credentials |
| `GMAIL_TOKEN_FILE` | `token.json` | Path to cached token |

## Project Structure

```
iobox/
├── src/iobox/                  # Source code
│   ├── __init__.py
│   ├── auth.py                 # OAuth 2.0 authentication
│   ├── cli.py                  # Typer CLI (search, save, send, forward, label, trash, drafts)
│   ├── email_search.py         # Email search with date filtering
│   ├── email_retrieval.py      # Full email content, labels, trash/untrash
│   ├── email_sender.py         # Compose, send, forward, and draft management
│   ├── markdown.py             # Markdown module re-exports
│   ├── markdown_converter.py   # HTML-to-Markdown and YAML frontmatter
│   ├── file_manager.py         # File save, deduplication, attachments, sync state
│   └── utils.py                # Filename generation and text utilities
├── tests/                      # Test files
│   ├── unit/                   # Unit tests for all modules
│   ├── integration/            # End-to-end workflow tests
│   ├── live/                   # Live CLI tests against a real Gmail account
│   └── fixtures/               # Mock API responses
├── credentials.json            # OAuth credentials (not committed)
├── token.json                  # OAuth token (not committed)
├── .env                        # Environment variables (not committed)
├── pyproject.toml              # Package configuration (hatchling)
└── README.md                   # This file
```

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=html
```

## License

MIT — see [LICENSE](LICENSE) for details.
