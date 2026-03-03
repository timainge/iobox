# MCP Server

iobox includes an MCP (Model Context Protocol) server that exposes Gmail operations as tools for Claude Desktop, Cursor, VS Code, and other MCP-compatible AI hosts.

## Installation

```bash
pip install "iobox[mcp]"
```

## Available Tools

### Search & Read

| Tool | Description |
|---|---|
| `search_gmail` | Search Gmail for emails matching a query |
| `get_email` | Retrieve full email content by message ID |

### Save

| Tool | Description |
|---|---|
| `save_email` | Save a single Gmail message as a Markdown file |
| `save_thread` | Save an entire thread as a single Markdown file |
| `save_emails_by_query` | Batch save emails matching a query, with optional sync |

### Send & Forward

| Tool | Description |
|---|---|
| `send_email` | Send an email (plain text or HTML, with optional attachments) |
| `forward_gmail` | Forward a Gmail message to a recipient |

### Drafts

| Tool | Description |
|---|---|
| `create_gmail_draft` | Create an email draft |
| `list_gmail_drafts` | List drafts |
| `send_gmail_draft` | Send an existing draft |
| `delete_gmail_draft` | Permanently delete a draft |

### Labels

| Tool | Description |
|---|---|
| `modify_labels` | Add/remove labels on a single message (read, star, archive, custom) |
| `batch_modify_gmail_labels` | Modify labels on multiple messages matching a query |

### Trash

| Tool | Description |
|---|---|
| `trash_gmail` | Move a message to trash |
| `untrash_gmail` | Restore a message from trash |

### Auth

| Tool | Description |
|---|---|
| `check_auth` | Check authentication status and Gmail profile info |

## Tool Details

**`search_gmail`**

```python
search_gmail(
    query: str,               # Gmail search syntax
    max_results: int = 10,
    days: int = 7,
    start_date: str = None,   # YYYY/MM/DD
    end_date: str = None,     # YYYY/MM/DD
    include_spam_trash: bool = False,
) -> list[dict]
```

**`get_email`**

```python
get_email(
    message_id: str,
    prefer_html: bool = True,
) -> dict
```

**`save_email`**

```python
save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str = None,  # comma-separated, e.g. "pdf,docx"
) -> str  # Returns path to saved file
```

**`save_thread`**

```python
save_thread(
    thread_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
) -> str  # Returns path to saved file
```

**`save_emails_by_query`**

```python
save_emails_by_query(
    query: str,
    output_dir: str = ".",
    max_results: int = 10,
    days: int = 7,
    start_date: str = None,
    end_date: str = None,
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str = None,
    include_spam_trash: bool = False,
    sync: bool = False,       # Incremental sync via Gmail history API
) -> dict  # {saved_count, skipped_count, attachment_count}
```

**`send_email`**

```python
send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = None,
    bcc: str = None,
    html: bool = False,
    attachments: list[str] = None,  # File paths
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

**`create_gmail_draft`**

```python
create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = None,
    bcc: str = None,
    html: bool = False,
    attachments: list[str] = None,
) -> dict
```

**`list_gmail_drafts`**

```python
list_gmail_drafts(max_results: int = 10) -> list[dict]
```

**`send_gmail_draft`**

```python
send_gmail_draft(draft_id: str) -> dict
```

**`delete_gmail_draft`**

```python
delete_gmail_draft(draft_id: str) -> dict
```

**`modify_labels`**

```python
modify_labels(
    message_id: str,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str = None,
    remove_label: str = None,
) -> dict
```

**`batch_modify_gmail_labels`**

```python
batch_modify_gmail_labels(
    query: str,
    max_results: int = 10,
    days: int = 7,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str = None,
    remove_label: str = None,
) -> dict  # {modified_count}
```

**`trash_gmail`**

```python
trash_gmail(message_id: str) -> dict
```

**`untrash_gmail`**

```python
untrash_gmail(message_id: str) -> dict
```

**`check_auth`**

```python
check_auth() -> dict  # Includes email, messages_total, threads_total
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
- "Save all emails from my boss this month as markdown"
- "Forward the last email from my boss to my personal address"
- "Create a draft reply to the last email from HR"
- "Star all unread emails from the marketing team"
- "Trash all emails from promotions older than 30 days"
- "Check if my Gmail authentication is working"

## Authentication

The MCP server uses the same OAuth 2.0 credentials as the CLI. Ensure you have completed the authentication setup before using the MCP server — run `iobox auth-status` from the command line first.

See [Authentication](getting-started/authentication.md) for full setup instructions.
