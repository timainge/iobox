# What is iobox?

iobox is a **personal workspace context tool**: a single interface for searching, retrieving, and exporting email, calendar events, and files across multiple accounts and providers.

## The problem

The context you need to get work done is scattered:

- A thread with your accountant lives in personal Gmail.
- The meeting where it was discussed is on your work Microsoft 365 calendar.
- The spreadsheet that came out of it is in Google Drive.

Each service has its own app, its own search syntax, and its own API. AI assistants can usually see one of them at best — and only if someone has built a connector for that specific service and account.

## What iobox does

iobox puts a single layer over all of it:

- **One workspace, many accounts.** Group any mix of Google and Microsoft 365 accounts into a named workspace (`personal`, `work`, …). Mixing ecosystems — Gmail for mail, OneDrive for files — is a first-class use case.
- **Fan-out queries.** One search runs in parallel against every relevant account and service. Results are merged and sorted. If one provider fails (expired token, network blip), the others still return.
- **A common data model.** An email from Outlook and an email from Gmail come back with the same fields. Events and files likewise. Your code and your prompts don't care where the data came from.
- **Markdown out.** Any email, thread, event, or file can be saved as Markdown with YAML frontmatter — easy to read, grep, version, or feed to an LLM.
- **Safe by default.** Every account is either read-only or read-write, and every command and tool is gated by an [access mode](concepts.md#access-modes), so an AI assistant can read your inbox without being able to send mail or delete files.

## Who it's for

- **People who use AI assistants** and want them to answer questions like *"what did we agree with the landlord, and when's the inspection?"* across all their accounts.
- **Developers building agents** that need email, calendar, and file context without writing three integrations per provider.
- **Anyone who wants their data as files** — archiving newsletters, exporting a project's correspondence, or building a local knowledge base.

## Three ways to use it

| | Use it when… | Start with |
|---|---|---|
| **[MCP server](../mcp/index.md)** | You want Claude Desktop (or another MCP host) to search and act on your accounts in conversation. | `iobox-mcp` |
| **[CLI](../cli/index.md)** | You want to search or export from the terminal, or script iobox from shell. | `iobox` |
| **[Python SDK](../sdk/index.md)** | You're building your own agent, pipeline, or automation in Python. | `from iobox.workspace import Workspace` |

All three share the same workspace configs and tokens under `~/.iobox/`. Set up your accounts once with the CLI and every interface can use them.

## Supported services

| Provider | Email | Calendar | Files |
|---|---|---|---|
| Google | Gmail | Google Calendar | Google Drive |
| Microsoft 365 | Outlook | Outlook Calendar | OneDrive |

!!! warning "Microsoft 365 status"
    Google providers are tested against live accounts. Microsoft 365 providers are fully implemented and unit-tested but have not yet been tested end-to-end against a real tenant. Expect rough edges and please [open an issue](https://github.com/timainge/iobox/issues).

## Next steps

1. Read the [Concepts](concepts.md) — five short ideas that make the rest of the docs make sense.
2. [Install iobox](installation.md).
3. Connect [Google](connect-google.md) or [Microsoft 365](connect-microsoft.md).
4. Follow the [Quick Start](quickstart.md).
