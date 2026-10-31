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

Returns a single `list[Resource]` sorted by `created_at`, newest first, with at most `max_results_per_type` results of each type. Emails are converted to the `Email` resource shape (`to`/`cc` split into lists) so all three types can be handled uniformly — dispatch on `r["resource_type"]`.

Event matches are limited to the last 90 days and the future (`DEFAULT_EVENT_SEARCH_DAYS`); use `list_events()` with an explicit `after` to search further back.

### Per-type queries

```python
from datetime import date
from iobox.providers.base import EmailQuery, EventQuery, FileQuery

emails = ws.search_emails(EmailQuery(from_addr="accountant@example.com", after=date(2026, 1, 1)))
events = ws.list_events(EventQuery(after="2026-11-01", before="2026-11-08"))
files  = ws.list_files(FileQuery(text="budget", max_results=20))
```

| Method | Returns | Sorted by | Capped to |
|---|---|---|---|
| `search_emails(query, providers=None, tags=None)` | `list[EmailData]` | `date`, newest first | `query.max_results` |
| `list_events(query, providers=None, tags=None)` | `list[Event]` | `start`, chronological | `query.max_results` |
| `list_files(query, providers=None, tags=None)` | `list[File]` | `modified_at`, newest first | `query.max_results` |
| `search(text, types=None, max_results_per_type=10)` | `list[Resource]` | `created_at`, newest first | `max_results_per_type` per type |

Each slot is asked for up to `max_results`; the merged list is then sorted and cut back to `max_results` (a value of `0` means no cap). Dates are compared as real instants: RFC 2822 email headers and ISO 8601 timestamps with any offset are parsed to UTC (`iobox.workspace.to_utc_datetime`), values without a timezone are taken as local time, and items with a missing or unparsable date sort last.

### Which slot did a result come from?

Every result carries a `"slot"` key. Use it for follow-up calls so they go to the right account:

```python
for msg in ws.search_emails(EmailQuery(text="invoice")):
    provider = ws.get_email_provider(msg["slot"])
    full = provider.get_email_content(msg["message_id"])

ev = ws.list_events(EventQuery(after="2026-11-01"))[0]
ws.get_calendar_provider(ev["slot"]).get_event(ev["id"])
```

See [Types](types.md) for the query and result fields.

### Narrowing to specific slots

```python
ws.list_events(q, providers=["work-gmail-cal"])     # by slot name
ws.search_emails(q, tags=["personal"])              # by tag (hand-built workspaces)
```

## Partial failures

A failing slot never raises out of a fan-out call. The error is logged, results from the other slots are returned, and `ws.last_errors` maps each failed slot name to its error message:

```python
events = ws.list_events(q)
for slot, message in ws.last_errors.items():
    print(f"{slot} failed: {message}")
```

`last_errors` is reset at the start of every `search_emails`, `list_events`, `list_files` and `search` call, so it always describes the most recent call (empty means every slot answered). In `search()` a failure of a whole result type is reported under `search:<type>`. Because it is per-call state, don't share one `Workspace` between threads if you rely on it.

If you need all-or-nothing behaviour, check `ws.last_errors` after each call and raise yourself.

## Writes

The workspace is read-oriented. For writes, get the provider for a specific slot and call it directly:

```python
gmail = ws.get_email_provider("you-gmail")
gmail.create_draft(to="alice@example.com", subject="Notes", body="Attached.")

cal = ws.get_calendar_provider("you-gmail-cal")
cal.create_event(title="Review", start="2026-11-03T10:00:00", end="2026-11-03T10:30:00")
```

Writes fail if the slot's account was added with `--read`.

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

Adding a `ServiceEntry` with `save_space` writes the config but does **not** run OAuth — use `iobox space add` (or `space login`) for that. To add one by hand, give it a slug that is unique in the space and skip accounts that are already there:

```python
from iobox.space_config import find_service, unique_slug

if find_service(cfg, "google", "tim@gmail.co.uk") is None:
    cfg.services.append(ServiceEntry(
        number=max((s.number for s in cfg.services), default=0) + 1,
        service="google",
        account="tim@gmail.co.uk",
        scopes=["email"],
        slug=unique_slug(cfg, "tim@gmail.co.uk"),   # "tim-gmail-2" if "tim-gmail" is taken
    ))
    save_space(cfg)
```

Rules enforced by `space_config`:

- Workspace names must match `^[A-Za-z0-9_-]{1,64}$`; every function that turns a name into a path (`load_space`, `save_space`, `set_active_space`, `load_session`, `save_session`) raises `ValueError` otherwise.
- Account strings are used as directory names, so they may not contain `/`, `\`, `..` or NUL, or start with `.` (`ValueError`).
- `load_space` raises `ValueError` naming the file for invalid TOML, a missing required key, or a `service` other than `google`/`o365` or `mode` other than `readonly`/`standard`/`dangerous`.
- The file name is the space name: `load_space("copy")` returns `name == "copy"` even if the file says otherwise, so saving writes back to the same file.
- Writes are atomic (temporary file, then rename).
- `get_active_space()` returns `None` (and logs a warning) if the active space has been deleted.
