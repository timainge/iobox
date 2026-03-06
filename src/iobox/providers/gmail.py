"""
GmailProvider — wraps existing Gmail modules behind the EmailProvider ABC.

All Gmail API interactions are delegated to:
  - iobox.auth            (authentication & profile)
  - iobox.email_search    (search, batch metadata, sync history)
  - iobox.email_retrieval (full content, batch fetch, labels, trash)
  - iobox.email_sender    (compose, send, forward, drafts)

No direct Gmail API calls are made in this file.
"""

from __future__ import annotations

import logging
from typing import Any

from iobox import auth as _auth
from iobox import email_retrieval as _retrieval
from iobox import email_search as _search
from iobox import email_sender as _sender
from iobox.providers.base import AttachmentInfo, EmailData, EmailProvider, EmailQuery

logger = logging.getLogger(__name__)


class GmailProvider(EmailProvider):
    """EmailProvider implementation backed by the existing Gmail modules."""

    def __init__(self) -> None:
        self._service: Any | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _svc(self) -> Any:
        """Return the authenticated Gmail API service, lazily authenticating."""
        if self._service is None:
            self._service = _auth.get_gmail_service()
        return self._service

    def _build_gmail_query(self, query: EmailQuery) -> str:
        """Translate an EmailQuery into a Gmail search query string.

        When ``raw_query`` is set it is returned verbatim so callers can pass
        native Gmail search syntax directly.  Otherwise each populated field is
        converted to the equivalent Gmail operator.

        Date fields (``after`` / ``before``) are *not* included here — they are
        passed as ``start_date`` / ``end_date`` keyword arguments to
        ``email_search.search_emails`` so that the existing date-handling logic
        is reused without duplication.

        Returns:
            Gmail ``q=`` query string (may be empty string).
        """
        if query.raw_query:
            return query.raw_query

        parts: list[str] = []

        if query.text:
            parts.append(query.text)
        if query.from_addr:
            parts.append(f"from:{query.from_addr}")
        if query.to_addr:
            parts.append(f"to:{query.to_addr}")
        if query.subject:
            parts.append(f"subject:{query.subject}")
        if query.has_attachment is True:
            parts.append("has:attachment")
        elif query.has_attachment is False:
            parts.append("-has:attachment")
        if query.is_unread is True:
            parts.append("is:unread")
        elif query.is_unread is False:
            parts.append("is:read")
        if query.label:
            parts.append(f"label:{query.label}")

        return " ".join(parts)

    def _to_email_data(self, raw: dict[str, Any]) -> EmailData:
        """Normalise a Gmail module result dict into an :class:`EmailData` TypedDict.

        Key differences between the raw Gmail dict and :class:`EmailData`:

        * Gmail uses ``"from"`` (a Python keyword); ``EmailData`` uses ``"from_"``.
        * Full-retrieval fields (``body``, ``content_type``, ``attachments``) may
          be absent in search/metadata results — they are only copied when present.

        Args:
            raw: Dict returned by any function in ``email_search`` or
                 ``email_retrieval``.

        Returns:
            Normalised :class:`EmailData` dict.
        """
        data: EmailData = {
            "message_id": raw.get("message_id", ""),
            "subject": raw.get("subject", ""),
            "from_": raw.get("from", raw.get("from_", "")),
            "date": raw.get("date", ""),
            "snippet": raw.get("snippet", ""),
            "labels": list(raw.get("labels", [])),
            "thread_id": raw.get("thread_id", ""),
        }

        # Full-retrieval fields — absent in metadata-only search results.
        if "body" in raw:
            data["body"] = raw["body"]
        if "content_type" in raw:
            data["content_type"] = raw["content_type"]
        if "attachments" in raw:
            data["attachments"] = [
                AttachmentInfo(
                    id=a.get("id", ""),
                    filename=a.get("filename", ""),
                    mime_type=a.get("mime_type", "application/octet-stream"),
                    size=a.get("size", 0),
                )
                for a in raw["attachments"]
            ]

        return data

    # ------------------------------------------------------------------
    # 1. Authentication & profile
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Trigger the OAuth flow (or load cached credentials) immediately."""
        self._service = _auth.get_gmail_service()

    def get_profile(self) -> dict:
        """Return Gmail profile info (emailAddress, messagesTotal, etc.)."""
        return _auth.get_gmail_profile(self._svc)

    # ------------------------------------------------------------------
    # 2. Search & read
    # ------------------------------------------------------------------

    def search_emails(self, query: EmailQuery) -> list[EmailData]:
        """Search Gmail and return normalised metadata results.

        Date range from ``query.after`` / ``query.before`` is forwarded to
        ``email_search.search_emails`` via ``start_date`` / ``end_date``.
        When no ``after`` date is given, a far-past anchor (``2000/01/01``) is
        used so that the function's default 7-day window is bypassed.
        """
        gmail_query = self._build_gmail_query(query)
        label_map = _retrieval.get_label_map(self._svc)

        # Always provide a start_date so email_search doesn't fall back to the
        # 7-day default window.
        start_date = query.after.strftime("%Y/%m/%d") if query.after else "2000/01/01"
        end_date = query.before.strftime("%Y/%m/%d") if query.before else None

        results = _search.search_emails(
            self._svc,
            query=gmail_query,
            max_results=query.max_results,
            start_date=start_date,
            end_date=end_date,
            label_map=label_map,
            include_spam_trash=query.include_spam_trash,
        )
        return [self._to_email_data(r) for r in results]

    def get_email_content(
        self, message_id: str, preferred_content_type: str = "text/plain"
    ) -> EmailData:
        """Retrieve the full content of a single email."""
        label_map = _retrieval.get_label_map(self._svc)
        raw = _retrieval.get_email_content(
            self._svc,
            message_id=message_id,
            preferred_content_type=preferred_content_type,
            label_map=label_map,
        )
        return self._to_email_data(raw)

    def batch_get_emails(
        self, message_ids: list[str], preferred_content_type: str = "text/plain"
    ) -> list[EmailData]:
        """Retrieve full content for multiple emails in batched API requests."""
        label_map = _retrieval.get_label_map(self._svc)
        results = _retrieval.batch_get_emails(
            self._svc,
            message_ids=message_ids,
            preferred_content_type=preferred_content_type,
            label_map=label_map,
        )
        return [self._to_email_data(r) for r in results]

    def get_thread(self, thread_id: str) -> list[EmailData]:
        """Return all messages in a thread, ordered chronologically."""
        results = _retrieval.get_thread_content(self._svc, thread_id=thread_id)
        return [self._to_email_data(r) for r in results]

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download a single attachment and return its raw bytes."""
        return _retrieval.download_attachment(self._svc, message_id, attachment_id)

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
        """Compose and immediately send an email."""
        message = _sender.compose_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
            attachments=attachments,
        )
        return _sender.send_message(self._svc, message)

    def forward_message(
        self, message_id: str, to: str, comment: str | None = None
    ) -> dict:
        """Retrieve an existing email and forward it to ``to``."""
        return _sender.forward_email(
            self._svc,
            message_id=message_id,
            to=to,
            additional_text=comment,
        )

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
    ) -> dict:
        """Compose a message and save it as a draft."""
        message = _sender.compose_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            content_type=content_type,
        )
        return _sender.create_draft(self._svc, message)

    def list_drafts(self, max_results: int = 10) -> list[dict]:
        """Return a list of draft summaries (id, subject, snippet)."""
        return _sender.list_drafts(self._svc, max_results=max_results)

    def send_draft(self, draft_id: str) -> dict:
        """Send an existing draft."""
        return _sender.send_draft(self._svc, draft_id)

    def delete_draft(self, draft_id: str) -> dict:
        """Permanently delete a draft."""
        return _sender.delete_draft(self._svc, draft_id)

    # ------------------------------------------------------------------
    # 4. System operations
    # ------------------------------------------------------------------

    def mark_read(self, message_id: str, read: bool = True) -> None:
        """Mark a message as read or unread."""
        if read:
            _retrieval.modify_message_labels(
                self._svc, message_id, remove_labels=["UNREAD"]
            )
        else:
            _retrieval.modify_message_labels(
                self._svc, message_id, add_labels=["UNREAD"]
            )

    def set_star(self, message_id: str, starred: bool = True) -> None:
        """Add or remove the STARRED label."""
        if starred:
            _retrieval.modify_message_labels(
                self._svc, message_id, add_labels=["STARRED"]
            )
        else:
            _retrieval.modify_message_labels(
                self._svc, message_id, remove_labels=["STARRED"]
            )

    def archive(self, message_id: str) -> None:
        """Archive a message by removing the INBOX label."""
        _retrieval.modify_message_labels(
            self._svc, message_id, remove_labels=["INBOX"]
        )

    def trash(self, message_id: str) -> None:
        """Move a message to Trash."""
        _retrieval.trash_message(self._svc, message_id)

    def untrash(self, message_id: str) -> None:
        """Restore a message from Trash."""
        _retrieval.untrash_message(self._svc, message_id)

    # ------------------------------------------------------------------
    # 5. Tag operations (Gmail labels)
    # ------------------------------------------------------------------

    def add_tag(self, message_id: str, tag_name: str) -> None:
        """Apply a label (tag) to a message, resolving the name to a label ID."""
        label_id = _retrieval.resolve_label_name(self._svc, tag_name)
        _retrieval.modify_message_labels(
            self._svc, message_id, add_labels=[label_id]
        )

    def remove_tag(self, message_id: str, tag_name: str) -> None:
        """Remove a label (tag) from a message."""
        label_id = _retrieval.resolve_label_name(self._svc, tag_name)
        _retrieval.modify_message_labels(
            self._svc, message_id, remove_labels=[label_id]
        )

    def list_tags(self) -> dict[str, str]:
        """Return the full label ID → name mapping for the authenticated account."""
        return _retrieval.get_label_map(self._svc)

    # ------------------------------------------------------------------
    # 6. Sync
    # ------------------------------------------------------------------

    def get_sync_state(self) -> str:
        """Return the current Gmail ``historyId`` as an opaque sync-state token."""
        profile = _auth.get_gmail_profile(self._svc)
        return str(profile.get("historyId", ""))

    def get_new_messages(self, sync_token: str) -> list[str] | None:
        """Return message IDs added since ``sync_token`` (a Gmail historyId).

        Returns ``None`` when the history has expired and a full re-sync is needed.
        """
        return _search.get_new_messages(self._svc, sync_token)
