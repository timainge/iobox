# Configuration

The MCP server is configured entirely through environment variables set in your host's MCP config.

## Config file locations (Claude Desktop)

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Always restart Claude Desktop fully after editing.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `IOBOX_MODE` | `standard` | Which tools are registered: `readonly`, `standard`, or `dangerous` |
| `IOBOX_ACCOUNT` | `default` | Account for the single-account Gmail fallback (no workspace configured) |
| `CREDENTIALS_DIR` | process working directory | Credentials and tokens for the single-account fallback |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | Path to the Google OAuth client file |
| `OUTLOOK_CLIENT_ID` | — | Required for Microsoft 365 slots |
| `OUTLOOK_TENANT_ID` | `common` | Microsoft 365 tenant |

Workspace configs and tokens are always read from `~/.iobox/`.

!!! warning "Set `IOBOX_MODE` explicitly"
    If `IOBOX_MODE` is unset, the server starts in `standard` mode, which includes drafts, label changes, calendar writes, and file uploads. For a read-only assistant, set `IOBOX_MODE=readonly`.

## Access modes

`IOBOX_MODE` controls which tools are registered. A tool that isn't registered doesn't exist as far as the assistant is concerned. Modes are additive.

| Mode | Adds | Tools |
|---|---|---|
| `readonly` | Reads and saves to local disk | `search_gmail`, `get_email`, `get_emails`, `save_email`, `save_thread`, `save_emails_by_query`, `download_email_attachment`, `list_gmail_drafts`, `list_labels`, `check_auth`, `search_workspace`, `semantic_search_workspace`, `list_events`, `get_event`, `save_event`, `list_files`, `get_file`, `get_file_content`, `save_file`, `download_file`, `list_workspaces`, `get_active_workspace`, `list_provider_slots`, `workspace_auth_status` |
| `standard` | Drafts, labels, calendar and file writes, switching workspace | `create_gmail_draft`, `send_gmail_draft`, `delete_gmail_draft`, `create_label`, `modify_labels`, `batch_modify_gmail_labels`, `create_event`, `update_event`, `rsvp_event`, `upload_file`, `create_folder`, `delete_file`, `set_active_workspace` |
| `dangerous` | Outbound mail and irreversible actions | `send_email`, `forward_gmail`, `batch_forward_gmail`, `trash_gmail`, `untrash_gmail`, `batch_trash_gmail`, `delete_event` |

Note that `standard` includes `send_gmail_draft`, so an assistant in `standard` mode can send mail via a draft. Accounts added with `--read` hold read-only tokens and reject all writes regardless of mode — see [access modes](../get-started/concepts.md#access-modes).

The allowlists live in `src/iobox/modes.py`.

## Examples

### Read-only assistant

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/full/path/to/iobox-mcp",
      "env": { "IOBOX_MODE": "readonly" }
    }
  }
}
```

### Assistant that can draft and organise

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/full/path/to/iobox-mcp",
      "env": { "IOBOX_MODE": "standard" }
    }
  }
}
```

### With Microsoft 365

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/full/path/to/iobox-mcp",
      "env": {
        "IOBOX_MODE": "readonly",
        "OUTLOOK_CLIENT_ID": "00000000-0000-0000-0000-000000000000",
        "OUTLOOK_TENANT_ID": "common"
      }
    }
  }
}
```

### Separate servers per access level

Run a read-only server for everyday use and a `dangerous` one that you enable only when needed:

```json
{
  "mcpServers": {
    "iobox": {
      "command": "/full/path/to/iobox-mcp",
      "env": { "IOBOX_MODE": "readonly" }
    },
    "iobox-write": {
      "command": "/full/path/to/iobox-mcp",
      "env": { "IOBOX_MODE": "dangerous" }
    }
  }
}
```

## Without a workspace

If no workspace is configured, email tools fall back to a single Gmail account using `CREDENTIALS_DIR`, `IOBOX_ACCOUNT`, and `credentials.json` — the same setup as the [CLI email commands](../cli/index.md). Calendar, file, and cross-type tools require a workspace.
