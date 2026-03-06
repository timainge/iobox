# Phase 10: O365/Outlook Support

**Status**: Not started
**Priority**: High — enables iobox to work with Microsoft 365 mailboxes alongside Gmail
**Scope change**: Major — introduces provider abstraction layer, new dependencies, refactors CLI
**Depends on**: None (can be developed in parallel with existing Gmail features)
**Research**: `.dev/research/iobox-o365-outlook-support/report.md`

---

## Overview

Add Microsoft 365 / Outlook support to iobox via the Microsoft Graph API, achieving full feature parity with existing Gmail capabilities. This requires: (1) an `EmailProvider` abstraction layer, (2) wrapping existing Gmail code into a `GmailProvider`, (3) implementing an `OutlookProvider` using `python-o365`, and (4) refactoring the CLI to route through the provider interface.

### New Dependencies

```toml
[project.optional-dependencies]
outlook = ["O365>=2.1.8"]
```

The `O365` package bundles `msal`, `msal-extensions`, `requests`, and `beautifulsoup4`. Gmail remains the default with no new dependencies.

### Feature Parity Summary

| Feature | Gmail | Outlook (Graph) | Parity |
|---|---|---|---|
| Search | `q=` Gmail syntax | `$search` KQL / `$filter` OData | Full |
| Read email | base64 MIME parts | JSON body (HTML/text) | Full |
| Send | Raw MIME base64url | Structured JSON | Full |
| Forward | Manual reconstruction | Native endpoint | Full (Graph is simpler) |
| Drafts CRUD | Separate `drafts` resource | Messages with `isDraft=true` | Full |
| Star/flag | STARRED label | `followupFlag` | Full |
| Mark read | UNREAD label | `isRead` boolean | Full |
| Archive | Remove INBOX label | Move to archive folder | Full |
| Custom tags | Label IDs | Categories array | Full |
| Trash | `messages.trash()` | `DELETE` (soft delete) | Full |
| Attachments | base64url decode | `/$value` raw bytes | Full |
| Incremental sync | Global `historyId` | Per-folder `deltaLink` | Full (architectural diff) |

---

## 10.1 Provider Abstraction Layer

### Problem

Every iobox module (`email_search.py`, `email_retrieval.py`, `email_sender.py`, `auth.py`) is hardwired to the Gmail API. Functions accept a Gmail `service` object directly and call Gmail-specific endpoints. Adding Outlook support without an abstraction layer would require duplicating the entire CLI routing logic or littering every command with `if provider == "gmail"` branches.

### Required Changes

**File**: `src/iobox/providers/__init__.py`

Create the providers package with a factory function:

```python
from iobox.providers.base import EmailProvider, EmailQuery, EmailData

_PROVIDERS: dict[str, str] = {
    "gmail": "iobox.providers.gmail.GmailProvider",
    "outlook": "iobox.providers.outlook.OutlookProvider",
}


def get_provider(name: str = "gmail", **kwargs) -> EmailProvider:
    """Instantiate an email provider by name.

    Uses lazy importlib import so Outlook dependencies are never
    required for Gmail-only users.
    """
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS)}"
        )
    module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**kwargs)
```

---

**File**: `src/iobox/providers/base.py`

Define the ABC, query dataclass, and normalized return type:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import TypedDict


class AttachmentInfo(TypedDict):
    id: str
    filename: str
    mime_type: str
    size: int


class EmailData(TypedDict, total=False):
    """Normalized email data dict returned by all providers."""
    # Required — always present
    message_id: str
    subject: str
    from_: str              # "Display Name <email>" format
    date: str
    snippet: str
    labels: list[str]       # Gmail labels or Outlook categories
    thread_id: str          # Gmail threadId or Outlook conversationId

    # Present in full retrieval, absent in search/metadata results
    body: str
    content_type: str       # 'text/plain' or 'text/html'
    attachments: list[AttachmentInfo]


@dataclass
class EmailQuery:
    """Provider-agnostic search query.

    Each provider translates this into its native query format.
    Set 'raw_query' to bypass translation and pass provider-native
    syntax directly (Gmail search syntax or OData/KQL).
    """
    text: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    subject: str | None = None
    after: date | None = None
    before: date | None = None
    has_attachment: bool | None = None
    is_unread: bool | None = None
    label: str | None = None
    max_results: int = 100
    include_spam_trash: bool = False
    raw_query: str | None = None


class EmailProvider(ABC):
    """Abstract interface for email provider backends.

    Methods are grouped into:
    1. Authentication and profile
    2. Search and read
    3. Send, forward, and drafts
    4. System operations (mark_read, star, archive, trash)
    5. Tag operations (add_tag, remove_tag, list_tags)
    6. Sync
    """

    # ── 1. Authentication ─────────────────────────────────────

    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_profile(self) -> dict: ...

    # ── 2. Search & Read ──────────────────────────────────────

    @abstractmethod
    def search_emails(self, query: EmailQuery) -> list[EmailData]: ...

    @abstractmethod
    def get_email_content(
        self, message_id: str, preferred_content_type: str = "text/plain"
    ) -> EmailData: ...

    @abstractmethod
    def batch_get_emails(
        self, message_ids: list[str], preferred_content_type: str = "text/plain"
    ) -> list[EmailData]: ...

    @abstractmethod
    def get_thread(self, thread_id: str) -> list[EmailData]: ...

    @abstractmethod
    def download_attachment(self, message_id: str, attachment_id: str) -> bytes: ...

    # ── 3. Send, Forward & Drafts ─────────────────────────────

    @abstractmethod
    def send_message(
        self, to: str, subject: str, body: str,
        cc: str | None = None, bcc: str | None = None,
        content_type: str = "plain", attachments: list[str] | None = None,
    ) -> dict: ...

    @abstractmethod
    def forward_message(
        self, message_id: str, to: str, comment: str | None = None
    ) -> dict: ...

    @abstractmethod
    def create_draft(
        self, to: str, subject: str, body: str,
        cc: str | None = None, bcc: str | None = None,
        content_type: str = "plain",
    ) -> dict: ...

    @abstractmethod
    def list_drafts(self, max_results: int = 10) -> list[dict]: ...

    @abstractmethod
    def send_draft(self, draft_id: str) -> dict: ...

    @abstractmethod
    def delete_draft(self, draft_id: str) -> dict: ...

    # ── 4. System Operations ──────────────────────────────────
    # Dedicated methods for operations that map differently across
    # providers. Gmail uses label add/remove; Outlook uses property
    # patches and folder moves.

    @abstractmethod
    def mark_read(self, message_id: str, read: bool = True) -> None: ...

    @abstractmethod
    def set_star(self, message_id: str, starred: bool = True) -> None: ...

    @abstractmethod
    def archive(self, message_id: str) -> None: ...

    @abstractmethod
    def trash(self, message_id: str) -> None: ...

    @abstractmethod
    def untrash(self, message_id: str) -> None: ...

    # ── 5. Tag Operations ─────────────────────────────────────
    # Gmail custom labels / Outlook categories.

    @abstractmethod
    def add_tag(self, message_id: str, tag_name: str) -> None: ...

    @abstractmethod
    def remove_tag(self, message_id: str, tag_name: str) -> None: ...

    @abstractmethod
    def list_tags(self) -> dict[str, str]: ...

    # ── 6. Sync ───────────────────────────────────────────────

    @abstractmethod
    def get_sync_state(self) -> str: ...

    @abstractmethod
    def get_new_messages(self, sync_token: str) -> list[str] | None: ...
```

### Design Decisions

**System operations vs tag operations.** Gmail conflates system state with labels (star = add `STARRED`, archive = remove `INBOX`). Outlook uses property patches (`isRead`, `flag.flagStatus`) and folder moves. Separate abstract methods avoid leaking either provider's model:

| ABC Method | Gmail Implementation | Outlook Implementation |
|---|---|---|
| `mark_read()` | Remove/add `UNREAD` label | PATCH `isRead` |
| `set_star()` | Add/remove `STARRED` label | PATCH `flag.flagStatus` |
| `archive()` | Remove `INBOX` label | Move to archive folder |
| `trash()` | `messages.trash()` | `DELETE /me/messages/{id}` |
| `add_tag()` | Add custom label ID | Append to `categories` array |
| `remove_tag()` | Remove custom label ID | Remove from `categories` array |

**`EmailData` uses `from_`** (trailing underscore) to avoid shadowing Python's `from` keyword. Providers populate this as `"Display Name <email>"` string format matching current Gmail output.

**Lazy provider import.** The factory uses `importlib.import_module` so that `import iobox` never triggers an `O365` import.

### Acceptance Criteria

- [ ] `src/iobox/providers/__init__.py` exports `get_provider`, `EmailProvider`, `EmailQuery`, `EmailData`
- [ ] `EmailProvider` ABC has dedicated methods for system ops: `mark_read`, `set_star`, `archive`, `trash`, `untrash`
- [ ] `EmailProvider` ABC has separate methods for tags: `add_tag`, `remove_tag`, `list_tags`
- [ ] `EmailQuery` includes all fields: `text`, `from_addr`, `to_addr`, `subject`, `after`, `before`, `has_attachment`, `is_unread`, `label`, `max_results`, `include_spam_trash`, `raw_query`
- [ ] `EmailData` TypedDict defines: `message_id`, `subject`, `from_`, `date`, `body`, `content_type`, `labels`, `attachments`, `thread_id`, `snippet`
- [ ] `get_provider("unknown")` raises `ValueError`
- [ ] `get_provider("outlook")` raises `ImportError` with install instructions when `O365` is not installed
- [ ] `EmailProvider` cannot be instantiated directly (ABC enforcement)

---

## 10.2 GmailProvider — Wrap Existing Code

### Problem

The existing Gmail functionality lives in standalone modules that the CLI calls directly. To support multiple providers, this code must be accessible through the `EmailProvider` ABC. The `GmailProvider` is a thin delegation wrapper — no behavior changes, preserving full backward compatibility.

### Required Changes

**File**: `src/iobox/providers/gmail.py` (new)

1. **Authentication**: `authenticate()` wraps `get_gmail_service()`, stores service as `self._service`. `get_profile()` delegates to `get_gmail_profile()`.

2. **Query translation**: `_build_gmail_query(query: EmailQuery) -> str`:

| `EmailQuery` field | Gmail query token |
|---|---|
| `from_addr` | `from:{value}` |
| `to_addr` | `to:{value}` |
| `subject` | `subject:{value}` |
| `text` | appended as-is |
| `after` | `after:{YYYY/MM/DD}` |
| `before` | `before:{YYYY/MM/DD}` |
| `has_attachment` | `has:attachment` |
| `is_unread` | `is:unread` |
| `label` | `label:{value}` |
| `raw_query` | passed verbatim, overrides all structured fields |

When `raw_query` is not set, date fields are passed as `start_date`/`end_date` to `search_emails()` to preserve its existing date-handling logic.

3. **Search**: `search_emails(query)` translates `EmailQuery` → Gmail query string, delegates to `email_search.search_emails()`.

4. **Read**: `get_email_content(message_id)` delegates to `email_retrieval.get_email_content()`, converts result via `_to_email_data()`.

5. **Normalization**: `_to_email_data(raw: dict) -> EmailData` maps Gmail's dict format to `EmailData`. The `from` key maps to `from_`.

6. **Send/forward/drafts**: Each method delegates directly:

| Method | Delegates to |
|---|---|
| `send_message()` | `compose_message()` + `email_sender.send_message()` |
| `forward_message()` | `email_sender.forward_email()` |
| `create_draft()` | `compose_message()` + `email_sender.create_draft()` |
| `list_drafts()` | `email_sender.list_drafts()` |
| `send_draft()` | `email_sender.send_draft()` |
| `delete_draft()` | `email_sender.delete_draft()` |

7. **System operations**: Map to `modify_message_labels()`:

| Method | Implementation |
|---|---|
| `mark_read(id, True)` | `remove_labels=["UNREAD"]` |
| `mark_read(id, False)` | `add_labels=["UNREAD"]` |
| `set_star(id, True)` | `add_labels=["STARRED"]` |
| `set_star(id, False)` | `remove_labels=["STARRED"]` |
| `archive(id)` | `remove_labels=["INBOX"]` |
| `add_tag(id, name)` | `resolve_label_name()` then `add_labels=[label_id]` |
| `remove_tag(id, name)` | `resolve_label_name()` then `remove_labels=[label_id]` |

8. **Trash**: Delegates to `trash_message()` / `untrash_message()`.

9. **Attachments**: Delegates to `download_attachment()`.

10. **Sync**: `get_sync_state()` returns `historyId` from Gmail profile. `get_new_messages()` delegates to `email_search.get_new_messages()`.

### Acceptance Criteria

- [ ] `GmailProvider` implements every `EmailProvider` abstract method
- [ ] Every method delegates to existing functions — no direct Gmail API calls in `gmail.py`
- [ ] `_build_gmail_query()` correctly translates each `EmailQuery` field
- [ ] `_build_gmail_query()` returns `raw_query` verbatim when set
- [ ] `_to_email_data()` maps all Gmail dict keys to `EmailData` fields
- [ ] System operation mappings match the table above
- [ ] All existing unit tests continue to pass without modification
- [ ] New tests in `tests/unit/test_gmail_provider.py` cover each delegation path

---

## 10.3 Outlook Authentication

### Problem

iobox needs a parallel authentication module for Microsoft 365. The `python-o365` library bundles MSAL internally and provides its own `Account` class with built-in auth and token management.

### App Registration (Microsoft Entra)

Document these steps in user-facing docs:

1. Go to [Microsoft Entra admin center](https://entra.microsoft.com) > Identity > Applications > App registrations
2. Click "New registration"
3. Set name (e.g. "iobox"), select "Accounts in any organizational directory and personal Microsoft accounts"
4. Under Redirect URI, select "Mobile and desktop applications", set `http://localhost`
5. Note the **Application (client) ID** and **Directory (tenant) ID**
6. Under API Permissions, add Microsoft Graph delegated permissions: `Mail.ReadWrite` and `Mail.Send`
7. For public client (desktop) apps, no client secret is needed

### Required Changes

**File**: `src/iobox/providers/outlook_auth.py` (new)

```python
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID", "")
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_TENANT_ID = os.getenv("OUTLOOK_TENANT_ID", "common")
CREDENTIALS_DIR = os.getenv("CREDENTIALS_DIR", os.getcwd())
OUTLOOK_TOKEN_DIR = os.path.join(CREDENTIALS_DIR, "tokens", "outlook")
OUTLOOK_SCOPES = ["Mail.ReadWrite", "Mail.Send"]


def get_outlook_account(*, device_code: bool = False) -> "Account":
    from O365 import Account, FileSystemTokenBackend

    if not OUTLOOK_CLIENT_ID:
        raise ValueError(
            "OUTLOOK_CLIENT_ID environment variable is required. "
            "Register an app at https://entra.microsoft.com"
        )

    credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
    os.makedirs(OUTLOOK_TOKEN_DIR, exist_ok=True)
    token_backend = FileSystemTokenBackend(
        token_path=OUTLOOK_TOKEN_DIR, token_filename="o365_token.txt"
    )

    account = Account(credentials, tenant_id=OUTLOOK_TENANT_ID,
                      token_backend=token_backend)

    if not account.is_authenticated:
        if device_code:
            result = account.authenticate(scopes=OUTLOOK_SCOPES,
                                          grant_type="device_code")
        else:
            result = account.authenticate(scopes=OUTLOOK_SCOPES)
        if not result:
            raise RuntimeError("Outlook authentication failed.")
        logger.info("Successfully authenticated with Microsoft 365")

    return account


def check_outlook_auth_status() -> dict:
    from O365 import Account, FileSystemTokenBackend
    token_path = os.path.join(OUTLOOK_TOKEN_DIR, "o365_token.txt")
    status = {
        "authenticated": False,
        "client_id_configured": bool(OUTLOOK_CLIENT_ID),
        "tenant_id": OUTLOOK_TENANT_ID,
        "token_file_exists": os.path.exists(token_path),
        "token_path": token_path,
    }
    if not status["client_id_configured"] or not status["token_file_exists"]:
        return status
    try:
        credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
        token_backend = FileSystemTokenBackend(
            token_path=OUTLOOK_TOKEN_DIR, token_filename="o365_token.txt"
        )
        account = Account(credentials, tenant_id=OUTLOOK_TENANT_ID,
                          token_backend=token_backend)
        status["authenticated"] = account.is_authenticated
    except Exception as e:
        status["error"] = str(e)
    return status
```

**Environment variables** (`.env`):
```bash
OUTLOOK_CLIENT_ID=your-application-client-id
OUTLOOK_CLIENT_SECRET=              # optional for public client apps
OUTLOOK_TENANT_ID=common            # 'common' for multi-tenant
```

### Acceptance Criteria

- [ ] `OUTLOOK_CLIENT_ID` required; clear error if missing
- [ ] `OUTLOOK_CLIENT_SECRET` optional (empty default for public apps)
- [ ] `OUTLOOK_TENANT_ID` defaults to `common`
- [ ] Token persisted at `$CREDENTIALS_DIR/tokens/outlook/o365_token.txt`
- [ ] `get_outlook_account()` triggers browser flow on first call
- [ ] Subsequent calls use cached/refreshed tokens silently
- [ ] `get_outlook_account(device_code=True)` uses device code flow
- [ ] `check_outlook_auth_status()` returns state without triggering auth
- [ ] Scopes: `['Mail.ReadWrite', 'Mail.Send']`
- [ ] Unit tests mock `O365.Account` and verify flow selection

---

## 10.4 OutlookProvider — Read Operations

### Problem

iobox needs to search, retrieve, and download emails from Outlook mailboxes. The `OutlookProvider` must convert python-o365 `Message` objects into the normalized `EmailData` dict that downstream code (markdown converter, file manager) expects.

### Required Changes

**File**: `src/iobox/providers/outlook.py` (new)

1. **`search_emails(query)`** — Build python-o365 `Query` from `EmailQuery` fields, call `folder.get_messages()`. When `text` is present, use `$search` path; otherwise use `$filter` path (see 10.7).

2. **`get_email_content(message_id)`** — `mailbox.get_message(object_id=id)`, convert via `_message_to_email_data()`.

3. **`batch_get_emails(message_ids)`** — Loop `get_message()` per ID (Graph's list endpoint returns full content, reducing the need for batching vs Gmail).

4. **`get_thread(thread_id)`** — Filter by `conversationId`:
   ```python
   q = inbox.new_query().on_attribute("conversationId").equals(thread_id)
   messages = inbox.get_messages(query=q, order_by="receivedDateTime asc")
   ```

5. **`download_attachment(message_id, attachment_id)`** — Fetch message, iterate attachments, return matching content as `bytes`.

6. **`_message_to_email_data(msg, include_body=True)`** — Convert python-o365 `Message` to `EmailData`:

| python-o365 property | `EmailData` field |
|---|---|
| `msg.object_id` | `message_id` |
| `msg.conversation_id` | `thread_id` |
| `msg.subject` | `subject` |
| `f"{msg.sender.name} <{msg.sender.address}>"` | `from_` |
| `msg.received.isoformat()` | `date` |
| `msg.categories` | `labels` |
| `msg.body_preview` | `snippet` |
| `msg.body` (HTML) | `body` |
| `'text/html'` | `content_type` |
| attachment metadata | `attachments` |

**Body content handling**: Graph returns HTML body by default. We use `msg.body` (HTML) and pass it through the existing `html2text` converter in `markdown_converter.py`, matching the Gmail pipeline. We do NOT use `get_body_text()` (BeautifulSoup stripping) — `html2text` produces better markdown.

**Message ID stability**: All Graph requests must include `Prefer: IdType="ImmutableId"` header to prevent IDs from changing when messages move between folders:
```python
self._account.con.session.headers.update({
    "Prefer": 'IdType="ImmutableId"'
})
```

### Acceptance Criteria

- [ ] `search_emails()` translates `EmailQuery` fields to python-o365 `Query` filters
- [ ] `search_emails()` supports `from_addr`, `subject`, `after`, `before`, `has_attachment`
- [ ] `search_emails()` supports `raw_query` for KQL passthrough
- [ ] `get_email_content()` returns HTML body in `body` field with `content_type='text/html'`
- [ ] HTML body passes through existing `html2text` converter correctly
- [ ] `get_thread()` filters by `conversationId` and returns chronological order
- [ ] `download_attachment()` returns `bytes` for matching attachment ID
- [ ] `_message_to_email_data()` produces `EmailData` compatible with `markdown_converter.py`
- [ ] Outlook categories mapped to `labels` list
- [ ] Immutable ID header set on all Graph requests
- [ ] Unit tests mock python-o365 `Message` objects and verify output

---

## 10.5 OutlookProvider — Write Operations

### Problem

Gmail write operations require building raw RFC 2822 MIME messages. Microsoft Graph uses structured JSON and provides native forward/reply endpoints, making the implementation simpler. python-o365 wraps these into a high-level `Message` object.

### Required Changes

**File**: `src/iobox/providers/outlook.py`

1. **`send_message(to, subject, body, **kwargs)`**:
   ```python
   msg = self._account.mailbox().new_message()
   msg.to.add(to)
   msg.subject = subject
   msg.body = body
   for path in (kwargs.get("attachments") or []):
       msg.attachments.add(path)
   msg.send()
   ```
   python-o365 handles attachment sizing internally: <3 MB inline, 3-150 MB via upload session.

2. **`forward_message(message_id, to, comment=None)`** — Native Graph forward:
   ```python
   msg = self._account.mailbox().get_message(object_id=message_id)
   fwd = msg.forward()
   fwd.to.add(to)
   if comment:
       fwd.body = comment
   fwd.send()
   ```
   No manual "---------- Forwarded message ----------" body construction needed.

3. **`create_draft(to, subject, body, **kwargs)`** — `new_message()` → set fields → `.save_draft()`

4. **`list_drafts(max_results)`** — `mailbox.drafts_folder().get_messages(limit=max_results)`

5. **`send_draft(draft_id)`** — `get_message(object_id=draft_id)` → `.send()`

6. **`delete_draft(draft_id)`** — `get_message(object_id=draft_id)` → `.delete()`

### Acceptance Criteria

- [ ] `send_message()` sends via `mailbox.new_message()` with to, cc, bcc, subject, body
- [ ] `send_message()` supports file attachments via `msg.attachments.add(path)`
- [ ] `forward_message()` uses python-o365's native forward (not manual reconstruction)
- [ ] `forward_message()` supports optional comment text
- [ ] `create_draft()` saves via `msg.save_draft()` and returns message ID
- [ ] `list_drafts()` queries Drafts folder with configurable limit
- [ ] `send_draft()` fetches by ID and calls `.send()`
- [ ] `delete_draft()` fetches by ID and calls `.delete()`
- [ ] Unit tests for all six methods with mocked python-o365 objects

---

## 10.6 OutlookProvider — Organization (Labels/Folders/Trash)

### Problem

Gmail treats all organizational operations as label manipulation. Outlook uses separate API patterns for each: boolean properties, flag objects, folder moves, and category arrays. Each system operation maps differently.

### Gmail-to-Outlook Operation Mapping

| Abstract Method | Gmail | Outlook |
|---|---|---|
| `mark_read(id, True)` | Remove `UNREAD` label | PATCH `isRead = true` |
| `set_star(id, True)` | Add `STARRED` label | PATCH `flag.flagStatus = "flagged"` |
| `archive(id)` | Remove `INBOX` label | `message.move(archive_folder)` |
| `add_tag(id, name)` | Add label ID | Append to `categories` array |
| `remove_tag(id, name)` | Remove label ID | Remove from `categories` array |
| `trash(id)` | `messages.trash()` | `message.delete()` (soft delete) |
| `untrash(id)` | `messages.untrash()` | `message.move(inbox_folder)` |
| `list_tags()` | `labels.list()` | `GET /me/outlook/masterCategories` |

### Required Changes

**File**: `src/iobox/providers/outlook.py`

1. **`mark_read(message_id, read=True)`**: `msg.mark_as_read()` / `msg.mark_as_unread()`
2. **`set_star(message_id, starred=True)`**: Set `msg.flag = {"flagStatus": "flagged"/"notFlagged"}`, call `msg.save_message()`
3. **`archive(message_id)`**: `msg.move(mailbox.archive_folder())`
4. **`add_tag/remove_tag`**: Modify `msg.categories` list, call `msg.save_message()`
5. **`trash(message_id)`**: `msg.delete()` (soft delete to Deleted Items)
6. **`untrash(message_id)`**: `msg.move(mailbox.inbox_folder())`
7. **`list_tags()`**: Fetch master categories, return `{name: name}` mapping

**Batch operations note**: Gmail's `batchModify` applies changes to up to 1000 messages in one call. Graph has no equivalent — use `$batch` endpoint (20 requests/batch) or sequential loop. Implement internal chunking so callers don't see the difference.

### Acceptance Criteria

- [ ] `mark_read()` toggles `isRead` correctly
- [ ] `set_star()` toggles `flag.flagStatus` correctly
- [ ] `archive()` moves to archive well-known folder
- [ ] `add_tag()` appends to categories without duplicates
- [ ] `remove_tag()` removes from categories (no-op if absent)
- [ ] `trash()` soft-deletes to Deleted Items
- [ ] `untrash()` moves from Deleted Items to Inbox
- [ ] `list_tags()` returns master category list
- [ ] Batch operations on 2+ messages use `$batch` with 20-request chunking
- [ ] Unit tests for all methods with mocked python-o365 objects

---

## 10.7 Query Translation Layer

### Problem

Gmail and Microsoft Graph use fundamentally different query syntaxes. Gmail accepts a single `q=` string. Graph uses OData `$filter` for structured queries and KQL `$search` for text search — and the two **cannot be combined** on message collections.

### Gmail Translation

**File**: `src/iobox/providers/gmail.py`

```python
def _build_gmail_query(self, query: EmailQuery) -> str:
    if query.raw_query:
        return query.raw_query
    parts: list[str] = []
    if query.from_addr:
        parts.append(f"from:{query.from_addr}")
    if query.to_addr:
        parts.append(f"to:{query.to_addr}")
    if query.subject:
        parts.append(f"subject:{query.subject}")
    if query.has_attachment:
        parts.append("has:attachment")
    if query.is_unread is True:
        parts.append("is:unread")
    if query.label:
        parts.append(f"label:{query.label}")
    if query.text:
        parts.append(query.text)
    return " ".join(parts)
```

Date fields (`after`, `before`) are passed to `search_emails()` as `start_date`/`end_date` parameters.

### Outlook Translation

**File**: `src/iobox/providers/outlook.py`

Strategy for the `$search`/`$filter` constraint:

1. **If `text` is present**: use `$search` exclusively — build KQL string combining all fields
2. **If `text` is absent**: use `$filter` via python-o365 `Query` builder

**`$filter` path** (no free-text):
```python
def _build_outlook_filter(self, query: EmailQuery) -> Query:
    q = self._mailbox.new_query()
    if query.from_addr:
        q = q.on_attribute("from/emailAddress/address").equals(query.from_addr)
    if query.subject:
        q = q.on_attribute("subject").contains(query.subject)
    if query.after:
        q = q.on_attribute("receivedDateTime").greater_equal(
            datetime.combine(query.after, datetime.min.time())
        )
    if query.before:
        q = q.on_attribute("receivedDateTime").less(
            datetime.combine(query.before, datetime.min.time())
        )
    if query.has_attachment:
        q = q.on_attribute("hasAttachments").equals(True)
    return q
```

**`$search` path** (free-text present):
```python
def _build_outlook_search(self, query: EmailQuery) -> str:
    parts: list[str] = []
    if query.from_addr:
        parts.append(f"from:{query.from_addr}")
    if query.subject:
        parts.append(f"subject:{query.subject}")
    if query.after:
        parts.append(f"received>={query.after.isoformat()}")
    if query.before:
        parts.append(f"received<{query.before.isoformat()}")
    if query.has_attachment:
        parts.append("hasAttachments:true")
    if query.text:
        parts.append(f'"{query.text}"')
    return " ".join(parts)
```

### Raw Query Passthrough

```bash
# Gmail raw syntax
iobox search -q "from:newsletter@example.com has:attachment newer_than:7d" --provider gmail

# KQL raw syntax
iobox search -q "from:newsletter@example.com hasAttachments:true received>=2026-02-26" --provider outlook
```

`-q` populates `EmailQuery.raw_query`. Preserves full backward compatibility.

### New Structured CLI Options

Cross-provider options that map to `EmailQuery` fields:

| CLI Option | EmailQuery Field |
|---|---|
| `--from` | `from_addr` |
| `--to` | `to_addr` |
| `--subject` | `subject` |
| `--after` | `after` |
| `--before` | `before` |
| `--has-attachment` | `has_attachment` |

When `-q` is also provided, it takes precedence (sets `raw_query`, structured fields ignored).

### Acceptance Criteria

- [ ] Gmail translation produces correct query strings for all field combinations
- [ ] Outlook `$filter` path used when no free-text present
- [ ] Outlook `$search` path used when `text` field populated
- [ ] `$search` and `$filter` never combined in a single Graph request
- [ ] `raw_query` passes through verbatim to both providers
- [ ] Structured CLI options produce identical results across providers
- [ ] Unit tests for both translation paths with all field combinations

---

## 10.8 CLI Refactor — Provider Selection

### Problem

Every CLI command imports and calls Gmail-specific functions directly. Commands must route through the provider abstraction layer instead.

### Required Changes

**File**: `src/iobox/cli.py`

1. **Global `--provider` option** in `app.callback()`:
   ```python
   @app.callback()
   def main(
       ctx: typer.Context,
       version_flag: bool = version_callback,
       provider: str = typer.Option(
           "gmail", "--provider",
           help="Email provider: gmail or outlook",
           envvar="IOBOX_PROVIDER",
       ),
   ):
       from iobox.providers import get_provider
       ctx.ensure_object(dict)
       p = get_provider(provider)
       p.authenticate()
       ctx.obj["provider"] = p
       ctx.obj["provider_name"] = provider
   ```

2. **Command refactoring pattern**:

   Before:
   ```python
   service = get_gmail_service()
   label_map = get_label_map(service)
   results = search_emails(service, query, max_results, days, ...)
   ```

   After:
   ```python
   provider = ctx.obj["provider"]
   eq = EmailQuery(raw_query=query, max_results=max_results, after=..., before=...)
   results = provider.search_emails(eq)
   ```

3. **`auth-status` command** — Show provider-specific information:
   ```python
   @app.command()
   def auth_status(ctx: typer.Context):
       provider_name = ctx.obj["provider_name"]
       if provider_name == "gmail":
           # existing Gmail auth status logic
       elif provider_name == "outlook":
           from iobox.providers.outlook_auth import check_outlook_auth_status
           status = check_outlook_auth_status()
           # display Outlook-specific status
   ```

4. **Backward compatibility**: All existing commands work unchanged when provider is `gmail` (default). `IOBOX_PROVIDER=outlook` env var allows default override.

### Acceptance Criteria

- [ ] `--provider` option available on all commands (default: `gmail`)
- [ ] `IOBOX_PROVIDER` environment variable sets default provider
- [ ] All commands use `ctx.obj["provider"]` instead of direct Gmail imports
- [ ] Existing Gmail workflows produce identical output with no flags changed
- [ ] `auth-status` displays provider-appropriate information
- [ ] `--provider outlook` fails gracefully with install instructions if `O365` not installed

---

## 10.9 Incremental Sync for Outlook

### Problem

Gmail's incremental sync uses a global `historyId`. Microsoft Graph uses per-folder delta queries with opaque `deltaLink` URLs. The existing `SyncState` class stores a single `last_history_id`.

### Key Differences

| Aspect | Gmail | Outlook (Graph) |
|---|---|---|
| Scope | Global (entire mailbox) | Per-folder |
| Token type | Numeric `historyId` | Opaque `deltaLink` URL |
| Expiry | History may be unavailable | Returns 410 Gone |
| Granularity | `messageAdded`, `messageDeleted` | Full message with `@removed` annotation |

### Required Changes

**File**: `src/iobox/file_manager.py`

Extend `SyncState` to support both providers:

```python
class SyncState:
    FILENAME = ".iobox-sync.json"

    def __init__(self, directory: str):
        self.filepath = os.path.join(directory, self.FILENAME)
        self.provider: str | None = None
        self.last_history_id: str | None = None        # Gmail
        self.delta_links: dict[str, str] = {}           # Outlook: folder_id → deltaLink
        self.last_sync_time: str | None = None
        self.synced_message_ids: list[str] = []
```

**File**: `src/iobox/providers/outlook.py`

```python
def get_new_messages(self, sync_token: str) -> list[str] | None:
    delta_link = sync_token  # stored deltaLink URL
    try:
        response = self._account.con.get(delta_link)
    except Exception as e:
        if "410" in str(e):  # deltaLink expired
            return None
        raise
    new_ids = [msg["id"] for msg in response.json().get("value", [])
               if "@removed" not in msg]
    # Store new deltaLink for next sync
    return new_ids
```

**Fallback**: When deltaLink expires (410 Gone), return `None` — CLI falls back to full query, same pattern as Gmail historyId expiry.

**Message ID stability**: Set `Prefer: IdType="ImmutableId"` header on all Graph requests (see 10.4).

### Acceptance Criteria

- [ ] `SyncState` supports both `last_history_id` (Gmail) and `delta_links` (Outlook)
- [ ] `OutlookProvider.get_new_messages()` returns new IDs from inbox delta
- [ ] Expired deltaLink (410 Gone) triggers graceful fallback to full query
- [ ] All Graph requests include `Prefer: IdType="ImmutableId"` header
- [ ] Unit tests for delta response parsing and 410 handling

---

## 10.10 Testing Strategy

### Unit Tests

**GmailProvider**: Mock `googleapiclient` service, verify delegation paths. Existing tests continue to pass.

**OutlookProvider**: Mock `O365.Account`, `Mailbox`, `Message`. Test each method in isolation.

### ABC Contract Tests

**File**: `tests/unit/test_provider_contract.py`

Shared test suite runs against both providers with mocked backends, verifying:
- All methods return correct types
- `EmailData` dicts have required keys
- System operations (mark_read, star, etc.) work correctly

### Query Translation Tests

**File**: `tests/unit/test_query_translation.py`

- Each `EmailQuery` field individually and combined
- `$search` vs `$filter` path selection for Outlook
- `raw_query` passthrough for both providers

### New Test Files

| File | Contents |
|---|---|
| `tests/unit/test_gmail_provider.py` | GmailProvider delegation tests |
| `tests/unit/test_outlook_provider.py` | OutlookProvider tests with mocked O365 |
| `tests/unit/test_provider_contract.py` | Shared ABC contract tests |
| `tests/unit/test_query_translation.py` | Query builder tests |
| `tests/unit/test_outlook_auth.py` | Auth flow tests |
| `tests/unit/test_outlook_sync.py` | Delta sync tests |
| `tests/integration/test_provider_parity.py` | Cross-provider output format tests |
| `tests/fixtures/mock_outlook_responses.py` | Mock O365 objects |

### Acceptance Criteria

- [ ] GmailProvider tests pass with mocked service
- [ ] OutlookProvider tests cover all abstract methods
- [ ] Contract tests verify both providers satisfy ABC interface
- [ ] Query translation tests cover all fields for both providers
- [ ] Integration tests confirm identical output format across providers
- [ ] Delta sync tests cover normal, expired deltaLink, and initial sync

---

## Implementation Order

1. **Provider abstraction layer** (10.1) — ABC, EmailQuery, EmailData, factory
2. **GmailProvider wrapper** (10.2) — Wrap existing code, verify no regressions
3. **CLI refactor** (10.8) — `--provider` option, route through provider interface
4. **Query translation** (10.7) — Gmail translation, structured CLI options
5. **Outlook auth** (10.3) — MSAL via python-o365, env var config
6. **Outlook read ops** (10.4) — Search, get content, attachments
7. **Outlook write ops** (10.5) — Send, forward, drafts
8. **Outlook organization** (10.6) — Categories, folders, star, read, trash
9. **Outlook sync** (10.9) — Delta query, SyncState changes, immutable IDs
10. **Cross-provider testing** (10.10) — Contract tests, parity tests

Steps 1-4 can ship independently (pure refactor, no new features). Steps 5-9 add Outlook support incrementally. Step 10 runs continuously.

---

## Files Created/Modified

| Action | File |
|---|---|
| Create | `src/iobox/providers/__init__.py` |
| Create | `src/iobox/providers/base.py` |
| Create | `src/iobox/providers/gmail.py` |
| Create | `src/iobox/providers/outlook.py` |
| Create | `src/iobox/providers/outlook_auth.py` |
| Modify | `src/iobox/cli.py` |
| Modify | `src/iobox/file_manager.py` |
| Modify | `pyproject.toml` |
| Create | `tests/unit/test_gmail_provider.py` |
| Create | `tests/unit/test_outlook_provider.py` |
| Create | `tests/unit/test_provider_contract.py` |
| Create | `tests/unit/test_query_translation.py` |
| Create | `tests/unit/test_outlook_auth.py` |
| Create | `tests/unit/test_outlook_sync.py` |
| Create | `tests/integration/test_provider_parity.py` |
| Create | `tests/fixtures/mock_outlook_responses.py` |
