"""
Unit tests for workspace-centric CLI commands.

Tests events, files, and workspace command groups added in task-010.
Uses Typer's CliRunner with patched Workspace to avoid real API calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from iobox.cli import app
from iobox.providers.base import Event, EventQuery, File, FileQuery
from iobox.workspace import ProviderSlot, Workspace, WorkspaceSession

runner = CliRunner()


# ── Mock helpers ──────────────────────────────────────────────────────────────


def _mock_event(event_id: str = "evt1", title: str = "Team standup") -> Event:
    return Event(
        id=event_id,
        provider_id="google_calendar",
        resource_type="event",
        title=title,
        created_at="2026-01-01",
        modified_at="2026-01-01",
        url=None,
        start="2026-03-15T09:00:00",
        end="2026-03-15T09:30:00",
        all_day=False,
        organizer="boss@example.com",
        attendees=[],
        location=None,
        description=None,
        meeting_url=None,
        status="confirmed",
        recurrence=None,
    )


def _mock_file(file_id: str = "file1", name: str = "report.pdf") -> File:
    return File(
        id=file_id,
        provider_id="google_drive",
        resource_type="file",
        title=name,
        created_at="2026-01-01",
        modified_at="2026-03-10",
        url=None,
        name=name,
        mime_type="application/pdf",
        size=12345,
        path=None,
        parent_id=None,
        is_folder=False,
        download_url=None,
        content=None,
    )


def _make_ws(
    events: list[Event] | None = None,
    files: list[File] | None = None,
) -> Workspace:
    """Build a minimal mock Workspace."""
    ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))

    if events is not None:
        cal_provider = MagicMock()
        cal_provider.list_events.return_value = events
        cal_provider.get_event.return_value = events[0] if events else _mock_event()
        ws.calendar_providers = [ProviderSlot(name="gcal", provider=cal_provider)]

    if files is not None:
        file_provider = MagicMock()
        file_provider.list_files.return_value = files
        file_provider.get_file.return_value = files[0] if files else _mock_file()
        ws.file_providers = [ProviderSlot(name="gdrive", provider=file_provider)]

    return ws


# ── TestEventsListCommand ─────────────────────────────────────────────────────


class TestEventsListCommand:
    def test_events_list_basic(self) -> None:
        ws = _make_ws(events=[_mock_event(title="Team standup")])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "list"])
        assert result.exit_code == 0
        assert "Team standup" in result.output

    def test_events_list_empty(self) -> None:
        ws = _make_ws(events=[])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "list"])
        assert result.exit_code == 0
        assert "No events found" in result.output

    def test_events_list_passes_max_results(self) -> None:
        ws = _make_ws(events=[])
        with patch("iobox.cli._get_workspace", return_value=ws):
            runner.invoke(app, ["events", "list", "--max", "5"])
        # Verify list_events was called with correct max_results
        cal_prov = ws.calendar_providers[0].provider
        call_kwargs = cal_prov.list_events.call_args
        assert call_kwargs is not None
        called_query: EventQuery = call_kwargs[0][0]
        assert called_query.max_results == 5

    def test_events_list_provider_filter(self) -> None:
        ws = _make_ws(events=[_mock_event()])
        # Add a second slot
        extra = MagicMock()
        extra.list_events.return_value = []
        ws.calendar_providers.append(ProviderSlot(name="other-cal", provider=extra))
        with patch("iobox.cli._get_workspace", return_value=ws):
            runner.invoke(app, ["events", "list", "--provider", "gcal"])
        # Only the first slot should be queried (filtered by name)
        extra.list_events.assert_not_called()

    def test_events_list_unknown_provider_returns_empty(self) -> None:
        ws = _make_ws(events=[_mock_event()])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "list", "--provider", "nonexistent"])
        # _fan_out filters out non-matching slots and returns [] gracefully
        assert "No events found" in result.output

    def test_events_list_no_providers_returns_empty(self) -> None:
        ws = Workspace(name="test", session=WorkspaceSession(workspace_name="test"))
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "list"])
        # No calendar providers — returns "No events found"
        assert result.exit_code == 0
        assert "No events found" in result.output


# ── TestEventsGetCommand ──────────────────────────────────────────────────────


class TestEventsGetCommand:
    def test_events_get_prints_markdown(self) -> None:
        ev = _mock_event(event_id="evt1", title="Board meeting")
        ws = _make_ws(events=[ev])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "get", "evt1"])
        assert result.exit_code == 0
        assert "Board meeting" in result.output

    def test_events_get_calls_provider_get_event(self) -> None:
        ws = _make_ws(events=[_mock_event()])
        with patch("iobox.cli._get_workspace", return_value=ws):
            runner.invoke(app, ["events", "get", "evt123"])
        ws.calendar_providers[0].provider.get_event.assert_called_once_with("evt123")


# ── TestEventsSaveCommand ─────────────────────────────────────────────────────


class TestEventsSaveCommand:
    def test_events_save_writes_file(self, tmp_path: Path) -> None:
        ev = _mock_event(title="Q4 planning")
        ws = _make_ws(events=[ev])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["events", "save", "evt1", "--output", str(tmp_path)])
        assert result.exit_code == 0
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1
        assert "q4" in md_files[0].name


# ── TestFilesListCommand ──────────────────────────────────────────────────────


class TestFilesListCommand:
    def test_files_list_requires_query(self) -> None:
        ws = _make_ws(files=[])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["files", "list"])
        assert result.exit_code != 0
        assert "--query" in result.output or "query" in result.output.lower()

    def test_files_list_with_query(self) -> None:
        ws = _make_ws(files=[_mock_file(name="Q4 report.pdf")])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["files", "list", "--query", "Q4"])
        assert result.exit_code == 0
        assert "Q4 report.pdf" in result.output

    def test_files_list_empty(self) -> None:
        ws = _make_ws(files=[])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["files", "list", "--query", "nothing"])
        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_files_list_passes_query_to_provider(self) -> None:
        ws = _make_ws(files=[])
        with patch("iobox.cli._get_workspace", return_value=ws):
            runner.invoke(app, ["files", "list", "--query", "budget"])
        file_prov = ws.file_providers[0].provider
        called_query: FileQuery = file_prov.list_files.call_args[0][0]
        assert called_query.text == "budget"


# ── TestFilesGetCommand ───────────────────────────────────────────────────────


class TestFilesGetCommand:
    def test_files_get_prints_markdown(self) -> None:
        f = _mock_file(name="report.pdf")
        ws = _make_ws(files=[f])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["files", "get", "file1"])
        assert result.exit_code == 0
        assert "report.pdf" in result.output


# ── TestFilesSaveCommand ──────────────────────────────────────────────────────


class TestFilesSaveCommand:
    def test_files_save_writes_file(self, tmp_path: Path) -> None:
        f = _mock_file(name="budget.pdf")
        ws = _make_ws(files=[f])
        with patch("iobox.cli._get_workspace", return_value=ws):
            result = runner.invoke(app, ["files", "save", "file1", "--output", str(tmp_path)])
        assert result.exit_code == 0
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1


# ── TestWorkspaceUseCommand ───────────────────────────────────────────────────


class TestWorkspaceUseCommand:
    def test_workspace_use_sets_active_space(self) -> None:
        with (
            patch("iobox.space_config.list_spaces", return_value=["personal", "work"]),
            patch("iobox.space_config.set_active_space") as mock_set,
        ):
            result = runner.invoke(app, ["workspace", "use", "personal"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with("personal")

    def test_workspace_use_unknown_space_exits(self) -> None:
        with patch("iobox.space_config.list_spaces", return_value=["personal"]):
            result = runner.invoke(app, ["workspace", "use", "nonexistent"])
        assert result.exit_code != 0

    def test_workspace_use_prints_confirmation(self) -> None:
        with (
            patch("iobox.space_config.list_spaces", return_value=["work"]),
            patch("iobox.space_config.set_active_space"),
        ):
            result = runner.invoke(app, ["workspace", "use", "work"])
        assert "work" in result.output


# ── TestWorkspaceStatusCommand ────────────────────────────────────────────────


class TestWorkspaceStatusCommand:
    def test_workspace_status_shows_services(self) -> None:
        from iobox.space_config import ServiceEntry, SpaceConfig

        config = SpaceConfig(
            name="personal",
            services=[
                ServiceEntry(
                    number=1,
                    service="gmail",
                    account="tim@gmail.com",
                    scopes=["messages", "calendar"],
                    mode="readonly",
                )
            ],
        )
        with (
            patch("iobox.space_config.get_active_space", return_value="personal"),
            patch("iobox.space_config.load_space", return_value=config),
        ):
            result = runner.invoke(app, ["workspace", "status"])
        assert result.exit_code == 0
        assert "gmail" in result.output
        assert "tim@gmail.com" in result.output

    def test_workspace_status_no_active_space_exits(self) -> None:
        with patch("iobox.space_config.get_active_space", return_value=None):
            result = runner.invoke(app, ["workspace", "status"])
        assert result.exit_code != 0
