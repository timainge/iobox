"""
MCP Server for iobox workspace tools.

Exposes iobox functions as MCP tools for use with Claude Desktop,
Cursor, VS Code, and other MCP-compatible hosts.

Install with: pip install iobox[mcp]
Run with: python -m iobox.mcp_server
"""

import functools
import os
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from iobox.modes import MCP_TOOLS_BY_MODE, AccessMode, get_mode_from_env
from iobox.processing.file_manager import (
    SyncState,
    check_for_duplicates,
    create_output_directory,
    download_email_attachments,
    save_email_to_markdown,
)
from iobox.processing.markdown_converter import (
    convert_email_to_markdown,
    convert_thread_to_markdown,
)
from iobox.providers.google.auth import (
    check_auth_status,
    set_active_mode,
)
from iobox.utils import slugify_text

mcp = FastMCP("iobox")

# ---------------------------------------------------------------------------
# Tool registry – functions are collected here and selectively registered
# with mcp.tool() based on the active access mode.
# ---------------------------------------------------------------------------

_ALL_TOOLS: dict[str, Any] = {}


class ToolInputError(Exception):
    """A tool call that must be refused with ``{"error": ...}`` rather than raised.

    Raised by helpers (workspace loading, path confinement) deep inside a tool;
    the ``_tool`` wrapper converts it into the tool's error return shape.
    """


class WorkspaceLoadError(ToolInputError):
    """A named or active workspace is configured but could not be loaded."""


def _error_result(fn: Any, message: str) -> Any:
    """Return ``{"error": message}`` in the shape *fn* normally returns."""
    ret = getattr(fn, "__annotations__", {}).get("return")
    if ret is list or typing.get_origin(ret) is list:
        return [{"error": message}]
    return {"error": message}


def _tool(fn: Any) -> Any:
    """Collect a tool function without registering it yet.

    The collected wrapper turns a ``ToolInputError`` into an ``{"error": ...}``
    result so a refused call never surfaces as an unhandled exception.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolInputError as exc:
            return _error_result(fn, str(exc))

    _ALL_TOOLS[fn.__name__] = wrapper
    return wrapper


def register_tools(mode: AccessMode) -> None:
    """Register only the MCP tools allowed for *mode*."""
    allowed = MCP_TOOLS_BY_MODE[mode]
    for name, fn in _ALL_TOOLS.items():
        if name in allowed:
            mcp.tool()(fn)


# ---------------------------------------------------------------------------
# Provider / workspace factories (injectable for tests)
# ---------------------------------------------------------------------------


def _get_gmail_provider() -> Any:
    """Return a GmailProvider instance. Override in tests by patching."""
    from iobox.providers.google.email import GmailProvider

    return GmailProvider()


def _default_workspace_fn(name: str | None = None) -> Any | None:
    """Default factory: load the named (or active) workspace from disk.

    Returns ``None`` only when no workspace is requested *and* none is active —
    the one case where email tools may fall back to legacy single-account Gmail.
    A requested or active workspace that fails to load raises
    ``WorkspaceLoadError``; it never silently degrades to another account.
    """
    from iobox.space_config import IOBOX_HOME, get_active_space, load_space
    from iobox.workspace import Workspace

    try:
        target = name or get_active_space()
    except Exception as exc:
        raise WorkspaceLoadError(f"Could not read the active workspace: {exc}") from exc
    if not target:
        return None
    try:
        config = load_space(target)
        return Workspace.from_config(config, credentials_dir=str(IOBOX_HOME))
    except Exception as exc:
        raise WorkspaceLoadError(f"Could not load workspace '{target}': {exc}") from exc


def create_mcp_server(*, _workspace_fn: Callable[..., Any] | None = None) -> FastMCP:
    """Build the FastMCP server with an optional mock workspace factory for tests."""
    return mcp


# Module-level workspace factory (can be replaced in tests).
# Accepts an optional workspace name; ``None`` means "use the active space".
_workspace_factory: Callable[..., Any | None] = _default_workspace_fn


def _get_workspace(name: str | None = None) -> Any | None:
    """Return the named (or active) Workspace, or None if none is configured.

    Raises ``WorkspaceLoadError`` when a requested/active workspace can't load.
    """
    return _workspace_factory(name)


def _find_email_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named email slot, or the first slot if name is None."""
    if not ws.email_providers:
        return None
    if name is None:
        return ws.email_providers[0]
    for slot in ws.email_providers:
        if slot.name == name:
            return slot
    return None


def _find_calendar_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named calendar slot, or the first slot if name is None."""
    if not ws.calendar_providers:
        return None
    if name is None:
        return ws.calendar_providers[0]
    for slot in ws.calendar_providers:
        if slot.name == name:
            return slot
    return None


def _find_file_slot(ws: Any, name: str | None = None) -> Any | None:
    """Return the named file slot, or the first slot if name is None."""
    if not ws.file_providers:
        return None
    if name is None:
        return ws.file_providers[0]
    for slot in ws.file_providers:
        if slot.name == name:
            return slot
    return None


def _resolve_email_provider(
    provider: str | None = None,
    workspace: str | None = None,
) -> Any:
    """Resolve an email provider via workspace slot, falling back to legacy Gmail.

    Resolution order:
    1. If a workspace (named or active) is configured, return the matching
       email slot's provider — this is the only path that supports multiple
       Gmail/Outlook accounts. A workspace that fails to load, or has no email
       slots, is an error (never a silent fallback to another account).
    2. Only when no workspace is requested or active, fall back to the legacy
       module-level ``GmailProvider()`` (single-account, env-driven).
    """
    ws = _get_workspace(workspace)
    if ws is not None:
        if not ws.email_providers:
            raise WorkspaceLoadError(f"Workspace '{ws.name}' has no email accounts configured.")
        slot = _find_email_slot(ws, provider)
        if slot is None:
            available = ", ".join(s.name for s in ws.email_providers)
            raise ValueError(
                f"Email provider '{provider}' not found in workspace. Available: {available}"
            )
        return slot.provider
    if provider is not None:
        raise ValueError(
            "No active workspace; cannot route by provider name. "
            "Run `iobox space create` and `iobox space add google ACCOUNT --email ...` first."
        )
    return _get_gmail_provider()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class PathNotAllowedError(ToolInputError):
    """A filesystem path supplied to a tool falls outside the MCP root."""


_DEFAULT_MCP_ROOT = "~/iobox"


def _mcp_root() -> Path:
    """Return the resolved directory every MCP filesystem path is confined to.

    Set with ``IOBOX_MCP_ROOT`` (default ``~/iobox``). Created on demand.
    """
    raw = os.environ.get("IOBOX_MCP_ROOT", "").strip() or _DEFAULT_MCP_ROOT
    root = Path(os.path.realpath(os.path.expanduser(raw)))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _denied_paths() -> tuple[list[Path], list[Path]]:
    """Return (denied directories, denied files) holding credentials or tokens.

    ``~/.iobox`` (workspace tokens) is always denied, even when the MCP root is
    configured to contain it. The legacy single-account credential/token files
    under ``CREDENTIALS_DIR`` are denied too.
    """

    def _real(p: str) -> Path:
        return Path(os.path.realpath(os.path.expanduser(p)))

    creds_dir = os.environ.get("CREDENTIALS_DIR") or os.getcwd()
    dirs = [_real("~/.iobox"), _real(os.path.join(creds_dir, "tokens"))]
    files = [
        _real(
            os.path.join(
                creds_dir, os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            )
        ),
        _real(os.path.join(creds_dir, os.environ.get("GMAIL_TOKEN_FILE", "token.json"))),
        _real(os.path.join(creds_dir, "o365_token.txt")),
    ]
    return dirs, files


def _confine_path(path: str | None, *, purpose: str = "path") -> Path:
    """Resolve *path* inside the MCP root, or raise ``PathNotAllowedError``.

    Relative paths resolve under the root; absolute (and ``~``) paths must
    resolve inside it. Symlinks are resolved first (``os.path.realpath``) so a
    link inside the root can't point outside it. Paths inside ``~/.iobox`` or
    at legacy credential/token files are always refused.
    """
    root = _mcp_root()
    raw = (path or "").strip() or "."
    expanded = os.path.expanduser(raw)
    candidate = expanded if os.path.isabs(expanded) else os.path.join(root, expanded)
    resolved = Path(os.path.realpath(candidate))

    if resolved != root and not resolved.is_relative_to(root):
        raise PathNotAllowedError(
            f"{purpose} {raw!r} is outside the iobox MCP root {str(root)!r}. "
            "Use a path inside it (relative paths resolve under it), or set "
            "IOBOX_MCP_ROOT to change it."
        )
    denied_dirs, denied_files = _denied_paths()
    if any(resolved == d or resolved.is_relative_to(d) for d in denied_dirs) or (
        resolved in denied_files
    ):
        raise PathNotAllowedError(f"{purpose} {raw!r} points at iobox credentials or tokens.")
    return resolved


def _confine_existing_file(path: str, *, purpose: str) -> Path:
    """Confine *path* and require it to be an existing regular file."""
    resolved = _confine_path(path, purpose=purpose)
    if not resolved.is_file():
        raise PathNotAllowedError(f"{purpose} not found or not a regular file: {path!r}")
    return resolved


def _confine_output_dir(output_dir: str | None) -> str:
    """Confine and create an output directory; return it as a string."""
    resolved = _confine_path(output_dir, purpose="output_dir")
    return create_output_directory(str(resolved))


def _confine_attachments(attachments: list[str] | None) -> list[str] | None:
    """Confine each outgoing attachment path; return the resolved paths."""
    if not attachments:
        return attachments
    return [str(_confine_existing_file(fp, purpose="Attachment")) for fp in attachments]


def _write_new_file(path: Path, data: bytes) -> None:
    """Write *data* to *path*, refusing to overwrite anything already there.

    ``O_EXCL`` also refuses a pre-planted symlink at *path*.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "xb") as fh:
            fh.write(data)
    except FileExistsError:
        raise PathNotAllowedError(
            f"Refusing to overwrite existing file {str(path)!r}; choose a new output_path."
        ) from None


def _email_data_to_dict(data: Any) -> dict[str, Any]:
    """Convert EmailData (from_ key) to legacy MCP format (from key).

    Preserves backward compatibility for MCP clients that expect ``from``
    rather than ``from_``.
    """
    result = dict(data)
    if "from_" in result and "from" not in result:
        result["from"] = result.pop("from_")
    return result


_VALID_BODY_MODES = ("none", "text", "html", "markdown")


def _apply_body_mode(data: dict[str, Any], mode: str, max_body_chars: int | None) -> dict[str, Any]:
    """Apply a ``get_email`` body mode (none|text|html|markdown) + truncation.

    Operates on an already-fetched, ``_email_data_to_dict``-normalised dict.
    ``markdown`` converts an HTML body; ``text`` converts an HTML body to plain
    text (HTML-only emails and Outlook bodies have no text/plain part);
    ``none`` drops the body entirely.
    """
    from iobox.processing.markdown_converter import (
        convert_html_to_markdown,
        convert_html_to_text,
    )

    raw_body = data.get("body", "") or ""
    fetched_type = data.get("content_type", "text/plain")

    if mode == "none":
        data.pop("body", None)
        data.pop("content_type", None)
        return data

    if mode == "markdown":
        data["body"] = (
            convert_html_to_markdown(raw_body) if fetched_type == "text/html" else raw_body
        )
        data["content_type"] = "text/markdown"
    elif mode == "text" and fetched_type == "text/html":
        data["body"] = convert_html_to_text(raw_body)
        data["content_type"] = "text/plain"
    else:
        data["body"] = raw_body

    if max_body_chars is not None and len(data["body"]) > max_body_chars:
        omitted = len(data["body"]) - max_body_chars
        data["body"] = data["body"][:max_body_chars] + f"\n...[truncated {omitted} chars]"
        data["truncated"] = True

    return data


BATCH_MAX_RESULTS = 100


def _parse_ymd(value: str, field: str) -> Any:
    """Parse ``YYYY/MM/DD`` (or ``YYYY-MM-DD``) into a ``date``."""
    from datetime import date

    try:
        y, m, d = (int(x) for x in value.replace("-", "/").split("/"))
        return date(y, m, d)
    except (ValueError, TypeError):
        raise ToolInputError(f"{field} must be YYYY/MM/DD, got {value!r}.") from None


def _batch_query(
    query: str,
    max_results: int,
    days: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[Any, str | None]:
    """Build a bounded ``EmailQuery`` for a destructive batch tool.

    Requires a non-empty query, and ``days >= 1`` unless ``start_date`` gives
    an explicit lower bound. Clamps ``max_results`` to 1..``BATCH_MAX_RESULTS``.
    Returns ``(query, note)`` where *note* explains any clamping.
    """
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    if not query or not query.strip():
        raise ToolInputError(
            "Batch operations require a non-empty query; refusing to act on the whole mailbox."
        )
    if start_date:
        after = _parse_ymd(start_date, "start_date")
    elif days is None or days < 1:
        raise ToolInputError(
            "Batch operations require days >= 1 (or an explicit start_date); "
            "refusing to act on the whole mailbox history."
        )
    else:
        after = date.today() - timedelta(days=days)
    before = _parse_ymd(end_date, "end_date") if end_date else None
    limit = max(1, min(int(max_results), BATCH_MAX_RESULTS))
    eq = EmailQuery(text=query, max_results=limit, after=after, before=before)
    note = f"max_results clamped to {limit}." if limit != max_results else None
    return eq, note


def _run_batch(
    message_ids: list[str], action: Callable[[str], Any]
) -> tuple[list[str], list[dict[str, str]]]:
    """Apply *action* to each ID, collecting per-item failures instead of aborting."""
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for mid in message_ids:
        try:
            action(mid)
            succeeded.append(mid)
        except Exception as exc:
            failed.append({"message_id": mid, "error": str(exc)})
    return succeeded, failed


def _batch_result(
    count_key: str,
    matched: int,
    succeeded: list[str],
    failed: list[dict[str, str]],
    note: str | None,
) -> dict[str, Any]:
    """Summarise a batch: ``<count_key>`` (successes), matched, per-item outcome."""
    result: dict[str, Any] = {
        count_key: len(succeeded),
        "matched_count": matched,
        "succeeded": succeeded,
        "failed": failed,
    }
    if note:
        result["detail"] = note
    return result


# ---------------------------------------------------------------------------
# Search & Read
# ---------------------------------------------------------------------------


@_tool
def search_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    include_spam_trash: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """Search email for messages matching a query.

    When an iobox workspace is active, this fans out across the configured
    email slots (Gmail and/or Outlook). Pass ``provider`` to target a single
    slot, or omit to search every email slot in parallel. With no active
    workspace, falls back to the single-account Gmail provider.

    Args:
        query: Search text (Gmail uses Gmail search syntax; Outlook accepts
            free-text and basic operators).
        max_results: Maximum number of results per slot (default 10). Every
            returned row carries full metadata (subject/from/to/cc/date/labels)
            up to this count — there are no empty placeholder rows.
        days: Days back to search (default 7). Used only when ``start_date`` is
            not given.
        start_date: Start date YYYY/MM/DD. When set, it takes precedence over
            ``days`` for the lower bound.
        end_date: End date YYYY/MM/DD. Independent upper bound; combine with
            ``start_date`` (or ``days``) to bound a window on both sides.
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name (e.g. ``"personal-gmail"``).
        workspace: Optional workspace name (default: active workspace).
    """
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    # Build EmailQuery from the legacy date params
    after: date | None = None
    before: date | None = None
    if start_date:
        parts = start_date.replace("-", "/").split("/")
        after = date(int(parts[0]), int(parts[1]), int(parts[2]))
    elif days:
        after = date.today() - timedelta(days=days)
    if end_date:
        parts = end_date.replace("-", "/").split("/")
        before = date(int(parts[0]), int(parts[1]), int(parts[2]))

    eq = EmailQuery(
        text=query,
        max_results=max_results,
        after=after,
        before=before,
        include_spam_trash=include_spam_trash,
    )

    ws = _get_workspace(workspace)
    if ws is not None:
        if not ws.email_providers:
            return [{"error": f"Workspace '{ws.name}' has no email accounts configured."}]
        providers_arg = [provider] if provider else None
        try:
            results = ws.search_emails(eq, providers=providers_arg)
        except Exception as exc:
            return [{"error": str(exc)}]
        return [_email_data_to_dict(r) for r in results]

    # Legacy fallback: single-account Gmail (no workspace configured at all)
    if provider is not None:
        return [{"error": "No active workspace; cannot route by provider name."}]
    p = _get_gmail_provider()
    results = p.search_emails(eq)
    return [_email_data_to_dict(r) for r in results]


@_tool
def get_email(
    message_id: str,
    body: str = "markdown",
    max_body_chars: int | None = None,
    prefer_html: bool | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Retrieve email content by message ID, with control over body size.

    A single raw-HTML email can be tens of thousands of characters and blow the
    tool's token budget. Use ``body`` and ``max_body_chars`` to keep responses
    small — default ``"markdown"`` is far more compact than raw HTML.

    Args:
        message_id: Email message ID (Gmail message ID or Outlook ImmutableId).
        body: How to return the message body:
            ``"none"`` — headers + attachment manifest only, no body;
            ``"text"`` — plain-text body;
            ``"html"`` — raw HTML body;
            ``"markdown"`` (default) — HTML converted to compact Markdown.
        max_body_chars: If set, truncate the body to this many characters and
            set ``truncated: true`` in the result. ``None`` means no limit.
        prefer_html: Deprecated. ``True`` maps to ``body="html"``, ``False`` to
            ``body="text"``. Ignored when ``body`` is set to a non-default value.
        provider: Optional email slot name. Required when the workspace has
            multiple email slots and you want a specific account.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Email dict. The ``body`` field reflects the requested mode (absent for
        ``"none"``); ``truncated`` is present and True when the body was cut.
    """
    # Backward-compat: honour prefer_html only when body is left at default.
    mode = body.lower()
    if prefer_html is not None and mode == "markdown":
        mode = "html" if prefer_html else "text"

    if mode not in _VALID_BODY_MODES:
        return {"error": f"Invalid body mode {body!r}. Use none|text|html|markdown."}

    # Fetch richer HTML when we need to render markdown or html; plain otherwise.
    content_type = "text/html" if mode in ("html", "markdown") else "text/plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    data = _email_data_to_dict(p.get_email_content(message_id, content_type))
    return _apply_body_mode(data, mode, max_body_chars)


@_tool
def get_emails(
    message_ids: list[str],
    body: str = "none",
    max_body_chars: int | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """Fetch multiple emails in one call — the fast path for triage scanning.

    Retrieves headers (subject, from, to, cc, date, labels) and an attachment
    manifest for every ID in a single batched request, instead of calling
    ``get_email`` one message at a time. Default ``body="none"`` keeps the
    response compact for scanning; raise it to ``"text"``/``"markdown"`` when
    you need content.

    Args:
        message_ids: Email message IDs to fetch.
        body: Body mode applied to every message — ``"none"`` (default,
            headers + attachment manifest only), ``"text"``, ``"html"``, or
            ``"markdown"``. See ``get_email`` for semantics.
        max_body_chars: Per-message body truncation (see ``get_email``).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Exactly one entry per requested ID, in the same order as
        ``message_ids``. Missing or failed messages appear in place as
        ``{"message_id": ..., "error": ...}``; one failure never drops or
        shifts the others.
    """
    mode = body.lower()
    if mode not in _VALID_BODY_MODES:
        return [{"error": f"Invalid body mode {body!r}. Use none|text|html|markdown."}]

    content_type = "text/html" if mode in ("html", "markdown") else "text/plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)

    # Index whatever the provider returns by ID: providers may reorder, drop
    # missing IDs (Outlook), or return per-item error rows (Gmail).
    by_id: dict[str, dict[str, Any]] = {}
    try:
        for raw in p.batch_get_emails(list(message_ids), preferred_content_type=content_type):
            mid = raw.get("message_id")
            if mid is not None and mid not in by_id:
                by_id[mid] = dict(raw)
    except Exception:
        by_id = {}  # whole-batch failure: fall back to per-message fetches below.

    out: list[dict] = []
    for mid in message_ids:
        raw = by_id.get(mid)
        if raw is not None and "error" in raw:
            out.append({"message_id": mid, "error": raw["error"]})
            continue
        if raw is None:
            # Not in the batch response: fetch it alone to get a real answer.
            try:
                raw = dict(p.get_email_content(mid, content_type))
            except Exception as exc:
                out.append({"message_id": mid, "error": str(exc)})
                continue
        try:
            out.append(_apply_body_mode(_email_data_to_dict(raw), mode, max_body_chars))
        except Exception as exc:
            out.append({"message_id": mid, "error": str(exc)})
    return out


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


@_tool
def save_email(
    message_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str | None = None,
    include_inline: bool = False,
    include_spam_trash: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save an email message as a Markdown file.

    Set ``download_attachments=True`` to also pull every attachment on the
    message into ``output_dir`` alongside the Markdown — this is the easiest
    way to grab attachments in bulk. For a single attachment by ID without
    saving the email body, use ``download_email_attachment`` instead.

    Attachments are written to ``<output_dir>/attachments/<message_id>/``; the
    returned manifest lists each saved file so you don't have to walk the tree.

    Args:
        message_id: Email message ID.
        output_dir: Directory to save the file, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it (default: the root itself).
        prefer_html: Use HTML content if available (default: True).
        download_attachments: Also save every attachment on this email into
            ``output_dir`` (default: False — Markdown only). Gmail slots only.
        attachment_types: When ``download_attachments`` is True, restrict to
            these extensions (comma-separated, e.g. ``"pdf,docx"``).
        include_inline: Include inline parts (signature logos, cid images) when
            downloading attachments (default False — skip inline cruft).
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``markdown_path`` and an ``attachments`` manifest — a list of
        ``{filename, path, inline, mime_type, size}`` for each saved attachment.
    """
    content_type = "text/html" if prefer_html else "text/plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    email_data = _email_data_to_dict(p.get_email_content(message_id, content_type))
    md = convert_email_to_markdown(email_data)
    out = _confine_output_dir(output_dir)
    filepath = save_email_to_markdown(email_data, md, out)

    saved: list[dict] = []
    if download_attachments and email_data.get("attachments"):
        filters = (
            [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []
        )
        result = download_email_attachments(
            download_fn=p.download_attachment,
            email_data=email_data,
            output_dir=out,
            attachment_filters=filters,
            include_inline=include_inline,
        )
        saved = result.get("saved", [])

    return {"markdown_path": filepath, "attachments": saved}


@_tool
def save_thread(
    thread_id: str,
    output_dir: str = ".",
    prefer_html: bool = True,
    include_spam_trash: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> str | dict:
    """Save an entire email thread/conversation as a single Markdown file.

    Args:
        thread_id: Thread/conversation ID.
        output_dir: Directory to save the file, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it (default: the root itself).
        prefer_html: Use HTML content if available (default: True).
        include_spam_trash: Include messages from SPAM and TRASH (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Absolute path to the saved file, or ``{"error": ...}`` when the
        output location is refused.
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    messages_raw = p.get_thread(thread_id)
    messages = [_email_data_to_dict(m) for m in messages_raw]
    md = convert_thread_to_markdown(messages)
    subject = messages[0].get("subject", "thread") if messages else "thread"
    subject_slug = slugify_text(subject)
    filename = f"{subject_slug}_{thread_id}.md"
    out = _confine_output_dir(output_dir)
    filepath = str(_confine_path(os.path.join(out, filename), purpose="output file"))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)
    return filepath


def _refresh_sync_state(p: Any, sync_state: Any, ids: list[str], fallback: str = "") -> None:
    """Record the provider's current sync token (e.g. Gmail historyId).

    Asks the *selected* provider rather than the legacy module-level Gmail
    service, so the token belongs to the account that was searched and no
    separate (possibly interactive) auth path is triggered.
    """
    try:
        token = p.get_sync_state()
    except Exception:
        return  # sync only meaningful where the provider supports it.
    sync_state.update(str(token or fallback), ids)


@_tool
def save_emails_by_query(
    query: str,
    output_dir: str = ".",
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    prefer_html: bool = True,
    download_attachments: bool = False,
    attachment_types: str | None = None,
    include_inline: bool = False,
    include_spam_trash: bool = False,
    sync: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save multiple email messages matching a query as Markdown files.

    Set ``download_attachments=True`` to also pull every attachment from each
    matched email into ``output_dir`` — this is the bulk-grab path. For a
    single attachment by ID, use ``download_email_attachment`` instead.

    Args:
        query: Email search syntax.
        output_dir: Directory to save files, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it (default: the root itself).
        max_results: Maximum emails to save (default 10).
        days: Days back to search (default 7).
        start_date: Start date YYYY/MM/DD (overrides days).
        end_date: End date YYYY/MM/DD.
        prefer_html: Use HTML content if available (default True).
        download_attachments: Also save every attachment from each matched
            email into ``output_dir`` (default: False — Markdown only).
            Gmail slots only.
        attachment_types: When ``download_attachments`` is True, restrict to
            these extensions (comma-separated, e.g. ``"pdf,docx"``).
        include_spam_trash: Include SPAM and TRASH (default False).
        sync: Enable incremental sync — Gmail only (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict with saved_count, skipped_count, attachment_count, and
        ``failed`` (``{message_id, error}`` for messages that could not be saved).
    """
    from datetime import date, timedelta

    from iobox.providers.base import EmailQuery

    content_type = "text/html" if prefer_html else "text/plain"
    out = _confine_output_dir(output_dir)
    att_filters = (
        [ext.strip().lower() for ext in attachment_types.split(",")] if attachment_types else []
    )
    p = _resolve_email_provider(provider=provider, workspace=workspace)

    # Incremental sync
    sync_state = SyncState(out)
    message_ids_to_fetch: list[str] | None = None

    if sync:
        state_exists = sync_state.load()
        if state_exists and sync_state.last_history_id:
            new_ids = p.get_new_messages(sync_state.last_history_id)
            if new_ids is not None:
                message_ids_to_fetch = new_ids

    if message_ids_to_fetch is not None:
        if not message_ids_to_fetch:
            _refresh_sync_state(p, sync_state, [], fallback=sync_state.last_history_id or "")
            return {
                "saved_count": 0,
                "skipped_count": 0,
                "attachment_count": 0,
                "detail": "No new emails since last sync.",
            }
    else:
        # Build EmailQuery
        after: date | None = None
        before: date | None = None
        if start_date:
            parts = start_date.replace("-", "/").split("/")
            after = date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif days:
            after = date.today() - timedelta(days=days)
        if end_date:
            parts = end_date.replace("-", "/").split("/")
            before = date(int(parts[0]), int(parts[1]), int(parts[2]))

        search_results = p.search_emails(
            EmailQuery(
                text=query,
                max_results=max_results,
                after=after,
                before=before,
                include_spam_trash=include_spam_trash,
            )
        )
        if not search_results:
            if sync:
                _refresh_sync_state(p, sync_state, [])
            return {
                "saved_count": 0,
                "skipped_count": 0,
                "attachment_count": 0,
                "detail": "No emails found.",
            }
        message_ids_to_fetch = [r["message_id"] for r in search_results]

    all_ids = list(message_ids_to_fetch)
    duplicates = check_for_duplicates(all_ids, out)
    ids_to_process = [mid for mid in all_ids if mid not in duplicates]

    saved_count = 0
    attachment_count = 0
    failed: list[dict[str, str]] = []

    if ids_to_process:
        email_batch = p.batch_get_emails(ids_to_process, preferred_content_type=content_type)
        for email_raw in email_batch:
            if "error" in email_raw:
                failed.append(
                    {"message_id": email_raw.get("message_id", ""), "error": email_raw["error"]}
                )
                continue
            email_data = _email_data_to_dict(email_raw)
            try:
                md = convert_email_to_markdown(email_data)
                save_email_to_markdown(email_data, md, out)
                saved_count += 1
                if download_attachments and email_data.get("attachments"):
                    res = download_email_attachments(
                        download_fn=p.download_attachment,
                        email_data=email_data,
                        output_dir=out,
                        attachment_filters=att_filters,
                        include_inline=include_inline,
                    )
                    attachment_count += res["downloaded_count"]
            except Exception as exc:
                failed.append({"message_id": email_data.get("message_id", ""), "error": str(exc)})

    if sync:
        _refresh_sync_state(p, sync_state, ids_to_process)

    return {
        "saved_count": saved_count,
        "skipped_count": len(duplicates),
        "attachment_count": attachment_count,
        "failed": failed,
    }


@_tool
def download_email_attachment(
    message_id: str,
    attachment_id: str,
    output_path: str | None = None,
    return_base64: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Download a single email attachment by ID.

    Use this when you want one specific attachment without saving the whole
    email. To grab every attachment on a message alongside its Markdown body,
    use ``save_email(download_attachments=True)`` instead.

    Get ``attachment_id`` values from the ``attachments`` list returned by
    ``get_email`` — each entry has ``id``, ``filename``, ``mime_type``, ``size``.

    By default writes the bytes to disk and returns the filepath. Set
    ``return_base64=True`` to receive the bytes inline as a base64 string
    (useful when the caller has no filesystem to write to).

    Args:
        message_id: Email message ID containing the attachment.
        attachment_id: Attachment ID from the email's ``attachments`` list.
        output_path: File path to write, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it. Required when ``return_base64`` is False. Parent
            directories are created. An existing file is never overwritten —
            the call returns an error instead.
        return_base64: If True, skip the disk write and return the bytes
            inline as a base64-encoded ASCII string in the ``data`` field
            (default False).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        On disk write: ``{"filepath": str, "bytes_written": int}``.
        On base64: ``{"data": str, "bytes_written": int, "encoding": "base64"}``.
        On failure: ``{"error": str}``.
    """
    path: Path | None = None
    if not return_base64:
        if not output_path:
            return {"error": "output_path is required when return_base64=False."}
        path = _confine_path(output_path, purpose="output_path")
        if path.exists() or path.is_symlink():
            return {"error": f"Refusing to overwrite existing file {str(path)!r}."}
    try:
        p = _resolve_email_provider(provider=provider, workspace=workspace)
        data = p.download_attachment(message_id, attachment_id)
    except Exception as exc:
        return {"error": str(exc)}

    if path is None:
        import base64

        return {
            "data": base64.b64encode(data).decode("ascii"),
            "bytes_written": len(data),
            "encoding": "base64",
        }

    _write_new_file(path, data)
    return {"filepath": str(path), "bytes_written": len(data)}


# ---------------------------------------------------------------------------
# Send & Forward
# ---------------------------------------------------------------------------


@_tool
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html: bool = False,
    attachments: list[str] | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Send an email via the active provider slot.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text (plain text or HTML).
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        html: Send body as HTML content (default False).
        attachments: List of file paths to attach. Each must be an existing
            file inside the MCP root (``IOBOX_MCP_ROOT``, default
            ``~/iobox``); relative paths resolve under it.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    attachments = _confine_attachments(attachments)

    content_type = "html" if html else "plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.send_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        content_type=content_type,
        attachments=attachments,
    )


@_tool
def forward_gmail(
    message_id: str,
    to: str,
    note: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Forward an email to a recipient.

    Args:
        message_id: Source message ID to forward.
        to: Recipient email address.
        note: Optional text to prepend.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.forward_message(message_id=message_id, to=to, comment=note)


@_tool
def batch_forward_gmail(
    query: str,
    to: str,
    max_results: int = 10,
    days: int = 7,
    start_date: str | None = None,
    end_date: str | None = None,
    note: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Forward multiple emails matching a query to a recipient.

    Args:
        query: Email search syntax to find messages.
        to: Recipient email address.
        max_results: Maximum messages to forward (default 10, capped at 100).
        days: Days back to search (default 7; must be >= 1 unless
            ``start_date`` is given).
        start_date: Start date YYYY/MM/DD (overrides days).
        end_date: End date YYYY/MM/DD.
        note: Optional text to prepend to each forwarded email.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict: ``forwarded_count`` (successes), ``matched_count``,
        ``succeeded`` (message IDs) and ``failed`` (``{message_id, error}``).
        One failure doesn't stop the rest.
    """
    eq, limit_note = _batch_query(query, max_results, days, start_date, end_date)
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    results = p.search_emails(eq)[: eq.max_results]
    if not results:
        return _batch_result("forwarded_count", 0, [], [], "No emails found matching the query.")

    succeeded, failed = _run_batch(
        [r["message_id"] for r in results],
        lambda mid: p.forward_message(message_id=mid, to=to, comment=note),
    )
    return _batch_result("forwarded_count", len(results), succeeded, failed, limit_note)


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


@_tool
def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html: bool = False,
    attachments: list[str] | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create an email draft.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text (plain text or HTML).
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        html: Use HTML content type (default False).
        attachments: List of file paths to attach. Each must be an existing
            file inside the MCP root (``IOBOX_MCP_ROOT``, default
            ``~/iobox``); relative paths resolve under it.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    attachments = _confine_attachments(attachments)

    content_type = "html" if html else "plain"
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.create_draft(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        content_type=content_type,
        attachments=attachments,
    )


@_tool
def list_gmail_drafts(
    max_results: int = 10,
    provider: str | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """List email drafts.

    Args:
        max_results: Maximum number of drafts to return (default 10).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return list(p.list_drafts(max_results=max_results))


@_tool
def send_gmail_draft(
    draft_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Send an existing email draft.

    Args:
        draft_id: The draft ID to send.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.send_draft(draft_id)


@_tool
def delete_gmail_draft(
    draft_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Permanently delete an email draft.

    Args:
        draft_id: The draft ID to delete.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    return p.delete_draft(draft_id)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def _apply_label_actions(
    p: Any,
    message_id: str,
    *,
    mark_read: bool,
    mark_unread: bool,
    star: bool,
    unstar: bool,
    archive: bool,
    add_label: str | None,
    remove_label: str | None,
) -> None:
    """Apply label actions via the EmailProvider ABC (works for Gmail + Outlook)."""
    if mark_read:
        p.mark_read(message_id, True)
    if mark_unread:
        p.mark_read(message_id, False)
    if star:
        p.set_star(message_id, True)
    if unstar:
        p.set_star(message_id, False)
    if archive:
        p.archive(message_id)
    if add_label:
        p.add_tag(message_id, add_label)
    if remove_label:
        p.remove_tag(message_id, remove_label)


@_tool
def list_labels(
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """List the labels/categories available on an email account.

    Resolves the opaque label IDs that appear on messages to human-readable
    names — use it to discover which labels exist before applying them with
    ``modify_labels``.

    Args:
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``labels``: a mapping of label ID → display name (for Outlook,
        category name → category name).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    try:
        return {"labels": p.list_tags()}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def create_label(
    name: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create a label/category, including nested taxonomies.

    Gmail supports nesting via ``/``-delimited names (e.g.
    ``"LifeAdmin/property/7-leslie-st"``) — the hierarchy renders automatically.
    Outlook categories are free-form; the name is registered as a master
    category. Existing labels are returned rather than erroring.

    Note: ``modify_labels(add_label=...)`` already auto-creates a missing label
    when applying it, so call this only when you want to create a label without
    tagging a message.

    Args:
        name: Label name (``/``-delimited for nesting on Gmail).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``name`` of the created (or existing) label.
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    try:
        return p.create_tag(name)
    except NotImplementedError:
        return {"error": "This provider does not support label creation."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def modify_labels(
    message_id: str,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str | None = None,
    remove_label: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Add or remove labels/tags on an email message.

    Args:
        message_id: Email message ID.
        mark_read: Mark as read.
        mark_unread: Mark as unread.
        star: Star the message.
        unstar: Unstar the message.
        archive: Archive (remove from INBOX).
        add_label: Label/tag name to add.
        remove_label: Label/tag name to remove.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Status dict with the message ID and ``status: "modified"``.
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    _apply_label_actions(
        p,
        message_id,
        mark_read=mark_read,
        mark_unread=mark_unread,
        star=star,
        unstar=unstar,
        archive=archive,
        add_label=add_label,
        remove_label=remove_label,
    )
    return {"message_id": message_id, "status": "modified"}


@_tool
def batch_modify_gmail_labels(
    query: str,
    max_results: int = 10,
    days: int = 7,
    mark_read: bool = False,
    mark_unread: bool = False,
    star: bool = False,
    unstar: bool = False,
    archive: bool = False,
    add_label: str | None = None,
    remove_label: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Modify labels/tags on multiple email messages matching a query.

    Args:
        query: Email search syntax to find messages.
        max_results: Maximum messages to modify (default 10, capped at 100).
        days: Days back to search (default 7; must be >= 1).
        mark_read: Mark as read.
        mark_unread: Mark as unread.
        star: Star messages.
        unstar: Unstar messages.
        archive: Archive (remove from INBOX).
        add_label: Label/tag name to add.
        remove_label: Label/tag name to remove.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict: ``modified_count`` (successes), ``matched_count``,
        ``succeeded`` (message IDs) and ``failed`` (``{message_id, error}``).
        One failure doesn't stop the rest.
    """
    eq, limit_note = _batch_query(query, max_results, days)
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    results = p.search_emails(eq)[: eq.max_results]
    if not results:
        return _batch_result("modified_count", 0, [], [], "No emails found matching the query.")

    succeeded, failed = _run_batch(
        [r["message_id"] for r in results],
        lambda mid: _apply_label_actions(
            p,
            mid,
            mark_read=mark_read,
            mark_unread=mark_unread,
            star=star,
            unstar=unstar,
            archive=archive,
            add_label=add_label,
            remove_label=remove_label,
        ),
    )
    return _batch_result("modified_count", len(results), succeeded, failed, limit_note)


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


@_tool
def trash_gmail(
    message_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Move an email message to trash.

    Args:
        message_id: Email message ID to trash.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    p.trash(message_id)
    return {"message_id": message_id, "status": "trashed"}


@_tool
def untrash_gmail(
    message_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Restore an email message from trash.

    Args:
        message_id: Email message ID to restore.
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).
    """
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    p.untrash(message_id)
    return {"message_id": message_id, "status": "untrashed"}


@_tool
def batch_trash_gmail(
    query: str,
    max_results: int = 10,
    days: int = 7,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Move multiple email messages matching a query to trash.

    Args:
        query: Email search syntax to find messages.
        max_results: Maximum messages to trash (default 10, capped at 100).
        days: Days back to search (default 7; must be >= 1).
        provider: Optional email slot name.
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Summary dict: ``trashed_count`` (successes), ``matched_count``,
        ``succeeded`` (message IDs) and ``failed`` (``{message_id, error}``).
        One failure doesn't stop the rest.
    """
    eq, limit_note = _batch_query(query, max_results, days)
    p = _resolve_email_provider(provider=provider, workspace=workspace)
    results = p.search_emails(eq)[: eq.max_results]
    if not results:
        return _batch_result("trashed_count", 0, [], [], "No emails found matching the query.")

    succeeded, failed = _run_batch([r["message_id"] for r in results], p.trash)
    return _batch_result("trashed_count", len(results), succeeded, failed, limit_note)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


_WRITE_OP_TOOLS = ("create_gmail_draft", "modify_labels", "create_event", "upload_file")
_SEND_OP_TOOLS = ("send_email", "send_gmail_draft", "forward_gmail", "trash_gmail")


def _mode_capabilities() -> dict[str, Any]:
    """Describe the active mode, derived from the same allowlist that registers tools."""
    mode = get_mode_from_env()
    allowed = MCP_TOOLS_BY_MODE[mode]
    caps: dict[str, Any] = {
        "mode": mode.value,
        "available_write_ops": all(t in allowed for t in _WRITE_OP_TOOLS),
        "available_send_ops": all(t in allowed for t in _SEND_OP_TOOLS),
    }
    if not caps["available_send_ops"]:
        caps["mode_hint"] = (
            f"Running in {mode.value} mode. "
            + (
                "Set IOBOX_MODE=standard for labels/drafts/calendar/file writes, or "
                if not caps["available_write_ops"]
                else ""
            )
            + "set IOBOX_MODE=dangerous to send mail (including sending drafts), "
            "forward, or trash."
        )
    return caps


@_tool
def check_auth(workspace: str | None = None) -> dict:
    """Check cached authentication state and the active access mode.

    Reports from cached tokens on disk only — it never contacts Google or
    Microsoft and never starts an interactive sign-in. When a workspace is
    named or active, reports each of its service sessions; otherwise reports
    the legacy single-account Gmail token. For a live per-slot check, call
    ``workspace_auth_status``. To (re-)authenticate, run
    ``iobox space login`` in a terminal.

    The ``mode`` / ``available_write_ops`` fields let a constrained agent
    self-diagnose: if write tools seem to be missing, it's almost always because
    of the server's ``IOBOX_MODE`` rather than a missing feature.

    Args:
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Status dict including ``authenticated``, ``mode``
        (readonly|standard|dangerous), ``available_write_ops``
        (labels/drafts/calendar/file writes), ``available_send_ops`` (send
        email or drafts, forward, trash), and a ``mode_hint`` when sending is
        unavailable. With a workspace, also ``workspace`` and ``services`` —
        one ``{service, account, mode, scopes, authenticated}`` entry per
        configured session.
    """
    from iobox.space_config import get_active_space, is_authenticated, load_space

    caps = _mode_capabilities()
    try:
        target = workspace or get_active_space()
    except Exception as exc:
        return {"authenticated": False, "error": f"Could not read active workspace: {exc}", **caps}

    if target:
        try:
            config = load_space(target)
        except Exception as exc:
            return {
                "authenticated": False,
                "workspace": target,
                "error": f"Could not load workspace '{target}': {exc}",
                **caps,
            }
        services = [
            {
                "service": entry.service,
                "account": entry.account,
                "mode": entry.mode,
                "scopes": list(entry.scopes),
                "authenticated": is_authenticated(entry),
            }
            for entry in config.services
        ]
        return {
            "workspace": target,
            "authenticated": bool(services) and all(s["authenticated"] for s in services),
            "services": services,
            **caps,
        }

    # No workspace: legacy single-account Gmail, from the cached token only.
    status = check_auth_status()
    status.update(caps)
    return status


# ---------------------------------------------------------------------------
# Workspace: cross-type search
# ---------------------------------------------------------------------------


@_tool
def search_workspace(
    query: str,
    types: list[str] | None = None,
    max_results: int = 10,
    workspace: str | None = None,
) -> list[dict]:
    """Cross-type search across email, calendar events, and files.

    Fans out across every configured slot in parallel — covers multiple
    Gmail accounts, multiple Outlook accounts, or any mix.

    Args:
        query: Search text.
        types: List of ``"email"``, ``"event"``, ``"file"`` (default: all).
        max_results: Max results per resource type (default 10).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        List of Resource dicts with a ``resource_type`` field for dispatch.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return [{"error": "No active workspace configured. Run `iobox space create` first."}]
    try:
        results = ws.search(query, types=types, max_results_per_type=max_results)
        return [dict(r) for r in results]
    except Exception as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Workspace: calendar events
# ---------------------------------------------------------------------------


@_tool
def list_events(
    after: str | None = None,
    before: str | None = None,
    text: str | None = None,
    provider: str | None = None,
    max_results: int = 25,
    workspace: str | None = None,
) -> list[dict]:
    """List calendar events from the active workspace.

    Fans out across every calendar slot when ``provider`` is omitted —
    covers multiple Google Calendar accounts in a single call.

    Args:
        after: Start date filter (YYYY-MM-DD).
        before: End date filter (YYYY-MM-DD).
        text: Text search filter.
        provider: Calendar slot name (default: all calendar slots).
        max_results: Maximum results (default 25).
        workspace: Optional workspace name (default: active workspace).
    """
    from iobox.providers.base import EventQuery

    ws = _get_workspace(workspace)
    if not ws:
        return [{"error": "No active workspace configured."}]
    try:
        query = EventQuery(text=text, after=after, before=before, max_results=max_results)
        providers = [provider] if provider else None
        events = ws.list_events(query, providers=providers)
        return [dict(e) for e in events]
    except Exception as exc:
        return [{"error": str(exc)}]


@_tool
def get_event(
    event_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get a single calendar event by ID.

    Args:
        event_id: Event ID.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.get_event(event_id))
    except KeyError:
        return {"error": f"Event '{event_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def save_event(
    event_id: str,
    output_dir: str = ".",
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save a calendar event as a Markdown file.

    Args:
        event_id: Event ID.
        output_dir: Directory to save the file, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it (default: the root itself).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``title`` keys, or ``error``.
    """
    from iobox.processing.markdown import convert_event_to_markdown

    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        event = slot.provider.get_event(event_id)
        md = convert_event_to_markdown(event)
        out = _confine_output_dir(output_dir)
        title_slug = slugify_text(event.get("title", "event"))
        filename = f"{title_slug}_{event_id}.md"
        filepath = str(_confine_path(os.path.join(out, filename), purpose="output file"))
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return {"filepath": filepath, "title": event.get("title", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def create_event(
    title: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    all_day: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create a calendar event.

    Args:
        title: Event title.
        start: ISO 8601 start (e.g. ``"2026-04-01T09:00:00"``) or ``YYYY-MM-DD``
            for all-day events.
        end: ISO 8601 end or ``YYYY-MM-DD``.
        description: Optional event description.
        location: Optional location.
        attendees: Optional list of attendee email addresses.
        all_day: Treat start/end as date-only (default False).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``title``, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        event = slot.provider.create_event(
            title=title,
            start=start,
            end=end,
            all_day=all_day,
            description=description,
            location=location,
            attendees=attendees or [],
        )
        return {"id": event.get("id", ""), "title": event.get("title", title)}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def update_event(
    event_id: str,
    updates: dict,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Update fields on an existing calendar event.

    Args:
        event_id: Event ID to update.
        updates: Dict of fields to change (e.g. ``{"title": "...", "start": "..."}``).
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Updated event dict, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.update_event(event_id, updates))
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def delete_event(
    event_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Delete a calendar event.

    Args:
        event_id: Event ID to delete.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        slot.provider.delete_event(event_id)
        return {"event_id": event_id, "status": "deleted"}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def rsvp_event(
    event_id: str,
    response: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """RSVP to a calendar event invitation.

    Args:
        event_id: Event ID.
        response: ``"accepted"``, ``"declined"``, or ``"tentative"``.
        provider: Calendar slot name (default: first calendar slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Updated event dict with the new response, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_calendar_slot(ws, provider)
    if slot is None:
        if not ws.calendar_providers:
            return {"error": "No calendar providers in workspace."}
        return {"error": f"Calendar provider '{provider}' not found."}
    try:
        return dict(slot.provider.rsvp(event_id, response))
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Workspace: files
# ---------------------------------------------------------------------------


@_tool
def list_files(
    query: str,
    provider: str | None = None,
    max_results: int = 20,
    workspace: str | None = None,
) -> list[dict]:
    """List files from the active workspace.

    Fans out across every file slot when ``provider`` is omitted — covers
    multiple Drive/OneDrive accounts in a single call.

    Args:
        query: Search text (required — avoids listing all files).
        provider: File slot name (default: all file slots).
        max_results: Maximum results (default 20).
        workspace: Optional workspace name (default: active workspace).
    """
    from iobox.providers.base import FileQuery

    ws = _get_workspace(workspace)
    if not ws:
        return [{"error": "No active workspace configured."}]
    try:
        fq = FileQuery(text=query, max_results=max_results)
        providers = [provider] if provider else None
        files = ws.list_files(fq, providers=providers)
        return [dict(f) for f in files]
    except Exception as exc:
        return [{"error": str(exc)}]


@_tool
def get_file(
    file_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get file metadata by ID.

    Args:
        file_id: File ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        return dict(slot.provider.get_file(file_id))
    except KeyError:
        return {"error": f"File '{file_id}' not found."}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def get_file_content(
    file_id: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Get text content of a file.

    Args:
        file_id: File ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``content`` key (str) or ``error`` key on failure.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        content = slot.provider.get_file_content(file_id)
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def save_file(
    file_id: str,
    output_dir: str = ".",
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Save a file's metadata + extracted text content as a Markdown file.

    Args:
        file_id: File ID.
        output_dir: Directory to save the file, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it (default: the root itself).
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``name``, or ``error``.
    """
    from iobox.processing.markdown import convert_file_to_markdown

    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        file_meta = slot.provider.get_file(file_id)
        md = convert_file_to_markdown(file_meta)
        out = _confine_output_dir(output_dir)
        name_slug = slugify_text(file_meta.get("title") or file_meta.get("name", "file"))
        filename = f"{name_slug}_{file_id}.md"
        filepath = str(_confine_path(os.path.join(out, filename), purpose="output file"))
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        return {"filepath": filepath, "name": file_meta.get("title", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def download_file(
    file_id: str,
    output_path: str,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Download a file's binary content to disk.

    Args:
        file_id: File ID.
        output_path: File path to write the bytes to, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it. An existing file is never overwritten — the call
            returns an error instead.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``filepath`` and ``bytes_written``, or ``error``.
    """
    path = _confine_path(output_path, purpose="output_path")
    if path.exists() or path.is_symlink():
        return {"error": f"Refusing to overwrite existing file {str(path)!r}."}
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        data = slot.provider.download_file(file_id)
        _write_new_file(path, data)
        return {"filepath": str(path), "bytes_written": len(data)}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def upload_file(
    local_path: str,
    name: str | None = None,
    parent_id: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Upload a local file to the file provider.

    Args:
        local_path: Path to the file on disk, inside the MCP root
            (``IOBOX_MCP_ROOT``, default ``~/iobox``); relative paths resolve
            under it.
        name: Optional remote filename (defaults to ``Path(local_path).name``).
        parent_id: Optional parent folder ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``name``, or ``error``.
    """
    resolved = _confine_existing_file(local_path, purpose="local_path")
    name = name or Path(local_path).name
    local_path = str(resolved)
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        f = slot.provider.upload_file(local_path, parent_id=parent_id, name=name)
        return {"id": f.get("id", ""), "name": f.get("title") or f.get("name", "")}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def delete_file(
    file_id: str,
    permanent: bool = False,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Delete a file (move to trash by default).

    Args:
        file_id: File ID.
        permanent: If True, permanently delete (skip trash).
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        slot.provider.delete_file(file_id, permanent=permanent)
        return {
            "file_id": file_id,
            "status": "deleted_permanently" if permanent else "trashed",
        }
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def create_folder(
    name: str,
    parent_id: str | None = None,
    provider: str | None = None,
    workspace: str | None = None,
) -> dict:
    """Create a folder/directory in the file provider.

    Args:
        name: Folder name.
        parent_id: Optional parent folder ID.
        provider: File slot name (default: first file slot).
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``id`` and ``name``, or ``error``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}
    slot = _find_file_slot(ws, provider)
    if slot is None:
        if not ws.file_providers:
            return {"error": "No file providers in workspace."}
        return {"error": f"File provider '{provider}' not found."}
    try:
        f = slot.provider.create_folder(name, parent_id=parent_id)
        return {"id": f.get("id", ""), "name": f.get("title") or f.get("name", name)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Workspace: discovery + auth
# ---------------------------------------------------------------------------


@_tool
def list_workspaces() -> dict:
    """List all configured workspaces and the active one.

    Returns:
        Dict with ``workspaces`` (list of names) and ``active`` (name or None).
    """
    try:
        from iobox.space_config import get_active_space, list_spaces

        return {"workspaces": list_spaces(), "active": get_active_space()}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def get_active_workspace() -> dict:
    """Return the name of the currently active workspace, or None."""
    try:
        from iobox.space_config import get_active_space

        return {"active": get_active_space()}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def set_active_workspace(name: str) -> dict:
    """Switch the active workspace to ``name``.

    Args:
        name: Workspace name (must exist on disk).

    Returns:
        Dict with ``active`` set to the new name, or ``error``.
    """
    try:
        from iobox.space_config import list_spaces, set_active_space

        if name not in list_spaces():
            available = ", ".join(list_spaces()) or "(none)"
            return {"error": f"Workspace '{name}' not found. Available: {available}"}
        set_active_space(name)
        return {"active": name}
    except Exception as exc:
        return {"error": str(exc)}


@_tool
def list_provider_slots(workspace: str | None = None) -> dict:
    """Enumerate every provider slot in a workspace.

    Useful for discovering which ``provider`` names are available to pass
    to other tools when working with multiple accounts.

    Args:
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict with ``email``, ``calendar``, ``file`` lists. Each entry has
        ``name``, ``tags``, and ``provider_class``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}

    def _describe(slot: Any) -> dict:
        return {
            "name": slot.name,
            "tags": list(slot.tags),
            "provider_class": type(slot.provider).__name__,
        }

    return {
        "workspace": ws.name,
        "email": [_describe(s) for s in ws.email_providers],
        "calendar": [_describe(s) for s in ws.calendar_providers],
        "file": [_describe(s) for s in ws.file_providers],
    }


def _cached_auth_by_slot(ws_name: str) -> dict[str, bool] | None:
    """Map each slot name in *ws_name* to whether a cached token exists.

    Slot names mirror ``Workspace.from_config``: ``slug`` (email),
    ``slug-cal``, ``slug-drive``. Returns None if the config can't be read.
    """
    try:
        from iobox.space_config import is_authenticated, load_space

        config = load_space(ws_name)
    except Exception:
        return None
    out: dict[str, bool] = {}
    for entry in config.services:
        authed = is_authenticated(entry)
        for name in (entry.slug, f"{entry.slug}-cal", f"{entry.slug}-drive"):
            out[name] = authed
    return out


@_tool
def workspace_auth_status(workspace: str | None = None) -> dict:
    """Report per-slot authentication status across the workspace.

    Calls ``get_profile`` on each slot that has a cached token, to surface
    whether the token still works and which account it belongs to. Slots
    with no cached token are reported as unauthenticated without contacting
    the provider (so the server never opens an interactive sign-in).

    Args:
        workspace: Optional workspace name (default: active workspace).

    Returns:
        Dict mapping slot name to ``{authenticated, account, error}``.
    """
    ws = _get_workspace(workspace)
    if not ws:
        return {"error": "No active workspace configured."}

    cached = _cached_auth_by_slot(ws.name)

    def _check(slot: Any) -> dict:
        if cached is not None and cached.get(slot.name) is False:
            # No cached token: calling the provider would start an interactive
            # sign-in inside the server process. Report instead.
            return {
                "authenticated": False,
                "account": None,
                "error": "No cached token; run `iobox space login` in a terminal.",
            }
        try:
            profile = slot.provider.get_profile()
            return {
                "authenticated": True,
                "account": profile.get("emailAddress") or profile.get("email") or "",
                "error": None,
            }
        except Exception as exc:
            return {"authenticated": False, "account": None, "error": str(exc)}

    out: dict[str, Any] = {"workspace": ws.name, "slots": {}}
    for slot in ws.email_providers + ws.calendar_providers + ws.file_providers:
        out["slots"][slot.name] = _check(slot)
    return out


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


@_tool
def semantic_search_workspace(
    query: str,
    types: list[str] | None = None,
    top_k: int = 10,
    backend: str = "openai",
    workspace: str | None = None,
) -> list[dict]:
    """Semantic (vector) search across indexed workspace resources.

    Requires the ``semantic`` optional dependency group:
    ``pip install 'iobox[semantic]'``.

    Resources must be indexed first via ``embed_resources()`` before this
    tool returns meaningful results.  Falls back gracefully if no index
    exists yet.

    Args:
        query: Natural-language search query.
        types: Resource types to search — any of ``"email"``, ``"event"``,
            ``"file"`` (default: all types).
        top_k: Maximum number of results (default 10).
        backend: Embedding backend — ``"openai"`` (default), ``"voyage"``,
            or ``"local"``.
        workspace: Workspace name (default: active workspace).

    Returns:
        List of dicts with ``id``, ``resource_type``, ``provider_id``, and
        ``score`` fields, ranked by similarity (highest first).
    """
    try:
        from iobox.processing.embed import get_backend as _get_backend
        from iobox.processing.embed import semantic_search as _semantic_search
    except ImportError:
        return [
            {
                "error": (
                    "Semantic search requires 'iobox[semantic]'. Run: pip install 'iobox[semantic]'"
                )
            }
        ]

    # Resolve workspace name
    ws_name = workspace
    if not ws_name:
        try:
            from iobox.space_config import get_active_space

            ws_name = get_active_space()
        except Exception:
            pass
    if not ws_name:
        return [{"error": "No active workspace. Set one with `iobox space use NAME`."}]

    try:
        emb_backend = _get_backend(backend)
        results = _semantic_search(query, ws_name, types=types, top_k=top_k, backend=emb_backend)
        return results
    except Exception as exc:
        return [{"error": str(exc)}]


def main() -> None:
    from iobox.accounts import get_account_from_env, set_active_account

    mode = get_mode_from_env()
    set_active_mode(mode)
    set_active_account(get_account_from_env())
    register_tools(mode)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
