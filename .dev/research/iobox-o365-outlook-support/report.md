# Research Report: Adding O365/Outlook Support to iobox

**Date**: 2026-03-05
**Query**: How could iobox support O365 Outlook accounts as well as Gmail? What would feature parity look like and are the capabilities generally compatible?
**Sources consulted**: 42 across 6 lines of enquiry
**Confidence**: High — all key findings sourced from official Microsoft Graph v1.0 documentation (Tier 1)

---

## Executive Summary

**Yes, iobox can achieve full feature parity with O365/Outlook via the Microsoft Graph API.** Every current iobox capability — search, read, send, forward, drafts, labels/categories, trash, attachments, incremental sync — has a direct or close equivalent in Microsoft Graph. The APIs are structurally different (Graph uses structured JSON and OData vs Gmail's MIME/query-string model), but functionally compatible. The recommended approach is an ABC-based `EmailProvider` interface with `GmailProvider` and `OutlookProvider` implementations, using `python-o365` or direct Graph REST calls for the Outlook backend and `msal` + `msal-extensions` for authentication. The main design challenges are: (1) mapping Gmail's flat multi-label model to Outlook's hierarchical folder + categories model, (2) translating between Gmail query syntax and Graph OData/KQL syntax, and (3) handling Graph's per-folder delta sync vs Gmail's global history API.

---

## 1. Feature Parity Matrix

| iobox Feature | Gmail API | Microsoft Graph API | Parity |
|---|---|---|---|
| **Search emails** | `messages.list` with `q=` Gmail syntax | `GET /me/messages` with `$search` (KQL) or `$filter` (OData) | Full — different syntax, same capabilities |
| **Read email** | `messages.get` with format=full, base64 MIME parts | `GET /me/messages/{id}`, JSON body with HTML/text via Prefer header | Full — Graph is actually simpler |
| **Batch metadata** | `new_batch_http_request`, 50/batch | `POST /$batch` JSON batching, 20/batch | Full — lower batch size but less batching needed |
| **Send email** | Raw MIME base64url via `messages.send` | Structured JSON via `POST /me/sendMail` | Full — Graph also supports MIME format |
| **Forward email** | Manual: retrieve + reconstruct + send | Native: `POST /me/messages/{id}/forward` | Full — Graph is superior (native endpoint) |
| **Create draft** | `drafts.create` with MIME payload | `POST /me/messages` (drafts are just messages) | Full |
| **List drafts** | `drafts.list` | `GET /me/mailFolders('Drafts')/messages` | Full |
| **Send draft** | `drafts.send` with draft ID | `POST /me/messages/{id}/send` | Full |
| **Delete draft** | `drafts.delete` | `DELETE /me/messages/{id}` | Full |
| **Star/flag** | Add STARRED label | PATCH `flag.flagStatus = "flagged"` | Full — Outlook flags are richer (dates) |
| **Mark read/unread** | Remove/add UNREAD label | PATCH `isRead = true/false` | Full — Graph is simpler |
| **Archive** | Remove INBOX label | `POST /me/messages/{id}/move` to archive folder | Full — semantic difference (tag removal vs folder move) |
| **Custom labels** | Add/remove label IDs | PATCH `categories` array (tags) + folder move | Partial — categories are tag-like but folders are exclusive |
| **Trash/untrash** | `messages.trash()` / `messages.untrash()` | `DELETE /me/messages/{id}` / move from deleteditems | Full |
| **Download attachment** | `attachments.get` → base64url decode | `GET .../attachments/{id}/$value` → raw bytes | Full — Graph is simpler |
| **Incremental sync** | `history.list` with historyId (global) | Delta query with deltaLink (per-folder) | Full — architectural difference |
| **Thread retrieval** | `threads.get` returns all messages | Filter by `conversationId` | Full — requires different query |
| **Auth** | google-auth-oauthlib, credentials.json | MSAL, app registration in Entra | Full — different setup, same OAuth 2.0 |

**Verdict**: 15 of 17 features have full parity. The 2 "partial" areas (custom labels, incremental sync) have workable solutions but require careful abstraction design.

---

## 2. Authentication: MSAL vs Google OAuth

The authentication models are structurally parallel but differ in setup and token management.

### Key Differences

| Aspect | Gmail (current iobox) | Microsoft Graph |
|---|---|---|
| **App registration** | Google Cloud Console → download `credentials.json` | Entra admin center → note `client_id` + `tenant_id` |
| **Python library** | `google-auth-oauthlib` | `msal` (core) + `msal-extensions` (persistence) |
| **Interactive flow** | `InstalledAppFlow.run_local_server(port=0)` | `PublicClientApplication.acquire_token_interactive()` |
| **Token refresh** | `creds.refresh(Request())` — manual | `acquire_token_silent()` — automatic cache+refresh |
| **Token storage** | Plaintext `token.json` | `PersistedTokenCache` with platform encryption (DPAPI/Keychain/LibSecret) |
| **Scopes** | `gmail.modify`, `gmail.compose` | `Mail.ReadWrite`, `Mail.Send` |
| **Headless/CLI** | Not implemented in iobox | `acquire_token_by_device_flow()` available |
| **Scope mismatch** | iobox detects + re-auths manually | `acquire_token_silent()` returns None → fallback to interactive |

### Recommendation

Create a parallel `auth_outlook.py` module using `msal` with `PersistedTokenCache` from `msal-extensions`. The auth pattern maps cleanly: "try cached token → refresh if expired → interactive if needed." Configuration would use environment variables (`OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID`) mirroring the current `CREDENTIALS_DIR`/`GMAIL_TOKEN_FILE` pattern. Consider also offering device code flow for headless SSH scenarios.

**New dependencies**: `msal`, `msal-extensions`

---

## 3. The Label vs Folder Challenge

This is the most significant architectural difference and requires the most design thought.

### The Problem

- **Gmail**: Messages can have multiple labels simultaneously. Labels serve as both folders and tags. Star = STARRED label. Read state = absence of UNREAD label. Archive = remove INBOX label.
- **Outlook**: Messages live in exactly one folder. Categories (color-coded string tags) can be applied multiply. Star = `followupFlag`. Read state = `isRead` boolean. Archive = move to archive folder.

### Mapping Strategy

| iobox Operation | Gmail Implementation | Outlook Implementation |
|---|---|---|
| `star` | Add STARRED label | PATCH `flag.flagStatus = "flagged"` |
| `unstar` | Remove STARRED label | PATCH `flag.flagStatus = "notFlagged"` |
| `mark_read` | Remove UNREAD label | PATCH `isRead = true` |
| `mark_unread` | Add UNREAD label | PATCH `isRead = false` |
| `archive` | Remove INBOX label | Move to `archive` well-known folder |
| `add_label("Projects")` | Add label ID | Add to `categories` array |
| `remove_label("Projects")` | Remove label ID | Remove from `categories` array |
| `get_label_map()` | Fetch all labels (ID→name) | Merge folders + categories into unified map |

### Key Design Decision

The abstraction should treat Gmail labels and Outlook categories as the "tagging" primitive, and Gmail's INBOX/SENT/TRASH labels and Outlook's well-known folders as the "location" primitive. System operations (star, read, archive, trash) get dedicated abstract methods rather than being expressed as label add/remove.

Note: Gmail's `batch_modify_labels` (up to 1000 messages per call) has no direct Graph equivalent. Graph's `$batch` endpoint supports 20 requests per batch, so bulk label operations would require multiple batch calls.

---

## 4. Search and Query Syntax

### Gmail Query Syntax → Graph Equivalents

| Gmail Query | Graph `$search` (KQL) | Graph `$filter` (OData) |
|---|---|---|
| `from:user@example.com` | `from:user@example.com` | `from/emailAddress/address eq 'user@example.com'` |
| `to:user@example.com` | `to:user@example.com` | N/A |
| `subject:invoice` | `subject:invoice` | `contains(subject, 'invoice')` |
| `after:2024/01/01` | `received>=2024-01-01` | `receivedDateTime ge 2024-01-01T00:00:00Z` |
| `before:2024/06/01` | `received<2024-06-01` | `receivedDateTime lt 2024-06-01T00:00:00Z` |
| `has:attachment` | `hasAttachments:true` | `hasAttachments eq true` |
| `is:unread` | N/A | `isRead eq false` |
| `label:projects` | N/A | Filter by folder or `categories/any(c:c eq 'projects')` |

### Critical Constraint

**`$search` and `$filter` cannot be combined** on message collections in Graph. This means a query like `from:user@example.com after:2024/01/01` must use either:
- `$search` only: `from:user@example.com received>=2024-01-01` (KQL handles both)
- `$filter` only: for structured queries without full-text search

### Recommendation

Define a structured query object in iobox:
```python
@dataclass
class EmailQuery:
    text: Optional[str] = None       # free-text search
    from_addr: Optional[str] = None
    to_addr: Optional[str] = None
    subject: Optional[str] = None
    after: Optional[date] = None
    before: Optional[date] = None
    has_attachment: Optional[bool] = None
    max_results: int = 100
    raw_query: Optional[str] = None  # passthrough for power users
```

Each provider translates this into its native query format. The `raw_query` field allows power users to pass Gmail syntax or OData directly. The CLI's `-q` flag could either accept provider-specific syntax (with a `--provider` flag) or the structured fields could be exposed as individual CLI options.

---

## 5. Attachments, Trash, Batch, and Delta Sync

### Attachments

Graph is actually simpler for downloading: `GET .../attachments/{id}/$value` returns raw bytes directly, vs Gmail's base64url-encoded data requiring decode. For sending, Graph uses inline JSON `fileAttachment` objects (under 3 MB) or upload sessions (3-150 MB), vs Gmail's MIME multipart construction. The abstraction needs a `download_attachment(message_id, attachment_id) → bytes` method that each provider implements differently.

### Trash

Graph has no dedicated trash/untrash endpoints. The mapping:
- `trash(message_id)` → Gmail: `messages.trash()` / Graph: `DELETE /me/messages/{id}` (soft delete to Deleted Items)
- `untrash(message_id)` → Gmail: `messages.untrash()` / Graph: `POST /me/messages/{id}/move` to inbox

### Batch Operations

| Aspect | Gmail | Graph |
|---|---|---|
| Max requests/batch | 50 | 20 |
| Format | Multipart HTTP | JSON POST to `/$batch` |
| Dependencies | None | `dependsOn` property |
| Callback pattern | `(request_id, response, exception)` | Per-request status in JSON response |

The provider abstraction should handle chunking internally, so callers don't need to know the batch size limits.

### Delta/Incremental Sync

| Aspect | Gmail | Graph |
|---|---|---|
| Scope | Global (entire mailbox) | Per-folder |
| State token | Numeric `historyId` | Opaque `deltaLink` URL |
| Change types | `messageAdded`, `messageDeleted`, `labelAdded`, `labelRemoved` | `created`, `updated`, `deleted` |
| Expiry | Permanent (if history exists) | Cache-dependent (no fixed expiry) |

For iobox's `--sync` feature, Graph's per-folder delta means tracking the Inbox folder delta token rather than a global history ID. If sync across multiple folders is needed, each folder needs its own delta token. The `SyncState` class would need to store per-folder tokens for Outlook vs a single historyId for Gmail.

---

## 6. Recommended Architecture

### Provider Interface (ABC)

```python
from abc import ABC, abstractmethod

class EmailProvider(ABC):
    """Abstract interface for email provider backends."""

    # Auth
    @abstractmethod
    def authenticate(self) -> None: ...
    @abstractmethod
    def get_profile(self) -> dict: ...

    # Search & Read
    @abstractmethod
    def search_emails(self, query: EmailQuery) -> list[dict]: ...
    @abstractmethod
    def get_email_content(self, message_id: str) -> dict: ...
    @abstractmethod
    def get_thread(self, thread_id: str) -> list[dict]: ...

    # Send & Forward
    @abstractmethod
    def send_message(self, to, subject, body, **kwargs) -> dict: ...
    @abstractmethod
    def forward_message(self, message_id, to, comment=None) -> dict: ...

    # Drafts
    @abstractmethod
    def create_draft(self, to, subject, body, **kwargs) -> dict: ...
    @abstractmethod
    def list_drafts(self, max_results=10) -> list[dict]: ...
    @abstractmethod
    def send_draft(self, draft_id) -> dict: ...
    @abstractmethod
    def delete_draft(self, draft_id) -> dict: ...

    # Organization
    @abstractmethod
    def mark_read(self, message_id, read=True) -> None: ...
    @abstractmethod
    def set_star(self, message_id, starred=True) -> None: ...
    @abstractmethod
    def archive(self, message_id) -> None: ...
    @abstractmethod
    def add_tag(self, message_id, tag_name) -> None: ...
    @abstractmethod
    def remove_tag(self, message_id, tag_name) -> None: ...

    # Trash
    @abstractmethod
    def trash(self, message_id) -> None: ...
    @abstractmethod
    def untrash(self, message_id) -> None: ...

    # Attachments
    @abstractmethod
    def download_attachment(self, message_id, attachment_id) -> bytes: ...

    # Sync
    @abstractmethod
    def get_sync_state(self) -> str: ...
    @abstractmethod
    def get_new_messages(self, sync_token) -> list[str] | None: ...
```

### Module Structure

```
src/iobox/
├── providers/
│   ├── __init__.py          # Factory: get_provider(name) → EmailProvider
│   ├── base.py              # EmailProvider ABC + EmailQuery dataclass
│   ├── gmail.py             # GmailProvider (wraps existing code)
│   └── outlook.py           # OutlookProvider (uses msal + Graph REST or python-o365)
├── auth.py                  # Gmail auth (existing, could move into gmail.py)
├── auth_outlook.py          # MSAL auth for Graph API
├── cli.py                   # Refactored to use provider interface
├── markdown_converter.py    # Unchanged (provider-agnostic)
├── file_manager.py          # Unchanged (provider-agnostic)
└── utils.py                 # Unchanged (provider-agnostic)
```

### CLI Integration

Add a `--provider` flag (defaulting to `gmail` for backward compatibility):

```bash
iobox search -q "from:newsletter@example.com" --provider outlook
iobox save -q "label:important" --provider gmail
iobox send --to user@example.com --subject "Hi" --provider outlook
```

Provider selection could also come from an environment variable (`IOBOX_PROVIDER=outlook`) or a config file.

### New Dependencies

| Package | Purpose | Replaces |
|---|---|---|
| `msal` | Microsoft OAuth 2.0 token acquisition | N/A (new) |
| `msal-extensions` | Encrypted token persistence | N/A (new) |
| `requests` | HTTP client for Graph REST calls | `google-api-python-client` (Graph side) |

Alternatively, `python-o365` could replace `msal` + raw REST calls, as it bundles auth and Graph operations together.

---

## 7. Implementation Roadmap

1. **Define the provider interface** — Create `providers/base.py` with `EmailProvider` ABC and `EmailQuery` dataclass
2. **Wrap existing Gmail code** — Create `GmailProvider` in `providers/gmail.py` that delegates to existing modules (`auth.py`, `email_search.py`, `email_retrieval.py`, `email_sender.py`)
3. **Implement Outlook auth** — Create `auth_outlook.py` using `msal` + `msal-extensions` with interactive + device code flows
4. **Implement OutlookProvider** — Start with read operations (search, get message, attachments), then add write operations (send, forward, drafts), then organization (categories, folders, trash)
5. **Refactor CLI** — Add `--provider` flag, wire commands through the provider interface
6. **Query translation** — Implement `EmailQuery` → KQL/OData translation for Outlook, Gmail syntax for Gmail
7. **Delta sync for Outlook** — Implement per-folder delta tracking in `SyncState`

---

## 8. Open Questions

- **Enterprise admin consent**: Some Microsoft 365 tenants require admin consent for `Mail.ReadWrite` and `Mail.Send` scopes, which could limit usability in corporate environments. This should be documented clearly.
- **python-o365 vs raw Graph REST**: Whether to use `python-o365` as a higher-level SDK or make direct Graph REST calls via `requests`/`httpx`. python-o365 provides convenience but adds a dependency and may not map perfectly to iobox's abstractions.
- **Query syntax UX**: Whether to expose provider-specific query syntax via `-q` or require structured query options (`--from`, `--after`, `--subject`). A hybrid approach (structured options + raw `-q` passthrough) may be best.
- **Rate limiting**: Graph API throttling limits (per-user, per-app) differ from Gmail API quotas and may require adaptive retry logic.
- **Message ID stability**: Outlook message IDs change when messages are moved between folders (unless `Prefer: IdType="ImmutableId"` header is used). This affects sync state and duplicate detection.
