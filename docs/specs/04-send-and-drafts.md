# Phase 4: Enhanced Send and Drafts

**Status**: Not started
**Priority**: Medium — upgrades send from plain text to full MIME, adds draft workflow
**Scope change**: Add `gmail.compose` for draft management
**Depends on**: Phase 3 (scope already at `gmail.modify`)

---

## 4.1 HTML Email Sending

### Problem

`compose_message()` in `src/iobox/email_sender.py:38` uses `MIMEText(body)` which defaults to `text/plain`. There is no support for HTML body content or mixed content.

### Required Changes

**File**: `src/iobox/email_sender.py`

1. Add `content_type: str = 'plain'` parameter to `compose_message()`
2. When `content_type='html'`, use `MIMEText(body, 'html')`
3. When both plain and HTML are desired, construct a `MIMEMultipart('alternative')` message with both parts

**File**: `src/iobox/cli.py`

4. Add `--html` flag to the `send` command
5. When `--body-file` is used with a `.html` file, auto-detect and set HTML mode

### Acceptance Criteria

- [ ] `iobox send --to x --subject y --body "<h1>Hello</h1>" --html` sends an HTML email
- [ ] `iobox send --to x --subject y --body-file message.html` auto-detects HTML
- [ ] Default behavior unchanged (plain text)
- [ ] Unit test: verify HTML MIMEText construction
- [ ] Unit test: verify auto-detection from .html file extension

---

## 4.2 Attachment Sending

### Problem

`compose_message()` has no support for attaching files to outgoing emails.

### Required Changes

**File**: `src/iobox/email_sender.py`

1. Add `attachments: list[str] = None` parameter to `compose_message()`
2. When attachments are provided, construct a `MIMEMultipart('mixed')` message
3. For each file path, detect MIME type, read file, and attach as `MIMEBase` part
4. Set `Content-Disposition: attachment` header with filename

**File**: `src/iobox/cli.py`

5. Add `--attach` option to `send` command (repeatable for multiple files)

```
iobox send --to x --subject y --body "See attached" --attach report.pdf --attach data.csv
```

### Acceptance Criteria

- [ ] `iobox send --to x --subject y --body z --attach file.pdf` sends with attachment
- [ ] Multiple `--attach` flags work correctly
- [ ] MIME types are auto-detected from file extension
- [ ] Files that don't exist produce a clear error before sending
- [ ] Unit test: verify MIME multipart construction with attachment

---

## 4.3 Draft Management

### Problem

The `send` command sends immediately. There is no way to compose a draft for review before sending, or to list/manage existing drafts.

### Gmail API

| Method | Description | Quota |
|---|---|---|
| `drafts.create` | Create a draft | 10 units |
| `drafts.list` | List all drafts | 5 units |
| `drafts.get` | Retrieve a draft | 5 units |
| `drafts.update` | Replace draft content | 10 units |
| `drafts.send` | Send a draft | 100 units |
| `drafts.delete` | Permanently delete a draft | 10 units |

### Required Changes

**File**: `src/iobox/email_sender.py`

1. Add `create_draft(service, message)` — calls `drafts.create`
2. Add `list_drafts(service, max_results=10)` — calls `drafts.list`, returns draft ID + subject + snippet
3. Add `get_draft(service, draft_id)` — calls `drafts.get`
4. Add `send_draft(service, draft_id)` — calls `drafts.send`
5. Add `delete_draft(service, draft_id)` — calls `drafts.delete`

**File**: `src/iobox/cli.py`

6. Add `draft` command with subcommands:

```
iobox draft create --to x --subject y --body "content"
iobox draft list
iobox draft send --draft-id DRAFT_ID
iobox draft delete --draft-id DRAFT_ID
```

7. `draft create` accepts the same options as `send` but calls `create_draft` instead

### Scope Change

Add `gmail.compose` to `SCOPES` in `auth.py`:
```python
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
]
```

Note: `gmail.modify` already includes send capability but not draft creation. `gmail.compose` adds create/update/send drafts.

### Acceptance Criteria

- [ ] `iobox draft create --to x --subject y --body z` creates a draft and shows its ID
- [ ] `iobox draft list` shows draft IDs, subjects, and snippets
- [ ] `iobox draft send --draft-id X` sends the draft
- [ ] `iobox draft delete --draft-id X` permanently deletes the draft
- [ ] Re-authentication triggered if existing token lacks `compose` scope
- [ ] Unit tests for each draft operation

---

## Test Files to Create/Modify

| File | Changes |
|---|---|
| `tests/unit/test_email_sender.py` | HTML compose, attachment compose, draft CRUD tests |
| `tests/unit/test_cli.py` | `send --html`, `send --attach`, `draft` subcommand tests |

## Quota Impact

| Operation | Units | Notes |
|---|---|---|
| `drafts.create` | 10 | Per draft |
| `drafts.list` | 5 | Per listing |
| `drafts.send` | 100 | Same as `messages.send` |
| `drafts.delete` | 10 | Per draft |
