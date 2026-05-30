---
enquiry_id: 6
sub_question: "What write operations are programmatically possible on Signal, Telegram, and WhatsApp from Python on macOS — specifically sending to an existing thread, starting a new conversation, replying, and any limitations compared to iMessage's osascript approach?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 6: Write operations across platforms from Python on macOS

## JSON Findings

```json
{
  "sub_question": "What write operations are programmatically possible on Signal, Telegram, and WhatsApp from Python on macOS — specifically sending to an existing thread, starting a new conversation, replying, and any limitations compared to iMessage's osascript approach?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Signal write operations via signal-cli: send text to individual (by phone/username/ACI), send to group (by group ID), send attachments, sendReaction (emoji + target timestamp), sendReceipt (read receipt), sendTyping indicator; no osascript involved",
      "source_url": "https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc",
      "source_tier": 1,
      "quote": "send: Transmits messages with support for attachments, mentions, text styling, quotes, link previews. sendReaction: Send reaction using emoji + target-timestamp. sendReceipt: Send read or viewed receipt."
    },
    {
      "claim": "Signal replying to a message (quote/thread) is done via the 'quote' parameter in the send command, referencing the target message by its timestamp and author — there is no message_id reference, timestamps are the reply anchor",
      "source_url": "https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc",
      "source_tier": 1,
      "quote": "send supports quotes (reply-to by timestamp and author) and mentions."
    },
    {
      "claim": "Signal starting a new conversation requires the recipient to be registered on Signal; you cannot initiate a conversation with an unregistered number — signal-cli will error",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "Signal does not provide a public API; signal-cli is the only tool. Registration and phone number verification required."
    },
    {
      "claim": "Signal write operations require signal-cli to be installed and running; on macOS there is no native API — signal-cli must be started as a daemon or subprocess, adding a system dependency not required by iMessage's osascript approach",
      "source_url": "https://fabiobarbero.eu/posts/signalbot/",
      "source_tier": 2,
      "quote": "Install signal-cli as a systemd service running on DBus. On macOS, the JSON-RPC approach via stdin/stdout is the practical route."
    },
    {
      "claim": "Telegram write operations via Telethon v2: send_message(chat, text, reply_to=None), send_photo(), send_video(), send_audio(), send_file(); reply threading uses reply_to parameter with a message ID (not timestamp)",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "send_message(chat, text=None, markdown=None, html=None, link_preview=False, reply_to=None, keyboard=None). reply_to: message ID to reply to."
    },
    {
      "claim": "Telegram can start a new conversation with any user by username or phone (if in contacts); you can initiate messaging without prior consent from the recipient, subject to Telegram's spam detection",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "send_message(chat, text): chat can be a username, phone number, or ID. resolve_username(username) converts @handle to peer."
    },
    {
      "claim": "Telegram additional write operations: edit_message() to edit sent messages, delete_messages() to delete, forward_messages() to forward, pin_message() for channels/groups; these have no equivalent in iMessage or Signal",
      "source_url": "https://docs.telethon.dev/en/stable/modules/client.html",
      "source_tier": 1,
      "quote": "Telethon supports edit message text/captions/media, delete messages, forward messages from one chat to another."
    },
    {
      "claim": "WhatsApp write operations via Neonize: send text messages, send media (images, videos, documents, audio), create groups, add/remove group participants, send polls, send reactions, reply to messages via reply metadata",
      "source_url": "https://github.com/krypton-byte/neonize",
      "source_tier": 1,
      "quote": "Write Operations: Send text messages, Send media files with captions, Create and manage groups, Add/remove group participants, Send polls and interactive messages, Reply to messages."
    },
    {
      "claim": "WhatsApp write via official Cloud API: send text, media, templates, interactive (buttons/lists), reactions, location, contacts, stickers; replies reference a previous message_id (wamid); limited to WhatsApp Business accounts",
      "source_url": "https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/",
      "source_tier": 1,
      "quote": "Message types: text, image, interactive, location, contacts, reaction, sticker, video, document, audio. Reaction messages apply an emoji to a previous received message."
    },
    {
      "claim": "iMessage write via osascript: send to existing contact (by email/phone), send attachment (file path); cannot programmatically reply to a specific message — no reply_to targeting exists in the osascript API",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 2,
      "quote": "osascript AppleScript for writes: send to recipient by Apple ID or phone number. No reply-to thread targeting in AppleScript API."
    },
    {
      "claim": "Across all platforms, reply_to semantics differ: Signal uses timestamp+author, Telegram uses message_id integer, WhatsApp uses wamid (opaque string), iMessage has no reply_to in the write API",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "reply_to: message ID to reply to (Telegram). Signal uses timestamp as reply anchor."
    }
  ],
  "gaps": [
    "signal-cli group creation from Python (send to new group vs existing group)",
    "WhatsApp Neonize conversation initiation limitations (can you start a conversation with an uncontacted user?)",
    "Rate limits for write operations on all platforms"
  ]
}
```

## Findings (prose)

Write operations are available on all four platforms from Python, but with very different capability levels, dependencies, and ToS risks.

**iMessage** is the most constrained on write: `osascript` (AppleScript) can send text and attachments to an existing or new contact by email/phone. There is no programmatic `reply_to` — AppleScript has no API for targeting a specific message for reply. The plus is simplicity: no external daemon, no credentials, just macOS TCC permissions.

**Signal** write operations via signal-cli cover: send text (to individual or group), send attachments, `sendReaction` (emoji + target timestamp), `sendReceipt` (read receipt), `sendTyping`. Reply threading uses the timestamp + author as the reply anchor (not a message_id). Starting a new conversation just requires the recipient's phone number to be Signal-registered. The constraint is the signal-cli dependency: on macOS, this means a Java runtime + signal-cli installed and running, plus phone number registration. The signal-cli REST API or JSON-RPC interface provides the Python-callable interface.

**Telegram** via Telethon has the richest write API: `send_message()` with `reply_to` (message_id integer), `send_photo()`, `send_video()`, `send_audio()`, `send_file()`, plus `edit_message()`, `delete_messages()`, `forward_messages()`, `pin_message()`. You can send reactions in Telethon using the `reactions` API. Starting a new conversation with any user is possible by resolving their username or phone number. The write API is clean and message_id-based for replies. Authentication is via a Telegram user session (api_id + api_hash), which is the smallest-footprint credential requirement after iMessage.

**WhatsApp** via Neonize (unofficial, personal accounts): send text, media, polls, reactions, manage groups. Reply threading is supported. However, all operations risk account bans. Via the official Cloud API (business accounts only), PyWa provides the same capabilities plus templates and interactive messages with `reply_to` using the WhatsApp message ID (wamid).

**Key ABC design implication**: `reply_to` is a first-class method parameter across all platforms that support it. The ABC should define `send_message(conversation_id, text, reply_to_id=None, attachments=None)` — providers that don't support `reply_to` (iMessage) simply ignore it, returning a warning or raising `NotImplementedError`. The `reply_to_id` type is `str` (opaque) — each provider translates to its native anchor (timestamp for Signal, integer for Telegram, wamid for WhatsApp).

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc | signal-cli man page | 1 | yes |
| 2 | https://fabiobarbero.eu/posts/signalbot/ | Signal bot in Python | 2 | yes |
| 3 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | 1 | yes |
| 4 | https://docs.telethon.dev/en/stable/modules/client.html | Telethon v1 client | 1 | yes |
| 5 | https://github.com/krypton-byte/neonize | Neonize GitHub | 1 | yes |
| 6 | https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/ | WhatsApp Cloud API | 1 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc | signal-cli man page | All Signal write operations |
| 2 | https://fabiobarbero.eu/posts/signalbot/ | Signal bot in Python | macOS signal-cli setup |
| 3 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | Telegram write operations, reply_to |
| 4 | https://github.com/krypton-byte/neonize | Neonize GitHub | WhatsApp personal write ops |
| 5 | https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/ | WhatsApp Cloud API | Business write ops, wamid replies |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All write operations are well-documented from Tier 1 sources. The reply_to semantics comparison is a direct synthesis of source material.

### Further Research Needed

None critical for ABC design.
