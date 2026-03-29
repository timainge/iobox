# auth-status

Check the status of Gmail API authentication and display the Gmail profile for the authenticated account.

## Syntax

```
iobox auth-status
```

## Description

This command checks whether valid credentials exist and displays:

- Whether authentication is active
- Whether the `credentials.json` file exists and its path
- Whether the `token.json` file exists and its path
- Token expiry and refresh token status (if token file exists)
- Gmail profile: email address, total messages, and total threads

If no credentials file is found, step-by-step setup instructions are printed.

## Example Output

Authenticated:

```
Authentication Status
-------------------
Authenticated: True
Credentials file exists: True
Credentials path: /home/user/credentials.json
Token file exists: True
Token path: /home/user/token.json
Token expired: False
Has refresh token: True

Gmail Profile
-------------------
Email: you@example.com
Messages: 12,345
Threads: 9,876
```

Not authenticated (missing credentials):

```
Authentication Status
-------------------
Authenticated: False
Credentials file exists: False
Credentials path: /home/user/credentials.json
Token file exists: False
Token path: /home/user/token.json

To set up Google Cloud OAuth 2.0 credentials:
1. Go to https://console.cloud.google.com/
2. Create a project or select an existing one
3. Navigate to APIs & Services > Credentials
4. Click 'Create Credentials' > 'OAuth client ID'
5. Choose 'Desktop app' as application type
6. Download the JSON file and save it as 'credentials.json' in the project root
```

## Troubleshooting

If the token has expired or access was revoked:

1. Delete `token.json`
2. Run any iobox command — a new OAuth flow will be triggered automatically

## Related

- [Authentication](../getting-started/authentication.md) — full OAuth documentation
- [Installation](../getting-started/installation.md) — credential setup instructions
