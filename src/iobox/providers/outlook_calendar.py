"""
OutlookCalendarProvider — read-only CalendarProvider backed by python-o365.

Uses the same O365 Account object as OutlookProvider for the same account.
O365 is an optional dependency; this module raises ImportError with a clear
message if the package is not installed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from iobox.providers.base import AttendeeInfo, CalendarProvider, Event, EventQuery

try:
    from O365 import Account as _O365Account  # noqa: F401

    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace for event descriptions."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class OutlookCalendarProvider(CalendarProvider):
    """Read-only CalendarProvider for Microsoft 365 via python-o365."""

    PROVIDER_ID: str = "outlook_calendar"

    def __init__(
        self,
        account_email: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
        auth: Any | None = None,
    ) -> None:
        if not HAS_O365:
            raise ImportError(
                "O365 package required for Outlook support. "
                "Install with: pip install 'iobox[outlook]'"
            )
        self.account_email = account_email
        self.credentials_dir = credentials_dir
        self.mode = mode
        self._microsoft_auth: Any | None = auth
        self._account: Any = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        self._get_account()

    def get_profile(self) -> dict[str, Any]:
        """Return account info: email and display name."""
        account = self._get_account()
        # O365 Account doesn't have a direct profile call — use account_email
        return {
            "email": self.account_email,
            "display_name": getattr(account, "main_resource", self.account_email),
        }

    def _get_account(self) -> Any:
        if self._account is None:
            if self._microsoft_auth is not None:
                self._account = self._microsoft_auth.get_account()
            else:
                from iobox.providers.outlook_auth import get_outlook_account

                self._account = get_outlook_account(account=self.account_email)
        return self._account

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_events(self, query: EventQuery) -> list[Event]:
        """Return events matching query."""
        account = self._get_account()
        schedule = account.schedule()
        calendar = schedule.get_default_calendar()

        kwargs: dict[str, Any] = {
            "limit": query.max_results,
            "include_recurring": True,
        }
        if query.after:
            kwargs["start"] = datetime.fromisoformat(query.after)
        if query.before:
            kwargs["end"] = datetime.fromisoformat(query.before)

        if query.text:
            try:
                raw_events = list(schedule.search_events(query=query.text, limit=query.max_results))
            except Exception:
                logger.debug("search_events failed, falling back to get_events")
                raw_events = list(calendar.get_events(**kwargs))
        else:
            raw_events = list(calendar.get_events(**kwargs))

        return [self._o365_event_to_event(e) for e in raw_events]

    def get_event(self, event_id: str) -> Event:
        """Return a single event by ID."""
        account = self._get_account()
        schedule = account.schedule()
        ev = schedule.get_event(object_id=event_id)
        if ev is None:
            raise KeyError(f"Event '{event_id}' not found")
        return self._o365_event_to_event(ev)

    # ── Sync stubs ────────────────────────────────────────────────────────────

    def get_sync_state(self) -> dict[str, Any]:
        """Return empty sync state — O365 incremental sync is complex (stub)."""
        return {}

    def get_new_events(self, sync_token: str) -> tuple[list[Event], str]:
        """Stub — O365 incremental event sync not implemented for MVP."""
        return [], sync_token

    # ── Write ─────────────────────────────────────────────────────────────────

    def _check_write_mode(self) -> None:
        if self.mode == "readonly":
            raise PermissionError("Calendar write operations require mode='standard'.")

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
        """Create a new calendar event on the default calendar."""
        self._check_write_mode()
        calendar = self._get_account().schedule().get_default_calendar()
        event = calendar.new_event()
        event.subject = title
        event.start = datetime.fromisoformat(start)
        event.end = datetime.fromisoformat(end)
        event.is_all_day = all_day
        if description:
            event.body = description
        if location:
            event.location = location
        if attendees:
            for email in attendees:
                event.attendees.add(email)
        event.save()
        return self._o365_event_to_event(event)

    def update_event(self, event_id: str, updates: dict[str, Any]) -> Event:
        """Update an event — MVP stub: loads event and saves it back.

        For a full implementation, map ``updates`` keys to O365 event attributes.
        """
        self._check_write_mode()
        ev = self._get_account().schedule().get_event(object_id=event_id)
        if ev is None:
            raise KeyError(f"Event '{event_id}' not found")
        for key, value in updates.items():
            if hasattr(ev, key):
                setattr(ev, key, value)
        ev.save()
        return self._o365_event_to_event(ev)

    def delete_event(self, event_id: str) -> None:
        """Delete an event from the calendar."""
        self._check_write_mode()
        ev = self._get_account().schedule().get_event(object_id=event_id)
        if ev is not None:
            ev.delete()

    def rsvp(self, event_id: str, response: str) -> Event:
        """Respond to a calendar invite.

        response: "accepted" | "declined" | "tentative"
        """
        self._check_write_mode()
        ev = self._get_account().schedule().get_event(object_id=event_id)
        if ev is None:
            raise KeyError(f"Event '{event_id}' not found")
        if response == "accepted":
            ev.accept()
        elif response == "declined":
            ev.decline()
        elif response == "tentative":
            ev.tentatively_accept()
        else:
            raise ValueError(
                f"Unknown RSVP response: {response!r}. Use accepted/declined/tentative"
            )
        return self._o365_event_to_event(ev)

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _o365_event_to_event(self, ev: Any) -> Event:
        """Map a python-o365 Event object to the Event TypedDict."""
        title: str = getattr(ev, "subject", "") or "(no title)"

        start_obj = getattr(ev, "start", None)
        end_obj = getattr(ev, "end", None)
        all_day: bool = bool(getattr(ev, "is_all_day", False))

        if all_day:
            start = str(start_obj.date()) if start_obj else ""
            end = str(end_obj.date()) if end_obj else ""
        else:
            start = start_obj.isoformat() if start_obj else ""
            end = end_obj.isoformat() if end_obj else ""

        # Attendees
        attendees: list[AttendeeInfo] = []
        for att in getattr(ev, "attendees", None) or []:
            rs = getattr(att, "response_status", None)
            rs_value = str(getattr(rs, "value", "")) if rs is not None else None
            attendees.append(
                AttendeeInfo(
                    email=getattr(att, "address", "") or "",
                    name=getattr(att, "name", None),
                    response_status=rs_value or None,
                )
            )

        # Organizer
        organizer_obj = getattr(ev, "organizer", None)
        organizer: str | None = getattr(organizer_obj, "address", None) if organizer_obj else None

        # Meeting URL — prefer explicit field, then scan body for Teams URL
        meeting_url: str | None = getattr(ev, "online_meeting_url", None)
        if not meeting_url:
            body_content: str = getattr(getattr(ev, "body", None), "content", "") or ""
            if "teams.microsoft.com" in body_content:
                m = re.search(r"https://teams\.microsoft\.com/[^\s\"'<>]+", body_content)
                if m:
                    meeting_url = m.group(0)

        # Description — strip HTML from body
        raw_body: str = getattr(getattr(ev, "body", None), "content", "") or ""
        description: str | None = _strip_html(raw_body) or None

        # Location
        location_obj = getattr(ev, "location", None)
        location: str | None = getattr(location_obj, "display_name", None) if location_obj else None

        created = getattr(ev, "created", None)
        modified = getattr(ev, "modified", None)

        return Event(
            id=str(getattr(ev, "object_id", "") or ""),
            provider_id=self.PROVIDER_ID,
            resource_type="event",
            title=title,
            created_at=created.isoformat() if created else "",
            modified_at=modified.isoformat() if modified else "",
            url=getattr(ev, "web_link", None),
            start=start,
            end=end,
            all_day=all_day,
            organizer=organizer,
            attendees=attendees,
            location=location,
            description=description,
            meeting_url=meeting_url,
            status="confirmed",
            recurrence=None,
        )
