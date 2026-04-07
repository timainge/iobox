"""
Workspace compositor — fans out queries across multiple providers.

A ``Workspace`` is the primary user-facing abstraction in iobox. It holds
named provider slots (``ProviderSlot``) for email, calendar, and file
providers, and runs queries against all of them in parallel using a
``ThreadPoolExecutor``. Individual provider failures are caught, logged, and
recorded in the workspace session without aborting the overall query.

Usage::

    from iobox.workspace import Workspace
    from iobox.space_config import load_space

    config = load_space("personal")
    ws = Workspace.from_config(config)
    results = ws.search("Q4 planning")
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


# ── Session state ─────────────────────────────────────────────────────────────


@dataclass
class ProviderSession:
    """Mutable per-slot state: auth status, last error, sync token."""

    provider_name: str
    authenticated: bool = False
    scopes: list[str] = field(default_factory=list)
    sync_token: str | None = None
    last_sync: str | None = None
    error: str | None = None


@dataclass
class WorkspaceSession:
    """Collection of all per-slot states for a workspace."""

    workspace_name: str
    providers: dict[str, ProviderSession] = field(default_factory=dict)


# ── Provider slot ─────────────────────────────────────────────────────────────


@dataclass
class ProviderSlot:
    """Named, tagged provider instance within a workspace."""

    name: str
    provider: Any  # EmailProvider | CalendarProvider | FileProvider
    tags: list[str] = field(default_factory=list)


# ── Workspace ─────────────────────────────────────────────────────────────────


@dataclass
class Workspace:
    """Compositor that fans out queries across multiple provider slots."""

    name: str
    email_providers: list[ProviderSlot] = field(default_factory=list)
    calendar_providers: list[ProviderSlot] = field(default_factory=list)
    file_providers: list[ProviderSlot] = field(default_factory=list)
    session: WorkspaceSession = field(default_factory=lambda: WorkspaceSession(workspace_name=""))

    # ── Fan-out ───────────────────────────────────────────────────────────────

    def _fan_out(
        self,
        slots: list[ProviderSlot],
        fn_name: str,
        query: Any,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
        max_workers: int = 4,
    ) -> list[Any]:
        """Call ``fn_name(query)`` on each matching slot in parallel.

        Partial failures are logged and recorded in the session; results from
        other slots are returned normally.
        """
        active_slots = slots
        if providers is not None:
            active_slots = [s for s in active_slots if s.name in providers]
        if tags is not None:
            active_slots = [s for s in active_slots if any(t in s.tags for t in tags)]

        if not active_slots:
            return []

        results: list[Any] = []

        def call_slot(slot: ProviderSlot) -> list[Any]:
            method = getattr(slot.provider, fn_name)
            return list(method(query))

        with ThreadPoolExecutor(max_workers=min(max_workers, len(active_slots))) as ex:
            future_to_slot = {ex.submit(call_slot, slot): slot for slot in active_slots}
            for future in as_completed(future_to_slot):
                slot = future_to_slot[future]
                try:
                    slot_results = future.result()
                    results.extend(slot_results)
                    if slot.name in self.session.providers:
                        self.session.providers[slot.name].error = None
                except Exception as exc:
                    logger.error("Provider '%s' failed: %s", slot.name, exc)
                    if slot.name not in self.session.providers:
                        self.session.providers[slot.name] = ProviderSession(provider_name=slot.name)
                    self.session.providers[slot.name].error = str(exc)

        return results

    # ── Query methods ─────────────────────────────────────────────────────────

    def search_emails(
        self,
        query: EmailQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[EmailData]:
        """Fan out email search across email provider slots."""
        results: list[EmailData] = self._fan_out(
            self.email_providers, "search_emails", query, providers, tags
        )
        return sorted(results, key=lambda m: m.get("date", ""), reverse=True)

    def list_events(
        self,
        query: EventQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[Event]:
        """Fan out event listing across calendar provider slots."""
        results: list[Event] = self._fan_out(
            self.calendar_providers, "list_events", query, providers, tags
        )
        # Events sorted ascending by start time (chronological order)
        return sorted(results, key=lambda e: e.get("start", ""), reverse=False)

    def list_files(
        self,
        query: FileQuery,
        providers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[File]:
        """Fan out file listing across file provider slots."""
        results: list[File] = self._fan_out(
            self.file_providers, "list_files", query, providers, tags
        )
        return sorted(results, key=lambda f: f.get("modified_at", ""), reverse=True)

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
            max_results_per_type: ``max_results`` passed to each sub-query.

        Returns:
            Merged list sorted by ``created_at`` descending.
        """
        types = types or ["email", "event", "file"]
        all_results: list[Resource] = []

        future_map: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            if "email" in types:
                q: EmailQuery = EmailQuery(text=text, max_results=max_results_per_type)
                future_map["email"] = ex.submit(self.search_emails, q)
            if "event" in types:
                eq: EventQuery = EventQuery(text=text, max_results=max_results_per_type)
                future_map["event"] = ex.submit(self.list_events, eq)
            if "file" in types:
                fq: FileQuery = FileQuery(text=text, max_results=max_results_per_type)
                future_map["file"] = ex.submit(self.list_files, fq)

            for type_name, future in future_map.items():
                try:
                    type_results = future.result()
                    if type_name == "email":
                        all_results.extend(_email_data_to_resource(r) for r in type_results)
                    else:
                        all_results.extend(type_results)
                except Exception as exc:
                    logger.error("search() %s fan-out failed: %s", type_name, exc)

        return sorted(all_results, key=lambda r: r.get("created_at", ""), reverse=True)

    def auth_status(self) -> dict[str, ProviderSession]:
        """Return current per-slot session state."""
        return dict(self.session.providers)

    # ── Write operations ──────────────────────────────────────────────────────

    def get_email_provider(self, slot_name: str | None = None) -> Any:
        """Return a specific email provider slot for write operations.

        Args:
            slot_name: Provider slot name. Defaults to the first slot.

        Raises:
            ValueError: If no email providers are configured, or the named
                slot does not exist.
        """
        if not self.email_providers:
            raise ValueError("No email providers in workspace.")
        if slot_name is None:
            return self.email_providers[0].provider
        for slot in self.email_providers:
            if slot.name == slot_name:
                return slot.provider
        raise ValueError(
            f"No email provider slot '{slot_name}'. "
            f"Available: {[s.name for s in self.email_providers]}"
        )

    def _check_write_mode(self, slot_name: str | None = None) -> None:
        """Raise PermissionError if the targeted slot is in readonly mode.

        Checks the first matching slot; if no slot is found, does nothing
        (``get_email_provider`` will raise a clearer error later).
        """
        target_slot = None
        for slot in self.email_providers:
            if slot_name is None or slot.name == slot_name:
                target_slot = slot
                break
        if target_slot is not None:
            provider = target_slot.provider
            mode = getattr(provider, "mode", None)
            if mode == "readonly":
                raise PermissionError(
                    f"Provider slot '{target_slot.name}' is in readonly mode. "
                    "Use --mode standard to enable write operations."
                )

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

                    g_msg: Any = GmailProvider()
                    email_slots.append(ProviderSlot(name=entry.slug, provider=g_msg))

                if "calendar" in entry.scopes:
                    from iobox.providers.google.calendar import GoogleCalendarProvider

                    g_cal: Any = GoogleCalendarProvider(auth=auth)
                    calendar_slots.append(ProviderSlot(name=f"{entry.slug}-cal", provider=g_cal))

                if "drive" in entry.scopes:
                    from iobox.providers.google.files import GoogleDriveProvider

                    g_drv: Any = GoogleDriveProvider(auth=auth)
                    file_slots.append(ProviderSlot(name=f"{entry.slug}-drive", provider=g_drv))

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
                    email_slots.append(ProviderSlot(name=entry.slug, provider=o_msg))

                if "calendar" in entry.scopes:
                    from iobox.providers.o365.calendar import OutlookCalendarProvider

                    o_cal: Any = OutlookCalendarProvider(
                        account_email=entry.account,
                        credentials_dir=creds_dir,
                        mode=entry.mode,
                        auth=ms_auth,
                    )
                    calendar_slots.append(ProviderSlot(name=f"{entry.slug}-cal", provider=o_cal))

                if "drive" in entry.scopes:
                    from iobox.providers.o365.files import OneDriveProvider

                    o_drv: Any = OneDriveProvider(
                        account_email=entry.account,
                        credentials_dir=creds_dir,
                        mode=entry.mode,
                        auth=ms_auth,
                    )
                    file_slots.append(ProviderSlot(name=f"{entry.slug}-drive", provider=o_drv))

        session = WorkspaceSession(workspace_name=config.name)
        return cls(
            name=config.name,
            email_providers=email_slots,
            calendar_providers=calendar_slots,
            file_providers=file_slots,
            session=session,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _email_data_to_resource(email: EmailData) -> Email:
    """Wrap EmailData as Email(Resource) for unified cross-type search results."""
    raw: Any = email  # bypass TypedDict key checks for extra provider fields
    return Email(
        id=email.get("message_id", ""),
        provider_id=raw.get("provider_id", ""),
        resource_type="email",
        title=email.get("subject", ""),
        created_at=email.get("date", ""),
        modified_at=email.get("date", ""),
        url=None,
        from_=email.get("from_", ""),
        to=raw.get("to", []),
        cc=raw.get("cc", []),
        thread_id=email.get("thread_id"),
        snippet=email.get("snippet"),
        labels=email.get("labels", []),
        body=email.get("body"),
        content_type=email.get("content_type"),
        attachments=email.get("attachments", []),
    )
