# label

Change read state, star, archive, or labels on one or more emails. Supports single message and batch modes.

!!! note "Single account, not the workspace"
    `label` does not use your workspace or `iobox space` sessions. It acts on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_standard.json`; `CREDENTIALS_DIR` defaults to the current directory. See [CLI overview](index.md) for global options.

**Access mode:** `standard` (the default) or `dangerous`. Not available in `readonly`.

## Syntax

```
iobox [--provider gmail|outlook] [--account NAME] label [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | | TEXT | `None` | Message ID for single message mode |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--max-results` | `-m` | INT | `10` | Maximum number of emails in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search (batch mode) |
| `--mark-read` | | FLAG | `False` | Mark as read |
| `--mark-unread` | | FLAG | `False` | Mark as unread |
| `--star` | | FLAG | `False` | Star (Outlook: flag) |
| `--unstar` | | FLAG | `False` | Unstar (Outlook: clear flag) |
| `--archive` | | FLAG | `False` | Archive. Gmail removes the `INBOX` label; Outlook moves to the Archive folder |
| `--add` | | TEXT | `None` | Add a label by name (created if it doesn't exist in Gmail; Outlook: category) |
| `--remove` | | TEXT | `None` | Remove a label by name (Outlook: category) |

One of `--message-id` or `--query` is required; `--message-id` wins if both are given. Several operation flags can be combined; batch mode applies them without a confirmation prompt.

## Examples

Mark one message as read:

```bash
iobox label --message-id 18e4a2b3c1d5f6a7 --mark-read
```

Star and archive last week's newsletters:

```bash
iobox label -q "from:newsletter@example.com" -d 7 --star --archive
```

Add a label to matching emails:

```bash
iobox label -q "subject:invoice" -d 30 --add "Finance"
```

Remove a label from one message:

```bash
iobox label --message-id 18e4a2b3c1d5f6a7 --remove "Needs Review"
```

## Example Output

Single mode:

```
Labels updated for message 18e4a2b3c1d5f6a7
```

Batch mode:

```
Labels updated for 5 email(s)
```

## Related Commands

- [`search`](search.md) — find message IDs
- [`trash`](trash.md) — move messages to trash
- [`save`](save.md) — save emails as Markdown
