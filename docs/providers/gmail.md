# Gmail Provider

The `GmailProvider` is the default iobox provider, backed by the Gmail API v3 via OAuth 2.0.

## Prerequisites

- Python 3.10+
- A Google Cloud project with the **Gmail API** enabled
- OAuth 2.0 credentials (Desktop app type) downloaded as `credentials.json`

## Setup

### 1. Enable Gmail API

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable **Gmail API**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID** (Desktop app type)
6. Download and save as `credentials.json` in your project root

### 2. Authenticate

The first command you run triggers an OAuth flow in your browser:

```bash
iobox auth-status
```

Or via the workspace flow:

```bash
iobox space create personal
iobox space add gmail you@gmail.com --messages --read
```

### 3. Token storage

Tokens are stored per account and per scope tier:

```
~/.iobox/tokens/you@gmail.com/
  token_readonly.json    # gmail.readonly scope
  token_standard.json    # gmail.modify + gmail.compose scopes
```

Switching between `--mode readonly` and `--mode standard` never destroys an existing token. A broader token is automatically accepted in readonly mode.

## Access Modes

| Mode | Scopes | Available commands |
|---|---|---|
| `readonly` | `gmail.readonly` | search, save, draft-list |
| `standard` | `gmail.modify`, `gmail.compose` | + draft management, label |
| `dangerous` | same as standard | + send, forward, trash |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `IOBOX_PROVIDER` | `gmail` | Set to `gmail` (default) |
| `IOBOX_MODE` | `standard` | Access mode |
| `IOBOX_ACCOUNT` | `default` | Account profile name |
| `CREDENTIALS_DIR` | `.` | Directory for credentials and tokens |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | OAuth credentials path |

## CLI Commands

See [CLI Reference](../cli/search.md) for full command documentation.

```bash
# Search
iobox search -q "from:boss@example.com" -d 7

# Save
iobox save -q "label:important" --max 50 -o ./emails

# Send (dangerous mode)
iobox --mode dangerous send --to recipient@example.com --subject "Hi" --body "Hello"

# Multi-account
iobox --account work search -q "from:client@company.com"
```
