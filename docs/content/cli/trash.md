# trash

Move emails to trash or restore them from trash. Supports single message and batch modes.

!!! note "Single account, not the workspace"
    `trash` does not use your workspace or `iobox space` sessions. It acts on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_standard.json`; `CREDENTIALS_DIR` defaults to the current directory. See [CLI overview](index.md) for global options.

**Access mode:** `dangerous` only. Run as `iobox --mode dangerous trash ...` or set `IOBOX_MODE=dangerous`.

## Syntax

```
iobox --mode dangerous [--provider gmail|outlook] [--account NAME] trash [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | | TEXT | `None` | Message ID for single message mode |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--untrash` | | FLAG | `False` | Restore from trash instead of trashing (Outlook restores to the Inbox) |
| `--days` | `-d` | INT | `7` | Number of days back to search (batch mode) |
| `--max-results` | `-m` | INT | `10` | Maximum number of emails in batch mode |

One of `--message-id` or `--query` is required; `--message-id` wins if both are given.

!!! warning "Batch mode asks for confirmation"
    With `--query`, iobox shows how many emails matched and asks before trashing or restoring them. Single mode does not prompt. Outlook moves messages to Deleted Items.

With `--untrash --query`, iobox searches trashed mail: on Gmail the query is prefixed with `in:trash` (unless it already contains an `in:` operator) and spam/trash are included in the search.

!!! warning "Outlook: restore by `--message-id`"
    Outlook searches only the Inbox, so `--untrash --query` won't find messages in Deleted Items. Restore Outlook messages one at a time with `--message-id`.

## Examples

Trash one message:

```bash
iobox --mode dangerous trash --message-id 18e4a2b3c1d5f6a7
```

Restore it:

```bash
iobox --mode dangerous trash --message-id 18e4a2b3c1d5f6a7 --untrash
```

Restore everything from a sender trashed in the last 30 days (Gmail):

```bash
iobox --mode dangerous trash -q "from:spam@example.com" -d 30 --untrash
```

Trash everything from a sender in the last 30 days:

```bash
iobox --mode dangerous trash -q "from:spam@example.com" -d 30
```

## Example Output

Single mode:

```
Trashed message 18e4a2b3c1d5f6a7
```

Batch mode:

```
Are you sure you want to trash 5 email(s)? [y/N]: y
Trashed 5 email(s)
```

Restore:

```
Restored message 18e4a2b3c1d5f6a7
```

## Related Commands

- [`search`](search.md) — find message IDs
- [`label`](label.md) — archive or relabel without trashing
