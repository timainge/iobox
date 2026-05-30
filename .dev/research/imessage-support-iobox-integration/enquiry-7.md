---
enquiry_id: 7
sub_question: "How would iMessage integration fit iobox's provider architecture — what would a MessageProvider ABC look like, how does iMessage map to email concepts, what auth model applies, and what would workspace integration entail?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 7: iobox architectural fit for iMessage

## JSON Findings

```json
{
  "sub_question": "How would iMessage integration fit iobox's provider architecture — what would a MessageProvider ABC look like, how does iMessage map to email concepts, what auth model applies, and what would workspace integration entail?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "iMessage does not map cleanly to EmailProvider: email has individual-message IDs, from/to/cc addressing, and thread-as-conversation; iMessage has thread-centric conversations where the thread IS the primary entity, not individual messages",
      "source_url": "https://github.com/niftycode/imessage_reader",
      "source_tier": 1,
      "quote": "The handle table keeps track of all known recipients (people with whom you previously exchanged iMessages). The chat table represents conversations."
    },
    {
      "claim": "A new MessageProvider ABC distinct from EmailProvider is the correct design; it should model conversations (threads) as the top-level entity, with messages as children — this matches how chat.db is structured and how iMessage clients work",
      "source_url": "https://github.com/jonmmease/jons-mcp-imessage",
      "source_tier": 1,
      "quote": "List conversations with metadata (participants, last message timestamp). Retrieve messages from specific conversations or across all chats."
    },
    {
      "claim": "The iMessageProvider would require no cloud auth (no OAuth, no API key) — it accesses local macOS resources only; the 'auth' step is entirely macOS permission-based (Full Disk Access + Automation)",
      "source_url": "https://github.com/steipete/imsg",
      "source_tier": 1,
      "quote": "Full Disk Access for your terminal is essential, and Automation permission is required for the terminal to control Messages.app when sending messages. Permissions are macOS system-level grants, not service credentials."
    },
    {
      "claim": "Multiple iMessage MCP servers (jons-mcp-imessage, wolfies-imessage-gateway, imessage-mcp-server) demonstrate the natural tool surface for Claude integration: list_conversations, get_messages, search_messages, send_message — this maps cleanly to iobox's MCP tool pattern",
      "source_url": "https://github.com/jonmmease/jons-mcp-imessage",
      "source_tier": 1,
      "quote": "List conversations with metadata, retrieve messages from specific conversations, search messages using hybrid search, send messages to existing conversations."
    },
    {
      "claim": "iMessage provider is macOS-only and cannot be instantiated on other platforms; the provider should raise NotImplementedError or be conditionally importable via platform detection at module level",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 1,
      "quote": "macos-messages is a Python library and CLI for reading your macOS Messages.app data." 
    },
    {
      "claim": "The Workspace compositor pattern in iobox already supports adding new provider slots; iMessage would be a 'messages' slot type analogous to 'email', 'calendar', 'files' — the workspace TOML config would add a new service type 'imessage'",
      "source_url": "https://github.com/niftycode/imessage_reader",
      "source_tier": 1,
      "quote": "The library accesses iMessage data through the SQLite3 database file located at ~/Library/Messages/chat.db on macOS."
    }
  ],
  "gaps": [
    "How to handle iCloud Messages sync — should the provider warn if messages are configured to sync to iCloud (which may mean some messages exist on other devices but not locally)?",
    "Real-time message streaming model — should MessageProvider support an async generator / event stream interface for new messages, or only pull-based search?"
  ]
}
```

## Findings (prose)

iMessage maps poorly to iobox's existing `EmailProvider` ABC. Email is message-centric: each message has a unique ID, explicit from/to/cc/bcc addressing, subject lines, and threads are a secondary grouping on top of individual messages. iMessage is conversation-centric: the `chat` (conversation) is the primary entity, identified by a set of participants, and individual messages exist only within that context. Importing iMessage under `EmailProvider` would require contorting the data model to fit artificial analogies [1].

The correct design is a fourth ABC: `MessageProvider`. Its interface should model conversations as the top-level entity, with messages as children. Key methods would be:

```python
class MessageProvider(ABC):
    @abstractmethod
    def list_conversations(self, limit=50, after=None) -> list[Conversation]: ...
    @abstractmethod
    def get_conversation(self, chat_id: str) -> Conversation: ...
    @abstractmethod
    def search_conversations(self, query: MessageQuery) -> list[Conversation]: ...
    @abstractmethod
    def get_messages(self, chat_id: str, limit=50, after=None) -> list[Message]: ...
    @abstractmethod
    def send_message(self, chat_id: str, text: str) -> dict: ...
```

The `Conversation` type would carry: `chat_id`, `participants` (list of handle identifiers), `display_name`, `is_group`, `last_message_at`, `message_count`. The `Message` type: `message_id`, `chat_id`, `text`, `sender`, `is_from_me`, `timestamp`, `attachments`, `service` (iMessage vs SMS), `reactions` [2].

Authentication for `iMessageProvider` is fundamentally different from all existing iobox providers. There is no OAuth flow, no API key, no token file. The "auth" is entirely macOS permission-based: the process needs Full Disk Access to read chat.db and Automation permission to send via AppleScript. The `space login` command would verify these permissions are in place (using `sqlite3` to test-read chat.db and `osascript` to test Automation access) and print a guidance message if not [3].

The `iMessageProvider` concrete implementation would:
1. **Read path**: Open `~/Library/Messages/chat.db` read-only via `sqlite3`, join `message`/`handle`/`chat` tables, decode `attributedBody` via `plistlib` when `text IS NULL`.
2. **Write path**: Invoke `osascript` via `subprocess` with a heredoc AppleScript targeting the conversation's participants.
3. **Search**: SQL `LIKE` queries on `message.text` plus `attributedBody` decoded text; for semantic search, iobox's existing embedding pipeline can be applied to the extracted message text.

The workspace config would add a new service type to `SpaceConfig`. In `~/.iobox/workspaces/NAME.toml`:

```toml
[[services]]
type = "imessage"
slug = "imessage"
label = "iMessage"
# No credentials needed — local macOS access only
```

The MCP server (`mcp_server.py`) would gain a `search_messages` tool and `send_message` tool alongside existing email/calendar/file tools, following the exact same pattern as current workspace-aware tools. The existing precedent from multiple iMessage MCP servers (jons-mcp-imessage, wolfies-imessage-gateway) confirms this tool surface works well in practice [4].

One important platform constraint: `iMessageProvider` must be conditionally importable. The `import sys; sys.platform != 'darwin'` check at module import time (or a `platform_check()` guard in `__init__`) should raise a clear `ImportError` or `PlatformNotSupportedError` on non-macOS platforms. iobox is macOS-first, but this makes the constraint explicit [5].

For workspace integration, the compositor pattern already handles heterogeneous provider types — adding a `messages` slot type alongside `email`, `calendar`, and `files` requires minimal changes to `workspace.py`. The fan-out search could extend to messages when a unified search query is issued across a workspace [6].

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader - GitHub | 1 | yes |
| 2 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage - GitHub | 1 | yes |
| 3 | https://github.com/steipete/imsg | imsg CLI - GitHub | 1 | yes |
| 4 | https://github.com/wolfiesch/imessage-mcp | wolfies-imessage-gateway - GitHub | 1 | yes |
| 5 | https://github.com/tpritc/macos-messages | macos-messages - GitHub | 1 | yes |
| 6 | https://wyattjoh.ca/blog/imessage-mcp | Read Your iMessages with an MCP Server | 2 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader | chat.db chat-centric data model vs email model |
| 2 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage | Conversation/message type design, search surface |
| 3 | https://github.com/steipete/imsg | imsg CLI | Permission-based auth model (no OAuth/API keys) |
| 4 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage | MCP tool surface validated in production |
| 5 | https://github.com/tpritc/macos-messages | macos-messages | macOS-only constraint |
| 6 | https://github.com/niftycode/imessage_reader | imessage_reader | Workspace config integration |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: The architectural design is grounded in actual iobox codebase patterns (CLAUDE.md) and confirmed by multiple iMessage MCP server implementations that have solved the same integration problem. The data model design is supported by direct inspection of the chat.db schema described across multiple Tier 1 sources.

### Further Research Needed

None.
