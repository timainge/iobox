"""
OutlookProvider — Microsoft 365 / Outlook email backend.

Implements the ``EmailProvider`` ABC for Microsoft 365 using the python-o365
library (which wraps the Microsoft Graph API internally).

Read operations (authenticate, search, get content, batch fetch, threads,
attachment download, and query translation) are fully implemented here.
Write operations (send, forward, drafts CRUD) are also fully implemented.
Organization operations (mark read, star/flag, archive, trash, untrash,
category tags) are fully implemented with a ``_batch_graph_requests()``
helper that chunks multi-message operations into 20-request batches via
Graph's ``$batch`` endpoint.
Sync operations use Microsoft Graph's delta query mechanism to enable
incremental sync — fetching only messages added or changed since the
last sync.  A 410-Gone response (expired delta token) is handled
gracefully by signalling a full re-sync.

ImmutableId header
------------------
All Graph requests made through ``account.con.session`` carry the header::

    Prefer: IdType="ImmutableId"

This prevents message IDs from silently changing when messages are moved
between folders — a Microsoft Graph quirk that would break any saved
reference to a message ID.

All-mail search
---------------
``search_emails()`` and ``get_thread()`` use the root mailbox message
collection (``self._mb.get_messages()``) rather than
``self._mb.inbox_folder().get_messages()``.  This searches across **all
folders** — Inbox, Sent, Archive, Drafts, and custom folders — so that no
messages are silently excluded.

The python-o365 ``MailBox`` object (``self._mb``) exposes a ``get_messages()``
method that targets the ``/me/messages`` Graph endpoint rather than the
folder-scoped ``/me/mailFolders/{id}/messages`` endpoint.

Query path selection
--------------------
Microsoft Graph's ``/me/messages`` endpoint (like its folder-scoped cousin)
cannot combine ``$filter`` and ``$search`` in the same request.  The provider
selects the path based on whether free-text search is needed:

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
        self._account: Any | None = None  # O365.Account instance
        self._mailbox: Any | None = None  # O365.MailBox instance

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
        assert self._account is not None  # guaranteed by authenticate() calling this
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
                        mime_type=getattr(a, "content_type", "application/octet-stream"),
                        size=getattr(a, "size", 0),
                    )
                    for a in msg.attachments
                ]
            else:
                data["attachments"] = []

        return data

    def _build_outlook_filter(self, query: EmailQuery) -> Any:
        """Build an OData ``$filter`` query using the python-o365 Query builder.

        Used when no free-text (``query.text``) is present.  All structured
        ``EmailQuery`` fields are translated to OData filter expressions.

        ``raw_query`` is handled upstream in ``search_emails()`` and is never
        passed to this method.

        Args:
            query: Structured email query parameters.

        Returns:
            A python-o365 ``Query`` object ready for ``get_messages(query=...)``.
        """
        q = self._mb.new_query()

        if query.from_addr:
            q = q.on_attribute("from/emailAddress/address").equals(query.from_addr)

        if query.to_addr:
            q = q.on_attribute("toRecipients/emailAddress/address").equals(query.to_addr)

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

        if query.label:
            # OData lambda: categories/any(c:c eq 'LabelName')
            # We encode the full OData filter expression as the "attribute"
            # and use a raw marker so the provider can reconstruct it.
            escaped = query.label.replace("'", "''")
            raw_expr = f"categories/any(c:c eq '{escaped}')"
            q = q.on_attribute(raw_expr).equals(True)

        return q

    def _build_outlook_search(self, query: EmailQuery) -> str:
        """Build a KQL ``$search`` string.

        Used when ``query.text`` is present or ``raw_query`` triggers the
        ``$search`` path.  Note: ``$filter`` and ``$search`` **cannot** be
        combined on Graph message collections, so all conditions are expressed
        as KQL keywords here.

        ``raw_query`` is handled upstream in ``search_emails()`` and is never
        passed to this method.

        Args:
            query: Structured email query parameters.

        Returns:
            KQL search string for the ``$search`` query parameter.
        """
        parts: list[str] = []

        if query.from_addr:
            parts.append(f"from:{query.from_addr}")
        if query.to_addr:
            parts.append(f"to:{query.to_addr}")
        if query.subject:
            parts.append(f"subject:{query.subject}")
        if query.after:
            parts.append(f"received>={query.after.isoformat()}")
        if query.before:
            parts.append(f"received<{query.before.isoformat()}")
        if query.has_attachment is True:
            parts.append("hasAttachments:true")
        elif query.has_attachment is False:
            parts.append("hasAttachments:false")
        if query.is_unread is True:
            parts.append("isRead:false")
        elif query.is_unread is False:
            parts.append("isRead:true")
        if query.label:
            parts.append(f"category:{query.label}")
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
        """Search all mail folders and return normalised metadata results.

        Searches across **all folders** (Inbox, Sent, Archive, Drafts, and
        custom folders) via the root mailbox message collection
        (``/me/messages``).

        Query path selection:

        1. ``raw_query`` set → KQL passthrough via ``$search``
        2. ``query.text`` set → ``$search`` with KQL built from all fields
        3. No free-text → ``$filter`` with OData conditions

        Args:
            query: Provider-agnostic search parameters.

        Returns:
            List of :class:`EmailData` dicts (body absent — metadata only).
        """
        if query.raw_query:
            # Raw KQL passthrough.
            q = self._mb.new_query().search(query.raw_query)
            messages = self._mb.get_messages(query=q, limit=query.max_results)
        elif query.text:
            # Free-text present — must use $search; cannot combine with $filter.
            kql = self._build_outlook_search(query)
            q = self._mb.new_query().search(kql)
            messages = self._mb.get_messages(query=q, limit=query.max_results)
        else:
            # Structured filters only — use $filter path.
            q = self._build_outlook_filter(query)
            messages = self._mb.get_messages(query=q, limit=query.max_results)

        return [self._message_to_email_data(msg, include_body=False) for msg in messages]

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

        Searches across **all folders** so that thread replies in Sent Items or
        other folders are included alongside Inbox messages.  Filters by
        ``conversationId`` using the ``$filter`` path via the root mailbox
        message collection (``/me/messages``).

        Args:
            thread_id: The Outlook ``conversationId`` (maps to ``thread_id``
                in :class:`EmailData`).

        Returns:
            List of :class:`EmailData` dicts ordered by ``receivedDateTime``.
        """
        q = self._mb.new_query().on_attribute("conversationId").equals(thread_id)
        messages = self._mb.get_messages(query=q, order_by="receivedDateTime asc")
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
                return bytes(attachment.content)  # type: ignore[arg-type]

        raise ValueError(f"Attachment {attachment_id!r} not found in message {message_id!r}")

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
        for path in attachments or []:
            msg.attachments.add(path)
        if not msg.send():
            raise RuntimeError(f"Failed to send message: {msg.object_id!r}")
        return {"message_id": msg.object_id, "status": "sent"}

    def forward_message(self, message_id: str, to: str, comment: str | None = None) -> dict:
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
        if not fwd.send():
            raise RuntimeError(f"Failed to forward message: {fwd.object_id!r}")
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
        if not msg.save_draft():
            raise RuntimeError(f"Failed to save draft: {msg.object_id!r}")
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
        if not msg.send():
            raise RuntimeError(f"Failed to send draft: {draft_id!r}")
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
        if not msg.delete():
            raise RuntimeError(f"Failed to delete draft: {draft_id!r}")
        return {"message_id": draft_id, "status": "deleted"}

    # ------------------------------------------------------------------
    # Internal batch helper
    # ------------------------------------------------------------------

    def _batch_graph_requests(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Send multiple Graph API requests using the ``$batch`` endpoint.

        Microsoft Graph's ``$batch`` endpoint accepts at most 20 individual
        requests per call.  This helper transparently chunks larger lists
        and returns all individual responses in order.

        Each element of *requests* should be a dict matching the Graph batch
        request format::

            {
                "id": "1",
                "method": "PATCH",
                "url": "/me/messages/{id}",
                "body": { ... },
                "headers": {"Content-Type": "application/json"},
            }

        Args:
            requests: List of individual Graph batch request dicts.

        Returns:
            Flat list of response dicts (``{"id", "status", "body"}``),
            one per input request.
        """
        _BATCH_LIMIT = 20
        con = self._acct.con
        all_responses: list[dict[str, Any]] = []

        for start in range(0, len(requests), _BATCH_LIMIT):
            chunk = requests[start : start + _BATCH_LIMIT]
            payload = {"requests": chunk}
            resp = con.post(
                f"{con.protocol.service_url}/$batch",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp and hasattr(resp, "json"):
                body = resp.json()
                all_responses.extend(body.get("responses", []))
            else:
                logger.warning("Batch request returned no response for chunk starting at %d", start)

        return all_responses

    # ------------------------------------------------------------------
    # 4. System operations (mark read, star, archive, trash)
    # ------------------------------------------------------------------

    def _get_message_or_raise(self, message_id: str) -> Any:
        """Fetch a message by ID, raising ``ValueError`` if not found."""
        msg = self._mb.get_message(object_id=message_id)
        if msg is None:
            raise ValueError(f"Message not found: {message_id!r}")
        return msg

    def mark_read(self, message_id: str, read: bool = True) -> None:
        """Toggle the ``isRead`` property on a message.

        Args:
            message_id: Immutable Graph message ID.
            read: ``True`` to mark as read (default), ``False`` for unread.
        """
        msg = self._get_message_or_raise(message_id)
        if read:
            msg.mark_as_read()
        else:
            msg.mark_as_unread()

    def set_star(self, message_id: str, starred: bool = True) -> None:
        """Toggle the follow-up flag (Outlook's equivalent of Gmail's star).

        Maps ``starred=True`` → ``flag.flagStatus = "flagged"`` and
        ``starred=False`` → ``flag.flagStatus = "notFlagged"``.

        Args:
            message_id: Immutable Graph message ID.
            starred: ``True`` to flag (default), ``False`` to unflag.
        """
        msg = self._get_message_or_raise(message_id)
        status = "flagged" if starred else "notFlagged"
        msg.flag = {"flagStatus": status}
        msg.save_message()

    def archive(self, message_id: str) -> None:
        """Move a message to the Archive well-known folder.

        Args:
            message_id: Immutable Graph message ID.
        """
        msg = self._get_message_or_raise(message_id)
        archive_folder = self._mb.archive_folder()
        msg.move(archive_folder)

    def trash(self, message_id: str) -> None:
        """Soft-delete a message (move to Deleted Items).

        python-o365's ``Message.delete()`` performs a soft delete,
        moving the message to the Deleted Items folder.

        Args:
            message_id: Immutable Graph message ID.
        """
        msg = self._get_message_or_raise(message_id)
        msg.delete()

    def untrash(self, message_id: str) -> None:
        """Restore a message from Deleted Items back to Inbox.

        Args:
            message_id: Immutable Graph message ID.
        """
        msg = self._get_message_or_raise(message_id)
        inbox_folder = self._mb.inbox_folder()
        msg.move(inbox_folder)

    # ------------------------------------------------------------------
    # 5. Tag operations (Outlook categories)
    # ------------------------------------------------------------------

    def add_tag(self, message_id: str, tag_name: str) -> None:
        """Append a category to the message's ``categories`` array.

        No-op if the category is already present.

        Args:
            message_id: Immutable Graph message ID.
            tag_name: Category name to add.
        """
        msg = self._get_message_or_raise(message_id)
        categories: list[str] = list(msg.categories) if msg.categories else []
        if tag_name not in categories:
            categories.append(tag_name)
            msg.categories = categories
            msg.save_message()

    def remove_tag(self, message_id: str, tag_name: str) -> None:
        """Remove a category from the message's ``categories`` array.

        No-op if the category is not present.

        Args:
            message_id: Immutable Graph message ID.
            tag_name: Category name to remove.
        """
        msg = self._get_message_or_raise(message_id)
        categories: list[str] = list(msg.categories) if msg.categories else []
        if tag_name in categories:
            categories.remove(tag_name)
            msg.categories = categories
            msg.save_message()

    def list_tags(self) -> dict[str, str]:
        """Return the master category list as a ``{name: name}`` mapping.

        Outlook categories are identified by display name (not ID), so
        both key and value are the category name.

        Returns:
            Dict mapping category name → category name.
        """
        con = self._acct.con
        url = f"{con.protocol.service_url}/me/outlook/masterCategories"
        resp = con.get(url)
        result: dict[str, str] = {}
        if resp and hasattr(resp, "json"):
            data = resp.json()
            for cat in data.get("value", []):
                name = cat.get("displayName", "")
                if name:
                    result[name] = name
        return result

    # ------------------------------------------------------------------
    # 6. Sync — delta query for incremental sync
    # ------------------------------------------------------------------

    # Default folder used for delta sync.
    _DELTA_FOLDER = "inbox"

    def _get_inbox_delta_url(self) -> str:
        """Return the initial delta URL for the inbox folder."""
        con = self._acct.con
        return f"{con.protocol.service_url}/me/mailFolders/inbox/messages/delta"

    def get_sync_state(self) -> str:
        """Return an opaque sync-state token for the Outlook inbox.

        Performs an initial delta query that walks all pages until the
        ``@odata.deltaLink`` is returned, then returns that link as the
        sync token.  Callers should persist this and pass it to
        :meth:`get_new_messages` for subsequent incremental syncs.

        Returns:
            The ``@odata.deltaLink`` URL (an opaque token string).
        """
        con = self._acct.con
        url = self._get_inbox_delta_url()
        # Walk all pages to exhaust the initial snapshot.
        delta_link = self._exhaust_delta_pages(con, url)
        return delta_link

    def get_new_messages(self, sync_token: str) -> list[str] | None:
        """Return message IDs added/changed since *sync_token*.

        *sync_token* is a ``@odata.deltaLink`` URL previously returned by
        :meth:`get_sync_state` or a prior call to this method.

        Returns:
            A list of message IDs (may be empty), or ``None`` when the
            delta token has expired (HTTP 410 Gone) and a full re-sync is
            needed.  The caller should discard the old token and call
            :meth:`get_sync_state` again to obtain a fresh baseline.
        """
        con = self._acct.con

        try:
            message_ids, _new_delta = self._fetch_delta(con, sync_token)
            return message_ids
        except _DeltaGoneError:
            # 410 Gone — delta token expired; signal full re-sync.
            logger.warning("Outlook delta token expired (410 Gone). A full re-sync is required.")
            return None

    def get_new_messages_with_token(self, sync_token: str) -> tuple[list[str], str] | None:
        """Like :meth:`get_new_messages` but also returns the refreshed delta link.

        Returns:
            A ``(message_ids, new_delta_link)`` tuple, or ``None`` when the
            delta token has expired and a full re-sync is needed.
        """
        con = self._acct.con
        try:
            return self._fetch_delta(con, sync_token)
        except _DeltaGoneError:
            logger.warning("Outlook delta token expired (410 Gone). A full re-sync is required.")
            return None

    # ---- internal delta helpers ----------------------------------------

    def _fetch_delta(self, con: Any, url: str) -> tuple[list[str], str]:
        """Follow delta pages starting at *url*, collecting message IDs.

        Args:
            con: The authenticated ``Connection`` from the O365 account.
            url: Either a ``@odata.deltaLink`` (incremental) or the initial
                delta endpoint URL.

        Returns:
            ``(message_ids, delta_link)`` where ``delta_link`` is the new
            ``@odata.deltaLink`` for the next sync round.

        Raises:
            _DeltaGoneError: If the server returns HTTP 410 (token expired).
        """
        message_ids: list[str] = []
        delta_link = self._exhaust_delta_pages(con, url, message_ids)
        return message_ids, delta_link

    def _exhaust_delta_pages(self, con: Any, url: str, message_ids: list[str] | None = None) -> str:
        """Walk all delta response pages and return the final deltaLink.

        Args:
            con: Authenticated connection.
            url: Starting URL (initial delta URL or a deltaLink).
            message_ids: If provided, message IDs from each page are appended
                into this list (mutated in place).

        Returns:
            The ``@odata.deltaLink`` from the last page.

        Raises:
            _DeltaGoneError: On HTTP 410.
            RuntimeError: If no ``@odata.deltaLink`` is found after paging.
        """
        current_url = url
        while True:
            resp = con.get(current_url, headers=_IMMUTABLE_ID_HEADER)

            # Handle 410 Gone — delta token expired.
            if hasattr(resp, "status_code") and resp.status_code == 410:
                raise _DeltaGoneError("Delta token expired (HTTP 410 Gone)")

            if resp is None or not hasattr(resp, "json"):
                raise RuntimeError("Delta request returned no valid response")

            data = resp.json()

            # Collect message IDs from this page.
            if message_ids is not None:
                for item in data.get("value", []):
                    mid = item.get("id")
                    if mid:
                        message_ids.append(mid)

            # Check for next page or final delta link.
            next_link = data.get("@odata.nextLink")
            delta_link = data.get("@odata.deltaLink")

            if delta_link:
                return delta_link
            elif next_link:
                current_url = next_link
            else:
                raise RuntimeError(
                    "Delta response contained neither @odata.nextLink nor @odata.deltaLink"
                )


class _DeltaGoneError(Exception):
    """Internal exception raised when Graph returns 410 for an expired delta token."""
