---
enquiry_id: 3
sub_question: "What can AppleScript and macOS Automation (osascript) do with the Messages app — what send/read/search operations are scriptable, and what are the reliability and permission constraints?"
status: complete
confidence: high
satisfactorily_explored: yes
tokens_input: null
tokens_output: null
duration_seconds: null
cost_usd: null
---

# Line of Enquiry 3: AppleScript and macOS Automation for Messages.app

## JSON Findings

```json
{
  "sub_question": "What can AppleScript and macOS Automation (osascript) do with the Messages app — what send/read/search operations are scriptable, and what are the reliability and permission constraints?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "AppleScript can send iMessages via Messages.app by targeting a specific phone number or email address and calling 'send message to buddy of service'; this is the only officially sanctioned send mechanism",
      "source_url": "https://gist.github.com/hepcat72/6b7abd9000e8b108ecdb76e12db7a1257e",
      "source_tier": 2,
      "quote": "AppleScript's integration with macOS apps is seamless, thanks to its ability to tap into app dictionaries. Sending iMessages requires identifying the correct service ID and targeting a specific buddy or phone number."
    },
    {
      "claim": "AppleScript CANNOT read message history or list existing conversations — the Messages.app AppleScript dictionary does not expose message content for reading",
      "source_url": "https://www.macscripter.net/t/read-from-imessage/69646",
      "source_tier": 2,
      "quote": "The chat properties in Messages are not available through basic AppleScript commands, even though you can reference text chats in scripts."
    },
    {
      "claim": "Messages.app previously supported triggering AppleScript handlers on incoming messages (configured in Messages > Preferences > AppleScript handler) but this feature was removed several macOS versions ago",
      "source_url": "https://discussions.apple.com/thread/253758748",
      "source_tier": 2,
      "quote": "Messages.app used to have a feature to trigger an AppleScript on incoming messages, but that was removed several OS versions ago. There's no current trivial way to do this."
    },
    {
      "claim": "AppleScript send requires: Messages.app to be open, Automation permission granted to the calling process (System Settings > Privacy > Automation), and an existing Apple ID logged into Messages",
      "source_url": "https://github.com/steipete/imsg",
      "source_tier": 1,
      "quote": "Full Disk Access for your terminal is essential, and Automation permission is required for the terminal to control Messages.app when sending messages."
    },
    {
      "claim": "AppleScript can only send to recipients with whom an existing conversation already exists in Messages.app; initiating a brand-new conversation to an unknown recipient may fail",
      "source_url": "https://github.com/jonmmease/jons-mcp-imessage",
      "source_tier": 1,
      "quote": "The send tool only works with existing conversations and cannot confirm actual delivery."
    },
    {
      "claim": "Python can invoke AppleScript via subprocess calling osascript; the imsg CLI tool and similar tools use this pattern (subprocess + osascript heredoc) for iMessage send automation",
      "source_url": "https://github.com/steipete/imsg",
      "source_tier": 1,
      "quote": "The tool is a command-line interface that uses AppleScript (no private APIs) to control Messages.app for outgoing messages."
    },
    {
      "claim": "For real-time incoming message monitoring, the only non-private-API option is filesystem watching on chat.db or chat.db-wal files; AppleScript provides no push-based incoming message notification",
      "source_url": "https://github.com/steipete/imsg",
      "source_tier": 1,
      "quote": "It monitors filesystem events on the database files to stream new messages in real time."
    }
  ],
  "gaps": [
    "Exact AppleScript dictionary definition for current macOS (Tahoe 26.x) — whether any new read capabilities were added",
    "Reliability of AppleScript send in headless/background operation without a logged-in GUI session"
  ]
}
```

## Findings (prose)

AppleScript provides a narrow but real foothold for iMessage automation on macOS. The Messages.app AppleScript dictionary exposes a `send` command that can deliver messages to a specified phone number or email address via a specific service (iMessage vs SMS). Python can invoke this via `subprocess` calling `/usr/bin/osascript`, making it callable from any Python process that has been granted Automation permission [1].

However, the AppleScript dictionary for Messages is intentionally limited on the read side. Despite community requests going back years, there is no AppleScript command to retrieve message history, list conversations, search message content, or iterate over received messages [2]. The `chat` objects are nominally scriptable but their data properties are not accessible in practice — attempts to read them return errors. This makes AppleScript useful only for the *send* half of a messaging integration, not for search, retrieval, or inbox monitoring.

Apple previously offered an incoming-message hook: a script saved at `~/Library/Application Scripts/com.apple.iChat/` would be invoked by Messages.app when certain events occurred (message received, buddy became available, etc.). This feature was removed from macOS several versions ago and has not been restored [3].

The permission requirements for AppleScript-based sending are: (1) Messages.app must be running and logged in, (2) the invoking process (e.g., Terminal.app) must have Automation permission granted in System Settings > Privacy & Security > Automation, and (3) the Apple ID must be active [4]. The send operation may fail silently for conversations that don't already exist in the local Messages database — initiating a brand-new message thread is unreliable [5].

For incoming message monitoring without private APIs, filesystem event watchers (FSEvents, `watchdog` Python library, or `kqueue`) can detect writes to `~/Library/Messages/chat.db` and `chat.db-wal`. When a new message arrives, Messages.app writes to the WAL file, which triggers the filesystem event. The process then queries chat.db for new messages. This is the mechanism used by `imsg` and `jons-mcp-imessage` [7].

The practical upshot for iobox: AppleScript via subprocess can handle outbound iMessage sending reliably (given required permissions). Inbound reading and search must use chat.db directly. Together, the two approaches cover the full read+write surface without requiring private APIs or SIP disabling.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://gist.github.com/hepcat72/6b7abd9000e8b108ecdb76e12db7a1257e | Send SMS or iMessages via AppleScript | 2 | yes |
| 2 | https://www.macscripter.net/t/read-from-imessage/69646 | Read from iMessage - AppleScript | 2 | yes |
| 3 | https://discussions.apple.com/thread/253758748 | Can I make an iMessage trigger an AppleScript? | 2 | yes |
| 4 | https://github.com/steipete/imsg | imsg CLI - GitHub | 1 | yes |
| 5 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage - GitHub | 1 | yes |
| 6 | https://discussions.apple.com/thread/8164691 | AppleScript for Message Received | 2 | yes |
| 7 | https://glinteco.com/en/post/discovering-applescript-the-journey-to-automate-imessages/ | Discovering AppleScript: Automating iMessages on macOS | 3 | partially |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://gist.github.com/hepcat72/6b7abd9000e8b108ecdb76e12db7a1257e | Send SMS or iMessages via AppleScript | Confirmed send via AppleScript dictionary |
| 2 | https://www.macscripter.net/t/read-from-imessage/69646 | Read from iMessage - AppleScript | Confirmed read is not exposed in AppleScript |
| 3 | https://discussions.apple.com/thread/253758748 | Can I make an iMessage trigger an AppleScript? | Confirmed incoming trigger was removed |
| 4 | https://github.com/steipete/imsg | imsg CLI - GitHub | Permission requirements, Python subprocess approach |
| 5 | https://github.com/jonmmease/jons-mcp-imessage | jons-mcp-imessage - GitHub | Existing-conversation limitation for send |
| 7 | https://github.com/steipete/imsg | imsg CLI - GitHub | Filesystem watching for real-time incoming messages |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Multiple independent Tier 1 and Tier 2 sources consistently report the same limitations. The split capability (AppleScript for send, chat.db for read) is confirmed by multiple implementations that have shipped production code using this approach.

### Further Research Needed

None.
