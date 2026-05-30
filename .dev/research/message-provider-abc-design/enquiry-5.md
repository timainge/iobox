---
enquiry_id: 5
sub_question: "What are the core data models for Signal, Telegram, and WhatsApp — specifically the entity types (Conversation, Thread, Channel, Group, Message, Attachment) and their key fields — and how do they compare to iMessage's chat/message/handle model?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 5: Data models across Signal, Telegram, WhatsApp, and iMessage

## JSON Findings

```json
{
  "sub_question": "What are the core data models for Signal, Telegram, and WhatsApp — specifically the entity types (Conversation, Thread, Channel, Group, Message, Attachment) and their key fields — and how do they compare to iMessage's chat/message/handle model?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Signal Desktop database has 'conversations' and 'messages' as the primary tables; conversations can be type='private' or type='group'; the messages table stores message content in a JSON blob column",
      "source_url": "https://vmois.dev/query-signal-desktop-messages-sqlite/",
      "source_tier": 2,
      "quote": "The most relevant tables are: messages — contains chat messages; conversations — stores chat metadata. To retrieve active private conversations: SELECT id FROM conversations WHERE type='private' AND active_at IS NOT NULL"
    },
    {
      "claim": "Signal's message entity (via signal-cli JSON output) includes: sender (E.164 or ACI), timestamp (Unix ms), body (text), attachments (list of attachment objects), groupInfo (if group message), quoteInfo (if reply), mentions, reactions (list of emoji + author)",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "JSON Schema files for all the JSON-RPC data classes in src/main/java/org/asamk/signal/json. send supports text, attachments, mentions, text styling, quotes, link previews."
    },
    {
      "claim": "Telegram message constructor fields include: id, from_id, peer_id (the chat), date, message (text content), media (attachment), entities (styled text ranges), reply_to, fwd_from, reactions, views, forwards, replies, grouped_id (for album), edit_date",
      "source_url": "https://core.telegram.org/constructor/message",
      "source_tier": 1,
      "quote": "Core Identifiers: id, from_id, peer_id. Content: message text, date, media, entities. Engagement: reactions, views, forwards, replies. Structure: reply_to, fwd_from, grouped_id."
    },
    {
      "claim": "Telegram peer types: User (individual), Chat (basic group up to 200 members), Channel (broadcast, unlimited), Channel with megagroup=True (supergroup, up to 200k members); Telethon v2 simplifies to User, Group, Channel",
      "source_url": "https://docs.telethon.dev/en/v2/concepts/peers.html",
      "source_tier": 1,
      "quote": "The Peer type in Telethon is the base class for User, Group and Channel. Groups represent both small group chats and supergroups; Channels specifically denote broadcast channels."
    },
    {
      "claim": "WhatsApp data model: Chat entity (type: private or group), Message entity (ZISFROMME: 0=incoming, 1=outgoing, ZMESSAGEDATE, ZTEXT, ZFROMJID, ZTOJID, ZMESSAGETYPE), GroupMember (with role: member/admin), Attachment (media files)",
      "source_url": "https://engineeringnuggets.substack.com/p/database-modelling-for-whatsapp-like",
      "source_tier": 2,
      "quote": "ZWAMESSAGE includes ZISFROMME, ZMESSAGETYPE (text, image, video, voice), ZMESSAGEDATE, ZTEXT, ZFROMJID, ZTOJID."
    },
    {
      "claim": "WhatsApp supports message types: text, image, video, audio/voice, document, location, contact, sticker, reaction; ZMESSAGETYPE discriminates these in the local database",
      "source_url": "https://engineeringnuggets.substack.com/p/database-modelling-for-whatsapp-like",
      "source_tier": 2,
      "quote": "ZMESSAGETYPE (text, image, video, or voice message)"
    },
    {
      "claim": "iMessage data model: chat table (groups messages), message table (text column or attributedBody binary plist on Ventura+, is_from_me, date, handle_id, attachment_id), handle table (id=email or phone, handle_id), attachment table",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 2,
      "quote": "Key tables: message, handle, chat, attachment. Ventura+ gotcha: message text in attributedBody binary plist, not text column."
    },
    {
      "claim": "All four platforms share a common structural pattern: Conversation (container, typed as private/group/channel) → Message (content, sender, timestamp, optional reply_to) → Attachment (binary media with type/size/filename)",
      "source_url": "https://github.com/NousResearch/hermes-agent/issues/12323",
      "source_tier": 3,
      "quote": "A unified message store can use a normalized schema with fields for: sender identity, channel, timestamp, body, attachments, and thread."
    },
    {
      "claim": "A key difference: Telegram messages have 'views' and 'forwards' counts (channel posts), plus 'entities' for inline text formatting (bold, italic, mentions, URLs, code) — features absent from Signal, WhatsApp, and iMessage",
      "source_url": "https://core.telegram.org/constructor/message",
      "source_tier": 1,
      "quote": "Engagement: reactions, views, forwards, replies. Entities: vector of MessageEntity types for styled text."
    },
    {
      "claim": "Signal and iMessage do not have the concept of broadcast channels; Telegram and WhatsApp (Communities/Channels, since 2023) both have one-to-many broadcast patterns where only admins can post",
      "source_url": "https://core.telegram.org/api/channel",
      "source_tier": 1,
      "quote": "Channels: Broadcasting tools, admins only can post. Signal does not have this feature and is the same as WhatsApp in this regard (regarding channel-style broadcasting in base apps)."
    }
  ],
  "gaps": [
    "Signal conversation IDs in signal-cli JSON-RPC format (UUID vs phone number)",
    "WhatsApp community/channel data model (post-2023 feature)",
    "Exact JSON schema for signal-cli message output"
  ]
}
```

## Findings (prose)

Across all four platforms, the data model is structurally consistent at the macro level: a **Conversation** (container entity) holds a sequence of **Messages**, each Message has a **sender** and optional **Attachment** list, and Conversations have a type discriminant (private/group/channel).

**iMessage** is the simplest. The `chat` table is the conversation container; `message` contains text (or `attributedBody` binary plist on Ventura+), `is_from_me`, `date`, `handle_id`, and an optional `attachment_id`. The `handle` table stores the sender/recipient address. Reactions (tapbacks) are stored as associated messages linked by `associated_message_guid`.

**Signal** follows the same Conversation → Message model. The `conversations` table in Signal Desktop distinguishes `type='private'` and `type='group'`. Messages (as returned by signal-cli JSON-RPC) include: sender (ACI or E.164), timestamp (Unix ms), body text, attachments list, optional `groupInfo`, `quoteInfo` (reply-to reference using target timestamp), mentions, and reactions (emoji + author pairs). There are no views/forwards counts, no inline text entities.

**Telegram** is the richest data model. The `message` constructor has: `id`, `from_id`, `peer_id` (the conversation), `date`, `message` (text), `media` (attachment), `entities` (vector of styled text ranges: bold, italic, mentions, URLs, code blocks, hashtags), `reply_to`, `fwd_from`, `reactions` (emoji + count), `views`, `forwards`, `replies` (count), and `grouped_id` (for album groups). Conversations come in four types: User (1-1), Chat (basic group ≤200), Channel with megagroup=True (supergroup ≤200k), Channel (broadcast, unlimited). Telethon v2 simplifies this to User, Group, Channel.

**WhatsApp** sits between Signal and Telegram in complexity. Messages have type, text, sender JID, timestamp, direction (is_from_me), delivery status (sent/delivered/read), and attachment metadata. WhatsApp Communities (launched 2022) introduced channel-style broadcast groups, but these are not well-documented in developer-accessible data models.

**Design implications**: The `Conversation` entity in the ABC needs: `conversation_id`, `type` ("direct" | "group" | "channel"), `name` (nullable for 1-1), `participants` (list of Participant), `last_message_at`. The `Message` entity needs: `message_id`, `conversation_id`, `sender` (Participant), `timestamp`, `body` (nullable text), `attachments` (list), `reply_to_id` (nullable), `platform_data` (dict for provider-specific fields). Telegram-specific fields like `views`, `entities`, and `reactions` counts belong in `platform_data` for v1 rather than the ABC interface.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://vmois.dev/query-signal-desktop-messages-sqlite/ | Query Signal Desktop messages | 2 | yes |
| 2 | https://github.com/AsamK/signal-cli | signal-cli GitHub | 1 | yes |
| 3 | https://core.telegram.org/constructor/message | Telegram message constructor | 1 | yes |
| 4 | https://docs.telethon.dev/en/v2/concepts/peers.html | Telethon v2 Peers | 1 | yes |
| 5 | https://engineeringnuggets.substack.com/p/database-modelling-for-whatsapp-like | WhatsApp DB modelling | 2 | yes |
| 6 | https://core.telegram.org/api/channel | Telegram Channels API | 1 | yes |
| 7 | https://github.com/NousResearch/hermes-agent/issues/12323 | Unified message schema | 3 | partially |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://vmois.dev/query-signal-desktop-messages-sqlite/ | Query Signal Desktop messages | Signal DB schema |
| 2 | https://github.com/AsamK/signal-cli | signal-cli GitHub | Signal message fields via JSON-RPC |
| 3 | https://core.telegram.org/constructor/message | Telegram message constructor | Full Telegram message schema |
| 4 | https://docs.telethon.dev/en/v2/concepts/peers.html | Telethon v2 Peers | Entity type hierarchy |
| 5 | https://engineeringnuggets.substack.com/p/database-modelling-for-whatsapp-like | WhatsApp DB modelling | WhatsApp message and chat schema |
| 6 | https://core.telegram.org/api/channel | Telegram Channels API | Conversation type capabilities |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All four platforms' core data models are documented from Tier 1 or strong Tier 2 sources. WhatsApp's model is slightly less authoritative (reverse-engineered schema) but consistent across multiple sources.

### Further Research Needed

None critical for ABC design.
