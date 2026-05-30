---
enquiry_id: 7
sub_question: "What platform-specific features exist across Signal, Telegram, WhatsApp, and iMessage (reactions/tapbacks, disappearing messages, read receipts, typing indicators, channels, bots, polls) and what is the recommended strategy for handling them in a v1 MessageProvider ABC — optional typed fields, provider capabilities flags, or out of scope?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 7: Platform-specific features and ABC handling strategy

## JSON Findings

```json
{
  "sub_question": "What platform-specific features exist across Signal, Telegram, WhatsApp, and iMessage (reactions/tapbacks, disappearing messages, read receipts, typing indicators, channels, bots, polls) and what is the implication for ABC design?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Reactions are supported on all four platforms: iMessage tapbacks (limited set: heart/thumbs-up/thumbs-down/ha/!!/?) , Signal (any emoji, customizable set of 6 quick-reactions), Telegram (any emoji, with counts for channel posts), WhatsApp (emoji reactions via Cloud API)",
      "source_url": "https://support.signal.org/hc/en-us/articles/360039929972-Message-Reactions",
      "source_tier": 1,
      "quote": "Signal lets you react with more emoji than the default set, and Signal lets you use all emoji as reactions."
    },
    {
      "claim": "Read receipts: Signal (user-toggleable, blue checkmarks), WhatsApp (double blue ticks, user-toggleable), Telegram (only for private chats, no group read receipts), iMessage (blue 'Read' indicator, toggleable per conversation)",
      "source_url": "https://setapp.com/lifestyle/signal-vs-whatsapp",
      "source_tier": 2,
      "quote": "Signal allows users to enable or disable read receipts and typing indicators, which Telegram does not have (for groups)."
    },
    {
      "claim": "Typing indicators: Signal (yes, toggleable), WhatsApp (yes, via sendTyping in API), Telegram (yes, via MTProto sendTyping action), iMessage (yes, the three-dot bubble); all four support typing indicators",
      "source_url": "https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc",
      "source_tier": 1,
      "quote": "sendTyping: Send typing message to trigger a typing indicator for the recipient."
    },
    {
      "claim": "Disappearing messages: Signal (all message types, configurable timer, enabled per conversation), WhatsApp (user-toggleable per chat), Telegram (Secret Chats only — not regular chats, self-destructs on timer); iMessage does not support disappearing messages",
      "source_url": "https://widgeti.tech/mobile/whatsapp-vs-signal-vs-telegram-vs-viber-vs-imessage-all-you-need-to-know-before-switching-messaging-apps-full-comparison/",
      "source_tier": 2,
      "quote": "Telegram secret chat feature: self-destruct message feature where users can set a specific period of time. Signal implements complete end-to-end encryption and offers the self-destruct option for all messages."
    },
    {
      "claim": "Broadcast channels: Telegram (native, unlimited subscribers, admin-only posting), WhatsApp (Communities/Channels since 2022, one-way broadcast); Signal and iMessage do not have broadcast channel functionality",
      "source_url": "https://core.telegram.org/api/channel",
      "source_tier": 1,
      "quote": "Channels are broadcasting tools with unlimited subscriber capacity, channels have their own view counter for each post. Signal does not have this feature."
    },
    {
      "claim": "Bots: Telegram (native Bot API, extensive ecosystem, bots can be added to groups); Signal (no native bot support — bots implemented via signal-cli as a regular account); WhatsApp (Cloud API creates business bot-like endpoints); iMessage (no bot support)",
      "source_url": "https://www.androidcentral.com/telegram-vs-signal-vs-whatsapp",
      "source_tier": 2,
      "quote": "Telegram supports using bots to automate conversations, while Signal does not allow the use of bots."
    },
    {
      "claim": "Polls: Telegram (native polls in groups/channels with vote counts, anonymous voting option), WhatsApp (polls in groups since 2022), Signal (no native polls), iMessage (no polls)",
      "source_url": "https://setapp.com/lifestyle/signal-vs-whatsapp",
      "source_tier": 2,
      "quote": "Telegram provides animated stickers and polls; Signal lacks these."
    },
    {
      "claim": "Message editing: Telegram (edit sent messages, with edit timestamp); Signal (no message editing); WhatsApp (edit within 15 minutes); iMessage (edit within 15 minutes on iOS 16+/macOS Ventura+)",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "Telethon supports: edit message text, captions, media, reply markup after posting."
    },
    {
      "claim": "Signal-cli exposes reactions as a list on message objects (emoji + author), and can send reactions via sendReaction command; reactions are read-accessible from the local Signal Desktop database via a dedicated 'reactions' table",
      "source_url": "https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc",
      "source_tier": 1,
      "quote": "sendReaction: Send reaction to a previously received or sent message using emoji responses."
    },
    {
      "claim": "Recommended ABC strategy for platform-specific features: reactions and read receipts are common enough to include as optional fields in the Message TypedDict (reactions: list | None, read_at: str | None); disappearing messages, channels, bots, polls are provider-specific and should be deferred to provider-specific extensions or platform_data dict",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "signal-cli supports sendReaction, sendReceipt (read receipt), sendTyping — all three are cross-platform enough to warrant ABC inclusion."
    }
  ],
  "gaps": [
    "Formal capability flag pattern best practices for Python ABCs",
    "iMessage edit support via osascript (likely not available)",
    "WhatsApp Communities channel data model in whatsmeow/Neonize"
  ]
}
```

## Findings (prose)

Comparing features across all four platforms reveals three tiers of cross-platform support:

**Universal (all four platforms)**: Reactions, typing indicators, media attachments (images, video, audio, documents). These belong in the core ABC.

**Three-platform (not iMessage)**: Read receipts as a programmatic operation (send/receive), group conversations with multiple participants. These belong in the ABC with iMessage implementing a stub or raising `NotImplementedError` for send_read_receipt().

**Two-platform or fewer**: Disappearing messages (Signal, WhatsApp, Telegram Secret Chats), broadcast channels (Telegram, WhatsApp), polls (Telegram, WhatsApp), bots (Telegram), message editing (Telegram, WhatsApp, iMessage with caveats). These should be deferred to v1 as `platform_data` fields or provider-specific subclass methods.

**Reactions** deserve special attention because they exist on all four platforms but differ in semantics. iMessage has a fixed set of tapbacks (6 emotions). Signal allows any emoji. Telegram reactions on channels include view counts. The ABC should define: `reactions: list[Reaction]` on the Message TypedDict where `Reaction` = `{emoji: str, sender: Participant | None, count: int | None}`. The `count` field is Telegram-specific; it can be None on other platforms.

**Read receipts** are available on Signal (toggleable), WhatsApp (toggleable), iMessage (toggleable), and partially on Telegram (private chats only). The ABC should define `send_read_receipt(message_id: str) -> None` as an abstract method with a default no-op implementation — providers that don't support it can override to raise `FeatureNotSupportedError` or silently no-op.

**Typing indicators** are universal and can be included as `send_typing(conversation_id: str) -> None`.

**Disappearing messages**: Provider-specific, not in ABC v1. Expose via `platform_data` on the Conversation TypedDict.

**Channels**: A major structural divergence. Telegram channels and WhatsApp Communities are fundamentally different from private/group conversations: they are one-to-many broadcast containers with view counts, subscriber lists, and admin-only posting. The ABC should include `type: "direct" | "group" | "channel"` as a Conversation discriminant so the Workspace layer can route channel queries to providers that support them. But channel-specific operations (subscribe, publish) are v2 features.

**Bots**: Out of scope for MessageProvider ABC v1. Bot management is a separate concern.

**Polls**: Out of scope for v1; add to `platform_data`.

**Message editing**: Include `edit_message(message_id: str, new_text: str) -> Message` as an optional abstract method (default raises `NotImplementedError`). Signal does not support it; iMessage support via osascript is uncertain.

**Provider capabilities flags pattern**: Consider adding a `capabilities() -> set[str]` method to the ABC returning strings like `{"reactions", "read_receipts", "typing_indicators", "message_edit", "channels", "polls"}`. This lets the Workspace layer query provider capabilities before dispatching operations and avoids `try/except NotImplementedError` scattered in caller code.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://support.signal.org/hc/en-us/articles/360039929972-Message-Reactions | Signal reactions | 1 | yes |
| 2 | https://setapp.com/lifestyle/signal-vs-whatsapp | Signal vs WhatsApp comparison | 2 | yes |
| 3 | https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc | signal-cli man page | 1 | yes |
| 4 | https://widgeti.tech/mobile/whatsapp-vs-signal-vs-telegram | Full messaging comparison | 2 | yes |
| 5 | https://core.telegram.org/api/channel | Telegram channels API | 1 | yes |
| 6 | https://www.androidcentral.com/telegram-vs-signal-vs-whatsapp | Telegram vs Signal vs WhatsApp | 2 | yes |
| 7 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | 1 | yes |
| 8 | https://thenextweb.com/news/how-to-emoji-react-on-whatsapp-telegram-signal | Emoji reactions comparison | 2 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://support.signal.org/hc/en-us/articles/360039929972-Message-Reactions | Signal reactions | All-emoji reactions, customizable set |
| 2 | https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc | signal-cli man page | sendReaction, sendReceipt, sendTyping |
| 3 | https://core.telegram.org/api/channel | Telegram channels API | Broadcast channel capabilities |
| 4 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 client | Message editing support |
| 5 | https://setapp.com/lifestyle/signal-vs-whatsapp | Signal vs WhatsApp | Read receipts, typing indicators |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Feature comparison is well-documented across multiple Tier 1 and 2 sources. The ABC design recommendation is derived from cross-platform analysis of what is universal vs. provider-specific.

### Further Research Needed

None critical for ABC design. Capability flags pattern could benefit from examining existing Python ABC patterns in open-source libraries.
