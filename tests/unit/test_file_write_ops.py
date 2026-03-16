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

from iobox.providers.google_drive import FOLDER_MIME_TYPE, GoogleDriveProvider

# ── Helpers ───────────────────────────────────────────────────────────────────

_GDrive_MODULE = "iobox.providers.google_drive"
_OneDrive_MODULE = "iobox.providers.onedrive"
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
    """Smoke tests for OneDriveProvider write methods using HAS_O365 patch."""

    def _make_provider(self, mode: str = "standard") -> Any:  # type: ignore[name-defined]
        from iobox.providers.onedrive import OneDriveProvider

        auth = MagicMock()
        account = MagicMock()
        auth.get_account.return_value = account
        with patch(f"{_OneDrive_MODULE}.HAS_O365", True):
            provider = OneDriveProvider.__new__(OneDriveProvider)
            provider.account_email = "user@example.com"
            provider.credentials_dir = None
            provider.mode = mode
            provider._microsoft_auth = auth
            provider._account = None
        return provider

    def _make_item(self, name: str = "file.txt", is_folder: bool = False) -> MagicMock:
        item = MagicMock()
        item.object_id = "item-1"
        item.name = name
        item.is_folder = is_folder
        item.mime_type = "inode/directory" if is_folder else "text/plain"
        item.size = 1024
        item.created_datetime = None
        item.modified_datetime = None
        item.parent = None
        item.web_url = None
        return item

    def test_check_write_mode_raises_in_readonly(self) -> None:
        from iobox.providers.onedrive import OneDriveProvider

        with patch(f"{_OneDrive_MODULE}.HAS_O365", True):
            provider = OneDriveProvider.__new__(OneDriveProvider)
            provider.mode = "readonly"
        with pytest.raises(PermissionError):
            provider._check_write_mode()

    def test_upload_file(self, tmp_path: Path) -> None:
        local = tmp_path / "test.txt"
        local.write_text("hello")
        provider = self._make_provider()
        item = self._make_item("test.txt")
        drive = provider._microsoft_auth.get_account().storage().get_default_drive()
        drive.get_root_folder().upload_file.return_value = item
        file = provider.upload_file(str(local))
        assert file["name"] == "test.txt"

    def test_upload_to_folder(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        provider = self._make_provider()
        item = self._make_item("doc.txt")
        drive = provider._microsoft_auth.get_account().storage().get_default_drive()
        drive.get_item().upload_file.return_value = item
        provider.upload_file(str(local), parent_id="folder-id")
        drive.get_item.assert_called_with("folder-id")

    def test_upload_blocked_in_readonly(self, tmp_path: Path) -> None:
        local = tmp_path / "doc.txt"
        local.write_text("content")
        provider = self._make_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.upload_file(str(local))

    def test_delete_file(self) -> None:
        provider = self._make_provider()
        item = self._make_item()
        drive = provider._microsoft_auth.get_account().storage().get_default_drive()
        drive.get_item.return_value = item
        provider.delete_file("item-1")
        item.delete.assert_called_once()

    def test_delete_blocked_in_readonly(self) -> None:
        provider = self._make_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.delete_file("item-1")

    def test_create_folder(self) -> None:
        provider = self._make_provider()
        folder_item = self._make_item("Reports", is_folder=True)
        drive = provider._microsoft_auth.get_account().storage().get_default_drive()
        drive.get_root_folder().mkdir.return_value = folder_item
        folder = provider.create_folder("Reports")
        assert folder["name"] == "Reports"

    def test_create_folder_with_parent(self) -> None:
        provider = self._make_provider()
        folder_item = self._make_item("Sub", is_folder=True)
        drive = provider._microsoft_auth.get_account().storage().get_default_drive()
        drive.get_item().mkdir.return_value = folder_item
        provider.create_folder("Sub", parent_id="parent-id")
        drive.get_item.assert_called_with("parent-id")

    def test_create_folder_blocked_in_readonly(self) -> None:
        provider = self._make_provider(mode="readonly")
        with pytest.raises(PermissionError):
            provider.create_folder("My Folder")
