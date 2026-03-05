# Line of Enquiry 5: Graph API attachments, trash, batch, and delta sync vs Gmail

## JSON Findings

```json
{
  "sub_question": "How does Microsoft Graph handle attachments, trash, batch requests, and delta sync compared to Gmail API?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "topic": "Attachments",
      "detail": "Graph API supports three attachment types: fileAttachment (with base64 contentBytes), itemAttachment (embedded Outlook items), and referenceAttachment (cloud file links). Attachments under 3 MB use a single POST; 3-150 MB require an upload session with chunked PUT requests. Download uses GET /me/messages/{id}/attachments/{id} for metadata+base64 or /$value suffix for raw bytes. Gmail uses a simpler model: base64url-encoded data from attachments().get(), decoded with base64.urlsafe_b64decode(). Gmail has a 25 MB send limit; Graph supports up to 150 MB via upload sessions.",
      "sources": ["https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0", "https://learn.microsoft.com/en-us/graph/outlook-large-attachments"]
    },
    {
      "topic": "Trash and Delete",
      "detail": "Graph API has no direct trash/untrash endpoints like Gmail. Instead: DELETE /me/messages/{id} moves to Deleted Items (soft delete), POST /me/messages/{id}/move with destinationId 'deleteditems' also moves to trash, and POST /me/messages/{id}/permanentDelete bypasses trash entirely. To restore (untrash), use POST /me/messages/{id}/move with the destination folder (e.g., 'inbox'). Gmail provides dedicated .trash() and .untrash() methods. The iobox abstraction layer must map trash to DELETE or move-to-deleteditems, and untrash to move-from-deleteditems.",
      "sources": ["https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0", "https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0", "https://learn.microsoft.com/en-us/graph/api/message-permanentdelete?view=graph-rest-1.0"]
    },
    {
      "topic": "Batch Requests",
      "detail": "Graph uses JSON batching via POST to /$batch endpoint, accepting up to 20 requests per batch (vs Gmail's 50). Each request in the batch has an id, method, url, optional headers and body. Responses come back with per-request status codes. The dependsOn property enables sequential ordering. Gmail uses service.new_batch_http_request() with a callback pattern. Key differences: Graph limit is 20 vs Gmail's 50; Graph uses a pure JSON POST body vs Gmail's multipart HTTP; Graph supports explicit request dependencies.",
      "sources": ["https://learn.microsoft.com/en-us/graph/json-batching"]
    },
    {
      "topic": "Delta (Incremental) Sync",
      "detail": "Graph uses delta queries: GET /me/mailFolders/{id}/messages/delta returns messages with @odata.nextLink (for pagination) or @odata.deltaLink (sync complete, save for next round). Supports changeType filter (created/updated/deleted). Delta is per-folder, requiring separate tracking for each folder. Gmail uses history().list() with a startHistoryId, which works across all labels globally. Key differences: Graph is per-folder vs Gmail's global history; Graph uses opaque deltaLink tokens vs Gmail's numeric historyId; Graph supports filtering by change type natively; Graph delta tokens have no fixed expiry but are cache-size dependent, while Gmail historyId is permanent as long as it exists in the history.",
      "sources": ["https://learn.microsoft.com/en-us/graph/delta-query-messages", "https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0"]
    },
    {
      "topic": "Pagination",
      "detail": "Graph uses @odata.nextLink URLs containing $skipToken or $skip parameters. The client should follow the full URL without extracting tokens. Default page size is 10 messages, controllable via $top or Prefer: odata.maxpagesize header. Gmail uses nextPageToken passed as a parameter to subsequent requests. Both patterns are conceptually similar cursor-based pagination.",
      "sources": ["https://learn.microsoft.com/en-us/graph/paging"]
    }
  ],
  "gaps": [
    "Exact throttling rates for Graph mail API endpoints (per-user, per-app) were not deeply explored",
    "Python SDK specifics for Graph (msgraph-sdk-python) were not examined in detail for attachment handling convenience methods"
  ]
}
```

## Findings (prose)

**Attachments.** The Microsoft Graph API handles email attachments through a richer type system than Gmail. Graph supports three attachment types: `fileAttachment` (standard files with base64-encoded `contentBytes`), `itemAttachment` (embedded Outlook items like contacts, events, or messages), and `referenceAttachment` (links to cloud-stored files). For downloading, `GET /me/messages/{id}/attachments/{id}` returns metadata plus base64 content, while appending `/$value` returns raw binary bytes directly [1]. Gmail's model is simpler: `attachments().get()` returns base64url-encoded data that the client decodes. A significant difference is large file handling: Graph requires an upload session (`POST .../attachments/createUploadSession`) for files between 3 MB and 150 MB, uploading in chunks via PUT requests, while files under 3 MB use a single POST [2]. Gmail has a flat 25 MB attachment limit for sending with no chunked upload mechanism. For iobox's read-focused use case (downloading attachments), the Graph `/$value` endpoint returning raw bytes is actually simpler than Gmail's base64url approach, as it avoids the decode step.

**Trash and Delete Operations.** Unlike Gmail's dedicated `trash()` and `untrash()` methods, Graph API takes a more compositional approach. Calling `DELETE /me/messages/{id}` performs a soft delete, moving the message to the Deleted Items folder [3]. Alternatively, `POST /me/messages/{id}/move` with `destinationId: "deleteditems"` achieves the same effect [4]. For permanent deletion bypassing the trash, Graph offers `POST /me/messages/{id}/permanentDelete` [5]. To restore a message from trash (the equivalent of Gmail's `untrash`), you use the move endpoint again: `POST /me/messages/{id}/move` with the destination set to the target folder (e.g., `"inbox"`). This means iobox's trash abstraction would map Gmail's `trash()` to Graph's `DELETE` and Gmail's `untrash()` to Graph's `move` with a destination folder ID. The key semantic difference is that Graph's DELETE is a soft delete (recoverable), while Gmail's `delete()` (not `trash()`) is permanent -- Graph's equivalent is `permanentDelete`.

**Batch Requests.** Graph implements JSON batching through a `POST /$batch` endpoint that accepts up to 20 individual requests in a single JSON payload, compared to Gmail's limit of 50 requests per batch [6]. Each request in the batch specifies an `id`, `method`, `url`, and optional `headers` and `body`. Responses return per-request status codes, meaning a batch can return HTTP 200 overall while individual requests within it fail. Graph also supports a `dependsOn` property for sequencing requests within a batch, which Gmail lacks. Gmail uses `service.new_batch_http_request(callback=callback)` with a callback pattern that receives `(request_id, response, exception)` per request. For iobox, the batch abstraction would need to handle different chunk sizes (20 for Graph vs 50 for Gmail) and different request/response formats. The lower Graph limit means more batch calls for the same number of messages, though individual requests within Graph batches can be any mix of HTTP methods (GET, POST, DELETE, PATCH).

**Delta (Incremental) Sync.** Graph's delta query mechanism differs fundamentally from Gmail's history-based approach. Graph uses `GET /me/mailFolders/{id}/messages/delta` which returns messages along with either an `@odata.nextLink` (more pages to fetch) or `@odata.deltaLink` (sync complete -- save this URL for next round) [7]. A critical architectural difference is that Graph delta queries are per-folder: to track changes across the entire mailbox, each folder must be tracked individually. Gmail's `history().list()` with a `startHistoryId` operates globally across all labels. Graph supports native filtering by change type (`?changeType=created`, `updated`, or `deleted`), while Gmail filters via `historyTypes` parameter. Graph delta tokens are opaque URLs with no fixed expiration (they expire when the server's internal cache fills), whereas Gmail uses a numeric `historyId` that is simpler but offers less built-in filtering. Graph supports `$select`, `$top`, and limited `$filter` in delta queries, and deleted items appear with an `@removed` annotation containing the reason [7].

**Pagination.** Both APIs use cursor-based pagination but with different token mechanisms. Graph returns `@odata.nextLink` URLs containing `$skipToken` or `$skip` parameters, with a default page size of 10 messages (adjustable via `$top` or the `Prefer: odata.maxpagesize` header) [8]. Gmail uses `nextPageToken` values passed as query parameters. Both require the client to follow opaque tokens without extracting or manipulating them. The pagination abstraction in iobox would be straightforward to unify, as both follow the same logical pattern of "fetch page, check for continuation token, repeat."

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0 | Get attachment - Microsoft Graph v1.0 | Tier 1 | Yes |
| 2 | https://learn.microsoft.com/en-us/graph/outlook-large-attachments | Attach large files to Outlook messages or events | Tier 1 | Yes |
| 3 | https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0 | Delete message - Microsoft Graph v1.0 | Tier 1 | Yes |
| 4 | https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0 | message: move - Microsoft Graph v1.0 | Tier 1 | Yes |
| 5 | https://learn.microsoft.com/en-us/graph/api/message-permanentdelete?view=graph-rest-1.0 | message: permanentDelete - Microsoft Graph v1.0 | Tier 1 | Yes |
| 6 | https://learn.microsoft.com/en-us/graph/json-batching | Combine multiple HTTP requests using JSON batching | Tier 1 | Yes |
| 7 | https://learn.microsoft.com/en-us/graph/delta-query-messages | Get incremental changes to messages in a folder | Tier 1 | Yes |
| 8 | https://learn.microsoft.com/en-us/graph/paging | Paging Microsoft Graph data in your app | Tier 1 | Yes |
| 9 | https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0 | message: delta - Microsoft Graph v1.0 | Tier 1 | Yes |
| 10 | https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0 | List attachments - Microsoft Graph v1.0 | Tier 1 | Yes |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0 | Get attachment | Attachment types (file/item/reference), /$value for raw content, contentBytes base64 format |
| 2 | https://learn.microsoft.com/en-us/graph/outlook-large-attachments | Large attachments | 3 MB threshold, upload session mechanism, 150 MB max, chunked PUT workflow |
| 3 | https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0 | Delete message | DELETE endpoint moves to Deleted Items (soft delete), 204 No Content response |
| 4 | https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0 | message: move | Move to deleteditems for trash, move from deleteditems for untrash |
| 5 | https://learn.microsoft.com/en-us/graph/api/message-permanentdelete?view=graph-rest-1.0 | permanentDelete | Bypass trash, permanent removal equivalent |
| 6 | https://learn.microsoft.com/en-us/graph/json-batching | JSON batching | 20 request limit, POST /$batch, dependsOn for sequencing, per-request status codes |
| 7 | https://learn.microsoft.com/en-us/graph/delta-query-messages | Delta query messages | Per-folder delta, deltaLink/nextLink tokens, changeType filter, @removed annotation |
| 8 | https://learn.microsoft.com/en-us/graph/paging | Paging | @odata.nextLink pattern, $skipToken/$skip, default page size 10 |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All four feature areas (attachments, trash/delete, batch, delta sync) were thoroughly documented using official Microsoft Graph v1.0 documentation. The comparison points with Gmail API are clear and actionable for designing an iobox abstraction layer.

### Further Research Needed

- Exact per-user and per-app throttling rates for Graph mail endpoints to inform batch chunking strategy.
- Python SDK (`msgraph-sdk-python`) convenience methods for attachment download and delta queries, to determine whether to use the SDK or raw REST calls in iobox.
- Whether Graph's delta query can be made to work across all folders simultaneously (current docs say per-folder only), and the performance implications of tracking many folders.
