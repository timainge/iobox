# Sprint — Life Admin feedback triage

Source: `.dev/iobox-requirements.md` (captured 2026-05-30 by an agent using the
iobox MCP while triaging 90 days of mail). Reviewed against the current code on
`main` (v0.5.0).

**Key finding:** the reporting agent was on an old / read-only build. Most of
its headline asks — apply/remove labels, send, forward, trash, mark read,
archive, calendar write, file write — **already ship**. The genuine, code-
confirmed gaps are narrower and listed below. One item (forward drops
attachments) is a real correctness bug, not a missing feature.

---

## Status (updated)

| Task | Status |
|---|---|
| 1 — Forward preserves attachments (BUG) | ✅ Done |
| 2 — Recipient headers (To/Cc/Bcc/Reply-To) | ✅ Done |
| 3 — `get_email` body-size control | ✅ Done |
| 4 — Batch header fetch (`get_emails`) | ✅ Done |
| 5 — Label list + create (nested, auto-create) | ✅ Done |
| 6 — Attachment inline-awareness | ✅ Done |
| 7 — Attachment manifest on save | ✅ Done |
| 8 — Search pagination (verify + document) | ✅ Done (optional `ids_only` deferred) |
| 9 — Self-diagnosable mode in `check_auth` | ✅ Done |

All implemented tasks ship with unit tests (mocked only — no live writes, per
`feedback_no_live_write_ops`). Outlook forward already preserved attachments via
Graph's native `msg.forward()`, so Task 1's bug was Gmail-only.

---

## A. Already implemented — no work needed (just version/permission)

These were reported as gaps but exist today. The agent likely ran in
`readonly` mode or an older release.

| Feedback item | Where it already lives |
|---|---|
| Apply/remove labels, nested-label *application* | `modify_labels`, `batch_modify_gmail_labels` (mcp_server.py:858, 903); `GmailProvider.add_tag/remove_tag` |
| Mark read/unread, archive, trash, untrash | `modify_labels` flags; `trash_gmail`/`untrash_gmail`; `GmailProvider.mark_read/archive/trash` |
| Send / forward / drafts | `send_email`, `forward_gmail`, `create_gmail_draft` + draft list/send/delete |
| Send **with attachments** | `send_email(attachments=[...])` → `compose_message` builds MIME multipart (`_sender.py:53-83`) |
| Label IDs resolved to names | `get_label_map` wired into search + get + batch (`email.py:174,196,209`) — opaque `Label_xxx` is fixed |
| Calendar create/update/delete/rsvp | `create_event`/`update_event`/`delete_event`/`rsvp_event` (mcp_server.py:1209+) |
| Filter by `label:` / `in:` in queries | passes through Gmail raw query; `EmailQuery.label` also translated (`email.py:98`) |

> Action: none beyond telling the caller to run `IOBOX_MODE=standard` (or
> `dangerous` for send/trash) on a current build. Consider surfacing the active
> mode in `check_auth` so a read-only agent self-diagnoses (see Task 9).

---

## B. Genuine gaps — sprint backlog

Priority follows the reporter's own ordering, adjusted for what's already done.

### Task 1 — Forward must preserve attachments  🔴 BUG, P0  ✅ DONE
**Shipped:** `forward_email` now fetches the source (HTML-preferred), downloads
each attachment to bytes, and `compose_forward_message` re-attaches them via the
new `attachment_blobs` path in `compose_message`; HTML bodies are preserved.
Failed attachment downloads are logged and skipped, never fatal. Outlook already
preserved attachments via Graph's native `msg.forward()`. Tests in
`test_email_sender.py::TestForwardPreservesAttachments`.

**Problem:** `compose_forward_message` (`_sender.py:101-141`) rebuilds only the
text body of the original — `From/Date/Subject` + body string. **All
attachments are silently dropped.** This directly defeats the reporter's #3
ask (receipts → Hubdoc) and is a correctness bug regardless of feature scope.

**Fix:**
- Re-fetch the source message, download each real attachment, and re-attach
  them to the forwarded MIME message (reuse the attach loop in
  `compose_message`). Simplest correct path: download attachments to bytes and
  build `MIMEBase` parts inline rather than from disk.
- Preserve original HTML body when present (current forward is plain-text only).
- Consider the cleaner Gmail-native route: `messages().get(format='raw')` →
  rewrap headers → send, which preserves attachments and inline parts verbatim.
  Prefer this if it doesn't complicate the prepended note.

**Acceptance:** forwarding a message with a PDF delivers the PDF; unit test with
a mocked multipart source asserting attachment parts survive. Add a live-test
note (do **not** run live sends — see memory `feedback_no_live_write_ops`).

**Files:** `providers/google/_sender.py`, `tests/unit/` (+ Outlook parity check
in `providers/o365/email.py`).

---

### Task 2 — Surface recipient headers (To/Cc/Bcc/Reply-To)  🟠 P1  ✅ DONE
**Shipped:** `to/cc/bcc/reply_to` added to `EmailData` and extracted in full
retrieval (`_process_message_response`), search metadata (`batch_get_metadata`,
with the headers requested in `metadataHeaders`), the thread path, and the
Outlook provider. Carried through `_to_email_data`; surfaced in `get_email`,
`search_gmail`, single-email frontmatter (`cc`/`reply_to`), and per-message
thread sections (**To:**/**Cc:**). Tests:
`test_email_retrieval.py::TestRecipientHeaders`,
`test_email_search.py::test_batch_get_metadata_extracts_recipients`.

**Problem:** `_process_message_response` (`_retrieval.py:76-88`) and
`batch_get_metadata` (`_search.py:79-89`) extract only `Subject/From/Date`.
`EmailMetadata` (`base.py:31-41`) has no `to`/`cc`/`reply_to`. The reporter
couldn't recover a forwarding address from past `Fwd:` messages, and triage
can't see who a thread went to.

**Fix:**
- Add `to`, `cc`, `bcc`, `reply_to` to the header extraction in both retrieval
  and batch-metadata paths (request the headers in `metadataHeaders`).
- Add the fields to `EmailMetadata` and carry them through `_to_email_data`
  (`email.py:118-126`) and the `_email_data_to_dict` shim (mcp_server.py:178).
- Thread path (`get_thread_content`, `_retrieval.py:243`) already pulls `to`;
  add `cc` and ensure per-message participants flow through `save_thread`.

**Acceptance:** `get_email` and `search_gmail` rows include `to`/`cc`;
`save_thread` frontmatter lists participants. Update the EmailData invariant note
in CLAUDE.md if the `from_`/`from` shim grows to cover new keys.

**Files:** `_retrieval.py`, `_search.py`, `base.py`, `email.py`, `mcp_server.py`,
`processing/markdown_converter.py` (thread participant block), tests.

---

### Task 3 — `get_email` body-size control  🟠 P1  ✅ DONE
**Shipped:** `get_email` now takes `body="none"|"text"|"html"|"markdown"`
(default `markdown`) and `max_body_chars`. `markdown` renders HTML via
`convert_html_to_markdown`; `none` drops the body; truncation adds a
`truncated: true` flag and `...[truncated N chars]` marker. `prefer_html` kept
as a deprecated alias. Logic factored into `_apply_body_mode` (shared with
`get_emails`). Tests in `test_mcp_server.py::TestGetEmail`.

**Problem:** `get_email` (mcp_server.py:263) only takes `prefer_html: bool` and
returns the full body. A single 60k-char HTML email blew the tool token budget,
making the message unreadable. No truncation, no text/markdown coercion.

**Fix:**
- Replace/augment `prefer_html` with `body: "none" | "text" | "html" | "markdown"`
  (default `"markdown"` or `"text"`). `markdown` reuses
  `convert_email_to_markdown`. `none` returns headers + attachment manifest only.
- Add `max_body_chars: int | None` server-side truncation with a clear
  `"...[truncated N chars]"` marker and a `truncated: true` flag in the result.
- Keep `prefer_html` working as a deprecated alias for one release.

**Acceptance:** `get_email(message_id, body="none")` returns no body;
`body="markdown"` returns converted text; oversized bodies truncate and flag.

**Files:** `mcp_server.py` (`get_email`), tests.

---

### Task 4 — Metadata-only + batch header fetch tools  🟡 P2  ✅ DONE
**Shipped:** new `get_emails(message_ids, body="none", max_body_chars, ...)` MCP
tool routes to `provider.batch_get_emails`, applies the Task 3 body modes per
message, and propagates per-message `error` rows. Registered in `_READONLY_MCP`.
Tests in `test_mcp_server.py::TestGetEmails`.

**Problem:** No way to scan N messages' headers in one call. The provider
already has `batch_get_emails` (`email.py:205`) and `batch_get_metadata`
(`_search.py:25`) but **neither is exposed as an MCP tool**. Triage is forced
one-at-a-time.

**Fix:**
- Add `get_emails(message_ids: list[str], body="none"|"text"|..., provider, workspace)`
  MCP tool routing to `provider.batch_get_emails` (or a new metadata-only batch
  when `body="none"`).
- Wire into `_READONLY_MCP` in `modes.py`.

**Acceptance:** one call returns headers (subject/from/to/cc/date/labels/
attachment manifest) for a list of IDs; honours the Task 3 `body` modes.

**Files:** `mcp_server.py`, `modes.py`, tests.

---

### Task 5 — Label management: list + create (incl. nested)  🟡 P2  ✅ DONE
**Shipped:** `_retrieval.create_label` (Gmail `labels().create`, nested via `/`,
409→returns existing, refreshes cache); `EmailProvider.create_tag` (default
`NotImplementedError`) implemented on Gmail and Outlook (free-form master
category). `GmailProvider.add_tag` now **auto-creates** a missing label so a new
bucket applies in one call. New MCP tools `list_labels` (readonly) and
`create_label` (standard). Tests across `test_email_retrieval.py::TestCreateLabel`,
`test_gmail_provider.py::TestTagOperations`,
`test_mcp_server.py::TestLabelDiscovery`.

**Problem:**
- `list_tags()` exists on the provider (`email.py:340`) but **no MCP tool**
  exposes it — callers can't enumerate available labels.
- `add_tag` → `resolve_label_name` **raises `ValueError` for unknown labels**
  (`_retrieval.py:327`). A new nested bucket like
  `LifeAdmin/property/7-leslie-st` can't be applied because it can't be created.

**Fix:**
- Add `list_labels(provider, workspace)` MCP tool → `provider.list_tags()`
  (readonly tier).
- Add a `create_label` provider method (Gmail `labels().create`, nested via
  `/`-delimited name) and a `create_label` MCP tool (standard tier).
- Make `add_tag` optionally auto-create a missing label (flag, default off) or
  document the create-then-apply flow.

**Acceptance:** can list labels by name, create `A/B/C`, then apply it. Outlook
parity = categories (note OneNote-style nesting isn't supported — log/skip).

**Files:** `_retrieval.py`, `email.py`, `o365/email.py`, `mcp_server.py`,
`modes.py`, tests.

---

### Task 6 — Attachment inline-awareness  🟡 P2  ✅ DONE
**Shipped:** `AttachmentInfo` gained optional `inline: bool` / `content_id`.
`_find_attachments` reads `Content-Disposition` and `Content-ID` (inline when
dispositioned inline, or cid-referenced with no disposition); Outlook reads
`is_inline`/`content_id`. `download_email_attachments` skips inline by default
(`include_inline=True` to keep) and returns a `saved` manifest. Tests:
`test_email_retrieval.py::TestInlineAttachments`,
`test_file_manager.py::test_inline_attachments_*`.

**Problem:** `_find_attachments` (`_retrieval.py:394-420`) returns
`id/filename/mime_type/size` but no inline flag, so signature logos
(`image001.png`) mix with real documents. `AttachmentInfo` (`base.py:24-28`)
has no `inline`/`content_id`.

**Fix:**
- Extract `Content-Disposition` (inline vs attachment) and `Content-ID` from
  each part; add `inline: bool` and `content_id: str | None` to
  `AttachmentInfo` and the finder.
- Let `download_attachments`/`save_email` skip inline parts by default (flag to
  include them).

**Acceptance:** `get_email` attachment list flags inline parts;
`save_email(download_attachments=True)` skips inline cruft unless opted in.

**Files:** `_retrieval.py`, `base.py`, `email.py`, `processing/file_manager.py`,
`mcp_server.py`, tests.

---

### Task 7 — Attachment manifest on save  🟢 P3  ✅ DONE
**Shipped:** `save_email` now returns `{markdown_path, attachments: [{filename,
path, inline, mime_type, size}]}` (was a bare filepath string) and accepts
`include_inline`; `save_emails_by_query` also passes `include_inline`. The
`<output_dir>/attachments/{message_id}/` layout + manifest are documented in
CLAUDE.md. Tests in `test_mcp_server.py::TestSaveEmail`.

**Problem:** `save_email(download_attachments=True)` returns only the markdown
filepath. Callers must `find` the `attachments/<message_id>/` tree afterward.
The path contract is also undocumented.

**Fix:**
- Return a manifest: `{markdown_path, attachments: [{filename, path, inline,
  mime_type, size}]}` from `save_email` and `save_emails_by_query`.
- Document the `<output_dir>/attachments/<message_id>/` layout in CLAUDE.md
  (File Output Format section).

**Files:** `mcp_server.py`, `processing/file_manager.py`, CLAUDE.md, tests.

---

### Task 8 — Search pagination ergonomics  🟢 P3 (verify first)  ✅ DONE
**Shipped:** confirmed the stub-row symptom is gone on `main`; added a 60-row
regression test asserting every row is fully populated, plus the existing
partial-failure test confirms failures surface as explicit `error` rows.
Documented `days` vs `start_date`/`end_date` precedence in the `search_gmail`
docstring. The optional `ids_only` mode was **deferred** (would require threading
a flag through `EmailQuery` → provider → `_search`; not needed now that rows are
reliable). Tests:
`test_email_search.py::test_large_window_all_rows_fully_populated`.

**Problem reported:** past ~30 enriched results, rows came back as stubs with
empty `subject/date/from/labels`; early-March never surfaced.

**Current state:** `search_emails` paginates internally up to `max_results` and
fills every row via `batch_get_metadata` (chunks of 50). The stub-row symptom
**appears already fixed** on `main` — likely an old-build artifact.

**Fix (scoped to what's left):**
- Add a regression test: 60-result window returns 60 fully-populated rows (no
  empty metadata), and verify partial batch failures surface as explicit
  `error` rows rather than silent stubs.
- Document `days` vs `start_date`/`end_date` precedence in the `search_gmail`
  docstring (start_date overrides days; end_date independent; full coverage up
  to `max_results`).
- Optional: `ids_only: bool` mode that's honest about returning ID-only rows
  cheaply for very large windows.

**Files:** `_search.py` (doc only), `mcp_server.py` (docstring/optional flag),
tests.

---

### Task 9 — Self-diagnosable mode (small DX win)  🟢 P3  ✅ DONE
**Shipped:** `check_auth` now reports `mode`, `available_write_ops`,
`available_send_ops`, and a `mode_hint` when read-only — so a constrained agent
can tell why writes are absent and how to elevate. Tests:
`test_mcp_server.py::TestCheckAuth::test_check_auth_reports_*`.

**Problem:** the entire false-gap report stems from the agent not knowing it was
in `readonly` mode. `check_auth` doesn't report the active mode or the toolset.

**Fix:** add `mode` and `available_write_ops: bool` to `check_auth` /
`workspace_auth_status` output so a constrained agent can tell why writes are
absent and how to elevate (`IOBOX_MODE=standard`).

**Files:** `mcp_server.py`, `modes.py`, tests.

---

## C. Out of scope / confirmed done
- **Calendar write** (reporter §6): fully implemented and CLI-exercised.
- **Label IDs → names** (reporter §6): wired via `label_map` on all read paths.

## Suggested order
1. Task 1 (forward attachments — bug)
2. Task 2 (recipient headers)
3. Task 3 (get_email body size)
4. Tasks 4–6 (batch headers, label list/create, inline flags)
5. Tasks 7–9 (manifest, search docs/regression, mode self-report)

Tasks 1–3 unblock the reporter's stated workflow (receipts automation + triage).
All write-path testing must respect `feedback_no_live_write_ops` — unit/mocked
only, no live sends/forwards/trash against real accounts.
