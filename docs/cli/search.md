# search

Search for emails in Gmail using Gmail's search syntax.

## Syntax

```
iobox search [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--query` | `-q` | TEXT | *(required)* | Search query using Gmail search syntax |
| `--max-results` | `-m` | INT | `10` | Maximum number of results to return |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--start-date` | `-s` | TEXT | `None` | Start date in `YYYY/MM/DD` format (overrides `--days`) |
| `--end-date` | `-e` | TEXT | `None` | End date in `YYYY/MM/DD` format (requires `--start-date`) |
| `--verbose` | `-v` | FLAG | `False` | Show detailed information including labels |
| `--debug` | | FLAG | `False` | Show raw API response fields for the first result |
| `--include-spam-trash` | | FLAG | `False` | Include messages from SPAM and TRASH |

## Examples

Search for emails from a specific sender in the last 7 days:

```bash
iobox search -q "from:newsletter@example.com"
```

Search for up to 20 emails in the last 30 days with verbose output:

```bash
iobox search -q "subject:invoice" -m 20 -d 30 -v
```

Search within a specific date range:

```bash
iobox search -q "label:important" -s 2026/01/01 -e 2026/01/31
```

## Example Output

```
Searching for emails matching: from:newsletter@example.com
Found 3 emails:
1. Weekly Digest - March 2026
   ID: 18e4a2b3c1d5f6a7
   Preview: Here's what happened this week in tech...
   From: newsletter@example.com
   Date: 01/03/2026 09:00
   ----------------------------------------
```

With `--verbose`:

```
1. Weekly Digest - March 2026
   ID: 18e4a2b3c1d5f6a7
   Preview: Here's what happened this week in tech...
   From: newsletter@example.com
   Date: 01/03/2026 09:00
   Labels: INBOX, UNREAD
```

## Gmail Search Syntax

Common query operators:

| Operator | Example | Description |
|---|---|---|
| `from:` | `from:user@example.com` | Filter by sender |
| `to:` | `to:me` | Filter by recipient |
| `subject:` | `subject:invoice` | Filter by subject |
| `label:` | `label:important` | Filter by label |
| `has:attachment` | `has:attachment` | Only emails with attachments |
| `is:unread` | `is:unread` | Only unread emails |

## Related Commands

- [`save`](save.md) — save matching emails as Markdown files
- [`forward`](forward.md) — forward matching emails to a recipient
- [`label`](label.md) — modify labels on matching emails
