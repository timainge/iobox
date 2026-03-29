"""
Shared ABC contract tests for EmailProvider implementations.

Verifies that both GmailProvider and OutlookProvider:
1. Implement all abstract methods defined in EmailProvider
2. Return correct types from key methods
3. Produce EmailData dicts with all required keys
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from iobox.providers.base import (
    CalendarProvider,
    EmailProvider,
    EmailQuery,
    EventQuery,
    FileProvider,
    FileQuery,
)
from iobox.providers.google.email import GmailProvider
from iobox.providers.google.calendar import GoogleCalendarProvider
from iobox.providers.google.files import GoogleDriveProvider
from iobox.providers.o365.email import OutlookProvider
from tests.fixtures.mock_calendar_responses import MOCK_LIST_RESPONSE, MOCK_SYNC_RESPONSE
from tests.fixtures.mock_drive_responses import MOCK_LIST_RESPONSE as MOCK_DRIVE_LIST_RESPONSE
from tests.fixtures.mock_outlook_responses import (
    MockHttpResponse,
    make_full_mock_account,
    make_mock_message,
)

# ---------------------------------------------------------------------------
# Required keys that must be present in every EmailData dict
# ---------------------------------------------------------------------------

REQUIRED_EMAILDATA_KEYS = {
    "message_id",
    "subject",
    "from_",
    "date",
    "snippet",
    "labels",
    "thread_id",
}

FULL_RETRIEVAL_KEYS = {"body", "content_type", "attachments"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gmail_provider():
    """Return a GmailProvider with a mock Gmail service."""
    p = GmailProvider()
    p._service = MagicMock(name="gmail_service")
    return p


@pytest.fixture
def outlook_provider():
    """Return an OutlookProvider with a full mock account."""
    p = OutlookProvider()
    account = make_full_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    return p


# ---------------------------------------------------------------------------
# 1. Both providers implement all abstract methods
# ---------------------------------------------------------------------------


class TestABCCompleteness:
    """Verify both provider classes implement every abstract method."""

    def _get_abstract_methods(self) -> set[str]:
        """Return names of all abstract methods on EmailProvider."""
        return {
            name
            for name, _ in inspect.getmembers(EmailProvider, predicate=inspect.isfunction)
            if getattr(getattr(EmailProvider, name), "__isabstractmethod__", False)
        }

    def test_gmail_implements_all_abstract_methods(self):
        abstract = self._get_abstract_methods()
        assert abstract, "EmailProvider should have abstract methods"
        for method_name in abstract:
            assert hasattr(GmailProvider, method_name), (
                f"GmailProvider missing abstract method: {method_name}"
            )
            # Ensure it's actually implemented (not still abstract)
            method = getattr(GmailProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False), (
                f"GmailProvider.{method_name} is still abstract"
            )

    def test_outlook_implements_all_abstract_methods(self):
        abstract = self._get_abstract_methods()
        assert abstract, "EmailProvider should have abstract methods"
        for method_name in abstract:
            assert hasattr(OutlookProvider, method_name), (
                f"OutlookProvider missing abstract method: {method_name}"
            )
            method = getattr(OutlookProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False), (
                f"OutlookProvider.{method_name} is still abstract"
            )

    def test_providers_are_subclasses_of_email_provider(self):
        assert issubclass(GmailProvider, EmailProvider)
        assert issubclass(OutlookProvider, EmailProvider)

    def test_providers_are_instantiable(self):
        """Non-abstract classes should be instantiable without errors."""
        # GmailProvider() and OutlookProvider() should not raise TypeError
        # (which ABC raises for unimplemented abstract methods)
        g = GmailProvider()
        o = OutlookProvider()
        assert isinstance(g, EmailProvider)
        assert isinstance(o, EmailProvider)

    def test_abstract_method_count(self):
        """Guard against forgetting to check newly added methods."""
        abstract = self._get_abstract_methods()
        # If a new abstract method is added to EmailProvider, this count
        # will need updating — which forces adding contract tests.
        assert len(abstract) >= 20, (
            f"Expected at least 20 abstract methods, got {len(abstract)}. "
            "Update this test if new methods were intentionally added."
        )


# ---------------------------------------------------------------------------
# 2. Return types from key methods
# ---------------------------------------------------------------------------


class TestGmailReturnTypes:
    """Verify GmailProvider methods return correct types."""

    @patch("iobox.providers.google._retrieval.get_label_map", return_value={})
    @patch("iobox.providers.google._search.search_emails", return_value=[])
    def test_search_emails_returns_list(self, _mock_search, _mock_labels, gmail_provider):
        result = gmail_provider.search_emails(EmailQuery(text="test"))
        assert isinstance(result, list)

    @patch("iobox.providers.google._retrieval.get_label_map", return_value={})
    @patch("iobox.providers.google._search.search_emails")
    def test_search_emails_items_are_dicts(self, mock_search, _mock_labels, gmail_provider):
        mock_search.return_value = [{"message_id": "m1", "from": "a@b.com"}]
        result = gmail_provider.search_emails(EmailQuery(text="test"))
        assert len(result) == 1
        assert isinstance(result[0], dict)

    @patch("iobox.providers.google._retrieval.get_label_map", return_value={})
    @patch("iobox.providers.google._retrieval.get_email_content")
    def test_get_email_content_returns_dict(self, mock_get, _mock_labels, gmail_provider):
        mock_get.return_value = {
            "message_id": "m1",
            "body": "text",
            "content_type": "text/plain",
        }
        result = gmail_provider.get_email_content("m1")
        assert isinstance(result, dict)

    @patch("iobox.providers.google._retrieval.get_label_map", return_value={})
    @patch("iobox.providers.google._retrieval.batch_get_emails")
    def test_batch_get_emails_returns_list(self, mock_batch, _mock_labels, gmail_provider):
        mock_batch.return_value = [{"message_id": "m1"}, {"message_id": "m2"}]
        result = gmail_provider.batch_get_emails(["m1", "m2"])
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    @patch("iobox.providers.google._retrieval.get_thread_content")
    def test_get_thread_returns_list(self, mock_thread, gmail_provider):
        mock_thread.return_value = [{"message_id": "m1"}]
        result = gmail_provider.get_thread("t1")
        assert isinstance(result, list)

    @patch("iobox.providers.google._retrieval.download_attachment")
    def test_download_attachment_returns_bytes(self, mock_dl, gmail_provider):
        mock_dl.return_value = b"\x89PNG"
        result = gmail_provider.download_attachment("m1", "att1")
        assert isinstance(result, bytes)

    @patch("iobox.providers.google.auth.get_gmail_profile")
    def test_get_sync_state_returns_str(self, mock_profile, gmail_provider):
        mock_profile.return_value = {"historyId": "12345"}
        result = gmail_provider.get_sync_state()
        assert isinstance(result, str)

    @patch("iobox.providers.google._retrieval.get_label_map")
    def test_list_tags_returns_dict(self, mock_labels, gmail_provider):
        mock_labels.return_value = {"INBOX": "INBOX"}
        result = gmail_provider.list_tags()
        assert isinstance(result, dict)

    @patch("iobox.providers.google.auth.get_gmail_profile")
    @patch("iobox.providers.google._search.get_new_messages")
    def test_get_new_messages_with_token_returns_tuple(
        self, mock_get_new, mock_profile, gmail_provider
    ):
        mock_get_new.return_value = ["m1", "m2"]
        mock_profile.return_value = {"historyId": "99999"}
        result = gmail_provider.get_new_messages_with_token("12345")
        assert isinstance(result, tuple)
        message_ids, new_token = result
        assert isinstance(message_ids, list)
        assert isinstance(new_token, str)
        assert message_ids == ["m1", "m2"]
        assert new_token == "99999"

    @patch("iobox.providers.google._search.get_new_messages")
    def test_get_new_messages_with_token_returns_none_on_expiry(self, mock_get_new, gmail_provider):
        mock_get_new.return_value = None
        result = gmail_provider.get_new_messages_with_token("expired-token")
        assert result is None


class TestOutlookReturnTypes:
    """Verify OutlookProvider methods return correct types."""

    def test_search_emails_returns_list(self, outlook_provider):
        result = outlook_provider.search_emails(EmailQuery(text="test"))
        assert isinstance(result, list)

    def test_search_emails_items_are_dicts(self, outlook_provider):
        result = outlook_provider.search_emails(EmailQuery())
        assert all(isinstance(item, dict) for item in result)

    def test_get_email_content_returns_dict(self, outlook_provider):
        result = outlook_provider.get_email_content("outlook-msg-id-1")
        assert isinstance(result, dict)

    def test_batch_get_emails_returns_list(self, outlook_provider):
        result = outlook_provider.batch_get_emails(["outlook-msg-id-1", "outlook-msg-id-2"])
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_get_thread_returns_list(self, outlook_provider):
        result = outlook_provider.get_thread("outlook-conv-thread-1")
        assert isinstance(result, list)

    def test_download_attachment_returns_bytes(self, outlook_provider):
        result = outlook_provider.download_attachment("outlook-msg-id-3", "outlook-attach-id-1")
        assert isinstance(result, bytes)

    def test_get_profile_returns_dict(self, outlook_provider):
        result = outlook_provider.get_profile()
        assert isinstance(result, dict)

    def test_list_drafts_returns_list(self, outlook_provider):
        result = outlook_provider.list_drafts()
        assert isinstance(result, list)

    def test_list_tags_returns_dict(self, outlook_provider):
        # Mock the protocol attribute and register a response
        con = outlook_provider._account.con
        con.protocol = MagicMock()
        con.protocol.service_url = "https://graph.microsoft.com/v1.0"
        url = "https://graph.microsoft.com/v1.0/me/outlook/masterCategories"
        con._delta_responses[url] = {"value": [{"displayName": "Work"}]}
        result = outlook_provider.list_tags()
        assert isinstance(result, dict)

    def test_get_new_messages_with_token_returns_tuple(self, outlook_provider):
        delta_link = "https://graph.microsoft.com/v1.0/delta?token=abc"
        new_delta = "https://graph.microsoft.com/v1.0/delta?token=def"
        outlook_provider._account.con._delta_responses[delta_link] = {
            "value": [{"id": "msg-a"}, {"id": "msg-b"}],
            "@odata.deltaLink": new_delta,
        }
        result = outlook_provider.get_new_messages_with_token(delta_link)
        assert result is not None
        message_ids, new_token = result
        assert isinstance(message_ids, list)
        assert isinstance(new_token, str)
        assert message_ids == ["msg-a", "msg-b"]
        assert new_token == new_delta

    def test_get_new_messages_with_token_returns_none_on_expiry(self, outlook_provider):
        gone_resp = MockHttpResponse({})
        gone_resp.status_code = 410
        outlook_provider._account.con.get = MagicMock(return_value=gone_resp)
        result = outlook_provider.get_new_messages_with_token(
            "https://graph.microsoft.com/v1.0/delta?token=expired"
        )
        assert result is None


# ---------------------------------------------------------------------------
# 3. EmailData required keys
# ---------------------------------------------------------------------------


class TestGmailEmailDataKeys:
    """Verify GmailProvider produces EmailData with all required keys."""

    def test_to_email_data_has_required_keys(self, gmail_provider):
        raw = {
            "message_id": "m1",
            "subject": "Test",
            "from": "Alice <alice@x.com>",
            "date": "2024-01-15",
            "snippet": "Preview",
            "labels": ["INBOX"],
            "thread_id": "t1",
        }
        data = gmail_provider._to_email_data(raw)
        for key in REQUIRED_EMAILDATA_KEYS:
            assert key in data, f"Missing required key: {key}"

    def test_to_email_data_full_retrieval_has_all_keys(self, gmail_provider):
        raw = {
            "message_id": "m1",
            "subject": "Test",
            "from": "Alice <alice@x.com>",
            "date": "2024-01-15",
            "snippet": "Preview",
            "labels": ["INBOX"],
            "thread_id": "t1",
            "body": "<p>Hello</p>",
            "content_type": "text/html",
            "attachments": [],
        }
        data = gmail_provider._to_email_data(raw)
        for key in REQUIRED_EMAILDATA_KEYS | FULL_RETRIEVAL_KEYS:
            assert key in data, f"Missing key: {key}"

    def test_to_email_data_empty_input_has_required_keys(self, gmail_provider):
        """Even with empty input, all required keys must be present."""
        data = gmail_provider._to_email_data({})
        for key in REQUIRED_EMAILDATA_KEYS:
            assert key in data, f"Missing required key: {key}"

    def test_to_email_data_labels_is_list(self, gmail_provider):
        data = gmail_provider._to_email_data({"labels": ["INBOX", "STARRED"]})
        assert isinstance(data["labels"], list)

    @patch("iobox.providers.google._retrieval.get_label_map", return_value={})
    @patch("iobox.providers.google._search.search_emails")
    def test_search_results_have_required_keys(self, mock_search, _mock_labels, gmail_provider):
        mock_search.return_value = [
            {
                "message_id": "m1",
                "subject": "Hi",
                "from": "a@b.com",
                "date": "2024-01-01",
                "snippet": "hello",
                "labels": [],
                "thread_id": "t1",
            }
        ]
        results = gmail_provider.search_emails(EmailQuery(text="test"))
        for result in results:
            for key in REQUIRED_EMAILDATA_KEYS:
                assert key in result, f"Search result missing key: {key}"


class TestOutlookEmailDataKeys:
    """Verify OutlookProvider produces EmailData with all required keys."""

    def test_message_to_email_data_has_required_keys(self, outlook_provider):
        msg = make_mock_message()
        data = outlook_provider._message_to_email_data(msg, include_body=False)
        for key in REQUIRED_EMAILDATA_KEYS:
            assert key in data, f"Missing required key: {key}"

    def test_message_to_email_data_full_has_all_keys(self, outlook_provider):
        msg = make_mock_message()
        data = outlook_provider._message_to_email_data(msg, include_body=True)
        for key in REQUIRED_EMAILDATA_KEYS | FULL_RETRIEVAL_KEYS:
            assert key in data, f"Missing key: {key}"

    def test_message_to_email_data_labels_is_list(self, outlook_provider):
        msg = make_mock_message(categories=["Work", "Important"])
        data = outlook_provider._message_to_email_data(msg, include_body=False)
        assert isinstance(data["labels"], list)
        assert data["labels"] == ["Work", "Important"]

    def test_search_results_have_required_keys(self, outlook_provider):
        results = outlook_provider.search_emails(EmailQuery())
        for result in results:
            for key in REQUIRED_EMAILDATA_KEYS:
                assert key in result, f"Search result missing key: {key}"

    def test_get_email_content_has_all_keys(self, outlook_provider):
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        for key in REQUIRED_EMAILDATA_KEYS | FULL_RETRIEVAL_KEYS:
            assert key in data, f"Full content missing key: {key}"

    def test_batch_results_have_required_keys(self, outlook_provider):
        results = outlook_provider.batch_get_emails(["outlook-msg-id-1"])
        for result in results:
            for key in REQUIRED_EMAILDATA_KEYS | FULL_RETRIEVAL_KEYS:
                assert key in result, f"Batch result missing key: {key}"


# ---------------------------------------------------------------------------
# 4. EmailData value types
# ---------------------------------------------------------------------------


class TestEmailDataValueTypes:
    """Verify that EmailData field values have correct types in both providers."""

    def test_gmail_field_types(self, gmail_provider):
        raw = {
            "message_id": "m1",
            "subject": "Test",
            "from": "Alice <alice@x.com>",
            "date": "2024-01-15",
            "snippet": "Preview",
            "labels": ["INBOX"],
            "thread_id": "t1",
            "body": "<p>Hello</p>",
            "content_type": "text/html",
            "attachments": [
                {"id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}
            ],
        }
        data = gmail_provider._to_email_data(raw)
        assert isinstance(data["message_id"], str)
        assert isinstance(data["subject"], str)
        assert isinstance(data["from_"], str)
        assert isinstance(data["date"], str)
        assert isinstance(data["snippet"], str)
        assert isinstance(data["labels"], list)
        assert isinstance(data["thread_id"], str)
        assert isinstance(data["body"], str)
        assert isinstance(data["content_type"], str)
        assert isinstance(data["attachments"], list)

    def test_outlook_field_types(self, outlook_provider):
        msg = make_mock_message(has_attachments=False)
        data = outlook_provider._message_to_email_data(msg, include_body=True)
        assert isinstance(data["message_id"], str)
        assert isinstance(data["subject"], str)
        assert isinstance(data["from_"], str)
        assert isinstance(data["date"], str)
        assert isinstance(data["snippet"], str)
        assert isinstance(data["labels"], list)
        assert isinstance(data["thread_id"], str)
        assert isinstance(data["body"], str)
        assert isinstance(data["content_type"], str)
        assert isinstance(data["attachments"], list)


# ---------------------------------------------------------------------------
# 5. CalendarProvider — GoogleCalendarProvider contract
# ---------------------------------------------------------------------------

REQUIRED_EVENT_KEYS = {
    "id",
    "provider_id",
    "resource_type",
    "title",
    "created_at",
    "modified_at",
    "start",
    "end",
    "all_day",
    "attendees",
}


@pytest.fixture
def google_calendar_provider() -> GoogleCalendarProvider:
    """Return a GoogleCalendarProvider with a mocked auth object."""
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return GoogleCalendarProvider(auth=auth)


@pytest.fixture
def mock_calendar_svc() -> MagicMock:
    svc = MagicMock()
    svc.events().list().execute.return_value = MOCK_LIST_RESPONSE
    return svc


class TestCalendarProviderABCCompleteness:
    """Verify GoogleCalendarProvider implements all abstract methods on CalendarProvider."""

    def _get_abstract_methods(self) -> set[str]:
        import inspect

        return {
            name
            for name, _ in inspect.getmembers(CalendarProvider, predicate=inspect.isfunction)
            if getattr(getattr(CalendarProvider, name), "__isabstractmethod__", False)
        }

    def test_google_calendar_implements_all_abstract_methods(self) -> None:
        abstract = self._get_abstract_methods()
        assert abstract, "CalendarProvider should have abstract methods"
        for method_name in abstract:
            assert hasattr(GoogleCalendarProvider, method_name), (
                f"GoogleCalendarProvider missing: {method_name}"
            )
            method = getattr(GoogleCalendarProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False), (
                f"GoogleCalendarProvider.{method_name} is still abstract"
            )

    def test_is_subclass_of_calendar_provider(self) -> None:
        assert issubclass(GoogleCalendarProvider, CalendarProvider)

    def test_is_instantiable_with_auth(self) -> None:
        auth = MagicMock()
        p = GoogleCalendarProvider(auth=auth)
        assert isinstance(p, CalendarProvider)


class TestGoogleCalendarReturnTypes:
    """Verify GoogleCalendarProvider methods return correct types."""

    def test_list_events_returns_list(
        self,
        google_calendar_provider: GoogleCalendarProvider,
        mock_calendar_svc: MagicMock,
    ) -> None:
        result = google_calendar_provider.list_events(
            EventQuery(max_results=10), _service_fn=mock_calendar_svc
        )
        assert isinstance(result, list)

    def test_list_events_items_are_dicts(
        self,
        google_calendar_provider: GoogleCalendarProvider,
        mock_calendar_svc: MagicMock,
    ) -> None:
        result = google_calendar_provider.list_events(
            EventQuery(max_results=10), _service_fn=mock_calendar_svc
        )
        assert all(isinstance(e, dict) for e in result)

    def test_list_events_have_required_keys(
        self,
        google_calendar_provider: GoogleCalendarProvider,
        mock_calendar_svc: MagicMock,
    ) -> None:
        result = google_calendar_provider.list_events(
            EventQuery(max_results=10), _service_fn=mock_calendar_svc
        )
        for event in result:
            for key in REQUIRED_EVENT_KEYS:
                assert key in event, f"Event missing required key: {key}"

    def test_get_sync_state_returns_dict(
        self,
        google_calendar_provider: GoogleCalendarProvider,
    ) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = {"nextSyncToken": "tok"}
        result = google_calendar_provider.get_sync_state(_service_fn=svc)
        assert isinstance(result, dict)

    def test_get_new_events_returns_tuple(
        self,
        google_calendar_provider: GoogleCalendarProvider,
    ) -> None:
        svc = MagicMock()
        svc.events().list().execute.return_value = MOCK_SYNC_RESPONSE
        events, token = google_calendar_provider.get_new_events("tok", _service_fn=svc)
        assert isinstance(events, list)
        assert isinstance(token, str)


# ---------------------------------------------------------------------------
# 6. FileProvider — GoogleDriveProvider contract
# ---------------------------------------------------------------------------

REQUIRED_FILE_KEYS = {
    "id",
    "provider_id",
    "resource_type",
    "title",
    "created_at",
    "modified_at",
    "name",
    "mime_type",
    "size",
    "is_folder",
}


@pytest.fixture
def google_drive_provider() -> GoogleDriveProvider:
    """Return a GoogleDriveProvider with a mocked auth object."""
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return GoogleDriveProvider(auth=auth)


@pytest.fixture
def mock_drive_svc() -> MagicMock:
    svc = MagicMock()
    svc.files().list().execute.return_value = MOCK_DRIVE_LIST_RESPONSE
    return svc


class TestFileProviderABCCompleteness:
    """Verify GoogleDriveProvider implements all abstract methods on FileProvider."""

    def _get_abstract_methods(self) -> set[str]:
        import inspect

        return {
            name
            for name, _ in inspect.getmembers(FileProvider, predicate=inspect.isfunction)
            if getattr(getattr(FileProvider, name), "__isabstractmethod__", False)
        }

    def test_google_drive_implements_all_abstract_methods(self) -> None:
        abstract = self._get_abstract_methods()
        assert abstract, "FileProvider should have abstract methods"
        for method_name in abstract:
            assert hasattr(GoogleDriveProvider, method_name), (
                f"GoogleDriveProvider missing: {method_name}"
            )
            method = getattr(GoogleDriveProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False), (
                f"GoogleDriveProvider.{method_name} is still abstract"
            )

    def test_is_subclass_of_file_provider(self) -> None:
        assert issubclass(GoogleDriveProvider, FileProvider)

    def test_is_instantiable_with_auth(self) -> None:
        auth = MagicMock()
        p = GoogleDriveProvider(auth=auth)
        assert isinstance(p, FileProvider)


class TestGoogleDriveReturnTypes:
    """Verify GoogleDriveProvider methods return correct types."""

    def test_list_files_returns_list(
        self,
        google_drive_provider: GoogleDriveProvider,
        mock_drive_svc: MagicMock,
    ) -> None:
        result = google_drive_provider.list_files(
            FileQuery(max_results=10), _service_fn=mock_drive_svc
        )
        assert isinstance(result, list)

    def test_list_files_items_are_dicts(
        self,
        google_drive_provider: GoogleDriveProvider,
        mock_drive_svc: MagicMock,
    ) -> None:
        result = google_drive_provider.list_files(
            FileQuery(max_results=10), _service_fn=mock_drive_svc
        )
        assert all(isinstance(f, dict) for f in result)

    def test_list_files_have_required_keys(
        self,
        google_drive_provider: GoogleDriveProvider,
        mock_drive_svc: MagicMock,
    ) -> None:
        result = google_drive_provider.list_files(
            FileQuery(max_results=10), _service_fn=mock_drive_svc
        )
        for f in result:
            for key in REQUIRED_FILE_KEYS:
                assert key in f, f"File missing required key: {key}"

    def test_get_file_content_returns_str(
        self,
        google_drive_provider: GoogleDriveProvider,
    ) -> None:
        svc = MagicMock()
        from tests.fixtures.mock_drive_responses import MOCK_PDF_FILE

        svc.files().get().execute.return_value = MOCK_PDF_FILE
        result = google_drive_provider.get_file_content("pdf_002", _service_fn=svc)
        assert isinstance(result, str)

    def test_download_file_returns_bytes(
        self,
        google_drive_provider: GoogleDriveProvider,
    ) -> None:
        svc = MagicMock()
        svc.files().get_media().execute.return_value = b"data"
        result = google_drive_provider.download_file("file_001", _service_fn=svc)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# 7. CalendarProvider — OutlookCalendarProvider contract
# ---------------------------------------------------------------------------


def _make_outlook_calendar_provider():
    from iobox.providers.o365.calendar import OutlookCalendarProvider

    p = OutlookCalendarProvider.__new__(OutlookCalendarProvider)
    p.account_email = "user@company.com"
    p.credentials_dir = None
    p.mode = "readonly"

    from unittest.mock import MagicMock

    account = MagicMock()
    calendar = MagicMock()
    calendar.get_events.return_value = iter([])
    schedule = MagicMock()
    schedule.get_default_calendar.return_value = calendar
    account.schedule.return_value = schedule
    p._account = account
    return p


class TestOutlookCalendarABCCompleteness:
    """Verify OutlookCalendarProvider implements all CalendarProvider abstract methods."""

    def _get_abstract_methods(self) -> set[str]:
        import inspect

        from iobox.providers.base import CalendarProvider

        return {
            name
            for name, _ in inspect.getmembers(CalendarProvider, predicate=inspect.isfunction)
            if getattr(getattr(CalendarProvider, name), "__isabstractmethod__", False)
        }

    def test_outlook_calendar_implements_all_abstract_methods(self) -> None:
        from iobox.providers.o365.calendar import OutlookCalendarProvider

        abstract = self._get_abstract_methods()
        for method_name in abstract:
            assert hasattr(OutlookCalendarProvider, method_name), (
                f"OutlookCalendarProvider missing: {method_name}"
            )
            method = getattr(OutlookCalendarProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False)

    def test_is_subclass_of_calendar_provider(self) -> None:
        from iobox.providers.base import CalendarProvider
        from iobox.providers.o365.calendar import OutlookCalendarProvider

        assert issubclass(OutlookCalendarProvider, CalendarProvider)


class TestOutlookCalendarReturnTypes:
    """Verify OutlookCalendarProvider methods return correct types."""

    def test_list_events_returns_list(self) -> None:
        p = _make_outlook_calendar_provider()
        result = p.list_events(EventQuery(max_results=5))
        assert isinstance(result, list)

    def test_get_sync_state_returns_dict(self) -> None:
        p = _make_outlook_calendar_provider()
        result = p.get_sync_state()
        assert isinstance(result, dict)

    def test_get_new_events_returns_tuple(self) -> None:
        p = _make_outlook_calendar_provider()
        events, token = p.get_new_events("tok")
        assert isinstance(events, list)
        assert isinstance(token, str)


# ---------------------------------------------------------------------------
# 8. FileProvider — OneDriveProvider contract
# ---------------------------------------------------------------------------


def _make_onedrive_provider():
    from iobox.providers.o365.files import OneDriveProvider

    p = OneDriveProvider.__new__(OneDriveProvider)
    p.account_email = "user@company.com"
    p.credentials_dir = None
    p.mode = "readonly"

    account = MagicMock()
    drive = MagicMock()
    drive.search.return_value = []
    root = MagicMock()
    root.get_items.return_value = []
    drive.get_root_folder.return_value = root
    storage = MagicMock()
    storage.get_default_drive.return_value = drive
    account.storage.return_value = storage
    p._account = account
    return p


class TestOneDriveABCCompleteness:
    """Verify OneDriveProvider implements all FileProvider abstract methods."""

    def _get_abstract_methods(self) -> set[str]:
        import inspect

        return {
            name
            for name, _ in inspect.getmembers(FileProvider, predicate=inspect.isfunction)
            if getattr(getattr(FileProvider, name), "__isabstractmethod__", False)
        }

    def test_onedrive_implements_all_abstract_methods(self) -> None:
        from iobox.providers.o365.files import OneDriveProvider

        abstract = self._get_abstract_methods()
        for method_name in abstract:
            assert hasattr(OneDriveProvider, method_name), (
                f"OneDriveProvider missing: {method_name}"
            )
            method = getattr(OneDriveProvider, method_name)
            assert not getattr(method, "__isabstractmethod__", False)

    def test_is_subclass_of_file_provider(self) -> None:
        from iobox.providers.o365.files import OneDriveProvider

        assert issubclass(OneDriveProvider, FileProvider)


class TestOneDriveReturnTypes:
    """Verify OneDriveProvider methods return correct types."""

    def test_list_files_returns_list(self) -> None:
        p = _make_onedrive_provider()
        result = p.list_files(FileQuery(max_results=5))
        assert isinstance(result, list)

    def test_get_file_content_returns_str(self) -> None:

        p = _make_onedrive_provider()
        # inject a None-returning get_item so we get "" back
        p._account.storage().get_default_drive().get_item.return_value = None
        result = p.get_file_content("missing")
        assert isinstance(result, str)
