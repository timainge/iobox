---
enquiry_id: 2
sub_question: "What access methods are available for Telegram on macOS from Python — including the official Bot API, MTProto libraries like Telethon/Pyrogram, and any local desktop client options — and what are the authentication and permission models for each?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 2: Telegram access methods on macOS from Python

## JSON Findings

```json
{
  "sub_question": "What access methods are available for Telegram on macOS from Python — including the official Bot API, MTProto libraries like Telethon/Pyrogram, and any local desktop client options — and what are the authentication and permission models for each?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Telethon is the primary Python MTProto library for Telegram user accounts; it moved from GitHub to Codeberg and v1 is in maintenance mode, v2 is in alpha (v2.0.0a0); v1.43.0 remains the production-ready version",
      "source_url": "https://codeberg.org/Lonami/Telethon",
      "source_tier": 1,
      "quote": "Telethon v1 is for the most part in maintenance mode, with new layers still updated when released. The first alpha of Telethon v2 is available."
    },
    {
      "claim": "Pyrogram was archived on December 23, 2024 and is no longer maintained; developers should use Telethon or other alternatives",
      "source_url": "https://github.com/pyrogram/pyrogram",
      "source_tier": 1,
      "quote": "The project is no longer maintained or supported. Thanks for appreciating it. The GitHub page was archived on December 23, 2024, and is now read-only."
    },
    {
      "claim": "Telethon v2 supports: get_dialogs() for conversations, get_messages()/iter_messages() for message history, send_message() with reply_to support, search_messages() within a chat, search_all_messages() globally, download() for media, get_participants() for group members",
      "source_url": "https://docs.telethon.dev/en/v2/modules/client.html",
      "source_tier": 1,
      "quote": "get_dialogs(): Retrieves the dialogs you're part of. get_messages(chat): Fetches message history from newest to oldest. send_message(chat, text, reply_to=None). search_messages(chat, query=None). search_all_messages(query=None)"
    },
    {
      "claim": "Telethon authentication requires API credentials (api_id and api_hash) obtained from https://my.telegram.org — these are developer credentials tied to a Telegram account, plus phone number verification and 2FA if enabled",
      "source_url": "https://docs.telethon.dev/en/stable/basic/quick-start.html",
      "source_tier": 1,
      "quote": "You must get your own api_id and api_hash from https://my.telegram.org, under API Development."
    },
    {
      "claim": "Telethon uses a local session file to persist authentication; this file stores the authorization so subsequent runs don't require re-entering a verification code",
      "source_url": "https://dev.to/githubopensource/stop-re-authenticating-seamlessly-convert-telegram-sessions-between-telethon-and-pyrogram-with-4oc2",
      "source_tier": 2,
      "quote": "A session is a local authorization file used by the library that lets you reconnect without re-entering a verification code."
    },
    {
      "claim": "Telegram entity types in Telethon v2: User, Group (small chats and supergroups), Channel (broadcast only); supergroups are technically Channels with megagroup=True; all require an access_hash for operations",
      "source_url": "https://docs.telethon.dev/en/v2/concepts/peers.html",
      "source_tier": 1,
      "quote": "The Peer type in Telethon is the base class for User, Group and Channel. Groups represent both small group chats and supergroups; Channels specifically denote broadcast channels."
    },
    {
      "claim": "Telegram channels can have unlimited subscribers and are admin-only for posting; supergroups support up to 200,000 members and all members can post; basic groups max at 200 members",
      "source_url": "https://core.telegram.org/api/channel",
      "source_tier": 1,
      "quote": "Channels: Broadcasting tools with unlimited subscriber capacity. Supergroups: can support up to 200,000 members each. Basic groups: maximum 200 members."
    },
    {
      "claim": "Telegram Bot API is an alternative to MTProto; it uses HTTP REST calls with a bot token obtained from @BotFather; bots can only read messages sent to them or in groups where they are members — they cannot read full conversation history",
      "source_url": "https://docs.telethon.dev/en/v2/concepts/botapi-vs-mtproto.html",
      "source_tier": 1,
      "quote": "HTTP Bot API vs MTProto — Bot API is a simpler HTTP REST interface; MTProto gives full access to Telegram's API."
    },
    {
      "claim": "Telethon's iter_messages() accepts search query, offset_date, from_user, filter, and limit parameters; date filtering has known limitations (Telegram API does not reliably honour min_date/max_date in SearchRequest)",
      "source_url": "https://tl.telethon.dev/methods/messages/search.html",
      "source_tier": 1,
      "quote": "If date filtering isn't working, it's because the parameters don't work in the Telegram API itself, and unfortunately there's no way to fix this on the Telethon side."
    },
    {
      "claim": "There is no local Telegram Desktop database read approach equivalent to iMessage/Signal; Telegram's local storage is not documented for developer access and all read/write operations go through the MTProto API",
      "source_url": "https://docs.telethon.dev/en/stable/modules/client.html",
      "source_tier": 1,
      "quote": "Telethon is a pure Python 3 MTProto library; all operations communicate with Telegram servers via the protocol."
    }
  ],
  "gaps": [
    "Telethon v2 stable release timeline — currently alpha",
    "Rate limiting details for iter_messages() on large conversation histories",
    "Telethon ToS compliance — users can be banned for excessive API usage"
  ]
}
```

## Findings (prose)

Telegram has the richest and most developer-friendly API of any consumer messaging platform. There are two access paths from Python: the official Bot API (HTTP REST, limited to bot interactions) and the MTProto protocol via client libraries like Telethon (full user account access).

Telethon is the dominant Python MTProto library. It moved from GitHub to Codeberg in 2024 and v1 remains in maintenance mode. Pyrogram, once a popular alternative, was archived in December 2024 and should not be used for new projects [pyrogram GitHub]. Telethon v2 is available as an alpha and introduces a cleaner type-safe API — User, Group, Channel as first-class types rather than the ambiguous Chat/Channel distinction in v1.

Telethon's read capabilities are excellent. `get_dialogs()` lists all conversations (private chats, groups, channels, bots) ordered by recency. `get_messages(chat)` / `iter_messages(chat)` fetches full message history with pagination — this is a key advantage over Signal's signal-cli. The `search_messages()` method enables full-text search within a conversation; `search_all_messages()` performs global search across all chats. `get_participants()` retrieves group/channel member lists. Media can be downloaded with `download(media)`.

Write operations include: `send_message()` with `reply_to` for threading, plus `send_photo()`, `send_video()`, `send_file()`, `send_audio()`. Telethon also supports `delete_messages()`, `edit_message()`, and `forward_messages()`.

Authentication requires a Telegram developer account at my.telegram.org to obtain `api_id` and `api_hash` — these are permanent credentials for the application, not per-session. Phone number verification and 2FA if enabled. Sessions are stored in a local SQLite file. This is a meaningful credential management burden compared to iMessage's TCC-permission model.

The Bot API alternative is simpler but far more limited: bots cannot read conversation history, cannot initiate conversations with users (users must message first), and can only see messages where the bot is a participant. This makes it unsuitable for a personal workspace context tool.

For iobox, Telethon (v1 stable) is the practical implementation library, with v2 as a future migration path. The key design implication is that Telegram provides full message history read access — a `get_message_history(conversation_id, limit, before)` method is feasible, unlike Signal.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://codeberg.org/Lonami/Telethon | Telethon on Codeberg | 1 | yes |
| 2 | https://github.com/pyrogram/pyrogram | Pyrogram GitHub | 1 | yes |
| 3 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 Client docs | 1 | yes |
| 4 | https://docs.telethon.dev/en/stable/modules/client.html | Telethon v1 Client docs | 1 | yes |
| 5 | https://docs.telethon.dev/en/v2/concepts/peers.html | Telethon v2 Peers | 1 | yes |
| 6 | https://core.telegram.org/api/channel | Telegram API: Channels | 1 | yes |
| 7 | https://docs.telethon.dev/en/v2/concepts/botapi-vs-mtproto.html | Bot API vs MTProto | 1 | yes |
| 8 | https://tl.telethon.dev/methods/messages/search.html | Telethon SearchRequest | 1 | yes |
| 9 | https://dev.to/githubopensource/stop-re-authenticating-seamlessly-convert-telegram-sessions | TGConvertor session management | 2 | partially |
| 10 | https://core.telegram.org/constructor/message | Telegram message constructor | 1 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://codeberg.org/Lonami/Telethon | Telethon on Codeberg | Current maintenance status |
| 2 | https://github.com/pyrogram/pyrogram | Pyrogram GitHub | Archived December 2024 |
| 3 | https://docs.telethon.dev/en/v2/modules/client.html | Telethon v2 Client docs | Full method signatures |
| 4 | https://docs.telethon.dev/en/v2/concepts/peers.html | Telethon v2 Peers | Entity type hierarchy |
| 5 | https://core.telegram.org/api/channel | Telegram API: Channels | Group/channel limits and capabilities |
| 6 | https://tl.telethon.dev/methods/messages/search.html | Telethon SearchRequest | Date filter limitations |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Multiple Tier 1 sources (official Telegram docs, Telethon official docs) confirm all key findings. The main uncertainty is Telethon v2 stability timeline, which doesn't affect ABC design.

### Further Research Needed

None critical for ABC design. Telethon's ToS compliance for read-heavy use cases would matter for implementation guidance.
