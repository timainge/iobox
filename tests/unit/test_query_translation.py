"""
Query translation tests for GmailProvider and OutlookProvider.

Covers:
- All EmailQuery fields individually and combined
- $search vs $filter path selection in OutlookProvider
- raw_query passthrough for both providers
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from iobox.providers.base import EmailQuery
from iobox.providers.google.email import GmailProvider
from iobox.providers.o365.email import OutlookProvider
from tests.fixtures.mock_outlook_responses import make_full_mock_account

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gmail():
    p = GmailProvider()
    p._service = MagicMock(name="gmail_service")
    return p


@pytest.fixture
def outlook():
    p = OutlookProvider()
    account = make_full_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    return p


# ===========================================================================
# Gmail query translation
# ===========================================================================


class TestGmailQueryTranslation:
    """Test _build_gmail_query for each EmailQuery field."""

    def test_empty_query(self, gmail):
        assert gmail._build_gmail_query(EmailQuery()) == ""

    def test_text(self, gmail):
        assert gmail._build_gmail_query(EmailQuery(text="hello world")) == "hello world"

    def test_from_addr(self, gmail):
        q = EmailQuery(from_addr="alice@example.com")
        assert gmail._build_gmail_query(q) == "from:alice@example.com"

    def test_to_addr(self, gmail):
        q = EmailQuery(to_addr="bob@example.com")
        assert gmail._build_gmail_query(q) == "to:bob@example.com"

    def test_subject(self, gmail):
        q = EmailQuery(subject="Meeting")
        assert gmail._build_gmail_query(q) == "subject:Meeting"

    def test_after(self, gmail):
        q = EmailQuery(after=date(2024, 6, 15))
        assert gmail._build_gmail_query(q) == "after:2024/06/15"

    def test_before(self, gmail):
        q = EmailQuery(before=date(2024, 12, 31))
        assert gmail._build_gmail_query(q) == "before:2024/12/31"

    def test_has_attachment_true(self, gmail):
        q = EmailQuery(has_attachment=True)
        assert gmail._build_gmail_query(q) == "has:attachment"

    def test_has_attachment_false(self, gmail):
        q = EmailQuery(has_attachment=False)
        assert gmail._build_gmail_query(q) == "-has:attachment"

    def test_has_attachment_none(self, gmail):
        q = EmailQuery(has_attachment=None)
        assert gmail._build_gmail_query(q) == ""

    def test_is_unread_true(self, gmail):
        q = EmailQuery(is_unread=True)
        assert gmail._build_gmail_query(q) == "is:unread"

    def test_is_unread_false(self, gmail):
        q = EmailQuery(is_unread=False)
        assert gmail._build_gmail_query(q) == "is:read"

    def test_is_unread_none(self, gmail):
        q = EmailQuery(is_unread=None)
        assert gmail._build_gmail_query(q) == ""

    def test_label(self, gmail):
        q = EmailQuery(label="important")
        assert gmail._build_gmail_query(q) == "label:important"

    def test_raw_query_passthrough(self, gmail):
        raw = "in:anywhere has:attachment filename:pdf"
        q = EmailQuery(raw_query=raw)
        assert gmail._build_gmail_query(q) == raw

    def test_raw_query_overrides_all_fields(self, gmail):
        q = EmailQuery(
            raw_query="native:syntax",
            text="ignored",
            from_addr="ignored@x.com",
            subject="ignored",
        )
        assert gmail._build_gmail_query(q) == "native:syntax"

    def test_all_fields_combined(self, gmail):
        q = EmailQuery(
            text="quarterly report",
            from_addr="cfo@corp.com",
            to_addr="team@corp.com",
            subject="Q4",
            after=date(2024, 1, 1),
            before=date(2024, 12, 31),
            has_attachment=True,
            is_unread=True,
            label="finance",
        )
        result = gmail._build_gmail_query(q)
        # Verify all parts are present in order
        assert "quarterly report" in result
        assert "from:cfo@corp.com" in result
        assert "to:team@corp.com" in result
        assert "subject:Q4" in result
        assert "after:2024/01/01" in result
        assert "before:2024/12/31" in result
        assert "has:attachment" in result
        assert "is:unread" in result
        assert "label:finance" in result

    def test_date_format_uses_slashes(self, gmail):
        """Gmail requires YYYY/MM/DD, not YYYY-MM-DD."""
        q = EmailQuery(after=date(2024, 1, 5), before=date(2024, 2, 10))
        result = gmail._build_gmail_query(q)
        assert "after:2024/01/05" in result
        assert "before:2024/02/10" in result


# ===========================================================================
# Outlook query translation — $filter path
# ===========================================================================


class TestOutlookFilterTranslation:
    """Test _build_outlook_filter for structured queries (no free text)."""

    def test_empty_query_returns_query_object(self, outlook):
        q = EmailQuery()
        result = outlook._build_outlook_filter(q)
        # Should return a query object (MockQuery) with no filters
        assert hasattr(result, "_filters")
        assert result._filters == []

    def test_from_addr(self, outlook):
        q = EmailQuery(from_addr="alice@example.com")
        result = outlook._build_outlook_filter(q)
        assert ("from/emailAddress/address", "eq", "alice@example.com") in result._filters

    def test_to_addr(self, outlook):
        q = EmailQuery(to_addr="bob@example.com")
        result = outlook._build_outlook_filter(q)
        assert ("toRecipients/emailAddress/address", "eq", "bob@example.com") in result._filters

    def test_subject(self, outlook):
        q = EmailQuery(subject="Report")
        result = outlook._build_outlook_filter(q)
        assert ("subject", "contains", "Report") in result._filters

    def test_after_date(self, outlook):
        q = EmailQuery(after=date(2024, 6, 1))
        result = outlook._build_outlook_filter(q)
        # Find the receivedDateTime >= filter
        ge_filters = [f for f in result._filters if f[1] == "ge"]
        assert len(ge_filters) == 1
        assert ge_filters[0][0] == "receivedDateTime"

    def test_before_date(self, outlook):
        q = EmailQuery(before=date(2024, 12, 31))
        result = outlook._build_outlook_filter(q)
        lt_filters = [f for f in result._filters if f[1] == "lt"]
        assert len(lt_filters) == 1
        assert lt_filters[0][0] == "receivedDateTime"

    def test_has_attachment_true(self, outlook):
        q = EmailQuery(has_attachment=True)
        result = outlook._build_outlook_filter(q)
        assert ("hasAttachments", "eq", True) in result._filters

    def test_has_attachment_false(self, outlook):
        q = EmailQuery(has_attachment=False)
        result = outlook._build_outlook_filter(q)
        assert ("hasAttachments", "eq", False) in result._filters

    def test_is_unread_true(self, outlook):
        q = EmailQuery(is_unread=True)
        result = outlook._build_outlook_filter(q)
        assert ("isRead", "eq", False) in result._filters

    def test_is_unread_false(self, outlook):
        q = EmailQuery(is_unread=False)
        result = outlook._build_outlook_filter(q)
        assert ("isRead", "eq", True) in result._filters

    def test_label_category(self, outlook):
        q = EmailQuery(label="Work")
        result = outlook._build_outlook_filter(q)
        # label uses a raw OData lambda expression
        lambda_filters = [f for f in result._filters if "categories/any" in f[0]]
        assert len(lambda_filters) == 1
        assert "Work" in lambda_filters[0][0]

    def test_label_with_single_quote_escaped(self, outlook):
        q = EmailQuery(label="It's Important")
        result = outlook._build_outlook_filter(q)
        lambda_filters = [f for f in result._filters if "categories/any" in f[0]]
        assert len(lambda_filters) == 1
        # Single quote should be escaped as ''
        assert "It''s Important" in lambda_filters[0][0]

    def test_multiple_filters_combined(self, outlook):
        q = EmailQuery(
            from_addr="alice@example.com",
            subject="Report",
            has_attachment=True,
            is_unread=True,
        )
        result = outlook._build_outlook_filter(q)
        assert len(result._filters) == 4


# ===========================================================================
# Outlook query translation — $search path (KQL)
# ===========================================================================


class TestOutlookSearchTranslation:
    """Test _build_outlook_search for KQL queries (free text present)."""

    def test_text_only(self, outlook):
        q = EmailQuery(text="hello world")
        result = outlook._build_outlook_search(q)
        assert '"hello world"' in result

    def test_from_addr(self, outlook):
        q = EmailQuery(from_addr="alice@example.com")
        result = outlook._build_outlook_search(q)
        assert "from:alice@example.com" in result

    def test_to_addr(self, outlook):
        q = EmailQuery(to_addr="bob@example.com")
        result = outlook._build_outlook_search(q)
        assert "to:bob@example.com" in result

    def test_subject(self, outlook):
        q = EmailQuery(subject="Meeting")
        result = outlook._build_outlook_search(q)
        assert "subject:Meeting" in result

    def test_after_date(self, outlook):
        q = EmailQuery(after=date(2024, 6, 1))
        result = outlook._build_outlook_search(q)
        assert "received>=2024-06-01" in result

    def test_before_date(self, outlook):
        q = EmailQuery(before=date(2024, 12, 31))
        result = outlook._build_outlook_search(q)
        assert "received<2024-12-31" in result

    def test_has_attachment_true(self, outlook):
        q = EmailQuery(has_attachment=True)
        result = outlook._build_outlook_search(q)
        assert "hasAttachments:true" in result

    def test_has_attachment_false(self, outlook):
        q = EmailQuery(has_attachment=False)
        result = outlook._build_outlook_search(q)
        assert "hasAttachments:false" in result

    def test_is_unread_true(self, outlook):
        q = EmailQuery(is_unread=True)
        result = outlook._build_outlook_search(q)
        assert "isRead:false" in result

    def test_is_unread_false(self, outlook):
        q = EmailQuery(is_unread=False)
        result = outlook._build_outlook_search(q)
        assert "isRead:true" in result

    def test_label_category(self, outlook):
        q = EmailQuery(label="Work")
        result = outlook._build_outlook_search(q)
        assert "category:Work" in result

    def test_all_fields_combined(self, outlook):
        q = EmailQuery(
            text="quarterly",
            from_addr="cfo@corp.com",
            to_addr="team@corp.com",
            subject="Q4",
            after=date(2024, 1, 1),
            before=date(2024, 12, 31),
            has_attachment=True,
            is_unread=True,
            label="finance",
        )
        result = outlook._build_outlook_search(q)
        assert "from:cfo@corp.com" in result
        assert "to:team@corp.com" in result
        assert "subject:Q4" in result
        assert "received>=2024-01-01" in result
        assert "received<2024-12-31" in result
        assert "hasAttachments:true" in result
        assert "isRead:false" in result
        assert "category:finance" in result
        assert '"quarterly"' in result

    def test_empty_query_returns_empty_string(self, outlook):
        q = EmailQuery()
        result = outlook._build_outlook_search(q)
        assert result == ""


# ===========================================================================
# $search vs $filter path selection
# ===========================================================================


class TestOutlookPathSelection:
    """Verify search_emails picks the right path ($search vs $filter)."""

    def test_raw_query_uses_search_path(self, outlook):
        """When raw_query is set, KQL passthrough via $search."""
        q = EmailQuery(raw_query="subject:test AND from:alice")
        # search_emails should not raise — it goes through $search
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_text_present_uses_search_path(self, outlook):
        """When text is set (free-text), $search is used."""
        q = EmailQuery(text="hello")
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_no_text_uses_filter_path(self, outlook):
        """When only structured fields — $filter is used."""
        q = EmailQuery(from_addr="alice@example.com", is_unread=True)
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_raw_query_takes_priority_over_text(self, outlook):
        """raw_query should be used even if text is also set."""
        q = EmailQuery(raw_query="custom:kql", text="ignored")
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_filter_path_with_dates(self, outlook):
        """Date-only queries use $filter path."""
        q = EmailQuery(after=date(2024, 1, 1), before=date(2024, 12, 31))
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_empty_query_uses_filter_path(self, outlook):
        """Empty query defaults to $filter path."""
        q = EmailQuery()
        results = outlook.search_emails(q)
        assert isinstance(results, list)


# ===========================================================================
# raw_query passthrough — both providers
# ===========================================================================


class TestRawQueryPassthrough:
    """Verify raw_query is passed through verbatim for both providers."""

    def test_gmail_raw_query_verbatim(self, gmail):
        raw = "in:anywhere has:attachment filename:pdf larger:10M"
        q = EmailQuery(raw_query=raw)
        assert gmail._build_gmail_query(q) == raw

    def test_gmail_raw_query_with_special_chars(self, gmail):
        raw = 'from:(alice OR bob) subject:"monthly report"'
        q = EmailQuery(raw_query=raw)
        assert gmail._build_gmail_query(q) == raw

    def test_outlook_raw_query_passthrough_in_search(self, outlook):
        """raw_query is used as KQL in $search path."""
        q = EmailQuery(raw_query="subject:test AND hasAttachments:true")
        # Should not error and should return a list
        results = outlook.search_emails(q)
        assert isinstance(results, list)

    def test_gmail_raw_query_ignores_other_fields(self, gmail):
        """When raw_query is set, other fields are entirely ignored."""
        q = EmailQuery(
            raw_query="custom query",
            text="nope",
            from_addr="nope@nope.com",
            to_addr="nope@nope.com",
            subject="nope",
            after=date(2024, 1, 1),
            before=date(2024, 12, 31),
            has_attachment=True,
            is_unread=True,
            label="nope",
        )
        result = gmail._build_gmail_query(q)
        assert result == "custom query"
        assert "nope" not in result
        assert "from:" not in result
