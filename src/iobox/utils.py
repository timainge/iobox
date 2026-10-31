"""
Utility functions shared across iobox modules.

Contains filename generation and text sanitization helpers.
"""

import hashlib
import re
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any


def slugify_text(text: str | None, max_length: int = 50) -> str:
    """
    Convert text to a URL/filename-safe slug.

    Args:
        text: Text to slugify (``None`` is treated as empty)
        max_length: Maximum length for the slug

    Returns:
        str: Slugified text (may be empty for symbol-only input)
    """
    text = str(text or "").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return text[:max_length].strip("-")


def _safe_id(value: str, max_length: int = 80) -> str:
    """Make a provider message ID safe for use in a filename.

    Keeps case (Outlook/Graph IDs are case-sensitive base64) and replaces
    anything outside ``[A-Za-z0-9_-]`` (e.g. ``/``, ``+``, ``=``) with ``_``.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:max_length]


_ISO_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")


def parse_email_date(date_str: str | None) -> datetime | None:
    """Parse an email date header or ISO 8601 timestamp.

    Tries RFC 2822 (``Mon, 1 Mar 2025 10:00:00 +0000``, with or without a
    weekday) via :func:`email.utils.parsedate_to_datetime`, then ISO 8601
    (``2025-03-01T10:00:00Z`` as used by Outlook/Graph). Returns ``None`` when
    the value cannot be parsed.
    """
    if not date_str:
        return None
    date_str = str(date_str).strip()
    try:
        return parsedate_to_datetime(date_str)
    except (TypeError, ValueError, IndexError):
        pass
    iso = date_str[:-1] + "+00:00" if date_str.endswith(("Z", "z")) else date_str
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    # Python 3.10's fromisoformat rejects e.g. 7-digit fractional seconds
    # ("2025-03-01T10:00:00.0000000Z") — fall back to the calendar date.
    match = _ISO_DATE_RE.match(date_str)
    if match:
        try:
            return datetime(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            return None
    return None


def create_markdown_filename(email_data: dict[str, Any], use_subject: bool = True) -> str:
    """
    Create a filename for the markdown file based on email data.

    The subject-based form is ``YYYY-MM-DD-<subject-slug>.md``. When the
    subject is missing, empty, or slugifies to nothing (e.g. ``"!!!"``), the
    sanitised message ID is used in its place. When the date cannot be parsed
    the date prefix falls back to today.

    Args:
        email_data: Dictionary containing email metadata
        use_subject: If True, use the subject line in the filename

    Returns:
        str: Filename for the markdown file
    """
    message_id = str(email_data.get("message_id") or email_data.get("id") or "")
    subject = email_data.get("subject")

    if not message_id and subject:
        id_base = str(subject) + str(email_data.get("date") or datetime.now())
        message_id = hashlib.md5(id_base.encode()).hexdigest()[:12]

    if not message_id:
        raise ValueError("Email data missing message_id or id and no subject to create one from")

    safe_id = _safe_id(message_id) or hashlib.md5(message_id.encode()).hexdigest()[:12]

    if not use_subject:
        return f"{safe_id}.md"

    date_obj = parse_email_date(email_data.get("date"))
    date_prefix = (date_obj or datetime.now()).strftime("%Y-%m-%d")

    slug = slugify_text(subject) or safe_id
    return f"{date_prefix}-{slug}.md"


def _parse_ymd(value: str) -> date:
    """Parse ``YYYY/MM/DD`` or ``YYYY-MM-DD``."""
    parts = value.replace("-", "/").split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid date {value!r}; expected YYYY/MM/DD or YYYY-MM-DD.")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def parse_date_range(
    days: int | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[date | None, date | None]:
    """Convert user date options into ``(after, before)`` dates for an ``EmailQuery``.

    * ``start_date`` takes precedence over ``days``; ``days`` is relative to today.
    * ``end_date`` is **inclusive** for the user; providers treat ``before`` as
      exclusive, so the returned ``before`` is the day *after* ``end_date``.
    * Returns ``(None, None)`` when no date constraints are given.
    """
    after: date | None = None
    before: date | None = None
    if start_date:
        after = _parse_ymd(start_date)
    elif days is not None:
        after = date.today() - timedelta(days=days)
    if end_date:
        before = _parse_ymd(end_date) + timedelta(days=1)
    return after, before


def _short_id(resource_id: str) -> str:
    """Return a short, filename-safe token that identifies *resource_id*.

    Short ids made of safe characters are used as-is; anything else (long or
    punctuation-heavy ids such as Outlook ImmutableIds, which share long
    prefixes) is reduced to a stable 10-character hash.
    """
    if re.fullmatch(r"[A-Za-z0-9_-]{1,16}", resource_id):
        return resource_id
    return hashlib.sha1(resource_id.encode("utf-8")).hexdigest()[:10]


def resource_filename(title: str | None, resource_id: str, kind: str) -> str:
    """Build a Markdown filename ``{slug}_{short-id}.md`` for an event or file.

    The id suffix keeps resources with the same title from overwriting each
    other; an empty or unsluggable title falls back to ``{kind}_{short-id}.md``.
    """
    slug = slugify_text(title or "").strip("-_")
    return f"{slug or kind}_{_short_id(resource_id)}.md"
