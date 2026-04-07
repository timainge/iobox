"""
Provider abstraction layer for iobox.

Defines the EmailProvider ABC, EmailQuery dataclass, and EmailData TypedDict
that all provider implementations must satisfy.

Also defines the workspace-level resource type hierarchy:
  Resource (base TypedDict)
  ├── Email(Resource)   — email/message
  ├── Event(Resource)   — calendar event
  └── File(Resource)    — drive/storage file

And the CalendarProvider and FileProvider ABCs used by the Workspace layer.
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


# ═══════════════════════════════════════════════════════════════════════════════
# Workspace resource type hierarchy
# ───────────────────────────────────────────────────────────────────────────────
# These types are additive — they do NOT replace EmailData / EmailProvider.
# EmailProvider methods still use EmailData. The Resource/Email/Event/File types
# exist for the Workspace layer where all three resource types are handled
# together (e.g. Workspace.search() returns list[Resource]).
# ═══════════════════════════════════════════════════════════════════════════════


class Resource(TypedDict):
    """Base TypedDict shared by all workspace resource types.

    resource_type values: "email" | "event" | "file"
    """

    id: str
    provider_id: str  # "gmail" | "google_calendar" | "google_drive" | "outlook" | …
    resource_type: str  # discriminant — use to dispatch without isinstance
    title: str  # subject / event name / filename
    created_at: str  # ISO 8601
    modified_at: str  # ISO 8601
    url: str | None  # browser-accessible link, if any


class AttendeeInfo(TypedDict):
    """Calendar event attendee."""

    email: str
    name: str | None
    response_status: str | None  # "accepted" | "declined" | "tentative" | "needsAction"


class Email(Resource):
    """An email message in Resource context (for cross-type Workspace results).

    NOTE: EmailProvider methods return EmailData, not Email. Email is used
    only when emails are mixed with events/files in a unified result list.
    """

    from_: str
    to: list[str]
    cc: list[str]
    thread_id: str | None
    snippet: str | None
    labels: list[str]
    body: str | None
    content_type: str | None  # "text/html" | "text/plain"
    attachments: list[AttachmentInfo]


class Event(Resource):
    """A calendar event."""

    start: str  # ISO 8601 datetime or date (all-day)
    end: str  # ISO 8601 datetime or date
    all_day: bool
    organizer: str | None  # email address
    attendees: list[AttendeeInfo]
    location: str | None
    description: str | None
    meeting_url: str | None
    status: str | None  # "confirmed" | "tentative" | "cancelled"
    recurrence: str | None  # RRULE string, e.g. "RRULE:FREQ=DAILY;BYDAY=MO"


class File(Resource):
    """A file or folder in a cloud storage service."""

    name: str  # filename (not full path)
    mime_type: str
    size: int  # bytes; 0 for Google Workspace files and folders
    path: str | None  # folder path, if available
    parent_id: str | None
    is_folder: bool
    download_url: str | None
    content: str | None  # pre-fetched text content; None means not yet fetched


# ── Query dataclasses ──────────────────────────────────────────────────────────


@dataclass
class ResourceQuery:
    """Base query shared by all resource types."""

    text: str | None = None
    after: str | None = None  # ISO 8601 date string
    before: str | None = None  # ISO 8601 date string
    max_results: int = 25


@dataclass
class EventQuery(ResourceQuery):
    """Query for calendar events."""

    calendar_id: str = "primary"


@dataclass
class FileQuery(ResourceQuery):
    """Query for files and folders."""

    mime_type: str | None = None
    folder_id: str | None = None
    shared_with_me: bool = False


# ── CalendarProvider ABC ───────────────────────────────────────────────────────


class CalendarProvider(ABC):
    """Abstract base for calendar provider backends (read-only initially).

    Implementations: GoogleCalendarProvider, OutlookCalendarProvider.
    """

    @abstractmethod
    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        """Return basic account info: email, display_name."""
        ...

    @abstractmethod
    def list_events(self, query: EventQuery) -> list[Event]:
        """Return events matching query, sorted by start time ascending."""
        ...

    @abstractmethod
    def get_event(self, event_id: str) -> Event:
        """Return a single event by ID. Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_sync_state(self) -> dict[str, Any]:
        """Return provider-specific sync token/cursor for incremental sync."""
        ...

    @abstractmethod
    def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
        """Return (new_events, next_sync_token) since last sync.

        Raises NotImplementedError if the provider does not support incremental sync.
        """
        ...

    @abstractmethod
    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        *,
        all_day: bool = False,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> Event:
        """Create a new calendar event. Returns the created event.

        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def update_event(self, event_id: str, updates: dict[str, Any]) -> Event:
        """Update fields of an existing event. Returns the updated event.

        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def delete_event(self, event_id: str) -> None:
        """Delete an event from the calendar.

        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def rsvp(self, event_id: str, response: str) -> Event:
        """Respond to a calendar invite.

        response: "accepted" | "declined" | "tentative"
        Requires mode='standard'.
        """
        ...


# ── FileProvider ABC ───────────────────────────────────────────────────────────


class FileProvider(ABC):
    """Abstract base for file/storage provider backends (read-only initially).

    Implementations: GoogleDriveProvider, OneDriveProvider.
    """

    @abstractmethod
    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        """Return basic account info: email, display_name."""
        ...

    @abstractmethod
    def list_files(self, query: FileQuery) -> list[File]:
        """Return files matching query."""
        ...

    @abstractmethod
    def get_file(self, file_id: str) -> File:
        """Return file metadata by ID. Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_file_content(self, file_id: str) -> str:
        """Return text content of file.

        Returns empty string for binary files (with a warning log).
        Google Workspace files are exported as text/plain or text/csv.
        """
        ...

    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """Return raw bytes of file."""
        ...

    @abstractmethod
    def upload_file(
        self,
        local_path: str,
        *,
        parent_id: str | None = None,
        name: str | None = None,
    ) -> File:
        """Upload a local file. Returns the created File.

        name overrides the filename; defaults to basename of local_path.
        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def update_file(self, file_id: str, local_path: str) -> File:
        """Replace content of an existing file. Returns the updated File.

        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
        """Move file to trash (default) or permanently delete (permanent=True).

        OneDrive does not support trash — always permanent.
        Requires mode='standard'.
        """
        ...

    @abstractmethod
    def create_folder(
        self,
        name: str,
        *,
        parent_id: str | None = None,
    ) -> File:
        """Create a new folder. Returns File with is_folder=True.

        Requires mode='standard'.
        """
        ...
