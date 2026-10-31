"""
Unit tests for ``OutlookProvider``.

The provider runs on top of the **real** python-o365 objects (``Account``,
``Connection``, ``MailBox``, ``Message``, ``QueryBuilder``); only HTTP is
faked, by :class:`tests.fixtures.mock_outlook_responses.FakeOutlookTenant`.
Assertions are made on the Graph requests that would go over the wire, so a
call to a method python-o365 does not have (or a malformed URL / query)
fails here the same way it would against a real tenant.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("O365")  # whole module needs the outlook extra

from iobox.providers.base import EmailQuery  # noqa: E402
from iobox.providers.o365.auth import IMMUTABLE_ID_PREFER  # noqa: E402
from iobox.providers.o365.email import OutlookBatchError, OutlookProvider  # noqa: E402
from tests.fixtures.mock_outlook_responses import (  # noqa: E402
    ATTACHMENT_PDF_BYTES,
    ATTACHMENT_PNG_BYTES,
    WELL_KNOWN_FOLDER_IDS,
    FakeAuth,
    FakeOutlookTenant,
    graph_message,
    make_full_tenant,
    make_outlook_provider,
    make_real_account,
)


@pytest.fixture
def provider() -> OutlookProvider:
    return make_outlook_provider()


@pytest.fixture
def tenant(provider: OutlookProvider) -> FakeOutlookTenant:
    return provider.tenant  # type: ignore[attr-defined,no-any-return]


# ---------------------------------------------------------------------------
# Authentication / ImmutableId (O365-01)
# ---------------------------------------------------------------------------


class TestAuthenticate:
    def test_auth_path_does_not_touch_session(self) -> None:
        """Old code did account.con.session.headers.update() → AttributeError
        on a real account, whose session is None until the first request."""
        account = make_real_account()
        account.con.session = None
        account.con.default_headers = {}
        p = OutlookProvider(auth=FakeAuth(account))
        p.authenticate()
        assert account.con.default_headers["Prefer"] == IMMUTABLE_ID_PREFER
        assert p._mailbox is not None

    def test_every_request_carries_immutable_id(self, provider, tenant) -> None:
        provider.search_emails(EmailQuery(max_results=5))
        provider.get_email_content("outlook-msg-id-3")
        provider.mark_read("outlook-msg-id-1")
        assert tenant.graph.calls
        for call in tenant.graph.calls:
            assert IMMUTABLE_ID_PREFER in call.headers.get("Prefer", ""), call.path

    def test_legacy_path_uses_active_account_and_mode(self) -> None:
        account = make_real_account()
        with (
            patch(
                "iobox.providers.o365.auth.get_outlook_account", return_value=account
            ) as get_acct,
            patch("iobox.accounts.get_active_account", return_value="corp@x.com"),
        ):
            OutlookProvider(mode="readonly").authenticate()
        get_acct.assert_called_once_with(account="corp@x.com", mode="readonly")

    def test_get_profile(self, provider) -> None:
        profile = provider.get_profile()
        assert profile["provider"] == "outlook"
        assert profile["email"] == "user@example.com"


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


class TestMessageToEmailData:
    def test_basic_fields(self, provider) -> None:
        data = provider.get_email_content("outlook-msg-id-2")
        assert data["message_id"] == "outlook-msg-id-2"
        assert data["thread_id"] == "outlook-conv-id-2"
        assert data["subject"] == "HTML Email Subject"
        assert data["from_"] == "Carol Sender <carol@example.com>"
        assert data["to"] == "Me <me@example.com>"
        assert data["date"].startswith("2026-03-06T10:00:00")
        assert data["labels"] == []
        assert data["snippet"] == "This is the HTML version of the email."

    def test_html_content_type(self, provider) -> None:
        assert provider.get_email_content("outlook-msg-id-2")["content_type"] == "text/html"

    def test_text_content_type_is_case_insensitive(self, provider) -> None:
        """O365-14: Graph returns bodyType "text" (lower case); the old code
        compared against "Text" and labelled every plain-text body as HTML."""
        data = provider.get_email_content("outlook-msg-id-1")
        assert data["content_type"] == "text/plain"
        assert data["body"] == "This is a plain text email."

    def test_metadata_only_in_search(self, provider) -> None:
        results = provider.search_emails(EmailQuery(max_results=50))
        assert results
        for r in results:
            assert "body" not in r
            assert "attachments" not in r

    def test_categories_become_labels(self, provider) -> None:
        assert provider.get_email_content("outlook-msg-id-1")["labels"] == ["Work"]


# ---------------------------------------------------------------------------
# Attachments (O365-07)
# ---------------------------------------------------------------------------


class TestAttachments:
    def test_attachment_metadata_is_fetched(self, provider, tenant) -> None:
        """The old code iterated msg.attachments, which python-o365 leaves
        empty unless attachments are explicitly downloaded."""
        data = provider.get_email_content("outlook-msg-id-4")
        assert [a["filename"] for a in data["attachments"]] == ["document.pdf", "screenshot.png"]
        pdf, png = data["attachments"]
        assert pdf["mime_type"] == "application/pdf"
        assert pdf["size"] == len(ATTACHMENT_PDF_BYTES)
        assert pdf["inline"] is False
        assert png["inline"] is True
        assert png["content_id"] == "logo@cid"
        tenant.graph.last("GET", r"/me/messages/outlook-msg-id-4/attachments")

    def test_listing_does_not_download_content(self, provider, tenant) -> None:
        """FU-12: listing attachments returned contentBytes for every file."""
        provider.get_email_content("outlook-msg-id-4")
        listing = tenant.graph.last("GET", r"/me/messages/outlook-msg-id-4/attachments")
        selected = set(listing.params["$select"].split(","))
        assert "contentBytes" not in selected
        assert {"id", "name", "contentType", "size", "isInline"} <= selected
        # The non-inline PDF is never fetched individually; the small inline
        # image is (contentId lives only on fileAttachment).
        singles = tenant.graph.find("GET", r"/me/messages/outlook-msg-id-4/attachments/[^/]+")
        assert [c.path.rsplit("/", 1)[-1] for c in singles] == ["outlook-attach-id-2"]

    def test_no_attachment_request_without_attachments(self, provider, tenant) -> None:
        assert provider.get_email_content("outlook-msg-id-2")["attachments"] == []
        assert not tenant.graph.find("GET", r".*/attachments")

    def test_download_returns_raw_bytes(self, provider, tenant) -> None:
        """Graph's JSON contentBytes is base64 text; $value is the real file."""
        data = provider.download_attachment("outlook-msg-id-4", "outlook-attach-id-2")
        assert data == ATTACHMENT_PNG_BYTES
        assert data != base64.b64encode(ATTACHMENT_PNG_BYTES)
        tenant.graph.last(
            "GET", r"/me/messages/outlook-msg-id-4/attachments/outlook-attach-id-2/\$value"
        )

    def test_download_missing_attachment(self, provider) -> None:
        with pytest.raises(ValueError, match="not found"):
            provider.download_attachment("outlook-msg-id-3", "nope")


# ---------------------------------------------------------------------------
# Search (O365-04, O365-05)
# ---------------------------------------------------------------------------


class TestSearchFilterPath:
    """Structured queries → $filter built with the real QueryBuilder."""

    def _filter(self, provider, tenant, **kw) -> str:
        # include_spam_trash keeps the folder-exclusion clauses (FU-11) out
        # of the way; TestSpamTrashExclusion covers them.
        kw.setdefault("include_spam_trash", True)
        provider.search_emails(EmailQuery(**kw))
        call = tenant.graph.last("GET", r"/me/messages")
        assert "$search" not in call.params
        assert "$orderby" not in call.params
        return str(call.params.get("$filter", ""))

    def test_no_conditions_no_filter(self, provider, tenant) -> None:
        assert self._filter(provider, tenant) == ""

    def test_from(self, provider, tenant) -> None:
        f = self._filter(provider, tenant, from_addr="boss@example.com")
        assert f == "from/emailAddress/address eq 'boss@example.com'"

    def test_to_uses_any_lambda(self, provider, tenant) -> None:
        f = self._filter(provider, tenant, to_addr="me@example.com")
        assert f == "toRecipients/any(r: r/emailAddress/address eq 'me@example.com')"

    def test_label_uses_categories_any(self, provider, tenant) -> None:
        f = self._filter(provider, tenant, label="Work")
        assert f == "categories/any(c: c eq 'Work')"

    def test_quotes_are_escaped(self, provider, tenant) -> None:
        f = self._filter(provider, tenant, from_addr="o'brien@example.com", subject="it's")
        assert "'o''brien@example.com'" in f
        assert "contains(subject, 'it''s')" in f

    def test_dates_and_flags(self, provider, tenant) -> None:
        f = self._filter(
            provider,
            tenant,
            after=date(2026, 1, 1),
            before=date(2026, 2, 1),
            has_attachment=True,
            is_unread=True,
        )
        assert "receivedDateTime ge 2026-01-01T00:00:00" in f
        assert "receivedDateTime lt 2026-02-01T00:00:00" in f
        assert "hasAttachments eq true" in f
        assert "isRead eq false" in f
        assert f.count(" and ") == 3

    def test_is_unread_false(self, provider, tenant) -> None:
        assert self._filter(provider, tenant, is_unread=False) == "isRead eq true"

    def test_max_results_sent_as_top(self, provider, tenant) -> None:
        provider.search_emails(EmailQuery(max_results=7))
        assert tenant.graph.last("GET", r"/me/messages").params["$top"] == 7

    def test_searches_all_folders(self, provider, tenant) -> None:
        results = provider.search_emails(EmailQuery(max_results=50))
        ids = {r["message_id"] for r in results}
        assert "outlook-thread-msg-2" in ids  # lives in Sent Items
        assert not tenant.graph.find("GET", r"/me/mailFolders/.*/messages")


def _spam_trash_tenant(n_trash: int = 3, n_junk: int = 3, n_inbox: int = 2) -> FakeOutlookTenant:
    """Tenant whose newest messages sit in Deleted Items / Junk Email."""
    tenant = FakeOutlookTenant()
    for i in range(n_trash):
        tenant.add(graph_message(f"trash-{i}", folder=WELL_KNOWN_FOLDER_IDS["deleteditems"]))
    for i in range(n_junk):
        tenant.add(graph_message(f"junk-{i}", folder=WELL_KNOWN_FOLDER_IDS["junkemail"]))
    for i in range(n_inbox):
        tenant.add(graph_message(f"inbox-{i}", folder="inbox"))
    return tenant


class TestSpamTrashExclusion:
    """FU-11: include_spam_trash was ignored, so Deleted Items and Junk
    Email were always searched."""

    def test_filter_path_excludes_spam_and_trash(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        tenant = provider.tenant  # type: ignore[attr-defined]
        results = provider.search_emails(EmailQuery(max_results=50))
        assert {r["message_id"] for r in results} == {"inbox-0", "inbox-1"}
        f = tenant.graph.last("GET", r"/me/messages").params["$filter"]
        assert f == (
            f"parentFolderId ne '{WELL_KNOWN_FOLDER_IDS['deleteditems']}'"
            f" and parentFolderId ne '{WELL_KNOWN_FOLDER_IDS['junkemail']}'"
        )

    def test_filter_path_combines_with_other_clauses(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        tenant = provider.tenant  # type: ignore[attr-defined]
        provider.search_emails(EmailQuery(from_addr="a@b.com"))
        f = tenant.graph.last("GET", r"/me/messages").params["$filter"]
        assert f.startswith("from/emailAddress/address eq 'a@b.com' and parentFolderId ne ")

    def test_search_path_filters_client_side(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        tenant = provider.tenant  # type: ignore[attr-defined]
        results = provider.search_emails(EmailQuery(text="hello", max_results=50))
        assert {r["message_id"] for r in results} == {"inbox-0", "inbox-1"}
        call = tenant.graph.last("GET", r"/me/messages")
        assert "$filter" not in call.params  # Graph rejects $search + $filter
        assert "parentFolderId" in call.params["$select"].split(",")

    def test_raw_query_also_excludes(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        results = provider.search_emails(EmailQuery(raw_query="from:x", max_results=50))
        assert {r["message_id"] for r in results} == {"inbox-0", "inbox-1"}

    def test_max_results_filled_after_client_side_filtering(self) -> None:
        """Excluded hits must not eat into max_results: over-fetch."""
        provider = make_outlook_provider(_spam_trash_tenant(n_trash=60, n_junk=5, n_inbox=4))
        tenant = provider.tenant  # type: ignore[attr-defined]
        results = provider.search_emails(EmailQuery(text="hello", max_results=3))
        assert [r["message_id"] for r in results] == ["inbox-0", "inbox-1", "inbox-2"]
        pages = tenant.graph.find("GET", r"/me/messages")
        assert len(pages) >= 2  # followed @odata.nextLink past the excluded hits
        assert all("$search" in p.params for p in pages)

    def test_over_fetch_is_capped(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant(n_trash=400, n_junk=0, n_inbox=2))
        tenant = provider.tenant  # type: ignore[attr-defined]
        assert provider.search_emails(EmailQuery(text="hello", max_results=3)) == []
        fetched = sum(
            min(int(c.params["$top"]), 400 - int(c.params.get("$skip", 0)))
            for c in tenant.graph.find("GET", r"/me/messages")
        )
        assert fetched <= 250

    def test_include_spam_trash_returns_everything(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        tenant = provider.tenant  # type: ignore[attr-defined]
        for q in (
            EmailQuery(include_spam_trash=True, max_results=50),
            EmailQuery(text="hello", include_spam_trash=True, max_results=50),
        ):
            assert len(provider.search_emails(q)) == 8
        assert not tenant.graph.find("GET", r"/me/mailFolders/[^/]+")
        assert "$filter" not in tenant.graph.find("GET", r"/me/messages")[0].params

    def test_folder_ids_resolved_once_and_cached(self) -> None:
        provider = make_outlook_provider(_spam_trash_tenant())
        tenant = provider.tenant  # type: ignore[attr-defined]
        provider.search_emails(EmailQuery())
        provider.search_emails(EmailQuery(text="x"))
        lookups = tenant.graph.find("GET", r"/me/mailFolders/[^/]+")
        assert sorted(c.path for c in lookups) == [
            "/me/mailFolders/deleteditems",
            "/me/mailFolders/junkemail",
        ]

    def test_unresolvable_folder_is_skipped_and_retried(self) -> None:
        tenant = _spam_trash_tenant()
        tenant.graph.route(
            "GET",
            r"/me/mailFolders/junkemail",
            {"error": {"code": "ErrorAccessDenied", "message": "denied"}},
            status=403,
        )
        provider = make_outlook_provider(tenant)
        results = provider.search_emails(EmailQuery(max_results=50))
        # Trash still excluded; junk cannot be identified so it is kept.
        assert {r["message_id"] for r in results} == {"inbox-0", "inbox-1"} | {
            f"junk-{i}" for i in range(3)
        }
        provider.search_emails(EmailQuery(max_results=50))
        assert len(tenant.graph.find("GET", r"/me/mailFolders/junkemail")) == 2


class TestSearchKqlPath:
    def _search(self, provider, tenant, **kw) -> str:
        provider.search_emails(EmailQuery(**kw))
        call = tenant.graph.last("GET", r"/me/messages")
        assert "$filter" not in call.params
        assert "$orderby" not in call.params
        return str(call.params["$search"])

    def test_text_search_is_not_single_quoted(self, provider, tenant) -> None:
        """O365-05: QueryBuilder.search() produced "'from:x budget'" — one
        quoted phrase — so field restrictions were never applied."""
        s = self._search(provider, tenant, text="budget", from_addr="boss@example.com")
        assert s == '"from:boss@example.com budget"'
        assert "'" not in s

    def test_values_with_spaces_are_quoted_and_escaped(self, provider, tenant) -> None:
        s = self._search(provider, tenant, text="report", subject="quarterly results")
        assert s == '"subject:\\"quarterly results\\" report"'

    def test_dates_and_attachments(self, provider, tenant) -> None:
        s = self._search(provider, tenant, text="x", after=date(2026, 1, 1), has_attachment=True)
        assert s == '"received>=2026-01-01 hasAttachments:true x"'

    def test_raw_query_passthrough(self, provider, tenant) -> None:
        s = self._search(provider, tenant, raw_query='from:a@b.com subject:"hi there"')
        assert s == '"from:a@b.com subject:\\"hi there\\""'

    def test_unread_and_label_filtered_client_side(self, provider, tenant) -> None:
        results = provider.search_emails(
            EmailQuery(text="anything", is_unread=True, max_results=10)
        )
        assert {r["message_id"] for r in results} == {"outlook-msg-id-2", "outlook-msg-id-6"}
        results = provider.search_emails(EmailQuery(text="anything", label="work"))
        assert [r["message_id"] for r in results] == ["outlook-msg-id-1"]
        s = str(tenant.graph.last("GET", r"/me/messages").params["$search"])
        assert "isRead" not in s and "category" not in s

    def test_build_search_helper(self, provider) -> None:
        q = EmailQuery(from_addr="a@b.com", to_addr="c@d.com", has_attachment=False, text="hi")
        assert (
            provider._build_outlook_search(q) == "from:a@b.com to:c@d.com hasAttachments:false hi"
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class TestRead:
    def test_get_email_content_missing(self, provider) -> None:
        with pytest.raises(ValueError, match="not found"):
            provider.get_email_content("does-not-exist")

    def test_batch_get_skips_missing(self, provider) -> None:
        results = provider.batch_get_emails(["outlook-msg-id-1", "nope", "outlook-msg-id-2"])
        assert [r["message_id"] for r in results] == ["outlook-msg-id-1", "outlook-msg-id-2"]

    def test_thread_sorted_client_side_without_orderby(self, provider, tenant) -> None:
        msgs = provider.get_thread("outlook-conv-thread-1")
        assert [m["message_id"] for m in msgs] == ["outlook-thread-msg-1", "outlook-thread-msg-2"]
        call = tenant.graph.last("GET", r"/me/messages")
        assert call.params["$filter"] == "conversationId eq 'outlook-conv-thread-1'"
        assert "$orderby" not in call.params

    def test_empty_thread(self, provider) -> None:
        assert provider.get_thread("no-such-conversation") == []


# ---------------------------------------------------------------------------
# Send / forward / drafts (O365-14)
# ---------------------------------------------------------------------------


class TestSend:
    def test_send_returns_real_message_id(self, provider, tenant) -> None:
        """python-o365's sendMail path sets object_id = 'sent_message'."""
        result = provider.send_message("a@x.com, b@x.com", "Hi", "Body", cc="c@x.com")
        assert result["status"] == "sent"
        assert result["message_id"] != "sent_message"
        assert result["message_id"] in tenant.messages
        sent = tenant.sent[-1]
        assert [r["emailAddress"]["address"] for r in sent["toRecipients"]] == [
            "a@x.com",
            "b@x.com",
        ]
        assert sent["ccRecipients"][0]["emailAddress"]["address"] == "c@x.com"
        assert sent["body"] == {"contentType": "text", "content": "Body"}

    def test_send_html(self, provider, tenant) -> None:
        provider.send_message("a@x.com", "Hi", "<b>x</b>", content_type="html")
        assert tenant.sent[-1]["body"]["contentType"] == "html"

    def test_send_with_attachment(self, provider, tenant, tmp_path: Path) -> None:
        f = tmp_path / "note.txt"
        f.write_bytes(b"hello")
        provider.send_message("a@x.com", "Hi", "Body", attachments=[str(f)])
        att = tenant.sent[-1]["attachments"][0]
        assert att["name"] == "note.txt"
        assert base64.b64decode(att["contentBytes"]) == b"hello"

    def test_create_draft(self, provider, tenant) -> None:
        result = provider.create_draft("a@x.com", "Draft", "Body", bcc="z@x.com")
        assert result["status"] == "draft"
        draft = tenant.messages[result["message_id"]]
        assert draft["isDraft"] is True
        assert draft["bccRecipients"][0]["emailAddress"]["address"] == "z@x.com"
        assert not tenant.sent

    def test_forward_prepends_comment_and_keeps_original(self, provider, tenant) -> None:
        result = provider.forward_message("outlook-msg-id-2", "z@x.com", comment="FYI\nsee below")
        assert result["status"] == "sent"
        sent = tenant.sent[-1]
        body = sent["body"]["content"]
        assert "FYI<br/>see below" in body
        assert "<strong>HTML</strong> version" in body  # original quoted
        assert body.index("FYI") < body.index("HTML</strong>")
        assert sent["toRecipients"] == [{"emailAddress": {"address": "z@x.com"}}]
        tenant.graph.last("POST", r"/me/messages/outlook-msg-id-2/createForward")

    def test_forward_missing(self, provider) -> None:
        with pytest.raises(ValueError):
            provider.forward_message("nope", "z@x.com")

    def test_list_drafts(self, provider, tenant) -> None:
        drafts = provider.list_drafts()
        assert [d["message_id"] for d in drafts] == ["outlook-draft-id-1"]
        tenant.graph.last("GET", r"/me/mailFolders/Drafts/messages")

    def test_send_draft(self, provider, tenant) -> None:
        assert provider.send_draft("outlook-draft-id-1") == {
            "message_id": "outlook-draft-id-1",
            "status": "sent",
        }
        tenant.graph.last("POST", r"/me/messages/outlook-draft-id-1/send")

    def test_send_draft_rejects_non_draft(self, provider) -> None:
        with pytest.raises(ValueError, match="not a draft"):
            provider.send_draft("outlook-msg-id-1")

    def test_send_draft_missing(self, provider) -> None:
        with pytest.raises(ValueError, match="Draft not found"):
            provider.send_draft("nope")

    def test_delete_draft(self, provider, tenant) -> None:
        assert provider.delete_draft("outlook-draft-id-1")["status"] == "deleted"
        tenant.graph.last("DELETE", r"/me/messages/outlook-draft-id-1")


# ---------------------------------------------------------------------------
# Organisation ops (O365-08)
# ---------------------------------------------------------------------------


class TestOrganisation:
    def test_mark_read_and_unread(self, provider, tenant) -> None:
        provider.mark_read("outlook-msg-id-2")
        assert tenant.graph.last("PATCH", r"/me/messages/outlook-msg-id-2").body == {"isRead": True}
        provider.mark_read("outlook-msg-id-2", read=False)
        assert tenant.messages["outlook-msg-id-2"]["isRead"] is False

    def test_set_star_uses_message_flag_api(self, provider, tenant) -> None:
        """O365-08: Message.flag is a read-only property; assigning a dict
        raised AttributeError against the real library."""
        provider.set_star("outlook-msg-id-1")
        body = tenant.graph.last("PATCH", r"/me/messages/outlook-msg-id-1").body
        assert body["flag"]["flagStatus"] == "flagged"

    def test_unstar(self, provider, tenant) -> None:
        provider.set_star("outlook-msg-id-5", starred=False)
        body = tenant.graph.last("PATCH", r"/me/messages/outlook-msg-id-5").body
        assert body == {"flag": {"flagStatus": "notFlagged"}}

    def test_archive_trash_untrash(self, provider, tenant) -> None:
        provider.archive("outlook-msg-id-1")
        assert tenant.graph.last("POST", r"/me/messages/outlook-msg-id-1/move").body == {
            "destinationId": "Archive"
        }
        provider.trash("outlook-msg-id-2")
        tenant.graph.last("DELETE", r"/me/messages/outlook-msg-id-2")
        provider.untrash("outlook-msg-id-2")
        assert tenant.graph.last("POST", r"/me/messages/outlook-msg-id-2/move").body == {
            "destinationId": "Inbox"
        }

    @pytest.mark.parametrize("op", ["mark_read", "set_star", "archive", "trash", "untrash"])
    def test_missing_message_raises_value_error(self, provider, op: str) -> None:
        with pytest.raises(ValueError, match="not found"):
            getattr(provider, op)("does-not-exist")

    def test_add_and_remove_tag(self, provider, tenant) -> None:
        provider.add_tag("outlook-msg-id-2", "Urgent")
        assert tenant.messages["outlook-msg-id-2"]["categories"] == ["Urgent"]
        calls = len(tenant.graph.calls)
        provider.add_tag("outlook-msg-id-2", "Urgent")  # no-op: no PATCH
        assert not [c for c in tenant.graph.calls[calls:] if c.method == "PATCH"]
        provider.remove_tag("outlook-msg-id-2", "Urgent")
        assert tenant.messages["outlook-msg-id-2"]["categories"] == []

    def test_list_tags(self, provider, tenant) -> None:
        assert provider.list_tags() == {
            "Work": "Work",
            "Personal": "Personal",
            "Important": "Important",
        }
        tenant.graph.last("GET", r"/me/outlook/masterCategories")

    def test_create_tag(self, provider, tenant) -> None:
        tag = provider.create_tag("Receipts")
        assert tag["name"] == "Receipts"
        assert (
            tenant.graph.last("POST", r"/me/outlook/masterCategories").body["displayName"]
            == "Receipts"
        )


# ---------------------------------------------------------------------------
# $batch (O365-13)
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_url_has_no_double_slash(self, provider, tenant) -> None:
        provider.batch_mark_read(["outlook-msg-id-1"])
        call = tenant.graph.last("POST", r"/\$batch")
        assert call.url == "https://graph.microsoft.com/v1.0/$batch"

    def test_sub_requests_carry_immutable_id(self, provider, tenant) -> None:
        provider.batch_archive(["outlook-msg-id-1", "outlook-msg-id-2"])
        reqs = tenant.graph.last("POST", r"/\$batch").body["requests"]
        assert [r["url"] for r in reqs] == [
            "/me/messages/outlook-msg-id-1/move",
            "/me/messages/outlook-msg-id-2/move",
        ]
        for r in reqs:
            assert r["headers"]["Prefer"] == IMMUTABLE_ID_PREFER
            assert r["body"] == {"destinationId": "archive"}

    def test_chunks_of_twenty(self, provider, tenant) -> None:
        ids = [f"m{i}" for i in range(45)]
        provider.batch_trash(ids)
        sizes = [len(c.body["requests"]) for c in tenant.graph.find("POST", r"/\$batch")]
        assert sizes == [20, 20, 5]

    def test_failed_sub_requests_raise_after_all_chunks(self, provider, tenant) -> None:
        """Old code ignored per-item statuses, reporting success for 404s."""
        tenant.batch_status["1"] = 404
        tenant.batch_status["21"] = 503
        ids = [f"m{i}" for i in range(25)]
        with pytest.raises(OutlookBatchError) as exc:
            provider.batch_trash(ids)
        assert len(tenant.graph.find("POST", r"/\$batch")) == 2  # both chunks ran
        assert [f["message_id"] for f in exc.value.failures] == ["m1", "m21"]
        assert [f["status"] for f in exc.value.failures] == [404, 503]
        assert exc.value.total == 25

    def test_batch_tags_only_patch_changed_messages(self, provider, tenant) -> None:
        provider.batch_add_tag(["outlook-msg-id-1", "outlook-msg-id-2", "missing"], "Work")
        reqs = tenant.graph.last("POST", r"/\$batch").body["requests"]
        assert reqs == [
            {
                "id": "0",
                "method": "PATCH",
                "url": "/me/messages/outlook-msg-id-2",
                "body": {"categories": ["Work"]},
                "headers": {"Content-Type": "application/json", "Prefer": IMMUTABLE_ID_PREFER},
            }
        ]

    def test_batch_remove_tag(self, provider, tenant) -> None:
        provider.batch_remove_tag(["outlook-msg-id-1"], "Work")
        req = tenant.graph.last("POST", r"/\$batch").body["requests"][0]
        assert req["body"] == {"categories": []}

    def test_empty_batch_makes_no_request(self, provider, tenant) -> None:
        provider.batch_mark_read([])
        assert not tenant.graph.find("POST", r"/\$batch")


def test_fixture_tenant_is_isolated() -> None:
    a = make_full_tenant()
    a.add(graph_message("extra"))
    assert "extra" not in make_full_tenant().messages
