"""
GoogleCalendarProvider — read-only CalendarProvider backed by Google Calendar API v3.

Shares OAuth tokens with GmailProvider for the same account via GoogleAuth.
Uses service injection (_service_fn=) for testability without patching build().
"""

from __future__ import annotations

from typing import Any

from iobox.providers.base import AttendeeInfo, CalendarProvider, Event, EventQuery
from iobox.providers.google.auth import GoogleAuth


def _to_rfc3339(date_str: str) -> str:
    """Convert YYYY-MM-DD to RFC 3339 (append T00:00:00Z if needed)."""
    if "T" in date_str:
        return date_str
    return f"{date_str}T00:00:00Z"


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
            params["timeMax"] = _to_rfc3339(query.before)

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

    def get_event(self, event_id: str, *, _service_fn: Any | None = None) -> Event:
        """Return a single event by ID."""
        svc = _service_fn or self._get_service()
        raw = svc.events().get(calendarId="primary", eventId=event_id).execute()
        return self._google_event_to_event(raw)

    # ── Sync ──────────────────────────────────────────────────────────────────

    def get_sync_state(self, *, _service_fn: Any | None = None) -> dict[str, Any]:
        """Return a sync token from a minimal full-sync request."""
        svc = _service_fn or self._get_service()
        resp = svc.events().list(calendarId="primary", maxResults=1).execute()
        return {"sync_token": resp.get("nextSyncToken", "")}

    def get_new_events(
        self, sync_token: str, *, _service_fn: Any | None = None
    ) -> tuple[list[Event], str]:
        """Return (new_events, next_sync_token) since last sync."""
        svc = _service_fn or self._get_service()
        resp = svc.events().list(calendarId="primary", syncToken=sync_token).execute()
        events = [self._google_event_to_event(item) for item in resp.get("items", [])]
        next_token = resp.get("nextSyncToken", sync_token)
        return events, next_token

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
        _service_fn: Any | None = None,
    ) -> Event:
        """Create a new calendar event on the primary calendar."""
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        if all_day:
            start_dict: dict[str, str] = {"date": start[:10]}
            end_dict: dict[str, str] = {"date": end[:10]}
        else:
            start_dict = {"dateTime": start, "timeZone": "UTC"}
            end_dict = {"dateTime": end, "timeZone": "UTC"}
        body: dict[str, Any] = {"summary": title, "start": start_dict, "end": end_dict}
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        result = svc.events().insert(calendarId="primary", body=body).execute()
        return self._google_event_to_event(result)

    def update_event(
        self,
        event_id: str,
        updates: dict[str, Any],
        *,
        _service_fn: Any | None = None,
    ) -> Event:
        """Patch an existing event with partial updates."""
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        result = svc.events().patch(calendarId="primary", eventId=event_id, body=updates).execute()
        return self._google_event_to_event(result)

    def delete_event(self, event_id: str, *, _service_fn: Any | None = None) -> None:
        """Delete an event from the primary calendar."""
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        svc.events().delete(calendarId="primary", eventId=event_id).execute()

    def rsvp(
        self,
        event_id: str,
        response: str,
        *,
        _service_fn: Any | None = None,
    ) -> Event:
        """Update the authenticated user's RSVP status for an event.

        response: "accepted" | "declined" | "tentative"
        """
        self._check_write_mode()
        svc = _service_fn or self._get_service()
        event_raw = svc.events().get(calendarId="primary", eventId=event_id).execute()
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
        result = (
            svc.events()
            .patch(
                calendarId="primary",
                eventId=event_id,
                body={"attendees": raw_attendees},
            )
            .execute()
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
