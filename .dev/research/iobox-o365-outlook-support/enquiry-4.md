# Line of Enquiry 4: Outlook mail folders and categories vs Gmail labels

## JSON Findings

```json
{
  "sub_question": "How do Outlook folders and categories compare to Gmail labels?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    "Outlook uses a hierarchical folder model (mailFolder resource with parentFolderId and childFolders) where each message resides in exactly one folder. Gmail uses a flat label model where multiple labels can be applied to a single message simultaneously.",
    "Outlook categories (outlookCategory resource) are color-coded tags with a displayName and one of 25 preset colors. They are the closest analog to Gmail labels since multiple categories can be applied to a single message. Categories are applied by writing to the message's 'categories' string array property via PATCH.",
    "Gmail's 'star' maps to Outlook's followupFlag with flagStatus='flagged'. Gmail sets star by adding the STARRED label; Outlook sets flag via PATCH on the message's flag property. Outlook flags are richer, supporting startDateTime, dueDateTime, and completedDateTime.",
    "Gmail's 'mark as read' (remove UNREAD label) maps to Outlook's isRead boolean property on the message resource, set via PATCH /me/messages/{id} with {isRead: true}.",
    "Gmail's 'archive' (remove INBOX label) maps to Outlook's message move operation: POST /me/messages/{id}/move with destinationId='archive'. This physically relocates the message to the archive folder.",
    "Gmail label add/remove is a single API call (users.messages.modify with addLabelIds/removeLabelIds). Outlook requires different APIs for different operations: PATCH for isRead/flag/categories, POST .../move for folder changes.",
    "Outlook well-known folders (inbox, drafts, sentitems, deleteditems, junkemail, archive, etc.) correspond roughly to Gmail system labels (INBOX, DRAFT, SENT, TRASH, SPAM, etc.), but they are real folders, not labels.",
    "Outlook has inferenceClassification (focused/other) for Focused Inbox, which has no direct Gmail equivalent. Gmail has CATEGORY_* labels (PROMOTIONS, SOCIAL, etc.) which have no direct Outlook equivalent.",
    "A message's folder membership is indicated by parentFolderId in Outlook (singular). In Gmail, a message can have any number of label IDs. This is the most fundamental architectural difference for iobox's abstraction layer."
  ],
  "gaps": [
    "Batch operations: Gmail supports batchModify for up to 1000 messages in one call. Microsoft Graph supports JSON batching ($batch endpoint) but not a direct equivalent of batchModify for label/folder operations.",
    "No investigation of how Outlook rules (messageRule resource) compare to Gmail filters for automated label/folder assignment."
  ]
}
```

## Findings (prose)

**Folder hierarchy vs flat labels.** The most fundamental architectural difference between Outlook and Gmail is their organizational model. Outlook organizes messages into a strict hierarchical folder tree, represented by the `mailFolder` resource type in Microsoft Graph. Each folder has a `parentFolderId`, can contain `childFolders`, and every message belongs to exactly one folder (identified by the message's `parentFolderId` property). In contrast, Gmail uses a flat labeling system where any number of labels can be applied to a single message simultaneously. A Gmail message in the Inbox with a "Projects" label and a "Client-A" label appears in all three views without duplication. In Outlook, achieving similar cross-cutting organization requires either duplicating the message (via copy) or using categories alongside folders [1][2].

**Outlook categories as the closest analog to Gmail labels.** Outlook categories (`outlookCategory` resource) are color-coded tags defined in a user's master category list. Each category has a unique `displayName` and a `color` property mapped to one of 25 preset color constants (Preset0 through Preset24, corresponding to colors like Red, Orange, Blue, Purple, etc.). Multiple categories can be applied to a single message by updating the message's `categories` string array via a PATCH request. This makes categories the closest functional equivalent to Gmail's custom labels -- both are tag-like, both support multiple assignments per message, and both are user-defined. However, categories lack hierarchy (no parent-child nesting), whereas Gmail labels support a naming-convention-based hierarchy using forward slashes (e.g., "Projects/Client-A") [3][4].

**Message flags vs Gmail stars.** Gmail implements starring by adding the `STARRED` system label to a message. Outlook uses the `followupFlag` complex type on the message resource, with a `flagStatus` enum of `notFlagged`, `flagged`, or `complete`. Outlook's flag is richer than Gmail's star: it supports `startDateTime`, `dueDateTime`, and `completedDateTime` for task-like follow-up tracking. To flag a message in Outlook, you PATCH the message with `{"flag": {"flagStatus": "flagged"}}`. For iobox's abstraction, the mapping is straightforward: star maps to flagStatus=flagged, unstar maps to flagStatus=notFlagged [5][6].

**Read/unread state.** Gmail represents read state as the presence or absence of the `UNREAD` label. Removing `UNREAD` marks a message as read; adding it marks as unread. Outlook uses a boolean `isRead` property directly on the message resource. Setting `isRead` to `true` via PATCH marks the message as read; setting it to `false` marks it as unread. This is actually simpler than Gmail's approach since it does not require resolving label IDs [2][7].

**Archiving.** In Gmail, archiving means removing the `INBOX` label from a message -- the message remains accessible via search and other labels but no longer appears in the inbox. In Outlook, archiving means moving the message to the dedicated `archive` well-known folder via `POST /me/messages/{id}/move` with `{"destinationId": "archive"}`. This is a physical relocation: the message leaves the inbox folder entirely. The Outlook archive folder is not the same as Exchange Online's Archive Mailbox feature (in-place archiving), which Microsoft Graph does not support. For iobox, the key difference is that Gmail archive is a label removal (non-destructive, message keeps other labels) while Outlook archive is a folder move (message changes parentFolderId) [1][8].

**Moving messages between folders.** Outlook's `message: move` API (`POST /me/messages/{id}/move`) creates a new copy in the destination folder and removes the original. Importantly, the message gets a new `id` after being moved (unless the `Prefer: IdType="ImmutableId"` header is used). Gmail has no equivalent folder-move concept because messages are not in folders -- adding and removing labels is the organizational primitive. For iobox to support both backends, operations like "move to folder X" on Outlook would need to map to "add label X, remove label Y" on Gmail, and vice versa [8][9].

**Well-known folders vs system labels.** Outlook defines well-known folder names that can be used in API calls regardless of locale: `inbox`, `drafts`, `sentitems`, `deleteditems`, `junkemail`, `archive`, `outbox`, `clutter`, and others. Gmail defines system labels: `INBOX`, `SENT`, `DRAFT`, `TRASH`, `SPAM`, `STARRED`, `UNREAD`, `IMPORTANT`, and `CATEGORY_*` labels. The mapping is mostly direct (inbox to INBOX, sentitems to SENT, deleteditems to TRASH, junkemail to SPAM, drafts to DRAFT), though some concepts differ. Gmail's `IMPORTANT` label and `CATEGORY_SOCIAL`/`CATEGORY_PROMOTIONS` labels have no direct Outlook folder equivalents; Outlook's `inferenceClassification` (focused/other for Focused Inbox) has no Gmail equivalent [1][2].

**Implications for iobox's abstraction layer.** The core challenge is that Gmail's label model is additive (attach/detach tags) while Outlook's folder model is positional (move between containers). iobox's current `modify_message_labels()` function, which adds and removes label IDs, would need to be decomposed for Outlook into: (a) PATCH for isRead, flag, and categories changes, and (b) POST .../move for folder changes. The `batch_modify_labels()` function for up to 1000 messages would need to use Microsoft Graph's JSON batching endpoint (`$batch`), which supports up to 20 requests per batch. The `resolve_label_name()` and `get_label_map()` functions would need dual implementations -- one for Gmail labels and one that merges Outlook folders and categories into a unified namespace [2][7][8].

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0 | mailFolder resource type - Microsoft Graph v1.0 | Tier 1 | Yes |
| 2 | https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0 | message resource type - Microsoft Graph v1.0 | Tier 1 | Yes |
| 3 | https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0 | outlookCategory resource type - Microsoft Graph v1.0 | Tier 1 | Yes |
| 4 | https://learn.microsoft.com/en-us/graph/outlook-mail-concept-overview | Outlook mail API overview - Microsoft Graph | Tier 1 | Yes |
| 5 | https://learn.microsoft.com/en-us/graph/api/resources/followupflag?view=graph-rest-1.0 | followupFlag resource type - Microsoft Graph v1.0 | Tier 1 | Yes |
| 6 | https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0 | Update message - Microsoft Graph v1.0 | Tier 1 | Yes |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0 | message: move - Microsoft Graph v1.0 | Tier 1 | Yes |
| 8 | https://hiverhq.com/blog/labels-vs-folders-guide | Labels vs Folders, Automated Tips - Hiver | Tier 3 | Moderate |
| 9 | https://www.kimbley.com/blog/30/1/2023/what-is-the-difference-between-labels-in-gmail-and-folders-in-outlook | Gmail Labels vs Outlook Folders - Kimbley IT | Tier 3 | Moderate |
| 10 | https://learn.microsoft.com/en-us/graph/api/outlookuser-post-mastercategories?view=graph-rest-1.0 | Create Outlook category - Microsoft Graph v1.0 | Tier 1 | Yes |
| 11 | https://learn.microsoft.com/en-us/graph/api/mailfolder-list-childfolders?view=graph-rest-1.0 | List childFolders - Microsoft Graph v1.0 | Tier 1 | Minor |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0 | mailFolder resource type | Folder hierarchy, well-known folder names, parent/child relationships, properties |
| 2 | https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0 | message resource type | Message properties: isRead, categories, flag, parentFolderId, importance, inferenceClassification |
| 3 | https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0 | outlookCategory resource type | Category properties, 25 color presets, master category list management |
| 4 | https://learn.microsoft.com/en-us/graph/outlook-mail-concept-overview | Outlook mail API overview | Overview of categories, flagging, organization capabilities |
| 5 | https://learn.microsoft.com/en-us/graph/api/resources/followupflag?view=graph-rest-1.0 | followupFlag resource type | Flag status enum (notFlagged/flagged/complete), date properties |
| 6 | https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0 | Update message | Writable message properties: isRead, categories, flag, importance, inferenceClassification |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0 | message: move | Move API details, archive via move to well-known folder, message ID changes |
| 8 | https://hiverhq.com/blog/labels-vs-folders-guide | Labels vs Folders guide | Conceptual comparison of label-based vs folder-based organization |
| 9 | https://www.kimbley.com/blog/30/1/2023/what-is-the-difference-between-labels-in-gmail-and-folders-in-outlook | Gmail Labels vs Outlook Folders | Single-folder constraint vs multi-label flexibility |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All key claims are sourced from official Microsoft Graph v1.0 documentation (Tier 1). The mapping between Gmail label operations and Outlook folder/category/property operations is well-documented and unambiguous. The core architectural difference (additive labels vs positional folders) is confirmed by multiple sources.

### Further Research Needed

- Microsoft Graph JSON batching (`$batch`) capacity and limitations for bulk message operations (equivalent to Gmail's batchModify for up to 1000 messages).
- Whether Outlook message rules (messageRule resource) could serve as an equivalent to Gmail filters for automated organization.
- Behavior of message IDs when using `Prefer: IdType="ImmutableId"` header during move operations, which is important for maintaining stable references across folder moves.
