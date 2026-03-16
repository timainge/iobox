"""
Unified resource → markdown converters.

Converts Event, File, and Email (via adapter) to markdown strings with
YAML frontmatter. The existing markdown_converter.py is untouched.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from iobox.providers.base import EmailData, Event, File, Resource

MAX_FILE_CONTENT_CHARS = 10_000

# Keys always included in frontmatter even when falsy (bool / int fields)
_ALWAYS_INCLUDE_EVENT = {"all_day", "attendees"}
_ALWAYS_INCLUDE_FILE = {"size", "is_folder", "attendees"}


def convert_event_to_markdown(event: Event) -> str:
    """Convert an Event TypedDict to a markdown string with YAML frontmatter."""
    frontmatter: dict[str, Any] = {
        "id": event["id"],
        "title": event["title"],
        "start": event["start"],
        "end": event["end"],
        "all_day": event["all_day"],
        "organizer": event.get("organizer"),
        "attendees": [
            {
                "email": att["email"],
                "name": att.get("name"),
                "response_status": att.get("response_status"),
            }
            for att in event.get("attendees", [])
        ],
        "location": event.get("location"),
        "meeting_url": event.get("meeting_url"),
        "status": event.get("status"),
        "recurrence": event.get("recurrence"),
        "provider_id": event["provider_id"],
        "resource_type": "event",
        "url": event.get("url"),
        "saved_date": date.today().isoformat(),
    }
    # Omit None values, but keep falsy keys that are always meaningful
    frontmatter = {
        k: v for k, v in frontmatter.items() if v is not None or k in _ALWAYS_INCLUDE_EVENT
    }

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    title = event["title"] or "(no title)"
    description = event.get("description") or ""

    parts = [f"---\n{fm_str}---", f"# {title}"]
    if description:
        parts.append(description)

    return "\n\n".join(parts) + "\n"


def convert_file_to_markdown(file: File) -> str:
    """Convert a File TypedDict to a markdown string with YAML frontmatter."""
    frontmatter: dict[str, Any] = {
        "id": file["id"],
        "title": file["title"],
        "name": file["name"],
        "mime_type": file["mime_type"],
        "size": file["size"],
        "path": file.get("path"),
        "parent_id": file.get("parent_id"),
        "is_folder": file["is_folder"],
        "provider_id": file["provider_id"],
        "resource_type": "file",
        "url": file.get("url"),
        "saved_date": date.today().isoformat(),
    }
    # Omit None values, but keep falsy keys that are always meaningful
    frontmatter = {
        k: v for k, v in frontmatter.items() if v is not None or k in _ALWAYS_INCLUDE_FILE
    }

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    title = file["title"] or file["name"] or "(unnamed)"

    parts = [f"---\n{fm_str}---", f"# {title}"]

    content = file.get("content")
    if content:
        truncated = False
        if len(content) > MAX_FILE_CONTENT_CHARS:
            content = content[:MAX_FILE_CONTENT_CHARS]
            truncated = True
        parts.append(content)
        if truncated:
            parts.append(f"*[Content truncated at {MAX_FILE_CONTENT_CHARS:,} characters]*")

    return "\n\n".join(parts) + "\n"


def convert_message_to_markdown(msg: EmailData) -> str:
    """Thin adapter: delegates to existing markdown_converter for backward compat."""
    from iobox.markdown_converter import convert_email_to_markdown

    return convert_email_to_markdown(msg)  # type: ignore[arg-type]


def convert_resource_to_markdown(resource: Resource) -> str:
    """Dispatch to the appropriate converter based on resource_type."""
    rtype = resource.get("resource_type")
    if rtype == "event":
        return convert_event_to_markdown(resource)  # type: ignore[arg-type]
    elif rtype == "file":
        return convert_file_to_markdown(resource)  # type: ignore[arg-type]
    elif rtype == "email":
        return convert_message_to_markdown(resource)  # type: ignore[arg-type]
    else:
        raise ValueError(f"Unknown resource_type: {rtype!r}")
