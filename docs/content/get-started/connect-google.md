# Connect Google

iobox talks to Gmail, Google Calendar, and Google Drive through Google's official APIs using OAuth 2.0. You create your own OAuth client once; your data never passes through any third-party server.

## 1. Create an OAuth client

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create (or select) a project.
2. Under **APIs & Services → Library**, enable the APIs you'll use:
    - **Gmail API**
    - **Google Calendar API**
    - **Google Drive API**
3. Under **APIs & Services → OAuth consent screen**, configure the app:
    - **Personal Gmail:** choose *External*, then set **Publishing status** to **In production**. In *Testing* mode, refresh tokens expire after 7 days and you'll be re-authenticating weekly.
    - **Google Workspace (one domain):** choose *Internal* — no verification needed.
4. Under **APIs & Services → Credentials**, click **Create credentials → OAuth client ID** and choose **Desktop app**.
5. Download the JSON file and save it as `~/.iobox/credentials.json`.

```bash
mkdir -p ~/.iobox
mv ~/Downloads/client_secret_*.json ~/.iobox/credentials.json
```

Set `GOOGLE_APPLICATION_CREDENTIALS` to use a different path.

!!! note "\"Google hasn't verified this app\""
    Because the Gmail scopes are sensitive, Google shows an unverified-app warning for personal OAuth clients. It's your own app — click **Advanced → Go to *project name*** to continue.

## 2. Add the account to a workspace

```bash
iobox space create personal
iobox space add google you@gmail.com --email --calendar --drive --read
```

Your browser opens for consent. After you approve, iobox checks that the account you signed in with matches the email you passed — a mismatch is rejected and the token discarded.

Choose scopes and mode up front:

| Flag | Enables | Read-only scope | Read-write scope |
|---|---|---|---|
| `--email` | Gmail | `gmail.readonly` | `gmail.modify`, `gmail.compose` |
| `--calendar` | Google Calendar | `calendar.readonly` | `calendar` |
| `--drive` | Google Drive | `drive.readonly` | `drive` |
| `--read` | Read-only scopes for all of the above | | |

!!! warning "Scopes are fixed per token"
    Google issues a token for a fixed set of scopes, and an existing token is reused as-is. To add a scope later, delete the token and the session, then add it again with the full set of flags:

    ```bash
    iobox space logout 1
    iobox space remove 1
    iobox space add google you@gmail.com --email --calendar --drive --read
    ```

## 3. Check it worked

```bash
iobox space status
```

```
#  service  account        scopes                 mode      status
1  google   you@gmail.com  email,calendar,drive   readonly  ✓ authenticated
```

Add more accounts the same way — each gets its own token under `~/.iobox/tokens/ACCOUNT/`.

## Token management

| Command | Effect |
|---|---|
| `iobox space login N` | Re-run OAuth for session `N` (by number or slug) |
| `iobox space logout N` | Revoke and delete the token, keep the config |
| `iobox space remove N` | Remove the session from the workspace |

Read-only and read-write tokens are stored separately (`token_readonly.json`, `token_standard.json`), so switching modes never destroys an existing token. A broader token is accepted in read-only mode.

## Alternatives not supported

- **Service accounts / domain-wide delegation** — Workspace-only and requires a super-admin; not currently supported.
- **IMAP with app passwords** — legacy and being phased out by Google; iobox uses the APIs only.

## Next

[Quick Start](quickstart.md) · [Connect Microsoft 365](connect-microsoft.md)
