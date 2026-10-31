# Configuration

## Environment variables

iobox loads a `.env` file from the working directory if present.

| Variable | Default | Used by | Purpose |
|---|---|---|---|
| `IOBOX_MODE` | `standard` | CLI, MCP | Access mode: `readonly`, `standard`, `dangerous` |
| `IOBOX_ACCOUNT` | `default` | CLI email commands, MCP fallback | Mailbox / token directory name |
| `IOBOX_PROVIDER` | `gmail` | CLI email commands | `gmail` or `outlook` |
| `CREDENTIALS_DIR` | current directory | CLI email commands, MCP fallback | Where `credentials.json` and `tokens/` live for single-account mode |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | All | Path to the Google OAuth client file |
| `GMAIL_TOKEN_FILE` | `token.json` | CLI email commands | Override the token path (disables per-account tokens) |
| `OUTLOOK_CLIENT_ID` | — | All (Microsoft 365) | Entra app client ID |
| `OUTLOOK_TENANT_ID` | `common` | All (Microsoft 365) | Entra tenant ID |
| `IOBOX_MCP_ROOT` | `~/iobox` | MCP server | Only directory MCP tools may read from or write to |
| `ANTHROPIC_API_KEY` | — | `processing.summarize` | Claude API key for summaries |
| `OPENAI_API_KEY` / `VOYAGE_API_KEY` | — | `processing.embed` | Embedding backend keys |

Workspace configuration (`iobox space`, `events`, `files`, the MCP workspace tools, and `Workspace.from_config`) always uses `~/.iobox`.

## Files on disk

```
~/.iobox/
  active_space                 # name of the active workspace
  credentials.json             # Google OAuth client
  workspaces/
    NAME.toml                  # one per workspace
  tokens/
    ACCOUNT/
      token_readonly.json      # Google, read-only scopes
      token_standard.json      # Google, read-write scopes
      microsoft_token.txt      # Microsoft 365
  indexes/                     # semantic search indexes
```

## Workspace TOML

```toml
[workspace]
name = "personal"

[[services]]
number = 1
id = "google-yougmailcom"
slug = "you-gmail"
service = "google"              # google | o365
account = "you@gmail.com"
scopes = ["email", "calendar", "drive"]
mode = "readonly"               # readonly | standard

[[services]]
number = 2
id = "o365-corpcompanycom"
slug = "corp-company"
service = "o365"
account = "corp@company.com"
scopes = ["email", "calendar"]
mode = "standard"
```

Prefer `iobox space add` over editing this file by hand, since adding a service also runs OAuth. `slug` determines the [slot names](../get-started/concepts.md#slot).
