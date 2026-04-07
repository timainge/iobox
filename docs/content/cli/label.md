# label

Add or remove labels on one or more Gmail messages. Supports single message and batch modes.

## Syntax

```
iobox label [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | | TEXT | `None` | Message ID for single message mode |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--max-results` | `-m` | INT | `10` | Maximum number of messages in batch mode |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--mark-read` | | FLAG | `False` | Mark message(s) as read |
| `--mark-unread` | | FLAG | `False` | Mark message(s) as unread |
| `--star` | | FLAG | `False` | Star message(s) |
| `--unstar` | | FLAG | `False` | Unstar message(s) |
| `--archive` | | FLAG | `False` | Archive message(s) (remove from INBOX) |
| `--add` | | TEXT | `None` | Add a label by name |
| `--remove` | | TEXT | `None` | Remove a label by name |

One of `--message-id` or `--query` is required.

## Examples

Mark a single message as read:

```bash
iobox label --message-id 18e4a2b3c1d5f6a7 --mark-read
```

Star and archive all newsletters from the last week:

```bash
iobox label -q "from:newsletter@example.com" -d 7 --star --archive
```

Add a custom label to matching emails:

```bash
iobox label -q "subject:invoice" -d 30 --add "Finance"
```

Remove a label from a specific message:

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
Labels updated for 5 message(s)
```

## Related Commands

- [`search`](search.md) — find message IDs
- [`trash`](trash.md) — move messages to trash
- [`save`](save.md) — save emails as Markdown
