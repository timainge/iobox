# Research Context: MessageProvider ABC design for iobox — Signal, Telegram, WhatsApp access and data models

---

## Enquiry 1: Signal access methods on macOS from Python

**Confidence**: high | **Coverage**: yes

- Signal Desktop stores messages in SQLCipher-encrypted SQLite at `~/Library/Application Support/Signal/sql/db.sqlite`; key was in plaintext `config.json` but Signal is migrating to macOS Keychain via Electron SafeStorage API [mjtsai blog](https://mjtsai.com/blog/2024/07/08/signal-for-macs-encrypted-database/)
- Signal Desktop DB has 34 tables: `conversations` (type: private/group), `messages`, `reactions`, `attachments`, `identityKeys` [vmois.dev SQLite query](https://vmois.dev/query-signal-desktop-messages-sqlite/)
- Python cannot use Signal's Node.js-based decryption fork; requires separate sqlcipher/pysqlcipher3 installation for local DB reads
- signal-cli (Java, unofficial) is the primary Python-callable interface — provides JSON-RPC, dbus (Linux only), and CLI; latest version active as of Sept 2025 [signal-cli GitHub](https://github.com/AsamK/signal-cli)
- signal-cli read operations: `receive` (new messages only — no history fetch), `listContacts`, `listGroups`, `getAttachment`; write: `send`, `sendReaction` (emoji + timestamp), `sendReceipt`, `sendTyping`
- pysignalclijsonrpc is a Python client for signal-cli's JSON-RPC HTTP endpoint, v25.9.0 (Sept 2025), indicating active maintenance [PyPI](https://pypi.org/project/pysignalclijsonrpc/)
- Authentication: phone number registration + SMS/voice verification; credentials stored at `~/.local/share/signal-cli/data/` — no OAuth, no API keys
- signal-cli-rest-api wraps signal-cli as an HTTP REST API with Swagger docs; practical for macOS where dbus is unavailable [GitHub](https://github.com/bbernhard/signal-cli-rest-api)
- Critical gap: signal-cli has NO message history fetch — only real-time push receive; local SQLite is the only way to read past messages
- Keychain migration in newer Signal Desktop versions may break plaintext config.json key access

**Gaps**: Keychain migration status in stable release, Python-specific post-Keychain sqlcipher approach.

---

## Enquiry 2: Telegram access methods on macOS from Python

**Confidence**: high | **Coverage**: yes

- Telethon is the primary Python MTProto library; moved to Codeberg; v1 (1.43.0) is in maintenance mode and production-ready; v2 (2.0.0a0) is alpha [Codeberg Telethon](https://codeberg.org/Lonami/Telethon)
- Pyrogram was archived December 2024 — do not use for new projects [Pyrogram GitHub](https://github.com/pyrogram/pyrogram)
- Telethon v2 read operations: `get_dialogs()` (all conversations), `get_messages(chat, limit, offset_date)` (full message history), `search_messages(chat, query)`, `search_all_messages(query)`, `get_participants(chat)`, `download(media)`
- Telethon v2 write operations: `send_message(chat, text, reply_to=None)`, `send_photo()`, `send_video()`, `send_file()`, `send_audio()` — reply_to uses integer message_id
- Authentication: api_id + api_hash from my.telegram.org (developer credentials per application) + phone verification + 2FA; sessions stored in local SQLite file
- Entity types in Telethon v2: User, Group (small groups + supergroups), Channel (broadcast); all require access_hash for API calls
- Telegram channel types: basic group (≤200 members), supergroup (≤200k), broadcast channel (unlimited subscribers, admin-only posting) [Telegram API docs](https://core.telegram.org/api/channel)
- Bot API alternative: simpler HTTP REST with bot token from @BotFather; bots cannot read conversation history — unsuitable for personal workspace tool
- Date filtering in iter_messages() has known limitations — Telegram API itself doesn't reliably honour min_date/max_date in SearchRequest
- No local database read approach exists for Telegram Desktop; all access goes through MTProto API

**Gaps**: Telethon v2 stable release timeline, rate limiting details for heavy history reads.

---

## Enquiry 3: WhatsApp access methods on macOS from Python

**Confidence**: high | **Coverage**: yes

- Official WhatsApp Cloud API requires a WhatsApp Business Account — personal accounts cannot use it; requires Meta business verification with documentation [Meta docs](https://developers.facebook.com/docs/whatsapp/)
- WhatsApp Cloud API is push/webhook-based; cannot retrieve message history; supports send text/media/reactions/templates/interactive messages
- PyWa is the leading Python Cloud API framework; requires Business Account; webhook-based receive [pywa docs](https://pywa.readthedocs.io/)
- Neonize (v0.3.17, April 2026, 384 stars) wraps whatsmeow Go library; supports personal accounts via QR code auth; send/receive/groups/media/reactions/polls; no explicit message history fetch documented [GitHub](https://github.com/krypton-byte/neonize)
- whatsapp-bridge (v0.1.0, April 2025) uses whatsmeow via HTTP localhost:8080; reads message history from local SQLite maintained by Go bridge — only Python route to WhatsApp history [PyPI](https://pypi.org/project/whatsapp-bridge/)
- Selenium-based options (pywhatkit, alright) are fragile, break on WhatsApp Web changes, unsuitable for production
- All unofficial libraries (Neonize, whatsapp-bridge) violate WhatsApp ToS — account ban risk is real
- WhatsApp JID addressing: personal = `phone@s.whatsapp.net`, groups = `timestamp_phone@g.us`; usernames being rolled out in 2025

**Gaps**: Neonize conversation list support (unconfirmed), WhatsApp username API format, ban rate for personal use.

---

## Enquiry 4: Participant addressing schemes across platforms

**Confidence**: high | **Coverage**: yes

- Signal identifiers: ACI (stable UUID, lifetime of account), PNI (phone-number-tied UUID), optional username (not visible to server); signal-cli addresses by E.164, `u:username`, or UUID; ACI is the stable routing identifier [signal-cli ACI/PNI discussion](https://github.com/AsamK/signal-cli/discussions/1323)
- Signal usernames (March 2024 rollout): optional, privacy-preserving, not visible to server; username links use a separate random UUID, not the ACI [Freedom of Press Foundation](https://freedom.press/digisec/blog/signal-identifiers/)
- Telegram: integer user_id/chat_id/channel_id are stable internal IDs; @username is optional mutable handle; phone number required for account creation but can be fully hidden; Telethon resolves all to peer object via resolve_username() or resolve_phone()
- WhatsApp JID: `phone_number@s.whatsapp.net` for contacts, `timestamp_phone@g.us` for groups; E.164 format without + prefix; usernames rolling out in 2025 but JID remains internal
- iMessage: email (Apple ID) or phone number (E.164); stored as text `id` in `handle` table
- All platforms use phone number as the foundational account creation identity; each has built privacy layers (usernames, UUID aliases) on top
- ABC implication: Participant needs `handle: str` (platform-native address), `handle_type: str` ("phone" | "email" | "username" | "jid" | "user_id"), `display_name: str | None`, optional `platform_id: str` for stable internal ID

**Gaps**: Signal ACI UUID format as exposed by signal-cli, Telegram user_id stability on re-registration.

---

## Enquiry 5: Data models across platforms

**Confidence**: high | **Coverage**: yes

- All four platforms share: Conversation (container, typed) → Message (content, sender, timestamp, optional reply_to) → Attachment (binary media)
- Signal DB: `conversations` table (type: private/group), `messages` with JSON blob, `reactions` table; signal-cli JSON: sender, timestamp, body, attachments, groupInfo, quoteInfo (reply by timestamp+author), mentions, reactions list [vmois.dev](https://vmois.dev/query-signal-desktop-messages-sqlite/)
- Telegram message constructor: id, from_id, peer_id, date, message (text), media, entities (styled text ranges), reply_to, fwd_from, reactions (with counts), views, forwards, replies, grouped_id, edit_date [Telegram API](https://core.telegram.org/constructor/message)
- Telegram conversation types: User (1-1), Chat (basic group ≤200), Channel/megagroup (supergroup ≤200k), Channel/broadcast (unlimited); Telethon v2 simplifies to User, Group, Channel
- WhatsApp ZWAMESSAGE: ZISFROMME (direction), ZMESSAGETYPE (text/image/video/voice/document), ZMESSAGEDATE, ZTEXT, ZFROMJID, ZTOJID; groups tracked separately with GroupMember table including admin roles
- iMessage: chat → message (text or attributedBody plist, is_from_me, date, handle_id), handle (id=email/phone), attachment
- Key differences: Telegram has views/forwards counts (channel-specific), entities (inline formatting), edit_date; Signal/WhatsApp/iMessage lack these
- Signal and iMessage have no broadcast channel type; Telegram and WhatsApp (Communities) do
- ABC design: Conversation(conversation_id, type, name, participants, last_message_at), Message(message_id, conversation_id, sender, timestamp, body, attachments, reply_to_id, platform_data), Attachment(attachment_id, filename, mime_type, size)

**Gaps**: Signal conversation IDs as exposed by signal-cli JSON-RPC, WhatsApp Communities data model.

---

## Enquiry 6: Write operations across platforms from Python

**Confidence**: high | **Coverage**: yes

- iMessage: osascript sends text/attachment to contact by email/phone; NO reply_to targeting in AppleScript API; simplest dependency (no daemon, no credentials)
- Signal via signal-cli: send to individual/group, send attachments, sendReaction, sendReceipt, sendTyping; reply uses timestamp+author as anchor (not message_id); requires signal-cli daemon + Java runtime on macOS
- Telegram via Telethon: send_message(chat, text, reply_to=int_message_id), send_photo/video/audio/file; edit_message(), delete_messages(), forward_messages(); reply_to is integer message_id; can initiate conversation with any user by username/phone
- WhatsApp Neonize: send text/media/polls/reactions, manage groups, reply by message metadata; unofficial, ToS violation risk
- WhatsApp Cloud API via PyWa: send text/media/reactions/templates/interactive; reply_to uses wamid (opaque string); business accounts only
- Reply_to semantics differ by platform: Signal=timestamp+author, Telegram=integer message_id, WhatsApp=wamid string, iMessage=no reply_to
- ABC design: `send_message(conversation_id, text, reply_to_id=None, attachments=None) -> Message`; reply_to_id is str (opaque); providers translate to native anchor; unsupported providers raise NotImplementedError or silently ignore
- Telegram uniquely supports: edit_message, delete_messages, forward_messages, pin_message — these are v2 features for the ABC

**Gaps**: Signal group creation from Python, WhatsApp conversation initiation limitations, rate limits per platform.

---

## Enquiry 7: Platform-specific features and ABC handling strategy

**Confidence**: high | **Coverage**: yes

- Reactions: all four platforms (iMessage=fixed 6 tapbacks, Signal=any emoji, Telegram=any emoji with view counts for channels, WhatsApp=emoji via API); include in ABC as `reactions: list[Reaction] | None` on Message
- Typing indicators: all four platforms support; include `send_typing(conversation_id: str) -> None` in ABC
- Read receipts: Signal (toggleable), WhatsApp (toggleable), iMessage (toggleable per conversation), Telegram (private chats only); include `send_read_receipt(message_id: str) -> None` with default no-op
- Disappearing messages: Signal (all chats), WhatsApp (per-chat toggle), Telegram (Secret Chats only), iMessage (none); provider-specific, expose via Conversation.platform_data in v1
- Broadcast channels: Telegram (unlimited subscribers, admin-only), WhatsApp Communities (admin-only); Signal and iMessage have none; include conversation_type="channel" discriminant in ABC but channel-specific operations are v2
- Bots: Telegram (native, extensive), Signal (signal-cli acts as user account), WhatsApp (Cloud API business bots), iMessage (none); out of scope for MessageProvider ABC v1
- Polls: Telegram and WhatsApp only; out of scope for v1
- Message editing: Telegram (unlimited), WhatsApp (within 15 min), iMessage (within 15 min on Ventura+), Signal (not supported); include optional `edit_message(message_id, new_text) -> Message` raising NotImplementedError by default
- Recommended capabilities() method: ABC defines `capabilities() -> set[str]` returning set of capability strings; providers declare what they support; Workspace layer queries before dispatching; avoids scattered try/except NotImplementedError

**Gaps**: iMessage edit via osascript (likely not available), WhatsApp Communities data model in Neonize.

---
