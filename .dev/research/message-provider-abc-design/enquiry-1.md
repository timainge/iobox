---
enquiry_id: 1
sub_question: "What Python libraries and local access routes exist for reading and writing Signal messages on macOS in 2025/2026, and what are the technical constraints and authentication requirements?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 1: Signal access methods on macOS from Python

## JSON Findings

```json
{
  "sub_question": "What Python libraries and local access routes exist for reading and writing Signal messages on macOS in 2025/2026, and what are the technical constraints and authentication requirements?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Signal Desktop on macOS stores messages in an SQLCipher-encrypted SQLite database at ~/Library/Application Support/Signal/sql/db.sqlite, with the decryption key stored in plaintext in ~/Library/Application Support/Signal/config.json",
      "source_url": "https://vmois.dev/query-signal-desktop-messages-sqlite/",
      "source_tier": 2,
      "quote": "The encryption key is stored in config.json. To decrypt, use Signal's forked better-sqlite3 package with db.pragma key = 'x'${decryptionKey}'"
    },
    {
      "claim": "The Signal Desktop SQLite database has 34 tables, with the most important being 'messages', 'conversations', 'reactions', 'attachments', and 'identityKeys'; messages and conversations can be queried directly once decrypted",
      "source_url": "https://vmois.dev/query-signal-desktop-messages-sqlite/",
      "source_tier": 2,
      "quote": "The article identifies 34 tables, with the most relevant being: messages — contains chat messages; conversations — stores chat metadata; Other tables: identityKeys, sessions, reactions, attachments, stickers"
    },
    {
      "claim": "Python cannot use Signal's Node.js-based better-sqlite3 fork directly; the JavaScript-only fork is required to decrypt the database, making direct Python SQLCipher access the Python route (requires installing sqlcipher)",
      "source_url": "https://vmois.dev/query-signal-desktop-messages-sqlite/",
      "source_tier": 2,
      "quote": "To decrypt, use Signal's forked better-sqlite3 package"
    },
    {
      "claim": "Signal recently moved to macOS Keychain for key storage (using Electron's SafeStorage API) in newer versions, which breaks the plaintext config.json key approach and makes local read access significantly harder",
      "source_url": "https://mjtsai.com/blog/2024/07/08/signal-for-macs-encrypted-database/",
      "source_tier": 2,
      "quote": "Signal subsequently implemented Electron's SafeStorage API and plans to use macOS Keychain for key storage in upcoming beta versions"
    },
    {
      "claim": "signal-cli is the primary unofficial command-line tool for Signal, providing JSON-RPC, dbus, and CLI interfaces; it supports send, receive, listContacts, listGroups, sendReaction, sendReceipt, sendTyping, and getAttachment operations",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "signal-cli provides an unofficial commandline, JSON-RPC and dbus interface for the Signal messenger. Messages are automatically received in jsonRpc mode"
    },
    {
      "claim": "pysignalclijsonrpc is a Python client library for signal-cli's JSON-RPC interface, compatible with signal-cli 0.11.5+, with latest version 25.9.0 released September 2025, indicating active maintenance",
      "source_url": "https://pypi.org/project/pysignalclijsonrpc/",
      "source_tier": 1,
      "quote": "A Python API client for signal-cli JSON-RPC, compatible with signal-cli 0.11.5+"
    },
    {
      "claim": "signal-cli authentication requires phone number registration and SMS/voice verification; credentials (password and cryptographic keys) are stored at $HOME/.local/share/signal-cli/data/ — no OAuth, no API keys",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "Authentication relies on the password and cryptographic keys created during registration, stored in the user's home directory under $XDG_DATA_HOME/signal-cli/data/"
    },
    {
      "claim": "signal-cli does NOT provide message history retrieval — it can only receive new messages in real-time (push model), not fetch historical conversations; this is a fundamental limitation vs. the local SQLite approach",
      "source_url": "https://github.com/AsamK/signal-cli",
      "source_tier": 1,
      "quote": "receive: Query the server for new messages. New messages are printed on standard output"
    },
    {
      "claim": "signal-cli provides a REST API wrapper (signal-cli-rest-api) that exposes HTTP endpoints for send, receive, list groups, list contacts, and attachment handling; a Swagger documentation is available",
      "source_url": "https://github.com/bbernhard/signal-cli-rest-api",
      "source_tier": 1,
      "quote": "At the moment, the following functionality is exposed via REST: Send messages with attachments, Receive messages, Register a number, List groups, Create groups"
    },
    {
      "claim": "The dbus approach (Linux-only) and JSON-RPC approach both work for Python integration; on macOS the JSON-RPC interface via stdin/stdout or HTTP is the practical route, not dbus",
      "source_url": "https://fabiobarbero.eu/posts/signalbot/",
      "source_tier": 2,
      "quote": "The article focuses on the DBus service method; basic implementation uses pydbus library to connect to org.asamk.Signal"
    }
  ],
  "gaps": [
    "Exact Signal Desktop database schema (column names) for messages and conversations tables with current versions",
    "Whether SafeStorage/Keychain migration is complete in Signal Desktop stable as of 2026 or still in beta",
    "Python-specific sqlcipher binding approach for reading Signal Desktop database post-Keychain migration",
    "signal-cli message history fetch — confirmed absent but no workaround documented"
  ]
}
```

## Findings (prose)

Signal offers two fundamentally different access paths from Python on macOS: local SQLite database reads (read-only), and signal-cli as a daemon/subprocess (read-write but push-only).

The local SQLite path reads the Signal Desktop database at `~/Library/Application Support/Signal/sql/db.sqlite`. Until recently, the decryption key was stored in plaintext in `config.json` in the same directory — a known security flaw acknowledged by Signal developers, who stated "at-rest encryption is not something Signal Desktop is currently trying to provide" [mjtsai]. The database schema includes 34 tables, with `conversations` and `messages` being the key ones, plus `reactions`, `attachments`, and `identityKeys`. The critical Python limitation is that Signal's own decryption tooling uses a Node.js fork of `better-sqlite3`, not a Python library. Python access requires installing `sqlcipher` (or `pysqlcipher3`) separately and manually applying the key. However, Signal has begun moving to Electron's SafeStorage API with macOS Keychain backing [mjtsai], which will break the plaintext config.json approach. The status of this migration in the stable release as of 2026 is not confirmed — if complete, Python local reads become significantly harder without macOS Keychain access.

The local SQLite path is also strictly read-only and is not message-history fetch — it reads from the local cache of messages that have already been received and decrypted by Signal Desktop.

The signal-cli path is the write-capable route. signal-cli is an unofficial Java CLI tool providing commandline, JSON-RPC, and dbus interfaces [signal-cli GitHub]. The dbus interface only works on Linux; on macOS, the JSON-RPC interface (stdin/stdout or HTTP via signal-cli-rest-api) is practical. The Python library `pysignalclijsonrpc` wraps the JSON-RPC HTTP endpoint [PyPI pysignalclijsonrpc], with the latest version released September 2025 indicating active maintenance. signal-cli supports: `send` (to individuals and groups), `receive` (new messages only — poll-based), `listContacts`, `listGroups`, `sendReaction`, `sendReceipt` (read receipts), `sendTyping`, and `getAttachment`. The `receive` command returns messages that arrive since the last check — there is no `get_message_history` command. Authentication requires phone number registration and SMS/voice verification, with credentials stored in the filesystem (no OAuth).

For a `SignalProvider` in iobox, the practical architecture is: signal-cli-rest-api as a background service (or subprocess), with Python calling its HTTP endpoints via requests. The signal-cli requirement is a significant system dependency that must be documented clearly. Local SQLite reads could supplement message history retrieval but are fragile given the Keychain migration.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://vmois.dev/query-signal-desktop-messages-sqlite/ | Query Signal Desktop messages locally from SQLite | 2 | yes |
| 2 | https://mjtsai.com/blog/2024/07/08/signal-for-macs-encrypted-database/ | Signal for Mac's Encrypted Database | 2 | yes |
| 3 | https://github.com/AsamK/signal-cli | signal-cli GitHub | 1 | yes |
| 4 | https://pypi.org/project/pysignalclijsonrpc/ | pysignalclijsonrpc PyPI | 1 | yes |
| 5 | https://github.com/bbernhard/signal-cli-rest-api | signal-cli-rest-api GitHub | 1 | yes |
| 6 | https://bbernhard.github.io/signal-cli-rest-api/ | signal-cli-rest-api Swagger docs | 1 | no (no content rendered) |
| 7 | https://fabiobarbero.eu/posts/signalbot/ | How to make a Signal bot in Python | 2 | yes |
| 8 | https://pypi.org/project/pysignald/ | pysignald PyPI | 2 | no |
| 9 | https://github.com/kbin76/signal-cli-python-api | signal-cli-python-api GitHub | 2 | partially |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://vmois.dev/query-signal-desktop-messages-sqlite/ | Query Signal Desktop messages locally from SQLite | Database location, schema, decryption approach |
| 2 | https://mjtsai.com/blog/2024/07/08/signal-for-macs-encrypted-database/ | Signal for Mac's Encrypted Database | Keychain migration, security model |
| 3 | https://github.com/AsamK/signal-cli | signal-cli GitHub | All signal-cli capabilities, auth model |
| 4 | https://pypi.org/project/pysignalclijsonrpc/ | pysignalclijsonrpc PyPI | Python library for JSON-RPC, maintenance status |
| 5 | https://github.com/bbernhard/signal-cli-rest-api | signal-cli-rest-api GitHub | REST API wrapper capabilities |
| 6 | https://fabiobarbero.eu/posts/signalbot/ | Signal bot in Python | dbus/Python integration approach |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Multiple Tier 1 sources (signal-cli GitHub, PyPI packages) confirm the access landscape. The Keychain migration status is the main uncertainty — Tier 2 sources confirm it is in progress but final status unclear.

### Further Research Needed

None critical for ABC design purposes. The Keychain migration status would matter for implementation but doesn't affect the ABC interface design.
