# send

Compose and send an email.

!!! note "Single account, not the workspace"
    `send` does not use your workspace or `iobox space` sessions. It sends from one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_standard.json`; `CREDENTIALS_DIR` defaults to the current directory. Outlook currently ignores `--account` and always uses the `default` token directory. See [CLI overview](index.md) for global options.

**Access mode:** `dangerous` only. Run as `iobox --mode dangerous send ...` or set `IOBOX_MODE=dangerous`.

## Syntax

```
iobox --mode dangerous [--provider gmail|outlook] [--account NAME] send [OPTIONS]
```

## Options

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--to` | `-t` | TEXT | *(required)* | Recipient email address |
| `--subject` | `-s` | TEXT | *(required)* | Email subject line |
| `--body` | `-b` | TEXT | `None` | Email body text (inline) |
| `--body-file` | `-f` | TEXT | `None` | Path to a file containing the body; a `.html` file is sent as HTML. Takes precedence over `--body` |
| `--cc` | | TEXT | `None` | CC recipients (comma-separated) |
| `--bcc` | | TEXT | `None` | BCC recipients (comma-separated) |
| `--html` | | FLAG | `False` | Send body as HTML |
| `--attach` | | TEXT | `None` | File path to attach (repeatable) |

One of `--body` or `--body-file` is required. Missing body or attachment files are reported before anything is sent.

## Examples

Plain text:

```bash
iobox --mode dangerous send --to recipient@example.com --subject "Hello" --body "Hi there!"
```

Body from a file, with CC:

```bash
iobox --mode dangerous send --to recipient@example.com --subject "Report" \
  --body-file ./report.txt --cc manager@example.com
```

HTML body (from a `.html` file) with attachments:

```bash
iobox --mode dangerous send --to team@example.com --subject "Invoice" \
  --body-file ./invoice.html --attach ./invoice.pdf --attach ./usage.xlsx
```

## Example Output

```
Email sent successfully. Message ID: 18e4a2b3c1d5f6a7
```

## Related Commands

- [`forward`](forward.md) — forward an existing email
- [`draft-create`](drafts.md#draft-create) — save a draft without sending (`standard` mode)
