# Workspace

`iobox.workspace.Workspace` is the compositor: it holds provider slots for email, calendar, and files, and fans queries out across them in parallel.

## Loading a workspace

From a saved config (the usual way):

```python
from iobox.space_config import get_active_space, load_space, list_spaces
from iobox.workspace import Workspace

print(list_spaces())                       # ['personal', 'work']
ws = Workspace.from_config(load_space("work"))
```

`from_config(config, credentials_dir=None)` reads tokens from `~/.iobox` unless you pass another directory.

Or build one by hand from provider instances:

```python
from iobox.providers.google.auth import GoogleAuth
from iobox.providers.google.email import GmailProvider
from iobox.providers.google.calendar import GoogleCalendarProvider
from iobox.modes import get_google_scopes
from iobox.workspace import ProviderSlot, Workspace

auth = GoogleAuth(
    account="you@gmail.com",
    scopes=get_google_scopes(["email", "calendar"], "readonly"),
    credentials_dir="/Users/you/.iobox",
    tier="readonly",
)
ws = Workspace(
    name="adhoc",
    email_providers=[ProviderSlot("you-gmail", GmailProvider(auth=auth), tags=["personal"])],
    calendar_providers=[ProviderSlot("you-gmail-cal", GoogleCalendarProvider(auth=auth), tags=["personal"])],
)
```

## Querying

### Cross-type search

```python
results = ws.search("Henderson", types=["email", "event", "file"], max_results_per_type=10)
```

Returns a single `list[Resource]` sorted by `created_at`, newest first. Emails are converted to the `Email` resource shape so all three types can be handled uniformly — dispatch on `r["resource_type"]`.

### Per-type queries

```python
from datetime import date
from iobox.providers.base import EmailQuery, EventQuery, FileQuery

emails = ws.search_emails(EmailQuery(from_addr="accountant@example.com", after=date(2026, 1, 1)))
events = ws.list_events(EventQuery(after="2026-11-01", before="2026-11-08"))
files  = ws.list_files(FileQuery(text="budget", max_results=20))
```

| Method | Returns | Sorted by |
|---|---|---|
| `search_emails(query, providers=None, tags=None)` | `list[EmailData]` | `date`, newest first |
| `list_events(query, providers=None, tags=None)` | `list[Event]` | `start`, chronological |
| `list_files(query, providers=None, tags=None)` | `list[File]` | `modified_at`, newest first |
| `search(text, types=None, max_results_per_type=10)` | `list[Resource]` | `created_at`, newest first |

See [Types](types.md) for the query and result fields.

### Narrowing to specific slots

```python
ws.list_events(q, providers=["work-gmail-cal"])     # by slot name
ws.search_emails(q, tags=["personal"])              # by tag (hand-built workspaces)
```

## Partial failures

A failing slot never raises out of a fan-out call. The error is logged and recorded on the session, and results from the other slots are returned:

```python
events = ws.list_events(q)
for slot, state in ws.auth_status().items():
    if state.error:
        print(f"{slot} failed: {state.error}")
```

If you need all-or-nothing behaviour, check `auth_status()` after each call and raise yourself.

## Writes

The workspace is read-oriented. For writes, get the provider for a specific slot and call it directly:

```python
gmail = ws.get_email_provider("you-gmail")
gmail.create_draft(to="alice@example.com", subject="Notes", body="Attached.")

cal = next(s.provider for s in ws.calendar_providers if s.name == "you-gmail-cal")
cal.create_event(title="Review", start="2026-11-03T10:00:00", end="2026-11-03T10:30:00")
```

Writes fail if the slot's account was added with `--read`.

!!! warning "Known issue"
    In the current release, `Workspace.from_config` builds Google Calendar and Google Drive providers without passing the session's mode, so their write methods raise `PermissionError` even for read-write sessions. Until that's fixed, construct those providers directly with `mode="standard"` for writes (see [Providers](providers.md#google)).

See [Providers](providers.md) for the full write surface.

## Working with configs

`iobox.space_config` reads and writes the TOML files behind `iobox space`:

```python
from iobox.space_config import ServiceEntry, load_space, save_space, set_active_space

cfg = load_space("personal")
for svc in cfg.services:
    print(svc.number, svc.service, svc.account, svc.scopes, svc.mode, svc.slug)

set_active_space("work")
```

Adding a `ServiceEntry` with `save_space` writes the config but does **not** run OAuth — use `iobox space add` (or `space login`) for that.
