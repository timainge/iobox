# forward

Forward emails to a recipient. Supports single email and batch modes.

!!! note "Single account, not the workspace"
    `forward` does not use your workspace or `iobox space` sessions. It acts on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_standard.json`; `CREDENTIALS_DIR` defaults to the current directory. Outlook currently ignores `--account` and always uses the `default` token directory. See [CLI overview](index.md) for global options.

**Access mode:** `dangerous` only. Run as `iobox --mode dangerous forward ...` or set `IOBOX_MODE=dangerous`.

## Syntax

```
iobox --mode dangerous [--provider gmail|outlook] [--account NAME] forward [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | `-m` | TEXT | `None` | ID of a specific email to forward |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--to` | `-t` | TEXT | *(required)* | Recipient email address |
| `--max` | | INT | `10` | Maximum number of emails in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search (batch mode) |
| `--start-date` | `-s` | TEXT | `None` | Start date `YYYY/MM/DD`; overrides `--days` (batch mode) |
| `--end-date` | `-e` | TEXT | `None` | End date `YYYY/MM/DD` (batch mode) |
| `--note` | `-n` | TEXT | `None` | Note to prepend to the forwarded email |

One of `--message-id` or `--query` is required; `--message-id` wins if both are given. Batch mode forwards every match without a confirmation prompt, so preview with [`search`](search.md) first.

## Examples

Forward one email:

```bash
iobox --mode dangerous forward --message-id 18e4a2b3c1d5f6a7 --to colleague@example.com
```

With a note:

```bash
iobox --mode dangerous forward --message-id 18e4a2b3c1d5f6a7 --to colleague@example.com \
  --note "FYI, see below."
```

Batch forward this week's reports:

```bash
iobox --mode dangerous forward -q "from:reports@example.com" --to team@example.com -d 7
```

## Example Output

Single mode:

```
Forwarding email 18e4a2b3c1d5f6a7 to colleague@example.com...
Successfully forwarded. New message ID: 18f5b3c4d2e6a7b8
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
