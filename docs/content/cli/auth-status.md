# auth-status

Show authentication status for the single-account email provider used by the top-level email commands.

!!! warning "Deprecated"
    `auth-status` prints a deprecation notice. For workspace sessions use [`iobox space status`](space.md#status).

!!! note "Single account, not the workspace"
    `auth-status` does not look at your workspace or `iobox space` sessions. It reports on the one mailbox chosen by the global options `--provider gmail|outlook` and `--account NAME` (or `IOBOX_PROVIDER` / `IOBOX_ACCOUNT`), which go **before** the command name. Gmail tokens are read from `$CREDENTIALS_DIR/tokens/NAME/token_{readonly|standard}.json`; `CREDENTIALS_DIR` defaults to the current directory. See [CLI overview](index.md) for global options.

**Access mode:** available in all modes (`readonly`, `standard`, `dangerous`).

## Syntax

```
iobox [--provider gmail|outlook] [--account NAME] [--mode MODE] auth-status
```

No command options.

## Description

Always prints the provider, access mode, and account name. Then:

**Gmail** (default):

- Whether a valid token exists (`Authenticated`)
- The OAuth client file (`credentials.json`, or `GOOGLE_APPLICATION_CREDENTIALS`) and whether it exists
- The token file for the current mode's tier and whether it exists; expiry and refresh-token status if it does
- Gmail profile (email address, message and thread counts) when the token is valid, or expired but refreshable, and grants the scopes the current mode needs
- Google Cloud setup steps if the credentials file is missing

The readonly mode reads `token_readonly.json` but also accepts an existing `token_standard.json`.

**Outlook** (`--provider outlook`):

- Whether a valid token exists, whether `OUTLOOK_CLIENT_ID` is set, the tenant ID, and the token file path
- Azure app setup steps if `OUTLOOK_CLIENT_ID` is not set
- Profile email and display name when authenticated

`auth-status` never opens a browser or starts an OAuth flow. If there's no usable token it prints `Not signed in` and how to sign in; if the token lacks scopes for the current mode it lists the missing scopes. Errors fetching the profile are printed (to stderr) rather than hidden.

## Example Output

```
Note: `auth-status` is deprecated. Use `iobox space status` instead.


Authentication Status
-------------------
Provider: gmail
Access mode: standard
Account: default
Authenticated: True
Credentials file exists: True
Credentials path: /home/user/iobox/credentials.json
Token file exists: True
Token path: /home/user/iobox/tokens/default/token_standard.json
Token expired: False
Has refresh token: True

Gmail Profile
-------------------
Email: you@example.com
Emails: 12,345
Threads: 9,876
```

## Troubleshooting

If the token has expired or access was revoked, delete the token file shown under `Token path` and run any email command; the OAuth flow starts again.

## Related

- [`space`](space.md) — workspace sessions and their auth status
- [Connect Google](../get-started/connect-google.md)
- [Connect Microsoft](../get-started/connect-microsoft.md)
- [Configuration](../reference/configuration.md) — `CREDENTIALS_DIR` and other environment variables
