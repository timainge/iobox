# save

Save emails as Markdown files. Supports single email, thread, and batch modes.

!!! note "Single account, not the workspace"
    `save` does not use your workspace or `iobox space` sessions. It acts on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_{readonly|standard}.json`; `CREDENTIALS_DIR` defaults to the current directory. See [CLI overview](index.md) for global options.

**Access mode:** available in all modes (`readonly`, `standard`, `dangerous`).

## Syntax

```
iobox [--provider gmail|outlook] [--account NAME] save [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | `-m` | TEXT | `None` | ID of a specific email to save (single mode) |
| `--thread-id` | | TEXT | `None` | ID of a thread to save as a single file |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--max` | | INT | `10` | Maximum number of emails in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search (batch mode) |
| `--start-date` | `-s` | TEXT | `None` | Start date `YYYY/MM/DD`; overrides `--days` (batch mode) |
| `--end-date` | `-e` | TEXT | `None` | End date `YYYY/MM/DD`, inclusive (batch mode) |
| `--output-dir` | `-o` | TEXT | `.` | Directory to save Markdown files to (created if missing) |
| `--html-preferred` | | FLAG | `True` | Prefer the HTML body when available. Always on; there is no `--no-html-preferred` |
| `--download-attachments` | | FLAG | `False` | Download attachments (single and batch modes; not thread mode) |
| `--attachment-types` | | TEXT | `None` | Only download these extensions, comma-separated (e.g. `pdf,docx`) |
| `--include-spam-trash` | | FLAG | `False` | Include messages from SPAM and TRASH (batch mode) |
| `--sync` | | FLAG | `False` | Incremental sync: later runs only search from the last complete `--sync` run (batch mode) |

One of `--message-id`, `--thread-id`, or `--query` is required. If more than one is given, `--thread-id` wins, then `--message-id`.

## Modes

### Single Email Mode

```bash
iobox save --message-id 18e4a2b3c1d5f6a7 -o ./emails
```

### Thread Mode

Save all messages in a thread as one file named `{subject-slug}_{thread_id}.md`:

```bash
iobox save --thread-id 18e4a2b3c1d5f6a7 -o ./emails
```

### Batch Mode

Save all emails matching a query. Re-running into the same directory skips emails already saved there (matched by the `message_id` in each file's frontmatter). Use `--sync` to keep a folder up to date cheaply (below).

```bash
iobox save -q "from:newsletter@example.com" -d 14 --max 50 -o ./emails
```

With `--sync`, iobox records the query, the start time of the last complete run, and the IDs it saved in `.iobox-sync.json` in the output directory. Later runs with the **same query** search from the day before that run (instead of `-d`/`--start-date`) and skip messages already saved, so mail that arrived while the previous run was in progress isn't missed. The window only moves forward when a run is complete — every match saved and fewer than `--max` matches — otherwise the next run retries from the same point. Changing the query starts a fresh full sync. This works the same for Gmail and Outlook.

## Examples

Save last week's reports with PDF and Excel attachments:

```bash
iobox save -q "has:attachment from:reports@example.com" -d 7 -o ./reports \
  --download-attachments --attachment-types pdf,xlsx
```

Incremental sync:

```bash
iobox save -q "label:important" -o ./important --sync
```

Save from a second Gmail account:

```bash
iobox --account work save -q "label:invoices" -o ./invoices
```

## Output Format

Each email is saved as `YYYY-MM-DD-subject-slug.md` (date from the email's `Date` header; a numeric suffix is added if the name is taken):

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

`cc` and `reply_to` are added when present. Attachments are saved to `attachments/{message_id}/` inside the output directory; inline parts (signature logos, `cid:` images) are skipped. See [Output format](../reference/output-format.md).

## Related Commands

- [`search`](search.md) — preview emails before saving
- [`forward`](forward.md) — forward emails to a recipient
