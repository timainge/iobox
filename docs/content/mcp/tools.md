# Tool Reference

Every tool below is registered only in the [access mode](configuration.md#access-modes) shown. Full docstrings — which hosts surface to the model — are in `src/iobox/mcp_server.py`.

**Common arguments.** Almost every tool also accepts:

- `provider` — a [slot name](multi-account.md#targeting-one-account). Search and list tools fan out across all slots when omitted; fetch and write tools use the first slot of their type.
- `workspace` — a workspace name. Defaults to the active workspace.

`search_workspace` takes `workspace` but not `provider`; `semantic_search_workspace` takes neither.

**File paths.** `output_dir`, `output_path`, `attachments`, and `local_path` are confined to the [file access root](configuration.md#file-access-root) (`IOBOX_MCP_ROOT`, default `~/iobox`). Relative paths resolve under it, and `output_dir="."` means the root itself. Downloads never overwrite an existing file.

## Cross-type

| Tool | Mode | Description | Key arguments |
|---|---|---|---|
| `search_workspace` | readonly | Search email, events, and files in parallel; results merged by date | `query`, `types=["email","event","file"]`, `max_results=10` |
| `semantic_search_workspace` | readonly | Vector search over the local embedding index (needs `iobox[semantic]` and a built index) | `query`, `types`, `top_k=10`, `backend="openai"` |

## Email

| Tool | Mode | Description | Key arguments |
|---|---|---|---|
| `search_gmail` | readonly | Search email (Gmail syntax; translated for Outlook). Fans out across email slots. | `query`, `max_results=10`, `days=7`, `start_date`, `end_date`, `include_spam_trash` |
| `get_email` | readonly | Fetch one message with control over body size | `message_id`, `body="markdown"` (`none`/`text`/`html`/`markdown`), `max_body_chars` |
| `get_emails` | readonly | Fetch many messages in one call — the fast path for triage | `message_ids`, `body="none"`, `max_body_chars` |
| `save_email` | readonly | Save one message as Markdown; returns a manifest of written files | `message_id`, `output_dir="."`, `download_attachments`, `attachment_types`, `include_inline` |
| `save_thread` | readonly | Save a whole thread as one Markdown file | `thread_id`, `output_dir="."` |
| `save_emails_by_query` | readonly | Search and save every match; optional incremental sync | `query`, `output_dir`, `max_results=10`, `days=7`, `download_attachments`, `sync` |
| `download_email_attachment` | readonly | Download one attachment to disk or return it as base64 | `message_id`, `attachment_id`, `output_path`, `return_base64` |
| `list_gmail_drafts` | readonly | List drafts | `max_results=10` |
| `list_labels` | readonly | List labels (Gmail) or categories (Outlook) | — |
| `create_gmail_draft` | standard | Create a draft | `to`, `subject`, `body`, `cc`, `bcc`, `html`, `attachments` |
| `send_gmail_draft` | dangerous | Send an existing draft | `draft_id` |
| `delete_gmail_draft` | standard | Delete a draft | `draft_id` |
| `create_label` | standard | Create a label, including nested (`Parent/Child`) | `name` |
| `modify_labels` | standard | Read/unread, star, archive, add/remove label on one message | `message_id`, `mark_read`, `mark_unread`, `star`, `unstar`, `archive`, `add_label`, `remove_label` |
| `batch_modify_gmail_labels` | standard | Same actions for every message matching a query | `query`, `max_results=10`, `days=7`, …same flags |
| `send_email` | dangerous | Send a new email | `to`, `subject`, `body`, `cc`, `bcc`, `html`, `attachments` |
| `forward_gmail` | dangerous | Forward a message | `message_id`, `to`, `note` |
| `batch_forward_gmail` | dangerous | Forward every message matching a query | `query`, `to`, `max_results=10`, `days=7`, `note` |
| `trash_gmail` | dangerous | Move a message to trash | `message_id` |
| `untrash_gmail` | dangerous | Restore a message from trash | `message_id` |
| `batch_trash_gmail` | dangerous | Trash every message matching a query | `query`, `max_results=10`, `days=7` |

Despite the `gmail` in some names, email tools work against whichever email provider the slot uses (Gmail or Outlook).

!!! tip "Keeping responses small"
    A raw HTML email can be tens of thousands of characters. For triage, search first, then call `get_emails(message_ids=[…], body="none")` to scan headers, and only fetch bodies (`body="markdown"`, `max_body_chars=4000`) for the messages that matter.

## Calendar

| Tool | Mode | Description | Key arguments |
|---|---|---|---|
| `list_events` | readonly | List events; fans out across calendar slots | `after`, `before` (YYYY-MM-DD), `text`, `max_results=25` |
| `get_event` | readonly | Get one event | `event_id` |
| `save_event` | readonly | Save an event as Markdown | `event_id`, `output_dir="."` |
| `create_event` | standard | Create an event | `title`, `start`, `end`, `description`, `location`, `attendees`, `all_day` |
| `update_event` | standard | Update fields on an event | `event_id`, `updates` (dict) |
| `rsvp_event` | standard | Respond to an invite | `event_id`, `response` (`accepted`/`declined`/`tentative`) |
| `delete_event` | dangerous | Delete an event | `event_id` |

## Files

| Tool | Mode | Description | Key arguments |
|---|---|---|---|
| `list_files` | readonly | Search files; fans out across file slots | `query`, `max_results=20` |
| `get_file` | readonly | File metadata | `file_id` |
| `get_file_content` | readonly | Extracted text (Docs → text, Sheets → CSV, text files as-is) | `file_id` |
| `save_file` | readonly | Save metadata and extracted text as Markdown | `file_id`, `output_dir="."` |
| `download_file` | readonly | Download the binary to disk | `file_id`, `output_path` |
| `upload_file` | standard | Upload a local file | `local_path`, `name`, `parent_id` |
| `create_folder` | standard | Create a folder | `name`, `parent_id` |
| `delete_file` | standard | Trash a file, or delete permanently | `file_id`, `permanent=False` |

## Workspace and auth

| Tool | Mode | Description |
|---|---|---|
| `list_workspaces` | readonly | All workspaces and which is active |
| `get_active_workspace` | readonly | The active workspace name |
| `list_provider_slots` | readonly | Every email/calendar/file slot in a workspace |
| `workspace_auth_status` | readonly | Per-slot auth check (calls each provider's profile endpoint) |
| `check_auth` | readonly | Legacy single-account Gmail auth check |
| `set_active_workspace` | standard | Switch the active workspace |

## Return values

- Search and list tools return lists of dicts. Email dicts use `from` (not `from_`) for the sender.
- Write tools return a dict with `message_id` and `status`.
- Errors are returned as `{"error": "..."}` rather than raised, so the assistant can see and react to them.
