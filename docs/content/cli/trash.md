# trash

Move messages to trash or restore them from trash. Supports single message and batch modes.

## Syntax

```
iobox trash [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--message-id` | | TEXT | `None` | Message ID for single message mode |
| `--query` | `-q` | TEXT | `None` | Search query for batch mode |
| `--untrash` | | FLAG | `False` | Restore from trash instead of trashing |
| `--days` | `-d` | INT | `7` | Number of days back to search |
| `--max-results` | `-m` | INT | `10` | Maximum number of messages in batch mode |

One of `--message-id` or `--query` is required.

!!! warning "Batch trash requires confirmation"
    When using `--query`, iobox will show how many messages will be trashed and
    ask for confirmation before proceeding.

## Examples

Trash a single message:

```bash
iobox trash --message-id 18e4a2b3c1d5f6a7
```

Restore a message from trash:

```bash
iobox trash --message-id 18e4a2b3c1d5f6a7 --untrash
```

Trash all emails from a spam sender in the last 30 days:

```bash
iobox trash -q "from:spam@example.com" -d 30
```

## Example Output

Single mode:

```
Trashed message 18e4a2b3c1d5f6a7
```

Batch mode (with confirmation prompt):

```
Are you sure you want to trash 5 message(s)? [y/N]: y
Trashed 5 message(s)
```

Restore mode:

```
Restored message 18e4a2b3c1d5f6a7
```

## Related Commands

- [`search`](search.md) — find message IDs
- [`label`](label.md) — modify labels without trashing
