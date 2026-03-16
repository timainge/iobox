# Outlook / Microsoft 365 Provider

The `OutlookProvider` and `OutlookCalendarProvider` connect iobox to Microsoft 365 via the `python-o365` library (Microsoft Graph API).

## Prerequisites

- `pip install 'iobox[outlook]'`
- An Azure app registration with appropriate Microsoft Graph permissions
- `OUTLOOK_CLIENT_ID` environment variable set

## Azure App Registration

1. Go to the [Azure Portal](https://portal.azure.com/) > **Azure Active Directory > App registrations**
2. Click **New registration**
3. Set redirect URI to `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Under **API permissions**, add delegated permissions:
   - `Mail.Read` / `Mail.ReadWrite` (for messages)
   - `Calendars.Read` / `Calendars.ReadWrite` (for calendar)
   - `Files.Read.All` (for OneDrive)
5. Copy the **Application (client) ID**

## Setup

```bash
pip install 'iobox[outlook]'

export OUTLOOK_CLIENT_ID=<your client ID>
export OUTLOOK_TENANT_ID=common    # or your specific tenant ID

# Add to workspace
iobox space add outlook you@company.com --messages --calendar --read
```

This triggers a device-code or browser OAuth flow.

## Token Storage

Tokens are stored at `~/.iobox/tokens/ACCOUNT/microsoft_token.txt`.

## Access Modes

| Mode | Mail scopes | Calendar scopes |
|---|---|---|
| `readonly` | `Mail.Read` | `Calendars.Read` |
| `standard` | `Mail.ReadWrite`, `Mail.Send` | `Calendars.ReadWrite` |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OUTLOOK_CLIENT_ID` | — | Required: Azure app client ID |
| `OUTLOOK_TENANT_ID` | `common` | Azure tenant ID (`common` for multi-tenant) |

## CLI Commands

Outlook works transparently through the same CLI commands as Gmail when configured as a workspace service session:

```bash
# Email
iobox search -q "from:boss@company.com" --provider my-outlook

# Calendar
iobox events list --after 2026-01-01 --provider my-outlook

# Status
iobox space status
```

## Limitations

- Outlook searches the **inbox folder** by default; Gmail searches all mail
- Outlook message IDs use ImmutableId format for stability across folder moves
- OneDrive deletion is always permanent (no trash API via python-o365)
- Incremental event sync not implemented for MVP
