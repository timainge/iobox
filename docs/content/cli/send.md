# send

Compose and send an email via Gmail.

## Syntax

```
iobox send [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--to` | `-t` | TEXT | *(required)* | Recipient email address |
| `--subject` | `-s` | TEXT | *(required)* | Email subject line |
| `--body` | `-b` | TEXT | `None` | Email body text (inline) |
| `--body-file` | `-f` | TEXT | `None` | Path to file containing email body |
| `--cc` | | TEXT | `None` | CC recipients (comma-separated) |
| `--bcc` | | TEXT | `None` | BCC recipients (comma-separated) |
| `--html` | | FLAG | `False` | Send body as HTML content |
| `--attach` | | TEXT | `None` | File path to attach (repeatable) |

One of `--body` or `--body-file` is required.

## Examples

Send a simple plain text email:

```bash
iobox send --to recipient@example.com --subject "Hello" --body "Hi there!"
```

Send from a file with CC:

```bash
iobox send --to recipient@example.com --subject "Report" \
  --body-file ./report.txt --cc manager@example.com
```

Send an HTML email with an attachment:

```bash
iobox send --to recipient@example.com --subject "Invoice" \
  --body-file ./invoice.html --html --attach ./invoice.pdf
```

Attach multiple files:

```bash
iobox send --to team@example.com --subject "Files" --body "See attached" \
  --attach ./file1.pdf --attach ./file2.xlsx
```

## Example Output

```
Email sent successfully. Message ID: 18e4a2b3c1d5f6a7
```

## Related Commands

- [`forward`](forward.md) — forward an existing email
- [`draft-create`](drafts.md) — save a draft without sending
