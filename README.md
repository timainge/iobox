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

Basic usage:
```bash
python src/main.py --query "label:inbox subject:(important meeting)" --output ./email_output --days 30
```

### Available Options

- `--query`: Gmail search query (required)
- `--output`: Output directory for markdown files (default: 'output')
- `--days`: Number of days back to search for emails (default: 7)

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

For development guidelines and detailed project information, see the files in the `memory-bank` directory.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Google Gmail API
- Python
- PyYAML
- Google Auth libraries
