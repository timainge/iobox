"""
Unit tests for OneDriveProvider.

Uses lightweight mock O365 DriveItem objects — no real O365 calls.
The _get_account() path is bypassed by injecting a mock account directly.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import FileQuery
from iobox.providers.o365.files import OneDriveProvider

# ── Mock O365 helpers ─────────────────────────────────────────────────────────


class MockParent:
    def __init__(self, object_id: str = "parent_folder_1") -> None:
        self.object_id = object_id


class MockDriveItem:
    """Minimal mock of a python-o365 DriveItem."""

    def __init__(
        self,
        object_id: str = "item_001",
        name: str = "Q4 Report.docx",
        is_folder: bool = False,
        mime_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size: int = 40960,
        web_url: str = "https://onedrive.live.com/item/item_001",
        created_datetime: datetime | None = None,
        modified_datetime: datetime | None = None,
        parent: Any = None,
        download_content: bytes = b"",
    ) -> None:
        self.object_id = object_id
        self.name = name
        self.is_folder = is_folder
        self.mime_type = mime_type
        self.size = size
        self.web_url = web_url
        self.created_datetime = created_datetime or datetime(2026, 1, 10, tzinfo=timezone.utc)
        self.modified_datetime = modified_datetime or datetime(2026, 3, 10, tzinfo=timezone.utc)
        self.parent = parent
        self._download_content = download_content

    def download(self, output: io.BytesIO) -> None:
        output.write(self._download_content)


class MockDriveFolder(MockDriveItem):
    def __init__(self, items: list[MockDriveItem], **kwargs: Any) -> None:
        super().__init__(is_folder=True, mime_type="", **kwargs)
        self._items = items

    def get_items(self) -> list[MockDriveItem]:
        return self._items


MOCK_WORD_FILE = MockDriveItem(
    object_id="word_001",
    name="Report.docx",
    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size=40960,
)
MOCK_TEXT_FILE = MockDriveItem(
    object_id="txt_002",
    name="notes.txt",
    mime_type="text/plain",
    size=1024,
    web_url="https://onedrive.live.com/item/txt_002",
    download_content=b"Hello from OneDrive",
)
MOCK_FOLDER_ITEM = MockDriveItem(
    object_id="folder_abc",
    name="Documents",
    is_folder=True,
    mime_type=None,  # type: ignore[arg-type]
    size=0,
)


def _make_provider_with_drive(mock_drive: Any) -> OneDriveProvider:
    """Build provider, bypassing auth by injecting a mock account with the given drive."""
    p = OneDriveProvider.__new__(OneDriveProvider)
    p.account_email = "user@company.com"
    p.credentials_dir = None
    p.mode = "readonly"

    mock_account = MagicMock()
    mock_storage = MagicMock()
    mock_storage.get_default_drive.return_value = mock_drive
    mock_account.storage.return_value = mock_storage
    p._account = mock_account
    return p


def _make_mock_drive(items: list[Any]) -> MagicMock:
    drive = MagicMock()
    drive.search.return_value = items
    root = MagicMock()
    root.get_items.return_value = items
    drive.get_root_folder.return_value = root
    return drive


# ── TestOneDriveProviderInit ──────────────────────────────────────────────────


class TestOneDriveProviderInit:
    def test_provider_id(self) -> None:
        assert OneDriveProvider.PROVIDER_ID == "onedrive"

    def test_raises_import_error_without_o365(self) -> None:
        with patch("iobox.providers.o365.files.HAS_O365", False):
            with pytest.raises(ImportError, match="pip install 'iobox\\[outlook\\]'"):
                OneDriveProvider()


# ── TestAuthenticate ──────────────────────────────────────────────────────────


class TestAuthenticate:
    def test_authenticate_triggers_get_account(self) -> None:
        p = _make_provider_with_drive(MagicMock())
        # _account already set — just verify no exception
        p.authenticate()


# ── TestListFiles ─────────────────────────────────────────────────────────────


class TestListFiles:
    def test_list_files_text_search_calls_drive_search(self) -> None:
        drive = _make_mock_drive([MOCK_WORD_FILE])
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(text="Q4", max_results=10))
        drive.search.assert_called_once_with("Q4", limit=10)
        assert len(files) == 1

    def test_list_files_no_text_uses_root(self) -> None:
        drive = _make_mock_drive([MOCK_TEXT_FILE])
        p = _make_provider_with_drive(drive)
        p.list_files(FileQuery(max_results=5))
        drive.get_root_folder().get_items.assert_called_once()

    def test_list_files_folder_id_uses_get_item(self) -> None:
        folder = MockDriveFolder([MOCK_TEXT_FILE], object_id="folder_xyz")
        drive = MagicMock()
        drive.get_item.return_value = folder
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(folder_id="folder_xyz", max_results=10))
        drive.get_item.assert_called_once_with("folder_xyz")
        assert len(files) == 1

    def test_list_files_mime_type_filter(self) -> None:
        items = [MOCK_WORD_FILE, MOCK_TEXT_FILE]
        drive = _make_mock_drive(items)
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(text="Q4", mime_type="text/plain", max_results=10))
        assert len(files) == 1
        assert files[0]["mime_type"] == "text/plain"

    def test_list_files_respects_max_results(self) -> None:
        items = [MOCK_WORD_FILE, MOCK_TEXT_FILE]
        drive = _make_mock_drive(items)
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(text="x", max_results=1))
        assert len(files) == 1

    def test_list_files_returns_list(self) -> None:
        drive = _make_mock_drive([])
        p = _make_provider_with_drive(drive)
        result = p.list_files(FileQuery(max_results=10))
        assert isinstance(result, list)

    def test_list_files_resource_type(self) -> None:
        drive = _make_mock_drive([MOCK_TEXT_FILE])
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(max_results=10))
        assert all(f["resource_type"] == "file" for f in files)

    def test_list_files_provider_id(self) -> None:
        drive = _make_mock_drive([MOCK_TEXT_FILE])
        p = _make_provider_with_drive(drive)
        files = p.list_files(FileQuery(max_results=10))
        assert all(f["provider_id"] == "onedrive" for f in files)


# ── TestGetFile ───────────────────────────────────────────────────────────────


class TestGetFile:
    def test_get_file_returns_file(self) -> None:
        drive = MagicMock()
        drive.get_item.return_value = MOCK_TEXT_FILE
        p = _make_provider_with_drive(drive)
        f = p.get_file("txt_002")
        assert f["id"] == "txt_002"
        assert f["name"] == "notes.txt"

    def test_get_file_not_found_raises(self) -> None:
        drive = MagicMock()
        drive.get_item.return_value = None
        p = _make_provider_with_drive(drive)
        with pytest.raises(KeyError, match="missing_id"):
            p.get_file("missing_id")


# ── TestGetFileContent ────────────────────────────────────────────────────────


class TestGetFileContent:
    def test_office_doc_returns_empty_string(self) -> None:
        drive = MagicMock()
        drive.get_item.return_value = MOCK_WORD_FILE
        p = _make_provider_with_drive(drive)
        result = p.get_file_content("word_001")
        assert result == ""

    def test_text_file_decoded(self) -> None:
        drive = MagicMock()
        drive.get_item.return_value = MOCK_TEXT_FILE
        p = _make_provider_with_drive(drive)
        result = p.get_file_content("txt_002")
        assert result == "Hello from OneDrive"

    def test_item_not_found_returns_empty(self) -> None:
        drive = MagicMock()
        drive.get_item.return_value = None
        p = _make_provider_with_drive(drive)
        result = p.get_file_content("missing")
        assert result == ""

    def test_download_exception_returns_empty(self) -> None:
        class BrokenItem:
            mime_type = "text/plain"

            def download(self, output: io.BytesIO) -> None:
                raise OSError("connection reset")

        drive = MagicMock()
        drive.get_item.return_value = BrokenItem()
        p = _make_provider_with_drive(drive)
        result = p.get_file_content("broken")
        assert result == ""

    def test_msword_legacy_returns_empty(self) -> None:
        item = MockDriveItem(mime_type="application/msword", download_content=b"")
        drive = MagicMock()
        drive.get_item.return_value = item
        p = _make_provider_with_drive(drive)
        result = p.get_file_content("word_old")
        assert result == ""


# ── TestDownloadFile ──────────────────────────────────────────────────────────


class TestDownloadFile:
    def test_download_file_returns_bytes(self) -> None:
        item = MockDriveItem(download_content=b"\x89PNG data")
        drive = MagicMock()
        drive.get_item.return_value = item
        p = _make_provider_with_drive(drive)
        result = p.download_file("img_001")
        assert isinstance(result, bytes)
        assert result == b"\x89PNG data"


# ── TestFileNormalization ─────────────────────────────────────────────────────


class TestFileNormalization:
    def _norm(self, item: MockDriveItem) -> dict:
        p = _make_provider_with_drive(MagicMock())
        return p._o365_item_to_file(item)

    def test_file_item_mapped(self) -> None:
        f = self._norm(MOCK_WORD_FILE)
        assert f["id"] == "word_001"
        assert f["name"] == "Report.docx"
        assert f["title"] == "Report.docx"
        assert f["provider_id"] == "onedrive"
        assert f["resource_type"] == "file"

    def test_folder_is_folder_true(self) -> None:
        f = self._norm(MOCK_FOLDER_ITEM)
        assert f["is_folder"] is True

    def test_folder_mime_type_fallback(self) -> None:
        f = self._norm(MOCK_FOLDER_ITEM)
        assert f["mime_type"] == "inode/directory"

    def test_regular_file_is_folder_false(self) -> None:
        f = self._norm(MOCK_TEXT_FILE)
        assert f["is_folder"] is False

    def test_size_parsed(self) -> None:
        f = self._norm(MOCK_WORD_FILE)
        assert f["size"] == 40960

    def test_size_zero_for_folder(self) -> None:
        f = self._norm(MOCK_FOLDER_ITEM)
        assert f["size"] == 0

    def test_url_from_web_url(self) -> None:
        f = self._norm(MOCK_TEXT_FILE)
        assert f["url"] == "https://onedrive.live.com/item/txt_002"

    def test_parent_id_from_parent(self) -> None:
        item = MockDriveItem(object_id="child", parent=MockParent("parent_123"))
        f = self._norm(item)
        assert f["parent_id"] == "parent_123"

    def test_parent_id_none_when_no_parent(self) -> None:
        item = MockDriveItem(object_id="root_item", parent=None)
        f = self._norm(item)
        assert f["parent_id"] is None

    def test_created_at_and_modified_at(self) -> None:
        dt = datetime(2026, 1, 10, tzinfo=timezone.utc)
        item = MockDriveItem(created_datetime=dt, modified_datetime=dt)
        f = self._norm(item)
        assert "2026-01-10" in f["created_at"]
        assert "2026-01-10" in f["modified_at"]

    def test_content_always_none(self) -> None:
        f = self._norm(MOCK_TEXT_FILE)
        assert f["content"] is None

    def test_path_always_none(self) -> None:
        f = self._norm(MOCK_TEXT_FILE)
        assert f["path"] is None
