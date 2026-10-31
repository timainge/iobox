# Output Format

Every resource iobox saves is a Markdown file with YAML frontmatter. The frontmatter carries structured metadata (for scripts, static-site generators, or LLM retrieval); the body carries the content.

## Email

Produced by `iobox save`, the `save_email` / `save_emails_by_query` MCP tools, and `convert_email_to_markdown` in the SDK.

```markdown
---
message_id: 18e4a2b3c1d5f6a7
thread_id: 18e4a2b3c1d5f6a7
subject: Weekly Digest
from: Newsletter <newsletter@example.com>
to: you@gmail.com
cc: team@example.com
date: Mon, 05 Jan 2026 09:00:00 +0000
labels:
  - INBOX
  - CATEGORY_UPDATES
saved_date: 2026-01-06T10:30:00.123456
---

Here's what happened this week…
```

| Field | Notes |
|---|---|
| `message_id`, `thread_id` | Provider IDs. Outlook IDs are ImmutableIds. |
| `from`, `to`, `subject`, `date` | As in the message headers |
| `cc`, `reply_to` | Only when present |
| `labels` | Gmail labels, or Outlook categories |
| `attachments` | Only when attachments are included |
| `saved_date` | When the file was written |

HTML bodies are converted to Markdown; plain-text bodies are kept as-is.

**Filenames:** `YYYY-MM-DD-subject-slug.md`. If the name exists, a numeric suffix is added (`…_1.md`).

**Threads** (`save_thread`, `iobox save --thread-id`) are written as a single file containing every message in order.

### Attachments

With attachment downloads enabled, files are written to `OUTPUT_DIR/attachments/MESSAGE_ID/`. Inline parts — signature logos, `cid:` images — are skipped unless you ask for them (`include_inline=True`).

The `save_email` MCP tool returns a manifest so callers don't have to walk the directory:

```json
{
  "markdown_path": "emails/2026-01-05-weekly-digest.md",
  "attachments": [
    {"filename": "report.pdf", "path": "emails/attachments/18e4…/report.pdf",
     "inline": false, "mime_type": "application/pdf", "size": 48213}
  ]
}
```

## Event

```markdown
---
id: abc123
title: Q4 Planning Session
start: 2026-03-16T10:00:00+11:00
end: 2026-03-16T12:00:00+11:00
all_day: false
organizer: boss@example.com
attendees:
  - email: alice@example.com
    name: Alice
    response_status: accepted
location: Conference Room A
meeting_url: https://meet.google.com/abc-defg-hij
status: confirmed
provider_id: google_calendar
resource_type: event
url: https://www.google.com/calendar/event?eid=…
saved_date: '2026-03-24'
---

Review Q4 plans and finalise budget allocations.
```

The body is the event description. Fields with no value are omitted.

## File

```markdown
---
id: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs
title: Q4 Planning Notes
name: Q4 Planning Notes
mime_type: application/vnd.google-apps.document
size: 0
is_folder: false
provider_id: google_drive
resource_type: file
url: https://docs.google.com/document/d/1Bxi…/edit
saved_date: '2026-03-24'
---

Key decisions from the Q4 planning session…
```

The body is the extracted text content when it has been fetched. See [Provider behaviour](providers.md#google-drive) for which file types yield text.
