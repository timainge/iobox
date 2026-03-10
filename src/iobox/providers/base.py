"""
Provider abstraction layer for iobox.

Defines the EmailProvider ABC, EmailQuery dataclass, and EmailData TypedDict
that all provider implementations must satisfy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, TypedDict


class AttachmentInfo(TypedDict):
    id: str
    filename: str
    mime_type: str
    size: int


class EmailMetadata(TypedDict):
    """Fields always present in every EmailData dict."""

    message_id: str
    subject: str
    from_: str  # "Display Name <email>" format
    date: str
    snippet: str
    labels: list[str]  # Gmail labels or Outlook categories
    thread_id: str  # Gmail threadId or Outlook conversationId


class EmailData(EmailMetadata, total=False):
    """Full email data — optional fields present only after content retrieval."""

    body: str
    content_type: str  # 'text/plain' or 'text/html'
    attachments: list[AttachmentInfo]


@dataclass
class EmailQuery:
    """Provider-agnostic search query.

    Each provider translates this into its native query format.
    Set 'raw_query' to bypass translation and pass provider-native
    syntax directly (Gmail search syntax or OData/KQL).
    """

    text: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    subject: str | None = None
    after: date | None = None
    before: date | None = None
    has_attachment: bool | None = None
    is_unread: bool | None = None
    label: str | None = None
    max_results: int = 100
    include_spam_trash: bool = False
    raw_query: str | None = None


class EmailProvider(ABC):
    """Abstract interface for email provider backends.

    Methods are grouped into:
    1. Authentication and profile
    2. Search and read
    3. Send, forward, and drafts
    4. System operations (mark_read, star, archive, trash)
    5. Tag operations (add_tag, remove_tag, list_tags)
    6. Sync
    """

    # ── 1. Authentication ─────────────────────────────────────

    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    # ── 2. Search & Read ──────────────────────────────────────

    @abstractmethod
    def search_emails(self, query: EmailQuery) -> list[EmailData]: ...

    @abstractmethod
    def get_email_content(
        self, message_id: str, preferred_content_type: str = "text/plain"
    ) -> EmailData: ...

    @abstractmethod
    def batch_get_emails(
        self, message_ids: list[str], preferred_content_type: str = "text/plain"
    ) -> list[EmailData]: ...

    @abstractmethod
    def get_thread(self, thread_id: str) -> list[EmailData]: ...

    @abstractmethod
    def download_attachment(self, message_id: str, attachment_id: str) -> bytes: ...

    # ── 3. Send, Forward & Drafts ─────────────────────────────

    @abstractmethod
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
        attachments: list[str] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def forward_message(
        self, message_id: str, to: str, comment: str | None = None
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def list_drafts(self, max_results: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    def send_draft(self, draft_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def delete_draft(self, draft_id: str) -> dict[str, Any]: ...

    # ── 4. System Operations ──────────────────────────────────
    # Dedicated methods for operations that map differently across
    # providers. Gmail uses label add/remove; Outlook uses property
    # patches and folder moves.

    @abstractmethod
    def mark_read(self, message_id: str, read: bool = True) -> None: ...

    @abstractmethod
    def set_star(self, message_id: str, starred: bool = True) -> None: ...

    @abstractmethod
    def archive(self, message_id: str) -> None: ...

    @abstractmethod
    def trash(self, message_id: str) -> None: ...

    @abstractmethod
    def untrash(self, message_id: str) -> None: ...

    # ── 5. Tag Operations ─────────────────────────────────────
    # Gmail custom labels / Outlook categories.

    @abstractmethod
    def add_tag(self, message_id: str, tag_name: str) -> None: ...

    @abstractmethod
    def remove_tag(self, message_id: str, tag_name: str) -> None: ...

    @abstractmethod
    def list_tags(self) -> dict[str, str]: ...

    # ── 7. Batch Operations (optional — loop default) ──────────
    # Non-abstract convenience methods for bulk org operations.
    # Providers may override to use native bulk APIs (e.g. Graph $batch).

    def batch_mark_read(self, message_ids: list[str], read: bool = True) -> None:
        """Mark multiple messages as read or unread.

        Default implementation calls :meth:`mark_read` for each message.
        Providers may override for more efficient bulk operations.

        Args:
            message_ids: List of message IDs to update.
            read: ``True`` to mark as read (default), ``False`` for unread.
        """
        for message_id in message_ids:
            self.mark_read(message_id, read=read)

    def batch_archive(self, message_ids: list[str]) -> None:
        """Archive multiple messages.

        Default implementation calls :meth:`archive` for each message.
        Providers may override for more efficient bulk operations.

        Args:
            message_ids: List of message IDs to archive.
        """
        for message_id in message_ids:
            self.archive(message_id)

    def batch_trash(self, message_ids: list[str]) -> None:
        """Trash multiple messages.

        Default implementation calls :meth:`trash` for each message.
        Providers may override for more efficient bulk operations.

        Args:
            message_ids: List of message IDs to trash.
        """
        for message_id in message_ids:
            self.trash(message_id)

    def batch_add_tag(self, message_ids: list[str], tag_name: str) -> None:
        """Add a tag to multiple messages.

        Default implementation calls :meth:`add_tag` for each message.
        Providers may override for more efficient bulk operations.

        Args:
            message_ids: List of message IDs to tag.
            tag_name: Tag name to add.
        """
        for message_id in message_ids:
            self.add_tag(message_id, tag_name)

    def batch_remove_tag(self, message_ids: list[str], tag_name: str) -> None:
        """Remove a tag from multiple messages.

        Default implementation calls :meth:`remove_tag` for each message.
        Providers may override for more efficient bulk operations.

        Args:
            message_ids: List of message IDs to untag.
            tag_name: Tag name to remove.
        """
        for message_id in message_ids:
            self.remove_tag(message_id, tag_name)

    # ── 6. Sync ───────────────────────────────────────────────

    @abstractmethod
    def get_sync_state(self) -> str: ...

    @abstractmethod
    def get_new_messages(self, sync_token: str) -> list[str] | None: ...

    @abstractmethod
    def get_new_messages_with_token(self, sync_token: str) -> tuple[list[str], str] | None:
        """Like :meth:`get_new_messages` but also returns the refreshed sync token.

        Returns:
            A ``(message_ids, new_sync_token)`` tuple, or ``None`` when the
            sync token has expired and a full re-sync is needed.

        Note:
            Implementations should return the refreshed token so callers can
            persist it for the next incremental sync without a second round-trip.
        """
        ...
