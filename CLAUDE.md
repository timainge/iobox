# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Iobox is a Gmail to Markdown converter that extracts emails from Gmail based on specific criteria and saves them as markdown files with YAML frontmatter. The tool provides a command-line interface for searching, filtering, and exporting emails with optional attachment downloads.

## Architecture

### Core Modules

- **`src/iobox/cli.py`**: Typer-based command-line interface with commands for search, save, auth-status, and version
- **`src/iobox/auth.py`**: Gmail API OAuth 2.0 authentication handling with credential management
- **`src/iobox/email_search.py`**: Email search and retrieval using Gmail API with query parsing and date filtering
- **`src/iobox/markdown.py`**: Email content conversion to markdown format with YAML frontmatter
- **`src/iobox/file_manager.py`**: File operations for saving emails, managing duplicates, and handling attachments

### Key Dependencies

- **Google APIs**: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
- **CLI Framework**: `typer` for command-line interface
- **Configuration**: `python-dotenv` for environment variable management
- **Content Processing**: `PyYAML` for frontmatter, `rich` for terminal output

## Development Commands

### Testing
```bash
# Run all tests with coverage
python -m pytest

# Run with detailed coverage report
python -m pytest --cov=src --cov-report=html

# Run specific test categories
python -m pytest tests/unit
python -m pytest tests/integration

# Run specific test file
python -m pytest tests/unit/test_auth.py
```

### Installation and Setup
```bash
# Install in development mode
pip install -e .

# Install dependencies
pip install -r requirements.txt

# Run the CLI
iobox --help
```

## Authentication Setup

The application requires Google OAuth 2.0 credentials:
1. Create a Google Cloud project with Gmail API enabled
2. Download OAuth credentials as `credentials.json` in project root
3. First run will trigger OAuth flow and create `token.json`

## Configuration

Environment variables can be set in `.env` file:
- `CREDENTIALS_DIR`: Directory for credential files (default: current working directory)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to credentials.json (default: 'credentials.json')
- `GMAIL_TOKEN_FILE`: Path to token.json (default: 'token.json')

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

### Utility Commands
```bash
iobox auth-status  # Check authentication
iobox version     # Show version
```

## Testing Strategy

- **Unit tests**: Mock Gmail API responses using `pytest-mock`
- **Integration tests**: End-to-end workflow testing
- **Coverage**: Configured via `pytest.ini` with HTML reports in `htmlcov/`
- **Fixtures**: Centralized mock responses in `tests/fixtures/mock_responses.py`

## File Output Format

Emails are saved as markdown files with:
- YAML frontmatter containing metadata (from, to, subject, date, message_id, labels)
- Markdown-converted email body
- Optional attachment downloads in `attachments/{email_id}/` subdirectories