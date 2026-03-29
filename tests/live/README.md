# Live CLI Integration Tests

Manual and automated test scenarios for verifying iobox CLI commands against a real Gmail account.

**Prerequisites:**
- Authenticated Gmail account (`iobox auth-status` shows `Authenticated: True`)
- All commands use the authenticated user's own email for send/forward targets

**Subject tagging:** Every sent/forwarded/drafted email uses `[iobox-test-<session_id>]` in the subject so `cleanup.py` can target exactly those messages.

---

## Section A: Read-Only Tests (safe, no side effects)

### 1. Auth status
Verify authenticated and shows profile info.
```bash
iobox auth-status
```
- [ ] Exit code 0
- [ ] Output contains `Authenticated: True`
- [ ] Output contains `Email:` with a valid address

### 2. Search — basic query with defaults
```bash
iobox search -q "in:inbox" -m 5
```
- [ ] Exit code 0
- [ ] Output contains `Found N emails`

### 3. Search — with `--days`, `--max-results`, `--verbose`
```bash
iobox search -q "in:inbox" -m 3 -d 30 --verbose
```
- [ ] Exit code 0
- [ ] Output contains `Labels:` (verbose mode)

### 4. Search — with `--start-date` / `--end-date` range
```bash
iobox search -q "in:inbox" -s 2025/01/01 -e 2025/01/31 -m 5
```
- [ ] Exit code 0
- [ ] Results fall within date range

### 5. Search — with `--include-spam-trash`
```bash
iobox search -q "in:anywhere" -m 3 --include-spam-trash
```
- [ ] Exit code 0

### 6. Save — single email by `--message-id` to temp dir
Requires a known message ID from a prior search.
```bash
iobox save --message-id <MSG_ID> -o /tmp/iobox-test-save
```
- [ ] Exit code 0
- [ ] Output contains `Successfully saved email to`
- [ ] A `.md` file exists in the output dir

### 7. Save — batch by query to temp dir
```bash
iobox save -q "in:inbox" --max 3 -d 30 -o /tmp/iobox-test-batch
```
- [ ] Exit code 0
- [ ] Output contains `emails saved to markdown`
- [ ] Multiple `.md` files in output dir

### 8. Save — with `--no-html-preferred` (plain text)
```bash
iobox save -q "in:inbox" --max 1 -d 30 --no-html-preferred -o /tmp/iobox-test-plain
```
- [ ] Exit code 0
- [ ] Saved markdown file exists

### 9. Save — with `--download-attachments`
```bash
iobox save -q "has:attachment" --max 1 -d 90 --download-attachments -o /tmp/iobox-test-attach
```
- [ ] Exit code 0
- [ ] `attachments/` subdirectory created (if email had attachments)

### 10. Save — `--thread-id` for thread export
Requires a known thread ID from a prior search.
```bash
iobox save --thread-id <THREAD_ID> -o /tmp/iobox-test-thread
```
- [ ] Exit code 0
- [ ] Output contains `Successfully saved thread to`

### 11. Save — `--sync` incremental (run twice, second should be no-op)
```bash
iobox save -q "in:inbox" --max 3 -d 7 --sync -o /tmp/iobox-test-sync
iobox save -q "in:inbox" --max 3 -d 7 --sync -o /tmp/iobox-test-sync
```
- [ ] First run saves emails
- [ ] Second run reports `Skipping already processed` or `No new emails`
- [ ] `Sync state updated` appears in output

---

## Section B: Write/Send Tests (sends only to self)

All `--to` addresses must be the authenticated user's own email.

### 12. Send — plain text email to self
```bash
iobox send --to <SELF_EMAIL> -s "[iobox-test-<ID>] Plain text test" -b "This is a plain text test email."
```
- [ ] Exit code 0
- [ ] Output contains `Email sent successfully`

### 13. Send — HTML email to self
```bash
iobox send --to <SELF_EMAIL> -s "[iobox-test-<ID>] HTML test" -b "<h1>Hello</h1><p>HTML body</p>" --html
```
- [ ] Exit code 0
- [ ] Output contains `Email sent successfully`

### 14. Send — with attachment
```bash
iobox send --to <SELF_EMAIL> -s "[iobox-test-<ID>] Attachment test" -b "See attached." --attach /tmp/iobox-test-attachment.txt
```
- [ ] Exit code 0
- [ ] Output contains `Email sent successfully`

### 15. Forward — forward a known message to self
```bash
iobox forward --message-id <MSG_ID> --to <SELF_EMAIL>
```
- [ ] Exit code 0
- [ ] Output contains `Successfully forwarded`

### 16. Draft — create a draft
```bash
iobox draft-create --to <SELF_EMAIL> -s "[iobox-test-<ID>] Draft test" -b "This is a draft."
```
- [ ] Exit code 0
- [ ] Output contains `Draft created successfully`

### 17. Draft — list drafts
```bash
iobox draft-list --max 20
```
- [ ] Exit code 0
- [ ] Output contains the test draft subject

### 18. Draft — delete the draft
```bash
iobox draft-delete --draft-id <DRAFT_ID>
```
- [ ] Exit code 0
- [ ] Output contains `Draft deleted successfully`

### 19. Label — star a message, then unstar it
```bash
iobox label --message-id <MSG_ID> --star
iobox label --message-id <MSG_ID> --unstar
```
- [ ] Both exit code 0
- [ ] Output contains `Labels updated`

### 20. Label — mark read, mark unread
```bash
iobox label --message-id <MSG_ID> --mark-read
iobox label --message-id <MSG_ID> --mark-unread
```
- [ ] Both exit code 0
- [ ] Output contains `Labels updated`

### 21. Trash — trash a test message, then untrash to restore it
```bash
iobox trash --message-id <MSG_ID>
iobox trash --message-id <MSG_ID> --untrash
```
- [ ] Both exit code 0
- [ ] Message is restored after untrash

---

## Section C: Space Management (local config, no OAuth required)

These tests exercise the `iobox space` command group against the local filesystem.
No live API calls are made; OAuth is not triggered.

### 22. Space — create a test space
```bash
iobox space create live-test-space
```
- [ ] Exit code 0
- [ ] Output confirms space created

### 23. Space — list spaces
```bash
iobox space list
```
- [ ] Exit code 0
- [ ] `live-test-space` appears in the list

### 24. Space — switch active space
```bash
iobox space use live-test-space
```
- [ ] Exit code 0
- [ ] Output confirms active space changed

### 25. Space — status (no services configured yet)
```bash
iobox space status
```
- [ ] Exit code 0
- [ ] Output shows empty or zero service sessions (not an error)

---

## Section D: Calendar Events (requires workspace with calendar configured)

These tests require an active workspace with at least one calendar provider configured
(`iobox space add gmail you@gmail.com --calendar --read`). If no calendar provider is
available the runner skips and marks SKIP rather than FAIL.

### 26. Events — list upcoming events
```bash
iobox events list --after <TODAY> --max 5
```
- [ ] Exit code 0
- [ ] Output contains event titles or `No events found`

### 27. Events — list with before/after range
```bash
iobox events list --after <TODAY> --before <TODAY+30D> --max 10
```
- [ ] Exit code 0
- [ ] All returned events fall within the date range

### 28. Events — get a single event by ID
Requires an event ID from a prior `events list` result.
```bash
iobox events get <EVENT_ID>
```
- [ ] Exit code 0
- [ ] Output contains `Title:` and `Start:`

### 29. Events — save an event to Markdown
```bash
iobox events save <EVENT_ID> -o /tmp/iobox-test-events
```
- [ ] Exit code 0
- [ ] A `.md` file is created in the output dir
- [ ] File contains YAML frontmatter with `start:` field

---

## Section E: Files (requires workspace with drive configured)

These tests require an active workspace with at least one file provider configured
(`iobox space add gmail you@gmail.com --drive --read`). The runner skips if no file
provider is available.

### 30. Files — list by query
```bash
iobox files list --query "report" --max 5
```
- [ ] Exit code 0
- [ ] Output contains file names or `No files found`

### 31. Files — get a single file by ID
Requires a file ID from a prior `files list` result.
```bash
iobox files get <FILE_ID>
```
- [ ] Exit code 0
- [ ] Output contains `Name:` and `Type:`

### 32. Files — save file metadata to Markdown
```bash
iobox files save <FILE_ID> -o /tmp/iobox-test-files
```
- [ ] Exit code 0
- [ ] A `.md` file is created in the output dir
- [ ] File contains YAML frontmatter with `mime_type:` field

---

## Section F: Cleanup

### 33. Run cleanup script
```bash
python tests/live/cleanup.py
```
- [ ] All emails with `[iobox-test-` in subject are trashed
- [ ] All drafts with `[iobox-test-` in subject are deleted
- [ ] Test space `live-test-space` removed from `~/.iobox/workspaces/`
- [ ] Summary printed

---

## Running

```bash
# Automated runner (all sections)
python tests/live/run_tests.py

# Cleanup only
python tests/live/cleanup.py
```
