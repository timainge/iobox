# Issues Register

Findings from the full code review on 2026-10-31 (six parallel reviewers, findings reproduced against mocks or confirmed by reading; Microsoft 365 findings checked against O365 2.1.9 source).

**Status:** `open` · `in-progress` · `fixed` (commit) · `wontfix` (reason) · `deferred` (reason)
**Severity:** `crit` · `high` · `med` · `low`
**Owner:** work package that fixes it — see [Work packages](#work-packages).

## Security

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| SEC-01 | crit | `mcp_server.py` `download_email_attachment`, `download_file` | Readonly tools write model-supplied bytes to any path (mkdir parents, overwrite) | WP-MCP | fixed (546e044) |
| SEC-02 | crit | `modes.py` `_STANDARD_MCP` | `send_gmail_draft` in standard mode lets standard send any mail; contradicts `check_auth` | WP-MCP | fixed (c03c07c, 8287896) |
| SEC-03 | crit | `mcp_server.py` `create_gmail_draft`, `send_email` attachments | Any readable local file (incl. token files) can be attached | WP-MCP | fixed (546e044) |
| SEC-04 | high | `mcp_server.py` `upload_file` | Any readable local file can be uploaded to a model-chosen folder | WP-MCP | fixed (546e044) |
| SEC-05 | high | `mcp_server.py` `_default_workspace_fn`, `_resolve_email_provider` | Misspelled/unloadable `workspace=` silently falls back to legacy Gmail, including for writes | WP-MCP | fixed (473a3a5) |
| SEC-06 | high | `mcp_server.py` batch tools | `batch_trash/forward/modify` unbounded `max_results`, empty query, `days=0` → whole mailbox | WP-MCP | fixed (cf69e02) |
| SEC-07 | high | `providers/token_store.py`, `google/auth.py`, `o365/auth.py` | Token files (refresh tokens, client secret) written 0644; dirs not 0700 | WP-GOOG (+WP-O365 for O365 backend) | fixed (d153727, 3741001, df7a151) |
| SEC-08 | high | `cli.py` mode gate, `modes.py` `_READONLY_CLI` | `--mode readonly` doesn't gate `events`/`files` write subcommands (`events delete` works in readonly) | WP-CLI | fixed (1bed297) |
| SEC-09 | med | `space_config.py`, `google/auth.py`, `embed.py` | Workspace names / account strings used in paths unvalidated (`space create ../../x`, MCP `workspace=`) | WP-WS | fixed (d148ef4, f3e2b2c) |
| SEC-10 | med | `google/files.py` `list_files` | Drive `q` escapes `'` but not `\`; `mime_type`/`folder_id` unescaped → query breakout | WP-GOOG | fixed (5fb14e7) |
| SEC-11 | med | `space_config.py` `_parse_space_config` | Unvalidated `mode` in TOML; any non-`readonly` value gets read-write scopes | WP-WS | fixed (d148ef4) |
| SEC-12 | low | `processing/file_manager.py` `create_attachments_directory` | `message_id` joined into path unsanitised | WP-PROC | fixed (8220a22) |

## Data correctness

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| DATA-01 | high | `processing/markdown_converter.py` `generate_yaml_frontmatter`, thread variant | Hand-built YAML: `Re:` subjects invalid, type coercion, key injection via newlines | WP-PROC | fixed (35a81bb, 900a3fa) |
| DATA-02 | high | `workspace.py` `search_emails`, `search`, `list_events` | Sorts on raw date strings (RFC 2822 vs ISO, mixed offsets) → wrong order | WP-WS | fixed (83213d9) |
| DATA-03 | high | `google/_sender.py`, `google/email.py` | Gmail write ops return raw API dicts, not `{"message_id","status"}` → "Draft ID: unknown" | WP-GOOG | fixed (6e6550f) |
| DATA-04 | high | `google/_retrieval.py` label cache | Module-global label cache shared across accounts and never refreshed | WP-GOOG | fixed (df51de4) |
| DATA-05 | high | `google/_retrieval.py` body decode | Bodies always decoded UTF-8; non-UTF-8 aborts entire batch | WP-GOOG | fixed (66ce428) |
| DATA-06 | med | `utils.py` `create_markdown_filename` | Date prefix falls back to today for 1-digit days, ISO (Outlook) dates, no-weekday dates | WP-PROC | fixed (d1321f2) |
| DATA-07 | high | `google/auth.py` `GoogleAuth.get_credentials` | Cached token not checked for scope coverage; scope additions silently 403 | WP-GOOG | fixed (d153727) |
| DATA-08 | med | `google/auth.py` | `RefreshError` (revoked/expired refresh token) not handled; user must delete token by hand | WP-GOOG | fixed (d153727, 3741001) |
| DATA-09 | med | `google/_retrieval.py` | Multipart bodies: later same-type parts overwrite earlier ones | WP-GOOG | fixed (66ce428) |
| DATA-10 | med | `google/_sender.py` | Non-ASCII attachment filenames / address display names mis-encoded | WP-GOOG | fixed (6c244b7) |
| DATA-11 | low | `google/_sender.py` forward | HTML forward header/plain original not escaped; inline images lose Content-ID | WP-GOOG | fixed (6c244b7) |
| DATA-12 | med | `processing/markdown.py` `convert_resource_to_markdown` | Email resources render `from: Unknown`, `No Subject` (key mismatch) | WP-PROC | fixed (d12df92) |
| DATA-13 | low | `utils.py` | `None`/empty/symbol-only subject → crash or `DATE-.md` | WP-PROC | fixed (d1321f2) |
| DATA-14 | low | `processing/file_manager.py` `sanitize_filename` | Char not byte length; long ext; `.`/`..`; multi-ext Windows reserved names | WP-PROC | fixed (8220a22) |
| DATA-15 | low | `processing/file_manager.py` attachment filter | Extensionless attachments bypass `--types` filter | WP-PROC | fixed (ebed578) |

## Calendar & time

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| TIME-01 | med | `google/calendar.py` `_to_rfc3339`, `cli.py` `_parse_dates` | End dates exclusive and UTC-midnight; offset-less datetimes rejected by Google | WP-GOOG + WP-CLI | fixed (2c9abf5, e621dd8) |
| TIME-02 | med | `google/calendar.py` `create_event` | Hard-coded `timeZone: "UTC"` → 9am becomes 8pm AEDT | WP-GOOG | fixed (2c9abf5) |
| TIME-03 | med | `google/calendar.py` `update_event` | Passes normalised keys (`title`, string `start`) straight to `events.patch` | WP-GOOG | fixed (2c9abf5) |
| TIME-04 | low | `workspace.py` `search` | Event text search has no `after` → returns oldest matches | WP-WS | fixed (1ed01ca) |
| TIME-05 | low | `google/calendar.py` | get/update/delete/rsvp hard-code `calendarId="primary"`; not-found raises HttpError not KeyError | WP-GOOG | fixed (2c9abf5, 5fb14e7) |

## Sync

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| SYNC-01 | high | `cli.py` `save --sync` | After first run ignores `--query`/date range; saves every new mailbox message | WP-SYNC | fixed (951ca85) |
| SYNC-02 | med | `cli.py`, `mcp_server.py`, `google/_search.py` | Cursor taken after processing → mail in between lost; failed IDs advance cursor | WP-SYNC | fixed (951ca85) |
| SYNC-03 | med | `processing/file_manager.py` `SyncState.save` | Non-atomic write; corrupt state raises on every later run | WP-PROC | fixed (48f7ade) |
| SYNC-04 | med | `mcp_server.py` `save_emails_by_query` | Sync cursor from legacy default Gmail, not the selected slot; breaks Outlook | WP-SYNC | fixed (951ca85) |
| SYNC-05 | high | `google/calendar.py` `get_sync_state`, `get_new_events` | `maxResults=1` never yields `nextSyncToken`; single page; no 410 handling | WP-GOOG | fixed (2c9abf5) |

## Workspace & config

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| WS-01 | med | `workspace.py` `_fan_out` | Per-slot failures recorded but never surfaced; partial results look complete | WP-WS (+WP-XC for CLI/MCP display) | fixed (1ed01ca, dbc98bf) |
| WS-02 | med | `workspace.py` | Results not tagged with slot; fetch-by-ID after fan-out hits wrong account | WP-WS (+WP-XC) | fixed (1ed01ca, dbc98bf, 6900660) |
| WS-03 | med | `workspace.py` | `max_results` per slot, never capped on merged list | WP-WS | fixed (1ed01ca) |
| WS-04 | med | `space_config.py` `_derive_slug`, `cli.py` `space add` | Slug collisions (`tim@gmail.com` / `tim@gmail.co.uk`); same account addable twice | WP-WS + WP-CLI | fixed (8107a46, 780ddab, f3e2b2c) |
| WS-05 | med | `space_config.py` `save_space` | Saves to `config.name` from TOML, not filename → copied file overwrites original | WP-WS | fixed (b26a401) |
| WS-06 | med | `google/auth.py` `GoogleAuth` | Shared auth across concurrent fan-out threads; no lock; non-atomic token write | WP-GOOG | fixed (d153727) |
| WS-07 | low | `workspace.py` `_email_data_to_resource` | `to`/`cc` strings not lists; `provider_id` always empty | WP-WS | fixed (1ed01ca) |
| WS-08 | low | `workspace.py`, `space_config.py` | Dead session code (`auth_status`, `_check_write_mode`, `save_session` never called) | WP-WS | fixed (1ed01ca, dbc98bf) |
| WS-09 | low | `space_config.py`, `cli.py` | Missing TOML keys → bare KeyError; non-atomic writes; deleted active space → traceback | WP-WS | fixed (b26a401, f3e2b2c) |
| WS-10 | low | `providers/__init__.py` | `get_provider` typed as returning `EmailProvider` for calendar/file names | WP-WS | fixed (3512ba3) |

## MCP behaviour

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| MCP-01 | med | batch tools | One failure aborts batch; caller can't tell what already happened | WP-MCP | fixed (cf69e02) |
| MCP-02 | low | `check_auth`, sync paths | Legacy `get_gmail_service()` can start interactive OAuth inside the server | WP-MCP | fixed (6e73244, 02bea56, f61c8a4) |
| MCP-03 | low | `get_emails` | Outlook drops missing IDs; results misalign; one exception aborts batch | WP-MCP | fixed (f64333e) |
| MCP-04 | low | `save_email`, `save_thread` | `include_spam_trash` / `prefer_html` accepted but unused | WP-MCP | fixed (2b1cf13) |
| MCP-05 | low | `_get_workspace` | `TypeError` retry silently swaps named workspace for active | WP-MCP | fixed (473a3a5) |
| MCP-06 | med | `semantic_search_workspace` | Index is never populated by anything → always `[]` | WP-PROC (decision) | fixed (3f8fe29) — clear error when nothing is indexed; an index-building CLI/MCP command is deferred (embed_resources is SDK-only) |

## CLI behaviour

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| CLI-01 | med | `forward` (batch) | No confirmation; partial failure unreported | WP-CLI | fixed (f8e8d0e) |
| CLI-02 | med | `trash --untrash` (batch) | Never finds trashed mail (`include_spam_trash=False`) | WP-CLI | fixed (7c00ecb) |
| CLI-03 | low | `label` (batch) | No op flags → reports success; contradictory flags accepted | WP-CLI | fixed (acced93) |
| CLI-04 | low | `events save`, `files save` | Filename from title only → silent overwrite; empty title → `.md` | WP-CLI | fixed (cc12ed2, 4954d20) |
| CLI-05 | low | `auth-status` | Can launch interactive OAuth; swallows errors | WP-CLI | fixed (d2c263e) |
| CLI-06 | low | `save`, `forward`, `send`, `draft-create`, `label` | `typer.Exit` caught by `except Exception` → garbled error line | WP-CLI | fixed (da20d17) |

## Processing / semantic search

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| PROC-01 | high | `embed.py` | Index dimension fixed at creation; hash ignores backend → switching backends breaks index | WP-PROC | fixed (8b2553e) |
| PROC-02 | high | `embed.py` `LocalEmbeddingBackend` | numpy float32 not JSON serialisable → local backend always fails | WP-PROC | fixed (8b2553e) |
| PROC-03 | med | `embed.py` `VoyageEmbeddingBackend` | Declares 1024 dims; `voyage-3-lite` is 512 | WP-PROC | fixed (8b2553e) |
| PROC-04 | med | `embed.py` | Rows written without sqlite-vec never backfilled; partial-failure leaves stale hash | WP-PROC | fixed (8b2553e) |
| PROC-05 | med | `embed.py` | vec0 L2 vs fallback cosine → inconsistent scores | WP-PROC | fixed (8b2553e) |
| PROC-06 | low | `file_manager.py`, `markdown_converter.py` | `logging.basicConfig` at import | WP-PROC | fixed (50f46c3, 16f2b86) |

## Microsoft 365 (not usable against a real tenant)

| ID | Sev | Location | Issue | Owner | Status |
|---|---|---|---|---|---|
| O365-01 | crit | `o365/email.py` `_set_immutable_id_header` | `con.session` is None before first request → every Outlook call fails; calendar/files never set header | WP-O365 | fixed (df7a151, 84dde40) — needs live-tenant verification |
| O365-02 | crit | `o365/calendar.py` `list_events` | `get_events` takes `start_recurring/end_recurring`; `Schedule.search_events` doesn't exist | WP-O365 | fixed (a4db471) — needs live-tenant verification |
| O365-03 | crit | `o365/calendar.py` | `Schedule.get_event`, `Event.accept/decline/tentatively_accept` don't exist | WP-O365 | fixed (a4db471) — needs live-tenant verification |
| O365-04 | crit | `o365/email.py` query building | O365 2.1 `QueryBuilder` has no `on_attribute`/`as_params`; invalid OData for to/categories | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-05 | high | `o365/email.py` `$search` | `QueryBuilder.search` quotes the whole KQL → field filters become phrase search | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-06 | crit | `o365/auth.py` | `authenticate(scopes=)` ignored (param is `requested_scopes`) → all 24 default scopes, readonly not enforced; device code ignored | WP-O365 | fixed (df7a151) — needs live-tenant verification |
| O365-07 | high | `o365/email.py` attachments | Attachments never downloaded; content is base64 str, not bytes | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-08 | med | `o365/email.py` `set_star` | `Message.flag` is read-only | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-09 | med | `o365/files.py` | Wrong DriveItem attrs (`parent`, `created_datetime`), `Folder.mkdir` missing | WP-O365 | fixed (818202e) — needs live-tenant verification |
| O365-10 | med | `o365/calendar.py` conversion | location dict, body str, attendee status object mis-read → fields always None | WP-O365 | fixed (a4db471) — needs live-tenant verification |
| O365-11 | med | `o365/email.py` delta sync | 410 raises HTTPError (never `_DeltaGoneError`); `@removed` counted as new | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-12 | med | `o365/auth.py` | One token per account regardless of mode/scopes; no scope-coverage check | WP-O365 | fixed (df7a151, f61c8a4) — needs live-tenant verification |
| O365-13 | med | `o365/email.py` `$batch` | Per-item failures ignored; `//` double-slash URLs | WP-O365 | fixed (84dde40) — needs live-tenant verification |
| O365-14 | low | `o365/email.py` | `contentType` case compare; `send` returns `"sent_message"` id; `update_event` raw keys; OneDrive `permanent` ignored | WP-O365 | fixed (84dde40, a4db471, 818202e) — needs live-tenant verification |

## Work packages

Packages own disjoint files so they can run in parallel. Cross-cutting items are done after the parallel packages are merged.

| Package | Owns | Issues |
|---|---|---|
| WP-MCP | `mcp_server.py`, `modes.py` (MCP allowlists) | SEC-01–06, MCP-01–05 |
| WP-GOOG | `providers/google/*`, `providers/token_store.py` | SEC-07 (store), SEC-10, DATA-03–05, 07–11, TIME-01 (provider side), TIME-02/03/05, SYNC-05, WS-06 |
| WP-PROC | `processing/*`, `utils.py` | SEC-12, DATA-01, 06, 12–15, SYNC-03, PROC-01–06, MCP-06 decision |
| WP-WS | `workspace.py`, `space_config.py`, `providers/base.py`, `providers/__init__.py` | SEC-09, SEC-11, DATA-02, TIME-04, WS-01–05, 07–10 |
| WP-O365 | `providers/o365/*` | O365-01–14, SEC-07 (O365 backend) |
| WP-CLI | `cli.py`, `modes.py` (CLI sets) | SEC-08, CLI-01–06, TIME-01 (CLI side), WS-04 (CLI side) |
| WP-SYNC / WP-XC | cross-cutting, after merge | SYNC-01, 02, 04; WS-01/02 surfacing in CLI and MCP |

## Follow-ups found while fixing

| ID | Sev | Location | Issue | Status |
|---|---|---|---|---|
| FU-01 | med | `pyproject.toml` pytest config | `log_cli = true` closed click CliRunner's output for any CLI test that logs | fixed (16f2b86) |
| FU-02 | med | `modes.py` `_STANDARD_CLI` | CLI `draft-send` allowed in standard mode (sends mail) — aligned with MCP | fixed (8287896) |
| FU-03 | low | `cli.py` `space status` | Reads `load_session()` error column, but nothing ever writes a session file | open |
| FU-04 | low | `google/_retrieval.py` | Read paths don't refetch labels for unknown label IDs (new labels show as raw IDs in long-lived MCP) | open |
| FU-05 | low | `google/_sender.py` | HTML email with attachments sends raw HTML as the text/plain alternative | open |
| FU-06 | low | `cli.py` mode gate | `--help` on a blocked subcommand prints the mode error instead of help | open |
| FU-07 | low | `space_config.validate_account` | Rejects any account containing `..`, so `a..b@x.com` can't be added | open |
| FU-08 | low | `workspace.search` | Event results in cross-type search sorted by `created_at`, not start time | open |
| FU-09 | med | — | No CLI/MCP command builds the semantic index (`embed_resources` is SDK-only) | deferred (feature) |
| FU-10 | med | `pyproject.toml`, CI | O365/MCP tests skipped without the libraries; CI installed only `.[dev]` | fixed (a16dd98) |
| FU-11 | med | `o365/email.py` search | `include_spam_trash` ignored for Outlook → Deleted Items and Junk always included | open |
| FU-12 | low | `o365/email.py` attachments | Listing attachments also downloads their content (slow for large files) | open |
| FU-13 | low | `o365/email.py` drafts | New drafts > ~3 MB with attachments fail (library chunks uploads only for existing drafts) | open |
| FU-14 | low | `o365/email.py` `$batch` | Throttled (429) batch items reported as failures, not retried | open |
| FU-15 | med | O365 providers | Live-tenant checks: KQL quoting/`hasAttachments:`, `any()` filters vs InefficientFilter, draft ImmutableId after send, public-client app setup, granted-scope format, calendarView `$orderby`, `permanentDelete` | open (needs M365 dev tenant) |

## Previously fixed (2026-10-31, branch `docs-restructure-and-fixes`)

| Issue | Commit |
|---|---|
| Workspace Google Calendar/Drive providers ignored session mode | `78bd778` |
| `space add` o365 token written where workspace never read it | `d0c0906` |
| `check_for_duplicates` never matched saved files | `ca08290` |
| `draft-create --attach` ignored; MCP draft attachments TypeError | `43ac4b4` |
| Outlook ignored `--account` | `aa005d8` |
| `space add --drive` help/error text; stale CLAUDE.md examples | `0a7c8d7` |
| Global `--provider` instantiated for every command; mode hint always "dangerous" | `760ca6e` |
