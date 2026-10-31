"""
OutlookCalendarProvider — CalendarProvider backed by python-o365.

Uses the same O365 Account object as OutlookProvider for the same account.
O365 is an optional dependency; this module raises ImportError with a clear
message if the package is not installed.

python-o365 2.1 API notes (verified against the source):

* ``Calendar.get_events(include_recurring=True)`` hits ``calendarView`` and
  *requires* ``start_recurring`` and ``end_recurring``; there is no
  ``Schedule.search_events`` (Graph events have no ``$search``), so text
  queries are filtered client-side.
* There is no ``Schedule.get_event``; events are fetched by ID from
  ``/me/events/{id}`` (works for any of the user's calendars).
* RSVP methods are ``Event.accept_event()``, ``Event.decline_event()`` and
  ``Event.accept_event(tentatively=True)``.
* ``Event.location`` is the Graph ``location`` dict, ``Event.body`` a string
  and ``Attendee.response_status`` a ``ResponseStatus`` whose ``status`` is an
  ``EventResponse`` enum (or ``None``).
* ``Event.start``/``end`` setters only accept naive datetimes or ``ZoneInfo``
  aware ones.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from iobox.providers.base import AttendeeInfo, CalendarProvider, Event, EventQuery

try:
    from O365 import Account as _O365Account  # noqa: F401

    HAS_O365 = True
except ImportError:
    HAS_O365 = False

logger = logging.getLogger(__name__)

# When no window is given, list this far ahead of ``after`` (or now).
_DEFAULT_WINDOW = timedelta(days=365)
# Candidates fetched when a text query is filtered client-side.
_TEXT_SEARCH_FETCH = 999

# EventResponse values → the Google-style vocabulary used by AttendeeInfo.
_RESPONSE_STATUS_MAP = {
    "accepted": "accepted",
    "organizer": "accepted",
    "declined": "declined",
    "tentativelyaccepted": "tentative",
    "notresponded": "needsAction",
    "none": "needsAction",
}

# update_event keys (iobox Event vocabulary + common aliases) → handler name.
_UPDATE_FIELDS = {
    "title": "subject",
    "subject": "subject",
    "summary": "subject",
    "start": "start",
    "end": "end",
    "all_day": "all_day",
    "description": "body",
    "body": "body",
    "location": "location",
    "attendees": "attendees",
}


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace for event descriptions."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


class OutlookCalendarProvider(CalendarProvider):
    """CalendarProvider for Microsoft 365 via python-o365."""

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
        """Return account info: email and display name (no network call)."""
        account = self._get_account()
        username = getattr(account, "username", None) or self.account_email
        return {"email": username, "display_name": username}

    def _get_account(self) -> Any:
        if self._account is None:
            from iobox.providers.o365.auth import ensure_immutable_ids

            if self._microsoft_auth is None:
                from iobox.providers.o365.auth import MicrosoftAuth, get_microsoft_scopes

                self._microsoft_auth = MicrosoftAuth(
                    account=self.account_email,
                    scopes=get_microsoft_scopes(["calendar"], self.mode),
                    credentials_dir=self.credentials_dir,
                    mode=self.mode,
                )
            self._account = self._microsoft_auth.get_account()
            ensure_immutable_ids(self._account)
        return self._account

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _to_local_dt(self, value: str | date | datetime, protocol: Any) -> datetime:
        """Parse an ISO date/datetime into something ``Event.start`` accepts.

        Date-only → local midnight; naive → protocol timezone; aware with a
        fixed offset → converted to the protocol's ``ZoneInfo``.
        """
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime(value.year, value.month, value.day)
        else:
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        tz = protocol.timezone
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    def _fetch_event(self, event_id: str) -> Any:
        """GET /me/events/{id} and wrap it in a python-o365 ``Event``.

        Raises:
            KeyError: If the event does not exist.
        """
        schedule = self._get_account().schedule()
        url = schedule.build_url(f"/events/{event_id}")
        try:
            resp = schedule.con.get(url)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 404:
                raise KeyError(f"Event '{event_id}' not found") from exc
            raise
        if not resp:
            raise KeyError(f"Event '{event_id}' not found")
        return schedule.event_constructor(
            parent=schedule, **{schedule._cloud_data_key: resp.json()}
        )

    @staticmethod
    def _matches_text(ev: Any, needle: str) -> bool:
        location = getattr(ev, "location", None)
        loc_name = location.get("displayName", "") if isinstance(location, dict) else location
        organizer = getattr(ev, "organizer", None)
        haystack = " ".join(
            str(x or "")
            for x in (
                getattr(ev, "subject", ""),
                _strip_html(getattr(ev, "body", "") or ""),
                loc_name,
                getattr(organizer, "address", ""),
                getattr(organizer, "name", ""),
            )
        ).lower()
        return all(term in haystack for term in needle.lower().split())

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_events(self, query: EventQuery) -> list[Event]:
        """Return events (recurring occurrences expanded) ordered by start.

        Uses Graph ``calendarView`` on the default calendar, which needs a
        window: ``after`` defaults to now and ``before`` to one year after
        ``after`` (or ``before`` minus one year when only ``before`` is set).
        Graph events have no ``$search``, so ``query.text`` is matched
        client-side against subject, body, location and organizer.
        """
        account = self._get_account()
        protocol = account.protocol
        calendar = account.schedule().get_default_calendar()

        start = self._to_local_dt(query.after, protocol) if query.after else None
        end = self._to_local_dt(query.before, protocol) if query.before else None
        if start is None and end is None:
            start = datetime.now(tz=protocol.timezone)
        if start is None:
            assert end is not None
            start = end - _DEFAULT_WINDOW
        if end is None:
            end = start + _DEFAULT_WINDOW

        limit = _TEXT_SEARCH_FETCH if query.text else query.max_results
        raw_events = calendar.get_events(
            limit=limit,
            include_recurring=True,
            start_recurring=start,
            end_recurring=end,
            order_by="start/dateTime",
        )

        events: list[Event] = []
        for ev in raw_events:
            if query.text and not self._matches_text(ev, query.text):
                continue
            events.append(self._o365_event_to_event(ev))
            if len(events) >= query.max_results:
                break
        return events

    def get_event(self, event_id: str) -> Event:
        """Return a single event by ID (any of the user's calendars)."""
        return self._o365_event_to_event(self._fetch_event(event_id))

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

    def _apply_times(
        self, event: Any, start: Any | None, end: Any | None, all_day: bool | None
    ) -> None:
        protocol = event.protocol
        if start is not None:
            event.start = self._to_local_dt(start, protocol)
        if end is not None:
            event.end = self._to_local_dt(end, protocol)
        if all_day is not None:
            # The setter normalises start/end to midnight (and ≥ 24h apart),
            # so it must run after start/end are assigned.
            event.is_all_day = bool(all_day)

    @staticmethod
    def _set_description(event: Any, description: str | None) -> None:
        event.body_type = "text"
        event.body = description or ""

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
        self._apply_times(event, start, end, all_day if all_day else None)
        if description:
            self._set_description(event, description)
        if location:
            event.location = location
        if attendees:
            event.attendees.add(list(attendees))
        if not event.save():
            raise RuntimeError(f"Failed to create event {title!r}")
        return self._o365_event_to_event(event)

    def update_event(self, event_id: str, updates: dict[str, Any]) -> Event:
        """Patch an event using iobox ``Event`` field names.

        Supported keys: ``title`` (aliases ``subject``/``summary``), ``start``,
        ``end``, ``all_day``, ``description`` (alias ``body``), ``location``
        and ``attendees`` (list of email addresses; replaces the list).

        Raises:
            ValueError: For unsupported keys (nothing is changed).
            KeyError: If the event does not exist.
        """
        self._check_write_mode()
        unknown = sorted(k for k in updates if k not in _UPDATE_FIELDS)
        if unknown:
            raise ValueError(
                f"Unsupported event update field(s): {', '.join(unknown)}. "
                f"Supported: {', '.join(sorted(_UPDATE_FIELDS))}"
            )
        ev = self._fetch_event(event_id)
        fields = {_UPDATE_FIELDS[k]: v for k, v in updates.items()}
        if "subject" in fields:
            ev.subject = fields["subject"] or ""
        if {"start", "end", "all_day"} & fields.keys():
            all_day = fields.get("all_day")
            self._apply_times(
                ev, fields.get("start"), fields.get("end"), None if all_day is None else all_day
            )
        if "body" in fields:
            self._set_description(ev, fields["body"])
        if "location" in fields:
            ev.location = fields["location"] or ""
        if "attendees" in fields:
            ev.attendees.clear()
            if fields["attendees"]:
                ev.attendees.add(list(fields["attendees"]))
        if not ev.save():
            raise RuntimeError(f"Failed to update event {event_id!r}")
        return self._o365_event_to_event(ev)

    def delete_event(self, event_id: str) -> None:
        """Delete an event (no-op with a warning if it does not exist)."""
        self._check_write_mode()
        try:
            ev = self._fetch_event(event_id)
        except KeyError:
            logger.warning("delete_event: event %r not found", event_id)
            return
        if not ev.delete():
            raise RuntimeError(f"Failed to delete event {event_id!r}")

    def rsvp(self, event_id: str, response: str) -> Event:
        """Respond to a calendar invite.

        response: "accepted" | "declined" | "tentative"
        """
        self._check_write_mode()
        if response not in ("accepted", "declined", "tentative"):
            raise ValueError(
                f"Unknown RSVP response: {response!r}. Use accepted/declined/tentative"
            )
        ev = self._fetch_event(event_id)
        if response == "accepted":
            ok = ev.accept_event()
        elif response == "declined":
            ok = ev.decline_event()
        else:
            ok = ev.accept_event(tentatively=True)
        if not ok:
            raise RuntimeError(f"Failed to RSVP {response!r} to event {event_id!r}")
        # Re-read so the returned Event reflects the new response status.
        return self._o365_event_to_event(self._fetch_event(event_id))

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _o365_event_to_event(self, ev: Any) -> Event:
        """Map a python-o365 ``Event`` to the iobox ``Event`` TypedDict."""
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

        attendees: list[AttendeeInfo] = []
        for att in getattr(ev, "attendees", None) or []:
            rs = getattr(att, "response_status", None)
            raw_status = _enum_value(getattr(rs, "status", None)) if rs is not None else ""
            attendees.append(
                AttendeeInfo(
                    email=getattr(att, "address", "") or "",
                    name=getattr(att, "name", None) or None,
                    # EventResponse values are snake_case ("tentatively_accepted").
                    response_status=_RESPONSE_STATUS_MAP.get(raw_status.replace("_", "").lower()),
                )
            )

        organizer_obj = getattr(ev, "organizer", None)
        organizer: str | None = getattr(organizer_obj, "address", None) or None

        raw_body: str = getattr(ev, "body", "") or ""
        body_type = str(getattr(ev, "body_type", "html") or "html").lower()

        meeting_url: str | None = getattr(ev, "online_meeting_url", None)
        if not meeting_url and "teams.microsoft.com" in raw_body:
            m = re.search(r"https://teams\.microsoft\.com/[^\s\"'<>]+", raw_body)
            if m:
                meeting_url = m.group(0)

        description_text = _strip_html(raw_body) if body_type == "html" else raw_body.strip()
        description: str | None = description_text or None

        location_obj = getattr(ev, "location", None)
        if isinstance(location_obj, dict):
            location: str | None = location_obj.get("displayName") or None
        else:
            location = str(location_obj) if location_obj else None

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
            status="cancelled" if getattr(ev, "is_cancelled", False) else "confirmed",
            recurrence=None,
        )
