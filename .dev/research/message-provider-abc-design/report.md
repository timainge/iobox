---
research_query: "MessageProvider ABC design for iobox — Signal, Telegram, WhatsApp access methods and data models to stress-test the ABC alongside iMessage"
date: 2026-05-05
slug: message-provider-abc-design
subagents: 7
total_sources_consulted: 52
total_sources_cited: 28
overall_confidence: high
---

# Research Report: MessageProvider ABC Design for iobox

## Executive Summary

A `MessageProvider` ABC for iobox can be designed with high confidence on the basis of four platforms: iMessage (local SQLite + osascript), Signal (signal-cli JSON-RPC daemon), Telegram (Telethon MTProto library), and WhatsApp (unofficial whatsmeow-based libraries or official Cloud API for business accounts). Across all four, the data model is structurally consistent: **Conversation → [Message]** with **Participant** addressing and optional **Attachment** lists. The structural convergence is strong enough that a lean shared ABC is feasible without overfitting to iMessage's local-database access pattern.

The key design tensions to resolve are: (1) whether to include message history fetch as an abstract method when Signal's only write-capable access path (signal-cli) does not support it; (2) how to define `Participant` addressing so it works across phone numbers, @usernames, integer user IDs, JIDs, and UUIDs; and (3) which platform-specific features (reactions, read receipts, typing indicators, channels, disappearing messages, message editing) belong in the shared ABC vs. deferred to provider extensions.

The recommended v1 ABC surface is: `authenticate()`, `get_profile()`, `list_conversations(query)`, `get_conversation(id)`, `get_messages(conversation_id, limit, before)`, `search_messages(query)`, `send_message(conversation_id, text, reply_to_id, attachments)`, `send_read_receipt(message_id)`, `send_typing(conversation_id)`, `download_attachment(message_id, attachment_id)`, and `capabilities() -> frozenset[str]`. Message history fetch (`get_messages`) should be abstract — all platforms can implement it, though Signal requires reading the local SQLite database rather than signal-cli's real-time receive. The `capabilities()` method is the critical addition that prevents the Workspace layer from attempting unsupported operations.

WhatsApp is the most constrained: personal account access requires unofficial libraries (Neonize, whatsapp-bridge) that violate WhatsApp's ToS; the official Cloud API requires a WhatsApp Business Account. A `WhatsAppProvider` should be clearly marked as experimental and ToS-noncompliant unless using the Cloud API. Telegram is the most capable, with Telethon providing full message history read, search, and a rich write API. Signal sits between them: full write capability via signal-cli but no history fetch via the daemon (local SQLite access needed).

---

## Findings

### Theme 1: Access Method Landscape

**Signal (macOS)** offers two access routes [Enquiry 1]:

- **Local SQLite read** — Signal Desktop at `~/Library/Application Support/Signal/sql/db.sqlite` (SQLCipher-encrypted). The decryption key was historically in plaintext `config.json` but Signal is migrating to macOS Keychain via Electron's SafeStorage API. Once complete, local reads require Keychain access — significantly harder from Python. This route is read-only and provides historical message access.

- **signal-cli daemon** — An unofficial Java CLI tool exposing JSON-RPC (macOS-compatible) and dbus (Linux only) interfaces. The Python library `pysignalclijsonrpc` (v25.9.0, Sept 2025) wraps the JSON-RPC endpoint. Operations: `send`, `receive` (new messages, real-time only), `listContacts`, `listGroups`, `sendReaction`, `sendReceipt`, `sendTyping`, `getAttachment`. Critically, **signal-cli has no message history fetch** — only real-time inbound messages. The `signal-cli-rest-api` Docker wrapper adds an HTTP layer.

Authentication: phone number registration + SMS/voice verification, credentials in local filesystem. No OAuth.

**Confidence**: high — Multiple Tier 1 sources confirm.

**Telegram (macOS)** is well-served by Telethon [Enquiry 2]:

- Telethon v1 (1.43.0) is production-ready and in maintenance mode; v2 (alpha on Codeberg) is the future. Pyrogram was archived December 2024 — avoid for new projects.
- Telethon read: `get_dialogs()` (conversation list), `get_messages(chat, limit, offset_date)` (full history), `search_messages(chat, query)`, `search_all_messages(query)`, `get_participants(chat)`, `download(media)`.
- Telethon write: `send_message(chat, text, reply_to=<int message_id>)`, `send_photo/video/audio/file()`, `edit_message()`, `delete_messages()`, `forward_messages()`.
- Authentication: `api_id` + `api_hash` from my.telegram.org (permanent developer credentials per application) + phone verification + optional 2FA. Session stored in local SQLite file.

No local database read approach exists for Telegram Desktop — all access is via the MTProto API.

**Confidence**: high — Official Telegram API docs + Telethon official docs.

**WhatsApp (macOS)** has the most fragmented landscape [Enquiry 3]:

- **Official Cloud API** (Meta): Business accounts only, requires Meta verification. Push/webhook for inbound, REST for outbound. Cannot read message history. PyWa is the Python framework. Suitable for business automation, not personal workspace use.
- **Neonize** (v0.3.17, April 2026, 384 GitHub stars): Python wrapping the whatsmeow Go library. Personal account, QR code auth. Send text/media/polls/reactions, manage groups, receive messages. Message history fetch not documented. Unofficial — ToS violation risk.
- **whatsapp-bridge** (v0.1.0, April 2025): Python wrapper for a Go bridge (whatsmeow). Connects via HTTP to a background Go process; reads message history from a local SQLite database maintained by the bridge. Only Python route to WhatsApp conversation history. Unofficial — ToS risk.
- **Selenium-based** (pywhatkit, alright): Fragile, breaks on WhatsApp Web updates. Not suitable.

Authentication for unofficial libraries: QR code pairing with the user's WhatsApp-connected phone.

**Confidence**: high — Tier 1 sources for official API, strong Tier 1/2 for unofficial.

**iMessage (macOS)** — confirmed from prior research: local `chat.db` SQLite reads + osascript writes. Full Disk Access TCC permission. No reply_to in osascript write API.

**Confidence**: high.

---

### Theme 2: Participant Addressing

All four platforms are phone-number-rooted but have diverged significantly [Enquiry 4]:

| Platform | Primary identifier | Alternative | Internal stable ID |
|---|---|---|---|
| iMessage | E.164 phone / email (Apple ID) | None | handle_id (local int) |
| Signal | E.164 phone | Username (u:handle, optional, encrypted) | ACI (UUID, permanent) |
| Telegram | Integer user_id/chat_id | @username (mutable), phone (hideable) | user_id (stable integer) |
| WhatsApp | JID (phone@s.whatsapp.net) | Username (rolling out 2025) | JID |

Signal's identifier system is the most complex: ACI (Account Identifier, stable UUID), PNI (Phone Number Identifier, changes with number), and optional usernames cryptographically invisible to Signal servers. signal-cli addresses recipients by E.164 phone number, `u:username` prefix, or UUID.

Telegram resolves any of username, phone number, or integer ID to the same Peer object via `resolve_username()` / `resolve_phone()`. Integer IDs are stable.

WhatsApp uses JIDs (`phone@s.whatsapp.net` for contacts, `timestamp_phone@g.us` for groups). Usernames are being introduced in 2025 but JIDs remain the internal mechanism.

**ABC implication**: `Participant` TypedDict should have: `handle: str` (platform-native address string), `handle_type: str` ("phone" | "email" | "username" | "jid" | "user_id"), `display_name: str | None`, and optional `platform_id: str` for the stable internal ID.

**Confidence**: high.

---

### Theme 3: Data Models

The macro structure is consistent across all platforms [Enquiry 5]:

```
Conversation (container)
├── type: "direct" | "group" | "channel"
├── participants: list[Participant]
└── messages: [Message]
             ├── sender: Participant
             ├── timestamp: str (ISO 8601)
             ├── body: str | None
             ├── attachments: list[AttachmentRef]
             ├── reply_to_id: str | None
             └── reactions: list[Reaction] | None
```

Platform-specific departures worth noting:

- **Telegram**: Messages add `entities` (inline formatting: bold, italic, mention, URL, code, hashtag), `edit_date`, `views` (channel posts), `forwards`, `fwd_from` (forward attribution), `grouped_id` (album). These belong in `platform_data` for v1.

- **Signal**: Reply threading uses `quoteInfo` (timestamp + author), not a message_id reference. The `reply_to_id` in the ABC is opaque — each provider translates it to its native anchor (timestamp for Signal, integer for Telegram, wamid for WhatsApp).

- **WhatsApp**: Adds per-message delivery status (sent/delivered/read), ZMESSAGETYPE discriminant (text/image/video/voice/document), and group admin role tracking on participants.

- **iMessage**: `is_from_me` boolean for direction; reactions as associated message rows (not inline); Ventura+ `attributedBody` binary plist requirement.

**Confidence**: high.

---

### Theme 4: Write Operations and reply_to Semantics

Write operations are available on all four platforms but with significant variation [Enquiry 6]:

| Platform | Send new | Reply | Edit | React | Read receipt | Typing |
|---|---|---|---|---|---|---|
| iMessage | Yes (osascript) | No reply_to | No (osascript) | No (write) | Toggleable | Yes |
| Signal | Yes (signal-cli) | Yes (timestamp) | No | Yes | Yes | Yes |
| Telegram | Yes (Telethon) | Yes (message_id) | Yes | Yes | Private only | Yes |
| WhatsApp | Yes (Neonize/API) | Yes (wamid) | Yes (15 min) | Yes | Yes | Yes |

The `reply_to` anchor differs per platform: Signal=`{timestamp+author}`, Telegram=integer `message_id`, WhatsApp=`wamid` opaque string, iMessage=no reply_to targeting. In the ABC, `reply_to_id: str | None` is the right type — each provider translates the opaque string to its native anchor.

**Confidence**: high — All write APIs documented from Tier 1 sources.

---

### Theme 5: Platform-Specific Features — Inclusion Strategy

Feature distribution [Enquiry 7]:

| Feature | iMessage | Signal | Telegram | WhatsApp |
|---|---|---|---|---|
| Reactions | Yes (6 tapbacks) | Yes (any emoji) | Yes (any + counts) | Yes (any emoji) |
| Typing indicators | Yes | Yes | Yes | Yes |
| Read receipts | Yes | Yes | Private chats | Yes |
| Disappearing messages | No | Yes | Secret Chats | Yes |
| Broadcast channels | No | No | Yes | Yes (Communities) |
| Bots | No | No (simulation) | Yes (native) | Yes (Business) |
| Polls | No | No | Yes | Yes |
| Message editing | Ventura+ | No | Yes | Yes (15 min) |
| History fetch | Local DB | Local DB | Full API | Go bridge |

**v1 ABC inclusion strategy**:

- **Universal (all 4)**: `send_typing()` as abstract no-op default. Reactions as optional `reactions` field on `MessageData`.
- **Near-universal (3/4)**: `send_read_receipt()` as abstract no-op default. `reply_to_id` as optional field on `MessageData` and parameter on `send_message()`.
- **Deferred to v2 / platform_data**: Disappearing messages, channels operations, bots, polls, forwarding, message deletes.
- **Optional abstract with NotImplementedError default**: `send_reaction(message_id, emoji)`, `edit_message(message_id, new_text)`.
- **Critical addition**: `capabilities() -> frozenset[str]` — lets Workspace layer query provider support before dispatching.

**Confidence**: high.

---

### Theme 6: Proposed MessageProvider ABC

Based on all findings, the following v1 ABC is recommended for iobox, consistent with the `EmailProvider` / `CalendarProvider` / `FileProvider` pattern:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypedDict


class Participant(TypedDict, total=False):
    handle: str           # Platform-native address (required)
    handle_type: str      # "phone"|"email"|"username"|"jid"|"user_id" (required)
    display_name: str | None
    platform_id: str | None    # Stable internal ID (ACI for Signal, int for Telegram)


class AttachmentRef(TypedDict):
    attachment_id: str
    filename: str
    mime_type: str
    size: int


class Reaction(TypedDict, total=False):
    emoji: str
    sender: Participant | None
    count: int | None          # Telegram channel reactions have counts


class MessageData(TypedDict, total=False):
    message_id: str
    conversation_id: str
    sender: Participant
    timestamp: str             # ISO 8601
    is_from_me: bool
    body: str | None
    attachments: list[AttachmentRef]
    reply_to_id: str | None    # Opaque — provider translates to native anchor
    reactions: list[Reaction]
    edited_at: str | None
    platform_data: dict[str, Any]


class ConversationData(TypedDict, total=False):
    conversation_id: str
    type: str                  # "direct" | "group" | "channel"
    name: str | None
    participants: list[Participant]
    last_message_at: str | None
    unread_count: int | None
    platform_data: dict[str, Any]


@dataclass
class MessageQuery:
    text: str | None = None
    conversation_id: str | None = None
    from_handle: str | None = None
    after: str | None = None
    before: str | None = None
    max_results: int = 50
    raw_query: str | None = None


@dataclass
class ConversationQuery:
    text: str | None = None
    types: list[str] | None = None
    max_results: int = 25


class FeatureNotSupportedError(Exception):
    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"Feature '{feature}' is not supported by this provider")


class MessageProvider(ABC):
    """Abstract interface for messaging provider backends.

    Implementations: iMessageProvider, SignalProvider,
    TelegramProvider, WhatsAppProvider.
    """

    # ── 1. Authentication ──────────────────────────────────────────
    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    # ── 2. Conversation Read ───────────────────────────────────────
    @abstractmethod
    def list_conversations(self, query: ConversationQuery) -> list[ConversationData]: ...

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> ConversationData: ...

    # ── 3. Message Read ────────────────────────────────────────────
    @abstractmethod
    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before: str | None = None,  # ISO 8601
    ) -> list[MessageData]:
        """Return messages newest-first.

        SignalProvider via signal-cli only: raises FeatureNotSupportedError
        unless local SQLite access is available.
        """
        ...

    @abstractmethod
    def get_message(self, message_id: str) -> MessageData: ...

    @abstractmethod
    def search_messages(self, query: MessageQuery) -> list[MessageData]: ...

    @abstractmethod
    def download_attachment(self, message_id: str, attachment_id: str) -> bytes: ...

    # ── 4. Write Operations ────────────────────────────────────────
    @abstractmethod
    def send_message(
        self,
        conversation_id: str,
        text: str | None = None,
        *,
        reply_to_id: str | None = None,
        attachments: list[str] | None = None,
    ) -> MessageData: ...

    def send_reaction(self, message_id: str, emoji: str) -> None:
        raise FeatureNotSupportedError("reactions")

    def edit_message(self, message_id: str, new_text: str) -> MessageData:
        raise FeatureNotSupportedError("message_edit")

    # ── 5. Indicators ──────────────────────────────────────────────
    def send_read_receipt(self, message_id: str) -> None:
        """Default no-op. Override in providers that support read receipts."""

    def send_typing(self, conversation_id: str) -> None:
        """Default no-op. Override in providers that support typing indicators."""

    # ── 6. Capabilities ────────────────────────────────────────────
    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        """Declare supported features. Standard capability strings:
          "message_history"   — get_messages() returns historical data
          "message_search"    — search_messages() is meaningful
          "reactions"         — send_reaction() is supported
          "read_receipts"     — send_read_receipt() works
          "typing_indicators" — send_typing() works
          "reply_to"          — reply_to_id in send_message() works
          "message_edit"      — edit_message() is supported
          "channels"          — conversation_type="channel" is supported
        """
        ...
```

**Capabilities matrix by provider**:
- `iMessageProvider`: `{"message_history", "message_search"}` — no send_reaction write, no reply_to in osascript
- `SignalProvider` (signal-cli only): `{"reactions", "read_receipts", "typing_indicators", "reply_to"}` — no "message_history" without local SQLite
- `SignalProvider` (with local SQLite): add `"message_history"`, `"message_search"`
- `TelegramProvider`: `{"message_history", "message_search", "reactions", "read_receipts", "typing_indicators", "reply_to", "message_edit", "channels"}`
- `WhatsAppProvider` (Neonize): `{"reactions", "read_receipts", "typing_indicators", "reply_to"}` — "message_history" only with whatsapp-bridge

---

## Contradictions and Open Questions

### Contradictions Found

**Signal-CLI GitHub claims** signal-cli has no message history fetch (`receive` is real-time only) [Tier 1]; **vmois.dev** [Tier 2] shows Signal Desktop has full history in local SQLite. The two sources are not contradictory — they describe different access paths — but the implication that `get_messages()` should be abstract (providers implement it however they can) rather than a stub that always returns [] is the correct resolution.

**Pyrogram vs. Telethon**: Multiple early search results listed Pyrogram as an active alternative to Telethon. The official Pyrogram GitHub [Tier 1] directly contradicts this — Pyrogram was archived December 2024. The discrepancy reflects search results indexing pre-archival content. Trust Tier 1: Pyrogram is dead.

**WhatsApp message history via whatsapp-bridge**: whatsapp-bridge documentation [Tier 1, PyPI] says it reads history from a local SQLite DB. However, the library is v0.1.0/Alpha (April 2025) — the reliability of this for production iobox use is unconfirmed. Treat as experimental.

### Open Questions

- **Signal Keychain migration status**: Is macOS Keychain-backed key storage complete in the current Signal Desktop stable release (2026)? If yes, local SQLite reads without Keychain access are blocked. This is the highest-priority implementation-time question.

- **Signal conversation_id format from signal-cli**: `listContacts` and `listGroups` output needs to be matched to Signal Desktop SQLite `conversations.id`. The format (UUID vs. phone number vs. group ID) needs verification.

- **Telethon ToS for heavy history reads**: Heavy use of `get_messages()` for full sync may trigger rate limiting or account suspension. Iobox should implement exponential backoff.

- **WhatsApp personal account longevity**: Meta has closed unofficial WhatsApp clients before. The `WhatsAppProvider` should be treated as high-risk for long-term stability.

---

## Sources

See [sources.md](sources.md) for the full deduplicated source list.

### Key Sources

| # | URL | Title | Tier | Contribution |
|---|-----|-------|------|-------------|
| 1 | https://github.com/AsamK/signal-cli | signal-cli GitHub | 1 | Signal write operations, JSON-RPC interface, all signal-cli commands |
| 2 | https://vmois.dev/query-signal-desktop-messages-sqlite/ | Query Signal Desktop SQLite | 2 | Signal DB schema, conversations/messages tables, decryption approach |
| 3 | https://mjtsai.com/blog/2024/07/08/signal-for-macs-encrypted-database/ | Signal for Mac's Encrypted Database | 2 | Keychain migration, at-rest encryption model |
| 4 | https://codeberg.org/Lonami/Telethon | Telethon on Codeberg | 1 | Telethon v1/v2 maintenance status |
| 5 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 Client docs | 1 | Full v2 method signatures, read + write ops |
| 6 | https://core.telegram.org/constructor/message | Telegram message constructor | 1 | Complete Telegram message schema |
| 7 | https://core.telegram.org/api/channel | Telegram Channels API | 1 | Group/channel/supergroup capability differences |
| 8 | https://pywa.readthedocs.io/ | PyWa documentation | 1 | WhatsApp Cloud API Python framework |
| 9 | https://github.com/krypton-byte/neonize | Neonize GitHub | 1 | WhatsApp personal account access, operations, status |
| 10 | https://pypi.org/project/whatsapp-bridge/ | whatsapp-bridge PyPI | 1 | WhatsApp local history via Go bridge SQLite |
| 11 | https://freedom.press/digisec/blog/signal-identifiers/ | Signal's identifiers | 1 | Signal ACI/PNI/username system |
| 12 | https://github.com/AsamK/signal-cli/discussions/1323 | E164, ACI, PNI discussion | 1 | Signal identifier technical details |
| 13 | https://docs.telethon.dev/en/v2/concepts/peers.html | Telethon v2 Peers | 1 | Telegram entity type hierarchy |
