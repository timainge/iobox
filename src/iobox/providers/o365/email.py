"""
OutlookProvider — Microsoft 365 / Outlook email backend.

Implements the ``EmailProvider`` ABC for Microsoft 365 using the python-o365
library (O365 >= 2.1, which wraps the Microsoft Graph API).

ImmutableId
-----------
Every Graph request carries ``Prefer: IdType="ImmutableId"`` (set on
``account.con.default_headers`` by :func:`~iobox.providers.o365.auth.ensure_immutable_ids`),
so message IDs stay stable when messages move between folders. ``$batch``
sub-requests carry the header individually because Graph does not apply the
outer request's headers to them.

All-mail search
---------------
``search_emails()`` and ``get_thread()`` use the root mailbox message
collection (``/me/messages``), which spans every folder (Inbox, Sent,
Archive, Drafts, Deleted Items, Junk and custom folders).

Unless ``EmailQuery.include_spam_trash`` is set, ``search_emails()`` drops
messages whose ``parentFolderId`` is the Deleted Items or Junk Email folder.
The ids of those well-known folders are resolved once per provider. On the
``$filter`` path the exclusion is sent to Graph as ``parentFolderId ne '...'``
clauses (not yet verified against a live tenant, so results are also checked
client-side); on the ``$search`` path -- where Graph forbids ``$filter`` -- it
is applied client-side, over-fetching pages until ``max_results`` is filled.

Query path selection
--------------------
Graph cannot combine ``$search`` with ``$filter`` or ``$orderby`` on message
collections, so the provider picks one:

* ``raw_query`` set → KQL passthrough via ``$search``
* ``query.text`` set → ``$search`` with KQL built from the query fields;
  ``is_unread`` and ``label`` have no KQL equivalent and are applied
  client-side
* otherwise → ``$filter`` built with python-o365's ``QueryBuilder``
"""

from __future__ import annotations

import html
import logging
import mimetypes
import os
import re
import time
from datetime import datetime
from typing import Any

from iobox.providers.base import AttachmentInfo, EmailData, EmailProvider, EmailQuery
from iobox.providers.o365.auth import IMMUTABLE_ID_PREFER, ensure_immutable_ids

logger = logging.getLogger(__name__)

# Graph $batch accepts at most 20 sub-requests per call.
_BATCH_LIMIT = 20
# Throttled (429) $batch sub-requests are retried this many times, sleeping
# for the sub-response's Retry-After (or an exponential backoff), capped.
_BATCH_MAX_RETRIES = 3
_BATCH_MAX_SLEEP = 30.0
_batch_sleep = time.sleep  # indirection so tests can patch the wait out
# When $search results are filtered client-side, examine at least this many
# candidates (or 5 x max_results, whichever is larger) before giving up.
_CLIENT_FILTER_FETCH = 250
# Attachments are sent inline in the create-draft POST while their combined
# size stays within this budget (Graph caps request bodies at 4 MB and base64
# adds a third); the rest are added to the saved draft afterwards, files over
# 3 MB through an upload session (python-o365's UPLOAD_SIZE_LIMIT_SIMPLE).
_INLINE_ATTACHMENT_BUDGET = 3 * 1024 * 1024
# Attachment metadata (base ``attachment`` type properties; no contentBytes).
_ATTACHMENT_SELECT = "id,name,contentType,size,isInline"
# Well-known folders excluded from search unless include_spam_trash is set.
_SPAM_TRASH_FOLDERS = ("deleteditems", "junkemail")
# Message properties needed for metadata-only search results (and for
# client-side filtering); the body is not downloaded.
_SEARCH_SELECT = ",".join(
    [
        "id",
        "conversationId",
        "subject",
        "from",
        "sender",
        "toRecipients",
        "ccRecipients",
        "bccRecipients",
        "replyTo",
        "receivedDateTime",
        "bodyPreview",
        "categories",
        "isRead",
        "isDraft",
        "hasAttachments",
        "parentFolderId",
    ]
)
# Error codes Graph uses (besides HTTP 410) for an unusable delta token.
_DELTA_RESYNC_CODES = {"syncstatenotfound", "syncstateinvalid", "resyncrequired"}

_KQL_NEEDS_QUOTES = re.compile(r'[\s"():]')


class OutlookBatchError(RuntimeError):
    """Raised when one or more ``$batch`` sub-requests fail.

    ``failures`` lists ``{"message_id", "status", "error"}`` dicts; every
    other sub-request in the batch succeeded.
    """

    def __init__(self, failures: list[dict[str, Any]], total: int) -> None:
        self.failures = failures
        self.total = total
        ids = ", ".join(str(f["message_id"]) for f in failures[:5])
        more = "" if len(failures) <= 5 else f" (+{len(failures) - 5} more)"
        super().__init__(f"{len(failures)} of {total} Outlook batch operations failed: {ids}{more}")


def _http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _graph_error_code(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if response is None:  # NB: a 4xx requests.Response is falsy
        return ""
    try:
        return str(response.json().get("error", {}).get("code", ""))
    except Exception:
        return ""


def _retry_after_seconds(sub_response: dict[str, Any], attempt: int) -> float:
    """Delay before retrying a throttled ``$batch`` sub-request (capped)."""
    headers = sub_response.get("headers") or {}
    raw = next((v for k, v in headers.items() if str(k).lower() == "retry-after"), None)
    try:
        delay = float(raw) if raw is not None else float(2**attempt)
    except (TypeError, ValueError):
        delay = float(2**attempt)
    return min(max(delay, 0.0), _BATCH_MAX_SLEEP)


def _kql_term(prop: str, value: str) -> str:
    """Render ``prop:value``, quoting the value when it contains spaces etc."""
    if _KQL_NEEDS_QUOTES.search(value):
        return f'{prop}:"{value.replace(chr(34), "")}"'
    return f"{prop}:{value}"


def _search_param(kql: str) -> str:
    """Wrap a KQL expression for Graph's ``$search`` (double quotes, escaped)."""
    return '"' + kql.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _odata_str(value: str) -> str:
    """Escape a value for an OData string literal (single quotes doubled)."""
    return value.replace("'", "''")


class _SearchQuery:
    """Minimal query object for ``Folder.get_messages(query=...)``.

    python-o365's ``QueryBuilder.search()`` runs the text through its
    ``$filter`` literal formatter (``'...'``) and then wraps it in double
    quotes, so ``from:x subject:y`` becomes the phrase ``"'from:x subject:y'"``.
    ``get_messages`` only needs ``as_params()``.
    """

    def __init__(self, kql: str, select: str | None = None) -> None:
        self.kql = kql
        self.select = select

    def as_params(self) -> dict[str, str]:
        params = {"$search": _search_param(self.kql)}
        if self.select:
            params["$select"] = self.select
        return params

    @property
    def has_selects(self) -> bool:
        return False

    @property
    def has_expands(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"_SearchQuery({self.kql!r})"


class _ParamsQuery:
    """Query object wrapping pre-rendered OData params (``$filter``/``$select``)."""

    def __init__(self, params: dict[str, str]) -> None:
        self.params = params

    def as_params(self) -> dict[str, str]:
        return dict(self.params)

    @property
    def has_selects(self) -> bool:
        return "$select" in self.params

    @property
    def has_expands(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"_ParamsQuery({self.params!r})"


class OutlookProvider(EmailProvider):
    """EmailProvider backed by Microsoft 365 via python-o365 / Graph API."""

    def __init__(
        self,
        auth: Any | None = None,
        *,
        mode: str | None = None,
    ) -> None:
        self._microsoft_auth: Any | None = auth  # MicrosoftAuth (optional)
        # Access mode for the legacy (no ``auth``) path — selects the token tier.
        self._mode = mode or "standard"
        self._account: Any | None = None  # O365.Account instance
        self._mailbox: Any | None = None  # O365.mailbox.MailBox instance
        # Folder ids of Deleted Items / Junk Email (resolved lazily, cached).
        self._spam_trash_ids: frozenset[str] | None = None

    # ------------------------------------------------------------------
    # Internal lazy-access properties
    # ------------------------------------------------------------------

    @property
    def _acct(self) -> Any:
        """Return the authenticated Account, authenticating lazily if needed."""
        if self._account is None:
            self.authenticate()
        return self._account

    @property
    def _mb(self) -> Any:
        """Return the authenticated Mailbox, initialising lazily if needed."""
        if self._mailbox is None:
            self._mailbox = self._acct.mailbox()
        return self._mailbox

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _attachment_infos(self, message_id: str) -> list[AttachmentInfo]:
        """Fetch attachment metadata for a message.

        python-o365 only populates ``Message.attachments`` when asked to
        download them, and its attachment objects drop ``contentType``, so
        the attachment list is read straight from Graph.

        Only metadata is requested (``$select`` of base ``attachment``
        properties), so file content is not downloaded — that happens in
        :meth:`download_attachment`. ``contentId`` exists only on the derived
        ``fileAttachment`` type and cannot be selected on the collection, so
        it is fetched per *inline* attachment (typically small images).
        """
        con = self._acct.con
        resp = con.get(
            self._mb.build_url(f"/messages/{message_id}/attachments"),
            params={"$select": _ATTACHMENT_SELECT},
        )
        infos: list[AttachmentInfo] = []
        for a in resp.json().get("value", []) if resp else []:
            name = a.get("name") or ""
            mime = a.get("contentType") or (
                mimetypes.guess_type(name)[0] or "application/octet-stream"
            )
            content_id = a.get("contentId")
            if a.get("isInline") and not content_id and a.get("id"):
                content_id = self._attachment_content_id(message_id, a["id"])
            if content_id:
                content_id = content_id.strip().strip("<>")
            infos.append(
                AttachmentInfo(
                    id=a.get("id", ""),
                    filename=name,
                    mime_type=mime,
                    size=int(a.get("size") or 0),
                    inline=bool(a.get("isInline", False)),
                    content_id=content_id or None,
                )
            )
        return infos

    def _attachment_content_id(self, message_id: str, attachment_id: str) -> str | None:
        """Return the ``contentId`` of one attachment (``None`` if unavailable)."""
        try:
            resp = self._acct.con.get(
                self._mb.build_url(f"/messages/{message_id}/attachments/{attachment_id}")
            )
            return (resp.json().get("contentId") if resp else None) or None
        except Exception as exc:
            logger.warning("Could not read contentId of attachment %r: %s", attachment_id, exc)
            return None

    def _message_to_email_data(
        self,
        msg: Any,
        include_body: bool = True,
    ) -> EmailData:
        """Convert a python-o365 ``Message`` into an :class:`EmailData` dict.

        Args:
            msg: A python-o365 ``Message``.
            include_body: When ``True``, include ``body``, ``content_type``,
                and ``attachments`` (one extra Graph call when the message has
                attachments).
        """
        sender = msg.sender
        if sender and getattr(sender, "address", None):
            name = getattr(sender, "name", "") or ""
            from_ = f"{name} <{sender.address}>" if name else sender.address
        else:
            from_ = ""

        received = msg.received
        if received is not None and hasattr(received, "isoformat"):
            date_str = received.isoformat()
        else:
            date_str = str(received) if received is not None else ""

        def _recipients(recipients: Any) -> str:
            if not recipients:
                return ""
            out = []
            for r in recipients:
                addr = getattr(r, "address", None)
                if not addr:
                    continue
                rname = getattr(r, "name", "") or ""
                out.append(f"{rname} <{addr}>" if rname else addr)
            return ", ".join(out)

        data: EmailData = {
            "message_id": msg.object_id or "",
            "thread_id": msg.conversation_id or "",
            "subject": msg.subject or "",
            "from_": from_,
            "to": _recipients(getattr(msg, "to", None)),
            "cc": _recipients(getattr(msg, "cc", None)),
            "bcc": _recipients(getattr(msg, "bcc", None)),
            "reply_to": _recipients(getattr(msg, "reply_to", None)),
            "date": date_str,
            "snippet": msg.body_preview or "",
            "labels": list(msg.categories) if msg.categories else [],
        }

        if include_body:
            data["body"] = msg.body or ""
            # Graph v1.0 returns bodyType as "html" / "text" (lower case).
            body_type = str(getattr(msg, "body_type", "html") or "html").lower()
            data["content_type"] = "text/plain" if body_type == "text" else "text/html"
            data["attachments"] = (
                self._attachment_infos(msg.object_id) if msg.has_attachments else []
            )

        return data

    def _spam_trash_folder_ids(self) -> frozenset[str]:
        """Return the ids of the Deleted Items and Junk Email folders.

        Resolved via ``GET /me/mailFolders/{well-known name}`` and cached for
        the provider's lifetime. A folder that cannot be resolved (missing,
        access denied, transient error) is logged and left out -- its messages
        are then not excluded -- and the lookup is retried on the next search.
        """
        if self._spam_trash_ids is not None:
            return self._spam_trash_ids
        con = self._acct.con
        ids: set[str] = set()
        complete = True
        for name in _SPAM_TRASH_FOLDERS:
            folder_id = None
            try:
                resp = con.get(self._mb.build_url(f"/mailFolders/{name}"), params={"$select": "id"})
                folder_id = resp.json().get("id") if resp else None
            except Exception as exc:
                logger.warning("Could not resolve Outlook folder %r: %s", name, exc)
            if folder_id:
                ids.add(str(folder_id))
            else:
                complete = False
        result = frozenset(ids)
        if complete:
            self._spam_trash_ids = result
        return result

    def _build_outlook_filter(
        self, query: EmailQuery, exclude_folder_ids: frozenset[str] = frozenset()
    ) -> Any | None:
        """Build an OData ``$filter`` with python-o365's ``QueryBuilder``.

        Used when no free-text (``query.text``) is present. Returns a
        ``CompositeFilter`` (or ``None`` when the query has no conditions).
        ``exclude_folder_ids`` adds ``parentFolderId ne '...'`` clauses.
        """
        from O365.utils.query import CompositeFilter, IterableFilter, LogicalFilter

        qb = self._mb.new_query()
        parts: list[Any] = []

        if query.from_addr:
            # "from" maps to from/emailAddress/address in QueryBuilder.
            parts.append(qb.equals("from", _odata_str(query.from_addr)))

        if query.to_addr:
            # toRecipients/any(r: r/emailAddress/address eq '...'). Built from
            # the filter primitives because QueryBuilder's casing helper
            # mangles multi-segment attributes ("emailAddress/address").
            inner = LogicalFilter("eq", "emailAddress/address", f"'{_odata_str(query.to_addr)}'")
            parts.append(
                CompositeFilter(filters=IterableFilter("any", "toRecipients", inner, item_name="r"))
            )

        if query.subject:
            parts.append(qb.contains("subject", _odata_str(query.subject)))

        if query.after:
            after_dt = datetime.combine(query.after, datetime.min.time())
            parts.append(qb.greater_equal("receivedDateTime", after_dt))

        if query.before:
            before_dt = datetime.combine(query.before, datetime.min.time())
            parts.append(qb.less("receivedDateTime", before_dt))

        if query.has_attachment is not None:
            parts.append(qb.equals("hasAttachments", bool(query.has_attachment)))

        if query.is_unread is not None:
            parts.append(qb.equals("isRead", not query.is_unread))

        if query.label:
            # categories/any(c: c eq 'Label')
            inner = LogicalFilter("eq", None, f"'{_odata_str(query.label)}'")
            parts.append(
                CompositeFilter(filters=IterableFilter("any", "categories", inner, item_name="c"))
            )

        for folder_id in sorted(exclude_folder_ids):
            parts.append(qb.unequal("parentFolderId", _odata_str(folder_id)))

        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return qb.chain_and(*parts)

    def _build_outlook_search(self, query: EmailQuery) -> str:
        """Build a KQL expression for ``$search`` (unquoted; see ``_search_param``).

        ``is_unread`` and ``label`` have no reliable KQL property on Graph
        messages; :meth:`search_emails` applies them client-side.
        """
        parts: list[str] = []

        if query.from_addr:
            parts.append(_kql_term("from", query.from_addr))
        if query.to_addr:
            parts.append(_kql_term("to", query.to_addr))
        if query.subject:
            parts.append(_kql_term("subject", query.subject))
        if query.after:
            parts.append(f"received>={query.after.isoformat()}")
        if query.before:
            parts.append(f"received<{query.before.isoformat()}")
        if query.has_attachment is True:
            parts.append("hasAttachments:true")
        elif query.has_attachment is False:
            parts.append("hasAttachments:false")
        if query.text:
            parts.append(query.text.strip())

        return " ".join(parts)

    @staticmethod
    def _client_side_match(msg: Any, query: EmailQuery) -> bool:
        if query.is_unread is not None and bool(msg.is_read) == bool(query.is_unread):
            return False
        if query.label:
            cats = [c.lower() for c in (msg.categories or [])]
            if query.label.lower() not in cats:
                return False
        return True

    def _get_message_or_raise(self, message_id: str) -> Any:
        """Fetch a message by ID, raising ``ValueError`` if it does not exist."""
        try:
            msg = self._mb.get_message(object_id=message_id)
        except Exception as exc:
            if _http_status(exc) == 404:
                raise ValueError(f"Message not found: {message_id!r}") from exc
            raise
        if msg is None:
            raise ValueError(f"Message not found: {message_id!r}")
        return msg

    # ------------------------------------------------------------------
    # 1. Authentication & profile
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Authenticate with Microsoft 365 and enable immutable IDs."""
        if self._microsoft_auth is not None:
            self._account = self._microsoft_auth.get_account()
        else:
            from iobox.accounts import get_active_account
            from iobox.providers.o365.auth import get_outlook_account

            self._account = get_outlook_account(account=get_active_account(), mode=self._mode)
        ensure_immutable_ids(self._account)
        self._mailbox = self._account.mailbox()

    def get_profile(self) -> dict[str, Any]:
        """Return authentication status and the signed-in username (no network call)."""
        acct = self._acct
        return {
            "provider": "outlook",
            "authenticated": acct.is_authenticated,
            "email": getattr(acct, "username", None),
        }

    # ------------------------------------------------------------------
    # 2. Search & read
    # ------------------------------------------------------------------

    def search_emails(self, query: EmailQuery) -> list[EmailData]:
        """Search mail folders and return metadata-only results.

        All folders are searched; Deleted Items and Junk Email are excluded
        unless ``query.include_spam_trash`` is set.
        """
        excluded = frozenset() if query.include_spam_trash else self._spam_trash_folder_ids()
        limit = query.max_results
        batch: int | None = None
        match_fields = False  # apply is_unread / label client-side
        q: Any
        if query.raw_query or query.text:
            kql = query.raw_query or self._build_outlook_search(query)
            q = _SearchQuery(kql, select=_SEARCH_SELECT)
            # $search cannot be combined with $filter, so unread/label (text
            # path only) and the folder exclusion are applied here instead.
            match_fields = not query.raw_query and (
                query.is_unread is not None or bool(query.label)
            )
            if match_fields or excluded:
                # Over-fetch: page through results until max_results matches
                # are found or a bounded number of candidates is examined.
                limit = max(_CLIENT_FILTER_FETCH, query.max_results * 5)
                batch = min(max(query.max_results * 2, 50), 999)
        else:
            f = self._build_outlook_filter(query, excluded)
            params = dict(f.as_params()) if f is not None else {}
            params["$select"] = _SEARCH_SELECT
            q = _ParamsQuery(params)

        messages = self._mb.get_messages(limit=limit, query=q, batch=batch)
        results: list[EmailData] = []
        for msg in messages:
            # The $filter path excludes these folders server-side as well;
            # re-checking is free and guards against Graph ignoring it.
            if excluded and msg.folder_id in excluded:
                continue
            if match_fields and not self._client_side_match(msg, query):
                continue
            results.append(self._message_to_email_data(msg, include_body=False))
            if len(results) >= query.max_results:
                break
        return results

    def get_email_content(
        self, message_id: str, preferred_content_type: str = "text/plain"
    ) -> EmailData:
        """Retrieve the full content of a single email by its immutable ID.

        Raises:
            ValueError: If the message ID is not found.
        """
        msg = self._get_message_or_raise(message_id)
        return self._message_to_email_data(msg, include_body=True)

    def batch_get_emails(
        self, message_ids: list[str], preferred_content_type: str = "text/plain"
    ) -> list[EmailData]:
        """Retrieve full content for a list of message IDs (missing IDs are skipped)."""
        results: list[EmailData] = []
        for mid in message_ids:
            try:
                msg = self._get_message_or_raise(mid)
            except ValueError:
                logger.warning("Message not found during batch_get_emails: %r", mid)
                continue
            results.append(self._message_to_email_data(msg, include_body=True))
        return results

    def get_thread(self, thread_id: str) -> list[EmailData]:
        """Return all messages in a conversation (all folders), oldest first.

        Graph rejects ``$orderby`` combined with a ``conversationId`` filter
        on ``/me/messages`` (InefficientFilter), so ordering is done here.
        """
        qb = self._mb.new_query()
        q = qb.equals("conversationId", _odata_str(thread_id))
        messages = list(self._mb.get_messages(limit=None, query=q))
        far_past = datetime.min

        def _key(m: Any) -> Any:
            r = m.received
            return r.replace(tzinfo=None) if r is not None else far_past

        messages.sort(key=_key)
        return [self._message_to_email_data(msg, include_body=True) for msg in messages]

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download a single attachment and return its raw bytes.

        Uses ``GET /messages/{id}/attachments/{aid}/$value``, which returns
        the decoded file content (the JSON form carries base64 text).

        Raises:
            ValueError: If the message or attachment is not found.
        """
        con = self._acct.con
        url = self._mb.build_url(f"/messages/{message_id}/attachments/{attachment_id}/$value")
        try:
            resp = con.get(url)
        except Exception as exc:
            if _http_status(exc) == 404:
                raise ValueError(
                    f"Attachment {attachment_id!r} not found in message {message_id!r}"
                ) from exc
            raise
        if not resp:
            raise ValueError(f"Attachment {attachment_id!r} not found in message {message_id!r}")
        return bytes(resp.content)

    # ------------------------------------------------------------------
    # 3. Send, forward & drafts
    # ------------------------------------------------------------------

    @staticmethod
    def _split_addresses(value: str | None) -> list[str]:
        if not value:
            return []
        return [a.strip() for a in re.split(r"[,;]", value) if a.strip()]

    def _compose(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None,
        bcc: str | None,
        content_type: str,
        attachments: list[str] | None,
    ) -> tuple[Any, list[str]]:
        """Build an unsaved message.

        Returns the message and the attachment paths that did not fit in the
        create request; pass both to :meth:`_save_new_draft`.
        """
        msg = self._mb.new_message()
        msg.to.add(self._split_addresses(to))
        if cc:
            msg.cc.add(self._split_addresses(cc))
        if bcc:
            msg.bcc.add(self._split_addresses(bcc))
        msg.subject = subject
        msg.body_type = "html" if content_type.lower() == "html" else "text"
        msg.body = body
        inline: list[str] = []
        deferred: list[str] = []
        used = 0
        for path in attachments or []:
            size = os.path.getsize(path)
            if used + size <= _INLINE_ATTACHMENT_BUDGET:
                inline.append(path)
                used += size
            else:
                deferred.append(path)
        if inline:
            msg.attachments.add(inline)
        return msg, deferred

    def _save_new_draft(self, msg: Any, deferred: list[str]) -> None:
        """Save a composed message as a draft, then attach ``deferred`` files.

        python-o365 only uses upload sessions (needed above 3 MB) for
        messages that already exist, so large or overflowing attachments are
        added after the draft is created: each goes to
        ``POST /messages/{id}/attachments`` or, when over 3 MB, through
        ``createUploadSession`` + chunked ``PUT``. If that fails the draft
        is deleted and ``RuntimeError`` raised.
        """
        if not msg.save_draft():
            raise RuntimeError("Failed to save draft")
        if not deferred:
            return
        # The create POST already stored these, but python-o365 leaves them
        # flagged as not-on-cloud, so they would be uploaded a second time.
        for attachment in msg.attachments:
            attachment.on_cloud = True
        msg.attachments.add(deferred)
        error: str = ""
        try:
            # save_draft() would call this too but ignores its result.
            ok = msg.attachments._update_attachments_to_cloud()
        except Exception as exc:
            ok, error = False, f": {exc}"
        if not ok:
            draft_id = msg.object_id
            try:
                msg.delete()
            except Exception as exc:
                logger.warning("Could not delete incomplete draft %r: %s", draft_id, exc)
            raise RuntimeError(f"Failed to upload attachments to draft {draft_id!r}{error}")
        msg._track_changes.discard("attachments")

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
        attachments: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compose and send an email.

        The message is saved as a draft first and then sent, so the returned
        ``message_id`` is a real immutable ID (python-o365's direct
        ``sendMail`` path only yields the placeholder ``"sent_message"``) and
        attachments over 3 MB can be uploaded to the draft in chunks.
        """
        msg, deferred = self._compose(to, subject, body, cc, bcc, content_type, attachments)
        self._save_new_draft(msg, deferred)
        if not msg.send():
            raise RuntimeError(f"Failed to send message: {msg.object_id!r}")
        return {"message_id": msg.object_id, "status": "sent"}

    def forward_message(
        self, message_id: str, to: str, comment: str | None = None
    ) -> dict[str, Any]:
        """Forward a message via Graph ``createForward`` + ``send``.

        The forward draft already quotes the original; ``comment`` is
        prepended to it (python-o365's ``Message.body`` setter prepends when
        the body is non-empty).
        """
        src = self._get_message_or_raise(message_id)
        fwd = src.forward()
        if fwd is None:
            raise RuntimeError(f"Failed to create forward of message: {message_id!r}")
        fwd.to.add(self._split_addresses(to))
        if comment:
            if str(fwd.body_type).lower() == "html":
                fwd.body = "<p>" + html.escape(comment).replace("\n", "<br>") + "</p>"
            else:
                fwd.body = comment
        if not fwd.send():
            raise RuntimeError(f"Failed to forward message: {message_id!r}")
        return {"message_id": fwd.object_id, "status": "sent"}

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        content_type: str = "plain",
        attachments: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new draft message in the Drafts folder."""
        msg, deferred = self._compose(to, subject, body, cc, bcc, content_type, attachments)
        self._save_new_draft(msg, deferred)
        return {"message_id": msg.object_id, "status": "draft"}

    def list_drafts(self, max_results: int = 10) -> list[dict[str, Any]]:
        """Return draft summaries from the Drafts folder."""
        drafts_folder = self._mb.drafts_folder()
        messages = drafts_folder.get_messages(limit=max_results)
        return [
            {
                "message_id": msg.object_id,
                "subject": msg.subject or "",
                "snippet": msg.body_preview or "",
            }
            for msg in messages
        ]

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Send an existing draft message.

        Raises:
            ValueError: If the draft is not found or the message is not a draft.
        """
        try:
            msg = self._get_message_or_raise(draft_id)
        except ValueError:
            raise ValueError(f"Draft not found: {draft_id!r}") from None
        if not msg.is_draft:
            # Message.send() *returns* (not raises) a RuntimeError here.
            raise ValueError(f"Message {draft_id!r} is not a draft")
        if not msg.send():
            raise RuntimeError(f"Failed to send draft: {draft_id!r}")
        return {"message_id": draft_id, "status": "sent"}

    def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """Delete a draft message (Graph moves it to Deleted Items)."""
        try:
            msg = self._get_message_or_raise(draft_id)
        except ValueError:
            raise ValueError(f"Draft not found: {draft_id!r}") from None
        if not msg.delete():
            raise RuntimeError(f"Failed to delete draft: {draft_id!r}")
        return {"message_id": draft_id, "status": "deleted"}

    # ------------------------------------------------------------------
    # Internal batch helper
    # ------------------------------------------------------------------

    def _batch_graph_requests(
        self, requests: list[dict[str, Any]], message_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Send requests through Graph ``$batch`` (chunks of 20) and check results.

        Each sub-request gets the ImmutableId ``Prefer`` header (outer request
        headers are not inherited by sub-requests). Every sub-response status
        is checked. Throttled (429) sub-requests are re-sent on their own, up
        to ``_BATCH_MAX_RETRIES`` times, after waiting for the largest
        ``Retry-After`` among them (capped at ``_BATCH_MAX_SLEEP`` seconds).
        Remaining failures are collected across all chunks and raised
        together as :class:`OutlookBatchError` once every chunk has run.

        Args:
            requests: Graph batch request dicts (``id``, ``method``, ``url``…).
            message_ids: Message ID for each request (same order), used in
                error reports. Defaults to the request ``id``.

        Returns:
            All sub-response dicts (``{"id", "status", "body"}``).
        """
        acct = self._acct
        con = acct.con
        # The protocol lives on the Account (Connection has no ``protocol``);
        # service_url already ends with "/".
        url = f"{acct.protocol.service_url.rstrip('/')}/$batch"
        ids = message_ids or [r["id"] for r in requests]
        by_req_id = {r["id"]: ids[i] for i, r in enumerate(requests)}
        all_responses: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for start in range(0, len(requests), _BATCH_LIMIT):
            chunk = []
            for req in requests[start : start + _BATCH_LIMIT]:
                headers = {"Content-Type": "application/json", **req.get("headers", {})}
                prefer = headers.get("Prefer")
                if not prefer:
                    headers["Prefer"] = IMMUTABLE_ID_PREFER
                elif "immutableid" not in prefer.lower():
                    headers["Prefer"] = f"{prefer}, {IMMUTABLE_ID_PREFER}"
                chunk.append({**req, "headers": headers})

            pending = chunk
            for attempt in range(_BATCH_MAX_RETRIES + 1):
                resp = con.post(url, data={"requests": pending})
                responses = resp.json().get("responses", []) if resp else []
                seen = set()
                throttled: set[str] = set()
                delay = 0.0
                for r in responses:
                    seen.add(r.get("id"))
                    status = int(r.get("status", 0))
                    if status == 429 and attempt < _BATCH_MAX_RETRIES:
                        throttled.add(r.get("id"))
                        delay = max(delay, _retry_after_seconds(r, attempt))
                        continue
                    all_responses.append(r)
                    if not 200 <= status < 300:
                        body = r.get("body") or {}
                        err = body.get("error", {}) if isinstance(body, dict) else {}
                        failures.append(
                            {
                                "message_id": by_req_id.get(r.get("id"), r.get("id")),
                                "status": status,
                                "error": err.get("message") or err.get("code") or "",
                            }
                        )
                for req in pending:
                    if req["id"] not in seen:
                        failures.append(
                            {
                                "message_id": by_req_id.get(req["id"], req["id"]),
                                "status": 0,
                                "error": "no response in $batch reply",
                            }
                        )
                if not throttled:
                    break
                logger.info(
                    "Outlook $batch: %d sub-request(s) throttled; retrying in %.1fs",
                    len(throttled),
                    delay,
                )
                _batch_sleep(delay)
                pending = [req for req in pending if req["id"] in throttled]

        if failures:
            raise OutlookBatchError(failures, total=len(requests))
        return all_responses

    def _batch_per_message(
        self, message_ids: list[str], method: str, suffix: str, body: dict[str, Any]
    ) -> None:
        requests = [
            {
                "id": str(i),
                "method": method,
                "url": f"/me/messages/{mid}{suffix}",
                "body": body,
            }
            for i, mid in enumerate(message_ids)
        ]
        if requests:
            self._batch_graph_requests(requests, list(message_ids))

    # ------------------------------------------------------------------
    # 4. System operations (mark read, star, archive, trash)
    # ------------------------------------------------------------------

    def mark_read(self, message_id: str, read: bool = True) -> None:
        """Toggle the ``isRead`` property on a message."""
        msg = self._get_message_or_raise(message_id)
        ok = msg.mark_as_read() if read else msg.mark_as_unread()
        if not ok:
            raise RuntimeError(f"Failed to update read state: {message_id!r}")

    def set_star(self, message_id: str, starred: bool = True) -> None:
        """Toggle the follow-up flag (Outlook's equivalent of Gmail's star).

        ``Message.flag`` is a read-only ``MessageFlag``; it is changed through
        ``set_flagged()`` / ``delete_flag()`` and persisted by
        ``save_message()``.
        """
        msg = self._get_message_or_raise(message_id)
        if starred:
            msg.flag.set_flagged()
        else:
            msg.flag.delete_flag()
        if not msg.save_message():
            raise RuntimeError(f"Failed to update flag: {message_id!r}")

    def archive(self, message_id: str) -> None:
        """Move a message to the Archive well-known folder."""
        msg = self._get_message_or_raise(message_id)
        if not msg.move(self._mb.archive_folder()):
            raise RuntimeError(f"Failed to archive message: {message_id!r}")

    def trash(self, message_id: str) -> None:
        """Soft-delete a message (Graph ``DELETE`` moves it to Deleted Items)."""
        msg = self._get_message_or_raise(message_id)
        if not msg.delete():
            raise RuntimeError(f"Failed to trash message: {message_id!r}")

    def untrash(self, message_id: str) -> None:
        """Restore a message from Deleted Items back to Inbox."""
        msg = self._get_message_or_raise(message_id)
        if not msg.move(self._mb.inbox_folder()):
            raise RuntimeError(f"Failed to restore message: {message_id!r}")

    # ------------------------------------------------------------------
    # 5. Tag operations (Outlook categories)
    # ------------------------------------------------------------------

    def add_tag(self, message_id: str, tag_name: str) -> None:
        """Append a category to the message (no-op if already present)."""
        msg = self._get_message_or_raise(message_id)
        categories: list[str] = list(msg.categories) if msg.categories else []
        if tag_name not in categories:
            categories.append(tag_name)
            msg.categories = categories
            if not msg.save_message():
                raise RuntimeError(f"Failed to add category to {message_id!r}")

    def remove_tag(self, message_id: str, tag_name: str) -> None:
        """Remove a category from the message (no-op if absent)."""
        msg = self._get_message_or_raise(message_id)
        categories: list[str] = list(msg.categories) if msg.categories else []
        if tag_name in categories:
            categories.remove(tag_name)
            msg.categories = categories
            if not msg.save_message():
                raise RuntimeError(f"Failed to remove category from {message_id!r}")

    def list_tags(self) -> dict[str, str]:
        """Return the master category list as a ``{name: name}`` mapping."""
        categories = self._acct.outlook_categories().get_categories()
        return {c.name: c.name for c in categories if c.name}

    def create_tag(self, name: str) -> dict[str, str]:
        """Register a master category named ``name``; returns ``{"id", "name"}``.

        Outlook categories are free-form display-name strings — ``add_tag``
        works on any name without pre-registration — but creating the master
        category makes it appear in the user's category picker. If it already
        exists (or creation is not permitted) the name is returned as-is.
        """
        try:
            created = self._acct.outlook_categories().create_category(name)
            if created is not None:
                return {"id": created.object_id or name, "name": created.name or name}
        except Exception as exc:  # already exists or restricted — fall back to name
            logger.warning("create_tag(%r) falling back to free-form category: %s", name, exc)
        return {"id": name, "name": name}

    # ------------------------------------------------------------------
    # 7. Batch operations — Graph $batch for bulk org mutations
    # ------------------------------------------------------------------

    def batch_mark_read(self, message_ids: list[str], read: bool = True) -> None:
        """Mark messages read/unread via Graph ``$batch``."""
        self._batch_per_message(message_ids, "PATCH", "", {"isRead": read})

    def batch_archive(self, message_ids: list[str]) -> None:
        """Move messages to the Archive folder via Graph ``$batch``."""
        self._batch_per_message(message_ids, "POST", "/move", {"destinationId": "archive"})

    def batch_trash(self, message_ids: list[str]) -> None:
        """Move messages to Deleted Items via Graph ``$batch``."""
        self._batch_per_message(message_ids, "POST", "/move", {"destinationId": "deleteditems"})

    def _batch_set_categories(
        self, message_ids: list[str], tag_name: str, *, add: bool, op: str
    ) -> None:
        batch_requests: list[dict[str, Any]] = []
        batch_ids: list[str] = []
        for mid in message_ids:
            try:
                msg = self._get_message_or_raise(mid)
            except ValueError:
                logger.warning("%s: message not found, skipping: %r", op, mid)
                continue
            categories: list[str] = list(msg.categories) if msg.categories else []
            if add and tag_name not in categories:
                categories.append(tag_name)
            elif not add and tag_name in categories:
                categories.remove(tag_name)
            else:
                continue
            batch_requests.append(
                {
                    "id": str(len(batch_requests)),
                    "method": "PATCH",
                    "url": f"/me/messages/{mid}",
                    "body": {"categories": categories},
                }
            )
            batch_ids.append(mid)
        if batch_requests:
            self._batch_graph_requests(batch_requests, batch_ids)

    def batch_add_tag(self, message_ids: list[str], tag_name: str) -> None:
        """Add a category to multiple messages via Graph ``$batch``."""
        self._batch_set_categories(message_ids, tag_name, add=True, op="batch_add_tag")

    def batch_remove_tag(self, message_ids: list[str], tag_name: str) -> None:
        """Remove a category from multiple messages via Graph ``$batch``."""
        self._batch_set_categories(message_ids, tag_name, add=False, op="batch_remove_tag")

    # ------------------------------------------------------------------
    # 6. Sync — delta query for incremental sync
    # ------------------------------------------------------------------

    # Default folder used for delta sync.
    _DELTA_FOLDER = "inbox"

    def _get_inbox_delta_url(self) -> str:
        """Return the initial delta URL for the inbox folder."""
        return str(self._mb.build_url(f"/mailFolders/{self._DELTA_FOLDER}/messages/delta"))

    def get_sync_state(self) -> str:
        """Return an opaque sync-state token (the ``@odata.deltaLink``) for the inbox.

        Walks the initial delta snapshot (selecting only ``id``) until Graph
        returns the delta link.
        """
        con = self._acct.con
        return self._exhaust_delta_pages(con, self._get_inbox_delta_url(), params={"$select": "id"})

    def get_new_messages(self, sync_token: str) -> list[str] | None:
        """Return message IDs added/changed since *sync_token*.

        Returns ``None`` when the delta token has expired (HTTP 410 Gone) and
        a full re-sync is needed.
        """
        result = self.get_new_messages_with_token(sync_token)
        return None if result is None else result[0]

    def get_new_messages_with_token(self, sync_token: str) -> tuple[list[str], str] | None:
        """Like :meth:`get_new_messages` but also returns the refreshed delta link."""
        con = self._acct.con
        try:
            return self._fetch_delta(con, sync_token)
        except _DeltaGoneError:
            logger.warning("Outlook delta token expired (410 Gone). A full re-sync is required.")
            return None

    # ---- internal delta helpers ----------------------------------------

    def _fetch_delta(self, con: Any, url: str) -> tuple[list[str], str]:
        """Follow delta pages starting at *url*, collecting changed message IDs."""
        message_ids: list[str] = []
        delta_link = self._exhaust_delta_pages(con, url, message_ids=message_ids)
        return message_ids, delta_link

    def _exhaust_delta_pages(
        self,
        con: Any,
        url: str,
        message_ids: list[str] | None = None,
        params: dict[str, str] | None = None,
    ) -> str:
        """Walk all delta pages and return the final deltaLink.

        python-o365 raises ``requests.HTTPError`` for 4xx/5xx; a 410 (or a
        sync-state error code) is translated to :class:`_DeltaGoneError`.
        Items carrying ``@removed`` (deleted / moved out of the folder) are
        not reported as new.
        """
        current_url = url
        current_params = params
        seen: set[str] = set()
        while True:
            try:
                resp = con.get(current_url, params=current_params)
            except Exception as exc:
                status = _http_status(exc)
                if status == 410 or (
                    status is not None
                    and 400 <= status < 500
                    and _graph_error_code(exc).lower() in _DELTA_RESYNC_CODES
                ):
                    raise _DeltaGoneError("Delta token expired") from exc
                raise
            current_params = None  # next/delta links already carry the query

            if resp is None or not hasattr(resp, "json"):
                raise RuntimeError("Delta request returned no valid response")

            data = resp.json()

            if message_ids is not None:
                for item in data.get("value", []):
                    if "@removed" in item:
                        continue
                    mid = item.get("id")
                    if mid and mid not in seen:
                        seen.add(mid)
                        message_ids.append(mid)

            next_link: str | None = data.get("@odata.nextLink")
            delta_link: str | None = data.get("@odata.deltaLink")

            if delta_link:
                return delta_link
            if next_link:
                current_url = next_link
            else:
                raise RuntimeError(
                    "Delta response contained neither @odata.nextLink nor @odata.deltaLink"
                )


class _DeltaGoneError(Exception):
    """Internal exception raised when Graph reports an expired delta token."""
