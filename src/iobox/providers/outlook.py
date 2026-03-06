"""
OutlookProvider — Microsoft 365 / Outlook email backend.

Implements the ``EmailProvider`` ABC for Microsoft 365 using the python-o365
library (which wraps the Microsoft Graph API internally).

Read operations (authenticate, search, get content, batch fetch, threads,
attachment download, and query translation) are fully implemented here.
Write operations (send, forward, drafts CRUD) are also fully implemented.
Organization and sync operations are stubbed with ``NotImplementedError``
and will be filled in by subsequent tasks.

ImmutableId header
------------------
All Graph requests made through ``account.con.session`` carry the header::

    Prefer: IdType="ImmutableId"

This prevents message IDs from silently changing when messages are moved
between folders — a Microsoft Graph quirk that would break any saved
reference to a message ID.

Query path selection
--------------------
Microsoft Graph's ``/me/mailFolders/{id}/messages`` endpoint cannot combine
``$filter`` and ``$search`` in the same request.  The provider selects the
path based on whether free-text search is needed:

* ``raw_query`` set → KQL passthrough via ``$search``
* ``query.text`` set → ``$search`` with KQL built from all query fields
* otherwise → ``$filter`` via python-o365 ``Query`` builder
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from iobox.providers.base import AttachmentInfo, EmailData, EmailProvider, EmailQuery

logger = logging.getLogger(__name__)

# Header applied to every Graph request to ensure stable, immutable message IDs.
_IMMUTABLE_ID_HEADER: dict[str, str] = {"Prefer": 'IdType="ImmutableId"'}


class OutlookProvider(EmailProvider):
    """EmailProvider backed by Microsoft 365 via python-o365 / Graph API."""

    def __init__(self) -> None:
        self._account: Any | None = None   # O365.Account instance
        self._mailbox: Any | None = None   # O365.MailBox instance

    # ------------------------------------------------------------------
    # Internal lazy-access properties
    # ------------------------------------------------------------------

    @property
    def _acct(self) -> Any:
        """Return the authenticated Account, authenticating lazily if needed."""
        if self._account is None:
            self.authenticate()
        return self._account

    @property
    def _mb(self) -> Any:
        """Return the authenticated Mailbox, initialising lazily if needed."""
        if self._mailbox is None:
            self._mailbox = self._acct.mailbox()
        return self._mailbox

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_immutable_id_header(self) -> None:
        """Apply the ImmutableId preference header to all Graph requests."""
        self._account.con.session.headers.update(_IMMUTABLE_ID_HEADER)

    def _message_to_email_data(
        self,
        msg: Any,
        include_body: bool = True,
    ) -> EmailData:
        """Convert a python-o365 ``Message`` object into an :class:`EmailData` dict.

        Args:
            msg: A python-o365 ``Message`` (or ``MockMessage`` in tests).
            include_body: When ``True``, include ``body``, ``content_type``,
                and ``attachments`` fields.  Set to ``False`` for lightweight
                search/metadata results.

        Returns:
            Normalised :class:`EmailData` dict compatible with downstream
            modules (``markdown_converter``, ``file_manager``).
        """
        # ── Sender → "Display Name <email>" string ───────────────────
        sender = msg.sender
        if sender and getattr(sender, "address", None):
            name = getattr(sender, "name", "") or ""
            from_ = f"{name} <{sender.address}>" if name else sender.address
        else:
            from_ = ""

        # ── Received datetime → ISO 8601 string ──────────────────────
        received = msg.received
        if received is not None and hasattr(received, "isoformat"):
            date_str = received.isoformat()
        else:
            date_str = str(received) if received is not None else ""

        data: EmailData = {
            "message_id": msg.object_id or "",
            "thread_id": msg.conversation_id or "",
            "subject": msg.subject or "",
            "from_": from_,
            "date": date_str,
            "snippet": msg.body_preview or "",
            "labels": list(msg.categories) if msg.categories else [],
        }

        if include_body:
            data["body"] = msg.body or ""

            # Graph returns HTML by default; preserve for html2text conversion.
            # body_type is 'HTML' or 'Text' on real Graph messages.
            body_type = getattr(msg, "body_type", "HTML")
            data["content_type"] = "text/plain" if body_type == "Text" else "text/html"

            # Attachment metadata (content bytes fetched separately).
            if msg.has_attachments:
                data["attachments"] = [
                    AttachmentInfo(
                        id=getattr(a, "attachment_id", ""),
                        filename=getattr(a, "name", ""),
                        mime_type=getattr(
                            a, "content_type", "application/octet-stream"
                        ),
                        size=getattr(a, "size", 0),
                    )
                    for a in msg.attachments
                ]
            else:
                data["attachments"] = []

        return data

    def _build_outlook_filter(self, query: EmailQuery) -> Any:
        """Build an OData ``$filter`` query using the python-o365 Query builder.

        Used when no free-text (``query.text``) is present.

        Args:
            query: Structured email query parameters.

        Returns:
            A python-o365 ``Query`` object ready for ``get_messages(query=...)``.
        """
        q = self._mb.new_query()

        if query.from_addr:
            q = q.on_attribute("from/emailAddress/address").equals(query.from_addr)

        if query.subject:
            q = q.on_attribute("subject").contains(query.subject)

        if query.after:
            after_dt = datetime.combine(query.after, datetime.min.time())
            q = q.on_attribute("receivedDateTime").greater_equal(after_dt)

        if query.before:
            before_dt = datetime.combine(query.before, datetime.min.time())
            q = q.on_attribute("receivedDateTime").less(before_dt)

        if query.has_attachment is True:
            q = q.on_attribute("hasAttachments").equals(True)
        elif query.has_attachment is False:
            q = q.on_attribute("hasAttachments").equals(False)

        if query.is_unread is True:
            q = q.on_attribute("isRead").equals(False)
        elif query.is_unread is False:
            q = q.on_attribute("isRead").equals(True)

        return q

    def _build_outlook_search(self, query: EmailQuery) -> str:
        """Build a KQL ``$search`` string.

        Used when ``query.text`` is present.  Note: ``$filter`` and ``$search``
        **cannot** be combined on Graph message collections.

        Args:
            query: Structured email query parameters.

        Returns:
            KQL search string for the ``$search`` query parameter.
        """
        parts: list[str] = []

        if query.from_addr:
            parts.append(f"from:{query.from_addr}")
        if query.subject:
            parts.append(f"subject:{query.subject}")
        if query.after:
            parts.append(f"received>={query.after.isoformat()}")
        if query.before:
            parts.append(f"received<{query.before.isoformat()}")
        if query.has_attachment is True:
            parts.append("hasAttachments:true")
        if query.text:
            parts.append(f'"{query.text}"')

        return " ".join(parts)

    # ------------------------------------------------------------------
    # 1. Authentication & profile
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Authenticate with Microsoft 365 and configure the ImmutableId header.

        On first call this triggers the OAuth consent flow (browser or
        device-code depending on the ``outlook_auth`` configuration).
        Subsequent calls reuse the cached token transparently.
        """
        from iobox.providers.outlook_auth import get_outlook_account

        self._account = get_outlook_account()
        self._mailbox = self._account.mailbox()
        self._set_immutable_id_header()

    def get_profile(self) -> dict:
        """Return basic authentication status as a profile dict.

        python-o365 does not expose ``/me`` profile data via a dedicated method;
        a future enhancement can call ``self._acct.con.get('.../me')`` to fetch
        the full profile (displayName, mail, etc.).
        """
        acct = self._acct
        return {
            "provider": "outlook",
            "authenticated": acct.is_authenticated,
        }

    # ------------------------------------------------------------------
    # 2. Search & read
    # ------------------------------------------------------------------

    def search_emails(self, query: EmailQuery) -> list[EmailData]:
        """Search the Outlook inbox and return normalised metadata results.

        Query path selection:

        1. ``raw_query`` set → KQL passthrough via ``$search``
        2. ``query.text`` set → ``$search`` with KQL built from all fields
        3. No free-text → ``$filter`` with OData conditions

        Args:
            query: Provider-agnostic search parameters.

        Returns:
            List of :class:`EmailData` dicts (body absent — metadata only).
        """
        inbox = self._mb.inbox_folder()

        if query.raw_query:
            # Raw KQL passthrough.
            q = inbox.new_query().search(query.raw_query)
            messages = inbox.get_messages(query=q, limit=query.max_results)
        elif query.text:
            # Free-text present — must use $search; cannot combine with $filter.
            kql = self._build_outlook_search(query)
            q = inbox.new_query().search(kql)
            messages = inbox.get_messages(query=q, limit=query.max_results)
        else:
            # Structured filters only — use $filter path.
            q = self._build_outlook_filter(query)
            messages = inbox.get_messages(query=q, limit=query.max_results)

        return [
            self._message_to_email_data(msg, include_body=False) for msg in messages
        ]

    def get_email_content(
        self, message_id: str, preferred_content_type: str = "text/plain"
    ) -> EmailData:
        """Retrieve the full content of a single email by its immutable ID.

        Args:
            message_id: The message's immutable Graph object ID.
            preferred_content_type: Not used for Outlook (body is always HTML
                from Graph); kept for ABC compatibility.

        Returns:
            :class:`EmailData` dict with ``body`` and ``attachments`` populated.

        Raises:
            ValueError: If the message ID is not found.
        """
        msg = self._mb.get_message(object_id=message_id)
        if msg is None:
            raise ValueError(f"Message not found: {message_id!r}")
        return self._message_to_email_data(msg, include_body=True)

    def batch_get_emails(
        self, message_ids: list[str], preferred_content_type: str = "text/plain"
    ) -> list[EmailData]:
        """Retrieve full content for a list of message IDs.

        Graph's list endpoint returns complete message bodies, so individual
        ``GET`` calls are sufficient here.  Missing IDs are logged and skipped.

        Args:
            message_ids: List of immutable Graph message IDs.
            preferred_content_type: Not used for Outlook; kept for ABC compat.

        Returns:
            List of :class:`EmailData` dicts in the same order as ``message_ids``
            (missing messages are omitted).
        """
        results: list[EmailData] = []
        for mid in message_ids:
            msg = self._mb.get_message(object_id=mid)
            if msg is not None:
                results.append(self._message_to_email_data(msg, include_body=True))
            else:
                logger.warning("Message not found during batch_get_emails: %r", mid)
        return results

    def get_thread(self, thread_id: str) -> list[EmailData]:
        """Return all messages in a conversation, ordered chronologically.

        Filters inbox messages by ``conversationId`` using the ``$filter`` path.

        Args:
            thread_id: The Outlook ``conversationId`` (maps to ``thread_id``
                in :class:`EmailData`).

        Returns:
            List of :class:`EmailData` dicts ordered by ``receivedDateTime``.
        """
        inbox = self._mb.inbox_folder()
        q = inbox.new_query().on_attribute("conversationId").equals(thread_id)
        messages = inbox.get_messages(query=q, order_by="receivedDateTime asc")
        return [self._message_to_email_data(msg, include_body=True) for msg in messages]

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download a single attachment and return its raw bytes.

        Args:
            message_id: Immutable message ID containing the attachment.
            attachment_id: The attachment's ID (``attachment_id`` attribute on
                the attachment object).

        Returns:
            Raw attachment bytes.

        Raises:
            ValueError: If the message or attachment is not found.
        """
        msg = self._mb.get_message(object_id=message_id)
        if msg is None:
            raise ValueError(f"Message not found: {message_id!r}")

        for attachment in msg.attachments:
            a_id = getattr(attachment, "attachment_id", None)
            if a_id == attachment_id:
                return attachment.content

        raise ValueError(
            f"Attachment {attachment_id!r} not found in message {message_id!r}"
        )

    # ------------------------------------------------------------------
    # 3. Send, forward & drafts
    # ------------------------------------------------------------------

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
        attachments: list[str] | None = None,
    ) -> dict:
        """Compose and immediately send an email via Microsoft Graph.

        python-o365 handles attachment sizing internally:
        files < 3 MB are sent inline; larger files use an upload session.

        Args:
            to: Primary recipient email address.
            subject: Email subject line.
            body: Email body text (plain or HTML depending on *content_type*).
            cc: Optional CC recipient address.
            bcc: Optional BCC recipient address.
            content_type: ``"plain"`` (default) or ``"html"``.
            attachments: Optional list of local file paths to attach.

        Returns:
            Dict with ``message_id`` and ``status`` keys.
        """
        msg = self._mb.new_message()
        msg.to.add(to)
        if cc:
            msg.cc.add(cc)
        if bcc:
            msg.bcc.add(bcc)
        msg.subject = subject
        msg.body = body
        if content_type.lower() == "html":
            msg.body_type = "HTML"
        else:
            msg.body_type = "Text"
        for path in (attachments or []):
            msg.attachments.add(path)
        msg.send()
        return {"message_id": msg.object_id, "status": "sent"}

    def forward_message(
        self, message_id: str, to: str, comment: str | None = None
    ) -> dict:
        """Forward an existing message using the native Graph forward endpoint.

        No manual "---------- Forwarded message ----------" body construction
        is needed — Graph handles the forwarded body automatically.

        Args:
            message_id: Immutable message ID to forward.
            to: Recipient address for the forward.
            comment: Optional introductory text prepended to the forwarded body.

        Returns:
            Dict with ``message_id`` and ``status`` keys.

        Raises:
            ValueError: If the source message is not found.
        """
        msg = self._mb.get_message(object_id=message_id)
        if msg is None:
            raise ValueError(f"Message not found: {message_id!r}")
        fwd = msg.forward()
        fwd.to.add(to)
        if comment:
            fwd.body = comment
        fwd.send()
        return {"message_id": fwd.object_id, "status": "sent"}

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
    ) -> dict:
        """Create a new draft message and save it in the Drafts folder.

        Args:
            to: Primary recipient email address.
            subject: Email subject line.
            body: Email body text (plain or HTML depending on *content_type*).
            cc: Optional CC recipient address.
            bcc: Optional BCC recipient address.
            content_type: ``"plain"`` (default) or ``"html"``.

        Returns:
            Dict with ``message_id`` and ``status`` keys.
        """
        msg = self._mb.new_message()
        msg.to.add(to)
        if cc:
            msg.cc.add(cc)
        if bcc:
            msg.bcc.add(bcc)
        msg.subject = subject
        msg.body = body
        if content_type.lower() == "html":
            msg.body_type = "HTML"
        else:
            msg.body_type = "Text"
        msg.save_draft()
        return {"message_id": msg.object_id, "status": "draft"}

    def list_drafts(self, max_results: int = 10) -> list[dict]:
        """Return a list of draft summaries from the Drafts folder.

        Args:
            max_results: Maximum number of drafts to return (default 10).

        Returns:
            List of dicts with ``message_id``, ``subject``, and ``snippet`` keys.
        """
        drafts_folder = self._mb.drafts_folder()
        messages = drafts_folder.get_messages(limit=max_results)
        return [
            {
                "message_id": msg.object_id,
                "subject": msg.subject or "",
                "snippet": msg.body_preview or "",
            }
            for msg in messages
        ]

    def send_draft(self, draft_id: str) -> dict:
        """Send an existing draft message.

        Args:
            draft_id: Immutable message ID of the draft to send.

        Returns:
            Dict with ``message_id`` and ``status`` keys.

        Raises:
            ValueError: If the draft is not found.
        """
        msg = self._mb.get_message(object_id=draft_id)
        if msg is None:
            raise ValueError(f"Draft not found: {draft_id!r}")
        msg.send()
        return {"message_id": draft_id, "status": "sent"}

    def delete_draft(self, draft_id: str) -> dict:
        """Permanently delete a draft message.

        Args:
            draft_id: Immutable message ID of the draft to delete.

        Returns:
            Dict with ``message_id`` and ``status`` keys.

        Raises:
            ValueError: If the draft is not found.
        """
        msg = self._mb.get_message(object_id=draft_id)
        if msg is None:
            raise ValueError(f"Draft not found: {draft_id!r}")
        msg.delete()
        return {"message_id": draft_id, "status": "deleted"}

    # ------------------------------------------------------------------
    # 4. System operations — to be implemented in a later task
    # ------------------------------------------------------------------

    def mark_read(self, message_id: str, read: bool = True) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.mark_read() will be implemented in the org-ops task."
        )

    def set_star(self, message_id: str, starred: bool = True) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.set_star() will be implemented in the org-ops task."
        )

    def archive(self, message_id: str) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.archive() will be implemented in the org-ops task."
        )

    def trash(self, message_id: str) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.trash() will be implemented in the org-ops task."
        )

    def untrash(self, message_id: str) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.untrash() will be implemented in the org-ops task."
        )

    # ------------------------------------------------------------------
    # 5. Tag operations — to be implemented in a later task
    # ------------------------------------------------------------------

    def add_tag(self, message_id: str, tag_name: str) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.add_tag() will be implemented in the org-ops task."
        )

    def remove_tag(self, message_id: str, tag_name: str) -> None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.remove_tag() will be implemented in the org-ops task."
        )

    def list_tags(self) -> dict[str, str]:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.list_tags() will be implemented in the org-ops task."
        )

    # ------------------------------------------------------------------
    # 6. Sync — to be implemented in a later task
    # ------------------------------------------------------------------

    def get_sync_state(self) -> str:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.get_sync_state() will be implemented in the sync task."
        )

    def get_new_messages(self, sync_token: str) -> list[str] | None:
        raise NotImplementedError(  # pragma: no cover
            "OutlookProvider.get_new_messages() will be implemented in the sync task."
        )
