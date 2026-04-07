# forward

Forward emails to a recipient. Supports single email and batch modes.

## Syntax

```
iobox forward [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | `-m` | TEXT | `None` | ID of a specific email to forward |
| `--query` | `-q` | TEXT | `None` | Search query for batch forward mode |
| `--to` | `-t` | TEXT | *(required)* | Recipient email address |
| `--max` | | INT | `10` | Maximum number of emails in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--start-date` | `-s` | TEXT | `None` | Start date in `YYYY/MM/DD` format |
| `--end-date` | `-e` | TEXT | `None` | End date in `YYYY/MM/DD` format |
| `--note` | `-n` | TEXT | `None` | Optional note to prepend to forwarded email |

One of `--message-id` or `--query` is required.

## Examples

Forward a single email by ID:

```bash
iobox forward --message-id 18e4a2b3c1d5f6a7 --to colleague@example.com
```

Forward with a note:

```bash
iobox forward --message-id 18e4a2b3c1d5f6a7 --to colleague@example.com \
  --note "FYI — see below."
```

Batch forward recent reports to a team:

```bash
iobox forward -q "from:reports@example.com" --to team@example.com -d 7
```

## Example Output

Single mode:

```
Forwarding email 18e4a2b3c1d5f6a7 to colleague@example.com...
Successfully forwarded. New message ID: 18f5b3c4d2e6g7h8
```

Batch mode:

```
Searching for emails matching: from:reports@example.com
Found 2 emails to forward.
Forwarding: Monthly Report - March 2026
Forwarding: Monthly Report - February 2026

Forwarded 2 emails to team@example.com.
```

## Related Commands

- [`search`](search.md) — preview emails before forwarding
- [`send`](send.md) — compose and send a new email
