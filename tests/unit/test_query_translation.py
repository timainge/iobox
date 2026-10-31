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
from tests.fixtures.mock_outlook_responses import make_outlook_provider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gmail():
    p = GmailProvider()
    p._service = MagicMock(name="gmail_service")
    return p


@pytest.fixture
def outlook() -> OutlookProvider:
    # Real python-o365 objects over a fake Graph session (skips without O365).
    return make_outlook_provider()


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


def _render_filter(outlook, q: EmailQuery) -> str:
    """Render _build_outlook_filter's real python-o365 CompositeFilter."""
    result = outlook._build_outlook_filter(q)
    return "" if result is None else str(result.as_params().get("$filter", ""))


class TestOutlookFilterTranslation:
    """_build_outlook_filter → real python-o365 QueryBuilder output."""

    def test_empty_query_returns_none(self, outlook):
        assert outlook._build_outlook_filter(EmailQuery()) is None

    def test_from_addr(self, outlook):
        f = _render_filter(outlook, EmailQuery(from_addr="alice@example.com"))
        assert f == "from/emailAddress/address eq 'alice@example.com'"

    def test_to_addr_uses_any_lambda(self, outlook):
        # toRecipients is a collection: "toRecipients/emailAddress/address eq"
        # (the old translation) is invalid OData.
        f = _render_filter(outlook, EmailQuery(to_addr="bob@example.com"))
        assert f == "toRecipients/any(r: r/emailAddress/address eq 'bob@example.com')"

    def test_subject(self, outlook):
        f = _render_filter(outlook, EmailQuery(subject="Report"))
        assert f == "contains(subject, 'Report')"

    def test_dates(self, outlook):
        f = _render_filter(outlook, EmailQuery(after=date(2024, 6, 1), before=date(2024, 12, 31)))
        assert "receivedDateTime ge 2024-06-01T00:00:00" in f
        assert "receivedDateTime lt 2024-12-31T00:00:00" in f

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"has_attachment": True}, "hasAttachments eq true"),
            ({"has_attachment": False}, "hasAttachments eq false"),
            ({"is_unread": True}, "isRead eq false"),
            ({"is_unread": False}, "isRead eq true"),
        ],
    )
    def test_booleans(self, outlook, kwargs, expected):
        assert _render_filter(outlook, EmailQuery(**kwargs)) == expected

    def test_label_category(self, outlook):
        f = _render_filter(outlook, EmailQuery(label="Work"))
        assert f == "categories/any(c: c eq 'Work')"

    def test_label_with_single_quote_escaped(self, outlook):
        f = _render_filter(outlook, EmailQuery(label="It's Important"))
        assert f == "categories/any(c: c eq 'It''s Important')"

    def test_multiple_filters_combined(self, outlook):
        q = EmailQuery(
            from_addr="alice@example.com", subject="Report", has_attachment=True, is_unread=True
        )
        assert _render_filter(outlook, q).count(" and ") == 3


# ===========================================================================
# Outlook query translation — $search path (KQL)
# ===========================================================================


class TestOutlookSearchTranslation:
    """_build_outlook_search → unquoted KQL (quoted once for $search)."""

    def test_text_only(self, outlook):
        assert outlook._build_outlook_search(EmailQuery(text="hello world")) == "hello world"

    def test_from_to_subject(self, outlook):
        q = EmailQuery(from_addr="alice@example.com", to_addr="bob@example.com", subject="Meeting")
        assert (
            outlook._build_outlook_search(q)
            == "from:alice@example.com to:bob@example.com subject:Meeting"
        )

    def test_subject_with_spaces_is_quoted(self, outlook):
        q = EmailQuery(subject="Q4 numbers")
        assert outlook._build_outlook_search(q) == 'subject:"Q4 numbers"'

    def test_dates(self, outlook):
        q = EmailQuery(after=date(2024, 6, 1), before=date(2024, 12, 31))
        assert outlook._build_outlook_search(q) == "received>=2024-06-01 received<2024-12-31"

    def test_has_attachment(self, outlook):
        assert outlook._build_outlook_search(EmailQuery(has_attachment=True)) == (
            "hasAttachments:true"
        )
        assert outlook._build_outlook_search(EmailQuery(has_attachment=False)) == (
            "hasAttachments:false"
        )

    def test_unread_and_label_not_in_kql(self, outlook):
        # No KQL property for read state / categories on Graph messages;
        # search_emails applies them client-side.
        assert outlook._build_outlook_search(EmailQuery(is_unread=True, label="Work")) == ""

    def test_empty_query_returns_empty_string(self, outlook):
        assert outlook._build_outlook_search(EmailQuery()) == ""


# ===========================================================================
# $search vs $filter path selection
# ===========================================================================


class TestOutlookPathSelection:
    """search_emails picks $search or $filter — never both, never $orderby."""

    def _params(self, outlook, q: EmailQuery) -> dict:
        outlook.search_emails(q)
        return dict(outlook.tenant.graph.last("GET", r"/me/messages").params)

    def test_raw_query_uses_search_path(self, outlook):
        p = self._params(outlook, EmailQuery(raw_query="subject:test AND from:alice"))
        assert p["$search"] == '"subject:test AND from:alice"'
        assert "$filter" not in p

    def test_text_present_uses_search_path(self, outlook):
        p = self._params(outlook, EmailQuery(text="hello", from_addr="a@b.com"))
        assert p["$search"] == '"from:a@b.com hello"'
        assert "$filter" not in p and "$orderby" not in p

    def test_no_text_uses_filter_path(self, outlook):
        p = self._params(outlook, EmailQuery(from_addr="alice@example.com", is_unread=True))
        assert "$search" not in p
        assert (
            p["$filter"] == "from/emailAddress/address eq 'alice@example.com' and isRead eq false"
        )

    def test_raw_query_takes_priority_over_text(self, outlook):
        p = self._params(outlook, EmailQuery(raw_query="custom:kql", text="ignored"))
        assert p["$search"] == '"custom:kql"'

    def test_empty_query_has_neither(self, outlook):
        p = self._params(outlook, EmailQuery())
        assert "$search" not in p and "$filter" not in p


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
        assert isinstance(outlook.search_emails(q), list)
        params = outlook.tenant.graph.last("GET", r"/me/messages").params
        assert params["$search"] == '"subject:test AND hasAttachments:true"'

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
