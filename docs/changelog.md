# Changelog

## v0.2.0

- **Label management**: Mark read/unread, star/unstar, archive, apply custom labels (`label` command)
- **Bulk label operations**: Batch label modifications for multiple messages at once
- **Trash/untrash**: Safe (reversible) message deletion with `trash` command
- **Draft management**: Create, list, send, and delete drafts (`draft-create`, `draft-list`, `draft-send`, `draft-delete`)
- **HTML email sending**: Full MIME support with HTML bodies and inline attachments
- **Attachment sending**: Attach files to outgoing emails via `--attach`
- **HTTP batch requests**: Reduced API round-trips with `messages.get` batching
- **Incremental sync**: `--sync` flag on `save` uses Gmail history API to fetch only new emails
- **Thread export**: Save full email threads as a single Markdown file (`--thread-id`)
- **MCP server**: `pip install iobox[mcp]` for Claude Desktop and MCP-compatible AI hosts
- **Packaging**: Migrated from `setup.py` to `pyproject.toml` with hatchling

## v0.1.0

Initial release.

- **`search` command**: Search Gmail using full Gmail query syntax with date filtering
- **`save` command**: Save emails as Markdown files with YAML frontmatter
- **`send` command**: Compose and send plain text emails via Gmail API
- **`forward` command**: Forward emails to another recipient
- **`auth-status` command**: Check Gmail OAuth authentication status
- **OAuth 2.0**: Secure authentication with token storage and automatic refresh
- **HTML-to-Markdown conversion**: Convert HTML email bodies using `html2text`
- **Attachment metadata**: List attachment filenames and MIME types in YAML frontmatter
- **Duplicate detection**: Skip already-saved emails based on message ID
