"""
GoogleCalendarProvider — read-only CalendarProvider backed by Google Calendar API v3.

Shares OAuth tokens with GmailProvider for the same account via GoogleAuth.
Uses service injection (_service_fn=) for testability without patching build().
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from googleapiclient.errors import HttpError

from iobox.providers.base import AttendeeInfo, CalendarProvider, Event, EventQuery
from iobox.providers.google.auth import GoogleAuth

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CalendarSyncTokenExpiredError(Exception):
    """The calendar sync token is no longer valid (HTTP 410 GONE).

    The caller must discard its stored token, call
    :meth:`GoogleCalendarProvider.get_sync_state` for a fresh one and do a
    full resync.
    """


def _http_status(exc: Exception) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_date_only(value: str) -> bool:
    return bool(_DATE_ONLY_RE.match(value.strip()))


def _parse_local_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime; offset-less values are taken as local time.

    ``naive.astimezone()`` applies the machine's timezone rules for that
    instant, so DST is handled for dates on either side of a transition.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date/time {value!r}: expected YYYY-MM-DD or ISO 8601 datetime"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _local_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day).astimezone()


def _to_rfc3339(value: str, *, end: bool = False) -> str:
    """Convert a query bound to an RFC 3339 timestamp with an explicit offset.

    * ``YYYY-MM-DD`` → local midnight at the start of that day; with
      ``end=True`` the bound is inclusive, i.e. local midnight at the start of
      the *next* day.
    * A datetime without an offset is interpreted in the local timezone.
    * A datetime with an offset (or ``Z``) is kept as that instant.
    """
    if _is_date_only(value):
        d = date.fromisoformat(value.strip())
        if end:
            d += timedelta(days=1)
        return _local_midnight(d).isoformat()
    return _parse_local_datetime(value).isoformat()


def _event_time(value: str, all_day: bool) -> dict[str, Any]:
    """Build a Google ``start``/``end`` object from a normalised time string.

    The opposite key is set to ``None`` so a PATCH that switches an event
    between timed and all-day clears the stale field.
    """
    if all_day or _is_date_only(value):
        return {"date": value.strip()[:10], "dateTime": None}
    return {"dateTime": _parse_local_datetime(value).isoformat(), "date": None}


class GoogleCalendarProvider(CalendarProvider):
    """Read-only CalendarProvider for Google Calendar API v3."""

    SCOPES_READONLY: list[str] = ["https://www.googleapis.com/auth/calendar.readonly"]
    PROVIDER_ID: str = "google_calendar"

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        account: str = "default",
        credentials_dir: str | None = None,
        mode: str = "readonly",
    ) -> None:
        if auth is not None:
            self._auth = auth
        else:
            from iobox.modes import _tier_for_mode, get_google_scopes

            scopes = get_google_scopes(["calendar"], mode)
            tier = _tier_for_mode(mode)
            self._auth = GoogleAuth(
                account=account,
                scopes=scopes,
                credentials_dir=credentials_dir,
                tier=tier,
            )
        self._service: Any = None
        self.mode = mode

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        """Trigger OAuth or token refresh as needed."""
        self._auth.get_credentials()

    def get_profile(self, *, _service_fn: Any | None = None) -> dict[str, Any]:
        """Return primary calendar info: email and display name."""
        svc = _service_fn or self._get_service()
        result = svc.calendarList().get(calendarId="primary").execute()
        return {
            "email": result.get("id"),
            "display_name": result.get("summary"),
        }

    def _get_service(self) -> Any:
        if self._service is None:
            self._service = self._auth.get_service("calendar", "v3")
        return self._service

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_events(self, query: EventQuery, *, _service_fn: Any | None = None) -> list[Event]:
        """Return events matching query, sorted by start time ascending."""
        svc = _service_fn or self._get_service()
        params: dict[str, Any] = {
            "calendarId": query.calendar_id,
            "maxResults": min(query.max_results, 250),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query.text:
            params["q"] = query.text
        if query.after:
            params["timeMin"] = _to_rfc3339(query.after)
        if query.before:
            # A date-only ``before`` is inclusive of that whole (local) day.
            params["timeMax"] = _to_rfc3339(query.before, end=True)

        events: list[Event] = []
        page_token: str | None = None
        while len(events) < query.max_results:
            if page_token:
                params["pageToken"] = page_token
            resp = svc.events().list(**params).execute()
            for item in resp.get("items", []):
                events.append(self._google_event_to_event(item))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return events[: query.max_results]

    def get_event(
        self,
        event_id: str,
        *,
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> Event:
        """Return a single event by ID. Raises ``KeyError`` if not found."""
        svc = _service_fn or self._get_service()
        raw = self._execute_for_event(
            svc.events().get(calendarId=calendar_id, eventId=event_id), event_id
        )
        return self._google_event_to_event(raw)

    @staticmethod
    def _execute_for_event(request: Any, event_id: str) -> Any:
        """Execute a single-event request, mapping 404/410 to ``KeyError``."""
        try:
            return request.execute()
        except HttpError as exc:
            if _http_status(exc) in (404, 410):
                raise KeyError(f"Event not found: {event_id}") from exc
            raise

    # ── Sync ──────────────────────────────────────────────────────────────────

    def get_sync_state(
        self, *, calendar_id: str = "primary", _service_fn: Any | None = None
    ) -> dict[str, Any]:
        """Return a sync token for the calendar's current state.

        Google only issues ``nextSyncToken`` on the *last* page of a full
        listing, so this pages through ``events.list`` (only requesting the
        paging/sync fields) until the token appears.
        """
        svc = _service_fn or self._get_service()
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "showDeleted": True,
            "maxResults": 2500,
            "fields": "nextPageToken,nextSyncToken",
        }
        while True:
            resp = svc.events().list(**params).execute()
            token = resp.get("nextSyncToken")
            if token:
                return {"sync_token": token}
            page_token = resp.get("nextPageToken")
            if not page_token:
                return {"sync_token": ""}
            params["pageToken"] = page_token

    def get_new_events(
        self,
        sync_token: str,
        *,
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> tuple[list[Event], str]:
        """Return ``(changed_events, next_sync_token)`` since ``sync_token``.

        Follows every page of the incremental listing. Deleted events are
        included with ``status == "cancelled"``.

        Raises:
            CalendarSyncTokenExpiredError: the token has expired (HTTP 410);
                a full resync is needed.
        """
        svc = _service_fn or self._get_service()
        params: dict[str, Any] = {"calendarId": calendar_id, "syncToken": sync_token}
        events: list[Event] = []
        while True:
            try:
                resp = svc.events().list(**params).execute()
            except HttpError as exc:
                if _http_status(exc) == 410:
                    raise CalendarSyncTokenExpiredError(
                        "Calendar sync token expired; a full resync is required."
                    ) from exc
                raise
            events.extend(self._google_event_to_event(item) for item in resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if page_token:
                params["pageToken"] = page_token
                continue
            return events, resp.get("nextSyncToken", sync_token)

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
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> Event:
        """Create a new calendar event.

        Timed events: ``start``/``end`` without a UTC offset are interpreted in
        the local timezone and sent as RFC 3339 with that offset. All-day
        events use the ``YYYY-MM-DD`` prefix of ``start``/``end``.
        """
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        if all_day:
            start_dict: dict[str, str] = {"date": start[:10]}
            end_dict: dict[str, str] = {"date": end[:10]}
        else:
            start_dict = {"dateTime": _parse_local_datetime(start).isoformat()}
            end_dict = {"dateTime": _parse_local_datetime(end).isoformat()}
        body: dict[str, Any] = {"summary": title, "start": start_dict, "end": end_dict}
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        result = svc.events().insert(calendarId=calendar_id, body=body).execute()
        return self._google_event_to_event(result)

    _UPDATE_KEYS = frozenset(
        {"title", "start", "end", "all_day", "description", "location", "attendees"}
    )

    def _updates_to_patch_body(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Translate normalised :class:`Event` keys into a Google PATCH body."""
        unknown = set(updates) - self._UPDATE_KEYS
        if unknown:
            raise ValueError(
                f"Unsupported event update field(s): {', '.join(sorted(unknown))}. "
                f"Supported: {', '.join(sorted(self._UPDATE_KEYS))}."
            )
        all_day = bool(updates.get("all_day", False))
        body: dict[str, Any] = {}
        if "title" in updates:
            body["summary"] = updates["title"]
        for key in ("start", "end"):
            if key in updates:
                value = updates[key]
                if not isinstance(value, str):
                    raise ValueError(f"Event '{key}' must be a date/datetime string")
                body[key] = _event_time(value, all_day)
        for key in ("description", "location"):
            if key in updates:
                body[key] = updates[key]
        if "attendees" in updates:
            body["attendees"] = [
                {"email": a} if isinstance(a, str) else {"email": a["email"]}
                for a in updates["attendees"] or []
            ]
        return body

    def update_event(
        self,
        event_id: str,
        updates: dict[str, Any],
        *,
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> Event:
        """Patch an existing event with partial updates.

        ``updates`` uses normalised :class:`Event` keys: ``title``, ``start``,
        ``end`` (``YYYY-MM-DD`` for all-day, else ISO datetime — local time if
        no offset), ``all_day``, ``description``, ``location`` and
        ``attendees`` (list of email strings). Other keys raise ``ValueError``.
        Raises ``KeyError`` if the event does not exist.
        """
        self._check_write_mode()
        body = self._updates_to_patch_body(updates)
        svc = _service_fn or self._get_service()
        result = self._execute_for_event(
            svc.events().patch(calendarId=calendar_id, eventId=event_id, body=body), event_id
        )
        return self._google_event_to_event(result)

    def delete_event(
        self,
        event_id: str,
        *,
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> None:
        """Delete an event. Raises ``KeyError`` if it does not exist."""
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        self._execute_for_event(
            svc.events().delete(calendarId=calendar_id, eventId=event_id), event_id
        )

    def rsvp(
        self,
        event_id: str,
        response: str,
        *,
        calendar_id: str = "primary",
        _service_fn: Any | None = None,
    ) -> Event:
        """Update the authenticated user's RSVP status for an event.

        response: "accepted" | "declined" | "tentative"
        """
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        event_raw = self._execute_for_event(
            svc.events().get(calendarId=calendar_id, eventId=event_id), event_id
        )
        profile = self.get_profile(_service_fn=svc)
        my_email = (profile.get("email") or "").lower()
        raw_attendees: list[dict[str, Any]] = event_raw.get("attendees", [])
        updated = False
        for att in raw_attendees:
            if att.get("email", "").lower() == my_email:
                att["responseStatus"] = response
                updated = True
                break
        if not updated:
            raise ValueError(
                f"Authenticated user '{my_email}' is not an attendee of event '{event_id}'"
            )
        result = self._execute_for_event(
            svc.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body={"attendees": raw_attendees},
            ),
            event_id,
        )
        return self._google_event_to_event(result)

    # ── Normalizer ────────────────────────────────────────────────────────────

    def _google_event_to_event(self, raw: dict[str, Any]) -> Event:
        """Map a Google Calendar API event dict to the Event TypedDict."""
        start_raw = raw.get("start", {})
        end_raw = raw.get("end", {})
        all_day = "date" in start_raw and "dateTime" not in start_raw
        start = start_raw.get("dateTime") or start_raw.get("date", "")
        end = end_raw.get("dateTime") or end_raw.get("date", "")

        attendees: list[AttendeeInfo] = []
        for att in raw.get("attendees", []):
            attendees.append(
                AttendeeInfo(
                    email=att.get("email", ""),
                    name=att.get("displayName"),
                    response_status=att.get("responseStatus"),
                )
            )

        # Meeting URL: hangoutLink takes priority, then conferenceData video entry
        meeting_url: str | None = raw.get("hangoutLink")
        if not meeting_url:
            conf = raw.get("conferenceData", {})
            for ep in conf.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meeting_url = ep.get("uri")
                    break

        organizer_raw = raw.get("organizer", {})
        organizer: str | None = organizer_raw.get("email")

        recurrence: str | None = None
        rec_list = raw.get("recurrence", [])
        if rec_list:
            recurrence = rec_list[0]

        return Event(
            id=raw.get("id", ""),
            provider_id=self.PROVIDER_ID,
            resource_type="event",
            title=raw.get("summary", "(no title)"),
            created_at=raw.get("created", ""),
            modified_at=raw.get("updated", ""),
            url=raw.get("htmlLink"),
            start=start,
            end=end,
            all_day=all_day,
            organizer=organizer,
            attendees=attendees,
            location=raw.get("location"),
            description=raw.get("description"),
            meeting_url=meeting_url,
            status=raw.get("status"),
            recurrence=recurrence,
        )
