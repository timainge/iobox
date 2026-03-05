# Line of Enquiry 6: Multi-provider email architecture patterns in Python

## JSON Findings

```json
{
  "sub_question": "What architecture patterns and libraries exist for multi-provider email clients supporting Gmail and Outlook?",
  "confidence": "high",
  "satisfactorily_explored": "yes",
  "findings": [
    {
      "finding": "The Strategy/Adapter pattern with ABC or Protocol interfaces is the dominant approach for multi-provider email abstractions in Python. ABCs enforce contracts at instantiation time and allow shared implementation in base classes; Protocols (PEP 544) offer structural subtyping without requiring inheritance, which is better for loose coupling.",
      "sources": ["https://jellis18.github.io/post/2022-01-11-abc-vs-protocol/", "https://docs.python.org/3/library/abc.html", "https://peps.python.org/pep-0544/"]
    },
    {
      "finding": "MailBridge is an open-source Python library that implements a unified email sending interface across SMTP, SendGrid, Mailgun, SES, Postmark, and Brevo. It uses a facade class (MailBridge) with provider selection via string parameter, demonstrating the Strategy pattern with internal adapter classes per provider. It has 156 tests and 96% coverage.",
      "sources": ["https://github.com/codevelo-pub/mailbridge", "https://dev.to/radomir_brkovic_954abae53/a-python-library-that-lets-you-switch-email-providers-without-changing-your-code-c41"]
    },
    {
      "finding": "Marrow Mailer uses a duck-typed transport plugin API with required lifecycle methods (startup, deliver, shutdown). Transports are organized into meta, disk, and network categories. This demonstrates a clean plugin architecture pattern where new transports can be added by implementing a known interface without modifying core code.",
      "sources": ["https://github.com/marrow/mailer"]
    },
    {
      "finding": "python-o365 is the most mature Python library for Microsoft Graph/O365 email operations, providing Pythonic abstractions for message CRUD, search via OData queries, attachments, OAuth with automatic refresh token handling, and pagination. It mirrors many capabilities that iobox uses from the Gmail API.",
      "sources": ["https://github.com/O365/python-o365", "https://pypi.org/project/o365/"]
    },
    {
      "finding": "EmailEngine (open-source, Node.js-based) demonstrates the unified REST API gateway pattern: a single API normalizes IMAP, Gmail API, and Microsoft Graph API differences. While not a Python library, its architecture validates that a single interface over multiple email backends is practical and production-proven.",
      "sources": ["https://emailengine.app/", "https://github.com/postalsys/emailengine"]
    },
    {
      "finding": "Nylas is the commercial gold standard for multi-provider email APIs, supporting Gmail, Outlook, Exchange, Yahoo, and IMAP through a single unified API with Python SDK. It abstracts provider-specific protocols, authentication flows, and edge cases. While not embeddable, it validates the abstraction model.",
      "sources": ["https://www.nylas.com/products/email-api/", "https://developer.nylas.com/docs/v3/email/"]
    },
    {
      "finding": "For iobox specifically, the recommended pattern is an ABC-based provider interface (e.g., EmailProvider) defining abstract methods for search, retrieve, send, forward, draft CRUD, label/folder management, and trash. Gmail and O365 concrete classes implement this interface, with a factory function selecting the provider based on configuration. ABCs are preferable to Protocols here because iobox owns all provider implementations, runtime enforcement catches errors early, and shared logic (e.g., markdown conversion) can live in the base class.",
      "sources": ["https://jellis18.github.io/post/2022-01-11-abc-vs-protocol/", "https://docs.python.org/3/library/abc.html"]
    }
  ],
  "gaps": [
    "No widely-adopted open-source Python library exists that provides a unified read+write email interface across both Gmail API and Microsoft Graph API -- the available libraries either focus on sending only (MailBridge) or target a single provider (python-o365, google-api-python-client).",
    "Limited real-world examples of Python CLIs that have successfully abstracted across Gmail and O365 for full mailbox operations (search, read, send, labels).",
    "Query syntax translation between Gmail search syntax and Microsoft Graph OData $filter/$search is not covered by any existing library and would need custom implementation."
  ]
}
```

## Findings (prose)

The most practical architecture pattern for adding O365/Outlook support to a Python email tool like iobox is the **Strategy pattern with Abstract Base Classes**. Python's `abc` module allows defining an `EmailProvider` ABC with abstract methods for each operation (search, retrieve, send, forward, draft CRUD, label management, trash). Concrete subclasses -- `GmailProvider` and `OutlookProvider` -- implement these methods using their respective APIs. ABCs are preferable to Python's newer Protocol classes (PEP 544) in this context because iobox owns all provider implementations, runtime enforcement at instantiation catches missing methods early, and the base class can hold shared logic like markdown conversion or filename generation ([ABC vs Protocol comparison](https://jellis18.github.io/post/2022-01-11-abc-vs-protocol/), [Python abc docs](https://docs.python.org/3/library/abc.html)).

Several open-source Python libraries demonstrate this pattern in practice. **MailBridge** implements a unified email-sending interface across six providers (SMTP, SendGrid, Mailgun, SES, Postmark, Brevo) using a facade class that delegates to internal adapter classes based on a provider string parameter. Its architecture is clean but limited to sending -- it does not handle reading, searching, or managing emails ([MailBridge GitHub](https://github.com/codevelo-pub/mailbridge)). **Marrow Mailer** takes a plugin-based approach with a duck-typed transport API requiring lifecycle methods (startup, deliver, shutdown), organized into meta, disk, and network transport categories. This demonstrates how new backends can be added without modifying core code ([Marrow Mailer](https://github.com/marrow/mailer)).

For the Microsoft side specifically, **python-o365** is the most mature Python library for interacting with Microsoft Graph API. It provides Pythonic abstractions for composing and sending messages, OAuth with automatic refresh token handling, OData query building for search/filter operations, pagination via custom iterators, and automatic timezone conversion. Its API surface maps reasonably well to what iobox currently does with the Gmail API, making it the natural choice for implementing an `OutlookProvider` ([python-o365 GitHub](https://github.com/O365/python-o365), [PyPI](https://pypi.org/project/o365/)).

At the commercial/hosted level, **Nylas** represents the gold standard for multi-provider email API unification. It provides a single REST API with Python SDK that connects to Gmail, Outlook, Exchange, Yahoo, and arbitrary IMAP servers, abstracting away protocol differences, authentication flows, and provider-specific edge cases. While Nylas is a hosted service rather than an embeddable library, its existence validates that a unified interface over Gmail and Outlook is achievable and that the abstraction boundaries it draws (messages, threads, folders/labels, drafts, attachments, search) are the right ones ([Nylas Email API](https://www.nylas.com/products/email-api/)).

**EmailEngine**, an open-source Node.js project, demonstrates the self-hosted gateway approach: a single REST API that normalizes IMAP, Gmail API, and Microsoft Graph API behind consistent endpoints. It uses Redis for state management and provides webhooks for real-time notifications. While not Python, its architecture confirms that provider differences can be hidden behind a unified interface covering full mailbox operations ([EmailEngine](https://emailengine.app/), [GitHub](https://github.com/postalsys/emailengine)).

A key challenge for iobox is **query syntax translation**. Gmail uses its own search syntax (e.g., `from:user@example.com after:2024/01/01`), while Microsoft Graph uses OData `$filter` and `$search` parameters with different syntax and capabilities. No existing library handles this translation, so iobox would need either a custom query normalization layer or would need to accept provider-specific query syntax. The recommended approach is to define a structured query object (with fields like `from_`, `to`, `subject`, `date_after`, `date_before`, `has_attachment`) that each provider translates into its native query format, while also supporting a raw query passthrough for power users.

For iobox's specific architecture, the recommended implementation would involve: (1) an `EmailProvider` ABC in a new `providers/base.py` module defining the contract; (2) `providers/gmail.py` wrapping the existing Gmail-specific code; (3) `providers/outlook.py` implementing the same interface using python-o365; (4) a factory function or registry that instantiates the correct provider based on CLI flags or configuration; and (5) refactoring `cli.py` to call provider methods through the abstract interface rather than importing Gmail-specific modules directly. Shared utilities like markdown conversion, file management, and frontmatter generation remain provider-agnostic and can stay in their current modules.

## Sources

### All Sources Accessed

| # | URL | Title | Tier | Useful? |
|---|-----|-------|------|---------|
| 1 | https://github.com/codevelo-pub/mailbridge | MailBridge - Flexible mail delivery library for Python | Tier 1 | Yes |
| 2 | https://github.com/O365/python-o365 | python-o365 - Microsoft Graph and Office 365 API | Tier 1 | Yes |
| 3 | https://docs.python.org/3/library/abc.html | abc - Abstract Base Classes (Python docs) | Tier 1 | Yes |
| 4 | https://peps.python.org/pep-0544/ | PEP 544 - Protocols: Structural subtyping | Tier 1 | Yes |
| 5 | https://jellis18.github.io/post/2022-01-11-abc-vs-protocol/ | Abstract Base Classes and Protocols: What Are They? | Tier 2 | Yes |
| 6 | https://emailengine.app/ | EmailEngine Email API | Tier 1 | Yes |
| 7 | https://github.com/postalsys/emailengine | EmailEngine GitHub repo | Tier 1 | Yes |
| 8 | https://www.nylas.com/products/email-api/ | Nylas Email API | Tier 1 | Yes |
| 9 | https://developer.nylas.com/docs/v3/email/ | Nylas Messages API docs | Tier 1 | Yes |
| 10 | https://github.com/marrow/mailer | Marrow Mailer - modular mail delivery framework | Tier 1 | Yes |
| 11 | https://dev.to/radomir_brkovic_954abae53/a-python-library-that-lets-you-switch-email-providers-without-changing-your-code-c41 | MailBridge blog post | Tier 2 | Yes |
| 12 | https://github.com/gamalan/mcp-email-client | MCP Email Client | Tier 1 | Moderate |
| 13 | https://learn.emailengine.app/docs/getting-started/introduction | EmailEngine docs - Introduction | Tier 1 | Yes |
| 14 | https://pypi.org/project/o365/ | o365 on PyPI | Tier 1 | Moderate |
| 15 | https://github.com/vgrem/office365-rest-python-client | office365-rest-python-client | Tier 1 | Moderate |

### Sources Cited in Findings

| # | URL | Title | Key Contribution |
|---|-----|-------|-----------------|
| 1 | https://jellis18.github.io/post/2022-01-11-abc-vs-protocol/ | ABC vs Protocol comparison | Practical guidance on when to use ABCs vs Protocols for provider interfaces |
| 2 | https://docs.python.org/3/library/abc.html | Python abc module docs | Reference for ABC implementation |
| 3 | https://github.com/codevelo-pub/mailbridge | MailBridge | Example of Strategy/Adapter pattern for multi-provider email sending |
| 4 | https://github.com/O365/python-o365 | python-o365 | Primary library for Microsoft Graph email operations in Python |
| 5 | https://emailengine.app/ | EmailEngine | Validates unified API over Gmail API + Microsoft Graph + IMAP |
| 6 | https://github.com/postalsys/emailengine | EmailEngine source | Architecture reference for multi-provider email gateway |
| 7 | https://www.nylas.com/products/email-api/ | Nylas Email API | Commercial validation of multi-provider email abstraction model |
| 8 | https://github.com/marrow/mailer | Marrow Mailer | Duck-typed transport plugin architecture example |

## Evaluation

**Confidence**: high
**Satisfactorily Explored**: yes
**Reasoning**: Multiple independent sources confirm the Strategy/ABC pattern as the standard approach. The python-o365 library is well-documented for the O365 side. Both commercial (Nylas) and open-source (EmailEngine, MailBridge) projects validate that multi-provider email abstraction is practical and well-understood.

### Further Research Needed

- Detailed mapping of Gmail API operations to Microsoft Graph API equivalents (field names, pagination models, error handling differences).
- Query syntax translation strategies between Gmail search syntax and OData $filter/$search.
- Authentication flow differences: Gmail OAuth scopes vs. Microsoft identity platform scopes/permissions, and how to manage credentials for multiple providers simultaneously.
