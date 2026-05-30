# Research Context: How could iMessage support be added to iobox?

---

## Enquiry 1: What official Apple APIs and frameworks exist for programmatic iMessage access on macOS?

**Confidence**: high | **Coverage**: yes

- Apple provides no public iMessage API for programmatic send/receive; the only sanctioned developer pathway (iMessage Apps) is a UI sticker/extension framework, not automation [Apple Developer](https://developer.apple.com/imessage/)
- Messages for Business is enterprise-only, delivers grey-bubble messages (not iMessage), and requires Apple approval — not usable for personal tooling [Lindy.ai](https://www.lindy.ai/blog/imessage-api-three-rewrites-one-apple-ban-and-what-actually-works)
- Apple's private IMCore framework powers iMessage internally; accessing it requires SIP disabling and Objective-C injection using undocumented headers [BlueBubbles Helper](https://github.com/BlueBubblesApp/bluebubbles-helper)
- Apple DTS engineering explicitly recommends against private APIs: "unsupported and can change without notice or warning" [Apple Developer Forums](https://developer.apple.com/forums/thread/702740)
- AppleScript's Messages.app dictionary supports sending only — not reading message history [imsg](https://github.com/steipete/imsg)
- Notarization does not currently audit for private API use, but Apple has reserved the right to restrict this in future [Apple Developer Forums](https://developer.apple.com/forums/thread/702740)

**Gaps**: Whether macOS 26 Tahoe adds any new iMessage developer APIs.

---

## Enquiry 2: iMessage chat.db SQLite database — schema, location, access, Python limitations

**Confidence**: high | **Coverage**: yes

- chat.db is at `~/Library/Messages/chat.db` (SQLite3), accessible to any process with Full Disk Access [imessage_reader](https://github.com/niftycode/imessage_reader)
- Key tables: `message`, `handle` (contact phone/email), `chat` (conversation threads), `attachment`; plus join tables `chat_handle_join`, `message_attachment_join`, `chat_message_join` [Atomic Object](https://spin.atomicobject.com/search-imessage-sql/)
- On macOS Ventura+, many messages have NULL `text` column; content is in `attributedBody` as binary plist blob — must decode with plistlib [imessage_tools](https://github.com/my-other-github-account/imessage_tools)
- attributedBody decoding: find NSString marker, skip 5 preamble bytes + 1- or 3-byte length prefix, extract UTF-8 string [LangChain source](https://api.python.langchain.com/en/latest/_modules/langchain_community/chat_loaders/imessage.html)
- Timestamps use Apple's NSDate epoch (seconds since 2001-01-01) stored in nanoseconds — convert: `date / 1e9 + 978307200` [Atomic Object](https://spin.atomicobject.com/search-imessage-sql/)
- Python built-in `sqlite3` module is sufficient; open with `uri=True` and `?mode=ro` for read-only access [macos-messages](https://github.com/tpritc/macos-messages)
- Attachments stored in `~/Library/Messages/Attachments/` with paths in the `attachment` table; also protected by Full Disk Access [imessage-exporter](https://github.com/ReagentX/imessage-exporter)

**Gaps**: Schema differences across macOS versions; cloud-only messages not yet synced to device.

---

## Enquiry 3: AppleScript and macOS Automation for Messages.app

**Confidence**: high | **Coverage**: yes

- AppleScript can send iMessages via Messages.app using `send message to buddy of service`; this is the only sanctioned non-database automation mechanism [AppleScript gist](https://gist.github.com/hepcat72/6b7abd9000e8b108ecdb76e12db7a1257e)
- AppleScript CANNOT read message history or list conversations — the Messages.app AppleScript dictionary does not expose read operations [MacScripter](https://www.macscripter.net/t/read-from-imessage/69646)
- The incoming-message AppleScript handler feature was removed from Messages.app several macOS versions ago [Apple Discussions](https://discussions.apple.com/thread/253758748)
- Sending requires: Messages.app open, Automation permission granted to the invoking process, valid Apple ID in Messages [imsg](https://github.com/steipete/imsg)
- Send only works to existing conversations; initiating brand-new threads may fail silently [jons-mcp-imessage](https://github.com/jonmmease/jons-mcp-imessage)
- Real-time incoming message monitoring requires filesystem watching on chat.db-wal — AppleScript provides no push notification [imsg](https://github.com/steipete/imsg)
- Python invokes AppleScript via `subprocess` + `osascript`; no additional dependencies needed [imsg](https://github.com/steipete/imsg)

**Gaps**: Whether macOS 26 Tahoe added any new AppleScript dictionary entries for Messages.

---

## Enquiry 4: Third-party iMessage bridges — technical mechanisms

**Confidence**: high | **Coverage**: yes

- All major bridges (BlueBubbles, AirMessage, Beeper/mautrix-imessage) require a Mac running 24/7 with iMessage active; they relay through Messages.app, not an alternative protocol [XDA Developers](https://www.xda-developers.com/bluebubbles-vs-airmessage/)
- BlueBubbles architecture: chat.db polling (receive) + AppleScript (send basic) + IMCore private API bundle (reactions, typing indicators, read receipts) [BlueBubbles Docs](https://docs.bluebubbles.app/server)
- BlueBubbles Private API requires SIP disabling: "Apple does not let us access the internal iMessage code to do things like send reactions if SIP is enabled" [BlueBubbles Private API](https://docs.bluebubbles.app/private-api/installation)
- mautrix-imessage (Beeper): same chat.db + AppleScript baseline; SIP disabled enables full features, normal Mac gives basic bridging [mautrix/imessage](https://github.com/mautrix/imessage)
- BlueBubbles exposes REST + WebSocket API over HTTPS (Ngrok/Cloudflare/DDNS); iobox could consume this API as an alternative to direct chat.db access [BlueBubbles Docs](https://docs.bluebubbles.app/server/developer-guides/rest-api-and-webhooks)
- Lindy.ai's Apple ID bans were triggered by high-volume automated sending with unusual send/receive ratios — risk is specific to bulk messaging infrastructure, not personal tooling [Lindy.ai](https://www.lindy.ai/blog/imessage-api-three-rewrites-one-apple-ban-and-what-actually-works)

**Gaps**: Whether any bridge handles iCloud Messages sync; initiating brand-new conversations to unknown contacts.

---

## Enquiry 5: Python libraries for iMessage integration

**Confidence**: high | **Coverage**: yes

- imessage_reader: read-only via chat.db, Python 3.9+, macOS 10.14+; marked Inactive on Snyk (no recent PyPI releases) but still functional [imessage_reader](https://github.com/niftycode/imessage_reader)
- imessage_tools: best read+write option for Ventura+; handles attributedBody decoding via plistlib AND sending via AppleScript; tested on macOS Ventura [imessage_tools](https://github.com/my-other-github-account/imessage_tools)
- macos-messages: modern read-only Python library + CLI; good code quality; cannot send [macos-messages](https://github.com/tpritc/macos-messages)
- imessage-exporter: Rust tool (PyPI wrapper) with most complete macOS version support; handles tapbacks, edits, stickers, reactions; actively maintained [imessage-exporter](https://github.com/ReagentX/imessage-exporter)
- LangChain iMessage loader: production-grade reference for attributedBody decoding with documented byte-level parsing [LangChain](https://api.python.langchain.com/en/latest/_modules/langchain_community/chat_loaders/imessage.html)
- Multiple iMessage MCP servers in 2025 validate the chat.db + AppleScript pattern for AI agent integration (Claude.ai uses this natively) [jons-mcp-imessage](https://github.com/jonmmease/jons-mcp-imessage)
- Recommendation: implement directly using stdlib (`sqlite3`, `subprocess`, `plistlib`) informed by these reference implementations — avoid taking dependencies on lightly-maintained libraries

**Gaps**: Real-time streaming interface; maintenance dates not independently verified.

---

## Enquiry 6: Privacy, security, TOS, and legal constraints

**Confidence**: high | **Coverage**: yes

- Full Disk Access (macOS TCC, Mojave 10.14+) required to read chat.db; user grants this explicitly in System Settings [Apple Security Guide](https://support.apple.com/guide/security/controlling-app-access-to-files-secddd1d86a6/web)
- Automation permission required for AppleScript send; separate from Full Disk Access, also user-granted [imsg](https://github.com/steipete/imsg)
- iMessage E2E encryption means messages are stored in plaintext in chat.db on the local device; reading chat.db is accessing your own locally-decrypted data, not breaking encryption [Apple Security Guide](https://support.apple.com/guide/security/imessage-security-overview-secd9764312f/web)
- iCloud TOS clause prohibiting "automated means" applies to the iCloud network service, not local macOS automation of Messages.app [Apple Legal](https://www.apple.com/legal/internet-services/icloud/us-en/terms.html)
- Account ban risk applies to high-volume automated sending; single-user personal tooling carries no documented risk [Lindy.ai](https://www.lindy.ai/blog/imessage-api-three-rewrites-one-apple-ban-and-what-actually-works)
- SIP disabling required only for private API (IMCore); the chat.db + AppleScript approach leaves SIP intact [Apple Security Guide](https://support.apple.com/guide/security/system-integrity-protection-secb7ea06b49/web)

**Gaps**: Whether Apple has ever enforced TOS automation clause against personal scripting tools (no cases found).

---

## Enquiry 7: iobox architectural fit for iMessage

**Confidence**: high | **Coverage**: yes

- iMessage does not map to EmailProvider: it is conversation-centric (chat is the primary entity), not message-centric (message is primary) — a new MessageProvider ABC is needed [imessage_reader](https://github.com/niftycode/imessage_reader)
- MessageProvider ABC methods: `list_conversations`, `get_conversation`, `search_conversations`, `get_messages`, `send_message` — matching MCP tool patterns already validated by multiple iMessage MCP servers [jons-mcp-imessage](https://github.com/jonmmease/jons-mcp-imessage)
- Auth model is macOS-permission-based (no OAuth, no API key, no token file); `space login` would verify Full Disk Access and Automation permissions via test calls [imsg](https://github.com/steipete/imsg)
- Workspace TOML config adds a new `[[services]] type = "imessage"` entry with no credentials — the provider is self-configuring from macOS permissions [imessage_reader](https://github.com/niftycode/imessage_reader)
- iMessageProvider must be conditionally importable with a macOS platform check; raise a clear error on non-darwin platforms [macos-messages](https://github.com/tpritc/macos-messages)
- MCP server gains `search_messages` and `send_message` tools following existing workspace-aware tool pattern [jons-mcp-imessage](https://github.com/jonmmease/jons-mcp-imessage)
- Iobox's existing embedding pipeline (`processing/embed.py`) can be applied to extracted message text for semantic search without changes [iobox CLAUDE.md]

**Gaps**: iCloud Messages sync warning; real-time streaming vs pull-based interface design decision.

---
