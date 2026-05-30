# Research Plan: MessageProvider ABC design for iobox — Signal, Telegram, WhatsApp

**Date**: 2026-05-05
**Mode**: deep
**Agent count**: 7

## Lines of Enquiry

1. What Python libraries and local access routes exist for reading and writing Signal messages on macOS in 2025/2026, and what are the technical constraints and authentication requirements?
2. What access methods are available for Telegram on macOS from Python — including the official Bot API, MTProto libraries like Telethon/Pyrogram, and any local desktop client options — and what are the authentication and permission models for each?
3. What Python libraries or automation routes allow reading and writing WhatsApp messages on macOS in 2025/2026, and what are the practical constraints (Meta Business API, whatsapp-web.js-style wrappers, unofficial libraries)?
4. How do participant addressing schemes differ across Signal, Telegram, WhatsApp, and iMessage — specifically the use of phone numbers, usernames, user IDs, and handle types — and what is the implication for a shared Participant type in a MessageProvider ABC?
5. What are the core data models for Signal, Telegram, and WhatsApp — specifically the entity types (Conversation, Thread, Channel, Group, Message, Attachment) and their key fields — and how do they compare to iMessage's chat/message/handle model?
6. What write operations are programmatically possible on Signal, Telegram, and WhatsApp from Python on macOS — specifically sending to an existing thread, starting a new conversation, replying, and any limitations compared to iMessage's osascript approach?
7. What platform-specific features exist across Signal, Telegram, WhatsApp, and iMessage (reactions/tapbacks, disappearing messages, read receipts, typing indicators, channels, bots, polls) and what is the recommended strategy for handling them in a v1 MessageProvider ABC — optional typed fields, provider capabilities flags, or out of scope?

## Project Context Detected

- iobox is a personal workspace context tool (Python, macOS-first) with three provider ABCs: EmailProvider, CalendarProvider, FileProvider.
- MessageProvider is a fourth ABC to be added alongside the existing three.
- iMessage is the first implementation target: local chat.db SQLite reads + osascript writes; Conversation → [Message] with Participant by Apple ID or phone number.
- Signal, Telegram, WhatsApp are stress-test platforms to prevent overfitting the ABC to iMessage's local SQLite / no-auth model.
- Providers follow a consistent pattern: authenticate(), get_profile(), list_*/get_*/search_* reads, write methods, returning typed dicts.
- Tech stack: Python 3.11+, macOS-first, heavy deps via package extras (iobox[signal], iobox[telegram], etc.).
