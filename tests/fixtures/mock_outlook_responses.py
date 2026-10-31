"""
Microsoft Graph test harness for the O365 providers.

Earlier versions of this module hand-rolled ``MockMessage`` / ``MockMailbox``
classes that mirrored an *imagined* python-o365 API, so the providers passed
their tests while failing against the real library. This module instead runs
the **real** python-o365 objects (``Account``, ``Connection``, ``MailBox``,
``Message``, ``Schedule``, ``Drive`` …) and replaces only the HTTP layer:

* :class:`FakeGraph` stands in for the ``requests.Session`` that
  ``O365.connection.Connection`` sends requests through. It records every
  request (method, path, params, headers, JSON body) and answers from
  registered routes; unknown routes return a Graph-style 404 so a wrong URL
  fails loudly.
* :class:`FakeOutlookTenant` is a small stateful mailbox server built on
  ``FakeGraph`` (list/get/patch/move/delete messages, attachments, drafts,
  send, createForward, ``$batch``, master categories).
* :func:`make_real_account` builds a real ``O365.Account`` wired to a
  ``FakeGraph`` with ImmutableId preferences applied exactly as
  ``MicrosoftAuth`` does.

Everything here requires the ``outlook`` extra; factories call
``pytest.importorskip("O365")`` so tests depending on them are skipped (not
failed) when python-o365 is not installed.

Fixture data is plain Graph JSON (camelCase resource dicts) so the library's
own parsing code runs on it.
"""

from __future__ import annotations

import base64
import copy
import itertools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# Fake HTTP layer
# ---------------------------------------------------------------------------


@dataclass
class GraphCall:
    """One HTTP request observed by :class:`FakeGraph`."""

    method: str
    url: str  # full URL without the query string
    path: str  # URL path relative to GRAPH_ROOT, e.g. "/me/messages"
    params: dict[str, Any]
    headers: dict[str, str]
    body: Any  # decoded JSON body (or raw data when not JSON)


Responder = Callable[[GraphCall], "tuple[int, Any] | Any"]


@dataclass
class _Route:
    method: str
    pattern: re.Pattern[str]
    responder: Any
    status: int = 200


@dataclass
class FakeGraph:
    """Drop-in for ``requests.Session`` underneath a real O365 ``Connection``.

    ``Connection.oauth_request`` requires ``session.headers['Authorization']``
    and calls ``session.request(method, url, **kwargs)``; that is all this
    class needs to provide.
    """

    headers: dict[str, str] = field(default_factory=lambda: {"Authorization": "Bearer test"})
    calls: list[GraphCall] = field(default_factory=list)
    verify: bool = True
    proxies: dict[str, str] = field(default_factory=dict)
    _routes: list[_Route] = field(default_factory=list)

    # ── route registration ────────────────────────────────────────────────

    def route(self, method: str, path_regex: str, response: Any = None, *, status: int = 200):
        """Register a response for ``method`` + path (regex, full match).

        ``response`` is JSON-serialisable data, ``bytes`` (raw body), or a
        callable ``(GraphCall) -> data | (status, data)``. Later routes win.
        """
        self._routes.append(_Route(method.upper(), re.compile(path_regex), response, status=status))
        return self

    # ── requests.Session protocol ─────────────────────────────────────────

    def request(self, method: str, url: str, **kwargs: Any):
        import requests

        split = urlsplit(url)
        base_url = f"{split.scheme}://{split.netloc}{split.path}"
        path = base_url[len(GRAPH_ROOT) :] if base_url.startswith(GRAPH_ROOT) else split.path
        params: dict[str, Any] = {k: v[0] for k, v in parse_qs(split.query).items()}
        params.update(kwargs.get("params") or {})
        raw = kwargs.get("data")
        try:
            body = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except ValueError:
            body = raw
        call = GraphCall(
            method=method.upper(),
            url=base_url,
            path=path,
            params=params,
            headers=dict(kwargs.get("headers") or {}),
            body=body,
        )
        self.calls.append(call)

        status, payload = (
            404,
            {"error": {"code": "ErrorItemNotFound", "message": f"No fake route: {method} {path}"}},
        )
        for r in reversed(self._routes):
            if r.method == call.method and r.pattern.fullmatch(path):
                result = r.responder(call) if callable(r.responder) else r.responder
                if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
                    status, payload = result
                else:
                    status, payload = r.status, result
                break

        resp = requests.Response()
        resp.status_code = status
        resp.url = url
        resp.reason = "OK" if status < 400 else "Error"
        if isinstance(payload, bytes):
            resp._content = payload
            resp.headers["Content-Type"] = "application/octet-stream"
        elif payload is None:
            resp._content = b""
        else:
            resp._content = json.dumps(payload).encode()
            resp.headers["Content-Type"] = "application/json"
        return resp

    def mount(self, *args: Any) -> None:  # pragma: no cover - session API parity
        pass

    def close(self) -> None:
        pass

    # ── assertions helpers ────────────────────────────────────────────────

    def find(self, method: str, path_regex: str) -> list[GraphCall]:
        pat = re.compile(path_regex)
        return [c for c in self.calls if c.method == method.upper() and pat.fullmatch(c.path)]

    def last(self, method: str, path_regex: str) -> GraphCall:
        found = self.find(method, path_regex)
        assert found, f"no {method} request matching {path_regex!r}; saw {self.summary()}"
        return found[-1]

    def summary(self) -> list[str]:
        return [f"{c.method} {c.path}" for c in self.calls]


def make_real_account(graph: FakeGraph | None = None, *, username: str = "user@example.com"):
    """Return a real ``O365.Account`` whose HTTP traffic goes to *graph*.

    Mirrors what ``MicrosoftAuth.get_account()`` produces: public-client
    flow, ImmutableId preference on ``con.default_headers``.
    """
    pytest.importorskip("O365")
    from O365 import Account
    from O365.utils.token import BaseTokenBackend

    from iobox.providers.o365.auth import ensure_immutable_ids

    class _MemoryBackend(BaseTokenBackend):  # type: ignore[misc]
        def load_token(self) -> bool:
            return False

        def save_token(self, force: bool = False) -> bool:
            return True

    graph = graph or FakeGraph()
    account = Account(
        ("test-client-id",),
        auth_flow_type="public",
        token_backend=_MemoryBackend(),
        username=username,
        timezone="UTC",
        requests_delay=0,
        request_retries=0,
    )
    account.con.session = graph
    ensure_immutable_ids(account)
    return account


class FakeAuth:
    """Minimal ``MicrosoftAuth`` stand-in: ``get_account()`` returns *account*."""

    def __init__(self, account: Any) -> None:
        self._account = account
        self.calls = 0

    def get_account(self) -> Any:
        self.calls += 1
        return self._account


# ---------------------------------------------------------------------------
# Graph JSON builders
# ---------------------------------------------------------------------------


def _addr(name: str, address: str) -> dict[str, Any]:
    return {"emailAddress": {"name": name, "address": address}}


def graph_message(
    id: str = "msg-id-1",
    *,
    conversation_id: str = "conv-id-1",
    subject: str = "Test Subject",
    sender: tuple[str, str] = ("Alice Sender", "alice@example.com"),
    to: list[tuple[str, str]] | None = None,
    cc: list[tuple[str, str]] | None = None,
    received: str = "2026-03-06T10:00:00Z",
    categories: list[str] | None = None,
    body_preview: str = "This is a preview of the email body.",
    body: str = "<html><body><p>This is the email body.</p></body></html>",
    content_type: str = "html",
    is_read: bool = True,
    is_draft: bool = False,
    has_attachments: bool = False,
    flag_status: str = "notFlagged",
    folder: str = "inbox",
) -> dict[str, Any]:
    """Return a Graph ``message`` resource as /me/messages returns it.

    Graph v1.0 serialises ``body.contentType`` in lower case (``"html"`` /
    ``"text"``).
    """
    return {
        "id": id,
        "conversationId": conversation_id,
        "subject": subject,
        "from": _addr(*sender),
        "sender": _addr(*sender),
        "toRecipients": [_addr(n, a) for n, a in (to or [("Me", "me@example.com")])],
        "ccRecipients": [_addr(n, a) for n, a in (cc or [])],
        "bccRecipients": [],
        "replyTo": [],
        "receivedDateTime": received,
        "sentDateTime": received,
        "createdDateTime": received,
        "lastModifiedDateTime": received,
        "categories": list(categories or []),
        "bodyPreview": body_preview,
        "body": {"contentType": content_type, "content": body},
        "isRead": is_read,
        "isDraft": is_draft,
        "hasAttachments": has_attachments,
        "flag": {"flagStatus": flag_status},
        "parentFolderId": folder,
        "importance": "normal",
        "webLink": f"https://outlook.office.com/mail/{id}",
    }


def graph_file_attachment(
    id: str,
    name: str,
    content: bytes,
    *,
    content_type: str = "application/octet-stream",
    is_inline: bool = False,
    content_id: str | None = None,
) -> dict[str, Any]:
    """Return a Graph ``fileAttachment`` (``contentBytes`` is base64 text)."""
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "id": id,
        "name": name,
        "contentType": content_type,
        "size": len(content),
        "isInline": is_inline,
        "contentId": content_id,
        "contentBytes": base64.b64encode(content).decode("ascii"),
    }


# ---------------------------------------------------------------------------
# Stateful fake mailbox
# ---------------------------------------------------------------------------

_ID = r"(?P<id>[^/]+)"

# Real Graph reports ``parentFolderId`` as an opaque folder id, never the
# well-known name; the fake resolves these names (case-insensitively) via
# ``GET /me/mailFolders/{name}``. Other folders keep their name as their id.
WELL_KNOWN_FOLDER_IDS: dict[str, str] = {
    "deleteditems": "AAMkFolderDeletedItems",
    "junkemail": "AAMkFolderJunkEmail",
}


class FakeOutlookTenant:
    """In-memory Graph mailbox for ``/me/...`` mail endpoints.

    State lives in ``messages`` (id → Graph JSON), ``attachments``
    (message id → list of attachment JSON), ``categories`` and ``sent``.
    """

    def __init__(self, graph: FakeGraph | None = None) -> None:
        self.graph = graph or FakeGraph()
        self.messages: dict[str, dict[str, Any]] = {}
        self.attachments: dict[str, list[dict[str, Any]]] = {}
        self.categories: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.batch_status: dict[str, int] = {}  # sub-request id → forced status
        self._ids = itertools.count(1)
        self._install_routes()

    # ── seeding ───────────────────────────────────────────────────────────

    def add(self, message: dict[str, Any], attachments: list[dict[str, Any]] | None = None):
        msg = copy.deepcopy(message)
        if attachments:
            msg["hasAttachments"] = True
            self.attachments[msg["id"]] = copy.deepcopy(attachments)
        self.messages[msg["id"]] = msg
        return self

    # ── routes ────────────────────────────────────────────────────────────

    def _install_routes(self) -> None:
        g = self.graph
        g.route("GET", r"/me/messages", self._list_all)
        g.route("GET", r"/me/mailFolders/(?P<folder>[^/]+)", self._get_folder)
        g.route("GET", r"/me/mailFolders/(?P<folder>[^/]+)/messages", self._list_folder)
        g.route("GET", rf"/me/messages/{_ID}", self._get)
        g.route("PATCH", rf"/me/messages/{_ID}", self._patch)
        g.route("DELETE", rf"/me/messages/{_ID}", self._delete)
        g.route("POST", rf"/me/messages/{_ID}/move", self._move)
        g.route("GET", rf"/me/messages/{_ID}/attachments", self._list_attachments)
        g.route("GET", rf"/me/messages/{_ID}/attachments/(?P<aid>[^/]+)", self._get_attachment)
        g.route("GET", rf"/me/messages/{_ID}/attachments/(?P<aid>[^/]+)/\$value", self._att_value)
        g.route("POST", r"/me/mailFolders/(?P<folder>[^/]+)/messages", self._create_draft)
        g.route("POST", rf"/me/messages/{_ID}/send", self._send_draft)
        g.route("POST", rf"/me/messages/{_ID}/createForward", self._create_forward)
        g.route("POST", r"/me/sendMail", self._send_mail)
        g.route("GET", r"/me/outlook/masterCategories", lambda c: {"value": self.categories})
        g.route("POST", r"/me/outlook/masterCategories", self._create_category)
        g.route("POST", r"/\$batch", self._batch)

    @staticmethod
    def _m(call: GraphCall) -> str:
        m = re.search(r"/me/messages/([^/]+)", call.path)
        assert m
        return m.group(1)

    @staticmethod
    def _project(call: GraphCall, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply ``$select`` like Graph does (``id`` is always returned)."""
        select = call.params.get("$select")
        if not select:
            return items
        keep = {k.strip() for k in str(select).split(",")} | {"id"}
        return [{k: v for k, v in i.items() if k in keep or k.startswith("@odata")} for i in items]

    def _list_all(self, call: GraphCall) -> Any:
        msgs = list(self.messages.values())
        # Honour the one $filter shape the fake needs: conversationId eq '...'.
        m = re.fullmatch(r"conversationId eq '(.*)'", call.params.get("$filter", ""))
        if m:
            conv = m.group(1).replace("''", "'")
            msgs = [x for x in msgs if x.get("conversationId") == conv]
        return self._page(call, self._project(call, msgs))

    @staticmethod
    def _page(call: GraphCall, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Honour ``$top`` / ``$skip`` and emit ``@odata.nextLink`` like Graph."""
        top = call.params.get("$top")
        if top is None:
            return {"value": items}
        skip = int(call.params.get("$skip", 0))
        top = int(top)
        page: dict[str, Any] = {"value": items[skip : skip + top]}
        if skip + top < len(items):
            params = {k: str(v) for k, v in call.params.items()}
            params["$skip"] = str(skip + top)
            page["@odata.nextLink"] = f"{call.url}?{urlencode(params)}"
        return page

    def _get_folder(self, call: GraphCall) -> Any:
        name = call.path.split("/")[3]
        folder_id = WELL_KNOWN_FOLDER_IDS.get(name.lower())
        if folder_id is None:
            return 404, {"error": {"code": "ErrorFolderNotFound", "message": "no folder"}}
        return {"id": folder_id, "displayName": name}

    def _list_folder(self, call: GraphCall) -> Any:
        # Well-known folder names are case-insensitive in Graph ("Drafts").
        folder = call.path.split("/")[3].lower()
        folder = WELL_KNOWN_FOLDER_IDS.get(folder, folder)
        return {
            "value": [
                m
                for m in self.messages.values()
                if str(m.get("parentFolderId")).lower() == folder.lower()
            ]
        }

    def _get(self, call: GraphCall) -> Any:
        mid = self._m(call)
        if mid not in self.messages:
            return 404, {"error": {"code": "ErrorItemNotFound", "message": "not found"}}
        return self.messages[mid]

    def _patch(self, call: GraphCall) -> Any:
        mid = self._m(call)
        if mid not in self.messages:
            return 404, {"error": {"code": "ErrorItemNotFound", "message": "not found"}}
        self.messages[mid].update(call.body or {})
        return self.messages[mid]

    def _delete(self, call: GraphCall) -> Any:
        mid = self._m(call)
        if mid not in self.messages:
            return 404, {"error": {"code": "ErrorItemNotFound", "message": "not found"}}
        self.messages[mid]["parentFolderId"] = WELL_KNOWN_FOLDER_IDS["deleteditems"]
        return 204, None

    def _move(self, call: GraphCall) -> Any:
        mid = self._m(call)
        dest = call.body["destinationId"]
        self.messages[mid]["parentFolderId"] = WELL_KNOWN_FOLDER_IDS.get(dest.lower(), dest)
        return 201, self.messages[mid]

    # Properties of the base ``microsoft.graph.attachment`` type. ``contentId``
    # and ``contentBytes`` exist only on the derived ``fileAttachment`` type,
    # so selecting them on the collection is rejected (as Graph does).
    ATTACHMENT_BASE_PROPS = frozenset(
        {"id", "name", "contentType", "size", "isInline", "lastModifiedDateTime"}
    )

    def _list_attachments(self, call: GraphCall) -> Any:
        items = self.attachments.get(self._m(call), [])
        select = call.params.get("$select")
        if select:
            unknown = {k.strip() for k in str(select).split(",")} - self.ATTACHMENT_BASE_PROPS
            if unknown:
                return 400, {
                    "error": {
                        "code": "RequestBroker--ParseUri",
                        "message": f"Could not find a property named '{sorted(unknown)[0]}'",
                    }
                }
        return {"value": self._project(call, items)}

    def _get_attachment(self, call: GraphCall) -> Any:
        mid = self._m(call)
        aid = call.path.split("/")[-1]
        for a in self.attachments.get(mid, []):
            if a["id"] == aid:
                return a
        return 404, {"error": {"code": "ErrorItemNotFound", "message": "no attachment"}}

    def _att_value(self, call: GraphCall) -> Any:
        mid = self._m(call)
        aid = call.path.split("/")[-2]
        for a in self.attachments.get(mid, []):
            if a["id"] == aid:
                return base64.b64decode(a["contentBytes"])
        return 404, {"error": {"code": "ErrorItemNotFound", "message": "no attachment"}}

    def _create_draft(self, call: GraphCall) -> Any:
        mid = f"draft-{next(self._ids)}"
        msg = {**(call.body or {}), "id": mid, "isDraft": True, "parentFolderId": "drafts"}
        msg.setdefault("conversationId", f"conv-{mid}")
        self.messages[mid] = msg
        return 201, msg

    def _send_draft(self, call: GraphCall) -> Any:
        mid = self._m(call)
        msg = self.messages[mid]
        msg["isDraft"] = False
        msg["parentFolderId"] = "sentitems"
        self.sent.append(copy.deepcopy(msg))
        return 202, None

    def _create_forward(self, call: GraphCall) -> Any:
        src = self.messages[self._m(call)]
        mid = f"fwd-{next(self._ids)}"
        quoted = src["body"]["content"]
        fwd = graph_message(
            mid,
            conversation_id=src["conversationId"],
            subject=f"FW: {src['subject']}",
            to=[],
            body=f"<html><body><div>original:</div>{quoted}</body></html>",
            is_draft=True,
            folder="drafts",
        )
        fwd["toRecipients"] = []
        self.messages[mid] = fwd
        return 201, fwd

    def _send_mail(self, call: GraphCall) -> Any:
        self.sent.append(copy.deepcopy(call.body))
        return 202, None

    def _create_category(self, call: GraphCall) -> Any:
        cat = {"id": f"cat-{next(self._ids)}", **(call.body or {})}
        self.categories.append(cat)
        return 201, cat

    def _batch(self, call: GraphCall) -> Any:
        responses = []
        for req in call.body["requests"]:
            status = self.batch_status.get(req["id"], 200)
            body: Any = {}
            if status >= 400:
                body = {"error": {"code": "ErrorItemNotFound", "message": "batch item failed"}}
            responses.append({"id": req["id"], "status": status, "body": body})
        return {"responses": responses}

    # ── wiring ────────────────────────────────────────────────────────────

    def account(self):
        return make_real_account(self.graph)


# ---------------------------------------------------------------------------
# Pre-built fixture data (Graph JSON)
# ---------------------------------------------------------------------------

ATTACHMENT_PDF_BYTES = b"%PDF-1.4 mock pdf content"
ATTACHMENT_PNG_BYTES = b"\x89PNG\r\n mock png content"

MOCK_ATTACHMENT_FILE = graph_file_attachment(
    "outlook-attach-id-1", "document.pdf", ATTACHMENT_PDF_BYTES, content_type="application/pdf"
)
MOCK_ATTACHMENT_IMAGE = graph_file_attachment(
    "outlook-attach-id-2",
    "screenshot.png",
    ATTACHMENT_PNG_BYTES,
    content_type="image/png",
    is_inline=True,
    content_id="logo@cid",
)

MOCK_PLAIN_TEXT_MESSAGE = graph_message(
    "outlook-msg-id-1",
    conversation_id="outlook-conv-id-1",
    subject="Plain Text Email",
    sender=("Bob Sender", "bob@example.com"),
    received="2026-03-06T09:00:00Z",
    body_preview="This is a plain text email.",
    body="This is a plain text email.",
    content_type="text",
    categories=["Work"],
)
MOCK_HTML_MESSAGE = graph_message(
    "outlook-msg-id-2",
    conversation_id="outlook-conv-id-2",
    subject="HTML Email Subject",
    sender=("Carol Sender", "carol@example.com"),
    received="2026-03-06T10:00:00Z",
    body_preview="This is the HTML version of the email.",
    body="<html><body><p>This is the <strong>HTML</strong> version of the email.</p></body></html>",
    is_read=False,
)
MOCK_ATTACHMENT_MESSAGE = graph_message(
    "outlook-msg-id-3",
    conversation_id="outlook-conv-id-3",
    subject="Email with Attachment",
    sender=("Dave Sender", "dave@example.com"),
    received="2026-03-06T11:00:00Z",
    body_preview="This email has an attachment.",
    has_attachments=True,
)
MOCK_MULTI_ATTACHMENT_MESSAGE = graph_message(
    "outlook-msg-id-4",
    conversation_id="outlook-conv-id-3",
    subject="Email with Multiple Attachments",
    sender=("Dave Sender", "dave@example.com"),
    received="2026-03-06T11:30:00Z",
    has_attachments=True,
)
MOCK_DRAFT_MESSAGE = graph_message(
    "outlook-draft-id-1",
    conversation_id="outlook-conv-draft-1",
    subject="Draft Email",
    sender=("Eve Sender", "eve@example.com"),
    received="2026-03-06T08:00:00Z",
    body_preview="This is a draft email.",
    is_draft=True,
    folder="drafts",
)
MOCK_STARRED_MESSAGE = graph_message(
    "outlook-msg-id-5",
    conversation_id="outlook-conv-id-5",
    subject="Starred/Flagged Email",
    sender=("Frank Sender", "frank@example.com"),
    received="2026-03-06T07:00:00Z",
    categories=["Important"],
    flag_status="flagged",
)
MOCK_UNREAD_MESSAGE = graph_message(
    "outlook-msg-id-6",
    conversation_id="outlook-conv-id-6",
    subject="Unread Email",
    sender=("Grace Sender", "grace@example.com"),
    received="2026-03-06T06:00:00Z",
    is_read=False,
)
# Thread: reply listed first to prove client-side chronological sorting.
MOCK_THREAD_MESSAGE_2 = graph_message(
    "outlook-thread-msg-2",
    conversation_id="outlook-conv-thread-1",
    subject="Re: Thread Email",
    sender=("Iris Recipient", "iris@example.com"),
    received="2026-03-06T09:30:00Z",
    folder="sentitems",
)
MOCK_THREAD_MESSAGE_1 = graph_message(
    "outlook-thread-msg-1",
    conversation_id="outlook-conv-thread-1",
    subject="Thread Email",
    sender=("Hank Sender", "hank@example.com"),
    received="2026-03-06T09:00:00Z",
)

MOCK_MASTER_CATEGORIES: list[dict[str, Any]] = [
    {"id": "cat-id-1", "displayName": "Work", "color": "preset0"},
    {"id": "cat-id-2", "displayName": "Personal", "color": "preset1"},
    {"id": "cat-id-3", "displayName": "Important", "color": "preset2"},
]

DELTA_ROOT = f"{GRAPH_ROOT}/me/mailFolders/inbox/messages/delta"

MOCK_DELTA_RESPONSE: dict[str, Any] = {
    "value": [
        {"id": "outlook-msg-id-1", "subject": "Plain Text Email"},
        {"id": "outlook-msg-id-2", "subject": "HTML Email Subject"},
    ],
    "@odata.deltaLink": f"{DELTA_ROOT}?$deltatoken=abc123",
}
MOCK_DELTA_RESPONSE_WITH_REMOVED: dict[str, Any] = {
    "value": [
        {"id": "outlook-msg-id-1", "subject": "New Message"},
        {"id": "outlook-msg-id-deleted", "@removed": {"reason": "deleted"}},
    ],
    "@odata.deltaLink": f"{DELTA_ROOT}?$deltatoken=def456",
}
MOCK_DELTA_RESPONSE_EMPTY: dict[str, Any] = {
    "value": [],
    "@odata.deltaLink": f"{DELTA_ROOT}?$deltatoken=ghi789",
}
MOCK_DELTA_RESPONSE_EXPIRED: dict[str, Any] = {
    "error": {
        "code": "SyncStateNotFound",
        "message": "The sync state generation is not found. Please do a full sync.",
    }
}


def make_full_tenant() -> FakeOutlookTenant:
    """Return a tenant seeded with every fixture message (O365 required)."""
    pytest.importorskip("O365")
    tenant = FakeOutlookTenant()
    for msg in (
        MOCK_PLAIN_TEXT_MESSAGE,
        MOCK_HTML_MESSAGE,
        MOCK_STARRED_MESSAGE,
        MOCK_UNREAD_MESSAGE,
        MOCK_THREAD_MESSAGE_2,
        MOCK_THREAD_MESSAGE_1,
        MOCK_DRAFT_MESSAGE,
    ):
        tenant.add(msg)
    tenant.add(MOCK_ATTACHMENT_MESSAGE, [MOCK_ATTACHMENT_FILE])
    tenant.add(MOCK_MULTI_ATTACHMENT_MESSAGE, [MOCK_ATTACHMENT_FILE, MOCK_ATTACHMENT_IMAGE])
    tenant.categories = copy.deepcopy(MOCK_MASTER_CATEGORIES)
    return tenant


def make_full_mock_account():
    """Return a real ``O365.Account`` backed by :func:`make_full_tenant`.

    The tenant is reachable as ``account.con.session`` (a :class:`FakeGraph`)
    and ``account.tenant``.
    """
    tenant = make_full_tenant()
    account = tenant.account()
    account.tenant = tenant
    return account


def make_outlook_provider(tenant: FakeOutlookTenant | None = None, **kwargs: Any):
    """Return an ``OutlookProvider`` wired to *tenant* (default: full tenant)."""
    from iobox.providers.o365.email import OutlookProvider

    tenant = tenant or make_full_tenant()
    provider = OutlookProvider(auth=FakeAuth(tenant.account()), **kwargs)
    provider.tenant = tenant  # type: ignore[attr-defined]
    return provider


# ---------------------------------------------------------------------------
# Calendar (Graph event resources)
# ---------------------------------------------------------------------------

DEFAULT_CALENDAR: dict[str, Any] = {"id": "cal-default", "name": "Calendar", "canEdit": True}


def graph_event(
    id: str = "evt-1",
    *,
    subject: str = "Team standup",
    start: str = "2026-03-15T09:00:00.0000000",
    end: str = "2026-03-15T09:30:00.0000000",
    time_zone: str = "UTC",
    is_all_day: bool = False,
    body: str = "",
    content_type: str = "html",
    location: str | None = None,
    organizer: tuple[str, str] | None = ("Org Anizer", "org@example.com"),
    attendees: list[tuple[str, str, str]] | None = None,
    online_meeting_url: str | None = None,
    is_cancelled: bool = False,
) -> dict[str, Any]:
    """Return a Graph ``event`` resource (``attendees``: (name, email, response))."""
    return {
        "id": id,
        "subject": subject,
        "body": {"contentType": content_type, "content": body},
        "start": {"dateTime": start, "timeZone": time_zone},
        "end": {"dateTime": end, "timeZone": time_zone},
        "isAllDay": is_all_day,
        "location": {"displayName": location or "", "locationType": "default"},
        "organizer": {"emailAddress": {"name": organizer[0], "address": organizer[1]}}
        if organizer
        else None,
        "attendees": [
            {
                "type": "required",
                "status": {"response": resp, "time": "0001-01-01T00:00:00Z"},
                "emailAddress": {"name": n, "address": a},
            }
            for n, a, resp in (attendees or [])
        ],
        "onlineMeetingUrl": online_meeting_url,
        "isOnlineMeeting": False,
        "isCancelled": is_cancelled,
        "createdDateTime": "2026-01-01T00:00:00Z",
        "lastModifiedDateTime": "2026-03-01T00:00:00Z",
        "webLink": f"https://outlook.office365.com/owa/?itemid={id}",
        "responseStatus": {"response": "none", "time": "0001-01-01T00:00:00Z"},
        "type": "singleInstance",
    }


def make_calendar_provider(
    events: list[dict[str, Any]] | None = None, *, mode: str = "standard"
) -> Any:
    """Return an ``OutlookCalendarProvider`` over a fake Graph calendar.

    ``provider.graph`` is the :class:`FakeGraph`; ``provider.events`` the
    id → event store used by GET/PATCH/DELETE ``/me/events/{id}``.
    """
    pytest.importorskip("O365")
    from iobox.providers.o365.calendar import OutlookCalendarProvider

    graph = FakeGraph()
    store: dict[str, dict[str, Any]] = {e["id"]: copy.deepcopy(e) for e in events or []}
    counter = itertools.count(1)

    def _event_id(call: GraphCall) -> str:
        return call.path.split("/")[3]

    def _get(call: GraphCall) -> Any:
        ev = store.get(_event_id(call))
        return ev if ev else (404, {"error": {"code": "ErrorItemNotFound", "message": "nf"}})

    def _patch(call: GraphCall) -> Any:
        store[_event_id(call)].update(call.body or {})
        return store[_event_id(call)]

    def _create(call: GraphCall) -> Any:
        ev = {**call.body, "id": f"new-evt-{next(counter)}"}
        ev.setdefault("createdDateTime", "2026-04-01T00:00:00Z")
        store[ev["id"]] = ev
        return 201, ev

    def _respond(call: GraphCall) -> Any:
        action = call.path.rsplit("/", 1)[-1]
        response = {
            "accept": "accepted",
            "decline": "declined",
            "tentativelyAccept": "tentativelyAccepted",
        }[action]
        store[call.path.split("/")[3]]["responseStatus"] = {"response": response}
        return 202, None

    graph.route("GET", r"/me/calendar", DEFAULT_CALENDAR)
    graph.route(
        "GET", r"/me/calendars/cal-default/calendarView", lambda c: {"value": list(store.values())}
    )
    graph.route("POST", r"/me/calendars/cal-default/events", _create)
    graph.route("GET", r"/me/events/[^/]+", _get)
    graph.route("PATCH", r"/me/events/[^/]+", _patch)
    graph.route("DELETE", r"/me/events/[^/]+", lambda c: (204, None))
    graph.route("POST", r"/me/events/[^/]+/(accept|decline|tentativelyAccept)", _respond)

    provider = OutlookCalendarProvider(
        account_email="user@example.com", mode=mode, auth=FakeAuth(make_real_account(graph))
    )
    provider.graph = graph  # type: ignore[attr-defined]
    provider.events = store  # type: ignore[attr-defined]
    return provider


# ---------------------------------------------------------------------------
# OneDrive (Graph driveItem resources)
# ---------------------------------------------------------------------------


def graph_drive_item(
    id: str = "item-1",
    *,
    name: str = "report.txt",
    folder: bool = False,
    mime_type: str = "text/plain",
    size: int = 42,
    parent_id: str = "root-id",
    parent_path: str = "/drive/root:",
) -> dict[str, Any]:
    """Return a Graph ``driveItem`` resource (file or folder)."""
    item: dict[str, Any] = {
        "id": id,
        "name": name,
        "size": size,
        "webUrl": f"https://onedrive.live.com/?id={id}",
        "createdDateTime": "2026-01-01T00:00:00Z",
        "lastModifiedDateTime": "2026-03-01T12:00:00Z",
        "parentReference": {"driveId": "drive-1", "id": parent_id, "path": parent_path},
    }
    if folder:
        item["folder"] = {"childCount": 0}
    else:
        item["file"] = {"mimeType": mime_type, "hashes": {}}
    return item


ROOT_FOLDER: dict[str, Any] = {
    "id": "root-id",
    "name": "root",
    "folder": {"childCount": 2},
    "root": {},
    "parentReference": {"driveId": "drive-1"},
}


def make_onedrive_provider(
    items: list[dict[str, Any]] | None = None,
    *,
    mode: str = "standard",
    contents: dict[str, bytes] | None = None,
) -> Any:
    """Return a ``OneDriveProvider`` over a fake Graph drive (``provider.graph``)."""
    pytest.importorskip("O365")
    from iobox.providers.o365.files import OneDriveProvider

    graph = FakeGraph()
    store: dict[str, dict[str, Any]] = {i["id"]: copy.deepcopy(i) for i in items or []}
    blobs = dict(contents or {})
    counter = itertools.count(1)

    def _get(call: GraphCall) -> Any:
        item_id = call.path.rsplit("/", 1)[-1]
        if item_id == "root-id":
            return ROOT_FOLDER
        it = store.get(item_id)
        return it if it else (404, {"error": {"code": "itemNotFound", "message": "nf"}})

    def _children(call: GraphCall) -> Any:
        parent = "root-id" if call.path.endswith("/root/children") else call.path.split("/")[-2]
        return {"value": [i for i in store.values() if i["parentReference"].get("id") == parent]}

    def _content(call: GraphCall) -> Any:
        return blobs.get(call.path.split("/")[-2], b"")

    def _mkdir(call: GraphCall) -> Any:
        parent = call.path.split("/")[-2]
        new = graph_drive_item(
            f"folder-{next(counter)}", name=call.body["name"], folder=True, parent_id=parent
        )
        store[new["id"]] = new
        return 201, new

    def _upload(call: GraphCall) -> Any:
        # PUT /items/{parent}:/{name}:/content (simple upload, < 4 MB)
        m = re.fullmatch(r".*/items/([^/:]+):/(.+):/content", call.path)
        assert m, call.path
        parent, name = m.groups()
        existing = next(
            (
                i
                for i in store.values()
                if i["name"] == name and i["parentReference"].get("id") == parent
            ),
            None,
        )
        item = existing or graph_drive_item(f"up-{next(counter)}", name=name, parent_id=parent)
        store[item["id"]] = item
        return 201, item

    graph.route("GET", r"/me/drive", {"id": "drive-1", "name": "OneDrive", "driveType": "business"})
    graph.route("GET", r"/me/drive/root", ROOT_FOLDER)
    graph.route("GET", r"/me/drive/items/[^/]+", _get)
    graph.route("GET", r"/me/drive/items/[^/]+/children", _children)
    graph.route("GET", r"/me/drive/root/children", _children)
    graph.route("GET", r"/me/drive/items/[^/]+/content", _content)
    graph.route("POST", r"/me/drive/items/[^/]+/children", _mkdir)
    graph.route("PUT", r"/me/drive/items/.+:/content", _upload)
    graph.route("DELETE", r"/me/drive/items/[^/]+", lambda c: (204, None))
    graph.route("POST", r"/me/drive/items/[^/]+/permanentDelete", lambda c: (204, None))
    graph.route("GET", r"/me/drive/search\(q='.*'\)", lambda c: {"value": list(store.values())})
    graph.route("GET", r"/me/drive/sharedWithMe", lambda c: {"value": list(store.values())})

    provider = OneDriveProvider(
        account_email="user@example.com", mode=mode, auth=FakeAuth(make_real_account(graph))
    )
    provider.graph = graph  # type: ignore[attr-defined]
    provider.items = store  # type: ignore[attr-defined]
    return provider
