---
id: task-007
title: "Workspace + WorkspaceSession compositor"
milestone: 0
status: done
priority: p0
depends_on: [task-001, task-002]
blocks: [task-010, task-011]
parallel_with: [task-004, task-005, task-006, task-008]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

`Workspace` is the primary user-facing abstraction in the expanded iobox. It fans out queries across multiple providers (Gmail accounts, GCal, GDrive), handles partial failures gracefully, merges results, and maintains per-provider session state. This is the "killer feature" that makes cross-type search possible.

The `Workspace` class does not own auth — it composes already-instantiated providers from config. Auth happens at `space add` / `space login` time (task-004).

## Scope

**Does:**
- `src/iobox/workspace.py` — `Workspace`, `ProviderSlot`, `WorkspaceSession`, `ProviderSession`
- `Workspace.search_messages(query, providers=None, tags=None) -> list[EmailData]`
- `Workspace.list_events(query, providers=None, tags=None) -> list[Event]`
- `Workspace.list_files(query, providers=None, tags=None) -> list[File]`
- `Workspace.search(text, types=None) -> list[Resource]` — cross-type unified search
- `Workspace.auth_status() -> dict[str, ProviderSession]`
- `Workspace.from_config(config, credentials_dir) -> Workspace` — factory method
- Fan-out with `ThreadPoolExecutor` — parallel provider calls
- Partial failure: catch per-slot exceptions, record in session, continue
- Result merging: sort by `created_at` descending across providers

**Does NOT:**
- Implement write operations through Workspace (task-017)
- Build CLI commands (task-010)
- Implement MCP tools (task-011)
- Persist session state to disk automatically — session is updated in-memory; callers save it

## Strategic Fit

This is the compositor layer that ties together task-001 (config), task-002 (types), task-003 (auth), task-005 (GCal), task-006 (GDrive), and the existing `GmailProvider`. After this task, the PoC demo is runnable.

## Architecture Notes

- `ProviderSlot` holds a concrete provider instance + name + tags
- `ProviderSession` is the mutable per-slot state: auth status, sync token, last error
- `WorkspaceSession` is the collection of all `ProviderSession` states — gets serialized to task-001's session JSON
- `Workspace.from_config()` reads the space TOML (via task-001), instantiates providers, and wires everything up
- Fan-out uses `concurrent.futures.ThreadPoolExecutor` — providers are I/O-bound (API calls)
- Partial failure: a slot that raises is logged + its `ProviderSession.error` field is updated; other slots continue
- Result sorting: `created_at` field is ISO 8601 strings — sort lexicographically (works for RFC 3339)
- `search()` cross-type: calls all three fan-outs in parallel, merges all results, sorts by `created_at`
- EmailData→Resource: `search_messages` returns `EmailData` (not `Email`) to preserve the existing invariant; but `search()` wraps email results as `Email` for the unified list

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/workspace.py` | All Workspace classes |
| Modify | `src/iobox/providers/__init__.py` | Expose `get_workspace()` factory |
| Create | `tests/unit/test_workspace.py` | Unit tests |

## Data Structures

```python
# src/iobox/workspace.py
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from iobox.providers.base import (
    EmailProvider, EmailData, EmailQuery,
    CalendarProvider, Event, EventQuery,
    FileProvider, File, FileQuery,
    Resource,
)

logger = logging.getLogger(__name__)

@dataclass
class ProviderSession:
    provider_name: str
    authenticated: bool = False
    scopes: list[str] = field(default_factory=list)
    sync_token: str | None = None
    last_sync: str | None = None
    error: str | None = None

@dataclass
class WorkspaceSession:
    workspace_name: str
    providers: dict[str, ProviderSession] = field(default_factory=dict)

@dataclass
class ProviderSlot:
    name: str
    provider: Any  # EmailProvider | CalendarProvider | FileProvider
    tags: list[str] = field(default_factory=list)

@dataclass
class Workspace:
    name: str
    message_providers: list[ProviderSlot] = field(default_factory=list)
    calendar_providers: list[ProviderSlot] = field(default_factory=list)
    file_providers: list[ProviderSlot] = field(default_factory=list)
    session: WorkspaceSession = field(default_factory=lambda: WorkspaceSession(""))
```

## Fan-out Implementation

```python
def _fan_out(
    self,
    slots: list[ProviderSlot],
    fn_name: str,
    query: Any,
    providers: list[str] | None = None,
    tags: list[str] | None = None,
    max_workers: int = 4,
) -> list[Any]:
    """
    Call fn_name(query) on each matching slot in parallel.
    Partial failures are logged and recorded in session; results from other slots continue.
    """
    # Filter slots
    active_slots = slots
    if providers is not None:
        active_slots = [s for s in active_slots if s.name in providers]
    if tags is not None:
        active_slots = [s for s in active_slots if any(t in s.tags for t in tags)]

    if not active_slots:
        return []

    results: list[Any] = []

    def call_slot(slot: ProviderSlot) -> list[Any]:
        method = getattr(slot.provider, fn_name)
        return method(query)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(active_slots))) as ex:
        future_to_slot = {ex.submit(call_slot, slot): slot for slot in active_slots}
        for future in as_completed(future_to_slot):
            slot = future_to_slot[future]
            try:
                slot_results = future.result()
                results.extend(slot_results)
                # Update session
                if slot.name in self.session.providers:
                    self.session.providers[slot.name].error = None
            except Exception as e:
                logger.error(f"Provider '{slot.name}' failed: {e}")
                if slot.name not in self.session.providers:
                    self.session.providers[slot.name] = ProviderSession(provider_name=slot.name)
                self.session.providers[slot.name].error = str(e)

    return results
```

## Workspace Methods

```python
    def search_messages(
        self,
        query: EmailQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[EmailData]:
        results = self._fan_out(self.message_providers, "search", query, providers, tags)
        return sorted(results, key=lambda m: m.get("date", ""), reverse=True)

    def list_events(
        self,
        query: EventQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[Event]:
        results = self._fan_out(self.calendar_providers, "list_events", query, providers, tags)
        return sorted(results, key=lambda e: e.get("start", ""), reverse=False)  # ascending for events

    def list_files(
        self,
        query: FileQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[File]:
        results = self._fan_out(self.file_providers, "list_files", query, providers, tags)
        return sorted(results, key=lambda f: f.get("modified_at", ""), reverse=True)

    def search(
        self,
        text: str,
        types: list[str] | None = None,
        max_results_per_type: int = 10,
    ) -> list[Resource]:
        """Cross-type search. types defaults to ['email', 'event', 'file']."""
        types = types or ["email", "event", "file"]
        all_results: list[Resource] = []

        # Run all type searches in parallel
        futures = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            if "email" in types:
                q = EmailQuery(query=text, max_results=max_results_per_type)
                futures["email"] = ex.submit(self.search_messages, q)
            if "event" in types:
                q = EventQuery(text=text, max_results=max_results_per_type)
                futures["event"] = ex.submit(self.list_events, q)
            if "file" in types:
                q = FileQuery(text=text, max_results=max_results_per_type)
                futures["file"] = ex.submit(self.list_files, q)

            for type_name, future in futures.items():
                try:
                    results = future.result()
                    if type_name == "email":
                        # Wrap EmailData as Email Resource for unified list
                        all_results.extend(_email_data_to_resource(r) for r in results)
                    else:
                        all_results.extend(results)
                except Exception as e:
                    logger.error(f"search() {type_name} fan-out failed: {e}")

        return sorted(all_results, key=lambda r: r.get("created_at", ""), reverse=True)

    def auth_status(self) -> dict[str, ProviderSession]:
        return dict(self.session.providers)
```

## Factory Method

```python
    @classmethod
    def from_config(cls, config: "SpaceConfig", credentials_dir: str | None = None) -> "Workspace":
        """
        Instantiate a Workspace from a SpaceConfig (task-001).
        Builds provider instances from service entries.
        """
        from iobox.space_config import SpaceConfig
        from iobox.providers.google_auth import GoogleAuth
        from iobox.modes import get_google_scopes, _tier_for_mode

        message_slots: list[ProviderSlot] = []
        calendar_slots: list[ProviderSlot] = []
        file_slots: list[ProviderSlot] = []

        # Group service entries by (service, account) to share GoogleAuth instances
        auth_cache: dict[str, GoogleAuth] = {}

        for entry in config.services:
            creds_dir = credentials_dir or str(Path.home() / ".iobox")
            cache_key = f"{entry.service}:{entry.account}:{entry.mode}"

            if entry.service == "gmail":
                scopes = get_google_scopes(entry.scopes, entry.mode)
                tier = _tier_for_mode(entry.mode)
                auth = auth_cache.get(cache_key)
                if auth is None:
                    auth = GoogleAuth(account=entry.account, scopes=scopes,
                                      credentials_dir=creds_dir, tier=tier)
                    auth_cache[cache_key] = auth

                if "messages" in entry.scopes:
                    from iobox.providers.gmail import GmailProvider
                    provider = GmailProvider(account=entry.account,
                                             credentials_dir=creds_dir,
                                             mode=entry.mode)
                    message_slots.append(ProviderSlot(name=entry.slug, provider=provider))

                if "calendar" in entry.scopes:
                    from iobox.providers.google_calendar import GoogleCalendarProvider
                    provider = GoogleCalendarProvider(auth=auth)
                    calendar_slots.append(ProviderSlot(name=f"{entry.slug}-cal", provider=provider))

                if "drive" in entry.scopes:
                    from iobox.providers.google_drive import GoogleDriveProvider
                    provider = GoogleDriveProvider(auth=auth)
                    file_slots.append(ProviderSlot(name=f"{entry.slug}-drive", provider=provider))

            elif entry.service == "outlook":
                if "messages" in entry.scopes:
                    from iobox.providers.outlook import OutlookProvider
                    provider = OutlookProvider(account=entry.account,
                                               credentials_dir=creds_dir,
                                               mode=entry.mode)
                    message_slots.append(ProviderSlot(name=entry.slug, provider=provider))
                # calendar/onedrive: task-012/013

        session = WorkspaceSession(workspace_name=config.name)
        return cls(
            name=config.name,
            message_providers=message_slots,
            calendar_providers=calendar_slots,
            file_providers=file_slots,
            session=session,
        )
```

## Helper: EmailData to Resource

```python
def _email_data_to_resource(email: EmailData) -> "Email":
    """Wrap EmailData as Email Resource for cross-type unified search results."""
    from iobox.providers.base import Email
    return Email(
        id=email.get("message_id", ""),
        provider_id=email.get("provider_id", ""),
        resource_type="email",
        title=email.get("subject", ""),
        created_at=email.get("date", ""),
        modified_at=email.get("date", ""),
        url=None,
        from_=email.get("from_", ""),
        to=email.get("to", []),
        cc=email.get("cc", []),
        thread_id=email.get("thread_id"),
        snippet=email.get("snippet"),
        labels=email.get("labels", []),
        body=email.get("body"),
        content_type=email.get("content_type"),
        attachments=email.get("attachments", []),
    )
```

## Implementation Guide

### Step 1 — Read existing GmailProvider

Read `src/iobox/providers/gmail.py` to understand the `search()` method signature — `EmailQuery` → `list[EmailData]`.

### Step 2 — Create workspace.py

Create `src/iobox/workspace.py` with all classes above. Keep imports lazy (inside `from_config` method) to avoid circular imports and optional dependency issues.

### Step 3 — Handle EmailQuery vs ResourceQuery mismatch

`EmailQuery` has a `query: str` field (not `text`). When building an `EmailQuery` from `search()`, map `text` → `query`. Check the exact field name in `providers/base.py`.

### Step 4 — Write comprehensive unit tests

The key behaviors to test:
1. Fan-out calls all matching slots
2. Partial failure: one slot raises, others still return results
3. Results sorted correctly
4. `providers=` filter limits which slots are called
5. `tags=` filter works
6. `search()` combines all three types

## Key Decisions

**Q: Should `from_config` create providers that auto-authenticate?**
No — providers should be created but not forced to authenticate at construction. Authentication happens lazily on first API call. `ProviderSlot.provider.authenticate()` can be called explicitly by the `space status` checker.

**Q: What's the right max_workers for ThreadPoolExecutor?**
Default to 4. Each provider makes 1 API call per fan-out. 4 concurrent calls is safe for rate limits. Make it configurable as a keyword arg.

**Q: Should search_messages return EmailData or Email(Resource)?**
`search_messages` returns `list[EmailData]` — preserving the invariant that existing code using the message provider directly still works. Only `search()` wraps results as `Email` for the unified list.

## Test Strategy

```python
# tests/unit/test_workspace.py
class TestFanOut:
    def test_calls_all_slots(self, mock_providers): ...
    def test_partial_failure_continues(self, mock_providers): ...
    def test_partial_failure_records_error_in_session(self, mock_providers): ...
    def test_provider_filter(self, mock_providers): ...
    def test_tag_filter(self, mock_providers): ...
    def test_empty_slots_returns_empty(self): ...

class TestSearchMessages:
    def test_merges_results_from_multiple_providers(self): ...
    def test_sorted_by_date_descending(self): ...

class TestListEvents:
    def test_sorted_by_start_ascending(self): ...

class TestSearch:
    def test_cross_type_returns_all_resource_types(self): ...
    def test_type_filter_limits_providers(self): ...
    def test_partial_failure_in_one_type_continues(self): ...

class TestFromConfig:
    def test_creates_gmail_message_slot(self, mock_space_config): ...
    def test_creates_calendar_slot_when_calendar_in_scopes(self): ...
    def test_creates_drive_slot_when_drive_in_scopes(self): ...
    def test_shares_google_auth_across_services_for_same_account(self): ...
```

## Verification

```bash
make test
python -c "from iobox.workspace import Workspace, ProviderSlot, WorkspaceSession"
```

## Acceptance Criteria

- [ ] `Workspace`, `ProviderSlot`, `WorkspaceSession`, `ProviderSession` dataclasses defined
- [ ] `_fan_out()` with ThreadPoolExecutor — parallel, partial-failure-tolerant
- [ ] `search_messages()`, `list_events()`, `list_files()` with provider/tag filtering
- [ ] `search()` cross-type unified search
- [ ] Results sorted correctly per type
- [ ] `auth_status()` returns current session state
- [ ] `Workspace.from_config()` factory wires up providers from SpaceConfig
- [ ] Lazy imports in `from_config` to avoid circular deps
- [ ] EmailData → Email(Resource) wrapper for unified results
- [ ] All unit tests pass including partial failure scenarios
- [ ] `make type-check` passes
