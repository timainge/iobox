# MCP Server

iobox includes an MCP (Model Context Protocol) server that exposes Gmail operations as tools for Claude Desktop, Cursor, VS Code, and other MCP-compatible AI hosts.

## Installation

```bash
pip install "iobox[mcp]"
```

## Available Tools

| Tool | Description |
|---|---|
| `search_gmail` | Search Gmail for emails matching a query |
| `get_email` | Retrieve full email content by message ID |
| `save_email` | Save a Gmail message as a Markdown file |
| `send_email` | Send an email via Gmail |
| `forward_gmail` | Forward a Gmail message to a recipient |
| `check_auth` | Check Gmail authentication status |

### Tool Details

**`search_gmail`**

```python
search_gmail(
    query: str,          # Gmail search syntax
    max_results: int = 10,
    days: int = 7,
    start_date: str = None,  # YYYY/MM/DD
    end_date: str = None,    # YYYY/MM/DD
) -> list[dict]
```

**`get_email`**

```python
get_email(message_id: str) -> dict
```

**`save_email`**

```python
save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
) -> str  # Returns path to saved file
```

**`send_email`**

```python
send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = None,
    bcc: str = None,
) -> dict
```

**`forward_gmail`**

```python
forward_gmail(
    message_id: str,
    to: str,
    note: str = None,
) -> dict
```

**`check_auth`**

```python
check_auth() -> dict
```

## Claude Desktop Configuration

Add the following to your Claude Desktop configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "iobox": {
      "command": "python",
      "args": ["-m", "iobox.mcp_server"],
      "env": {
        "CREDENTIALS_DIR": "/path/to/your/credentials"
      }
    }
  }
}
```

Replace `/path/to/your/credentials` with the directory containing your `credentials.json` and `token.json` files.

## Usage Examples

Once connected to Claude Desktop, you can ask Claude to:

- "Search my Gmail for emails from newsletters in the last week"
- "Save the email with ID 18e4a2b3c1d5f6a7 to my notes folder"
- "Forward the last email from my boss to my personal address"
- "Check if my Gmail authentication is working"

## Authentication

The MCP server uses the same OAuth 2.0 credentials as the CLI. Ensure you have completed the authentication setup before using the MCP server — run `iobox auth-status` from the command line first.

See [Authentication](getting-started/authentication.md) for full setup instructions.
