"""
Unit tests for FileProvider write operations.

Tests GoogleDriveProvider and OneDriveProvider write methods using
the _service_fn= injection pattern and HAS_O365 patching.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.google.files import FOLDER_MIME_TYPE, GoogleDriveProvider

# ── Helpers ───────────────────────────────────────────────────────────────────

_GDrive_MODULE = "iobox.providers.google.files"
_OneDrive_MODULE = "iobox.providers.o365.files"
_MEDIA_UPLOAD = "googleapiclient.http.MediaFileUpload"


def _make_raw_file(
    file_id: str = "file1",
    name: str = "test.txt",
    mime: str = "text/plain",
    is_folder: bool = False,
) -> dict:
    return {
        "id": file_id,
        "name": name,
        "mimeType": FOLDER_MIME_TYPE if is_folder else mime,
        "createdTime": "2026-03-01T00:00:00Z",
        "modifiedTime": "2026-03-10T00:00:00Z",
        "size": "1024",
        "parents": ["root"],
        "webViewLink": "https://drive.google.com/file/d/file1",
    }


def _make_google_provider(mode: str = "standard") -> GoogleDriveProvider:
    auth = MagicMock()
    return GoogleDriveProvider(auth=auth, mode=mode)


def _make_service(raw_file: dict | None = None) -> MagicMock:
    svc = MagicMock()
    raw = raw_file or _make_raw_file()
    svc.files.return_value.create.return_value.execute.return_value = raw
    svc.files.return_value.update.return_value.execute.return_value = raw
    svc.files.return_value.delete.return_value.execute.return_value = None
    svc.files.return_value.get.return_value.execute.return_value = raw
    return svc


# ── GoogleDriveProvider: _check_write_mode ────────────────────────────────────


class TestGoogleDriveWriteMode:
    def test_write_raises_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError, match="mode='standard'"):
            provider._check_write_mode()

    def test_write_allowed_in_standard(self) -> None:
        provider = _make_google_provider(mode="standard")
        provider._check_write_mode()  # should not raise


# ── GoogleDriveProvider: upload_file ─────────────────────────────────────────


class TestGoogleDriveUploadFile:
    def test_upload_basic(self, tmp_path: Path) -> None:
        local = tmp_path / "test.txt"
        local.write_text("hello")
        provider = _make_google_provider()
        svc = _make_service()
        with patch(_MEDIA_UPLOAD):
            file = provider.upload_file(str(local), _service_fn=svc)
        assert file["name"] == "test.txt"
        svc.files.return_value.create.assert_called_once()

    def test_upload_to_folder(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        provider = _make_google_provider()
        svc = _make_service()
        with patch(_MEDIA_UPLOAD):
            provider.upload_file(str(local), parent_id="folder123", _service_fn=svc)
        body = svc.files.return_value.create.call_args[1]["body"]
        assert "folder123" in body.get("parents", [])

    def test_upload_with_name_override(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        provider = _make_google_provider()
        raw = _make_raw_file(name="Custom Name.txt")
        svc = _make_service(raw)
        with patch(_MEDIA_UPLOAD):
            provider.upload_file(str(local), name="Custom Name.txt", _service_fn=svc)
        body = svc.files.return_value.create.call_args[1]["body"]
        assert body["name"] == "Custom Name.txt"

    def test_upload_blocked_in_readonly(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.upload_file(str(local))


# ── GoogleDriveProvider: update_file ─────────────────────────────────────────


class TestGoogleDriveUpdateFile:
    def test_update_file(self, tmp_path: Path) -> None:
        local = tmp_path / "updated.txt"
        local.write_text("new content")
        provider = _make_google_provider()
        svc = _make_service()
        with patch(_MEDIA_UPLOAD):
            file = provider.update_file("file1", str(local), _service_fn=svc)
        assert file["id"] == "file1"
        svc.files.return_value.update.assert_called_once()

    def test_update_blocked_in_readonly(self, tmp_path: Path) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.update_file("file1", "/tmp/x.txt")


# ── GoogleDriveProvider: delete_file ─────────────────────────────────────────


class TestGoogleDriveDeleteFile:
    def test_move_to_trash_default(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.delete_file("file1", _service_fn=svc)
        # Should call files().update() with trashed=True, not files().delete()
        svc.files.return_value.update.assert_called_once()
        body = svc.files.return_value.update.call_args[1]["body"]
        assert body.get("trashed") is True

    def test_permanent_delete(self) -> None:
        provider = _make_google_provider()
        svc = _make_service()
        provider.delete_file("file1", permanent=True, _service_fn=svc)
        svc.files.return_value.delete.assert_called_once()

    def test_delete_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.delete_file("file1")


# ── GoogleDriveProvider: create_folder ───────────────────────────────────────


class TestGoogleDriveCreateFolder:
    def test_create_folder_at_root(self) -> None:
        provider = _make_google_provider()
        raw = _make_raw_file(name="New Folder", is_folder=True)
        svc = _make_service(raw)
        folder = provider.create_folder("New Folder", _service_fn=svc)
        assert folder["is_folder"] is True
        body = svc.files.return_value.create.call_args[1]["body"]
        assert body["mimeType"] == FOLDER_MIME_TYPE

    def test_create_folder_with_parent(self) -> None:
        provider = _make_google_provider()
        raw = _make_raw_file(name="Sub Folder", is_folder=True)
        svc = _make_service(raw)
        provider.create_folder("Sub Folder", parent_id="parent123", _service_fn=svc)
        body = svc.files.return_value.create.call_args[1]["body"]
        assert "parent123" in body.get("parents", [])

    def test_create_folder_blocked_in_readonly(self) -> None:
        provider = _make_google_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.create_folder("My Folder")


# ── OneDriveProvider write ops ────────────────────────────────────────────────


class TestOneDriveWriteOps:
    """OneDriveProvider writes on real python-o365 Drive/Folder objects over a
    fake Graph session (skipped without the outlook extra)."""

    @staticmethod
    def _provider(mode: str = "standard") -> Any:
        from tests.fixtures.mock_outlook_responses import graph_drive_item, make_onedrive_provider

        return make_onedrive_provider(
            [
                graph_drive_item("item-1", name="file.txt"),
                graph_drive_item("folder-a", name="Reports", folder=True),
            ],
            mode=mode,
        )

    def test_upload_to_root(self, tmp_path: Path) -> None:
        local = tmp_path / "test.txt"
        local.write_text("hello")
        p = self._provider()
        file = p.upload_file(str(local))
        assert file["name"] == "test.txt"
        assert file["parent_id"] == "root-id"
        call = p.graph.last("PUT", r"/me/drive/items/.+:/content")
        assert call.path == "/me/drive/items/root-id:/test.txt:/content"

    def test_upload_to_folder_with_name(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        p = self._provider()
        p.upload_file(str(local), parent_id="folder-a", name="renamed.txt")
        call = p.graph.last("PUT", r"/me/drive/items/.+:/content")
        assert call.path == "/me/drive/items/folder-a:/renamed.txt:/content"

    def test_upload_into_a_file_is_rejected(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        with pytest.raises(ValueError, match="not a folder"):
            self._provider().upload_file(str(local), parent_id="item-1")

    def test_update_file_reuploads_into_parent(self, tmp_path: Path) -> None:
        """O365-09: DriveItem has no .parent; the item's parent_id is used."""
        local = tmp_path / "new.txt"
        local.write_text("v2")
        p = self._provider()
        file = p.update_file("item-1", str(local))
        call = p.graph.last("PUT", r"/me/drive/items/.+:/content")
        assert call.path == "/me/drive/items/root-id:/file.txt:/content"
        assert file["id"] == "item-1"  # same item replaced

    def test_delete_goes_to_recycle_bin(self) -> None:
        p = self._provider()
        p.delete_file("item-1")
        p.graph.last("DELETE", r"/me/drive/items/item-1")
        assert not p.graph.find("POST", r".*/permanentDelete")

    def test_delete_permanent(self) -> None:
        """O365-14: permanent=True was silently ignored."""
        p = self._provider()
        p.delete_file("item-1", permanent=True)
        p.graph.last("POST", r"/me/drive/items/item-1/permanentDelete")
        assert not p.graph.find("DELETE", r".*")

    def test_delete_missing_is_noop(self) -> None:
        p = self._provider()
        p.delete_file("nope")
        assert not p.graph.find("DELETE", r".*")

    def test_create_folder_uses_create_child_folder(self) -> None:
        """O365-09: Folder.mkdir does not exist in python-o365."""
        p = self._provider()
        folder = p.create_folder("New Folder")
        call = p.graph.last("POST", r"/me/drive/items/root-id/children")
        assert call.body == {"name": "New Folder", "folder": {}}
        assert folder["is_folder"] is True
        assert folder["name"] == "New Folder"
        assert folder["mime_type"] == "inode/directory"

    def test_create_subfolder(self) -> None:
        p = self._provider()
        p.create_folder("Q1", parent_id="folder-a")
        p.graph.last("POST", r"/me/drive/items/folder-a/children")

    def test_writes_blocked_in_readonly(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        p = self._provider(mode="readonly")
        with pytest.raises(PermissionError):
            p.upload_file(str(local))
        with pytest.raises(PermissionError):
            p.delete_file("item-1")
        with pytest.raises(PermissionError):
            p.create_folder("x")
        assert not p.graph.calls
