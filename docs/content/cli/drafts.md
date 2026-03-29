# Drafts

Manage Gmail drafts: create, list, send, and delete.

## Commands

| Command | Description |
|---|---|
| `draft-create` | Create a draft without sending |
| `draft-list` | List existing drafts |
| `draft-send` | Send an existing draft |
| `draft-delete` | Permanently delete a draft |

---

## draft-create

Create an email draft without sending it.

### Syntax

```
iobox draft-create [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--to` | `-t` | TEXT | *(required)* | Recipient email address |
| `--subject` | `-s` | TEXT | *(required)* | Email subject line |
| `--body` | `-b` | TEXT | `None` | Email body text (inline) |
| `--body-file` | `-f` | TEXT | `None` | Path to file containing email body |
| `--cc` | | TEXT | `None` | CC recipients (comma-separated) |
| `--bcc` | | TEXT | `None` | BCC recipients (comma-separated) |
| `--html` | | FLAG | `False` | Use HTML content type |
| `--attach` | | TEXT | `None` | File path to attach (repeatable) |

### Example

```bash
iobox draft-create --to recipient@example.com --subject "Draft Report" \
  --body-file ./report.md
```

Output:

```
Draft created successfully. Draft ID: r18e4a2b3c1d5f6a7
```

---

## draft-list

List Gmail drafts.

### Syntax

```
iobox draft-list [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--max` | `-m` | INT | `10` | Maximum number of drafts to list |

### Example

```bash
iobox draft-list --max 5
```

Output:

```
Found 2 draft(s):

ID: r18e4a2b3c1d5f6a7
  Subject: Draft Report
  Preview: Here is the quarterly report for...

ID: r29f5b4d6e3a7c8b9
  Subject: Meeting Notes
  Preview: Key points from today's standup...
```

---

## draft-send

Send an existing draft by its draft ID.

### Syntax

```
iobox draft-send [OPTIONS]
```

### Options

| Option | Type | Description |
|---|---|---|
| `--draft-id` | TEXT *(required)* | ID of the draft to send |

### Example

```bash
iobox draft-send --draft-id r18e4a2b3c1d5f6a7
```

Output:

```
Draft sent successfully. Message ID: 18e4a2b3c1d5f6a7
```

---

## draft-delete

Permanently delete a draft.

### Syntax

```
iobox draft-delete [OPTIONS]
```

### Options

| Option | Type | Description |
|---|---|---|
| `--draft-id` | TEXT *(required)* | ID of the draft to delete |

### Example

```bash
iobox draft-delete --draft-id r18e4a2b3c1d5f6a7
```

Output:

```
Draft deleted successfully. Draft ID: r18e4a2b3c1d5f6a7
```

## Related Commands

- [`send`](send.md) — compose and send immediately
- [`forward`](forward.md) — forward an existing email
