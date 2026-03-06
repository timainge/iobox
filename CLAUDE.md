# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Iobox is a Gmail to Markdown converter that extracts emails from Gmail based on specific criteria and saves them as markdown files with YAML frontmatter. The tool provides a command-line interface for searching, filtering, and exporting emails with optional attachment downloads.

## Architecture

### Core Modules

- **`src/iobox/cli.py`**: Typer-based CLI with commands for search, save, send, forward, draft-create/list/send/delete, label, trash, auth-status, and version
- **`src/iobox/auth.py`**: Gmail API OAuth 2.0 authentication with multi-profile token storage (per-account, per-scope-tier)
- **`src/iobox/accounts.py`**: Account management — tracks the active account name used to namespace token files
- **`src/iobox/modes.py`**: Access mode definitions (readonly/standard/dangerous) controlling scopes and command gating
- **`src/iobox/email_search.py`**: Email search using Gmail API with query parsing and date filtering
- **`src/iobox/email_retrieval.py`**: Full email content retrieval and attachment download
- **`src/iobox/email_sender.py`**: Compose, send, and forward emails via Gmail API
- **`src/iobox/markdown.py`**: Re-exports from markdown_converter and utils for backward compatibility
- **`src/iobox/markdown_converter.py`**: HTML-to-Markdown conversion and YAML frontmatter generation
- **`src/iobox/file_manager.py`**: File operations for saving emails, managing duplicates, and handling attachments
- **`src/iobox/utils.py`**: Shared filename generation and text slugifying utilities

### Key Dependencies

- **Google APIs**: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
- **CLI Framework**: `typer` for command-line interface
- **Configuration**: `python-dotenv` for environment variable management
- **Content Processing**: `html2text` for HTML-to-Markdown, `PyYAML` for frontmatter

## Development Commands

### Testing
```bash
# Run all tests with coverage
uv run pytest

# Run specific test categories
uv run pytest tests/unit
uv run pytest tests/integration

# Run specific test file
uv run pytest tests/unit/test_auth.py
```

### Installation and Setup
```bash
# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .

# Run the CLI
iobox --help
```

## Authentication Setup

The application requires Google OAuth 2.0 credentials:
1. Create a Google Cloud project with Gmail API enabled
2. Download OAuth credentials as `credentials.json` in project root
3. First run will trigger OAuth flow and create a token file

### Multi-Profile Token Storage

Tokens are stored per account and per scope tier under `$CREDENTIALS_DIR/tokens/{account}/`:
- `token_readonly.json` — gmail.readonly scope
- `token_standard.json` — gmail.modify + gmail.compose scopes

This means switching between `--mode readonly` and `--mode standard` never destroys an existing token. A broader token (standard) is automatically accepted in readonly mode.

Legacy `token.json` files are auto-migrated on first run (copied, not deleted).

If `GMAIL_TOKEN_FILE` is explicitly set to a non-default value, the legacy single-file behavior is used instead.

## Configuration

Environment variables can be set in `.env` file:
- `CREDENTIALS_DIR`: Directory for credential files (default: current working directory)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to credentials.json (default: 'credentials.json')
- `GMAIL_TOKEN_FILE`: Path to token.json (default: 'token.json') — when set to a non-default value, bypasses multi-profile token directory
- `IOBOX_MODE`: Access mode — `readonly`, `standard` (default), or `dangerous`
- `IOBOX_ACCOUNT`: Account profile name for multi-account token storage (default: 'default')

## CLI Commands

### Search Command
```bash
iobox search -q "from:newsletter@example.com" -m 20 -d 3
```
Options: `-q/--query`, `-m/--max-results`, `-d/--days`, `-s/--start-date`, `-e/--end-date`, `-v/--verbose`

### Save Command
```bash
# Single email by message ID
iobox save --message-id MESSAGE_ID -o ./output

# Batch save by query
iobox save -q "label:important" --max 50 -d 14 -o ./emails
```

### Send Command
```bash
iobox send --to recipient@example.com --subject "Hello" --body "Message"
iobox send --to recipient@example.com --subject "Report" --body-file ./report.txt
```

### Forward Command
```bash
iobox forward --message-id MESSAGE_ID --to recipient@example.com
iobox forward -q "from:reports@example.com" --to team@example.com -d 7
```

### Draft Commands
```bash
iobox draft-create --to recipient@example.com -s "Subject" -b "Body"
iobox draft-list --max 10
iobox draft-send --draft-id DRAFT_ID
iobox draft-delete --draft-id DRAFT_ID
```

### Label Command
```bash
iobox label --message-id MSG_ID --star          # Star a message
iobox label --message-id MSG_ID --mark-read     # Mark as read
iobox label -q "from:x@y.com" --archive         # Batch archive
```
Options: `--mark-read`, `--mark-unread`, `--star`, `--unstar`, `--archive`, `--add`, `--remove`

### Trash Command
```bash
iobox trash --message-id MSG_ID                 # Trash a message
iobox trash --message-id MSG_ID --untrash       # Restore from trash
```

### Utility Commands
```bash
iobox auth-status  # Check authentication
iobox version     # Show version
```

## Testing Strategy

- **Unit tests**: Mock Gmail API responses using `pytest-mock` (`tests/unit/`)
- **Integration tests**: End-to-end workflow testing (`tests/integration/`)
- **Live tests**: CLI integration tests against a real Gmail account (`tests/live/`)
- **Coverage**: Configured via `pyproject.toml` with HTML reports in `htmlcov/`
- **Fixtures**: Centralized mock responses in `tests/fixtures/mock_responses.py`

### Live Tests
```bash
# Run all 21 live CLI scenarios (requires authenticated Gmail account)
python tests/live/run_tests.py

# Clean up test emails from inbox after a run
python tests/live/cleanup.py
```

## File Output Format

Emails are saved as markdown files with:
- YAML frontmatter containing metadata (from, to, subject, date, message_id, labels)
- Markdown-converted email body
- Optional attachment downloads in `attachments/{email_id}/` subdirectories
