# Drafts

Create, list, send, and delete email drafts.

!!! note "Single account, not the workspace"
    The draft commands do not use your workspace or `iobox space` sessions. They act on one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_{readonly|standard}.json`; `CREDENTIALS_DIR` defaults to the current directory. Outlook currently ignores `--account` and always uses the `default` token directory. See [CLI overview](index.md) for global options.

## Commands

| Command | Access mode | Description |
|---|---|---|
| `draft-list` | all modes | List existing drafts |
| `draft-create` | `standard` or `dangerous` | Create a draft without sending |
| `draft-send` | `standard` or `dangerous` | Send an existing draft |
| `draft-delete` | `standard` or `dangerous` | Permanently delete a draft |

`standard` is the default mode, so no `--mode` flag is needed unless `IOBOX_MODE` is set to `readonly`.

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
| `--body-file` | `-f` | TEXT | `None` | Path to a file containing the body; a `.html` file is used as HTML. Takes precedence over `--body` |
| `--cc` | | TEXT | `None` | CC recipients (comma-separated) |
| `--bcc` | | TEXT | `None` | BCC recipients (comma-separated) |
| `--html` | | FLAG | `False` | Use HTML content type |
| `--attach` | | TEXT | `None` | File path to attach (repeatable). Each path must exist |

One of `--body` or `--body-file` is required.

### Example

```bash
iobox draft-create --to recipient@example.com --subject "Draft Report" \
  --body-file ./report.txt
```

Output:

```
Draft created successfully. Draft ID: r18e4a2b3c1d5f6a7
```

---

## draft-list

List drafts.

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
iobox draft-send --draft-id DRAFT_ID
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--draft-id` | | TEXT | *(required)* | ID of the draft to send |

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
iobox draft-delete --draft-id DRAFT_ID
```

### Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--draft-id` | | TEXT | *(required)* | ID of the draft to delete |

### Example

```bash
iobox draft-delete --draft-id r18e4a2b3c1d5f6a7
```

Output:

```
Draft deleted successfully. Draft ID: r18e4a2b3c1d5f6a7
```

## Related Commands

- [`send`](send.md) — compose and send immediately (`dangerous` mode)
- [`forward`](forward.md) — forward an existing email (`dangerous` mode)
