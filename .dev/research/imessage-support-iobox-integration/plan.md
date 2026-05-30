# Research Plan: How could iMessage support be added to iobox?

**Date**: 2026-05-05
**Mode**: deep
**Agent count**: 7

## Lines of Enquiry

1. What official Apple APIs and frameworks exist for programmatic iMessage access on macOS — are there any sanctioned developer APIs, entitlements, or private frameworks?
2. How does the iMessage SQLite database (chat.db) on macOS work — schema, location, access controls, what data is available, and what are the practical limitations of read-only access via Python?
3. What can AppleScript and macOS Automation (osascript) do with the Messages app — what send/read/search operations are scriptable, and what are the reliability and permission constraints?
4. How do third-party iMessage bridges (Beeper, BlueBubbles, matrix-imessage, AirMessage) access iMessage programmatically — what technical mechanisms do they use and what constraints do they operate under?
5. What Python libraries and open-source tools exist for iMessage integration on macOS — imessage-reader, py-imessage-utils, etc. — what do they support, their maintenance status, and practical limitations?
6. What are the privacy, security, TOS, and legal constraints on programmatic iMessage access — Full Disk Access requirements, Apple's stance on automation, encryption implications, and risks to developer accounts?
7. How would iMessage integration fit iobox's provider architecture — what would a MessageProvider ABC look like, how does iMessage map to email concepts, what auth model applies, and what would workspace integration entail?

## Perspectives Considered

1. **Practitioner/builder** — What has actually been built, what libraries exist, what do they require, how reliable are they in production?
2. **Platform/OS expert** — What does Apple's sandboxing, entitlements, and privacy model actually permit?
3. **Privacy/security skeptic** — iMessage is E2E encrypted; are there TOS or legal risks to programmatic access?
4. **Adjacent-domain expert (messaging bridges)** — Beeper, BlueBubbles, AirMessage have solved this at scale; what can iobox learn from their architecture?
5. **Product/architecture designer** — How does iMessage map to iobox's three-ABC model and what new abstractions would be needed?

## Project Context Detected

Iobox is a macOS-first personal workspace context tool (Python, CLI + MCP server). Three provider ABCs: EmailProvider, CalendarProvider, FileProvider. Workspace compositor fans out across named provider slots. Auth: Google OAuth + Microsoft MSAL. iMessage would be a new provider type (MessageProvider) using local Mac credentials rather than cloud API keys. Stack: Python, Typer CLI, FastMCP, uv/pyproject.toml. Single-user personal tool, not multi-tenant.
