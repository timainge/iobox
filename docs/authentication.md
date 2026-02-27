# Gmail API Authentication for Iobox: Google Workspace vs. Personal Accounts

## Current OAuth 2.0 Implementation in Iobox

Iobox is designed to use **Google's OAuth 2.0 flow for Gmail API
access**. The repository's authentication module uses the Google API
Python client and OAuth libraries to obtain credentials for the Gmail
API[\[1\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L50-L59)[\[2\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L69-L77).
In practice, this means you must create a Google Cloud project, enable
the Gmail API, and download an OAuth client credentials file (for a
*Desktop App* OAuth client) as
`credentials.json`[\[3\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/README.md#L52-L59).
On first run, Iobox launches an **OAuth consent flow** (opening a
browser or local server) to let the user grant Gmail read access. The
resulting access & refresh tokens are stored in `token.json` for
reuse[\[1\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L50-L59).
This implementation was tested with a Google Workspace (work) account,
which required the same OAuth process (with some domain admin
configuration, discussed below). The key points of the current approach
are:

- **OAuth Consent:** Iobox requests the Gmail API *readonly* scope,
  prompting the Google account owner to consent to read their
  email[\[4\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L61-L69).
  The code uses `InstalledAppFlow.run_local_server()` for a
  user-friendly local authentication
  flow[\[2\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L69-L77).
- **Token Storage:** After the user authorizes, Iobox saves the
  credentials (including a refresh token) to `token.json` so that
  subsequent runs can refresh the access token without asking the user
  to log in
  again[\[1\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L50-L59).
  The code will automatically refresh an expired token if a refresh
  token is available, or start a new OAuth flow if needed. This
  **"offline access"** capability is crucial for automation, as it
  avoids requiring interactive login each time.

In summary, **Iobox's current auth mechanism is the standard Google
OAuth 2.0 for installed applications**, which is applicable to any Gmail
account. This mechanism is not limited to Google Workspace accounts --
it works for personal Gmail accounts as well, since the Gmail API and
OAuth scopes are the same for personal and work accounts.

## Using Iobox with Personal Gmail Accounts

Yes -- you can use the **same OAuth 2.0 authorization mechanism** with a
personal Gmail account. Google's Gmail API does not distinguish between
Google Workspace (G Suite) and consumer Gmail for authentication; any
Google account can grant OAuth access to its mailbox. The setup steps
(creating a Google Cloud project, enabling the Gmail API, and obtaining
OAuth credentials) apply equally to personal Gmail
users[\[3\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/README.md#L52-L59).

However, there are a few **practical differences** to be aware of when
using a personal Gmail account versus a Workspace account:

- **OAuth Consent Screen and Publishing Status:** If you are testing
  Iobox with a personal Gmail, your Google Cloud OAuth consent screen
  will likely be in "external testing" mode (unverified and not
  published). In this mode, **refresh tokens expire after 7
  days**[\[5\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=This%20should%20be%20resulting%20in,an%20invalid_token%20error)
  -- meaning you would have to re-authorize weekly, which is not ideal
  for automation. To avoid this, you should set your OAuth consent
  screen **Publishing Status to "Production"** (even if you don't fully
  verify the app). Once the app is in production mode (and you've
  granted consent), the refresh token will last indefinitely (until
  revoked by the user) rather than being invalidated
  weekly[\[5\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=This%20should%20be%20resulting%20in,an%20invalid_token%20error).
  Keep in mind that if the app is unverified, Google will show an
  \"unverified app\" warning during consent, and it limits you to 100
  user grants maximum in this
  state[\[6\]](https://support.google.com/cloud/answer/7454865?hl=en#:~:text=the%20deadline,new%20users%20until%20it%20is%C2%A0verified)
  -- which is usually fine for personal use or small-scale testing.

- **Consent Screen Warnings:** Because Iobox requests Gmail access (a
  sensitive scope), personal users will see a warning that the app is
  unverified unless you go through Google's verification. This is normal
  for a personal project. You can manually proceed by clicking
  "Advanced" -\> "Go to \[Project Name\]" on the consent screen. For
  personal use, this warning and the 100-user cap are not a problem, but
  they would need addressing if you plan to distribute Iobox widely.

- **No Domain Admin Needed:** Unlike some Google Workspace environments,
  personal Google accounts don't have an admin restricting API client
  access. In a corporate Google Workspace, an administrator might need
  to **trust or whitelist the OAuth client ID** before users can consent
  to certain scopes. With a personal Gmail account, you are effectively
  the admin of your own account -- so there's no extra admin approval
  step beyond the standard OAuth consent. The same client credentials
  and OAuth flow will work out-of-the-box for your personal account.

In short, **the OAuth-based approach used by Iobox is fully compatible
with personal Gmail accounts**. You just need to ensure you configure
the Google Cloud credentials and consent screen appropriately for
non-Workspace use (e.g. use an external user type, and switch to
"production" to avoid 7-day token
expiration)[\[5\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=This%20should%20be%20resulting%20in,an%20invalid_token%20error).
After initial consent and token save, a personal Gmail user can run
Iobox repeatedly without reauthenticating, as long as the refresh token
remains valid.

## Alternative Authentication Mechanisms for Gmail

While Google's recommended method for integrating with Gmail is OAuth
2.0, there are a few other mechanisms (each with caveats) that you could
consider:

- **Google Workspace Service Accounts (Domain-Wide Delegation):** In
  Google Workspace domains, an administrator can use a service account
  with domain-wide delegation to access user mailboxes without
  individual user consent. This involves creating a service account in
  Google Cloud, granting it domain-wide authority for Gmail scopes, and
  impersonating user accounts. This method is **only available for
  Google Workspace (Work) accounts** where you have super-admin rights
  -- it **cannot be used for regular personal Gmail
  accounts**[\[7\]](https://www.reddit.com/r/googlecloud/comments/1bmppdf/can_service_accounts_be_used_by_regular_gmail/#:~:text=b,OAuth).
  If Iobox were to be used within a company for multiple users, a
  service account approach could allow the tool to run in the background
  accessing mailboxes (with admin-granted permission) rather than each
  user completing an OAuth flow. The current Iobox implementation does
  **not** use service accounts, but this is an alternative for
  enterprise scenarios. Keep in mind that using domain-wide delegation
  requires careful security controls (the service account has broad
  access) and setup in the Google Workspace Admin Console.

- **IMAP/POP with App Password:** Gmail still supports IMAP and POP3
  protocols for accessing emails, which can be used with an app password
  (for accounts with 2-Step Verification enabled) or OAuth. An **app
  password** is a 16-digit passcode Google allows you to generate as an
  alternative to your account password for less secure clients. Some
  tools and developers use Gmail's IMAP interface with an app password
  to fetch
  emails[\[8\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=I%20know%20some%20developers%20still,should%20trust%20your%20app).
  This bypasses the need for OAuth interactive consent and token refresh
  logic -- the script would simply log in to `imap.gmail.com` with the
  email and app password and retrieve messages. However, there are
  important drawbacks to this approach today:

- Google considers password-based access a *"less secure app"* method.
  In fact, as of **March 14, 2025 Google is disabling basic auth for all
  Google accounts** (no more login via username/password for IMAP, POP,
  SMTP)[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).
  The only exception will be app passwords, which are still allowed for
  certain cases, but even those are being strongly deprecated in favor
  of
  OAuth[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).

- Using IMAP means you'd have to manually handle email parsing and
  adhere to IMAP's quirks. The Gmail API, by contrast, gives structured
  message data (including metadata and MIME parts) and powerful query
  capabilities with Gmail's search syntax.

- App password access grants **full mailbox access** with no granular
  scope control. It's all-or-nothing and doesn't log an explicit
  third-party app consent. For personal hacks this might be acceptable,
  but from a security standpoint it's less transparent what access is
  being used.

In summary, while it's technically possible to modify Iobox to use
IMAP+app-password for Gmail (thus avoiding OAuth), this is a **hacky
workaround**. It may work for personal use (especially if you want a
quick setup without creating a Google Cloud project), but it goes
against Google's security best practices and might stop working in the
future as Google tightens app
security[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).

- **OAuth Client Whitelisting (Workspace only):** In a Google Workspace
  environment, a domain admin can **whitelist an OAuth client ID** for
  specific
  scopes[\[8\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=I%20know%20some%20developers%20still,should%20trust%20your%20app).
  This means the admin pre-approves the app, so users in that domain can
  grant consent without the app being verified by Google. It doesn't
  change the OAuth flow for users, but it removes any admin consent
  roadblocks. If Iobox's client ID is whitelisted in a Workspace, users
  wouldn't see any additional warnings from admin policies (though
  they'd still see the standard consent screen for the scopes). This is
  not an alternate auth method per se (it's still OAuth), but rather a
  way to streamline OAuth in an enterprise setting. It's relevant if
  deploying Iobox within a company -- the IT admin could add the OAuth
  client to the "Trusted" list for Gmail API scopes, making usage
  smoother.

- **Delegated Account Access:** This is more of a Gmail feature than an
  auth mechanism for apps -- Gmail allows users to delegate mailbox
  access to another Google account (often used for an assistant to
  manage an executive's email). In theory, one could delegate a Gmail
  account to a service account or another account and then access it,
  but this is complex and not a standard integration approach. It's
  generally easier to use the API directly or service accounts with
  delegation as described above.

To summarize, **the officially supported and future-proof method is
OAuth 2.0** (the route Iobox currently takes). Other methods like IMAP
with app passwords are legacy or niche solutions -- they might be useful
in specific cases (e.g. personal quick use, or if you absolutely need to
avoid the OAuth flow), but they either aren't allowed for wider use or
are on their way
out[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).
Service accounts with domain delegation are powerful for enterprise
automation, but only applicable in a Workspace context with admin
control.

## Recommendations for Iobox's Authentication Approach

Considering Google's policies and the goal of making Iobox both
**personally useful and potentially release-ready**, here are some
recommendations:

- **Stick with OAuth 2.0 as the Primary Method:** Google is pushing all
  integrations toward OAuth -- indeed, as of 2025, third-party apps
  *must* use OAuth to access
  Gmail/Calendar/Contacts[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).
  The current design of Iobox using OAuth 2.0 and the Gmail API is
  aligned with these best practices. It provides fine-grained scope
  control (Iobox only requests read-only Gmail access) and uses Google's
  secure token system. This is the right foundation for a tool intended
  to be reliable long-term. Make sure you request only the minimal
  scopes needed (currently Gmail read-only, which is good) and continue
  to handle token storage/encryption carefully.

- **Improve the OAuth User Experience for Release:** For a personal/hack
  usage, it's fine to require the user to create a Google Cloud project
  and supply credentials (as done now). For a more *releasable* project,
  consider streamlining this:

- **Documentation & Setup Scripts:** Provide clear documentation (or
  even a setup script) to guide non-technical users through obtaining
  their credentials JSON. The README already outlines the
  steps[\[10\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/test_auth.py#L34-L46);
  you might expand this with screenshots or a script to automate
  creating the Cloud project via Google's APIs if possible.

- **Device Code Flow Option:** If you expect some users to run Iobox on
  a remote server or headless environment, you could offer an
  alternative OAuth method (Google's Device Authorization Flow). This
  flow lets a CLI app obtain a code that the user can visit on a
  separate device to authorize. The Google OAuth client library supports
  this as well. It's a minor enhancement to accommodate more use cases.

- **Token Longevity:** Ensure that Iobox requests "offline" access so
  that a refresh token is issued. The current use of
  `InstalledAppFlow.run_local_server()` typically does default to
  offline access (i.e., includes `access_type=offline`). Double-check
  this in testing: if a refresh token is present in `token.json`, then
  it's working. This is critical for automation because it allows
  long-term access without user intervention. As discussed, instruct
  users to mark the app as "In Production" on their OAuth consent screen
  to avoid the 7-day expiration
  issue[\[5\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=This%20should%20be%20resulting%20in,an%20invalid_token%20error).

- **Error Handling & Re-Auth:** Implement clear messaging if the token
  refresh fails (e.g., if the user revoked access or changed their
  Google password, the refresh token can become
  invalid[\[11\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=Image%3A%20enter%20image%20description%20here)).
  In such cases, Iobox should prompt the user to re-authenticate (delete
  `token.json` and run the flow again). Having a command like
  `iobox auth-status` (which I see exists) is
  great[\[12\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L84-L93)
  -- it can be expanded to guide the user on how to fix auth issues.

- **Consider an IMAP/App Password Fallback (with Warnings):** Since you
  mentioned "can be hacky" and are initially targeting personal use, you
  might implement an *optional* fallback mode to fetch emails via IMAP
  with an app password. This could be a mode where advanced users put
  their email and an app password in the `.env` file and bypass the
  Gmail API. If you do this, **document the risks** and limitations:

- Note that Google may disable even app password access for new apps in
  the future. Already, Google prevents new connections with basic auth
  unless app passwords are used, and they encourage OAuth for all modern
  clients[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts).

- This method should be off by default -- only use if the user
  explicitly configures it (for example, if they absolutely cannot or
  will not do the OAuth setup).

- Using IMAP would limit some functionality (for instance, Gmail's
  advanced search queries might not all work through IMAP, and you'd
  have to manually convert messages to markdown). If the current
  implementation relies on the Gmail API for search queries
  (`iobox search -q "..."` uses Gmail's query syntax), replicating that
  via IMAP would require re-implementing search or filtering
  client-side. It's doable (Gmail's IMAP supports searching by some
  criteria, but not the full Gmail query language). This is a trade-off:
  the Gmail API is more powerful and efficient for queries. So, treat
  IMAP as a last-resort alternative rather than the recommended path.

- **Plan for Verification if Releasing Broadly:** If you intend to
  release Iobox to a broad audience (beyond personal/internal use), you
  should be aware of Google's **OAuth app verification** requirements.
  Gmail API scopes are classified as **sensitive or even restricted**
  user data. Google requires any public app requesting these scopes to
  go through a review. Specifically, reading Gmail messages falls under
  data that likely triggers a **restricted scope** category, which
  means:

- At minimum, you'll need to submit the app for verification,
  demonstrating compliance with Google's API data policies (with a
  privacy policy,
  etc.)[\[13\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=,5%20business%20days%20to%20complete).

- For restricted scopes (like full access to Gmail), Google additionally
  mandates an independent **security assessment** of the app if it's
  distributed publicly, which is
  costly[\[14\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=restricted).
  This is generally required for apps that store or process Gmail data
  on a server. In Iobox's case (a local tool storing data locally), you
  might qualify for some exceptions, but it's something to investigate
  if you go down the official verification route.

If this sounds onerous, an alternative strategy for an open-source
project is to **avoid handling user data on behalf of others**
altogether. In practice, that means each user would run their own
instance of Iobox with their own Google API credentials (as you
currently have it set up). This way, Iobox can remain an unverified app
used by individuals, and each user effectively "verifies" their own
usage by acknowledging the unverified warning. Google's policies **do
not require verification for apps in development or used only by the
developer/testers**[\[15\]](https://support.google.com/cloud/answer/7454865?hl=en#:~:text=You%20don%27t%20need%20to%20go,the%20following%20kinds%20of%20apps).
Many open-source Gmail tools take this approach (for example, some
backup utilities tell users to create their own client ID). It's less
convenient for end-users but sidesteps the need for a central app
verification and security audit.

If you do want to make Iobox more user-friendly and maybe even provide a
one-click binary with a built-in client ID, be cautious: embedding your
own client credentials means all users of the app share the same OAuth
client. This could hit the 100-user limit quickly if
unverified[\[6\]](https://support.google.com/cloud/answer/7454865?hl=en#:~:text=the%20deadline,new%20users%20until%20it%20is%C2%A0verified).
To go beyond that, you'd need to complete verification. As a
**recommendation**, until you're ready for that process, it's safest to
**continue having users supply their own credentials** for any
significant use. That keeps things in the "internal/test" domain per
user, and **no one hits global user limits or compliance issues**.

- **Enterprise (Workspace) Considerations:** For usage in a Google
  Workspace context (say a company wants to use Iobox), leverage
  Workspace features:

- If all users are in one domain, the Google Cloud OAuth consent screen
  can be set to **"Internal"** (only available to users in your domain).
  In this mode, the app doesn't need Google verification at
  all[\[16\]](https://support.google.com/cloud/answer/7454865?hl=en#:~:text=,see%20public%20and%20internal%20applications)
  (Google trusts the domain admin to vet the app). This requires that
  the Cloud project is owned by an organization linked to the Google
  Workspace. If you're developing Iobox within a company, this is ideal
  -- no unverified app warnings, and no 100-user limit, as long as only
  domain accounts use it.

- As mentioned, a domain admin can also **whitelist the app's client
  ID** for the Gmail API
  scopes[\[8\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=I%20know%20some%20developers%20still,should%20trust%20your%20app).
  This doesn't remove the consent screen, but it ensures users won't be
  blocked by admin security settings. It's a good practice in enterprise
  deployments to coordinate with IT.

- For a truly centralized solution, consider building a service mode
  where a service account (with domain-wide delegation) archives mail
  from multiple accounts. That goes beyond Iobox's initial scope (which
  is one user's mailbox to markdown), but it could be a powerful
  extension for organizational use. In that case, you'd store the
  service account credentials and have a config of which mailboxes to
  ingest. This would eliminate per-user OAuth flows entirely in a
  controlled environment. The downside is complexity and the need for
  admin-level setup. If your goal is *personal automation*, this is
  likely overkill; if your goal is an enterprise archival tool, this
  could be a future path.

- **Security and Privacy:** No matter which auth mechanism is used,
  emphasize to users that their email data is sensitive. If you release
  this tool, follow Google's API User Data Policy. For instance, **least
  privilege**: if in the future you add email-sending or modifying
  capabilities, consider keeping read-only and write scopes separate so
  users can choose. Also, **protect the credentials** -- the
  `credentials.json` (client secret) and the `token.json` (user tokens)
  should be kept safe. Encourage use of OS keyrings or encryption if
  distributing to less technical users. This isn't directly about auth
  mechanism, but it's part of providing a "releasable" tool that handles
  user data responsibly.

In conclusion, **my recommendation is to continue using the OAuth 2.0
flow as implemented, as it is the method supported by Google for both
personal and work Gmail accounts**. The same mechanism does work for
personal Gmail -- just mind the differences in token expiration and app
verification for personal use. You can supplement this with a *one-time
manual setup* (which you already have) and possibly offer advanced users
an IMAP/app-password fallback if they really need a quick hack. But for
a sustainable, release-quality project, focus on making the OAuth setup
as smooth as possible and plan for Google's verification requirements if
targeting a broader user base. This ensures Iobox remains functional in
the long run and in compliance with Google's policies, while meeting the
goal of **local programmatic email access with minimal ongoing effort**
(just an initial config, then automated operation thereafter).

**Sources:**

- Iobox README -- Gmail API OAuth setup and
  usage[\[3\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/README.md#L52-L59)[\[1\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L50-L59)
- Iobox Auth Implementation -- uses OAuth 2.0 Installed App flow with
  token
  storage[\[17\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L61-L70)[\[18\]](https://github.com/timainge/iobox/blob/b600f4bdc8e14faa7523bc91815240dd584035cd/src/iobox/auth.py#L71-L77)
- Google OAuth Token Policy -- Unverified apps in testing have 7-day
  token
  lifespans[\[5\]](https://stackoverflow.com/questions/69693237/request-had-insufficient-authentication-scopes-gmail-api-offline-not-working-r#:~:text=This%20should%20be%20resulting%20in,an%20invalid_token%20error)
- Google Support -- Basic auth deprecation (requiring OAuth for Gmail
  access)[\[9\]](https://support.google.com/a/answer/14114704?hl=en#:~:text=Starting%20March%2014%2C%202025%2C%20you,more%20vulnerable%20to%20hijacking%20attempts)
- Stack Overflow -- Alternatives (IMAP & app passwords, Workspace admin
  options)[\[8\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=I%20know%20some%20developers%20still,should%20trust%20your%20app)
- Google Cloud Docs -- Verification exemptions for internal
  (domain-only)
  apps[\[16\]](https://support.google.com/cloud/answer/7454865?hl=en#:~:text=,see%20public%20and%20internal%20applications)
- Google OAuth Verification -- Requirements for sensitive/restricted
  scopes[\[13\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=,5%20business%20days%20to%20complete)[\[14\]](https://stackoverflow.com/questions/72935714/how-to-avoid-security-assessment-for-gmail-api-integration#:~:text=restricted)

