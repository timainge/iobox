---
slug: message-provider-abc-design
query: "MessageProvider ABC design for iobox — Signal, Telegram, WhatsApp access methods and data models to stress-test the ABC alongside iMessage"
date: 2026-05-05
mode: deep
status: complete
agents_planned: 7
agents_complete: 7
total_tokens: 0
total_cost_usd: 0.00
enquiries:
  - id: 1
    sub_question: "What Python libraries and local access routes exist for reading and writing Signal messages on macOS in 2025/2026, and what are the technical constraints and authentication requirements?"
    status: complete
    output_file: enquiry-1.md
    tokens: null
    cost_usd: null
  - id: 2
    sub_question: "What access methods are available for Telegram on macOS from Python — including the official Bot API, MTProto libraries like Telethon/Pyrogram, and any local desktop client options — and what are the authentication and permission models for each?"
    status: complete
    output_file: enquiry-2.md
    tokens: null
    cost_usd: null
  - id: 3
    sub_question: "What Python libraries or automation routes allow reading and writing WhatsApp messages on macOS in 2025/2026, and what are the practical constraints (Meta Business API, whatsapp-web.js-style wrappers, unofficial libraries)?"
    status: complete
    output_file: enquiry-3.md
    tokens: null
    cost_usd: null
  - id: 4
    sub_question: "How do participant addressing schemes differ across Signal, Telegram, WhatsApp, and iMessage — specifically the use of phone numbers, usernames, user IDs, and handle types — and what is the implication for a shared Participant type in a MessageProvider ABC?"
    status: complete
    output_file: enquiry-4.md
    tokens: null
    cost_usd: null
  - id: 5
    sub_question: "What are the core data models for Signal, Telegram, and WhatsApp — specifically the entity types (Conversation, Thread, Channel, Group, Message, Attachment) and their key fields — and how do they compare to iMessage's chat/message/handle model?"
    status: complete
    output_file: enquiry-5.md
    tokens: null
    cost_usd: null
  - id: 6
    sub_question: "What write operations are programmatically possible on Signal, Telegram, and WhatsApp from Python on macOS — specifically sending to an existing thread, starting a new conversation, replying, and any limitations compared to iMessage's osascript approach?"
    status: complete
    output_file: enquiry-6.md
    tokens: null
    cost_usd: null
  - id: 7
    sub_question: "What platform-specific features exist across Signal, Telegram, WhatsApp, and iMessage (reactions/tapbacks, disappearing messages, read receipts, typing indicators, channels, bots, polls) and what is the recommended strategy for handling them in a v1 MessageProvider ABC — optional typed fields, provider capabilities flags, or out of scope?"
    status: complete
    output_file: enquiry-7.md
    tokens: null
    cost_usd: null
---

## Planning Scratchpad

### Perspectives Considered

1. **Python developer/builder** — what libraries exist that are stable enough to ship as iobox provider dependencies; what are install footprints and maintenance status.
2. **Messaging platform architect** — how data models (conversations, messages, participants, attachments) differ structurally across platforms and what a least-common-denominator ABC needs.
3. **Security/privacy researcher** — what access is actually permitted technically and legally on each platform; which require TCC/Full Disk Access (like iMessage), which require registered developer credentials, which are grey-area reverse-engineering.
4. **ABC/interface designer** — what belongs in the shared MessageProvider contract vs. provider-specific extensions; how to keep the ABC lean for v1 without overfitting to iMessage's local SQLite model.
5. **UX / CLI designer** — what the iobox user-facing surface should look like; how `iobox messages list`, `iobox messages send` commands map onto provider capabilities that vary significantly.

### Diversity Check

- Enquiries 1/2/3 are platform-specific access methods — complementary, not overlapping (different platforms, different library ecosystems).
- Enquiry 4 (addressing) and 5 (data models) are structural/schema questions; they could overlap slightly on "what fields does a Message have" — enquiry 4 is scoped strictly to identity/addressing, enquiry 5 to entity structure.
- Enquiry 6 (write ops) and 1/2/3 (access methods) overlap slightly — write ops are a facet of access. Enquiry 6 is scoped to write-specific constraints and reply threading, not auth or library landscape.
- Enquiry 7 (platform features) is orthogonal to all others — it focuses on what to do with feature divergence in ABC design.

### Project Context

- iobox uses three independent ABCs: EmailProvider, CalendarProvider, FileProvider — never a monolithic one. MessageProvider follows the same pattern.
- Providers return typed dicts; the ABC has `list_*`, `get_*`, `search_*` surface plus write methods.
- iMessage already researched: local chat.db SQLite reads + osascript writes; Conversation → [Message] model; Participant addressed by Apple ID or phone number.
- Tech stack: Python 3.11+, macOS-first, stdlib preferred for local access (as with iMessage), optional heavy deps via extras (`iobox[signal]`, etc.).
- Existing ABCs define `authenticate()`, `get_profile()`, then read methods, then write methods — MessageProvider should follow this shape.
