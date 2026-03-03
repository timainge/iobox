# Phase 5: Performance

**Status**: Not started
**Priority**: Medium — reduces API latency and enables efficient repeated syncing
**Scope change**: None
**Depends on**: Phase 1 (pagination fix), Phase 2 (thread export)

---

## 5.1 HTTP Batch Requests

### Problem

In batch `save` mode, iobox makes `2N` separate HTTP requests for `N` emails:
- `N` calls to `messages.get` with `format=metadata` (in `search_emails()`)
- `N` calls to `messages.get` with `format=full` (in `get_email_content()`)

Each HTTP round-trip adds latency (~100-300ms). For 50 emails, this is 100 HTTP requests taking 10-30 seconds of network time alone.

### Gmail API Batch Support

The Google API Python client supports batching up to 100 API calls in a single HTTP request. Quota units are unchanged, but network round-trips drop from `2N` to `ceil(2N/50)`.

```python
from googleapiclient.http import BatchHttpRequest

batch = service.new_batch_http_request()
batch.add(service.users().messages().get(userId='me', id=msg_id, format='full'), callback=cb)
batch.execute()
```

### Required Changes

**File**: `src/iobox/email_retrieval.py`

1. Add `batch_get_emails(service, message_ids, format='full', preferred_content_type='text/plain')` function
2. Use `BatchHttpRequest` to fetch multiple messages in chunks of 50
3. Return a list of email data dicts in the same order as input IDs
4. Handle per-message errors within the batch (some may fail while others succeed)

**File**: `src/iobox/email_search.py`

5. Add `batch_get_metadata(service, message_ids)` function
6. Use `BatchHttpRequest` with `format=metadata` to fetch preview info in bulk
7. Replace the sequential loop in `search_emails()` (lines 70-90)

**File**: `src/iobox/cli.py`

8. In batch `save` mode, use `batch_get_emails()` instead of calling `get_email_content()` per message
9. Add a progress indicator for batch operations

### Acceptance Criteria

- [ ] Batch save of 50 emails uses at most 2 HTTP requests (instead of 100)
- [ ] Individual message failures in a batch don't abort the entire operation
- [ ] Unit test: mock batch callback and verify all messages are processed
- [ ] Unit test: verify partial failure handling (2 of 5 messages fail)

---

## 5.2 Incremental Sync via history.list

### Problem

Every invocation of `iobox save --query "..."` runs a full `messages.list` query, re-fetching message IDs that may have already been saved. For users running iobox periodically (e.g., daily newsletter archiving), this is wasteful.

### Gmail API

`history.list` (2 quota units) returns all changes since a given `historyId`:
- `messagesAdded`: New messages
- `messagesDeleted`: Deleted messages
- `labelsAdded` / `labelsRemoved`: Label changes

Combined with `users.getProfile` (which returns the current `historyId`), this enables efficient delta sync.

### Required Changes

**File**: `src/iobox/file_manager.py` (or new `src/iobox/sync_state.py`)

1. Add `SyncState` class that reads/writes a `.iobox-sync.json` file in the output directory
2. State includes: `last_history_id`, `last_sync_time`, `synced_message_ids[]`
3. Methods: `load()`, `save()`, `update(history_id, message_ids)`

**File**: `src/iobox/email_search.py`

4. Add `get_new_messages(service, history_id)` function
5. Call `service.users().history().list(userId='me', startHistoryId=history_id, historyTypes=['messageAdded']).execute()`
6. Follow pagination (history.list also returns `nextPageToken`)
7. Return list of new message IDs

**File**: `src/iobox/cli.py`

8. Add `--sync` flag to the `save` command
9. When `--sync` is used:
   - Load sync state from output directory
   - If state exists, use `get_new_messages()` to fetch only new messages
   - If no state or state expired (HTTP 404 from API), fall back to full query
   - After saving, update sync state with new `historyId`

### Edge Cases

- `history.list` returns HTTP 404 when `startHistoryId` is too old (records kept ~1 week). Fall back to full sync.
- First run has no state — do a full sync and save the initial `historyId` via `getProfile`
- Sync state file should be `.gitignore`-able

### Acceptance Criteria

- [ ] `iobox save --query "..." --sync -o ./emails` creates `.iobox-sync.json` on first run
- [ ] Subsequent runs with `--sync` only fetch new messages
- [ ] Graceful fallback to full sync when history is unavailable
- [ ] Unit test: mock history.list response with new message IDs
- [ ] Unit test: mock HTTP 404 from history.list, verify full sync fallback

---

## 5.3 Refactor download_email_attachments

### Problem

`download_email_attachments()` is a business-logic function defined in `cli.py:472-534`. It belongs in the library layer so it can be used by library consumers and the MCP server.

### Required Changes

**File**: `src/iobox/file_manager.py`

1. Move `download_email_attachments()` from `cli.py` to `file_manager.py`
2. Remove `typer.echo()` calls — use `logging.info()` instead
3. Return a result dict with `downloaded_count`, `skipped_count`, `errors[]`

**File**: `src/iobox/cli.py`

4. Import `download_email_attachments` from `file_manager`
5. Use the returned result dict to display typer output

### Acceptance Criteria

- [ ] `download_email_attachments` importable from `iobox.file_manager`
- [ ] No `typer` dependency in `file_manager.py`
- [ ] CLI output unchanged
- [ ] Existing tests pass with updated import

---

## Test Files to Create/Modify

| File | Changes |
|---|---|
| `tests/unit/test_email_retrieval.py` | Batch retrieval tests |
| `tests/unit/test_email_search.py` | Batch metadata fetch tests |
| `tests/unit/test_file_manager.py` | Sync state tests, refactored attachment download tests |
| `tests/unit/test_cli.py` | `--sync` flag tests |

## Quota Impact

| Operation | Units | Notes |
|---|---|---|
| `history.list` | 2 per page | Much cheaper than full `messages.list` + `messages.get` |
| `users.getProfile` | 1 | Needed to get initial `historyId` |
| HTTP batch | Same units | Reduces HTTP round-trips, not quota |
