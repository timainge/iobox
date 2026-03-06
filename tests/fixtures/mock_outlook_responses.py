"""
Mock objects for python-o365 / Microsoft Graph API tests.

This module provides lightweight stand-in classes that mimic the python-o365
``Account``, ``Mailbox``, ``Message``, ``Attachment``, and delta-response
objects used by ``OutlookProvider``.  All classes expose only the attributes
and methods referenced in the provider spec (section 10.3–10.9).

Usage in tests::

    from tests.fixtures.mock_outlook_responses import (
        MockAccount,
        MockMailbox,
        MockMessage,
        MockAttachment,
        MOCK_PLAIN_TEXT_MESSAGE,
        MOCK_HTML_MESSAGE,
        MOCK_ATTACHMENT_MESSAGE,
        MOCK_DRAFT_MESSAGE,
        MOCK_DELTA_RESPONSE,
        MOCK_DELTA_RESPONSE_WITH_REMOVED,
        MOCK_DELTA_RESPONSE_EXPIRED,
        make_mock_account,
        make_mock_mailbox,
        make_mock_message,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Low-level building blocks
# ---------------------------------------------------------------------------


class MockEmailAddress:
    """Mimics the address object on ``msg.sender`` and ``msg.to``."""

    def __init__(self, name: str, address: str) -> None:
        self.name = name
        self.address = address

    def __str__(self) -> str:
        return f"{self.name} <{self.address}>"


class MockAttachment:
    """Mimics an ``O365.message.MessageAttachment`` object."""

    def __init__(
        self,
        attachment_id: str,
        name: str,
        content_type: str,
        size: int,
        content: bytes,
    ) -> None:
        self.attachment_id = attachment_id
        self.name = name
        self.content_type = content_type
        self.size = size
        # Raw bytes — returned by download_attachment()
        self.content = content

    def __repr__(self) -> str:
        return f"MockAttachment(name={self.name!r}, size={self.size})"


class MockAttachments:
    """Mimics the attachments container on a ``Message``.

    Supports iteration and ``add(path)`` (no-op in tests).
    """

    def __init__(self, attachments: list[MockAttachment] | None = None) -> None:
        self._items: list[MockAttachment] = attachments or []

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def add(self, path: str) -> None:
        """No-op stub for msg.attachments.add(path) in write-op tests."""


class MockRecipients:
    """Mimics a recipients container (msg.to, msg.cc, msg.bcc)."""

    def __init__(self, addresses: list[MockEmailAddress] | None = None) -> None:
        self._items: list[MockEmailAddress] = addresses or []

    def __iter__(self):
        return iter(self._items)

    def add(self, address: str) -> None:
        """No-op stub for msg.to.add(address) in write-op tests."""

    def __repr__(self) -> str:
        return f"MockRecipients({self._items!r})"


class MockFlag:
    """Mimics the ``flag`` property on a Graph message."""

    def __init__(self, flag_status: str = "notFlagged") -> None:
        # Valid values: "notFlagged", "flagged", "complete"
        self.flag_status = flag_status

    def __repr__(self) -> str:
        return f"MockFlag(flagStatus={self.flag_status!r})"


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class MockMessage:
    """Mimics an ``O365.message.Message`` object.

    Attributes mirror those accessed in ``OutlookProvider._message_to_email_data``
    and all write/organization methods described in spec sections 10.4–10.6.
    """

    def __init__(
        self,
        object_id: str,
        conversation_id: str,
        subject: str,
        sender_name: str,
        sender_address: str,
        received: datetime,
        categories: list[str],
        body_preview: str,
        body: str,
        body_type: str = "HTML",
        is_read: bool = True,
        is_draft: bool = False,
        has_attachments: bool = False,
        attachments: list[MockAttachment] | None = None,
        flag_status: str = "notFlagged",
    ) -> None:
        self.object_id = object_id
        self.conversation_id = conversation_id
        self.subject = subject
        self.sender = MockEmailAddress(sender_name, sender_address)
        self.received = received
        self.categories = list(categories)
        self.body_preview = body_preview
        self.body = body
        # body_type is 'HTML' or 'Text' — mirrors Graph bodyType
        self.body_type = body_type
        self.is_read = is_read
        self.is_draft = is_draft
        self.has_attachments = has_attachments
        self.attachments = MockAttachments(attachments)
        self.flag = MockFlag(flag_status)
        # Recipients containers
        self.to = MockRecipients()
        self.cc = MockRecipients()
        self.bcc = MockRecipients()

        # Track method calls for test assertions
        self._sent = False
        self._deleted = False
        self._draft_saved = False
        self._moved_to: Any = None
        self._read_marked: bool | None = None
        self._message_saved = False

    # ── Read helpers ──────────────────────────────────────────────────────

    def get_body_text(self) -> str:
        """BeautifulSoup plain-text fallback — returns body_preview in mocks."""
        return self.body_preview

    # ── Write helpers ─────────────────────────────────────────────────────

    def send(self) -> bool:
        self._sent = True
        return True

    def save_draft(self) -> bool:
        self._draft_saved = True
        return True

    def save_message(self) -> bool:
        self._message_saved = True
        return True

    def delete(self) -> bool:
        self._deleted = True
        return True

    def move(self, folder: Any) -> bool:
        self._moved_to = folder
        return True

    def mark_as_read(self) -> bool:
        self.is_read = True
        self._read_marked = True
        return True

    def mark_as_unread(self) -> bool:
        self.is_read = False
        self._read_marked = False
        return True

    def forward(self) -> "MockMessage":
        """Returns a new stub message to configure and send as a forward."""
        fwd = MockMessage(
            object_id=f"fwd-{self.object_id}",
            conversation_id=self.conversation_id,
            subject=f"FW: {self.subject}",
            sender_name="",
            sender_address="",
            received=self.received,
            categories=[],
            body_preview="",
            body=self.body,
        )
        return fwd

    def __repr__(self) -> str:
        return (
            f"MockMessage(object_id={self.object_id!r}, subject={self.subject!r})"
        )


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


class MockQueryCondition:
    """Mimics a chained condition returned by ``Query.on_attribute()``."""

    def __init__(self, query: "MockQuery", attribute: str) -> None:
        self._query = query
        self._attribute = attribute

    def equals(self, value: Any) -> "MockQuery":
        self._query._filters.append((self._attribute, "eq", value))
        return self._query

    def contains(self, value: Any) -> "MockQuery":
        self._query._filters.append((self._attribute, "contains", value))
        return self._query

    def greater_equal(self, value: Any) -> "MockQuery":
        self._query._filters.append((self._attribute, "ge", value))
        return self._query

    def less(self, value: Any) -> "MockQuery":
        self._query._filters.append((self._attribute, "lt", value))
        return self._query


class MockQuery:
    """Mimics ``O365.utils.Query`` — records filter conditions for assertions."""

    def __init__(self) -> None:
        self._filters: list[tuple[str, str, Any]] = []
        self._search: str | None = None
        self._order_by: str | None = None

    def on_attribute(self, attribute: str) -> MockQueryCondition:
        return MockQueryCondition(self, attribute)

    def search(self, search_text: str) -> "MockQuery":
        self._search = search_text
        return self

    def order_by(self, attribute: str, ascending: bool = True) -> "MockQuery":
        self._order_by = attribute
        return self

    def __repr__(self) -> str:
        return f"MockQuery(filters={self._filters!r}, search={self._search!r})"


# ---------------------------------------------------------------------------
# Folder
# ---------------------------------------------------------------------------


class MockFolder:
    """Mimics an ``O365.mailbox.MailBox`` folder (Inbox, Drafts, Archive …)."""

    def __init__(
        self,
        name: str,
        messages: list[MockMessage] | None = None,
    ) -> None:
        self.name = name
        self._messages: list[MockMessage] = messages or []

    def get_messages(
        self,
        query: MockQuery | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[MockMessage]:
        msgs = list(self._messages)
        if limit is not None:
            msgs = msgs[:limit]
        return msgs

    def new_query(self) -> MockQuery:
        return MockQuery()

    def __repr__(self) -> str:
        return f"MockFolder(name={self.name!r}, messages={len(self._messages)})"


# ---------------------------------------------------------------------------
# Mailbox
# ---------------------------------------------------------------------------


class MockMailbox:
    """Mimics ``O365.mailbox.MailBox``."""

    def __init__(
        self,
        inbox: MockFolder | None = None,
        drafts: MockFolder | None = None,
        archive: MockFolder | None = None,
        messages_by_id: dict[str, MockMessage] | None = None,
    ) -> None:
        self._inbox = inbox or MockFolder("Inbox")
        self._drafts = drafts or MockFolder("Drafts")
        self._archive = archive or MockFolder("Archive")
        # For get_message(object_id=…) lookups
        self._messages_by_id: dict[str, MockMessage] = messages_by_id or {}
        # Tracks new messages created via new_message()
        self._new_messages: list[MockMessage] = []

    def inbox_folder(self) -> MockFolder:
        return self._inbox

    def drafts_folder(self) -> MockFolder:
        return self._drafts

    def archive_folder(self) -> MockFolder:
        return self._archive

    def get_message(self, object_id: str) -> MockMessage | None:
        return self._messages_by_id.get(object_id)

    def new_message(self) -> MockMessage:
        msg = MockMessage(
            object_id=f"new-message-{len(self._new_messages) + 1}",
            conversation_id="new-conversation-id",
            subject="",
            sender_name="",
            sender_address="",
            received=datetime.now(tz=timezone.utc),
            categories=[],
            body_preview="",
            body="",
        )
        self._new_messages.append(msg)
        return msg

    def new_query(self) -> MockQuery:
        return MockQuery()

    def __repr__(self) -> str:
        return "MockMailbox()"


# ---------------------------------------------------------------------------
# Connection / session
# ---------------------------------------------------------------------------


class MockSession:
    """Mimics ``account.con.session`` — tracks header mutations."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


class MockConnection:
    """Mimics ``account.con`` — exposes session and a minimal get() stub."""

    def __init__(self) -> None:
        self.session = MockSession()
        self._delta_responses: dict[str, dict] = {}

    def get(self, url: str, **kwargs: Any) -> "MockHttpResponse":
        if url in self._delta_responses:
            return MockHttpResponse(self._delta_responses[url])
        raise ValueError(f"No mock delta response registered for URL: {url!r}")


class MockHttpResponse:
    """Minimal HTTP response stub returned by ``MockConnection.get()``."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self.status_code = 200

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class MockAccount:
    """Mimics ``O365.Account``.

    ``is_authenticated`` defaults to ``True`` so most tests skip the auth flow.
    Set it to ``False`` to test first-time auth branches.
    """

    def __init__(
        self,
        is_authenticated: bool = True,
        mailbox: MockMailbox | None = None,
    ) -> None:
        self.is_authenticated = is_authenticated
        self._mailbox = mailbox or MockMailbox()
        self.con = MockConnection()
        # Track authenticate() calls
        self._authenticate_calls: list[dict] = []

    def authenticate(
        self,
        scopes: list[str] | None = None,
        grant_type: str | None = None,
    ) -> bool:
        self._authenticate_calls.append(
            {"scopes": scopes, "grant_type": grant_type}
        )
        self.is_authenticated = True
        return True

    def mailbox(self) -> MockMailbox:
        return self._mailbox

    def __repr__(self) -> str:
        return f"MockAccount(is_authenticated={self.is_authenticated})"


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_mock_message(
    object_id: str = "msg-id-1",
    conversation_id: str = "conv-id-1",
    subject: str = "Test Subject",
    sender_name: str = "Alice Sender",
    sender_address: str = "alice@example.com",
    received: datetime | None = None,
    categories: list[str] | None = None,
    body_preview: str = "This is a preview of the email body.",
    body: str = "<html><body><p>This is the email body.</p></body></html>",
    body_type: str = "HTML",
    is_read: bool = True,
    is_draft: bool = False,
    has_attachments: bool = False,
    attachments: list[MockAttachment] | None = None,
    flag_status: str = "notFlagged",
) -> MockMessage:
    """Return a ``MockMessage`` with sensible defaults."""
    if received is None:
        received = datetime(2026, 3, 6, 10, 0, 0, tzinfo=timezone.utc)
    return MockMessage(
        object_id=object_id,
        conversation_id=conversation_id,
        subject=subject,
        sender_name=sender_name,
        sender_address=sender_address,
        received=received,
        categories=categories or [],
        body_preview=body_preview,
        body=body,
        body_type=body_type,
        is_read=is_read,
        is_draft=is_draft,
        has_attachments=has_attachments,
        attachments=attachments,
        flag_status=flag_status,
    )


def make_mock_mailbox(
    messages: list[MockMessage] | None = None,
) -> MockMailbox:
    """Return a ``MockMailbox`` pre-loaded with *messages* in the inbox.

    Each message is also indexed by ``object_id`` for ``get_message()`` lookups.
    """
    msgs = messages or []
    by_id = {m.object_id: m for m in msgs}
    inbox = MockFolder("Inbox", msgs)
    return MockMailbox(inbox=inbox, messages_by_id=by_id)


def make_mock_account(
    is_authenticated: bool = True,
    messages: list[MockMessage] | None = None,
) -> MockAccount:
    """Return a ``MockAccount`` wired to a mailbox containing *messages*."""
    mailbox = make_mock_mailbox(messages)
    return MockAccount(is_authenticated=is_authenticated, mailbox=mailbox)


# ---------------------------------------------------------------------------
# Pre-built message fixtures
# ---------------------------------------------------------------------------

MOCK_PLAIN_TEXT_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-1",
    conversation_id="outlook-conv-id-1",
    subject="Plain Text Email",
    sender_name="Bob Sender",
    sender_address="bob@example.com",
    received=datetime(2026, 3, 6, 9, 0, 0, tzinfo=timezone.utc),
    body_preview="This is a plain text email.",
    body="This is a plain text email.",
    body_type="Text",
    is_read=True,
    categories=["Work"],
)

MOCK_HTML_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-2",
    conversation_id="outlook-conv-id-2",
    subject="HTML Email Subject",
    sender_name="Carol Sender",
    sender_address="carol@example.com",
    received=datetime(2026, 3, 6, 10, 0, 0, tzinfo=timezone.utc),
    body_preview="This is the HTML version of the email.",
    body=(
        "<html><body>"
        "<p>This is the <strong>HTML</strong> version of the email.</p>"
        "</body></html>"
    ),
    body_type="HTML",
    is_read=False,
    categories=[],
)

MOCK_ATTACHMENT_FILE = MockAttachment(
    attachment_id="outlook-attach-id-1",
    name="document.pdf",
    content_type="application/pdf",
    size=1024,
    content=b"%PDF-1.4 mock pdf content",
)

MOCK_ATTACHMENT_IMAGE = MockAttachment(
    attachment_id="outlook-attach-id-2",
    name="screenshot.png",
    content_type="image/png",
    size=2048,
    content=b"\x89PNG\r\n mock png content",
)

MOCK_ATTACHMENT_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-3",
    conversation_id="outlook-conv-id-3",
    subject="Email with Attachment",
    sender_name="Dave Sender",
    sender_address="dave@example.com",
    received=datetime(2026, 3, 6, 11, 0, 0, tzinfo=timezone.utc),
    body_preview="This email has an attachment.",
    body="<html><body><p>This email has an attachment.</p></body></html>",
    body_type="HTML",
    has_attachments=True,
    attachments=[MOCK_ATTACHMENT_FILE],
)

MOCK_MULTI_ATTACHMENT_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-4",
    conversation_id="outlook-conv-id-3",
    subject="Email with Multiple Attachments",
    sender_name="Dave Sender",
    sender_address="dave@example.com",
    received=datetime(2026, 3, 6, 11, 30, 0, tzinfo=timezone.utc),
    body_preview="This email has multiple attachments.",
    body="<html><body><p>This email has multiple attachments.</p></body></html>",
    body_type="HTML",
    has_attachments=True,
    attachments=[MOCK_ATTACHMENT_FILE, MOCK_ATTACHMENT_IMAGE],
)

MOCK_DRAFT_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-draft-id-1",
    conversation_id="outlook-conv-draft-1",
    subject="Draft Email",
    sender_name="Eve Sender",
    sender_address="eve@example.com",
    received=datetime(2026, 3, 6, 8, 0, 0, tzinfo=timezone.utc),
    body_preview="This is a draft email.",
    body="<html><body><p>This is a draft email.</p></body></html>",
    is_read=True,
    is_draft=True,
    categories=[],
)

MOCK_STARRED_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-5",
    conversation_id="outlook-conv-id-5",
    subject="Starred/Flagged Email",
    sender_name="Frank Sender",
    sender_address="frank@example.com",
    received=datetime(2026, 3, 6, 7, 0, 0, tzinfo=timezone.utc),
    body_preview="This email is flagged.",
    body="<html><body><p>This email is flagged.</p></body></html>",
    categories=["Important"],
    flag_status="flagged",
)

MOCK_UNREAD_MESSAGE: MockMessage = make_mock_message(
    object_id="outlook-msg-id-6",
    conversation_id="outlook-conv-id-6",
    subject="Unread Email",
    sender_name="Grace Sender",
    sender_address="grace@example.com",
    received=datetime(2026, 3, 6, 6, 0, 0, tzinfo=timezone.utc),
    body_preview="This email is unread.",
    body="<html><body><p>This email is unread.</p></body></html>",
    is_read=False,
    categories=[],
)

# A thread with two messages sharing the same conversation_id
MOCK_THREAD_MESSAGE_1: MockMessage = make_mock_message(
    object_id="outlook-thread-msg-1",
    conversation_id="outlook-conv-thread-1",
    subject="Thread Email",
    sender_name="Hank Sender",
    sender_address="hank@example.com",
    received=datetime(2026, 3, 6, 9, 0, 0, tzinfo=timezone.utc),
    body_preview="First message in thread.",
    body="<html><body><p>First message in thread.</p></body></html>",
)

MOCK_THREAD_MESSAGE_2: MockMessage = make_mock_message(
    object_id="outlook-thread-msg-2",
    conversation_id="outlook-conv-thread-1",
    subject="Re: Thread Email",
    sender_name="Iris Recipient",
    sender_address="iris@example.com",
    received=datetime(2026, 3, 6, 9, 30, 0, tzinfo=timezone.utc),
    body_preview="Reply in thread.",
    body="<html><body><p>Reply in thread.</p></body></html>",
)

# ---------------------------------------------------------------------------
# Delta / sync response fixtures
# ---------------------------------------------------------------------------

#: Normal delta response — two new messages, no removals.
MOCK_DELTA_RESPONSE: dict = {
    "@odata.context": (
        "https://graph.microsoft.com/v1.0/$metadata#Collection(message)"
    ),
    "value": [
        {
            "id": "outlook-msg-id-1",
            "subject": "Plain Text Email",
            "receivedDateTime": "2026-03-06T09:00:00Z",
        },
        {
            "id": "outlook-msg-id-2",
            "subject": "HTML Email Subject",
            "receivedDateTime": "2026-03-06T10:00:00Z",
        },
    ],
    "@odata.deltaLink": (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        "/delta?$deltatoken=abc123"
    ),
}

#: Delta response that includes a soft-deleted message (``@removed`` annotation).
MOCK_DELTA_RESPONSE_WITH_REMOVED: dict = {
    "@odata.context": (
        "https://graph.microsoft.com/v1.0/$metadata#Collection(message)"
    ),
    "value": [
        {
            "id": "outlook-msg-id-1",
            "subject": "New Message",
            "receivedDateTime": "2026-03-06T09:00:00Z",
        },
        {
            "id": "outlook-msg-id-deleted",
            "@removed": {"reason": "deleted"},
        },
    ],
    "@odata.deltaLink": (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        "/delta?$deltatoken=def456"
    ),
}

#: Empty delta response — no new or removed messages since last sync.
MOCK_DELTA_RESPONSE_EMPTY: dict = {
    "@odata.context": (
        "https://graph.microsoft.com/v1.0/$metadata#Collection(message)"
    ),
    "value": [],
    "@odata.deltaLink": (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
        "/delta?$deltatoken=ghi789"
    ),
}

#: Simulated 410 Gone response body — deltaLink has expired, full re-sync needed.
MOCK_DELTA_RESPONSE_EXPIRED: dict = {
    "error": {
        "code": "SyncStateNotFound",
        "message": (
            "The sync state generation is not found. "
            "deltaLink may have expired. Please do a full sync."
        ),
    }
}

# ---------------------------------------------------------------------------
# Master categories (list_tags)
# ---------------------------------------------------------------------------

#: Mimics GET /me/outlook/masterCategories response value list.
MOCK_MASTER_CATEGORIES: list[dict] = [
    {"id": "cat-id-1", "displayName": "Work", "color": "preset0"},
    {"id": "cat-id-2", "displayName": "Personal", "color": "preset1"},
    {"id": "cat-id-3", "displayName": "Important", "color": "preset2"},
]

# ---------------------------------------------------------------------------
# Convenience account/mailbox fixtures
# ---------------------------------------------------------------------------

#: A pre-authenticated account with all fixture messages in the inbox.
def make_full_mock_account() -> MockAccount:
    """Return a fully-populated ``MockAccount`` containing all fixture messages.

    The inbox contains all non-draft messages; drafts folder contains
    ``MOCK_DRAFT_MESSAGE``.  All messages are indexed by ``object_id`` for
    ``get_message()`` lookups.
    """
    all_inbox_messages = [
        MOCK_PLAIN_TEXT_MESSAGE,
        MOCK_HTML_MESSAGE,
        MOCK_ATTACHMENT_MESSAGE,
        MOCK_MULTI_ATTACHMENT_MESSAGE,
        MOCK_STARRED_MESSAGE,
        MOCK_UNREAD_MESSAGE,
        MOCK_THREAD_MESSAGE_1,
        MOCK_THREAD_MESSAGE_2,
    ]
    inbox = MockFolder("Inbox", all_inbox_messages)
    drafts = MockFolder("Drafts", [MOCK_DRAFT_MESSAGE])
    archive = MockFolder("Archive", [])

    all_messages = {m.object_id: m for m in all_inbox_messages}
    all_messages[MOCK_DRAFT_MESSAGE.object_id] = MOCK_DRAFT_MESSAGE

    mailbox = MockMailbox(
        inbox=inbox,
        drafts=drafts,
        archive=archive,
        messages_by_id=all_messages,
    )
    account = MockAccount(is_authenticated=True, mailbox=mailbox)
    return account
