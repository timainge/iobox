# Types

All types are defined in `iobox.providers.base` and re-exported from `iobox.providers`. Results are `TypedDict`s — plain dicts at runtime, typed for your editor and mypy.

## Resources

Every resource shares these fields:

```python
class Resource(TypedDict):
    id: str
    provider_id: str      # "gmail" | "google_calendar" | "google_drive" | "outlook" | …
    resource_type: str    # "email" | "event" | "file"
    title: str            # subject / event name / filename
    created_at: str       # ISO 8601
    modified_at: str      # ISO 8601
    url: str | None       # browser link, if any
```

### Event

```python
class Event(Resource):
    start: str                 # ISO 8601 datetime, or date for all-day
    end: str
    all_day: bool
    organizer: str | None
    attendees: list[AttendeeInfo]   # {email, name, response_status}
    location: str | None
    description: str | None
    meeting_url: str | None
    status: str | None         # "confirmed" | "tentative" | "cancelled"
    recurrence: str | None     # RRULE
```

### File

```python
class File(Resource):
    name: str
    mime_type: str
    size: int                  # bytes; 0 for Google Docs/Sheets/Slides and folders
    path: str | None
    parent_id: str | None
    is_folder: bool
    download_url: str | None
    content: str | None        # pre-fetched text, or None if not fetched
```

### Email

The `Email` resource is used when emails are mixed with events and files (e.g. `Workspace.search()`):

```python
class Email(Resource):
    from_: str
    to: list[str]
    cc: list[str]
    thread_id: str | None
    snippet: str | None
    labels: list[str]
    body: str | None
    content_type: str | None
    attachments: list[AttachmentInfo]
```

## EmailData

`EmailProvider` methods and `Workspace.search_emails()` return `EmailData` instead — the provider-native email shape:

| Field | Always present | Notes |
|---|---|---|
| `message_id`, `subject`, `date`, `snippet`, `thread_id`, `labels` | ✓ | |
| `from_` | ✓ | `"Display Name <email>"`. Note the underscore. |
| `to`, `cc`, `bcc`, `reply_to` | | Comma-separated strings |
| `body`, `content_type` | | Present on full fetches |
| `attachments` | | `list[AttachmentInfo]` |
| `error` | | Set when a message in a batch couldn't be fetched |

`AttachmentInfo` has `id`, `filename`, `mime_type`, `size`, plus optional `inline` (signature logos, `cid:` images) and `content_id`.

!!! warning "`from_` vs `from`"
    Providers return the sender as `from_`. The email Markdown converter and file manager expect `from`. Rename the key before passing `EmailData` to them — see [Processing](processing.md#email).

## Queries

### EmailQuery

```python
@dataclass
class EmailQuery:
    text: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    subject: str | None = None
    after: date | None = None
    before: date | None = None
    has_attachment: bool | None = None
    is_unread: bool | None = None
    label: str | None = None
    max_results: int = 100
    include_spam_trash: bool = False
    raw_query: str | None = None   # native provider syntax; overrides the fields above
```

### EventQuery and FileQuery

```python
@dataclass
class ResourceQuery:
    text: str | None = None
    after: str | None = None       # ISO 8601 date
    before: str | None = None
    max_results: int = 25

@dataclass
class EventQuery(ResourceQuery):
    calendar_id: str = "primary"

@dataclass
class FileQuery(ResourceQuery):
    mime_type: str | None = None
    folder_id: str | None = None
    shared_with_me: bool = False
```

Note that `EmailQuery.after` takes a `date`, while `EventQuery`/`FileQuery` take ISO strings.
