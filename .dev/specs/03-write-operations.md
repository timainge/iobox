# Phase 3: Gmail Write Operations

**Status**: Not started
**Priority**: High — enables core email workflow actions (read/archive/label)
**Scope change**: Replace `gmail.readonly` + `gmail.send` with `gmail.modify`
**Depends on**: Phase 1 (label resolution for label name-to-ID mapping)

---

## Scope Upgrade

`gmail.modify` is a superset that includes read, send, label management, and trash — replacing both `gmail.readonly` and `gmail.send`. Users will need to delete `token.json` and re-authenticate after this change.

**File**: `src/iobox/auth.py`

Update `SCOPES`:
```python
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
]
```

Add a note in `get_gmail_service()` to detect scope mismatch and prompt re-auth.

---

## 3.1 Label Management (messages.modify)

### Problem

After saving emails, users cannot mark them as read, star them, archive them, or apply custom labels from the CLI. These are all label operations in the Gmail API.

### Gmail Label Operations

| Action | Add Labels | Remove Labels |
|---|---|---|
| Mark as read | — | `UNREAD` |
| Mark as unread | `UNREAD` | — |
| Star | `STARRED` | — |
| Unstar | — | `STARRED` |
| Archive | — | `INBOX` |
| Unarchive | `INBOX` | — |
| Apply custom label | `Label_XXXXX` | — |
| Remove custom label | — | `Label_XXXXX` |

### Required Changes

**File**: `src/iobox/email_retrieval.py` (or new `src/iobox/email_labels.py`)

1. Add `modify_message_labels(service, message_id, add_labels=None, remove_labels=None)` function
2. Call `service.users().messages().modify(userId='me', id=message_id, body={...}).execute()`
3. Add `resolve_label_name(service, label_name)` that maps human-readable names to IDs using `get_label_map()` from Phase 1

**File**: `src/iobox/cli.py`

4. Add `label` command with subactions:

```
iobox label --message-id MSG_ID --mark-read
iobox label --message-id MSG_ID --star
iobox label --message-id MSG_ID --archive
iobox label --message-id MSG_ID --add "Newsletter"
iobox label --message-id MSG_ID --remove "Newsletter"
iobox label --query "from:x" --mark-read          # batch mode
```

5. Support both `--message-id` (single) and `--query` (batch) modes, same pattern as save/forward

### Acceptance Criteria

- [ ] `iobox label --message-id X --mark-read` removes `UNREAD` label
- [ ] `iobox label --message-id X --star` adds `STARRED` label
- [ ] `iobox label --message-id X --archive` removes `INBOX` label
- [ ] `iobox label --message-id X --add "MyLabel"` resolves label name to ID and applies it
- [ ] Batch mode: `iobox label --query "from:x" --mark-read` processes all matching emails
- [ ] Unit tests for each label operation
- [ ] Unit test: verify label name-to-ID resolution

---

## 3.2 Batch Label Operations (messages.batchModify)

### Problem

Applying labels to many messages individually costs 5 quota units each. `messages.batchModify` applies label changes to up to 1000 messages in a single call for 50 quota units.

### Required Changes

**File**: `src/iobox/email_retrieval.py` (or `email_labels.py`)

1. Add `batch_modify_labels(service, message_ids, add_labels=None, remove_labels=None)` function
2. Call `service.users().messages().batchModify(userId='me', body={...}).execute()`
3. Chunk into groups of 1000 if needed

**File**: `src/iobox/cli.py`

4. When batch mode is used in the `label` command and more than 1 message is selected, use `batchModify` instead of individual `modify` calls

### Acceptance Criteria

- [ ] Batch mode uses `batchModify` for 2+ messages
- [ ] Single message mode still uses `messages.modify`
- [ ] Unit test: mock `batchModify` and verify correct payload

---

## 3.3 Trash / Untrash

### Problem

No way to move emails to trash or restore them from trash via CLI.

### Required Changes

**File**: `src/iobox/email_retrieval.py` (or `email_labels.py`)

1. Add `trash_message(service, message_id)` — calls `service.users().messages().trash()`
2. Add `untrash_message(service, message_id)` — calls `service.users().messages().untrash()`

**File**: `src/iobox/cli.py`

3. Add `trash` command:

```
iobox trash --message-id MSG_ID
iobox trash --query "from:x" --days 7
```

4. Add `--untrash` flag or separate `untrash` command

### Acceptance Criteria

- [ ] `iobox trash --message-id X` moves message to trash
- [ ] Batch mode supports query-based trashing
- [ ] Confirmation prompt before batch trash (typer.confirm)
- [ ] Unit tests for trash and untrash

---

## Re-authentication Strategy

When upgrading from `readonly`+`send` to `modify`, existing `token.json` files will have insufficient scopes.

**File**: `src/iobox/auth.py`

1. In `get_gmail_service()`, after loading credentials, check if `creds.scopes` matches `SCOPES`
2. If scopes don't match, log a warning and trigger re-auth flow (delete token, run OAuth again)
3. Display a user-friendly message: "Scope upgrade required. Re-authenticating..."

### Acceptance Criteria

- [ ] Existing users with old token.json are prompted to re-authenticate
- [ ] Re-auth is automatic (no manual token deletion needed)
- [ ] Unit test: mock credentials with old scopes, verify re-auth is triggered

---

## Test Files to Create/Modify

| File | Changes |
|---|---|
| `tests/unit/test_email_retrieval.py` or new `test_email_labels.py` | Label modify, batch modify, trash/untrash tests |
| `tests/unit/test_cli.py` | `label` and `trash` command tests |
| `tests/unit/test_auth.py` | Scope mismatch re-auth tests |

## Quota Impact

| Operation | Units | Notes |
|---|---|---|
| `messages.modify` | 5 | Per-message label change |
| `messages.batchModify` | 50 | Up to 1000 messages at once |
| `messages.trash` | 5 | Per message |
| `messages.untrash` | 5 | Per message |
