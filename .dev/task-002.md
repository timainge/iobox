---
id: task-002
title: "New type hierarchy in providers/base.py"
milestone: 0
status: done
priority: p0
depends_on: []
blocks: [task-005, task-006, task-007, task-008, task-012, task-013]
parallel_with: [task-001, task-003]
estimated_effort: L
research_needed: false
research_questions: []
assigned_to: null
---

## Context

The Workspace expansion needs three new resource types (`Email`, `Event`, `File`) that share a common `Resource` base, plus three provider ABCs (`CalendarProvider`, `FileProvider`, and `MessageProvider`). Currently `providers/base.py` only has `EmailProvider`, `EmailData`, `EmailQuery`, and related types.

This task is purely additive — it adds new types and ABCs without touching any existing ones. All current providers, tests, and CLI code continue to work unchanged.

## Scope

**Does:**
- Add `Resource` base TypedDict with shared fields
- Add `Email(Resource)` TypedDict wrapping/extending `EmailData` fields
- Add `Event(Resource)` TypedDict for calendar events
- Add `File(Resource)` TypedDict for drive/storage files
- Add `AttendeeInfo` TypedDict
- Add `CalendarProvider(ABC)` with read-only methods
- Add `FileProvider(ABC)` with read-only methods
- Add `ResourceQuery` base dataclass
- Add `EventQuery(ResourceQuery)` and `FileQuery(ResourceQuery)`
- Update `providers/__init__.py` to export new types

**Does NOT:**
- Rename or modify `EmailProvider`, `EmailData`, `EmailQuery`
- Change any method signatures on `GmailProvider` or `OutlookProvider`
- Remove or deprecate anything
- Add `MessageProvider` alias (the plan drops this rename entirely)
- Implement any provider (that's task-005, task-006, task-012, task-013)

## Strategic Fit

This is the foundational type layer for the entire Workspace expansion. Every provider, test, and CLI command in subsequent tasks imports from here. Getting the types right here avoids churn across all downstream tasks.

## Architecture Notes

- `Resource` is a TypedDict (not dataclass) for consistency with `EmailData`
- `Email(Resource)` is a NEW TypedDict that includes the workspace-level base fields plus email-specific fields — it does NOT replace `EmailData` in `EmailProvider` method signatures
- `EmailData` continues to be used everywhere in `GmailProvider`, `OutlookProvider`, and `cli.py` — zero changes
- The `resource_type` discriminant field enables `isinstance`-free dispatch in `Workspace.search()` and markdown converters
- `AttendeeInfo` is a separate TypedDict, not inline, because it appears in both `Event` and potentially future Chat types
- `CalendarProvider` and `FileProvider` follow the same ABC pattern as `EmailProvider` — abstract methods with clear docstrings
- `EventQuery` and `FileQuery` are dataclasses (not TypedDicts) for the same reason `EmailQuery` is: they benefit from defaults and `__post_init__`

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/providers/base.py` | Add new types and ABCs (all additive) |
| Modify | `src/iobox/providers/__init__.py` | Export new types |
| Modify | `tests/unit/test_provider_contract.py` | Add contract stubs for new ABCs |

## New Types

### Resource base

```python
class Resource(TypedDict):
    id: str
    provider_id: str        # "gmail" | "google_calendar" | "google_drive" | "outlook" | ...
    resource_type: str      # "email" | "event" | "file"
    title: str              # subject / event name / filename
    created_at: str         # ISO 8601
    modified_at: str        # ISO 8601
    url: str | None         # web link to item
```

### Email(Resource)

```python
class Email(Resource):
    """Cross-provider email in Resource context. EmailData is still used in EmailProvider methods."""
    from_: str
    to: list[str]
    cc: list[str]
    thread_id: str | None
    snippet: str | None
    labels: list[str]
    body: str | None
    content_type: str | None    # "text/html" | "text/plain"
    attachments: list[AttachmentInfo]
```

Note: `resource_type` is always `"email"` for `Email` instances.

### AttendeeInfo

```python
class AttendeeInfo(TypedDict):
    email: str
    name: str | None
    response_status: str | None  # "accepted" | "declined" | "tentative" | "needsAction"
```

### Event(Resource)

```python
class Event(Resource):
    start: str              # ISO 8601 datetime or date
    end: str                # ISO 8601 datetime or date
    all_day: bool
    organizer: str | None   # email address
    attendees: list[AttendeeInfo]
    location: str | None
    description: str | None
    meeting_url: str | None
    status: str | None      # "confirmed" | "tentative" | "cancelled"
    recurrence: str | None  # RRULE string
```

### File(Resource)

```python
class File(Resource):
    name: str               # filename (not full path)
    mime_type: str
    size: int               # bytes; 0 for folders
    path: str | None        # folder path (not always available)
    parent_id: str | None
    is_folder: bool
    download_url: str | None
    content: str | None     # text content if pre-fetched; None otherwise
```

### ResourceQuery base dataclass

```python
@dataclass
class ResourceQuery:
    text: str | None = None
    after: str | None = None    # ISO 8601 date
    before: str | None = None   # ISO 8601 date
    max_results: int = 25
```

### EventQuery

```python
@dataclass
class EventQuery(ResourceQuery):
    calendar_id: str = "primary"
```

### FileQuery

```python
@dataclass
class FileQuery(ResourceQuery):
    mime_type: str | None = None
    folder_id: str | None = None
    shared_with_me: bool = False
```

## New ABCs

### CalendarProvider

```python
class CalendarProvider(ABC):
    """Abstract base for calendar providers (read-only initially)."""

    @abstractmethod
    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        ...

    @abstractmethod
    def get_profile(self) -> dict:
        """Return basic account info: email, display_name."""
        ...

    @abstractmethod
    def list_events(self, query: EventQuery) -> list[Event]:
        """Return events matching query, sorted by start time ascending."""
        ...

    @abstractmethod
    def get_event(self, event_id: str) -> Event:
        """Return a single event by ID. Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_sync_state(self) -> dict:
        """Return provider-specific sync token/cursor for incremental sync."""
        ...

    @abstractmethod
    def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
        """Return (new_events, next_sync_token) since last sync."""
        ...
```

### FileProvider

```python
class FileProvider(ABC):
    """Abstract base for file/storage providers (read-only initially)."""

    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_profile(self) -> dict: ...

    @abstractmethod
    def list_files(self, query: FileQuery) -> list[File]:
        """Return files matching query."""
        ...

    @abstractmethod
    def get_file(self, file_id: str) -> File:
        """Return file metadata by ID."""
        ...

    @abstractmethod
    def get_file_content(self, file_id: str) -> str:
        """Return text content of file. Returns empty string for binary files."""
        ...

    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """Return raw bytes of file."""
        ...
```

## Implementation Guide

### Step 1 — Add imports to base.py

Add to top of `src/iobox/providers/base.py`:
```python
from dataclasses import dataclass
```
(if not already present — check existing imports)

### Step 2 — Add types in this order

1. `AttendeeInfo` (no deps)
2. `Resource` (no deps)
3. `Email(Resource)` — note: imports `AttachmentInfo` which is already defined
4. `Event(Resource)`
5. `File(Resource)`
6. `ResourceQuery` dataclass
7. `EventQuery(ResourceQuery)`
8. `FileQuery(ResourceQuery)`
9. `CalendarProvider(ABC)`
10. `FileProvider(ABC)`

Place all new content after the existing types/classes, not interleaved with them.

### Step 3 — Update providers/__init__.py

Add to exports:
```python
from iobox.providers.base import (
    # existing...
    # new:
    Resource,
    Email,
    Event,
    File,
    AttendeeInfo,
    ResourceQuery,
    EventQuery,
    FileQuery,
    CalendarProvider,
    FileProvider,
)
```

### Step 4 — Update test_provider_contract.py

Add abstract contract test stubs for `CalendarProvider` and `FileProvider`. These will be skipped until concrete implementations exist (task-005, task-006, task-012, task-013). Follow the existing pattern in that file.

## Key Decisions

**Q: Why `Email(Resource)` instead of just using `EmailData` in cross-type contexts?**
`EmailData` predates the Resource abstraction and lacks `resource_type`, `provider_id`, `title`, `created_at`, `modified_at`, `url`. Rather than modify `EmailData` (breaking change), `Email` is a new additive type for the Workspace layer. The CLI and provider methods continue using `EmailData`.

**Q: Should `resource_type` be `Literal["email", "event", "file"]`?**
Use `str` rather than `Literal` to avoid mypy issues with TypedDict inheritance. Document the valid values in a comment. If strict typing is desired later, a `ResourceType = Literal[...]` alias can be added.

**Q: Why are `EventQuery` and `FileQuery` dataclasses but `EmailQuery` already is one?**
Consistent — all query types are dataclasses. Verify `EmailQuery` is a dataclass (it should be); if it's a TypedDict, keep it as-is and make the new ones dataclasses.

**Q: `get_sync_state()` / `get_new_events()` on CalendarProvider — do these belong in the base?**
Yes — they enable incremental sync for the Workspace layer. The Workspace session stores sync tokens per-provider. If a provider doesn't support sync, raise `NotImplementedError`.

## Test Strategy

This task is mostly structural — the main risk is breaking existing tests.

```bash
# After implementing, verify zero regressions:
make test

# Verify imports work:
python -c "from iobox.providers.base import Resource, Event, File, CalendarProvider, FileProvider"
python -c "from iobox.providers import Resource, Event, File, EventQuery, FileQuery"
```

Unit tests for the new types themselves:
```python
# tests/unit/test_provider_base_types.py
class TestResourceTypes:
    def test_email_typeddict_fields(self): ...
    def test_event_typeddict_fields(self): ...
    def test_file_typeddict_fields(self): ...

class TestQueryDataclasses:
    def test_resource_query_defaults(self): ...
    def test_event_query_inherits_resource_query(self): ...
    def test_file_query_defaults(self): ...
```

## Verification

```bash
make type-check  # mypy passes with no new errors
make test        # all existing tests pass
python -c "from iobox.providers.base import CalendarProvider, FileProvider, Resource, Event, File, EventQuery, FileQuery"
```

## Acceptance Criteria

- [ ] `Resource`, `Email`, `Event`, `File`, `AttendeeInfo` TypedDicts defined
- [ ] `ResourceQuery`, `EventQuery`, `FileQuery` dataclasses defined
- [ ] `CalendarProvider(ABC)` with 6 abstract methods
- [ ] `FileProvider(ABC)` with 5 abstract methods
- [ ] All new types exported from `providers/__init__.py`
- [ ] Zero changes to `EmailProvider`, `EmailData`, `EmailQuery`, `AttachmentInfo`
- [ ] All existing tests pass (`make test`)
- [ ] `make type-check` passes with no new errors
- [ ] Contract test stubs added for new ABCs
