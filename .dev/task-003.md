---
id: task-003
title: "GoogleAuth shared object + scope aggregation"
milestone: 0
status: done
priority: p0
depends_on: []
blocks: [task-004, task-005, task-006]
parallel_with: [task-001, task-002]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Currently `auth.py` has Gmail-specific auth logic tightly coupled to `GmailProvider`. When we add `GoogleCalendarProvider` and `GoogleDriveProvider`, they need to share the same OAuth token (Google requires all scopes in a single flow). Similarly, `outlook_auth.py` hardcodes a token path, breaking multi-account setups.

This task extracts a `GoogleAuth` class from `auth.py` that can serve Gmail, Calendar, and Drive with one token file. It also fixes the Outlook account namespacing bug.

## Scope

**Does:**
- Extract `GoogleAuth` class from `auth.py` — centralizes credential/token management
- `GoogleAuth(account, scopes, credentials_dir)` — one instance per account, handles multiple services
- Add `GoogleAuth.get_service(api, version)` — returns authenticated googleapiclient service
- Extend `SCOPES_BY_MODE` in `modes.py` to include Calendar and Drive scopes
- Fix Outlook account namespacing: token stored at `tokens/{account}/outlook_token.txt`
- Refactor `auth.py` to use `GoogleAuth` internally (no interface changes)
- Refactor `outlook_auth.py` to use `MicrosoftAuth`-like pattern (full `MicrosoftAuth` in task-014)

**Does NOT:**
- Change any public-facing function signatures in `auth.py`
- Break existing Gmail token paths or force re-auth
- Implement calendar or drive providers (task-005, task-006)
- Implement full `MicrosoftAuth` shared object (that's task-014, after task-012/013)
- Move token files to `~/.iobox/tokens/` (that's a migration, deferred)

## Strategic Fit

Tasks 005 and 006 (`GoogleCalendarProvider`, `GoogleDriveProvider`) need `GoogleAuth` to get authenticated services. Without this, they'd have to implement their own auth — duplicating code and breaking token sharing.

## Architecture Notes

- `GoogleAuth` lives in `src/iobox/providers/google_auth.py` (new file) OR stays in `auth.py` as a class — prefer `google_auth.py` to keep provider code self-contained
- Token tier is determined by the scope set, not a fixed name — use a stable hash or explicit named tiers
- **Named tiers are simpler than hashes**: `readonly` tier = minimal read scopes, `standard` tier = read+write+compose. This preserves backward compat with existing token filenames.
- `GoogleAuth` uses `credentials_dir` for now (not `~/.iobox/tokens/`) — migration comes later
- The `get_service()` method is the key addition: `GoogleCalendarProvider` calls `self.auth.get_service("calendar", "v3")`
- Outlook fix: `OutlookAuth` should accept `account: str` and derive token path from it

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/providers/google_auth.py` | `GoogleAuth` class |
| Modify | `src/iobox/auth.py` | Delegate to `GoogleAuth` internally |
| Modify | `src/iobox/providers/outlook_auth.py` | Accept `account` param, derive namespaced token path |
| Modify | `src/iobox/modes.py` | Add Calendar and Drive scopes to `SCOPES_BY_MODE` |
| Create | `tests/unit/test_google_auth.py` | Unit tests for GoogleAuth |

## Google Scopes by Mode

```python
# src/iobox/modes.py additions

# Gmail scopes (existing)
GMAIL_SCOPES_READONLY = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_SCOPES_STANDARD = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]

# New: Calendar scopes
CALENDAR_SCOPES_READONLY = ["https://www.googleapis.com/auth/calendar.readonly"]
CALENDAR_SCOPES_STANDARD = ["https://www.googleapis.com/auth/calendar"]

# New: Drive scopes
DRIVE_SCOPES_READONLY = ["https://www.googleapis.com/auth/drive.readonly"]

# Scope aggregation by service set + mode
def get_google_scopes(services: list[str], mode: str) -> list[str]:
    """
    Build combined scope list for given services and mode.
    services: subset of ["messages", "calendar", "drive"]
    mode: "readonly" | "standard"
    """
    scopes = []
    if "messages" in services:
        if mode == "readonly":
            scopes.extend(GMAIL_SCOPES_READONLY)
        else:
            scopes.extend(GMAIL_SCOPES_STANDARD)
    if "calendar" in services:
        if mode == "readonly":
            scopes.extend(CALENDAR_SCOPES_READONLY)
        else:
            scopes.extend(CALENDAR_SCOPES_STANDARD)
    if "drive" in services:
        # Drive only has readonly for now (write ops in task-019)
        scopes.extend(DRIVE_SCOPES_READONLY)
    return scopes
```

## GoogleAuth Implementation

```python
# src/iobox/providers/google_auth.py
from __future__ import annotations
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

class GoogleAuth:
    """
    Shared OAuth credential manager for all Google services.
    One instance per (account, scope_set) — handles Gmail, Calendar, Drive.
    """

    def __init__(
        self,
        account: str,
        scopes: list[str],
        credentials_dir: str | None = None,
        tier: str = "readonly",
    ):
        self.account = account
        self.scopes = scopes
        self.tier = tier  # "readonly" or "standard" — determines token filename
        self.credentials_dir = Path(credentials_dir or os.getcwd())
        self._credentials: Credentials | None = None

    @property
    def token_path(self) -> Path:
        token_dir = self.credentials_dir / "tokens" / self.account
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir / f"token_{self.tier}.json"

    @property
    def credentials_file(self) -> Path:
        # Check GOOGLE_APPLICATION_CREDENTIALS env, else credentials.json in creds dir
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path:
            return Path(env_path)
        return self.credentials_dir / "credentials.json"

    def get_credentials(self) -> Credentials:
        """Load, refresh, or trigger new OAuth flow as needed."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.scopes
                )
                creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json())

        self._credentials = creds
        return creds

    def get_service(self, api: str, version: str):
        """Return authenticated googleapiclient service for any Google API."""
        creds = self.get_credentials()
        return build(api, version, credentials=creds)
```

## Outlook Auth Fix

```python
# src/iobox/providers/outlook_auth.py — key change

class OutlookAuth:
    def __init__(self, account: str = "default", credentials_dir: str | None = None):
        self.account = account
        self.credentials_dir = Path(credentials_dir or os.getcwd())

    @property
    def token_path(self) -> Path:
        # FIX: was hardcoded to "tokens/outlook/o365_token.txt"
        token_dir = self.credentials_dir / "tokens" / self.account
        token_dir.mkdir(parents=True, exist_ok=True)
        return token_dir / "outlook_token.txt"

    # ... rest of auth logic unchanged
```

Note: On first run with new account namespacing, existing `tokens/outlook/o365_token.txt` won't be found. Users will need to re-authenticate once. Document this in the change.

## Refactoring auth.py

The existing `auth.py` functions (`get_gmail_credentials()`, `get_authenticated_service()`) should delegate to `GoogleAuth` internally. No signature changes.

```python
# auth.py after refactor — same public API, delegates internally
from iobox.providers.google_auth import GoogleAuth

def get_gmail_credentials(account: str = "default", mode: str = "standard", credentials_dir: str | None = None):
    from iobox.modes import get_google_scopes, _tier_for_mode
    scopes = get_google_scopes(["messages"], mode)
    tier = _tier_for_mode(mode)
    auth = GoogleAuth(account=account, scopes=scopes, credentials_dir=credentials_dir, tier=tier)
    return auth.get_credentials()

def get_authenticated_service(account: str = "default", mode: str = "standard", credentials_dir: str | None = None):
    from iobox.modes import get_google_scopes, _tier_for_mode
    scopes = get_google_scopes(["messages"], mode)
    tier = _tier_for_mode(mode)
    auth = GoogleAuth(account=account, scopes=scopes, credentials_dir=credentials_dir, tier=tier)
    return auth.get_service("gmail", "v1")
```

## Implementation Guide

### Step 1 — Read existing auth.py and outlook_auth.py

Before touching anything, read both files completely. Note all public functions, the token path logic, and any migration code (legacy `token.json` migration).

### Step 2 — Create google_auth.py

Create `src/iobox/providers/google_auth.py` with the `GoogleAuth` class above. Keep the `GMAIL_TOKEN_FILE` env var override path in `GoogleAuth` for backward compat.

### Step 3 — Update modes.py

Add `get_google_scopes()` function and new scope constants. Do not remove or rename existing scope constants — other code may reference them.

### Step 4 — Refactor auth.py

Update `get_gmail_credentials()` and `get_authenticated_service()` to delegate to `GoogleAuth`. Verify all existing calls pass through correctly.

### Step 5 — Fix outlook_auth.py

Update `OutlookAuth` token path to be account-namespaced. Add a fallback: if the old hardcoded path exists and the new path doesn't, copy it to the new path and log a migration notice.

```python
# Migration fallback in OutlookAuth.token_path
old_path = self.credentials_dir / "tokens" / "outlook" / "o365_token.txt"
new_path = token_dir / "outlook_token.txt"
if old_path.exists() and not new_path.exists():
    import shutil
    shutil.copy(old_path, new_path)
    # log migration
return new_path
```

### Step 6 — Write tests

Test `GoogleAuth` with mocked `google.oauth2.credentials.Credentials` and `InstalledAppFlow`. Test that `get_service()` calls `build()` with correct args. Test Outlook migration fallback.

## Key Decisions

**Q: Should `GoogleAuth` handle the `GMAIL_TOKEN_FILE` env override?**
Yes — for backward compat. If `GMAIL_TOKEN_FILE` is set, use that path instead of the derived path. Only applies to `messages` scope (legacy Gmail-only behavior).

**Q: Should we move tokens to `~/.iobox/tokens/` in this task?**
No. That's a migration and would force all users to re-auth. Keep using `credentials_dir` for now. The `~/.iobox/tokens/` path is the long-term target but a separate migration task.

**Q: One `GoogleAuth` per account, or one per (account + scope_set)?**
One per (account + tier). The `tier` determines which token file is used. A `readonly` token is reused for Calendar + Drive + Gmail in readonly mode. A `standard` token for Calendar + Gmail in standard mode. Never mix scopes across tiers.

## Test Strategy

```python
# tests/unit/test_google_auth.py
class TestGoogleAuth:
    def test_token_path_is_account_namespaced(self, tmp_path): ...
    def test_get_credentials_loads_existing_token(self, tmp_path, mock_creds): ...
    def test_get_credentials_triggers_flow_when_no_token(self, tmp_path, mock_flow): ...
    def test_get_service_calls_build_with_correct_args(self, tmp_path, mock_creds, mock_build): ...

class TestOutlookAuthMigration:
    def test_migrates_old_token_path_to_new(self, tmp_path): ...
    def test_new_path_used_when_no_old_token(self, tmp_path): ...

class TestGetGoogleScopes:
    def test_messages_only_readonly(self): ...
    def test_messages_calendar_drive_readonly(self): ...
    def test_messages_calendar_standard(self): ...
```

## Verification

```bash
make test       # all existing tests pass, new tests pass
make type-check # no new mypy errors
python -c "from iobox.providers.google_auth import GoogleAuth"
python -c "from iobox.modes import get_google_scopes; print(get_google_scopes(['messages', 'calendar'], 'readonly'))"
```

## Acceptance Criteria

- [ ] `GoogleAuth` class in `src/iobox/providers/google_auth.py`
- [ ] `GoogleAuth.get_credentials()` loads/refreshes/creates token at account-namespaced path
- [ ] `GoogleAuth.get_service(api, version)` returns googleapiclient service
- [ ] `auth.py` public functions (`get_gmail_credentials`, `get_authenticated_service`) delegate to `GoogleAuth`
- [ ] `SCOPES_BY_MODE` in `modes.py` extended with Calendar and Drive scopes
- [ ] `get_google_scopes(services, mode)` function added to `modes.py`
- [ ] `OutlookAuth` token path is account-namespaced (no more hardcoded path)
- [ ] Migration fallback: old `tokens/outlook/o365_token.txt` copied to new path if found
- [ ] All existing tests pass (`make test`)
- [ ] `make type-check` passes
