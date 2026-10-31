"""
Workspace compositor — fans out queries across multiple providers.

A ``Workspace`` is the primary user-facing abstraction in iobox. It holds
named provider slots (``ProviderSlot``) for email, calendar, and file
providers, and runs queries against all of them in parallel using a
``ThreadPoolExecutor``. Individual provider failures are caught, logged, and
reported in ``Workspace.last_errors`` without aborting the overall query.

Usage::

    from iobox.workspace import Workspace
    from iobox.space_config import load_space

    config = load_space("personal")
    ws = Workspace.from_config(config)
    results = ws.search("Q4 planning")
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import formataddr, getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from iobox.providers.base import (
    Email,
    EmailData,
    EmailQuery,
    Event,
    EventQuery,
    File,
    FileQuery,
    Resource,
)

if TYPE_CHECKING:
    from iobox.space_config import SpaceConfig

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# ── Date normalisation ────────────────────────────────────────────────────────

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?"
    r"\s*(Z|[+-]\d{2}(?::?\d{2})?)?$",
    re.IGNORECASE,
)


def _as_utc(dt: datetime) -> datetime:
    """Naive datetimes are taken as local time; result is aware UTC."""
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret as local wall-clock time
    return dt.astimezone(timezone.utc)


def _parse_iso(text: str) -> datetime | None:
    m = _ISO_RE.match(text)
    if not m:
        return None
    year, month, day, hh, mm, ss, frac, tz = m.groups()
    micro = int((frac or "0")[:6].ljust(6, "0"))
    tzinfo: timezone | None = None
    if tz:
        if tz.upper() == "Z":
            tzinfo = timezone.utc
        else:
            sign = -1 if tz[0] == "-" else 1
            digits = tz[1:].replace(":", "")
            offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
            tzinfo = timezone(sign * offset)
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hh or 0),
            int(mm or 0),
            int(ss or 0),
            micro,
            tzinfo=tzinfo,
        )
    except ValueError:
        return None


def to_utc_datetime(value: object) -> datetime | None:
    """Parse any date value seen in provider results to an aware UTC datetime.

    Accepts ``datetime``/``date`` objects, RFC 2822 strings (Gmail ``Date``
    headers, e.g. ``"Tue, 10 Mar 2026 10:00:00 +1100"``) and ISO 8601 strings
    including a ``Z`` suffix, numeric offsets, long fractional seconds and
    date-only values (``"2026-03-10"``). Values without a timezone are taken
    as local time. Returns ``None`` for missing or unparsable values.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, date):
        return _as_utc(datetime(value.year, value.month, value.day))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    dt = _parse_iso(text)
    if dt is None:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
        if dt is None:  # older Pythons return None instead of raising
            return None
    return _as_utc(dt)


def sort_by_date(
    items: list[_T], key: Callable[[_T], object], *, newest_first: bool = True
) -> list[_T]:
    """Sort *items* by the date returned by *key* (see :func:`to_utc_datetime`).

    Items whose date is missing or unparsable sort last, in their original order.
    """
    dated: list[tuple[datetime, _T]] = []
    undated: list[_T] = []
    for item in items:
        dt = to_utc_datetime(key(item))
        if dt is None:
            undated.append(item)
        else:
            dated.append((dt, item))
    dated.sort(key=lambda pair: pair[0], reverse=newest_first)
    return [item for _, item in dated] + undated


# ── Provider slot ─────────────────────────────────────────────────────────────


@dataclass
class ProviderSlot:
    """Named, tagged provider instance within a workspace."""

    name: str
    provider: Any  # EmailProvider | CalendarProvider | FileProvider
    tags: list[str] = field(default_factory=list)
    #: ``ServiceEntry.id`` this slot was built from (set by ``from_config``).
    service_id: str | None = None


#: Default look-back window for event text search when no ``after`` is given.
DEFAULT_EVENT_SEARCH_DAYS = 90

_EMAIL_PROVIDER_IDS = {"GmailProvider": "gmail", "OutlookProvider": "outlook"}


def _provider_id_for(provider: Any) -> str:
    """Best-effort provider identifier (``"gmail"``, ``"google_calendar"`` …)."""
    pid = getattr(type(provider), "PROVIDER_ID", None)
    if isinstance(pid, str) and pid:
        return pid
    return _EMAIL_PROVIDER_IDS.get(type(provider).__name__, "")


def _cap(items: list[_T], limit: int | None) -> list[_T]:
    """Return the first *limit* items; ``None`` or ``<= 0`` means no cap."""
    if limit is None or limit <= 0:
        return items
    return items[:limit]


def _describe_error(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


# ── Workspace ─────────────────────────────────────────────────────────────────


@dataclass
class Workspace:
    """Compositor that fans out queries across multiple provider slots.

    Every result dict returned by the query methods carries a ``"slot"`` key
    naming the provider slot it came from; pass it back to
    :meth:`get_email_provider` / :meth:`get_calendar_provider` /
    :meth:`get_file_provider` to fetch or modify the item on the right account.

    After each query method, :attr:`last_errors` maps the name of every slot
    that failed to its error message (empty when everything succeeded). A
    failing slot never raises out of a query method. ``last_errors`` describes
    the most recent call only, so don't share one ``Workspace`` between
    threads if you rely on it.
    """

    name: str
    email_providers: list[ProviderSlot] = field(default_factory=list)
    calendar_providers: list[ProviderSlot] = field(default_factory=list)
    file_providers: list[ProviderSlot] = field(default_factory=list)
    last_errors: dict[str, str] = field(default_factory=dict)

    # ── Fan-out ───────────────────────────────────────────────────────────────

    def _fan_out(
        self,
        slots: list[ProviderSlot],
        fn_name: str,
        query: Any,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
        max_workers: int = 4,
    ) -> tuple[list[Any], dict[str, str]]:
        """Call ``fn_name(query)`` on each matching slot in parallel.

        Returns ``(results, errors)``. Each result is a shallow copy of the
        provider's dict with ``"slot"`` set to the slot name (and
        ``"provider_id"`` filled in when the provider left it out). Failures
        are logged and returned in ``errors`` (slot name → message); they
        never propagate.
        """
        active_slots = slots
        if providers is not None:
            active_slots = [s for s in active_slots if s.name in providers]
        if tags is not None:
            active_slots = [s for s in active_slots if any(t in s.tags for t in tags)]

        results: list[Any] = []
        errors: dict[str, str] = {}
        if not active_slots:
            return results, errors

        def call_slot(slot: ProviderSlot) -> list[Any]:
            method = getattr(slot.provider, fn_name)
            return list(method(query))

        with ThreadPoolExecutor(max_workers=min(max_workers, len(active_slots))) as ex:
            future_to_slot = {ex.submit(call_slot, slot): slot for slot in active_slots}
            for future in as_completed(future_to_slot):
                slot = future_to_slot[future]
                try:
                    slot_results = future.result()
                except Exception as exc:
                    errors[slot.name] = _describe_error(exc)
                    logger.error("Provider '%s' failed: %s", slot.name, errors[slot.name])
                    continue
                provider_id = _provider_id_for(slot.provider)
                for item in slot_results:
                    tagged = dict(item)
                    tagged["slot"] = slot.name
                    if not tagged.get("provider_id") and provider_id:
                        tagged["provider_id"] = provider_id
                    results.append(tagged)

        return results, errors

    # ── Query methods ─────────────────────────────────────────────────────────
    #
    # Each public method resets ``last_errors``; the ``_…`` variants return
    # their errors instead so ``search()`` can run them concurrently.

    def _search_emails(
        self, query: EmailQuery, providers: list[str] | None, tags: list[str] | None
    ) -> tuple[list[EmailData], dict[str, str]]:
        results, errors = self._fan_out(
            self.email_providers, "search_emails", query, providers, tags
        )
        ordered = sort_by_date(results, lambda m: m.get("date"))
        return _cap(ordered, query.max_results), errors

    def _list_events(
        self, query: EventQuery, providers: list[str] | None, tags: list[str] | None
    ) -> tuple[list[Event], dict[str, str]]:
        results, errors = self._fan_out(
            self.calendar_providers, "list_events", query, providers, tags
        )
        # Events sorted ascending by start time (chronological order)
        ordered = sort_by_date(results, lambda e: e.get("start"), newest_first=False)
        return _cap(ordered, query.max_results), errors

    def _list_files(
        self, query: FileQuery, providers: list[str] | None, tags: list[str] | None
    ) -> tuple[list[File], dict[str, str]]:
        results, errors = self._fan_out(self.file_providers, "list_files", query, providers, tags)
        ordered = sort_by_date(results, lambda f: f.get("modified_at"))
        return _cap(ordered, query.max_results), errors

    def search_emails(
        self,
        query: EmailQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[EmailData]:
        """Fan out email search across email provider slots.

        Returns at most ``query.max_results`` messages, newest first, each
        tagged with ``"slot"``. Failed slots are listed in :attr:`last_errors`.
        """
        self.last_errors = {}
        results, errors = self._search_emails(query, providers, tags)
        self.last_errors = errors
        return results

    def list_events(
        self,
        query: EventQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[Event]:
        """Fan out event listing across calendar provider slots.

        Returns at most ``query.max_results`` events in chronological order,
        each tagged with ``"slot"``. Failed slots are listed in :attr:`last_errors`.
        """
        self.last_errors = {}
        results, errors = self._list_events(query, providers, tags)
        self.last_errors = errors
        return results

    def list_files(
        self,
        query: FileQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[File]:
        """Fan out file listing across file provider slots.

        Returns at most ``query.max_results`` files, most recently modified
        first, each tagged with ``"slot"``. Failed slots are listed in
        :attr:`last_errors`.
        """
        self.last_errors = {}
        results, errors = self._list_files(query, providers, tags)
        self.last_errors = errors
        return results

    def search(
        self,
        text: str,
        types: list[str] | None = None,
        max_results_per_type: int = 10,
    ) -> list[Resource]:
        """Cross-type unified search across all provider slots.

        Args:
            text: Search text.
            types: Subset of ``["email", "event", "file"]``.  Defaults to all.
            max_results_per_type: Cap on results per type (also passed to each
                provider as ``max_results``).

        Returns:
            Merged list sorted by ``created_at`` descending, at most
            ``max_results_per_type`` per type. Events are limited to the last
            ``DEFAULT_EVENT_SEARCH_DAYS`` days (and the future). Failed slots
            are listed in :attr:`last_errors`.
        """
        self.last_errors = {}
        types = types or ["email", "event", "file"]
        all_results: list[Resource] = []
        errors: dict[str, str] = {}

        future_map: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            if "email" in types:
                q: EmailQuery = EmailQuery(text=text, max_results=max_results_per_type)
                future_map["email"] = ex.submit(self._search_emails, q, None, None)
            if "event" in types:
                after = (date.today() - timedelta(days=DEFAULT_EVENT_SEARCH_DAYS)).isoformat()
                eq: EventQuery = EventQuery(
                    text=text, after=after, max_results=max_results_per_type
                )
                future_map["event"] = ex.submit(self._list_events, eq, None, None)
            if "file" in types:
                fq: FileQuery = FileQuery(text=text, max_results=max_results_per_type)
                future_map["file"] = ex.submit(self._list_files, fq, None, None)

            for type_name, future in future_map.items():
                try:
                    type_results, type_errors = future.result()
                    errors.update(type_errors)
                    if type_name == "email":
                        all_results.extend(_email_data_to_resource(r) for r in type_results)
                    else:
                        all_results.extend(type_results)
                except Exception as exc:
                    logger.error("search() %s fan-out failed: %s", type_name, exc)
                    errors[f"search:{type_name}"] = _describe_error(exc)

        self.last_errors = errors
        return sort_by_date(all_results, lambda r: r.get("created_at"))

    # ── Slot lookup (for fetch-by-ID and writes) ──────────────────────────────

    @staticmethod
    def _find_slot(slots: list[ProviderSlot], kind: str, slot_name: str | None) -> Any:
        if not slots:
            raise ValueError(f"No {kind} providers in workspace.")
        if slot_name is None:
            return slots[0].provider
        for slot in slots:
            if slot.name == slot_name:
                return slot.provider
        raise ValueError(
            f"No {kind} provider slot '{slot_name}'. Available: {[s.name for s in slots]}"
        )

    def get_email_provider(self, slot_name: str | None = None) -> Any:
        """Return the email provider in slot *slot_name* (default: the first slot).

        Pass the ``"slot"`` value from a search result to act on the account
        the message came from.

        Raises:
            ValueError: If no email providers are configured, or the named
                slot does not exist.
        """
        return self._find_slot(self.email_providers, "email", slot_name)

    def get_calendar_provider(self, slot_name: str | None = None) -> Any:
        """Return the calendar provider in slot *slot_name* (default: the first slot).

        Raises:
            ValueError: If no calendar providers are configured, or the named
                slot does not exist.
        """
        return self._find_slot(self.calendar_providers, "calendar", slot_name)

    def get_file_provider(self, slot_name: str | None = None) -> Any:
        """Return the file provider in slot *slot_name* (default: the first slot).

        Raises:
            ValueError: If no file providers are configured, or the named
                slot does not exist.
        """
        return self._find_slot(self.file_providers, "file", slot_name)

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(
        cls,
        config: SpaceConfig,
        credentials_dir: str | None = None,
    ) -> Workspace:
        """Instantiate a Workspace from a SpaceConfig.

        Builds provider instances lazily from the service entries; auth happens
        on first API call, not at construction time.
        """
        from iobox.modes import _tier_for_mode, get_google_scopes
        from iobox.providers.google.auth import GoogleAuth

        creds_dir = credentials_dir or str(Path.home() / ".iobox")

        email_slots: list[ProviderSlot] = []
        calendar_slots: list[ProviderSlot] = []
        file_slots: list[ProviderSlot] = []

        # Cache (service, account, mode) → GoogleAuth to share one token
        google_auth_cache: dict[str, GoogleAuth] = {}

        for entry in config.services:
            cache_key = f"{entry.service}:{entry.account}:{entry.mode}"

            if entry.service == "google":
                scopes = get_google_scopes(entry.scopes, entry.mode)
                tier = _tier_for_mode(entry.mode)
                auth = google_auth_cache.get(cache_key)
                if auth is None:
                    auth = GoogleAuth(
                        account=entry.account,
                        scopes=scopes,
                        credentials_dir=creds_dir,
                        tier=tier,
                    )
                    google_auth_cache[cache_key] = auth

                if "email" in entry.scopes:
                    from iobox.providers.google.email import GmailProvider

                    g_msg: Any = GmailProvider(auth=auth)
                    email_slots.append(
                        ProviderSlot(name=entry.slug, provider=g_msg, service_id=entry.id)
                    )

                if "calendar" in entry.scopes:
                    from iobox.providers.google.calendar import GoogleCalendarProvider

                    g_cal: Any = GoogleCalendarProvider(auth=auth, mode=entry.mode)
                    calendar_slots.append(
                        ProviderSlot(name=f"{entry.slug}-cal", provider=g_cal, service_id=entry.id)
                    )

                if "drive" in entry.scopes:
                    from iobox.providers.google.files import GoogleDriveProvider

                    g_drv: Any = GoogleDriveProvider(auth=auth, mode=entry.mode)
                    file_slots.append(
                        ProviderSlot(
                            name=f"{entry.slug}-drive", provider=g_drv, service_id=entry.id
                        )
                    )

            elif entry.service == "o365":
                from iobox.providers.o365.auth import MicrosoftAuth, get_microsoft_scopes

                ms_cache_key = f"outlook:{entry.account}:{entry.mode}"
                ms_auth: Any = google_auth_cache.get(ms_cache_key)  # reuse same dict
                if ms_auth is None:
                    ms_scopes = get_microsoft_scopes(entry.scopes, entry.mode)
                    ms_auth = MicrosoftAuth(
                        account=entry.account,
                        scopes=ms_scopes,
                        credentials_dir=creds_dir,
                    )
                    google_auth_cache[ms_cache_key] = ms_auth

                if "email" in entry.scopes:
                    from iobox.providers.o365.email import OutlookProvider

                    o_msg: Any = OutlookProvider(auth=ms_auth)
                    email_slots.append(
                        ProviderSlot(name=entry.slug, provider=o_msg, service_id=entry.id)
                    )

                if "calendar" in entry.scopes:
                    from iobox.providers.o365.calendar import OutlookCalendarProvider

                    o_cal: Any = OutlookCalendarProvider(
                        account_email=entry.account,
                        credentials_dir=creds_dir,
                        mode=entry.mode,
                        auth=ms_auth,
                    )
                    calendar_slots.append(
                        ProviderSlot(name=f"{entry.slug}-cal", provider=o_cal, service_id=entry.id)
                    )

                if "drive" in entry.scopes:
                    from iobox.providers.o365.files import OneDriveProvider

                    o_drv: Any = OneDriveProvider(
                        account_email=entry.account,
                        credentials_dir=creds_dir,
                        mode=entry.mode,
                        auth=ms_auth,
                    )
                    file_slots.append(
                        ProviderSlot(
                            name=f"{entry.slug}-drive", provider=o_drv, service_id=entry.id
                        )
                    )

        for slots in (email_slots, calendar_slots, file_slots):
            _dedupe_slot_names(slots)

        return cls(
            name=config.name,
            email_providers=email_slots,
            calendar_providers=calendar_slots,
            file_providers=file_slots,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _dedupe_slot_names(slots: list[ProviderSlot]) -> None:
    """Rename colliding slot names in place (``x``, ``x-2``, ``x-3`` …).

    Configs written before slugs were made unique can contain two services with
    the same slug; without this, ``providers=[name]`` would be ambiguous.
    """
    seen: set[str] = set()
    for slot in slots:
        if slot.name in seen:
            n = 2
            while f"{slot.name}-{n}" in seen:
                n += 1
            new_name = f"{slot.name}-{n}"
            logger.warning(
                "Duplicate provider slot name '%s'; using '%s' instead", slot.name, new_name
            )
            slot.name = new_name
        seen.add(slot.name)


def _split_addresses(value: Any) -> list[str]:
    """Split a raw ``To``/``Cc`` header into one ``"Name <addr>"`` string per recipient."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    out: list[str] = []
    for name, addr in getaddresses([str(value)]):
        if not addr and not name:
            continue
        out.append(formataddr((name, addr)) if name else addr)
    return out


def _email_data_to_resource(email: EmailData) -> Email:
    """Wrap EmailData as Email(Resource) for unified cross-type search results.

    ``to``/``cc`` header strings are split into lists; ``slot`` and
    ``provider_id`` stamped by the fan-out are carried over.
    """
    raw: Any = email  # bypass TypedDict key checks for extra provider fields
    resource = Email(
        id=email.get("message_id", ""),
        provider_id=raw.get("provider_id", ""),
        resource_type="email",
        title=email.get("subject", ""),
        created_at=email.get("date", ""),
        modified_at=email.get("date", ""),
        url=None,
        from_=email.get("from_", ""),
        to=_split_addresses(raw.get("to")),
        cc=_split_addresses(raw.get("cc")),
        thread_id=email.get("thread_id"),
        snippet=email.get("snippet"),
        labels=email.get("labels", []),
        body=email.get("body"),
        content_type=email.get("content_type"),
        attachments=email.get("attachments", []),
    )
    if raw.get("slot"):
        resource["slot"] = raw["slot"]
    return resource
