# Line of Enquiry 3: MSAL/Azure authentication vs Gmail OAuth

## JSON Findings

```json
{
  "sub_question": "How does MSAL authentication for Microsoft Graph compare to Gmail OAuth via google-auth-oauthlib?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    "App registration for Microsoft Graph is done via the Microsoft Entra admin center (Identity > Applications > App registrations), yielding a client_id (Application ID) and optionally a client secret. This parallels Google Cloud Console where you create an OAuth 2.0 Client ID and download a credentials.json file. Microsoft does not use a downloadable JSON file; instead the client_id and tenant_id are configured directly in code.",
    "Microsoft Graph mail scopes are granular: Mail.Read, Mail.ReadWrite, Mail.Send, Mail.Read.Shared, etc. These map closely to Gmail scopes like gmail.readonly, gmail.modify, gmail.compose, gmail.send. For iobox's use case (read + send/forward), the equivalent Microsoft scopes would be Mail.ReadWrite and Mail.Send (delegated permissions).",
    "MSAL Python's PublicClientApplication is the direct counterpart to google-auth-oauthlib's InstalledAppFlow. For interactive auth, MSAL offers acquire_token_interactive() which opens a browser (similar to InstalledAppFlow.run_local_server), plus acquire_token_by_device_flow() for headless/CLI scenarios with no browser. The redirect URI for desktop apps is typically http://localhost.",
    "Token refresh in MSAL is handled automatically via acquire_token_silent(), which checks the in-memory cache for a valid access token or a valid refresh token, and silently redeems a new access token if needed. This is comparable to google.auth.credentials.Credentials.refresh(Request()) but more integrated -- MSAL combines cache lookup and refresh into a single call.",
    "Token persistence in MSAL requires explicit setup. The default is in-memory only. For file-based persistence, MSAL provides SerializableTokenCache with serialize()/deserialize() methods. The recommended approach for desktop apps is the msal-extensions package (v1.3.1), which provides PersistedTokenCache with platform-specific encryption: DPAPI on Windows, Keychain on macOS, LibSecret on Linux. This is more sophisticated than iobox's current plain-text token.json approach with google-auth-oauthlib.",
    "The Python library ecosystem includes: (1) msal -- the core authentication library, analogous to google-auth-oauthlib; (2) msal-extensions -- token cache persistence with encryption, no direct Google equivalent; (3) azure-identity -- a higher-level wrapper around msal designed for Azure SDK integration, uses msal internally. For calling Microsoft Graph directly (as iobox would), msal is the correct choice. azure-identity is better suited for Azure service clients.",
    "Scope mismatch handling differs: iobox currently detects when stored Google credentials have different scopes and triggers re-auth. MSAL does not store requested scopes in the same way; instead, acquire_token_silent() is called with the desired scopes, and if no matching token exists in cache, it returns None, prompting the app to fall back to interactive auth. The pattern is 'try silent, fall back to interactive' rather than explicit scope comparison.",
    "The recommended MSAL token acquisition pattern for a CLI app is: (1) call get_accounts() to find cached accounts, (2) call acquire_token_silent(scopes, account) to try cache/refresh, (3) if that returns None or an error, call acquire_token_interactive(scopes) or acquire_token_by_device_flow(). This maps well to iobox's current pattern of load-token -> check-valid -> refresh-or-reauth."
  ],
  "gaps": [
    "Admin consent requirements for organizational accounts were not deeply explored -- some Microsoft tenants require admin consent for Mail.ReadWrite and Mail.Send scopes, which could affect iobox usability in enterprise environments.",
    "The microsoft-graph-sdk (msgraph-sdk-python) as a higher-level alternative to raw HTTP calls was not investigated in depth."
  ]
}
```

## Findings (prose)

**App Registration.** To use Microsoft Graph API, developers register an application in the Microsoft Entra admin center (formerly Azure AD) under Identity > Applications > App registrations. The registration yields an Application (client) ID and a Directory (tenant) ID. For a desktop/CLI application like iobox, the platform type is "Mobile and desktop applications" with a redirect URI of `http://localhost`. Unlike Google's approach of downloading a `credentials.json` file containing client ID and secret, Microsoft's client_id and tenant_id are typically configured directly in application code or environment variables. For public client (desktop) apps, no client secret is needed -- the app is registered without credentials, relying on PKCE for security during the auth code flow [1][2].

**OAuth Scopes for Mail.** Microsoft Graph uses granular delegated permissions for mail access: `Mail.Read` (read-only), `Mail.ReadWrite` (read and modify), `Mail.Send` (send mail), and `Mail.Read.Shared` (shared mailboxes). For iobox's feature set -- searching, reading, saving, sending, forwarding, labeling, and trashing emails -- the equivalent scopes would be `Mail.ReadWrite` and `Mail.Send`. These permissions are configured in the app registration under API Permissions and may require admin consent in enterprise tenants. This is comparable to Gmail's `gmail.modify` and `gmail.compose` scopes, though Microsoft's permission model distinguishes between delegated (user-interactive) and application (daemon) permission types more explicitly [3][4].

**Token Acquisition -- Interactive Flow.** MSAL Python's `PublicClientApplication` is the direct counterpart to `google-auth-oauthlib`'s `InstalledAppFlow`. The interactive flow uses `acquire_token_interactive(scopes=["Mail.ReadWrite", "Mail.Send"])`, which opens a local browser for user sign-in, similar to `InstalledAppFlow.run_local_server(port=0)`. MSAL automatically provides PKCE protection. For headless or SSH-based CLI scenarios, MSAL additionally offers `acquire_token_by_device_flow()`, which displays a URL and code for the user to authenticate on a separate device -- a flow Google supports but that iobox does not currently use [5][6].

**Token Refresh and Silent Acquisition.** MSAL handles token refresh through `acquire_token_silent(scopes, account)`, which checks the in-memory cache for a valid access token, and if expired, automatically uses the cached refresh token to obtain a new access token. This is more streamlined than iobox's current Google approach, which requires separate steps: loading credentials from file, checking `creds.valid`, checking `creds.expired and creds.refresh_token`, and then calling `creds.refresh(Request())`. In MSAL, the recommended pattern is: call `get_accounts()` to find cached accounts, try `acquire_token_silent()`, and fall back to interactive auth if it returns None. Scope mismatch is handled implicitly -- if the requested scopes don't match cached tokens, silent acquisition fails and interactive auth is triggered [5][7].

**Token Persistence.** By default, MSAL Python only caches tokens in memory, meaning tokens are lost when the process exits. For CLI tools like iobox that need persistence across runs, there are two approaches. The basic approach uses `SerializableTokenCache` with `serialize()`/`deserialize()` methods to read/write a JSON file, conceptually similar to iobox's current `token.json` with Google. The recommended approach for desktop apps is the `msal-extensions` package (currently v1.3.1), which provides `PersistedTokenCache` with platform-specific encryption: DPAPI on Windows, Keychain on macOS, and LibSecret on Linux. This includes built-in file locking for concurrent access. The usage pattern is: `build_encrypted_persistence(location)` to create a persistence backend, wrap it in `PersistedTokenCache(persistence)`, and pass it as `token_cache=cache` to `PublicClientApplication`. This is notably more secure than iobox's current plaintext `token.json` for Google credentials [8][9][10].

**Python Library Ecosystem.** Three main libraries exist for Microsoft authentication in Python: (1) `msal` -- the core Microsoft Authentication Library, directly analogous to `google-auth-oauthlib`, handling OAuth flows and token management; (2) `msal-extensions` -- adds persistent, encrypted token caching, with no direct equivalent in the Google ecosystem; (3) `azure-identity` -- a higher-level library that wraps `msal` internally and provides `TokenCredential` implementations for Azure SDK clients. For iobox's use case of calling Microsoft Graph REST endpoints directly, `msal` is the appropriate choice. `azure-identity` would be overkill since it is designed to integrate with Azure SDK service clients rather than direct HTTP calls to Graph [11][12].

**Practical Mapping for iobox.** The current iobox auth flow in `auth.py` maps cleanly to MSAL equivalents. `InstalledAppFlow.from_client_secrets_file()` becomes `PublicClientApplication(client_id, authority=authority)`. The `flow.run_local_server(port=0)` call maps to `app.acquire_token_interactive(scopes)`. Loading saved credentials via `Credentials.from_authorized_user_file()` maps to constructing the app with a deserialized `PersistedTokenCache` and calling `acquire_token_silent()`. Token refresh via `creds.refresh(Request())` is handled automatically within `acquire_token_silent()`. The main structural difference is that MSAL manages the token lifecycle more holistically, combining cache lookup, refresh, and error handling in a unified API, while Google's libraries separate these concerns across multiple classes and method calls.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://learn.microsoft.com/en-us/graph/auth-register-app-v2 | Register an application with Microsoft identity platform | Tier 1 | Yes |
| 2 | https://learn.microsoft.com/en-us/entra/identity-platform/msal-client-applications | Public and confidential client apps (MSAL) | Tier 1 | Yes |
| 3 | https://learn.microsoft.com/en-us/graph/permissions-reference | Microsoft Graph permissions reference | Tier 1 | Yes |
| 4 | https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc | Scopes and permissions in Microsoft identity platform | Tier 1 | Yes |
| 5 | https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens | Acquire tokens for your app - MSAL Python | Tier 1 | Yes |
| 6 | https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-acquire-token-device-code-flow | Acquire token using device code flow | Tier 1 | Yes |
| 7 | https://learn.microsoft.com/en-us/entra/msal/python/ | Overview of MSAL for Python | Tier 1 | Yes |
| 8 | https://learn.microsoft.com/en-us/entra/msal/python/advanced/msal-python-token-cache-serialization | Custom token cache serialization (MSAL Python) | Tier 1 | Yes |
| 9 | https://pypi.org/project/msal-extensions/ | msal-extensions on PyPI | Tier 1 | Yes |
| 10 | https://github.com/AzureAD/microsoft-authentication-extensions-for-python | MSAL Extensions for Python (GitHub) | Tier 1 | Yes |
| 11 | https://github.com/AzureAD/microsoft-authentication-library-for-python/issues/299 | azure-identity vs MSAL discussion | Tier 1 | Yes |
| 12 | https://pypi.org/project/azure-identity/ | azure-identity on PyPI | Tier 1 | Partial |
| 13 | https://blog.darrenjrobinson.com/interactive-authentication-to-microsoft-graph-using-msal-with-python-and-delegated-permissions/ | Interactive Auth to Graph using MSAL Python | Tier 2 | Yes |
| 14 | https://learn.microsoft.com/en-us/graph/tutorials/python-email | Add email capabilities to Python apps using Graph | Tier 1 | Partial |
| 15 | https://graphpermissions.merill.net/permission/Mail.Read | Mail.Read permission details | Tier 2 | Partial |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://learn.microsoft.com/en-us/graph/auth-register-app-v2 | Register an application with Microsoft identity platform | App registration steps, platform configuration, redirect URIs |
| 2 | https://learn.microsoft.com/en-us/entra/identity-platform/msal-client-applications | Public and confidential client apps | PublicClientApplication characteristics, no secret needed |
| 3 | https://learn.microsoft.com/en-us/graph/permissions-reference | Microsoft Graph permissions reference | Mail.Read, Mail.ReadWrite, Mail.Send scope details |
| 4 | https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc | Scopes and permissions | Delegated vs application permission types |
| 5 | https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens | Acquire tokens - MSAL Python | acquire_token_interactive, acquire_token_silent, device code flow patterns |
| 6 | https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-acquire-token-device-code-flow | Device code flow | Headless/CLI authentication alternative |
| 7 | https://learn.microsoft.com/en-us/entra/msal/python/ | MSAL Python overview | Library architecture, recommended patterns |
| 8 | https://learn.microsoft.com/en-us/entra/msal/python/advanced/msal-python-token-cache-serialization | Token cache serialization | SerializableTokenCache, persistence strategies |
| 9 | https://pypi.org/project/msal-extensions/ | msal-extensions PyPI | PersistedTokenCache, encrypted persistence code example |
| 10 | https://github.com/AzureAD/microsoft-authentication-extensions-for-python | MSAL Extensions GitHub | Platform-specific encryption (DPAPI, Keychain, LibSecret) |
| 11 | https://github.com/AzureAD/microsoft-authentication-library-for-python/issues/299 | MSAL vs azure-identity | Clarification on when to use each library |
| 12 | https://pypi.org/project/azure-identity/ | azure-identity | Higher-level wrapper, uses msal internally |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All key aspects (app registration, scopes, token acquisition, refresh, persistence, library ecosystem) were covered using official Microsoft Tier 1 documentation. The mapping to iobox's current Google auth flow is well-established with direct API-level parallels identified.

### Further Research Needed

- Admin consent requirements and tenant restrictions for Mail.ReadWrite/Mail.Send in enterprise Microsoft 365 environments.
- The `msgraph-sdk-python` package as a higher-level SDK for making Graph API calls (analogous to `google-api-python-client`), which could simplify the HTTP layer.
- Whether iobox should support both interactive browser flow and device code flow to cover SSH/headless CLI usage.
