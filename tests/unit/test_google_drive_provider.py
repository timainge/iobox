"""
Unit tests for GoogleDriveProvider.

Uses _service_fn= injection so no real OAuth or googleapiclient calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iobox.providers.base import FileQuery
from iobox.providers.google.files import (
    FOLDER_MIME_TYPE,
    GOOGLE_WORKSPACE_EXPORT_TYPES,
    GoogleDriveProvider,
)
from tests.fixtures.mock_drive_responses import (
    MOCK_ABOUT_RESPONSE,
    MOCK_FOLDER,
    MOCK_GDOC_FILE,
    MOCK_LIST_RESPONSE,
    MOCK_LIST_RESPONSE_PAGINATED_PAGE1,
    MOCK_LIST_RESPONSE_PAGINATED_PAGE2,
    MOCK_LIST_RESPONSE_WITH_TRASHED,
    MOCK_PDF_FILE,
    MOCK_TEXT_FILE,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return auth


@pytest.fixture
def provider(mock_auth: MagicMock) -> GoogleDriveProvider:
    return GoogleDriveProvider(auth=mock_auth)


@pytest.fixture
def mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.files().list().execute.return_value = MOCK_LIST_RESPONSE
    return svc


# ── TestGoogleDriveProviderInit ───────────────────────────────────────────────


class TestGoogleDriveProviderInit:
    def test_accepts_auth_directly(self, mock_auth: MagicMock) -> None:
        p = GoogleDriveProvider(auth=mock_auth)
        assert p._auth is mock_auth

    def test_creates_auth_from_account_params(self, tmp_path: object) -> None:
        from iobox.providers.google.auth import GoogleAuth

        p = GoogleDriveProvider(
            account="test@gmail.com",
            credentials_dir=str(tmp_path),  # type: ignore[arg-type]
            mode="readonly",
        )
        assert isinstance(p._auth, GoogleAuth)

    def test_provider_id(self, provider: GoogleDriveProvider) -> None:
        assert provider.PROVIDER_ID == "google_drive"


# ── TestAuthenticate ──────────────────────────────────────────────────────────


class TestAuthenticate:
    def test_authenticate_calls_get_credentials(
        self, provider: GoogleDriveProvider, mock_auth: MagicMock
    ) -> None:
        provider.authenticate()
        mock_auth.get_credentials.assert_called_once()


# ── TestGetProfile ────────────────────────────────────────────────────────────


class TestGetProfile:
    def test_get_profile_returns_email_and_name(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.about().get().execute.return_value = MOCK_ABOUT_RESPONSE
        result = provider.get_profile(_service_fn=svc)
        assert result["email"] == "tim@gmail.com"
        assert result["display_name"] == "Tim"

    def test_get_profile_calls_about_get_with_user_fields(
        self, provider: GoogleDriveProvider
    ) -> None:
        svc = MagicMock()
        svc.about().get().execute.return_value = MOCK_ABOUT_RESPONSE
        provider.get_profile(_service_fn=svc)
        svc.about().get.assert_called_with(fields="user")


# ── TestListFiles ─────────────────────────────────────────────────────────────


class TestListFiles:
    def test_list_files_basic(self, provider: GoogleDriveProvider, mock_svc: MagicMock) -> None:
        files = provider.list_files(FileQuery(max_results=10), _service_fn=mock_svc)
        assert len(files) == 2

    def test_list_files_resource_type(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        files = provider.list_files(FileQuery(max_results=10), _service_fn=mock_svc)
        assert all(f["resource_type"] == "file" for f in files)

    def test_list_files_provider_id(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        files = provider.list_files(FileQuery(max_results=10), _service_fn=mock_svc)
        assert all(f["provider_id"] == "google_drive" for f in files)

    def test_list_files_text_search(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_files(FileQuery(text="Q4", max_results=10), _service_fn=mock_svc)
        q = mock_svc.files().list.call_args.kwargs["q"]
        assert "fullText contains 'Q4'" in q

    def test_list_files_skips_trashed(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().list().execute.return_value = MOCK_LIST_RESPONSE_WITH_TRASHED
        files = provider.list_files(FileQuery(max_results=10), _service_fn=svc)
        assert len(files) == 2  # trashed file excluded
        assert all(not f.get("trashed", False) for f in files)

    def test_list_files_respects_max_results(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        files = provider.list_files(FileQuery(max_results=1), _service_fn=mock_svc)
        assert len(files) == 1

    def test_list_files_pagination(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().list().execute.side_effect = [
            MOCK_LIST_RESPONSE_PAGINATED_PAGE1,
            MOCK_LIST_RESPONSE_PAGINATED_PAGE2,
        ]
        files = provider.list_files(FileQuery(max_results=10), _service_fn=svc)
        assert len(files) == 2
        assert svc.files().list().execute.call_count == 2

    def test_list_files_uses_corpora_user(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_files(FileQuery(max_results=5), _service_fn=mock_svc)
        call_kwargs = mock_svc.files().list.call_args.kwargs
        assert call_kwargs["corpora"] == "user"

    def test_list_files_query_always_excludes_trashed(
        self, provider: GoogleDriveProvider, mock_svc: MagicMock
    ) -> None:
        provider.list_files(FileQuery(max_results=5), _service_fn=mock_svc)
        q = mock_svc.files().list.call_args.kwargs["q"]
        assert "trashed = false" in q


# ── TestBuildDriveQuery ───────────────────────────────────────────────────────


class TestBuildDriveQuery:
    def _build(self, **kwargs: object) -> str:
        p = GoogleDriveProvider(auth=MagicMock())
        return p._build_drive_query(FileQuery(**kwargs))  # type: ignore[arg-type]

    def test_empty_query_only_trashed_false(self) -> None:
        q = self._build()
        assert q == "trashed = false"

    def test_text_filter(self) -> None:
        q = self._build(text="Q4 report")
        assert "fullText contains 'Q4 report'" in q
        assert "trashed = false" in q

    def test_text_escapes_single_quotes(self) -> None:
        q = self._build(text="it's here")
        assert "fullText contains 'it\\'s here'" in q

    def test_mime_type_filter(self) -> None:
        q = self._build(mime_type="application/pdf")
        assert "mimeType = 'application/pdf'" in q

    def test_folder_id_filter(self) -> None:
        q = self._build(folder_id="folder_abc")
        assert "'folder_abc' in parents" in q

    def test_shared_with_me(self) -> None:
        q = self._build(shared_with_me=True)
        assert "sharedWithMe = true" in q

    def test_combined_filters(self) -> None:
        q = self._build(text="Q4", mime_type="application/pdf", folder_id="f1")
        assert "trashed = false" in q
        assert "fullText contains 'Q4'" in q
        assert "mimeType = 'application/pdf'" in q
        assert "'f1' in parents" in q

    def test_filters_joined_with_and(self) -> None:
        q = self._build(text="foo", mime_type="text/plain")
        parts = q.split(" and ")
        assert len(parts) == 3  # trashed + text + mime


# ── TestFileNormalization ─────────────────────────────────────────────────────


class TestFileNormalization:
    def _norm(self, raw: dict) -> dict:
        p = GoogleDriveProvider(auth=MagicMock())
        return p._drive_file_to_file(raw)

    def test_google_doc_maps_to_file(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["id"] == "doc_001"
        assert f["name"] == "Q4 Planning Notes"
        assert f["mime_type"] == "application/vnd.google-apps.document"
        assert f["resource_type"] == "file"
        assert f["provider_id"] == "google_drive"

    def test_google_doc_size_is_zero(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["size"] == 0

    def test_pdf_size_parsed(self) -> None:
        f = self._norm(MOCK_PDF_FILE)
        assert f["size"] == 204800

    def test_folder_is_folder_true(self) -> None:
        f = self._norm(MOCK_FOLDER)
        assert f["is_folder"] is True

    def test_regular_file_is_folder_false(self) -> None:
        f = self._norm(MOCK_PDF_FILE)
        assert f["is_folder"] is False

    def test_parent_id_from_parents(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["parent_id"] == "folder_abc"

    def test_parent_id_none_when_no_parents(self) -> None:
        raw = {**MOCK_GDOC_FILE, "parents": None}
        f = self._norm(raw)
        assert f["parent_id"] is None

    def test_url_from_web_view_link(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["url"] == "https://docs.google.com/document/d/doc_001"

    def test_created_at_and_modified_at(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["created_at"] == "2026-01-10T10:00:00.000Z"
        assert f["modified_at"] == "2026-03-10T15:00:00.000Z"

    def test_title_equals_name(self) -> None:
        f = self._norm(MOCK_PDF_FILE)
        assert f["title"] == f["name"] == "budget.pdf"

    def test_content_is_none(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["content"] is None

    def test_path_is_none(self) -> None:
        f = self._norm(MOCK_GDOC_FILE)
        assert f["path"] is None


# ── TestGetFile ───────────────────────────────────────────────────────────────


class TestGetFile:
    def test_get_file_returns_file(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_PDF_FILE
        f = provider.get_file("pdf_002", _service_fn=svc)
        assert f["id"] == "pdf_002"

    def test_get_file_calls_correct_api(self, provider: GoogleDriveProvider) -> None:
        from iobox.providers.google.files import FILE_FIELDS

        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_PDF_FILE
        provider.get_file("pdf_002", _service_fn=svc)
        svc.files().get.assert_called_with(fileId="pdf_002", fields=FILE_FIELDS)


# ── TestGetFileContent ────────────────────────────────────────────────────────


class TestGetFileContent:
    def test_google_doc_exported_as_text(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        # get_file calls files().get().execute
        svc.files().get().execute.return_value = MOCK_GDOC_FILE
        svc.files().export().execute.return_value = b"Exported text content"
        result = provider.get_file_content("doc_001", _service_fn=svc)
        assert result == "Exported text content"
        svc.files().export.assert_called_with(fileId="doc_001", mimeType="text/plain")

    def test_text_file_downloaded(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_TEXT_FILE
        svc.files().get_media().execute.return_value = b"Plain text content"
        result = provider.get_file_content("txt_003", _service_fn=svc)
        assert result == "Plain text content"

    def test_binary_file_returns_empty_string(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_PDF_FILE
        result = provider.get_file_content("pdf_002", _service_fn=svc)
        assert result == ""

    def test_bytes_content_decoded(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_GDOC_FILE
        svc.files().export().execute.return_value = b"caf\xc3\xa9"
        result = provider.get_file_content("doc_001", _service_fn=svc)
        assert result == "café"

    def test_string_content_passthrough(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get().execute.return_value = MOCK_GDOC_FILE
        svc.files().export().execute.return_value = "Already a string"
        result = provider.get_file_content("doc_001", _service_fn=svc)
        assert result == "Already a string"


# ── TestDownloadFile ──────────────────────────────────────────────────────────


class TestDownloadFile:
    def test_download_file_returns_bytes(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get_media().execute.return_value = b"\x89PNG\r\n"
        result = provider.download_file("img_001", _service_fn=svc)
        assert isinstance(result, bytes)
        assert result == b"\x89PNG\r\n"

    def test_download_file_calls_get_media(self, provider: GoogleDriveProvider) -> None:
        svc = MagicMock()
        svc.files().get_media().execute.return_value = b"data"
        provider.download_file("img_001", _service_fn=svc)
        svc.files().get_media.assert_called_with(fileId="img_001")


# ── TestGoogleWorkspaceExportTypes ────────────────────────────────────────────


class TestGoogleWorkspaceExportTypes:
    def test_document_exports_as_text_plain(self) -> None:
        assert GOOGLE_WORKSPACE_EXPORT_TYPES["application/vnd.google-apps.document"] == "text/plain"

    def test_spreadsheet_exports_as_csv(self) -> None:
        key = "application/vnd.google-apps.spreadsheet"
        assert GOOGLE_WORKSPACE_EXPORT_TYPES[key] == "text/csv"

    def test_presentation_exports_as_text_plain(self) -> None:
        key = "application/vnd.google-apps.presentation"
        assert GOOGLE_WORKSPACE_EXPORT_TYPES[key] == "text/plain"

    def test_folder_mime_type_constant(self) -> None:
        assert FOLDER_MIME_TYPE == "application/vnd.google-apps.folder"
