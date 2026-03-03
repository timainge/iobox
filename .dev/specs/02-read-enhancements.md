# Phase 2: Gmail Read Enhancements

**Status**: Not started
**Priority**: High — expands read capabilities with no scope changes
**Scope change**: None — uses existing `gmail.readonly` scope
**Depends on**: Phase 1 (pagination fix)

---

## 2.1 Thread-Level Export

### Problem

`thread_id` is already captured in email metadata (`email_retrieval.py:53`) and saved in YAML frontmatter, but iobox has no way to fetch an entire email thread as a single document. Users who want to archive a full conversation must save each message individually.

### Gmail API

`threads.get` returns all messages in a thread in a single call (10 quota units). Response includes a `messages[]` array with full message objects.

### Required Changes

**File**: `src/iobox/email_retrieval.py`

1. Add `get_thread_content(service, thread_id, preferred_content_type='text/plain')` function
2. Call `service.users().threads().get(userId='me', id=thread_id, format='full').execute()`
3. Return a list of email data dicts (one per message in the thread), ordered chronologically

**File**: `src/iobox/markdown_converter.py`

4. Add `convert_thread_to_markdown(messages)` function
5. Produce a single markdown document with each message as a section, separated by horizontal rules
6. Include per-message metadata (from, date) as sub-headers

**File**: `src/iobox/cli.py`

7. Add `--thread-id` option to the `save` command
8. When `--thread-id` is provided, fetch the full thread and save as a single file
9. Filename based on thread subject + thread ID

### Acceptance Criteria

- [ ] `iobox save --thread-id THREAD_ID -o ./output` saves a single markdown file with all messages
- [ ] Messages appear in chronological order within the file
- [ ] YAML frontmatter includes `thread_id`, `message_count`, and combined labels
- [ ] Unit test: mock `threads.get` response with 3 messages, verify combined output
- [ ] Unit test: verify chronological ordering

---

## 2.2 Profile in auth-status

### Problem

The `auth-status` command shows token/credential file paths but doesn't confirm which Gmail account is authenticated or show mailbox statistics.

### Gmail API

`users.getProfile` (1 quota unit) returns:
- `emailAddress`: The authenticated user's email
- `messagesTotal`: Total messages in mailbox
- `threadsTotal`: Total threads in mailbox
- `historyId`: Current history record ID

### Required Changes

**File**: `src/iobox/auth.py`

1. Add `get_gmail_profile(service)` function that calls `service.users().getProfile(userId='me').execute()`
2. Return the profile dict

**File**: `src/iobox/cli.py`

3. In `auth_status()`, after displaying token info, attempt to build a service and call `get_gmail_profile()`
4. Display: email address, total messages, total threads
5. Wrap in try/except — if auth fails, show the existing status info without profile

### Output Example

```
Authentication Status
-------------------
Authenticated: True
Credentials file exists: True
Token file exists: True

Gmail Profile
-------------------
Email: user@gmail.com
Messages: 66,327
Threads: 13,902
```

### Acceptance Criteria

- [ ] `iobox auth-status` shows email address and mailbox stats when authenticated
- [ ] Gracefully falls back to existing output if authentication fails or service unavailable
- [ ] Unit test: mock `getProfile` response and verify output
- [ ] Unit test: verify fallback when `getProfile` raises an exception

---

## 2.3 Include Spam/Trash Flag

### Problem

`messages.list` supports an `includeSpamTrash` parameter but iobox never sets it. Users cannot search across spam and trash folders.

### Required Changes

**File**: `src/iobox/email_search.py`

1. Add `include_spam_trash: bool = False` parameter to `search_emails()`
2. Pass `includeSpamTrash=include_spam_trash` to `messages.list` call

**File**: `src/iobox/cli.py`

3. Add `--include-spam-trash` flag to `search` and `save` commands
4. Pass through to `search_emails()`

### Acceptance Criteria

- [ ] `iobox search -q "from:x" --include-spam-trash` searches across all folders
- [ ] Default behavior unchanged (spam/trash excluded)
- [ ] Unit test: verify `includeSpamTrash=True` is passed to the API mock

---

## Test Files to Create/Modify

| File | Changes |
|---|---|
| `tests/unit/test_email_retrieval.py` | Thread content retrieval tests |
| `tests/unit/test_markdown.py` | Thread-to-markdown conversion tests |
| `tests/unit/test_auth.py` | Profile retrieval tests |
| `tests/unit/test_cli.py` | Thread save, auth-status profile, spam/trash flag tests |
| `tests/unit/test_email_search.py` | `includeSpamTrash` parameter tests |

## Quota Impact

| Operation | Units | Notes |
|---|---|---|
| `threads.get` | 10 | One call per thread export |
| `users.getProfile` | 1 | One call per `auth-status` |
| `messages.list` (spam/trash) | 5 | Same cost, wider search scope |
