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


# ── TestEventsFilesModeGating (SEC-08) ────────────────────────────────────────


class TestEventsFilesModeGating:
    """events/files subcommands are gated by --mode, matching the MCP tiers."""

    def _ws(self) -> Workspace:
        ws = _make_ws(events=[_mock_event()], files=[_mock_file()])
        cal = ws.calendar_providers[0].provider
        cal.create_event.return_value = _mock_event()
        cal.rsvp.return_value = _mock_event()
        fp = ws.file_providers[0].provider
        fp.upload_file.return_value = _mock_file()
        fp.create_folder.return_value = _mock_file(name="New")
        return ws

    def _invoke(self, ws: Workspace, args: list[str], env: dict[str, str] | None = None):
        with patch("iobox.cli._get_workspace", return_value=ws):
            return runner.invoke(app, args, env=env)

    def test_readonly_blocks_events_delete(self) -> None:
        ws = self._ws()
        result = self._invoke(ws, ["--mode", "readonly", "events", "delete", "evt1", "--yes"])
        assert result.exit_code == 1
        assert (
            "Command 'events delete' is not allowed in 'readonly' mode. "
            "Use --mode dangerous to enable it." in result.stderr
        )
        ws.calendar_providers[0].provider.delete_event.assert_not_called()

    def test_standard_blocks_events_delete(self) -> None:
        ws = self._ws()
        result = self._invoke(ws, ["--mode", "standard", "events", "delete", "evt1", "--yes"])
        assert result.exit_code == 1
        assert "Use --mode dangerous" in result.stderr
        ws.calendar_providers[0].provider.delete_event.assert_not_called()

    def test_dangerous_allows_events_delete(self) -> None:
        ws = self._ws()
        result = self._invoke(ws, ["--mode", "dangerous", "events", "delete", "evt1", "--yes"])
        assert result.exit_code == 0, result.output
        ws.calendar_providers[0].provider.delete_event.assert_called_once_with("evt1")

    def test_readonly_blocks_events_create(self) -> None:
        ws = self._ws()
        args = [
            "--mode",
            "readonly",
            "events",
            "create",
            "--title",
            "x",
            "--start",
            "2026-04-01T09:00",
            "--end",
            "2026-04-01T09:30",
        ]
        result = self._invoke(ws, args)
        assert result.exit_code == 1
        assert "Command 'events create' is not allowed in 'readonly' mode." in result.stderr
        assert "Use --mode standard" in result.stderr
        ws.calendar_providers[0].provider.create_event.assert_not_called()

    def test_readonly_blocks_events_rsvp(self) -> None:
        ws = self._ws()
        result = self._invoke(
            ws, ["--mode", "readonly", "events", "rsvp", "evt1", "--response", "accepted"]
        )
        assert result.exit_code == 1
        assert "Use --mode standard" in result.stderr

    def test_standard_allows_events_rsvp(self) -> None:
        ws = self._ws()
        result = self._invoke(
            ws, ["--mode", "standard", "events", "rsvp", "evt1", "--response", "accepted"]
        )
        assert result.exit_code == 0, result.output

    def test_readonly_blocks_file_writes(self, tmp_path: Path) -> None:
        local = tmp_path / "a.txt"
        local.write_text("x")
        for args in (
            ["files", "upload", str(local)],
            ["files", "mkdir", "New"],
            ["files", "delete", "file1", "--yes"],
        ):
            ws = self._ws()
            result = self._invoke(ws, ["--mode", "readonly", *args])
            assert result.exit_code == 1, args
            assert f"Command 'files {args[1]}' is not allowed" in result.stderr
            assert "Use --mode standard" in result.stderr
            fp = ws.file_providers[0].provider
            fp.upload_file.assert_not_called()
            fp.create_folder.assert_not_called()
            fp.delete_file.assert_not_called()

    def test_standard_allows_file_writes(self) -> None:
        ws = self._ws()
        result = self._invoke(ws, ["--mode", "standard", "files", "mkdir", "New"])
        assert result.exit_code == 0, result.output
        result = self._invoke(ws, ["--mode", "standard", "files", "delete", "file1", "--yes"])
        assert result.exit_code == 0, result.output

    def test_readonly_allows_reads(self, tmp_path: Path) -> None:
        for args in (
            ["events", "list"],
            ["events", "get", "evt1"],
            ["events", "save", "evt1", "-o", str(tmp_path)],
            ["files", "list", "-q", "x"],
            ["files", "get", "file1"],
            ["files", "save", "file1", "-o", str(tmp_path)],
        ):
            result = self._invoke(self._ws(), ["--mode", "readonly", *args])
            assert result.exit_code == 0, (args, result.output)

    def test_mode_from_env_is_enforced(self) -> None:
        ws = self._ws()
        result = self._invoke(
            ws, ["events", "delete", "evt1", "--yes"], env={"IOBOX_MODE": "readonly"}
        )
        assert result.exit_code == 1
        assert "not allowed in 'readonly' mode" in result.stderr

    def test_workspace_group_allowed_in_readonly(self) -> None:
        with patch("iobox.space_config.get_active_space", return_value=None):
            result = runner.invoke(app, ["--mode", "readonly", "workspace", "status"])
        assert "not allowed" not in result.output


# ── TestSaveFilenames (CLI-04) ────────────────────────────────────────────────


class TestSaveFilenames:
    """events/files save never silently overwrite a different resource."""

    def _save_event(self, ev: Event, tmp_path: Path):
        ws = _make_ws(events=[ev])
        with patch("iobox.cli._get_workspace", return_value=ws):
            return runner.invoke(app, ["events", "save", ev["id"], "-o", str(tmp_path)])

    def _save_file(self, f: File, tmp_path: Path):
        ws = _make_ws(files=[f])
        with patch("iobox.cli._get_workspace", return_value=ws):
            return runner.invoke(app, ["files", "save", f["id"], "-o", str(tmp_path)])

    def test_same_title_events_get_distinct_files(self, tmp_path: Path) -> None:
        assert self._save_event(_mock_event("evtA", "Standup"), tmp_path).exit_code == 0
        assert self._save_event(_mock_event("evtB", "Standup"), tmp_path).exit_code == 0
        names = sorted(p.name for p in tmp_path.glob("*.md"))
        assert names == ["standup_evtA.md", "standup_evtB.md"]

    def test_same_event_saved_twice_reuses_file(self, tmp_path: Path) -> None:
        self._save_event(_mock_event("evtA", "Standup"), tmp_path)
        self._save_event(_mock_event("evtA", "Standup"), tmp_path)
        assert len(list(tmp_path.glob("*.md"))) == 1

    def test_empty_event_title_uses_id(self, tmp_path: Path) -> None:
        result = self._save_event(_mock_event("evtA", ""), tmp_path)
        assert result.exit_code == 0
        assert [p.name for p in tmp_path.glob("*.md")] == ["event_evtA.md"]

    def test_long_ids_with_shared_prefix_do_not_collide(self, tmp_path: Path) -> None:
        prefix = "AAMkADAwATM0MDAAMS1iNTcwLWI2NTEtMDACLTAwCgBGAAAD" * 2
        self._save_event(_mock_event(prefix + "x1==", "Sync"), tmp_path)
        self._save_event(_mock_event(prefix + "x2==", "Sync"), tmp_path)
        names = [p.name for p in tmp_path.glob("*.md")]
        assert len(names) == 2
        for n in names:
            assert n.startswith("sync_")
            assert "=" not in n and "/" not in n

    def test_same_name_files_get_distinct_files(self, tmp_path: Path) -> None:
        self._save_file(_mock_file("f1", "report.pdf"), tmp_path)
        self._save_file(_mock_file("f2", "report.pdf"), tmp_path)
        assert len(list(tmp_path.glob("*.md"))) == 2

    def test_unsluggable_file_name_uses_id(self, tmp_path: Path) -> None:
        self._save_file(_mock_file("f1", "!!!"), tmp_path)
        assert [p.name for p in tmp_path.glob("*.md")] == ["file_f1.md"]
