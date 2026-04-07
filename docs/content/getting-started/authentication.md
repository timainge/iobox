# Gmail API Authentication for Iobox: Google Workspace vs. Personal Accounts

## Current OAuth 2.0 Implementation in Iobox

Iobox is designed to use **Google's OAuth 2.0 flow for Gmail API
access**. The repository's authentication module uses the Google API
Python client and OAuth libraries to obtain credentials for the Gmail
API. In practice, this means you must create a Google Cloud project, enable
the Gmail API, and download an OAuth client credentials file (for a
*Desktop App* OAuth client) as `credentials.json`. On first run, Iobox
launches an **OAuth consent flow** (opening a browser or local server) to
let the user grant Gmail access. The resulting access & refresh tokens are
stored in `token.json` for reuse.

Key points:

- **OAuth Consent:** Iobox requests `gmail.modify` and `gmail.compose` scopes,
  prompting the Google account owner to consent. The code uses
  `InstalledAppFlow.run_local_server()` for a user-friendly local authentication flow.
- **Token Storage:** After authorization, Iobox saves credentials (including a
  refresh token) to `token.json` so subsequent runs can refresh the access token
  without prompting for login again. This **"offline access"** capability is critical
  for automation.

## Using Iobox with Personal Gmail Accounts

Yes — you can use the **same OAuth 2.0 authorization mechanism** with a personal
Gmail account. Google's Gmail API does not distinguish between Google Workspace
(G Suite) and consumer Gmail for authentication; any Google account can grant OAuth
access to its mailbox.

However, there are a few **practical differences** to be aware of:

- **OAuth Consent Screen and Publishing Status:** If you are testing Iobox with a
  personal Gmail, your Google Cloud OAuth consent screen will likely be in "external
  testing" mode (unverified and not published). In this mode, **refresh tokens expire
  after 7 days** — meaning you would have to re-authorize weekly. To avoid this, set
  your OAuth consent screen **Publishing Status to "Production"**. Once in production
  mode, the refresh token will last indefinitely (until revoked).

- **Consent Screen Warnings:** Because Iobox requests Gmail access (a sensitive scope),
  personal users will see a warning that the app is unverified unless you go through
  Google's verification. You can manually proceed by clicking "Advanced" → "Go to
  [Project Name]" on the consent screen. For personal use, this is fine.

- **No Domain Admin Needed:** Unlike some Google Workspace environments, personal Google
  accounts don't have an admin restricting API client access. There's no extra admin
  approval step beyond the standard OAuth consent.

## Alternative Authentication Mechanisms

- **Service Accounts (Domain-Wide Delegation):** Only available for Google Workspace
  domains with super-admin rights. Allows accessing multiple user mailboxes without
  individual user consent. Not applicable for personal Gmail accounts.

- **IMAP/POP with App Password:** Gmail still supports IMAP/POP3 with app passwords,
  but as of March 14, 2025, Google is disabling basic auth. This approach is a
  legacy workaround and is not recommended.

## Recommendations

- **Stick with OAuth 2.0** — it is the method supported by Google for both personal and
  work Gmail accounts and is aligned with long-term best practices.
- For personal use, switch the OAuth consent screen to "Production" to avoid 7-day token
  expiration.
- Ensure Iobox requests only the minimal scopes needed.
- Run `iobox auth-status` to verify your authentication state and diagnose issues.
- If the token refresh fails (revoked access or changed password), delete `token.json`
  and re-run the OAuth flow.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CREDENTIALS_DIR` | current directory | Directory containing credential files |
| `GOOGLE_APPLICATION_CREDENTIALS` | `credentials.json` | Path to OAuth credentials file |
| `GMAIL_TOKEN_FILE` | `token.json` | Path to stored token file |

These can be set in a `.env` file in your working directory.

## Enterprise (Workspace) Considerations

- Set the OAuth consent screen to **"Internal"** if all users are in one domain — no
  Google verification required.
- A domain admin can whitelist the app's OAuth client ID for Gmail API scopes to remove
  any admin consent roadblocks.
- For a centralized solution, consider a service account with domain-wide delegation
  (requires admin setup, but eliminates per-user OAuth flows).
