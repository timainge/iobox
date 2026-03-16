---
id: task-014
title: "MicrosoftAuth shared object"
milestone: 2
status: done
priority: p1
depends_on: [task-012, task-013]
blocks: []
parallel_with: [task-010, task-011]
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

`OutlookProvider`, `OutlookCalendarProvider`, and `OneDriveProvider` each manage their own O365 auth independently. This means three separate OAuth flows for the same Microsoft account — and the current `OutlookAuth` hardcodes a token path, breaking multi-account setups.

`MicrosoftAuth` is the Microsoft counterpart to `GoogleAuth` (task-003): a shared auth object for all Microsoft services, accepting `account` + `scopes` and managing a single token file per account.

## Scope

**Does:**
- `src/iobox/providers/microsoft_auth.py` — `MicrosoftAuth(account, scopes, credentials_dir)`
- `MicrosoftAuth.get_account() -> O365.Account` — authenticated O365 Account
- Account-namespaced token path: `~/.iobox/tokens/{account}/microsoft_token.txt`
- Scope aggregation: combine Mail + Calendar + Files scopes for one-time OAuth
- Refactor `OutlookProvider`, `OutlookCalendarProvider`, `OneDriveProvider` to accept `MicrosoftAuth`
- Fix the hardcoded path bug in `outlook_auth.py` (aligns with task-003's fix)

**Does NOT:**
- Change any public CLI behavior
- Migrate existing users' token files
- Implement new Outlook capabilities

## Architecture Notes

- `MicrosoftAuth` wraps `O365.Account` with `FileSystemTokenBackend`
- Token file: `{credentials_dir}/tokens/{account}/microsoft_token.txt`
- Scope sets by mode (parallel to `get_google_scopes` from task-003):
  - `messages` + `readonly` → `['Mail.Read']`
  - `messages` + `standard` → `['Mail.ReadWrite', 'Mail.Send']`
  - `calendar` + `readonly` → `['Calendars.Read']`
  - `calendar` + `standard` → `['Calendars.ReadWrite']`
  - `drive` + `readonly` → `['Files.Read.All']`
  - `drive` + `standard` → `['Files.ReadWrite.All']`
- Providers should accept `MicrosoftAuth` in constructor (via `auth=` kwarg) OR auto-construct from account+credentials_dir
- `OutlookAuth` becomes a thin wrapper that uses `MicrosoftAuth` internally
- `Workspace.from_config()` (task-007) will be updated to create one `MicrosoftAuth` per (account, mode) and share it across Outlook, Calendar, OneDrive providers

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/microsoft_auth.py` | `MicrosoftAuth` class |
| Modify | `src/iobox/providers/outlook_auth.py` | Delegate to `MicrosoftAuth` |
| Modify | `src/iobox/providers/outlook.py` | Accept `auth=` kwarg |
| Modify | `src/iobox/providers/outlook_calendar.py` | Accept `auth=` kwarg |
| Modify | `src/iobox/providers/onedrive.py` | Accept `auth=` kwarg |
| Modify | `src/iobox/workspace.py` | Share `MicrosoftAuth` per account in `from_config` |
| Create | `tests/unit/test_microsoft_auth.py` | Unit tests |

## MicrosoftAuth Implementation

```python
# src/iobox/providers/microsoft_auth.py
from __future__ import annotations
import os
from pathlib import Path

try:
    from O365 import Account, FileSystemTokenBackend
    HAS_O365 = True
except ImportError:
    HAS_O365 = False

def get_microsoft_scopes(services: list[str], mode: str) -> list[str]:
    """Build combined Microsoft scope list for given services and mode."""
    scopes = ["basic"]  # O365 'basic' = profile info
    if "messages" in services:
        if mode == "readonly":
            scopes.extend(["Mail.Read"])
        else:
            scopes.extend(["Mail.ReadWrite", "Mail.Send"])
    if "calendar" in services:
        if mode == "readonly":
            scopes.extend(["Calendars.Read"])
        else:
            scopes.extend(["Calendars.ReadWrite"])
    if "drive" in services:
        if mode == "readonly":
            scopes.extend(["Files.Read.All"])
        else:
            scopes.extend(["Files.ReadWrite.All"])
    return scopes

class MicrosoftAuth:
    """
    Shared auth for all Microsoft 365 services.
    One instance per (account, scope_set) — handles Outlook, Calendar, OneDrive.
    """

    def __init__(
        self,
        account: str,
        scopes: list[str],
        credentials_dir: str | None = None,
        client_id: str | None = None,
        tenant_id: str | None = None,
    ):
        if not HAS_O365:
            raise ImportError("O365 package required. Install with: pip install 'iobox[outlook]'")
        self.account = account
        self.scopes = scopes
        self.credentials_dir = Path(credentials_dir or Path.home() / ".iobox")
        self.client_id = client_id or os.environ.get("OUTLOOK_CLIENT_ID", "")
        self.tenant_id = tenant_id or os.environ.get("OUTLOOK_TENANT_ID", "common")
        self._o365_account = None

    @property
    def token_dir(self) -> Path:
        token_dir = self.credentials_dir / "tokens" / self.account
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir

    @property
    def token_file(self) -> Path:
        return self.token_dir / "microsoft_token.txt"

    def get_account(self) -> "Account":
        """Return authenticated O365 Account, triggering OAuth if needed."""
        if self._o365_account is not None:
            return self._o365_account

        if not self.client_id:
            raise ValueError("OUTLOOK_CLIENT_ID environment variable not set.")

        token_backend = FileSystemTokenBackend(
            token_path=str(self.token_dir),
            token_filename="microsoft_token.txt",
        )
        o365_account = Account(
            credentials=(self.client_id, ""),
            auth_flow_type="authorization",
            tenant_id=self.tenant_id,
            token_backend=token_backend,
            main_resource=self.account,
        )

        if not o365_account.is_authenticated:
            o365_account.authenticate(scopes=self.scopes)

        self._o365_account = o365_account
        return o365_account
```

## Updating Providers to Accept auth=

For each of `OutlookProvider`, `OutlookCalendarProvider`, `OneDriveProvider`:

```python
def __init__(
    self,
    auth: MicrosoftAuth | None = None,
    account_email: str = "default",
    credentials_dir: str | None = None,
    mode: str = "readonly",
):
    if auth is not None:
        self._microsoft_auth = auth
    else:
        from iobox.providers.microsoft_auth import MicrosoftAuth, get_microsoft_scopes
        service_name = "messages"  # or "calendar" / "drive" depending on provider
        scopes = get_microsoft_scopes([service_name], mode)
        self._microsoft_auth = MicrosoftAuth(
            account=account_email,
            scopes=scopes,
            credentials_dir=credentials_dir,
        )
```

## Updating Workspace.from_config()

In `workspace.py` `from_config()`, add Microsoft auth sharing:

```python
# In from_config, add microsoft auth cache:
ms_auth_cache: dict[str, MicrosoftAuth] = {}

for entry in config.services:
    if entry.service == "outlook":
        from iobox.providers.microsoft_auth import MicrosoftAuth, get_microsoft_scopes
        ms_cache_key = f"{entry.account}:{entry.mode}"
        ms_auth = ms_auth_cache.get(ms_cache_key)
        if ms_auth is None:
            scopes = get_microsoft_scopes(entry.scopes, entry.mode)
            ms_auth = MicrosoftAuth(account=entry.account, scopes=scopes, credentials_dir=creds_dir)
            ms_auth_cache[ms_cache_key] = ms_auth

        if "messages" in entry.scopes:
            from iobox.providers.outlook import OutlookProvider
            provider = OutlookProvider(auth=ms_auth)
            message_slots.append(ProviderSlot(name=entry.slug, provider=provider))
        if "calendar" in entry.scopes:
            from iobox.providers.outlook_calendar import OutlookCalendarProvider
            provider = OutlookCalendarProvider(auth=ms_auth)
            calendar_slots.append(ProviderSlot(...))
        # onedrive: same pattern
```

## Key Decisions

**Q: Should `OutlookAuth` be removed after this?**
Not immediately — keep it as a thin wrapper around `MicrosoftAuth` for any code that imports it directly. Deprecate it.

**Q: Should the token filename be `microsoft_token.txt` (same as before) or account-scoped?**
Use `microsoft_token.txt` per account directory: `~/.iobox/tokens/corp@company.com/microsoft_token.txt`. This is the account-namespaced version of what was previously `tokens/outlook/o365_token.txt`.

**Q: Migration from old token path?**
Check: if `tokens/outlook/o365_token.txt` exists and the new path doesn't, copy it. Log a notice. Same pattern as task-003's Outlook fix.

## Test Strategy

```python
# tests/unit/test_microsoft_auth.py
class TestMicrosoftAuth:
    def test_token_path_is_account_namespaced(self, tmp_path): ...
    def test_get_account_triggers_oauth_when_not_authenticated(self, mock_o365_account): ...
    def test_get_account_cached_after_first_call(self, mock_o365_account): ...

class TestGetMicrosoftScopes:
    def test_messages_readonly(self): ...
    def test_messages_calendar_drive_readonly(self): ...
    def test_standard_includes_write_scopes(self): ...
```

## Verification

```bash
make test
make type-check
python -c "from iobox.providers.microsoft_auth import MicrosoftAuth, get_microsoft_scopes"
```

## Acceptance Criteria

- [ ] `MicrosoftAuth` in `src/iobox/providers/microsoft_auth.py`
- [ ] Token stored at `{creds_dir}/tokens/{account}/microsoft_token.txt`
- [ ] `get_microsoft_scopes(services, mode)` function
- [ ] `OutlookProvider`, `OutlookCalendarProvider`, `OneDriveProvider` accept `auth=MicrosoftAuth`
- [ ] `Workspace.from_config()` shares one `MicrosoftAuth` per (account, mode) across providers
- [ ] Migration fallback from old `tokens/outlook/o365_token.txt`
- [ ] All tests pass
