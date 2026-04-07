"""
Resource summarization using Claude (Anthropic API).

Requires: pip install 'iobox[ai]'

Usage::

    from iobox.processing.summarize import summarize, summarize_batch

    summary = summarize(event_resource)
    summaries = summarize_batch([email1, email2, file1])
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from iobox.providers.base import Resource

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 300


def summarize(
    resource: Resource,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_key: str | None = None,
    _client_fn: Callable[[], Any] | None = None,
) -> str:
    """Summarize a Resource using Claude.

    Args:
        resource: Any Resource TypedDict (email, event, or file).
        model: Claude model ID.  Defaults to ``claude-haiku-4-5-20251001``.
        max_tokens: Maximum tokens in the summary response.
        api_key: Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY`` env var.
        _client_fn: Dependency-injection hook — pass a callable that returns a
            mock Anthropic client for testing.  Do not use in production.

    Returns:
        Plain-text summary (no markdown).

    Raises:
        ImportError: When the ``anthropic`` package is not installed.
    """
    if _client_fn is not None:
        client = _client_fn()
    else:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic package required for summarization. "
                "Install with: pip install 'iobox[ai]'"
            ) from exc
        client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(resource)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return str(message.content[0].text).strip()


def summarize_batch(
    resources: list[Resource],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_workers: int = 5,
    api_key: str | None = None,
    _client_fn: Callable[[], Any] | None = None,
) -> list[str]:
    """Summarize a list of Resources in parallel.

    Failed summarizations (e.g. API errors) log a warning and return an empty
    string for that position.  The output list preserves input order.

    Args:
        resources: List of Resources to summarize.
        model: Claude model ID.
        max_tokens: Maximum tokens per summary.
        max_workers: Maximum concurrent API calls (default 5).
        api_key: Anthropic API key.
        _client_fn: Dependency-injection hook for testing.

    Returns:
        List of summary strings in the same order as *resources*.
    """
    summaries: list[str] = [""] * len(resources)

    def _summarize_one(idx_and_resource: tuple[int, Resource]) -> tuple[int, str]:
        idx, resource = idx_and_resource
        try:
            text = summarize(
                resource,
                model=model,
                max_tokens=max_tokens,
                api_key=api_key,
                _client_fn=_client_fn,
            )
            return idx, text
        except Exception as exc:
            logger.warning(
                "Summarization failed for resource '%s': %s",
                resource.get("id", "?"),
                exc,
            )
            return idx, ""

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_summarize_one, (i, r)): i for i, r in enumerate(resources)}
        for future in as_completed(futures):
            idx, summary = future.result()
            summaries[idx] = summary

    return summaries


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_prompt(resource: Resource) -> str:
    """Dispatch to the appropriate prompt builder by resource_type."""
    rtype = resource.get("resource_type", "")
    if rtype == "email":
        return _email_prompt(resource)
    if rtype == "event":
        return _event_prompt(resource)
    if rtype == "file":
        return _file_prompt(resource)
    # Generic fallback (including EmailData which lacks resource_type)
    return f"Summarize this content in 2-3 sentences.\n\nTitle: {resource.get('title', '')}\n"


def _email_prompt(resource: Resource) -> str:
    raw: Any = resource
    body = (raw.get("body") or raw.get("snippet") or "")[:3000]
    return (
        "Summarize this email in 2-3 sentences. Focus on the main request or topic, "
        "any deadlines or action items, and who needs to act.\n\n"
        f"From: {raw.get('from_', '')}\n"
        f"Subject: {resource.get('title', '')}\n"
        f"Date: {resource.get('created_at', '')}\n"
        f"Body:\n{body}"
    )


def _event_prompt(resource: Resource) -> str:
    raw: Any = resource
    attendees = raw.get("attendees") or []
    att_list = ", ".join((a.get("name") or a.get("email", "")) for a in attendees[:10])
    description = (raw.get("description") or "")[:2000]
    return (
        "Summarize this calendar event in 1-2 sentences. Include the purpose, "
        "key attendees, and any action items if mentioned in the description.\n\n"
        f"Title: {resource.get('title', '')}\n"
        f"Start: {raw.get('start', '')}\n"
        f"Organizer: {raw.get('organizer', '')}\n"
        f"Attendees: {att_list}\n"
        f"Description: {description}"
    )


def _file_prompt(resource: Resource) -> str:
    raw: Any = resource
    content = (raw.get("content") or "")[:3000]
    return (
        "Summarize this document in 2-3 sentences. Focus on the main topic, "
        "key findings or decisions, and intended audience.\n\n"
        f"Title: {resource.get('title', '')}\n"
        f"Type: {raw.get('mime_type', '')}\n"
        f"Content preview:\n{content}"
    )
