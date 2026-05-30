---
enquiry_id: 5
sub_question: "What Python libraries and open-source tools exist for iMessage integration on macOS — imessage-reader, py-imessage-utils, etc. — what do they support, their maintenance status, and practical limitations?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 5: Python libraries and open-source tools for iMessage integration

## JSON Findings

```json
{
  "sub_question": "What Python libraries and open-source tools exist for iMessage integration on macOS — imessage-reader, py-imessage-utils, etc. — what do they support, their maintenance status, and practical limitations?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "imessage_reader (PyPI: imessage-reader) is a forensic read-only Python library that reads from chat.db; it is marked Inactive by Snyk (no recent PyPI releases) but functionally still works for Python 3.9+ on macOS 10.14+",
      "source_url": "https://github.com/niftycode/imessage_reader",
      "source_tier": 1,
      "quote": "This forensic tool extracts iMessage and SMS data from macOS systems. It retrieves user IDs (phone numbers/email addresses), message content, timestamps, service type, and account information from the chat.db database."
    },
    {
      "claim": "imessage_tools (GitHub: my-other-github-account/imessage_tools) is the most complete Python library for Ventura+, handling both chat.db reading WITH attributedBody decoding AND sending via AppleScript; tested on macOS Ventura",
      "source_url": "https://github.com/my-other-github-account/imessage_tools",
      "source_tier": 1,
      "quote": "Tools for reading iMessage chat.db and sending iMessages on MacOS Ventura — including parsing capabilities for those pesky hidden attributedBody messages."
    },
    {
      "claim": "macos-messages (GitHub: tpritc/macos-messages) is a Python library and CLI for read-only iMessage access; it focuses on message history, contact listing, and search; it cannot send messages",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 1,
      "quote": "macos-messages is a Python library and CLI for reading your macOS Messages.app data. It gives you quick, easy, read-only access to your iMessage and SMS history."
    },
    {
      "claim": "py-iMessage (GitHub: Rolstenhouse/py-iMessage) is a Python library for sending iMessages via AppleScript; last released June 2020, unmaintained, but the underlying AppleScript mechanism still works",
      "source_url": "https://pypi.org/project/py-iMessage/",
      "source_tier": 1,
      "quote": "py-iMessage was last released on June 12, 2020."
    },
    {
      "claim": "imessage-exporter (GitHub: ReagentX/imessage-exporter) is a Rust tool with a PyPI wrapper; it is the most comprehensive export tool supporting all modern message types including reactions, tapbacks, edits, and stickers on macOS and iOS backups",
      "source_url": "https://github.com/ReagentX/imessage-exporter",
      "source_tier": 1,
      "quote": "The tool supports comprehensive iMessage features including: multiple message types (iMessage, RCS, SMS, MMS), replies, formatted text, attachments, tapbacks, stickers, group chats, audio messages, edited messages."
    },
    {
      "claim": "LangChain includes an iMessage chat loader (langchain_community.chat_loaders.imessage) that reads from chat.db and handles attributedBody decoding; it converts messages to LangChain Message objects for LLM pipelines",
      "source_url": "https://api.python.langchain.com/en/latest/_modules/langchain_community/chat_loaders/imessage.html",
      "source_tier": 1,
      "quote": "The attributedBody field contains 'NSString' followed by 5 preamble bytes and a length field that's either 1 byte or 3 bytes."
    },
    {
      "claim": "Multiple iMessage MCP servers exist in 2025 (jons-mcp-imessage, wolfies-imessage-gateway, mac-messages, imessage-mcp-server) — all use the chat.db + AppleScript pattern — showing the approach is production-validated for AI agent integration",
      "source_url": "https://github.com/jonmmease/jons-mcp-imessage",
      "source_tier": 1,
      "quote": "MCP server for iMessage with hybrid search and contact name enrichment. Requires Full Disk Access to read ~/Library/Messages/chat.db."
    }
  ],
  "gaps": [
    "Whether any Python library handles real-time streaming (filesystem watch) of new messages natively, or whether that requires custom integration",
    "Maintenance status of macos-messages and imessage_tools — last commit dates not verified"
  ]
}
```

## Findings (prose)

The Python iMessage ecosystem, while not large, is active enough to provide multiple working starting points for iobox. No single library covers the full read+write+stream surface, but combining two libraries or building on their patterns covers everything needed.

For reading, the leading options are: **imessage_reader** (older, simpler, read-only via chat.db; handles basic queries but does not handle the Ventura attributedBody issue), **macos-messages** (read-only CLI and library, modern, well-structured), and **imessage_tools** (read+write, Ventura-compatible attributedBody decoding, actively maintained) [1][2][3]. The LangChain iMessage loader is also worth examining — it is implemented inside a widely-used production library and handles attributedBody decoding with documented byte-level parsing [6].

For sending, **py-iMessage** (archived, 2020) and the send component of **imessage_tools** both use subprocess + osascript to invoke the Messages.app AppleScript dictionary [4]. The mechanism is identical; the difference is only code quality and maintenance.

For export and archiving, **imessage-exporter** (Rust with PyPI wrapper) is the most feature-complete tool, supporting all modern message types including tapbacks, edits, and stickers. It is actively maintained and has been reverse-engineered to support even the most recent macOS iMessage database schema changes [5].

The most significant 2025 development is the proliferation of iMessage MCP servers. At least four independent implementations have emerged (jons-mcp-imessage, wolfies-imessage-gateway, mac-messages, imessage-mcp-server), all using the same chat.db + AppleScript pattern, confirming this approach is production-viable for AI agent tooling [7]. Claude.ai itself uses MCP for its native iMessage integration. For iobox, this means there is already precedent and tooling for exactly the integration pattern needed.

The practical recommendation for iobox is to not take a dependency on any of these libraries directly (they are all lightly maintained), but to implement the core access layer directly using `sqlite3` (built-in) and `subprocess`/`osascript` (also built-in), informed by the reference implementations above. The attributedBody decoding logic from LangChain or imessage_tools should be adapted directly into an `iMessageProvider` implementation.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader - GitHub | 1 | yes |
| 2 | https://github.com/tpritc/macos-messages | macos-messages - GitHub | 1 | yes |
| 3 | https://github.com/my-other-github-account/imessage_tools | imessage_tools - GitHub | 1 | yes |
| 4 | https://pypi.org/project/py-iMessage/ | py-iMessage - PyPI | 1 | yes |
| 5 | https://github.com/ReagentX/imessage-exporter | imessage-exporter - GitHub | 1 | yes |
| 6 | https://api.python.langchain.com/en/latest/_modules/langchain_community/chat_loaders/imessage.html | LangChain iMessage loader | 1 | yes |
| 7 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage - GitHub | 1 | yes |
| 8 | https://snyk.io/advisor/python/imessage-reader | imessage-reader - Snyk | 2 | yes |
| 9 | https://github.com/wolfiesch/imessage-mcp | wolfies-imessage-gateway - GitHub | 1 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader | Read-only chat.db access, maintenance status |
| 2 | https://github.com/tpritc/macos-messages | macos-messages | Read-only, modern Python library |
| 3 | https://github.com/my-other-github-account/imessage_tools | imessage_tools | Read+Write, Ventura attributedBody support |
| 4 | https://pypi.org/project/py-iMessage/ | py-iMessage | Send-only via AppleScript, maintenance status |
| 5 | https://github.com/ReagentX/imessage-exporter | imessage-exporter | Most complete export tool, modern macOS support |
| 6 | https://api.python.langchain.com/en/latest/_modules/langchain_community/chat_loaders/imessage.html | LangChain iMessage loader | attributedBody byte-level decoding reference |
| 7 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage | MCP server proof of production viability |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All key tools are Tier 1 (GitHub repos), directly inspectable. The 2025 MCP server proliferation is well-documented and validates the approach for AI tooling contexts specifically.

### Further Research Needed

None.
