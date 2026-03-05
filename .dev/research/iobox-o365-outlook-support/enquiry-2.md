# Line of Enquiry 2: Microsoft Graph API send/forward/draft vs Gmail API

## JSON Findings

```json
{
  "sub_question": "How does Microsoft Graph API handle sending, forwarding, and drafting emails compared to Gmail API?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "claim": "Microsoft Graph sendMail (POST /me/sendMail) creates and sends an email in a single call using a structured JSON message object with subject, body, toRecipients, ccRecipients, and attachments fields. It also supports MIME format via base64-encoded content with Content-Type: text/plain. Returns 202 Accepted.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Send the message specified in the request body using either JSON or MIME format. When using JSON format, you can include a file attachment in the same sendMail action call. This method saves the message in the Sent Items folder."
    },
    {
      "claim": "Gmail API send requires constructing an RFC 2822 MIME message (via Python email.mime), base64url-encoding the entire message, and POSTing it as {'raw': base64_encoded_string} to users.messages.send(). Graph API instead uses a structured JSON object with explicit fields for subject, body, recipients, and attachments.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "When using JSON format, you can include a file attachment in the same sendMail action call."
    },
    {
      "claim": "Microsoft Graph creates drafts via POST /me/messages, which saves to the Drafts folder and returns a 201 Created response with the full message object including its id. The draft can then be updated (PATCH /me/messages/{id}) and sent (POST /me/messages/{id}/send).",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Create a draft of a new message in either JSON or MIME format. By default, this operation saves the draft in the Drafts folder. Send the draft message in a subsequent operation."
    },
    {
      "claim": "Sending a draft in Microsoft Graph is done via POST /me/messages/{id}/send with no request body (Content-Length: 0). This differs from Gmail which uses drafts.send() with the draft ID. In Graph, drafts are just messages (isDraft=true) rather than a separate resource type.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Send an existing draft message. The draft message can be a new message draft, reply draft, reply-all draft, or a forward draft. This method saves the message in the Sent Items folder."
    },
    {
      "claim": "Microsoft Graph provides native forward and reply operations: POST /me/messages/{id}/forward and POST /me/messages/{id}/reply send immediately with comment and toRecipients parameters. The API automatically includes conversation history. Alternatively, createForward and createReply create draft versions for later editing.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Forward a message using either JSON or MIME format. When using JSON format, you can: Specify either a comment or the body property of the message parameter. Specify either the toRecipients parameter or the toRecipients property of the message parameter."
    },
    {
      "claim": "Microsoft Graph has no separate 'drafts' resource -- drafts are regular message objects with isDraft=true stored in the Drafts folder. Deleting a draft uses the same DELETE /me/messages/{id} endpoint as deleting any message. Gmail has a dedicated drafts resource with its own CRUD endpoints.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Delete a message in the specified user's mailbox, or delete a relationship of the message."
    },
    {
      "claim": "Microsoft Graph supports inline file attachments in the sendMail JSON body using @odata.type '#microsoft.graph.fileAttachment' with name, contentType, and contentBytes (base64-encoded). For attachments over 3MB, a separate upload session (POST /me/messages/{id}/attachments/createUploadSession) is required.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Create an upload session that allows an app to iteratively upload ranges of a file, so as to attach the file to the specified Outlook item."
    },
    {
      "claim": "Microsoft Graph provides createForward (POST /me/messages/{id}/createForward) which creates a forward draft that can be edited before sending, and createReply/createReplyAll which do the same for replies. These return 201 Created with the draft message object.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/message-createforward?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Create a draft to forward an existing message, in either JSON or MIME format. When using JSON format, you can: Specify either a comment or the body property of the message parameter. Update the draft later to add content to the body or change other message properties."
    },
    {
      "claim": "The Microsoft Graph mail API overview shows that message operations include draft, read, reply, forward, send, update, and delete -- all accessible through the message resource type. This is a unified resource model unlike Gmail which separates messages and drafts.",
      "source_url": "https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview?view=graph-rest-1.0",
      "source_tier": 1,
      "quote": "Draft, read, reply, forward, send, update, or delete messages"
    }
  ],
  "gaps": [
    "Detailed performance comparison (latency, rate limits) between Gmail API and Graph API for bulk email operations was not explored.",
    "Microsoft Graph batch request support ($batch endpoint) for sending multiple emails was not explored in depth."
  ]
}
```

## Findings (prose)

### Sending Emails: Structured JSON vs Raw MIME

The most significant architectural difference between Gmail API and Microsoft Graph API for sending emails lies in message construction. Gmail API requires building a full RFC 2822 MIME message using Python's `email.mime` library (MIMEText, MIMEMultipart, etc.), base64url-encoding the entire message, and sending it as `{'raw': base64_encoded_string}` via `service.users().messages().send()`. Microsoft Graph API, by contrast, uses a structured JSON object with explicit fields for `subject`, `body` (with `contentType` and `content`), `toRecipients`, `ccRecipients`, and `attachments`. The endpoint is `POST /me/sendMail` and returns `202 Accepted` ([Microsoft Graph sendMail docs](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0)). Graph also supports sending MIME content (base64-encoded, Content-Type: text/plain), which could provide a shared code path with Gmail's approach. For iobox, this means `compose_message()` would need to produce either a JSON dict (for Graph) or a MIME message (for Gmail), suggesting an abstraction layer that produces a provider-neutral message representation.

### Forwarding: Native API Support vs Manual Construction

Gmail API has no native forward endpoint. In iobox, `forward_email()` manually retrieves the original email, constructs a "---------- Forwarded message ----------" body via `compose_forward_message()`, and sends it as a new message through `send_message()`. Microsoft Graph provides first-class forwarding via `POST /me/messages/{id}/forward`, which accepts a `comment` and `toRecipients` in the JSON body and automatically includes the original message content and conversation history ([Microsoft Graph forward docs](https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0)). Additionally, Graph offers `POST /me/messages/{id}/createForward` to create a forward draft for later editing and sending ([Microsoft Graph createForward docs](https://learn.microsoft.com/en-us/graph/api/message-createforward?view=graph-rest-1.0)). This simplifies the forwarding implementation significantly for Outlook -- the provider layer would just call the forward endpoint with comment and recipients, rather than reconstructing the forwarded message body.

### Reply Operations: Graph's Built-in Support

Similarly, Microsoft Graph provides `POST /me/messages/{id}/reply`, `POST /me/messages/{id}/replyAll`, and their draft-creating counterparts `createReply` and `createReplyAll` ([Microsoft Graph reply docs](https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0)). Gmail API lacks dedicated reply endpoints; replies are constructed by setting the `threadId` and `In-Reply-To`/`References` headers manually. While iobox does not currently implement reply functionality as a CLI command, any future reply support would benefit from Graph's native reply operations.

### Draft Operations: Unified Messages vs Separate Drafts Resource

A key difference is how drafts are modeled. Gmail API treats drafts as a separate resource (`users.drafts`) with its own CRUD endpoints: `create`, `list`, `get`, `update`, `send`, and `delete`. Each draft wraps a message and has its own draft ID distinct from the message ID. Microsoft Graph treats drafts as regular message objects with `isDraft: true`, stored in the Drafts mail folder. Creating a draft is simply `POST /me/messages` which returns a `201 Created` response with the full message object ([Microsoft Graph create message docs](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0)). Sending a draft uses `POST /me/messages/{id}/send` with an empty body ([Microsoft Graph send draft docs](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0)). Listing drafts is done by querying the Drafts folder: `GET /me/mailFolders('Drafts')/messages`. Deleting a draft uses the standard `DELETE /me/messages/{id}` ([Microsoft Graph delete message docs](https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0)). For iobox, the mapping would be: `create_draft()` maps to `POST /me/messages`; `list_drafts()` maps to `GET /me/mailFolders('Drafts')/messages`; `send_draft()` maps to `POST /me/messages/{id}/send`; `delete_draft()` maps to `DELETE /me/messages/{id}`.

### Attachments: Inline JSON vs MIME Parts

Gmail API handles attachments by building MIMEMultipart('mixed') messages with MIMEBase parts for each attachment, encoding everything into the raw MIME payload. Microsoft Graph allows attachments to be included inline in the sendMail JSON body as `fileAttachment` objects with `@odata.type`, `name`, `contentType`, and `contentBytes` (base64-encoded) fields. For attachments under 3MB, they can be added directly. For larger attachments (3MB-150MB), Graph requires a separate upload session via `POST /me/messages/{id}/attachments/createUploadSession` ([Microsoft Graph upload session docs](https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession?view=graph-rest-1.0)). Attachments can also be added to existing draft messages via `POST /me/messages/{id}/attachments`. This two-tier approach (inline for small, upload session for large) differs from Gmail where all attachments are part of the MIME message, though Gmail similarly has a 5MB limit for simple upload and requires multipart or resumable upload for larger files.

### Permissions Model

Both APIs use OAuth 2.0 but with different permission scopes. Graph API requires `Mail.Send` for sending operations and `Mail.ReadWrite` for draft creation/management. These correspond to Gmail's scopes like `gmail.send` and `gmail.compose`. Graph supports both delegated (user-interactive) and application (daemon/service) permission types, with application permissions requiring `POST /users/{id}/sendMail` instead of `POST /me/sendMail`. This is analogous to Gmail's service account delegation.

### Implications for iobox Abstraction

The comparison reveals that while the operations are functionally equivalent, the implementation details differ substantially. Graph's structured JSON approach for message composition is arguably simpler than Gmail's raw MIME construction. Graph's native forward/reply endpoints eliminate the manual message reconstruction that iobox currently performs for Gmail. However, Graph's lack of a dedicated drafts resource means the abstraction layer needs to map draft operations to message operations filtered by folder. A provider interface for iobox would need methods like `send_message(message)`, `forward_message(message_id, recipients, comment)`, `create_draft(message)`, `send_draft(draft_id)`, `list_drafts(max_results)`, and `delete_draft(draft_id)`, with each provider implementing these against its respective API.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0 | user: sendMail - Microsoft Graph v1.0 | 1 | Yes |
| 2 | https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0 | Create message - Microsoft Graph v1.0 | 1 | Yes |
| 3 | https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0 | message: forward - Microsoft Graph v1.0 | 1 | Yes |
| 4 | https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0 | message: send - Microsoft Graph v1.0 | 1 | Yes |
| 5 | https://learn.microsoft.com/en-us/graph/api/message-createforward?view=graph-rest-1.0 | message: createForward - Microsoft Graph v1.0 | 1 | Yes |
| 6 | https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0 | message: reply - Microsoft Graph v1.0 | 1 | Yes |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-createreply?view=graph-rest-1.0 | message: createReply - Microsoft Graph v1.0 | 1 | Yes |
| 8 | https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0 | Delete message - Microsoft Graph v1.0 | 1 | Yes |
| 9 | https://learn.microsoft.com/en-us/graph/api/message-post-attachments?view=graph-rest-1.0 | Add attachment - Microsoft Graph v1.0 | 1 | Yes |
| 10 | https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession?view=graph-rest-1.0 | attachment: createUploadSession - Microsoft Graph v1.0 | 1 | Yes |
| 11 | https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview?view=graph-rest-1.0 | Use the Outlook mail REST API - Microsoft Graph v1.0 | 1 | Yes |
| 12 | https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail | Overview of the Microsoft Graph send mail process | 1 | Partially |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0 | user: sendMail | Documented the sendMail endpoint, JSON and MIME format support, attachment inclusion, saveToSentItems parameter |
| 2 | https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0 | Create message (draft) | Documented draft creation via POST /me/messages, JSON and MIME format, 201 response with message object |
| 3 | https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0 | message: forward | Documented native forward endpoint with comment and toRecipients, automatic conversation history inclusion |
| 4 | https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0 | message: send | Documented sending existing drafts via POST /me/messages/{id}/send with empty body |
| 5 | https://learn.microsoft.com/en-us/graph/api/message-createforward?view=graph-rest-1.0 | message: createForward | Documented creating forward drafts for later editing |
| 6 | https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0 | message: reply | Documented native reply endpoint |
| 7 | https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0 | Delete message | Confirmed draft deletion uses standard message delete endpoint |
| 8 | https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession?view=graph-rest-1.0 | createUploadSession | Documented large attachment upload (>3MB) via upload sessions |
| 9 | https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview?view=graph-rest-1.0 | Outlook mail REST API overview | Provided comprehensive overview of all mail operations |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: All key Microsoft Graph mail composition endpoints (sendMail, forward, reply, createForward, createReply, message send, draft CRUD, attachments) were documented from official Microsoft Learn Tier 1 sources. The comparison to Gmail API operations is well-grounded in the existing iobox codebase context.

### Further Research Needed

- Microsoft Graph batch requests (`$batch` endpoint) for sending multiple emails efficiently in bulk operations.
- Rate limiting and throttling differences between Gmail API and Microsoft Graph API for high-volume email operations.
- Microsoft Graph's support for S/MIME signed/encrypted email composition.
