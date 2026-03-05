# Line of Enquiry 1: Microsoft Graph API email search/list/read vs Gmail API

## JSON Findings

```json
{
  "sub_question": "How does the Microsoft Graph API handle email search, list, and read operations compared to Gmail API?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Microsoft Graph lists messages via GET /me/messages with OData query parameters ($filter, $select, $top, $orderby, $search), with a default page size of 10 and max of 1000 per page.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Use $top to customize the page size, within the range of 1 and 1000. The default page size is 10 messages."
    },
    {
      "claim": "Microsoft Graph retrieves individual messages via GET /me/messages/{id}, returning full message properties including body, recipients, and metadata in a single call, unlike Gmail which requires format='full' or 'metadata' parameters.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Retrieve the properties and relationships of a message object. You can use the $value parameter to get the MIME content of a message."
    },
    {
      "claim": "Graph API $search uses KQL syntax with properties like from:, to:, cc:, bcc:, subject:, body:, received:, sent:, hasAttachments:, attachment:, participants:, recipients:, importance:, and size:. A $search request returns up to 1,000 results.",
      "source_url": "https://learn.microsoft.com/en-us/graph/search-query-parameter",
      "source_tier": 1,
      "quote": "You can search messages by specifying message property names that Keyword Query Language (KQL) syntax recognizes. A $search request returns up to 1,000 results."
    },
    {
      "claim": "$search and $filter cannot be combined on message collections, unlike Gmail where a single query string handles both filtering and search. $filter supports OData expressions on properties like receivedDateTime, isRead, and subject.",
      "source_url": "https://learn.microsoft.com/en-us/graph/search-query-parameter",
      "source_tier": 1,
      "quote": "$search and $filter parameters cannot be used together while querying message collections."
    },
    {
      "claim": "Graph API pagination uses @odata.nextLink URLs (containing opaque skipToken values), analogous to Gmail's nextPageToken but using full URLs rather than separate token parameters.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "To get the next page of messages, simply apply the entire URL returned in @odata.nextLink to the next get-messages request."
    },
    {
      "claim": "Graph API supports JSON batching via POST to /$batch with up to 20 individual requests per batch, compared to Gmail's batch HTTP which supports up to 50 requests. Both return individual status codes per request.",
      "source_url": "https://learn.microsoft.com/en-us/graph/json-batching",
      "source_tier": 1,
      "quote": "JSON batch requests are currently limited to 20 individual requests."
    },
    {
      "claim": "Graph API provides delta query (GET /me/mailFolders/{id}/messages/delta) for incremental sync, analogous to Gmail's history.list. Delta query uses deltaToken/skipToken state tokens and can filter by changeType (created, updated, deleted).",
      "source_url": "https://learn.microsoft.com/en-us/graph/delta-query-messages",
      "source_tier": 1,
      "quote": "Delta query lets you query for additions, deletions, or updates to messages in a folder by way of a series of delta function calls."
    },
    {
      "claim": "Graph messages have a conversationId property for threading, analogous to Gmail's threadId. However, Graph threading is per-folder and subject-based, whereas Gmail threading is global across the mailbox.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "conversationId: The ID of the conversation the email belongs to."
    },
    {
      "claim": "Graph returns message bodies in HTML by default but supports text format via the Prefer: outlook.body-content-type='text' header. Gmail returns bodies as base64-encoded parts requiring manual extraction from the payload structure.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "The format of the body and uniqueBody properties to be returned in. Values can be 'text' or 'html'."
    },
    {
      "claim": "Graph messages use categories (string array) instead of Gmail's label system. Messages have a parentFolderId property referencing their mail folder, while Gmail uses label IDs that can represent both folders and tags.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "categories: [\"string\"]"
    },
    {
      "claim": "Graph provides attachments via a separate endpoint GET /me/messages/{id}/attachments or inline via $expand=attachments. Gmail similarly requires parsing attachment metadata from the message payload and fetching content via a separate attachments.get call.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Gets all attachments on a message."
    },
    {
      "claim": "Graph delta query is per-folder (must track each folder individually), while Gmail's history.list is global across the entire mailbox. Delta query supports $select, $top, $expand but only limited $filter (receivedDateTime) and no $search.",
      "source_url": "https://learn.microsoft.com/en-us/graph/delta-query-messages",
      "source_tier": 1,
      "quote": "Delta query is a per-folder operation. To track the changes of the messages in a folder hierarchy, you need to track each folder individually."
    },
    {
      "claim": "When using $filter and $orderby together on messages, properties in $orderby must also appear in $filter and in the same order, an OData constraint with no Gmail equivalent.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Properties that appear in $orderby must also appear in $filter. Properties that appear in $orderby are in the same order as in $filter."
    }
  ],
  "gaps": [
    "Exact throttling/rate limits for Graph mail API vs Gmail API quotas",
    "Performance benchmarks comparing Graph batch requests (20 max) vs Gmail batch (50 max) for metadata retrieval at scale"
  ]
}
```

## Findings (prose)

Microsoft Graph API provides a RESTful interface for accessing Outlook/O365 email that is broadly comparable to the Gmail API but differs in several important structural ways. The core message listing endpoint is `GET /me/messages`, which returns messages with full metadata and body content by default, unlike Gmail's `messages.list` which returns only message IDs requiring follow-up `messages.get` calls [1]. Graph supports OData query parameters including `$select` (to limit returned properties), `$top` (page size, 1-1000, default 10), `$filter` (OData filter expressions), `$orderby`, and `$search` (KQL-based full-text search) [1]. This is a fundamentally different query model from Gmail's single `q` parameter that accepts Gmail-specific search syntax.

The `$search` parameter uses Keyword Query Language (KQL) syntax and supports properties such as `from:`, `to:`, `cc:`, `bcc:`, `subject:`, `body:`, `received:`, `sent:`, `hasAttachments:`, `attachment:`, `participants:`, `recipients:`, `importance:`, `kind:`, and `size:` [3]. While these cover similar ground to Gmail's query operators (`from:`, `to:`, `subject:`, `has:attachment`, `after:`, `before:`, `is:read`, etc.), the syntax is different. Critically, `$search` and `$filter` cannot be combined on message collections [3], meaning you cannot do a full-text search and simultaneously filter by date using OData `$filter`. For date-based searches, you must either use the KQL `received:` or `sent:` properties within `$search`, or use `$filter=receivedDateTime ge {value}` without `$search`. Gmail's unified query syntax handles both seamlessly (e.g., `from:x@y.com after:2024/01/01`).

Individual message retrieval via `GET /me/messages/{id}` returns a rich JSON object with all message properties including body content, recipients, headers, and metadata in a single response [2]. This contrasts with Gmail where `messages.get` requires specifying `format='full'` to get the complete message, and the body content comes as base64-encoded MIME parts that require parsing. Graph can return the body in either HTML or plain text format via the `Prefer: outlook.body-content-type` header [2], which is more convenient for a tool like iobox that needs to convert to Markdown. Graph also supports MIME content retrieval via `GET /me/messages/{id}/$value` [2], which could be useful as a fallback.

For batch operations, Graph supports JSON batching at the `/$batch` endpoint with up to 20 requests per batch [4], compared to Gmail's batch HTTP which supports up to 50 requests per batch. Both systems return individual status codes per request and allow parallel execution. Graph also supports request dependencies via a `dependsOn` property for sequential execution [4]. The lower batch limit (20 vs 50) means that iobox would need more batch requests to fetch the same number of message metadata items, but since Graph's list endpoint already returns full message data (unlike Gmail's list which returns only IDs), batching may be needed less frequently.

Incremental synchronization is handled by Graph's delta query mechanism (`GET /me/mailFolders/{id}/messages/delta`) [5], which is analogous to Gmail's `history.list` API. A key difference is that Graph delta queries are per-folder, requiring separate tracking for each mail folder, while Gmail's history API is global across the entire mailbox [5]. Graph uses opaque state tokens (deltaToken and skipToken) instead of Gmail's historyId. Graph delta supports filtering by change type (`created`, `updated`, `deleted`) via a custom `changeType` query parameter [5], which is more granular than Gmail's `historyTypes` parameter.

Message threading in Graph uses a `conversationId` property on the message resource [6], similar to Gmail's `threadId`. However, Graph's conversation model is tied to subject lines and folder structure, while Gmail's threading is global and based on message references/in-reply-to headers. Graph does not provide a direct equivalent to Gmail's `threads.get` endpoint that returns all messages in a thread in one call; instead, you would filter messages by `conversationId`. Graph messages also use `categories` (an array of strings) rather than Gmail's label system [6]. Labels in Gmail serve dual purposes as both folders and tags, while Outlook strictly separates folders (`parentFolderId`) from categories.

Attachments in Graph are accessed via `GET /me/messages/{id}/attachments` or can be included inline via `$expand=attachments` [7]. This is somewhat simpler than Gmail's approach where attachment metadata is embedded in the message payload parts and the actual content must be fetched via a separate `attachments.get` call with the attachment ID. Graph's approach of optionally expanding attachments in the message response is more convenient for batch retrieval scenarios.

Pagination in both APIs uses opaque tokens, but Graph returns full `@odata.nextLink` URLs that should be followed as-is [1], while Gmail returns a `nextPageToken` string that must be passed as a parameter to the next request. The Graph approach is slightly simpler for implementation as no URL construction is needed for subsequent pages.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0 | List messages - Microsoft Graph v1.0 | 1 | yes |
| 2 | https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0 | Get message - Microsoft Graph v1.0 | 1 | yes |
| 3 | https://learn.microsoft.com/en-us/graph/search-query-parameter | Use $search Query Parameter in Microsoft Graph APIs | 1 | yes |
| 4 | https://learn.microsoft.com/en-us/graph/json-batching | Combine multiple HTTP requests using JSON batching | 1 | yes |
| 5 | https://learn.microsoft.com/en-us/graph/delta-query-messages | Get incremental changes to messages in a folder | 1 | yes |
| 6 | https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0 | message resource type - Microsoft Graph v1.0 | 1 | yes |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0 | List attachments - Microsoft Graph v1.0 | 1 | yes |
| 8 | https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview?view=graph-rest-1.0 | Use the Outlook mail REST API | 1 | yes |
| 9 | https://learn.microsoft.com/en-us/graph/search-concept-messages | Use the Microsoft Search API to search Outlook messages | 1 | no |
| 10 | https://learn.microsoft.com/en-us/graph/filter-query-parameter | Use the $filter query parameter | 1 | no |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0 | List messages | Endpoint structure, pagination, $top/$select/$filter/$orderby behavior |
| 2 | https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0 | Get message | Single message retrieval, MIME content, body format control |
| 3 | https://learn.microsoft.com/en-us/graph/search-query-parameter | $search Query Parameter | KQL syntax, searchable properties, $search/$filter mutual exclusion |
| 4 | https://learn.microsoft.com/en-us/graph/json-batching | JSON batching | Batch endpoint, 20-request limit, dependsOn sequencing |
| 5 | https://learn.microsoft.com/en-us/graph/delta-query-messages | Delta query messages | Incremental sync, per-folder tracking, changeType filtering |
| 6 | https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0 | message resource type | Full property list, conversationId, categories, parentFolderId |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0 | List attachments | Attachment retrieval endpoint and $expand option |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All findings are sourced from official Microsoft Learn documentation (Tier 1). The core operations (list, get, search, batch, incremental sync, threading, attachments) are well documented and directly comparable to the Gmail API operations used by iobox. The two identified gaps (throttling limits and performance benchmarks) are secondary concerns that do not affect architectural compatibility assessment.

### Further Research Needed

None.
