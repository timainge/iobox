# search

Search one mailbox and print matching messages.

!!! note "Single account, not the workspace"
    `search` does not use your workspace or `iobox space` sessions. It acts on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_{readonly|standard}.json`; `CREDENTIALS_DIR` defaults to the current directory. See [CLI overview](index.md) for global options.

**Access mode:** available in all modes (`readonly`, `standard`, `dangerous`).

## Syntax

```
iobox [--provider gmail|outlook] [--account NAME] search [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--query` | `-q` | TEXT | *(required)* | Search query. Gmail search syntax for Gmail; passed to Microsoft Graph `$search` (KQL) for Outlook |
| `--max-results` | `-m` | INT | `10` | Maximum number of results to return |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--start-date` | `-s` | TEXT | `None` | Start date `YYYY/MM/DD` (or `YYYY-MM-DD`); overrides `--days` |
| `--end-date` | `-e` | TEXT | `None` | End date `YYYY/MM/DD` (or `YYYY-MM-DD`), inclusive |
| `--verbose` | `-v` | FLAG | `False` | Also show labels for each result |
| `--debug` | | FLAG | `False` | Show the raw fields of the first result |
| `--include-spam-trash` | | FLAG | `False` | Include messages from SPAM and TRASH |

The `--days` window always applies unless `--start-date` is given, so a query alone only searches the last 7 days. `--end-date` is inclusive: `-s 2026/03/01 -e 2026/03/31` covers all of March.

## Examples

Search for emails from a sender in the last 7 days:

```bash
iobox search -q "from:newsletter@example.com"
```

Up to 20 results from the last 30 days, with labels:

```bash
iobox search -q "subject:invoice" -m 20 -d 30 -v
```

Search a date range:

```bash
iobox search -q "label:important" -s 2026/01/01 -e 2026/01/31
```

Search a different account or provider:

```bash
iobox --account work search -q "from:boss@example.com"
iobox --provider outlook search -q "from:boss@example.com"
```

## Example Output

```
Searching for emails matching: from:newsletter@example.com

Found 1 emails:
1. Weekly Digest - March 2026
   ID: 18e4a2b3c1d5f6a7
   Preview: Here's what happened this week in tech...
   From: newsletter@example.com
   Date: 01/03/2026 09:00
   ----------------------------------------
```

With `--verbose`, the separator line is replaced by `Labels: INBOX, UNREAD`.

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

Both providers search all mail; spam and trash (Outlook: Junk and Deleted Items) are excluded unless `--include-spam-trash` is given.

## Related Commands

- [`save`](save.md) — save matching emails as Markdown files
- [`forward`](forward.md) — forward matching emails to a recipient
- [`label`](label.md) — modify labels on matching emails
