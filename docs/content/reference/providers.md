# Provider Behaviour

iobox normalises results across providers, but the underlying services differ. This page lists the differences that affect what you get back.

## Gmail

- **Searches all mail**, not just the inbox. Use `in:inbox` to narrow.
- **Query syntax** is native [Gmail search](https://support.google.com/mail/answer/7190) (`from:`, `has:attachment`, `newer_than:7d`, `label:`, …).
- **Labels** map to iobox tags. Nested labels use `/` (`Clients/Acme`).
- Rate-limited batch fetches are retried automatically.

| Mode | Scopes |
|---|---|
| read-only | `gmail.readonly` |
| read-write | `gmail.modify`, `gmail.compose` |

## Google Calendar

- Events come from the **primary calendar** only.
- All-day events use a `date` (`2026-04-01`); timed events use an ISO datetime.
- `meeting_url` is taken from the Google Meet link or the conference entry points.
- Incremental sync is available in the SDK via `get_sync_state()` / `get_new_events(token)`.

| Mode | Scope |
|---|---|
| read-only | `calendar.readonly` |
| read-write | `calendar` |

## Google Drive

- Lists files in **My Drive** (`corpora=user`); trashed files are excluded.
- `delete_file` moves to trash by default; `permanent=True` deletes immediately.
- Text extraction:

| Type | Content returned |
|---|---|
| `text/*` | Downloaded as-is |
| Google Docs | Exported as plain text |
| Google Sheets | Exported as CSV |
| Google Slides | Exported as plain text |
| Other binary files | Metadata only — use `download_file` for the bytes |

| Mode | Scope |
|---|---|
| read-only | `drive.readonly` |
| read-write | `drive` |

## Outlook

- **Searches the Inbox only.** Messages in Sent, Archive, or custom folders may not be returned.
- **Query syntax** is passed to Microsoft Graph `$search` (KQL).
- **Message IDs are ImmutableIds** (`Prefer: IdType="ImmutableId"`), stable across folder moves.
- **Categories** map to iobox tags.
- Incremental sync is not implemented.

| Mode | Scopes |
|---|---|
| read-only | `Mail.Read` |
| read-write | `Mail.ReadWrite`, `Mail.Send` |

## Outlook Calendar

- Incremental event sync is not implemented.

| Mode | Scopes |
|---|---|
| read-only | `Calendars.Read` |
| read-write | `Calendars.ReadWrite` |

## OneDrive

- **Deletion is always permanent** — there's no trash API via the `O365` library.
- Not yet addable via `iobox space add`; available through the [SDK](../sdk/providers.md).

| Mode | Scopes |
|---|---|
| read-only | `Files.Read.All` |
| read-write | `Files.ReadWrite.All` |

!!! warning
    Microsoft 365 providers have not yet been tested against a real tenant.
