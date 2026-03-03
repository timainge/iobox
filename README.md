# Iobox (In and Out Box)

A Gmail to Markdown Converter tool that extracts emails from Gmail based on specific criteria and saves them as markdown files with YAML frontmatter for easy archiving, searching, and further processing.

## Background

Iobox was created to address the challenge of effectively managing and utilizing valuable information stored in email inboxes. Whether you're subscribed to industry newsletters, collecting research data, or tracking important communications, this tool provides a foundation for transforming your inbox into a processable knowledge resource.

The tool serves as the first step in workflows where you need to:
- Download newsletters or emails locally as structured markdown files
- Process email content for summarization or analysis
- Create searchable archives of important communications
- Integrate email content into note-taking systems or knowledge bases

## Overview

Iobox allows you to:
- Query your Gmail inbox for a specific date range
- Extract relevant emails based on labels, senders, or subject lines
- Save these emails as markdown files with metadata in YAML frontmatter
- Create a searchable, portable archive of important communications

The current implementation provides a solid foundation with OAuth 2.0 authentication, flexible search criteria, and robust file management capabilities.

## Features

- Gmail API integration with secure OAuth 2.0 authentication
- Flexible search criteria using Gmail's query syntax
- Email content extraction with both plain text and HTML support
- **HTML to Markdown conversion**: Properly converts HTML emails to well-formatted Markdown
  - Preserves formatting (bold, italic, headers)
  - Converts links and images to Markdown syntax
  - Handles tables, lists, and complex email structures
  - Cleans up common email artifacts (tracking pixels, empty links)
- Markdown conversion with consistent formatting
- YAML frontmatter for preserving email metadata
- Attachment download functionality with filtering options
- Duplicate prevention mechanism
- Command-line interface for easy use

## Installation

### Prerequisites

- Python 3.8+
- Google Cloud project with Gmail API enabled
- OAuth 2.0 credentials for the Gmail API

### Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/iobox.git
   cd iobox
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your Google Cloud project and obtain OAuth credentials:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API for your project
   - Create OAuth 2.0 credentials (Desktop app type)
   - Download the credentials JSON file and save it as `credentials.json` in the project root

5. Configure your environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your specific settings
   ```

## Usage

### Command-Line Interface

Iobox uses a command-based interface:

```bash
# Display version information
iobox --version

# Get help on available commands
iobox --help

# Get help on a specific command
iobox save --help
```

### Available Commands

```bash
# Search for emails
iobox search -q "from:newsletter@example.com" -m 20 -v

# Search for emails from the last 3 days
iobox search -q "from:newsletter@example.com" -d 3

# Save a specific email as Markdown
iobox save --message-id MESSAGE_ID -o ./output_folder

# Save multiple emails matching a query from the last 14 days
iobox save --query "label:important" --max 50 -d 14 -o ./important_emails

# Check authentication status
iobox auth-status

# Display version information
iobox version
```

### Search Command Options

- `-q, --query`: Gmail search query (required)
- `-m, --max-results`: Maximum number of results to return (default: 10)
- `-d, --days`: Number of days back to search (default: 7)
- `-s, --start-date`: Start date in YYYY/MM/DD format (overrides days parameter if provided)
- `-e, --end-date`: End date in YYYY/MM/DD format (requires start-date)
- `-v, --verbose`: Show detailed information for each result
- `--debug`: Show debug information about API responses

### Save Command Options

The save command supports two modes:
- **Single mode**: Save one specific email using `--message-id`
- **Batch mode**: Save multiple emails matching a query using `--query`

Options:
- `-m, --message-id`: Gmail message ID to save (for single email mode)
- `-q, --query`: Search query for emails to save (for batch mode)
- `--max`: Maximum number of emails to save in batch mode (default: 10)
- `-d, --days`: Number of days back to search (default: 7)
- `-s, --start-date`: Start date in YYYY/MM/DD format (overrides days parameter if provided)
- `-e, --end-date`: End date in YYYY/MM/DD format (requires start-date)
- `-o, --output-dir`: Directory to save markdown files to (default: '.')
- `--html-preferred`: Prefer HTML content if available (default: True)
- `--download-attachments`: Download email attachments (default: False)
- `--attachment-types`: Filter attachments by file extension (comma-separated, e.g., 'pdf,docx,xlsx')

### Send Command

Compose and send a new email:

```bash
# Send with inline body
iobox send --to recipient@example.com --subject "Hello" --body "Message body"

# Send with body from file
iobox send --to recipient@example.com --subject "Report" --body-file ./report.txt

# Send with CC and BCC
iobox send --to recipient@example.com --subject "Update" --body "Content" --cc team@example.com --bcc manager@example.com
```

Options:
- `-t, --to`: Recipient email address (required)
- `-s, --subject`: Email subject line (required)
- `-b, --body`: Email body text (inline)
- `-f, --body-file`: Path to file containing email body
- `--cc`: CC recipients (comma-separated)
- `--bcc`: BCC recipients (comma-separated)

### Forward Command

Forward one or more emails to a recipient:

```bash
# Forward a single email
iobox forward --message-id MESSAGE_ID --to recipient@example.com

# Forward with a note
iobox forward --message-id MESSAGE_ID --to recipient@example.com --note "FYI - see below"

# Forward multiple emails matching a query
iobox forward --query "from:reports@example.com" --to team@example.com --days 7
```

Options:
- `-m, --message-id`: ID of a specific email to forward
- `-q, --query`: Search query for emails to forward (batch mode)
- `-t, --to`: Recipient email address (required)
- `--max`: Maximum number of emails to forward in batch mode (default: 10)
- `-d, --days`: Number of days back to search (default: 7)
- `-s, --start-date`: Start date in YYYY/MM/DD format
- `-e, --end-date`: End date in YYYY/MM/DD format
- `-n, --note`: Optional note to prepend to forwarded email

### Draft Commands

Create, list, send, and delete email drafts:

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

### Label Command

Add or remove labels on one or more messages:

```bash
# Star a message
iobox label --message-id MSG_ID --star

# Mark as read
iobox label --message-id MSG_ID --mark-read

# Batch archive messages matching a query
iobox label -q "from:notifications@example.com" --archive
```

Options: `--mark-read`, `--mark-unread`, `--star`, `--unstar`, `--archive`, `--add LABEL`, `--remove LABEL`

### Trash Command

Move messages to trash or restore them:

```bash
# Trash a message
iobox trash --message-id MSG_ID

# Restore from trash
iobox trash --message-id MSG_ID --untrash

# Batch trash with confirmation
iobox trash -q "from:spam@example.com" -d 30
```

### Example Search Queries and Date Filtering

```bash
# Search for emails from the last 7 days (default)
iobox search -q "from:newsletter@example.com"

# Search for emails from the last 3 days
iobox search -q "from:newsletter@example.com" -d 3

# Search for emails within a specific date range (using long-form options)
iobox search -q "from:reports@example.com" --start-date 2025/04/01 --end-date 2025/04/10

# Search using shorthand date range options
iobox search -q "label:important" -s 2025/03/15 -e 2025/03/31

# Save emails matching a query from a specific date range
iobox save -q "label:important" -s 2025/03/15 -e 2025/03/31 -o ./important_emails
```

**Important Note**: Date format must be YYYY/MM/DD with forward slashes and leading zeros for month and day.

### Example Search Queries

- `"from:newsletter@example.com"` - Emails from a specific sender
- `"subject:newsletter"` - Emails with "newsletter" in the subject
- `"label:important"` - Emails with the "important" label
- `"has:attachment"` - Emails with attachments

### Save Examples

```bash
# Save a specific email as Markdown
iobox save --message-id MESSAGE_ID -o ./output_folder

# Save multiple emails matching a query from the last 14 days
iobox save --query "label:important" --max 50 -d 14 -o ./important_emails

# Save emails with attachments and download the attachments too
iobox save --query "has:attachment" --download-attachments -o ./emails_with_attachments

# Save emails and download only PDF attachments
iobox save --query "from:reports@example.com" --download-attachments --attachment-types pdf,xlsx -o ./reports
```

When attachments are downloaded, they are stored in an `attachments/{email_id}` directory structure within the output directory. Filenames are sanitised to ensure they are safe for all operating systems, and duplicate filenames are handled by appending a number to the filename.

## Output Format

Emails are saved as Markdown files with the following structure:

```markdown
---
date: Mon, 23 Mar 2025 10:00:00 +1100
from: sender@example.com
labels:
  - INBOX
  - CATEGORY_UPDATES
message_id: 123456789abcdef
saved_date: 2025-08-24T21:30:00.123456
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

### HTML Email Conversion

When processing HTML emails (the default behavior with `--html-preferred`), iobox:
- Converts HTML tags to proper Markdown syntax (headers, bold, italic, etc.)
- Preserves links in Markdown format: `[link text](url)`
- Converts images to Markdown image syntax: `![alt text](image_url)`
- Converts HTML tables to Markdown tables
- Handles lists (ordered and unordered) 
- Cleans up common email artifacts like tracking pixels and empty links
- Normalizes excessive whitespace and formatting

This ensures that HTML newsletters and formatted emails are readable and properly structured in Markdown format.

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
├── docs/                       # MkDocs documentation site
├── credentials.json            # OAuth credentials (not committed)
├── token.json                  # OAuth token (not committed)
├── .env                        # Environment variables (not committed)
├── pyproject.toml              # Package configuration (hatchling)
└── README.md                   # This file
```

## Development

### Running Tests

Tests are organized as unit tests and integration tests in the `tests` directory. To run the tests:

1. Ensure your virtual environment is activated:
   ```bash
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

2. Run all tests with pytest:
   ```bash
   python -m pytest
   ```

3. Run tests with coverage reporting:
   ```bash
   python -m pytest --cov=src
   ```

4. Run specific test categories:
   ```bash
   # Run only unit tests
   python -m pytest tests/unit

   # Run only integration tests
   python -m pytest tests/integration

   # Run a specific test file
   python -m pytest tests/unit/test_auth.py
   ```

5. View detailed coverage report:
   ```bash
   python -m pytest --cov=src --cov-report=html
   # Then open htmlcov/index.html in your browser
   ```

The test suite includes:
- Unit tests for all core modules (auth, cli, email_search, email_retrieval, email_sender, markdown, file_manager, utils)
- Integration tests for end-to-end workflows
- Comprehensive mocking of the Gmail API for consistent testing
- Live CLI integration tests against a real Gmail account (21 scenarios)

```bash
# Run live tests (requires authenticated Gmail account)
python tests/live/run_tests.py

# Clean up test emails afterwards
python tests/live/cleanup.py
```

For detailed documentation on authentication and integration patterns, see the `docs/` directory.

## What's Been Built

All 9 roadmap phases are complete. See the [full roadmap](docs/roadmap.md) for details.

- [x] Critical bug fixes (pagination, label resolution)
- [x] Gmail read enhancements (thread export, spam/trash, profile)
- [x] Gmail write operations (label, trash/untrash, batch modify)
- [x] Enhanced send and drafts (HTML, attachments, draft CRUD)
- [x] Performance (HTTP batching, incremental sync)
- [x] Packaging (`pyproject.toml`, hatchling, `py.typed`)
- [x] MCP server (`pip install iobox[mcp]`)
- [x] CI/CD (GitHub Actions, ruff, pytest matrix)
- [x] Documentation site (MkDocs Material, auto API docs)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Google Gmail API
- Python
- PyYAML
- Google Auth libraries
