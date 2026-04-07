# Installation

## Prerequisites

- Python 3.9 or higher
- A Google account (personal Gmail or Google Workspace)
- A Google Cloud project with the Gmail API enabled

## Install via pip

```bash
pip install iobox
```

## Development Installation

To install from source with development dependencies:

```bash
git clone https://github.com/yourusername/iobox.git
cd iobox
pip install -e ".[dev]"
```

## Optional Dependencies

### MCP Server

To use iobox as an MCP tool server with Claude Desktop or other AI hosts:

```bash
pip install "iobox[mcp]"
```

### Documentation

To build the documentation locally:

```bash
pip install "iobox[docs]"
mkdocs serve
```

## Google Cloud Setup

Before using iobox, you need a Google Cloud OAuth 2.0 credentials file:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select an existing one
3. Navigate to **APIs & Services > Library** and enable the **Gmail API**
4. Navigate to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. Choose **Desktop app** as the application type
7. Download the JSON file and save it as `credentials.json` in your working directory

See [Authentication](authentication.md) for full details on the OAuth flow and token management.
