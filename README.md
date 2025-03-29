# Iobox (In and Out Box)

A Gmail to Markdown Converter tool that extracts emails from Gmail based on specific criteria and saves them as markdown files with YAML frontmatter for easy archiving, searching, and further processing.

## Overview

Iobox allows you to:
- Query your Gmail inbox for a specific date range
- Extract relevant emails based on labels, senders, or subject lines
- Save these emails as markdown files with metadata in YAML frontmatter
- Create a searchable, portable archive of important communications

Once you have your emails saved locally as markdown files, you can proceed to build additional modules for summarisation, topic extraction, or any other text processing tasks you need.

## Features

- Gmail API integration with secure OAuth 2.0 authentication
- Flexible search criteria using Gmail's query syntax
- Email content extraction with both plain text and HTML support
- Markdown conversion with consistent formatting
- YAML frontmatter for preserving email metadata
- Duplicate prevention mechanism
- Command-line interface for easy use

## Installation

### Prerequisites

- Python 3.7+
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
- `-o, --output-dir`: Directory to save markdown files to (default: '.')
- `--html-preferred`: Prefer HTML content if available (default: True)

### Example Search Queries

- `"from:newsletter@example.com"` - Emails from a specific sender
- `"subject:newsletter"` - Emails with "newsletter" in the subject
- `"label:important"` - Emails with the "important" label
- `"has:attachment"` - Emails with attachments

## Project Structure

```
iobox/
├── src/                 # Source code
│   ├── __init__.py
│   ├── main.py          # Main entry point
│   ├── auth.py          # Authentication module
│   ├── email_search.py  # Email search and retrieval
│   ├── content.py       # Content extraction
│   ├── markdown.py      # Markdown conversion
│   └── file_manager.py  # File management
├── tests/               # Test files
├── memory-bank/         # Project planning and documentation
├── credentials.json     # OAuth credentials (not committed)
├── token.json           # OAuth token (not committed)
├── .env                 # Environment variables (not committed)
├── .env.example         # Template for environment variables
├── requirements.txt     # Python dependencies
└── README.md            # This file
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
- Unit tests for all core modules (auth, email_search, markdown, file_manager, cli)
- Integration tests for end-to-end workflows
- Comprehensive mocking of the Gmail API for consistent testing

For development guidelines and detailed project information, see the files in the `memory-bank` directory.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Google Gmail API
- Python
- PyYAML
- Google Auth libraries
