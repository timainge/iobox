# Providers

Providers are the per-service backends. There are three independent abstract base classes — one per resource type — so an account can mix ecosystems (Gmail for mail, OneDrive for files).

| ABC | Implementations | Module |
|---|---|---|
| `EmailProvider` | `GmailProvider`, `OutlookProvider` | `iobox.providers.google.email`, `iobox.providers.o365.email` |
| `CalendarProvider` | `GoogleCalendarProvider`, `OutlookCalendarProvider` | `iobox.providers.google.calendar`, `iobox.providers.o365.calendar` |
| `FileProvider` | `GoogleDriveProvider`, `OneDriveProvider` | `iobox.providers.google.files`, `iobox.providers.o365.files` |

All ABCs live in `iobox.providers.base` and are re-exported from `iobox.providers`.

## Using a provider directly

Use a provider directly when you only need one account, or for writes.

### Google

All Google providers for one account share a `GoogleAuth`, which owns one token per (account, tier):

```python
from iobox.modes import get_google_scopes
from iobox.providers.google.auth import GoogleAuth
from iobox.providers.google.email import GmailProvider
from iobox.providers.google.files import GoogleDriveProvider
from iobox.providers.base import EmailQuery, FileQuery

auth = GoogleAuth(
    account="you@gmail.com",
    scopes=get_google_scopes(["email", "drive"], "standard"),
    credentials_dir="/Users/you/.iobox",   # reuse tokens created by `iobox space add`
    tier="standard",                        # token_standard.json
)

gmail = GmailProvider(auth=auth)
drive = GoogleDriveProvider(auth=auth, mode="standard")   # mode gates writes

msgs = gmail.search_emails(EmailQuery(raw_query="has:attachment newer_than:7d", max_results=20))
docs = drive.list_files(FileQuery(text="quarterly report"))
```

!!! note
    Calendar and Drive providers also take `mode=` (default `"readonly"`), which gates their write methods independently of the token. Pass `mode="standard"` to enable writes.

!!! note
    `GoogleAuth` defaults `credentials_dir` to the current working directory. Pass `~/.iobox` (expanded) to share tokens with your workspace.

### Microsoft 365

```python
from iobox.providers.o365.auth import MicrosoftAuth, get_microsoft_scopes
from iobox.providers.o365.email import OutlookProvider

auth = MicrosoftAuth(
    account="you@company.com",
    scopes=get_microsoft_scopes(["email"], "readonly"),
    credentials_dir="/Users/you/.iobox",
)
outlook = OutlookProvider(auth=auth)
```

Requires `pip install 'iobox[outlook]'` and `OUTLOOK_CLIENT_ID` in the environment.

### Factory

`iobox.providers.get_provider(name)` instantiates a provider by name with environment-based defaults, importing optional dependencies lazily:

```python
from iobox.providers import get_provider
gmail = get_provider("gmail")   # gmail | outlook | google_calendar | google_drive | outlook_calendar | onedrive
```

The return type follows the name for type checkers: `"gmail"`/`"outlook"` → `EmailProvider`, `"google_calendar"`/`"outlook_calendar"` → `CalendarProvider`, `"google_drive"`/`"onedrive"` → `FileProvider`. A name only known at runtime (a plain `str`) gives the union of the three.

## EmailProvider

| Group | Methods |
|---|---|
| Read | `search_emails(query)`, `get_email_content(message_id)`, `batch_get_emails(ids)`, `get_thread(thread_id)`, `download_attachment(message_id, attachment_id)`, `get_profile()` |
| Send & drafts | `send_message(to, subject, body, cc, bcc, content_type, attachments)`, `forward_message(message_id, to, comment)`, `create_draft(…)`, `list_drafts()`, `send_draft(id)`, `delete_draft(id)` |
| Organise | `mark_read`, `set_star`, `archive`, `trash`, `untrash`, `add_tag`, `remove_tag`, `list_tags`, `create_tag`, and `batch_*` variants |
| Sync | `get_sync_state()`, `get_new_messages(sync_token)`, `get_new_messages_with_token(sync_token)` |

Tags map to Gmail labels and Outlook categories.

## CalendarProvider

| Group | Methods |
|---|---|
| Read | `list_events(query)`, `get_event(event_id)`, `get_profile()` |
| Write | `create_event(title, start, end, *, all_day, description, location, attendees)`, `update_event(event_id, updates)`, `delete_event(event_id)`, `rsvp(event_id, response)` |
| Sync | `get_sync_state()`, `get_new_events(sync_token)` |

## FileProvider

| Group | Methods |
|---|---|
| Read | `list_files(query)`, `get_file(file_id)`, `get_file_content(file_id)` → text, `download_file(file_id)` → bytes |
| Write | `upload_file(local_path, *, parent_id, name)`, `update_file(file_id, local_path)`, `delete_file(file_id, *, permanent=False)`, `create_folder(name, *, parent_id)` |

## Return conventions

- Email write methods return `{"message_id": ..., "status": ...}` — read `message_id`, not `id`.
- Email reads return `EmailData` with the sender under **`from_`** (to avoid the Python keyword). See [Types](types.md#emaildata).
- Calendar and file writes return the resulting `Event` / `File`.

## Implementing a provider

Subclass the relevant ABC and implement every abstract method. To make it available to workspaces, wrap it in a `ProviderSlot` (see [building a workspace by hand](workspace.md#loading-a-workspace)). Per-provider behaviour differences are listed in [Provider behaviour](../reference/providers.md).
