---
enquiry_id: 4
sub_question: "How do participant addressing schemes differ across Signal, Telegram, WhatsApp, and iMessage — specifically the use of phone numbers, usernames, user IDs, and handle types — and what is the implication for a shared Participant type in a MessageProvider ABC?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 4: Participant addressing schemes across platforms

## JSON Findings

```json
{
  "sub_question": "How do participant addressing schemes differ across Signal, Telegram, WhatsApp, and iMessage — specifically the use of phone numbers, usernames, user IDs, and handle types — and what is the implication for a shared Participant type in a MessageProvider ABC?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Signal uses three identifier types: ACI (Account Identifier — a stable UUID that never changes), PNI (Phone Number Identifier — changes when phone number changes), and optional username (not visible to server); the ACI is the stable identifier for messaging",
      "source_url": "https://github.com/AsamK/signal-cli/discussions/1323",
      "source_tier": 1,
      "quote": "ACI is considered to be the user's stable identifier. When checking a phone number on the signal server you currently get both the PNI and the ACI of the account. If an ACI is available, messages are sent to that."
    },
    {
      "claim": "Signal usernames (rolled out March 2024) are optional, not visible to the server, and function as a privacy-preserving alternative to sharing phone numbers; they are separate from display names and profile names",
      "source_url": "https://freedom.press/digisec/blog/signal-identifiers/",
      "source_tier": 1,
      "quote": "Usernames are optional and function similarly to meeting IDs for video calls. Phone numbers are now hidden from contacts by default."
    },
    {
      "claim": "Signal username links contain a random UUID (not the ACI/PNI) called a username link handle pointing to an encrypted username stored on the server; this prevents the server from learning usernames",
      "source_url": "https://signal.miraheze.org/wiki/Usernames",
      "source_tier": 2,
      "quote": "Usernames links contain a random UUID (not the account UUID, ACI, or PNI) called a username link handle that points to your encrypted username stored on the server."
    },
    {
      "claim": "In signal-cli, recipients are addressed by E.164 phone number (e.g. +15551234567), username prefixed with 'u:' (e.g. u:alice.123), or UUID/ACI; the E.164 phone number remains the most common addressing format",
      "source_url": "https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc",
      "source_tier": 1,
      "quote": "Send messages to individual recipients (prefixed with u: for usernames) or groups."
    },
    {
      "claim": "Telegram uses phone number as the account creation identifier but allows setting a @username that others can use to find and message you; phone number visibility is user-controlled (can be hidden from 'Nobody')",
      "source_url": "https://telegram.org/faq",
      "source_tier": 1,
      "quote": "Your username does not reveal your phone number in any way. Settings > Privacy and Security > Phone Number: Nobody option hides your phone number from everybody."
    },
    {
      "claim": "In Telegram's MTProto API, each user/chat/channel has a stable integer user_id (or chat_id / channel_id); Telethon uses marked IDs where negative numbers indicate chats and -100 prefix indicates channels",
      "source_url": "https://docs.telethon.dev/en/stable/concepts/chats-vs-channels.html",
      "source_tier": 1,
      "quote": "Both the bot API and Telethon add a minus sign (negate) the real chat ID to indicate entity type. For channels, they concatenate -100 to the real chat ID."
    },
    {
      "claim": "Telegram entities can be addressed by username (@handle), phone number (if in contacts), or integer user_id; all three resolve to the same Peer object in Telethon via resolve_username() or resolve_phone()",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "resolve_username(username): Converts @username to peer object. resolve_phone(phone): Converts phone number to peer object."
    },
    {
      "claim": "WhatsApp uses JID (Jabber ID) as its internal addressing: personal contacts are formatted as phone_number@s.whatsapp.net (E.164 without +), groups as timestamp_adminphone@g.us",
      "source_url": "https://github.com/andreas-mausch/whatsapp-viewer/blob/master/data/msgstore.db.schema.sql",
      "source_tier": 2,
      "quote": "Contacts ending in @s.whatsapp.net and groups ending in @g.us. ZCONTACTJID field serves as the identifier."
    },
    {
      "claim": "WhatsApp introduced usernames in 2025 (rolling out) as an optional identifier to replace phone numbers in chats, similar to Telegram and Signal; underlying addressing still uses JIDs internally",
      "source_url": "https://www.businesstoday.in/technology/news/story/whatsapp-to-introduce-usernames-instead-of-phone-numbers-similar-to-telegram-and-signal-478770-2025-06-03",
      "source_tier": 2,
      "quote": "WhatsApp is introducing a new system that will let users pick a unique identifier, much like Telegram or Signal, that replaces their phone number in chats and group conversations."
    },
    {
      "claim": "iMessage addresses participants by email address (Apple ID) or phone number (E.164 format); stored in the 'handle' table of chat.db with a handle_id integer and an 'id' text field containing the address",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 2,
      "quote": "iMessage participant addressing: Apple ID (email) or phone number; stored in handle table."
    }
  ],
  "gaps": [
    "Exact format of Signal ACI UUIDs as exposed by signal-cli in practice",
    "WhatsApp username API format (JID equivalent for usernames once fully rolled out)",
    "Telegram user_id stability over time (does it change on account re-registration?)"
  ]
}
```

## Findings (prose)

All four platforms share phone number as the foundational user identity, but each has built privacy layers and alternative identifiers on top in different ways.

**Signal** has the most complex identifier system [signal-cli ACI/PNI discussion]. It maintains two UUIDs per user: the ACI (Account Identifier, stable for the lifetime of the account) and PNI (Phone Number Identifier, tied to the phone number and changes if the number changes). Since March 2024, Signal also supports optional @usernames that are cryptographically hidden even from Signal's servers. In signal-cli, recipients are addressed by E.164 phone number, `u:username` prefix, or UUID. The ACI is the stable "real" identifier that messages route to.

**Telegram** uses integer IDs internally: user_id for users, chat_id for groups (negative), channel_id for channels (-100 prefix). The @username is an optional, mutable field that can be resolved to the integer ID. Phone number is required for account creation but can be completely hidden. Telethon's `resolve_username()` and `resolve_phone()` both return the same Peer object, normalizing all addressing to the integer ID for API calls.

**WhatsApp** uses JID (Jabber ID) addressing internally: `phone@s.whatsapp.net` for personal contacts, `timestamp_phone@g.us` for groups [whatsapp schema]. WhatsApp is introducing usernames in 2025 but the underlying JID system remains. The phone number (without the + prefix, in international format) is the primary identifier.

**iMessage** uses handle as the addressing unit: either an email (Apple ID) or phone number in E.164 format. These are stored in the `handle` table with an integer `handle_id` and text `id`.

**Implication for the ABC**: A `Participant` type needs to be flexible. The minimum shared fields across all platforms are: `display_name` (nullable), `handle` (the platform-native address string), and `handle_type` (discriminant: `"phone"`, `"email"`, `"username"`, `"jid"`, `"user_id"`). An optional `platform_id` field can hold the stable internal ID (ACI for Signal, integer user_id for Telegram). The ABC should accept any handle type in addressing and let providers translate to their native format. Requiring a single `address: str` field is the lean v1 approach — providers can expose typed `resolve_*` methods as extensions.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/AsamK/signal-cli/discussions/1323 | E164, ACI, PNI discussion | 1 | yes |
| 2 | https://freedom.press/digisec/blog/signal-identifiers/ | Signal's identifiers | 1 | yes |
| 3 | https://signal.miraheze.org/wiki/Usernames | Signal Usernames wiki | 2 | yes |
| 4 | https://telegram.org/faq | Telegram FAQ | 1 | yes |
| 5 | https://docs.telethon.dev/en/stable/concepts/chats-vs-channels.html | Telethon chats vs channels | 1 | yes |
| 6 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | 1 | yes |
| 7 | https://github.com/andreas-mausch/whatsapp-viewer | WhatsApp viewer schema | 2 | yes |
| 8 | https://www.businesstoday.in/technology/news/story/whatsapp-to-introduce-usernames | WhatsApp usernames news | 2 | partially |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://github.com/AsamK/signal-cli/discussions/1323 | E164, ACI, PNI discussion | Signal identifier types |
| 2 | https://freedom.press/digisec/blog/signal-identifiers/ | Signal's identifiers | Username rollout, phone privacy |
| 3 | https://telegram.org/faq | Telegram FAQ | Phone visibility, username system |
| 4 | https://docs.telethon.dev/en/stable/concepts/chats-vs-channels.html | Telethon chats vs channels | Integer ID addressing |
| 5 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | resolve_username, resolve_phone methods |
| 6 | https://github.com/andreas-mausch/whatsapp-viewer | WhatsApp viewer schema | JID addressing format |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Well-documented from Tier 1 sources for all platforms. Minor gaps on WhatsApp username API format don't affect ABC design.

### Further Research Needed

None critical for ABC design.
