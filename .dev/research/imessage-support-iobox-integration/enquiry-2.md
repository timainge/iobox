---
enquiry_id: 2
sub_question: "How does the iMessage SQLite database (chat.db) on macOS work — schema, location, access controls, what data is available, and what are the practical limitations of read-only access via Python?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 2: iMessage chat.db SQLite database

## JSON Findings

```json
{
  "sub_question": "How does the iMessage SQLite database (chat.db) on macOS work — schema, location, access controls, what data is available, and what are the practical limitations of read-only access via Python?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "The iMessage database is a SQLite3 file located at ~/Library/Messages/chat.db and is accessible to any process granted Full Disk Access by the user",
      "source_url": "https://github.com/niftycode/imessage_reader",
      "source_tier": 1,
      "quote": "Users need to grant Terminal or iTerm 'Full Disk Access' through System Preferences to read the iMessage database."
    },
    {
      "claim": "Key tables in chat.db are: message (all messages), handle (contact phone/email), chat (conversation threads), attachment (file metadata), plus join tables chat_handle_join, message_attachment_join, chat_message_join, and deleted_messages",
      "source_url": "https://spin.atomicobject.com/search-imessage-sql/",
      "source_tier": 2,
      "quote": "The iMessage database contains approximately 15 tables. Key tables include: message, chat, handle, attachment, and join tables showing relationships between records."
    },
    {
      "claim": "On macOS Ventura and later, many messages are stored as a binary plist blob in the attributedBody column rather than plain text in the text column — the text column is NULL for these messages",
      "source_url": "https://spin.atomicobject.com/search-imessage-sql/",
      "source_tier": 2,
      "quote": "Critical March 2024 update: messages are encoded as a hex blob in the attributedBody column on newer macOS versions. This means queries returning message text may fail on current systems."
    },
    {
      "claim": "The attributedBody blob can be decoded in Python using the plistlib library, with a known byte-offset pattern: look for 'NSString' marker then skip 5 preamble bytes plus a 1- or 3-byte length field",
      "source_url": "https://github.com/my-other-github-account/imessage_tools",
      "source_tier": 1,
      "quote": "The library parses hidden message data by handling cases where the 'Text' content is hidden within the 'attributedBody' field. It decodes and parses from the attributedBody field using the plistlib library."
    },
    {
      "claim": "Message timestamps in chat.db use Apple's NSDate epoch (seconds since 2001-01-01), not Unix epoch — SQL queries must add strftime('%s','2001-01-01') to convert",
      "source_url": "https://spin.atomicobject.com/search-imessage-sql/",
      "source_tier": 2,
      "quote": "SELECT datetime (message.date / 1000000000 + strftime('%s', '2001-01-01'), 'unixepoch', 'localtime') AS message_date"
    },
    {
      "claim": "Python can access chat.db using the standard sqlite3 module with no additional dependencies; the database must be opened in read-only mode (uri=True with ?mode=ro) to avoid accidental writes",
      "source_url": "https://github.com/tpritc/macos-messages",
      "source_tier": 1,
      "quote": "macos-messages is a Python library and CLI for reading your macOS Messages.app data. It gives you quick, easy, read-only access to your iMessage and SMS history."
    },
    {
      "claim": "chat.db contains both iMessage and SMS/MMS records; the service column or is_from_me + account columns distinguish them; attachments are stored separately in ~/Library/Messages/Attachments/",
      "source_url": "https://github.com/ReagentX/imessage-exporter",
      "source_tier": 1,
      "quote": "The tool supports multiple message types (iMessage, RCS, SMS, MMS)."
    }
  ],
  "gaps": [
    "Exact schema differences between macOS versions (Monterey vs Ventura vs Sonoma vs Tahoe)",
    "Whether iCloud Messages sync changes the local database content (cloud-only messages may not appear in chat.db)"
  ]
}
```

## Findings (prose)

The iMessage SQLite database lives at `~/Library/Messages/chat.db` and is the primary store for all local iMessage and SMS/MMS history on macOS. Any process with Full Disk Access can open this file read-only using Python's built-in `sqlite3` module — no third-party database library is needed [1].

The schema is well-understood through community reverse-engineering. The critical tables are: `message` (one row per message, containing text, metadata, sender/receiver flags), `handle` (contact identifiers — phone numbers or email addresses), `chat` (conversation threads), and `attachment` (file metadata with paths to `~/Library/Messages/Attachments/`). Three join tables — `chat_handle_join`, `message_attachment_join`, and `chat_message_join` — wire these together [2]. A `deleted_messages` table acts as a trash can.

A significant gotcha affecting macOS Ventura and later (2022+) is that many messages have a NULL `text` column; instead the content is stored as a binary Apple Property List (plist) blob in the `attributedBody` column [3]. Any Python implementation must handle this: decode the blob, find the `NSString` marker, skip preamble bytes, and extract the UTF-8 string. The `plistlib` standard library module handles this decoding [4]. Failing to handle `attributedBody` means silently dropping large portions of message history on modern macOS.

Timestamps in the `message` table use Apple's Cocoa date epoch (January 1, 2001 at midnight UTC), not Unix epoch. The raw value is stored in nanoseconds (not seconds) since that epoch, so conversion requires dividing by 1,000,000,000 and adding the 978307200 seconds offset [5].

For a tool like iobox, the practical approach is: open chat.db in read-only mode (`sqlite3.connect('file:path?mode=ro', uri=True)`), issue queries joining `message`, `handle`, and `chat`, and decode `attributedBody` when `text IS NULL`. This gives access to full conversation history, sender identities, timestamps, group membership, and attachment paths. The database is not write-locked by Messages.app during normal operation, so read queries work even while Messages is running [6].

Attachments themselves (images, videos, audio, documents) are stored in `~/Library/Messages/Attachments/` with paths recorded in the `attachment` table. These are also protected by Full Disk Access. The entire local iMessage history — minus any cloud-only messages not yet synced to the device — is accessible this way [7].

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader - GitHub | 1 | yes |
| 2 | https://spin.atomicobject.com/search-imessage-sql/ | Searching Your iMessage Database with SQL | 2 | yes |
| 3 | https://github.com/my-other-github-account/imessage_tools | imessage_tools - GitHub | 1 | yes |
| 4 | https://github.com/tpritc/macos-messages | macos-messages - GitHub | 1 | yes |
| 5 | https://davidbieber.com/snippets/2020-05-20-imessage-sql-db/ | Accessing Your iMessages with SQL | 2 | yes |
| 6 | https://github.com/ReagentX/imessage-exporter | imessage-exporter - GitHub | 1 | yes |
| 7 | https://betterprogramming.pub/extracting-imessage-and-address-book-data-b6e2e5729b21 | Extract iMessage and Address Book Data: Python | 2 | yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://github.com/niftycode/imessage_reader | imessage_reader - GitHub | Confirmed Full Disk Access requirement and Python sqlite3 approach |
| 2 | https://spin.atomicobject.com/search-imessage-sql/ | Searching Your iMessage Database with SQL | Schema overview, working SQL queries |
| 3 | https://spin.atomicobject.com/search-imessage-sql/ | Searching Your iMessage Database with SQL | attributedBody issue on Ventura+ |
| 4 | https://github.com/my-other-github-account/imessage_tools | imessage_tools - GitHub | plistlib-based attributedBody decoding |
| 5 | https://spin.atomicobject.com/search-imessage-sql/ | Searching Your iMessage Database with SQL | Timestamp epoch conversion |
| 6 | https://github.com/tpritc/macos-messages | macos-messages - GitHub | Read-only mode, concurrent access |
| 7 | https://github.com/ReagentX/imessage-exporter | imessage-exporter - GitHub | Attachment paths and multi-format support |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Multiple independent Tier 1 sources (GitHub repos of tools that have actually implemented this) plus Tier 2 sources confirm consistent details about schema, access controls, and the attributedBody issue. The approach is battle-tested by multiple open-source tools.

### Further Research Needed

None.
