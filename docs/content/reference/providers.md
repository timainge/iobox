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

- **Searches every folder** (`/me/messages`: Inbox, Sent, Archive, custom folders — and also Deleted Items and Junk, since `include_spam_trash` isn't applied for Outlook yet).
- **Query syntax** is Microsoft Graph `$search` (KQL). Structured filters (from, to, dates, attachments) use `$filter`; Graph can't combine `$search` with `$filter`/`$orderby`, so when both are needed unread/category filters and ordering are applied client-side.
- **Message IDs are ImmutableIds** (`Prefer: IdType="ImmutableId"` on every Graph request), stable across folder moves.
- **Categories** map to iobox tags.
- **Incremental sync** (SDK `get_sync_state()` / `get_new_messages()`) uses a Graph delta link on the Inbox; an expired delta link triggers a full re-sync. `iobox save --sync` uses the provider-neutral query window instead.
- New drafts larger than about 3 MB with attachments may fail (the library only uploads large attachments in chunks to existing drafts).

| Mode | Scopes |
|---|---|
| read-only | `Mail.Read` |
| read-write | `Mail.ReadWrite`, `Mail.Send` |

## Outlook Calendar

- Lists the default calendar's events in a date window (default: now to one year ahead), with recurring events expanded.
- **Text search is done client-side** over the window — Graph doesn't support `$search` on events.
- Incremental event sync is not implemented.

| Mode | Scopes |
|---|---|
| read-only | `Calendars.Read` |
| read-write | `Calendars.ReadWrite` |

## OneDrive

- `delete_file` sends items to the OneDrive recycle bin; `permanent=True` deletes permanently (Graph `permanentDelete`, available on OneDrive for Business and SharePoint only).
- Not yet addable via `iobox space add`; available through the [SDK](../sdk/providers.md).

| Mode | Scopes |
|---|---|
| read-only | `Files.Read.All` |
| read-write | `Files.ReadWrite.All` |

## Microsoft 365 tokens

Tokens are stored per account and tier at `~/.iobox/tokens/ACCOUNT/microsoft_token_{readonly|standard}.txt` (0600). A read-only session never reuses a read-write token. Tokens from older iobox versions (`microsoft_token.txt`, `o365_token.txt`) are migrated into the `standard` tier on first use.

!!! warning
    Microsoft 365 providers are verified against the real python-o365 library, but have not yet been tested end-to-end against a real tenant.
