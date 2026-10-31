# Connect Microsoft 365

iobox connects to Outlook mail, Outlook Calendar, and OneDrive through Microsoft Graph, using the [`O365`](https://github.com/O365/python-o365) library.

!!! warning "Experimental"
    The Microsoft 365 providers are implemented and unit-tested but have not yet been tested end-to-end against a real tenant. Please [report issues](https://github.com/timainge/iobox/issues).

## 1. Install the extra

```bash
pip install 'iobox[outlook]'
```

## 2. Register an app in Entra ID

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com/) → **App registrations → New registration**.
2. **Supported account types:** pick the option that matches your accounts (single tenant for one organisation; *any organisational directory and personal Microsoft accounts* for the broadest reach).
3. **Redirect URI:** platform *Public client/native*, value `https://login.microsoftonline.com/common/oauth2/nativeclient`.
4. Under **API permissions → Add a permission → Microsoft Graph → Delegated permissions**, add what you need:

    | Scope | Read-only | Read-write |
    |---|---|---|
    | Mail | `Mail.Read` | `Mail.ReadWrite`, `Mail.Send` |
    | Calendar | `Calendars.Read` | `Calendars.ReadWrite` |
    | OneDrive | `Files.Read.All` | `Files.ReadWrite.All` |

5. Copy the **Application (client) ID** and, for a single-tenant app, the **Directory (tenant) ID**.

## 3. Configure environment

```bash
export OUTLOOK_CLIENT_ID=<application client ID>
export OUTLOOK_TENANT_ID=<tenant ID>    # or "common" (default)
```

Put these in a `.env` file or your shell profile so the CLI and MCP server both see them. For the MCP server, add them to the server's `env` block — see [MCP configuration](../mcp/configuration.md).

## 4. Add the account to a workspace

```bash
iobox space add o365 you@company.com --email --calendar --read
iobox space status
```

A browser sign-in opens. The token is stored at `~/.iobox/tokens/you@company.com/microsoft_token.txt`.

!!! note
    `--drive` is not yet accepted for `o365` sessions in `space add`, even though the `OneDriveProvider` exists and can be used from the [SDK](../sdk/providers.md).

## Differences from Google

- **Outlook searches the Inbox only.** Gmail searches all mail. Messages in Sent, Archive, or custom folders may not be returned.
- **Message IDs are ImmutableIds**, so they stay stable when a message is moved between folders.
- **OneDrive deletion is permanent** — there's no trash API via `O365`.

See [Provider behaviour](../reference/providers.md) for the full list.

## Next

[Quick Start](quickstart.md)
