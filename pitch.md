# Iobox — Your Gmail as a Programmable Data Layer

## The Problem

Email is where critical information goes to die. Newsletters, reports, receipts, notifications, conversations — billions of messages sit locked inside Gmail's web UI, unsearchable by anything except Google, inaccessible to the tools you actually work with.

Developers and knowledge workers resort to copy-pasting, manual forwarding, or building one-off scripts against the raw Gmail API — a 40+ method surface area with OAuth headaches, pagination bugs, MIME encoding, and quota management that nobody wants to deal with twice.

## What Iobox Does

Iobox turns your Gmail into a structured, portable, programmable data source.

**One command to search.** Gmail's full query syntax — senders, labels, dates, attachments — from your terminal.

**One command to save.** Any email becomes a clean Markdown file with YAML frontmatter: metadata on top, content below, attachments alongside. Ready for grep, git, Obsidian, static site generators, or any tool that reads files.

**One command to act.** Send, forward, label, star, archive, trash — full inbox management without opening a browser.

**One line to integrate.** Import iobox as a Python library. Or connect it as an MCP server and let Claude, Cursor, or any LLM agent search, read, and act on your email autonomously.

## Three Ways to Use It

| Mode | For | Example |
|---|---|---|
| **CLI** | Developers, sysadmins, power users | `iobox save -q "from:stripe.com" -d 30 -o ./receipts` |
| **Library** | Python apps, scripts, pipelines | `from iobox import search_emails, save_email_to_markdown` |
| **MCP Server** | LLM agents (Claude, Cursor, VS Code) | "Search my Gmail for invoices from last week and save them" |

## Why Now

**LLMs need tools, not just text.** MCP is becoming the standard interface between AI agents and external services. Iobox is one of the first open-source projects to offer Gmail as a first-class MCP tool — letting AI assistants search, read, compose, and manage email on behalf of users with proper OAuth and structured output.

**Email is the original API.** Every SaaS product, every notification system, every business process still runs through email. Making that data programmable — as files, as function calls, as agent tools — unlocks workflows that are currently manual or impossible.

## What Sets It Apart

- **Markdown-native output** — not JSON blobs, not raw MIME. Human-readable files with structured metadata that slot into any knowledge management system.
- **Full Gmail API coverage** — search, save, send, forward, label, trash, drafts, threads, attachments, incremental sync. Not a toy wrapper around `messages.list`.
- **Three consumption modes from one codebase** — CLI, Python library, and MCP server share the same battle-tested core with no duplication.
- **Zero infrastructure** — `pip install iobox`. OAuth flow runs locally. No server, no database, no cloud account beyond Gmail itself.
- **Open source (MIT)** — extend it, embed it, ship it.

## The Audience

- **Developers** who want email data in their scripts, pipelines, and automation
- **AI/LLM builders** who need Gmail as a tool their agents can use
- **Knowledge workers** who archive newsletters, research, and communications into Obsidian, Logseq, or custom systems
- **Teams** who process inbound email (support, sales, ops) and want programmable access without building from scratch

## Traction Path

1. **PyPI package** — `pip install iobox` with CLI entry point
2. **MCP registry** — listed as a Gmail tool for Claude Desktop and Cursor
3. **GitHub community** — templates, integrations, cookbook examples
4. **Documentation site** — searchable docs with API reference and tutorials

---

*Iobox: stop reading email, start programming it.*
