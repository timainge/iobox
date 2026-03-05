# Research Plan: How could iobox support O365 Outlook accounts as well as Gmail?

**Date**: 2026-03-05
**Mode**: deep
**Agents**: 6
**Model**: default (inherited)

## Lines of Enquiry

1. Microsoft Graph API for reading/searching emails — how does search, list, and read work compared to Gmail API's `messages.list`, `messages.get`, and query syntax?
2. Microsoft Graph API for sending, forwarding, and drafting emails — how do `sendMail`, `createForward`, `createReply`, and draft CRUD compare to Gmail's compose/send/draft APIs?
3. Microsoft Graph API authentication with MSAL (OAuth 2.0) — how does the auth flow, token management, and scope model compare to Gmail's OAuth via `google-auth-oauthlib`?
4. Microsoft Graph API for mail folders and categories vs Gmail labels — how do Outlook folders, categories, and flag/read status map to Gmail's label system?
5. Microsoft Graph API for attachments, trash/delete, batch requests, and delta sync — how do these operations compare to Gmail's attachment download, trash/untrash, batch HTTP, and history API?
6. Architecture patterns for multi-provider email abstractions in Python — what libraries, patterns, or projects exist for supporting both Gmail and Outlook in a single codebase?

## Project Context Detected

- **iobox** is a Gmail-to-Markdown CLI tool using Typer, google-api-python-client, google-auth-oauthlib
- Core modules: auth.py (OAuth 2.0), email_search.py (search/list), email_retrieval.py (read/attachments/labels/trash), email_sender.py (send/forward/drafts), cli.py (Typer commands)
- Key Gmail API features used: messages.list with query syntax, messages.get (full/metadata), batch HTTP requests (50 per batch), labels API, history API for incremental sync, drafts CRUD, messages.send, messages.trash/untrash, messages.modify (label changes), attachments.get
- Auth uses OAuth 2.0 with scopes: gmail.modify, gmail.compose
- Output: Markdown files with YAML frontmatter
