"""
Unit tests for OneDriveProvider (read side and normalisation).

Runs the **real** python-o365 ``Storage`` / ``Drive`` / ``DriveItem``
classes over a fake Graph session
(:func:`tests.fixtures.mock_outlook_responses.make_onedrive_provider`), so
attribute names come from the library itself (O365-09: the old code read
``parent`` / ``created_datetime``, which DriveItem does not have).
Write operations are covered in ``test_file_write_ops.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from iobox.providers.base import FileQuery
from iobox.providers.o365.files import OneDriveProvider
from tests.fixtures.mock_outlook_responses import graph_drive_item, make_onedrive_provider

ITEMS = [
    graph_drive_item("f1", name="notes.txt", size=5),
    graph_drive_item(
        "f2",
        name="plan.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    graph_drive_item("d1", name="Reports", folder=True),
    graph_drive_item(
        "f3",
        name="q1.csv",
        mime_type="text/csv",
        parent_id="d1",
        parent_path="/drive/root:/Reports",
    ),
]


@pytest.fixture
def provider() -> OneDriveProvider:
    return make_onedrive_provider(ITEMS, mode="readonly", contents={"f1": b"hello"})


class TestInit:
    def test_provider_id(self) -> None:
        assert OneDriveProvider.PROVIDER_ID == "onedrive"

    def test_raises_import_error_without_o365(self) -> None:
        with (
            patch("iobox.providers.o365.files.HAS_O365", False),
            pytest.raises(ImportError, match="O365"),
        ):
            OneDriveProvider()

    def test_legacy_path_requests_drive_scopes_for_mode(self, tmp_path) -> None:
        pytest.importorskip("O365")
        p = OneDriveProvider(
            account_email="a@b.com", credentials_dir=str(tmp_path), mode="standard"
        )
        with patch("iobox.providers.o365.auth.MicrosoftAuth") as auth_cls:
            p.authenticate()
        kwargs = auth_cls.call_args.kwargs
        assert kwargs["scopes"] == ["basic", "Files.ReadWrite.All"]
        assert kwargs["mode"] == "standard"

    def test_get_profile(self, provider) -> None:
        assert provider.get_profile() == {"name": "OneDrive", "drive_type": "business"}


class TestListFiles:
    def test_root_listing(self, provider) -> None:
        files = provider.list_files(FileQuery(max_results=10))
        assert [f["id"] for f in files] == ["f1", "f2", "d1"]
        call = provider.graph.last("GET", r"/me/drive/items/root-id/children")
        assert call.params["$top"] == 10

    def test_folder_listing(self, provider) -> None:
        files = provider.list_files(FileQuery(folder_id="d1"))
        assert [f["id"] for f in files] == ["f3"]

    def test_text_search_escapes_quotes(self, provider) -> None:
        provider.list_files(FileQuery(text="o'brien"))
        call = provider.graph.last("GET", r"/me/drive/search\(q='.*'\)")
        assert call.path == "/me/drive/search(q='o''brien')"

    def test_shared_with_me(self, provider) -> None:
        """Was a logged no-op; Drive.get_shared_with_me exists in python-o365."""
        provider.list_files(FileQuery(shared_with_me=True))
        provider.graph.last("GET", r"/me/drive/sharedWithMe")

    def test_mime_type_filter(self, provider) -> None:
        files = provider.list_files(FileQuery(mime_type="text/plain"))
        assert [f["id"] for f in files] == ["f1"]

    def test_max_results(self, provider) -> None:
        assert len(provider.list_files(FileQuery(max_results=2))) == 2


class TestGetFile:
    def test_get_file(self, provider) -> None:
        f = provider.get_file("f1")
        assert f["name"] == "notes.txt"
        provider.graph.last("GET", r"/me/drive/items/f1")

    def test_not_found_raises_key_error(self, provider) -> None:
        with pytest.raises(KeyError):
            provider.get_file("missing")


class TestContent:
    def test_text_file_decoded(self, provider) -> None:
        assert provider.get_file_content("f1") == "hello"
        provider.graph.last("GET", r"/me/drive/items/f1/content")

    def test_office_doc_returns_empty(self, provider) -> None:
        assert provider.get_file_content("f2") == ""
        assert not provider.graph.find("GET", r".*/content")

    def test_missing_returns_empty(self, provider) -> None:
        assert provider.get_file_content("missing") == ""

    def test_download_failure_returns_empty(self, provider) -> None:
        provider.graph.route("GET", r"/me/drive/items/f1/content", {"error": {}}, status=500)
        assert provider.get_file_content("f1") == ""

    def test_download_file_bytes(self, provider) -> None:
        assert provider.download_file("f1") == b"hello"

    def test_download_failure_raises(self, provider) -> None:
        """DriveItem.download() returns False instead of raising."""
        provider.graph.route("GET", r"/me/drive/items/f1/content", {"error": {}}, status=500)
        with pytest.raises(RuntimeError, match="Failed to download"):
            provider.download_file("f1")

    def test_download_folder_rejected(self, provider) -> None:
        with pytest.raises(ValueError, match="folder"):
            provider.download_file("d1")


class TestNormalization:
    def test_file_fields(self, provider) -> None:
        f = provider.get_file("f1")
        assert f["provider_id"] == "onedrive"
        assert f["resource_type"] == "file"
        assert f["title"] == f["name"] == "notes.txt"
        assert f["mime_type"] == "text/plain"
        assert f["size"] == 5
        assert f["is_folder"] is False
        assert f["url"] == "https://onedrive.live.com/?id=f1"
        assert f["content"] is None

    def test_dates_from_created_and_modified(self, provider) -> None:
        f = provider.get_file("f1")
        assert f["created_at"].startswith("2026-01-01T00:00:00")
        assert f["modified_at"].startswith("2026-03-01T12:00:00")

    def test_parent_id_and_path(self, provider) -> None:
        f = provider.get_file("f3")
        assert f["parent_id"] == "d1"
        assert f["path"] == "/Reports/q1.csv"
        assert provider.get_file("f1")["path"] == "/notes.txt"

    def test_folder(self, provider) -> None:
        d = provider.get_file("d1")
        assert d["is_folder"] is True
        assert d["mime_type"] == "inode/directory"
