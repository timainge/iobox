# Phase 1: Critical Bug Fixes

**Status**: Not started
**Priority**: Critical — these are data-loss and usability bugs in existing functionality
**Scope change**: None — uses existing `gmail.readonly` scope

---

## 1.1 Pagination in `search_emails()`

### Problem

`search_emails()` in `src/iobox/email_search.py` calls `messages.list` once and stops. If the Gmail API returns a `nextPageToken` (indicating more results exist beyond the current page), iobox ignores it and silently drops all remaining results.

The Gmail API returns at most 500 messages per page (default 100). For any query returning more results than `maxResults`, iobox currently truncates without warning.

### Current Code (email_search.py:55-59)

```python
result = service.users().messages().list(
    userId='me',
    q=full_query,
    maxResults=max_results
).execute()
messages = result.get('messages', [])
```

### Required Changes

**File**: `src/iobox/email_search.py`

- After the initial `messages.list` call, loop while `nextPageToken` is present and `len(messages) < max_results`
- Pass `pageToken=result['nextPageToken']` to subsequent calls
- Truncate the final list to exactly `max_results` entries
- Log when pagination is used (e.g., "Fetching page 2...")

### Acceptance Criteria

- [ ] Queries returning more than one page of results retrieve all pages up to `max_results`
- [ ] The total number of returned messages never exceeds `max_results`
- [ ] Existing unit tests still pass (mocks return single pages, so behavior is unchanged)
- [ ] New unit test: mock a two-page response with `nextPageToken` and verify both pages are consumed
- [ ] New unit test: verify truncation when total results exceed `max_results`

---

## 1.2 Label ID Resolution

### Problem

Saved emails contain raw Gmail label IDs in the YAML frontmatter, e.g.:

```yaml
labels:
  - INBOX
  - UNREAD
  - Label_12345
```

System labels like `INBOX` are human-readable, but user-created labels appear as opaque IDs (`Label_12345`). One `labels.list` call (1 quota unit) returns the full ID-to-name mapping for all labels in the mailbox.

### Current Code

Labels are captured as raw IDs in two places:
- `email_search.py:89` — `'labels': msg.get('labelIds', [])`
- `email_retrieval.py:51` — `'labels': message.get('labelIds', [])`

Neither module calls `labels.list` to resolve IDs.

### Required Changes

**File**: `src/iobox/email_retrieval.py` (or a new helper)

1. Add a `get_label_map(service)` function that calls `service.users().labels().list(userId='me').execute()` and returns a `dict[str, str]` mapping label ID to display name
2. Cache the label map per service instance (or accept it as a parameter) to avoid redundant API calls
3. In `get_email_content()`, resolve label IDs to names before returning `email_data`

**File**: `src/iobox/email_search.py`

4. In `search_emails()`, optionally accept a label map and resolve labels on preview results
5. If no label map is provided, return raw IDs (backward compatible)

**File**: `src/iobox/cli.py`

6. In the `save` and `search` commands, call `get_label_map()` once and pass it through

### Acceptance Criteria

- [ ] `get_label_map()` function exists and returns `{id: name}` mapping
- [ ] Saved markdown files show human-readable label names (e.g., `Newsletter` instead of `Label_12345`)
- [ ] System labels pass through unchanged (`INBOX` stays `INBOX`)
- [ ] Label map is fetched at most once per CLI invocation
- [ ] Unit test: mock `labels.list` response and verify ID-to-name resolution
- [ ] Unit test: verify graceful fallback if `labels.list` fails (use raw IDs)

---

## Test Files to Modify

| File | Changes |
|---|---|
| `tests/unit/test_email_search.py` | Add pagination tests |
| `tests/unit/test_email_retrieval.py` | Add label resolution tests |
| `tests/unit/test_cli.py` | Update mocks if `get_label_map` is called in CLI layer |

## Quota Impact

| Operation | Units | Frequency |
|---|---|---|
| `messages.list` (pagination) | 5 per page | Was 1, now 1–N depending on result size |
| `labels.list` | 1 | Once per invocation |
