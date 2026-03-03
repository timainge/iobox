# Phase 7: MCP Server

**Status**: Not started
**Priority**: Medium — enables LLM-driven email workflows
**Scope change**: None (uses existing iobox library functions)
**Depends on**: Phase 6 (public API surface in `__init__.py`)

---

## Overview

Create an MCP (Model Context Protocol) server that exposes iobox functions as tools for Claude Desktop, Cursor, VS Code, and other MCP-compatible hosts.

MCP servers expose:
- **Tools**: Functions the LLM can call (like POST endpoints)
- **Resources**: Data the LLM can read (like GET endpoints)

## Dependencies

Add `mcp` as an optional dependency:
```
pip install iobox[mcp]
```

In `pyproject.toml`:
```toml
[project.optional-dependencies]
mcp = ["mcp>=1.2"]
```

---

## 7.1 MCP Server Module

### Required Changes

**Create**: `src/iobox/mcp_server.py`

```python
from mcp.server.fastmcp import FastMCP
from typing import Optional

from iobox.auth import get_gmail_service, check_auth_status
from iobox.email_search import search_emails
from iobox.email_retrieval import get_email_content
from iobox.markdown_converter import convert_email_to_markdown
from iobox.file_manager import create_output_directory, save_email_to_markdown
from iobox.email_sender import send_message, compose_message, forward_email

mcp = FastMCP("iobox")
```

### Tools to Expose

| Tool Name | Wraps | Description |
|---|---|---|
| `search_gmail` | `search_emails` | Search Gmail by query, date range, max results |
| `get_email` | `get_email_content` | Retrieve full email content by message ID |
| `save_email` | `get_email_content` + `convert_email_to_markdown` + `save_email_to_markdown` | Save an email as a markdown file |
| `send_email` | `compose_message` + `send_message` | Compose and send a new email |
| `forward_gmail` | `forward_email` | Forward an existing email |
| `check_auth` | `check_auth_status` | Check Gmail authentication state |

### Tool Specifications

**search_gmail**
```python
@mcp.tool()
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search syntax (e.g. 'from:newsletter@example.com')
        max_results: Maximum number of results (default 10)
        days: Days back to search (default 7)
        start_date: Start date YYYY/MM/DD (overrides days)
        end_date: End date YYYY/MM/DD
    """
    service = get_gmail_service()
    return search_emails(service, query, max_results, days, start_date, end_date)
```

**save_email**
```python
@mcp.tool()
def save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
) -> str:
    """Save a Gmail message as a Markdown file.

    Args:
        message_id: Gmail message ID
        output_dir: Directory to save the file (default: current dir)
        prefer_html: Use HTML content if available (default: True)

    Returns:
        Absolute path to the saved file.
    """
    service = get_gmail_service()
    content_type = "text/html" if prefer_html else "text/plain"
    email_data = get_email_content(service, message_id, preferred_content_type=content_type)
    md = convert_email_to_markdown(email_data)
    out = create_output_directory(output_dir)
    return save_email_to_markdown(email_data, md, out)
```

**send_email**
```python
@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> dict:
    """Send an email via Gmail.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
    """
    service = get_gmail_service()
    message = compose_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    return send_message(service, message)
```

**forward_gmail**
```python
@mcp.tool()
def forward_gmail(
    message_id: str,
    to: str,
    note: Optional[str] = None,
) -> dict:
    """Forward a Gmail message to a recipient.

    Args:
        message_id: Gmail message ID to forward
        to: Recipient email address
        note: Optional text to prepend
    """
    service = get_gmail_service()
    return forward_email(service, message_id=message_id, to=to, additional_text=note)
```

### Entry Point

Add to bottom of `mcp_server.py`:
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 7.2 Claude Desktop Registration

### Documentation

Add to `docs/mcp.md` (or within the docs site):

**Configuration** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "iobox": {
      "command": "python",
      "args": ["-m", "iobox.mcp_server"]
    }
  }
}
```

Or if installed in a virtualenv:
```json
{
  "mcpServers": {
    "iobox": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "iobox.mcp_server"]
    }
  }
}
```

---

## 7.3 Future MCP Enhancements

After Phase 3 (write operations), add additional tools:
- `label_email` — mark read, star, archive, apply labels
- `trash_email` — move to trash

After Phase 4 (drafts), add:
- `create_draft` — compose a draft
- `list_drafts` — list pending drafts

These are deferred until the underlying CLI commands exist.

---

## Acceptance Criteria

- [ ] `python -m iobox.mcp_server` starts without errors
- [ ] All 6 tools register correctly with FastMCP
- [ ] `search_gmail` tool returns email results
- [ ] `save_email` tool creates a markdown file
- [ ] `send_email` and `forward_gmail` tools send messages
- [ ] `check_auth` tool returns auth status dict
- [ ] Unit tests with mocked service for each tool
- [ ] Documentation for Claude Desktop setup

## Test Files to Create

| File | Contents |
|---|---|
| `tests/unit/test_mcp_server.py` | Test each tool function with mocked Gmail service |

## Files Created/Modified

| Action | File |
|---|---|
| Create | `src/iobox/mcp_server.py` |
| Create | `tests/unit/test_mcp_server.py` |
| Create | `docs/mcp.md` |
| Modify | `pyproject.toml` (add `[project.optional-dependencies] mcp`) |
