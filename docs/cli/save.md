# save

Save emails as Markdown files. Supports single email, thread, and batch modes.

## Syntax

```
iobox save [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | `-m` | TEXT | `None` | ID of a specific email to save (single mode) |
| `--thread-id` | | TEXT | `None` | ID of a thread to save as a single file |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--max` | | INT | `10` | Maximum number of emails in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--start-date` | `-s` | TEXT | `None` | Start date in `YYYY/MM/DD` format |
| `--end-date` | `-e` | TEXT | `None` | End date in `YYYY/MM/DD` format |
| `--output-dir` | `-o` | TEXT | `.` | Directory to save Markdown files |
| `--html-preferred` | | FLAG | `True` | Prefer HTML content if available |
| `--download-attachments` | | FLAG | `False` | Download email attachments |
| `--attachment-types` | | TEXT | `None` | Filter attachments by extension (e.g. `pdf,docx`) |
| `--include-spam-trash` | | FLAG | `False` | Include messages from SPAM and TRASH |
| `--sync` | | FLAG | `False` | Only fetch new emails since last run (incremental sync) |

One of `--message-id`, `--thread-id`, or `--query` is required.

## Modes

### Single Email Mode

Save one specific email by its message ID:

```bash
iobox save --message-id 18e4a2b3c1d5f6a7 -o ./emails
```

### Thread Mode

Save all messages in a thread as a single Markdown file:

```bash
iobox save --thread-id 18e4a2b3c1d5f6a7 -o ./emails
```

### Batch Mode

Save all emails matching a search query:

```bash
iobox save -q "from:newsletter@example.com" -d 14 --max 50 -o ./emails
```

## Examples

Save emails from the last week with attachments:

```bash
iobox save -q "has:attachment from:reports@example.com" -d 7 -o ./reports \
  --download-attachments --attachment-types pdf,xlsx
```

Incremental sync — only new emails since last run:

```bash
iobox save -q "label:important" -o ./important --sync
```

## Output Format

Each email is saved as a `.md` file named `YYYY-MM-DD-subject-slug.md`:

```markdown
---
date: Mon, 01 Mar 2026 09:00:00 +0000
from: sender@example.com
labels:
  - INBOX
message_id: 18e4a2b3c1d5f6a7
saved_date: 2026-03-02T10:30:00
subject: Email Subject
thread_id: 18e4a2b3c1d5f6a7
to: you@example.com
---

Email body content in Markdown...
```

Attachments are saved to `attachments/{message_id}/` within the output directory.

## Related Commands

- [`search`](search.md) — preview emails before saving
- [`forward`](forward.md) — forward emails to a recipient
