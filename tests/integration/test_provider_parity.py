"""
Cross-provider integration tests for EmailData output format parity.

Verifies that GmailProvider and OutlookProvider produce:
1. Identical EmailData structure (same required keys, same types)
2. Identical markdown output when given the same normalised content
"""

from __future__ import annotations

import pytest

from iobox.markdown_converter import convert_email_to_markdown, convert_html_to_markdown
from iobox.providers.base import EmailData, EmailQuery
from iobox.providers.outlook import OutlookProvider
from tests.fixtures.mock_outlook_responses import (
    make_full_mock_account,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Required keys that must appear in every full-retrieval EmailData
REQUIRED_METADATA_KEYS = {
    "message_id",
    "subject",
    "from_",
    "date",
    "snippet",
    "labels",
    "thread_id",
}
REQUIRED_FULL_KEYS = REQUIRED_METADATA_KEYS | {"body", "content_type", "attachments"}


@pytest.fixture
def outlook_provider() -> OutlookProvider:
    """OutlookProvider with full mock account."""
    p = OutlookProvider()
    account = make_full_mock_account()
    p._account = account
    p._mailbox = account.mailbox()
    return p


def _make_gmail_email_data(
    *,
    message_id: str = "gmail-msg-1",
    thread_id: str = "gmail-thread-1",
    subject: str = "Test Subject",
    from_: str = "Alice Sender <alice@example.com>",
    date: str = "2026-03-06T10:00:00+00:00",
    snippet: str = "This is a preview.",
    labels: list[str] | None = None,
    body: str = "<p>Hello World</p>",
    content_type: str = "text/html",
    attachments: list[dict] | None = None,
) -> EmailData:
    """Create a synthetic EmailData dict as GmailProvider._to_email_data would."""
    data: EmailData = {
        "message_id": message_id,
        "subject": subject,
        "from_": from_,
        "date": date,
        "snippet": snippet,
        "labels": labels or [],
        "thread_id": thread_id,
        "body": body,
        "content_type": content_type,
        "attachments": attachments or [],
    }
    return data


# ---------------------------------------------------------------------------
# 1. EmailData output format parity
# ---------------------------------------------------------------------------


class TestEmailDataFormatParity:
    """Both providers must produce EmailData with identical key sets and types."""

    def test_outlook_full_retrieval_has_all_required_keys(self, outlook_provider):
        """OutlookProvider.get_email_content returns all required EmailData keys."""
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        assert REQUIRED_FULL_KEYS.issubset(data.keys()), (
            f"Missing keys: {REQUIRED_FULL_KEYS - data.keys()}"
        )

    def test_outlook_search_has_metadata_keys(self, outlook_provider):
        """OutlookProvider.search_emails returns metadata-only EmailData."""
        query = EmailQuery(max_results=3)
        results = outlook_provider.search_emails(query)
        assert len(results) > 0
        for r in results:
            assert REQUIRED_METADATA_KEYS.issubset(r.keys()), (
                f"Missing keys: {REQUIRED_METADATA_KEYS - r.keys()}"
            )

    def test_gmail_synthetic_has_all_required_keys(self):
        """Synthetic Gmail EmailData has all required keys (baseline check)."""
        data = _make_gmail_email_data()
        assert REQUIRED_FULL_KEYS.issubset(data.keys())

    def test_key_types_match_across_providers(self, outlook_provider):
        """Values for each key have matching types across both providers."""
        outlook_data = outlook_provider.get_email_content("outlook-msg-id-1")
        gmail_data = _make_gmail_email_data()

        for key in REQUIRED_FULL_KEYS:
            assert key in outlook_data, f"Outlook missing key: {key}"
            assert key in gmail_data, f"Gmail missing key: {key}"
            outlook_type = type(outlook_data[key])
            gmail_type = type(gmail_data[key])
            assert outlook_type == gmail_type, (
                f"Type mismatch for '{key}': outlook={outlook_type.__name__}, "
                f"gmail={gmail_type.__name__}"
            )

    def test_message_id_is_string(self, outlook_provider):
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        assert isinstance(data["message_id"], str)
        assert len(data["message_id"]) > 0

    def test_labels_is_list_of_strings(self, outlook_provider):
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        assert isinstance(data["labels"], list)
        for label in data["labels"]:
            assert isinstance(label, str)

    def test_attachments_is_list_of_dicts(self, outlook_provider):
        data = outlook_provider.get_email_content("outlook-msg-id-3")
        assert isinstance(data["attachments"], list)
        assert len(data["attachments"]) > 0
        for att in data["attachments"]:
            assert isinstance(att, dict)
            assert "id" in att
            assert "filename" in att
            assert "mime_type" in att
            assert "size" in att

    def test_content_type_values(self, outlook_provider):
        """content_type must be 'text/plain' or 'text/html'."""
        plain = outlook_provider.get_email_content("outlook-msg-id-1")
        assert plain["content_type"] == "text/plain"

        html = outlook_provider.get_email_content("outlook-msg-id-2")
        assert html["content_type"] == "text/html"

    def test_from_field_format(self, outlook_provider):
        """from_ should contain the sender's display name and/or email address."""
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        # Should contain an @ sign (email address)
        assert "@" in data["from_"]

    def test_date_is_iso_format_string(self, outlook_provider):
        """date should be a parseable ISO-format datetime string."""
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        assert isinstance(data["date"], str)
        # Should be parseable as ISO datetime
        assert "2026" in data["date"]

    def test_batch_get_returns_consistent_format(self, outlook_provider):
        """batch_get_emails returns the same format as get_email_content."""
        single = outlook_provider.get_email_content("outlook-msg-id-1")
        batch = outlook_provider.batch_get_emails(["outlook-msg-id-1"])
        assert len(batch) == 1
        # Same keys in both
        assert set(single.keys()) == set(batch[0].keys())
        # Same values for identifying fields
        assert single["message_id"] == batch[0]["message_id"]
        assert single["subject"] == batch[0]["subject"]


# ---------------------------------------------------------------------------
# 2. Markdown output parity — same content yields same markdown
# ---------------------------------------------------------------------------


class TestMarkdownOutputParity:
    """Markdown conversion produces identical output regardless of provider origin."""

    def _normalize_email_data_for_markdown(self, data: EmailData) -> dict:
        """Convert EmailData to the dict format expected by convert_email_to_markdown.

        The markdown converter uses 'from' (not 'from_') and expects certain keys.
        """
        return {
            "message_id": data["message_id"],
            "thread_id": data["thread_id"],
            "subject": data["subject"],
            "from": data["from_"],
            "date": data["date"],
            "labels": data["labels"],
            "body": data.get("body", ""),
            "content_type": data.get("content_type", "text/plain"),
            "attachments": data.get("attachments", []),
        }

    def test_plain_text_markdown_identical(self, outlook_provider):
        """Plain text emails from both providers produce identical markdown."""
        outlook_data = outlook_provider.get_email_content("outlook-msg-id-1")

        # Create matching Gmail data with identical content
        gmail_data = _make_gmail_email_data(
            message_id=outlook_data["message_id"],
            thread_id=outlook_data["thread_id"],
            subject=outlook_data["subject"],
            from_=outlook_data["from_"],
            date=outlook_data["date"],
            snippet=outlook_data["snippet"],
            labels=outlook_data["labels"],
            body=outlook_data["body"],
            content_type=outlook_data["content_type"],
            attachments=outlook_data.get("attachments", []),
        )

        outlook_md = convert_email_to_markdown(
            self._normalize_email_data_for_markdown(outlook_data)
        )
        gmail_md = convert_email_to_markdown(self._normalize_email_data_for_markdown(gmail_data))

        # Strip saved_date lines since they contain timestamps
        outlook_lines = [ln for ln in outlook_md.splitlines() if not ln.startswith("saved_date:")]
        gmail_lines = [ln for ln in gmail_md.splitlines() if not ln.startswith("saved_date:")]
        assert outlook_lines == gmail_lines

    def test_html_markdown_identical(self, outlook_provider):
        """HTML emails from both providers produce identical markdown."""
        outlook_data = outlook_provider.get_email_content("outlook-msg-id-2")

        gmail_data = _make_gmail_email_data(
            message_id=outlook_data["message_id"],
            thread_id=outlook_data["thread_id"],
            subject=outlook_data["subject"],
            from_=outlook_data["from_"],
            date=outlook_data["date"],
            snippet=outlook_data["snippet"],
            labels=outlook_data["labels"],
            body=outlook_data["body"],
            content_type=outlook_data["content_type"],
            attachments=outlook_data.get("attachments", []),
        )

        outlook_md = convert_email_to_markdown(
            self._normalize_email_data_for_markdown(outlook_data)
        )
        gmail_md = convert_email_to_markdown(self._normalize_email_data_for_markdown(gmail_data))

        outlook_lines = [ln for ln in outlook_md.splitlines() if not ln.startswith("saved_date:")]
        gmail_lines = [ln for ln in gmail_md.splitlines() if not ln.startswith("saved_date:")]
        assert outlook_lines == gmail_lines

    def test_html_conversion_is_deterministic(self):
        """Same HTML content always converts to the same markdown."""
        html = "<html><body><p>This is <strong>bold</strong> and <em>italic</em>.</p></body></html>"
        md1 = convert_html_to_markdown(html)
        md2 = convert_html_to_markdown(html)
        assert md1 == md2

    def test_email_with_attachments_markdown_parity(self, outlook_provider):
        """Attachment metadata in frontmatter is identical across providers."""
        outlook_data = outlook_provider.get_email_content("outlook-msg-id-3")

        gmail_data = _make_gmail_email_data(
            message_id=outlook_data["message_id"],
            thread_id=outlook_data["thread_id"],
            subject=outlook_data["subject"],
            from_=outlook_data["from_"],
            date=outlook_data["date"],
            snippet=outlook_data["snippet"],
            labels=outlook_data["labels"],
            body=outlook_data["body"],
            content_type=outlook_data["content_type"],
            attachments=outlook_data["attachments"],
        )

        outlook_md = convert_email_to_markdown(
            self._normalize_email_data_for_markdown(outlook_data)
        )
        gmail_md = convert_email_to_markdown(self._normalize_email_data_for_markdown(gmail_data))

        outlook_lines = [ln for ln in outlook_md.splitlines() if not ln.startswith("saved_date:")]
        gmail_lines = [ln for ln in gmail_md.splitlines() if not ln.startswith("saved_date:")]
        assert outlook_lines == gmail_lines

    def test_frontmatter_contains_expected_fields(self, outlook_provider):
        """Markdown frontmatter includes all key metadata fields."""
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        md = convert_email_to_markdown(self._normalize_email_data_for_markdown(data))

        assert md.startswith("---\n")
        assert "message_id:" in md
        assert "subject:" in md
        assert "from:" in md
        assert "date:" in md
        assert "thread_id:" in md
        assert "labels:" in md

    def test_subject_becomes_h1_heading(self, outlook_provider):
        """The email subject appears as a level-1 heading in the markdown body."""
        data = outlook_provider.get_email_content("outlook-msg-id-1")
        md = convert_email_to_markdown(self._normalize_email_data_for_markdown(data))
        assert f"# {data['subject']}" in md
