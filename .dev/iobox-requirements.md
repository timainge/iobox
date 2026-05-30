# iobox — requirements / gaps hit building Life Admin

Context: triaging 90 days of mail across two Gmail accounts (`tim.ainge-gmail`, `tim-goodcollective`), saving important threads to disk with metadata, and wanting to push classification back into Gmail. Captured 2026-05-30.

## 1. Write / mutate Gmail (biggest gap — iobox is read-only)

- **Apply & remove labels.** `label_message`, `label_thread`, `unlabel_*`, `create_label`, `list_labels`, nested labels (e.g. `LifeAdmin/property/7-leslie-st`). This is the #1 ask — it lets the bucket taxonomy live natively in Gmail instead of only in `meta.yaml`. (Currently only doable via a *separate* Gmail connector.)
- **Send / forward email, with attachments.** Needed to automate receipts→Hubdoc. Specifically: forward an existing message **preserving its attachments** to a target address. The other available Gmail connector can only create drafts and *cannot attach files*, so this is blocked everywhere right now.
- **Mark read/unread, archive, trash, move.** So triage state in the system can be written back.

## 2. Read-side data exposure

- **Expose recipient headers: `To`, `Cc`, `Bcc`, `Reply-To`.** `search_gmail` and `get_email` only return `from` (+ subject/date/snippet). I could not recover Tim's Hubdoc forwarding address from past `Fwd:` sent messages because the destination is never surfaced. Recipients are also needed to know who a thread actually went to.
- **Thread participant list.** `save_thread`/`get_thread` should return the full set of participants and per-message to/from.

## 3. Search reliability

- **Pagination is broken for large windows.** Past ~30 enriched results, `search_gmail` returns stub rows with a `message_id` but empty `subject/date/from/labels`. Net effect: I couldn't reliably page a 90-day window — early March (1–8) never surfaced. Need real pagination (page tokens) and **consistent metadata on every returned row**, or an explicit "ids-only" mode that's honest about it.
- **`days` vs `start_date/end_date`.** Behaviour was unclear when both could apply; date-bounded queries still seemed newest-capped. Document precedence and guarantee full coverage within the range up to `max_results`.
- **Filter by label** in queries (in:, label:) and reliable negative sender filters.

## 4. `get_email` ergonomics

- **Body size guards / mode flag.** A single `get_email` returned ~60k chars of raw HTML and exceeded the tool token budget — so I couldn't read it at all. Add `body: none | text | html | markdown` and/or server-side truncation. Default to text/markdown.
- **Headers-only / metadata-only mode** (subject, from, to, cc, date, snippet, label ids, attachment manifest) without the body.
- **Batch get.** Fetch headers for N `message_id`s in one call — triage scanning one-at-a-time is slow.

## 5. Attachments

- **Inline vs real attachment flag.** Downloads mix real documents with inline signature images (`image001.png`, logos). Expose `inline` / `content-id` / `mime_type` / `size` so callers can skip cruft. (`attachment_types` filtering helps but is extension-based, not inline-aware.)
- **Output path contract.** `save_email(download_attachments=True)` writes attachments into a nested `<output_dir>/attachments/<message_id>/` subfolder. Fine, but undocumented; a returned **manifest** (saved paths + which are inline) would beat having to `find` the tree afterward.

## 6. Nice-to-have

- **`list_labels` + label IDs on messages** already partially present in `labels` (e.g. `Label_2218869635608765882`) but opaque — resolve IDs to names.
- **Calendar write** (`save_event` exists; confirm it can create/update on the provider, not just cache locally).

## Priority order for this project
1. Labels (read+write) — unlocks buckets-in-Gmail.
2. Expose `To/Cc` — unlocks Hubdoc address + better triage.
3. Forward-with-attachments (send) — unlocks receipt automation.
4. Search pagination + `get_email` size handling — unlocks reliable full-window scans.
