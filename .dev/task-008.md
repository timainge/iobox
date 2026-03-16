---
id: task-008
title: "processing/ — markdown for Event + File"
milestone: 0
status: done
priority: p0
depends_on: [task-002]
blocks: []
parallel_with: [task-004, task-005, task-006, task-007]
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

Iobox converts emails to markdown for saving and display. Now that calendar events and files are first-class resources, they need the same treatment. This task creates `src/iobox/processing/` as a new package with a unified markdown converter that handles all three resource types.

The existing `markdown_converter.py` is left untouched — backward compat is non-negotiable.

## Scope

**Does:**
- Create `src/iobox/processing/` package with `__init__.py`
- Create `src/iobox/processing/markdown.py` with:
  - `convert_event_to_markdown(event: Event) -> str`
  - `convert_file_to_markdown(file: File) -> str`
  - `convert_resource_to_markdown(resource: Resource) -> str` — dispatches by `resource_type`
  - `convert_message_to_markdown(msg: EmailData) -> str` — thin adapter around existing converter
- Unit tests: `tests/unit/test_processing_markdown.py`

**Does NOT:**
- Modify `src/iobox/markdown_converter.py`
- Modify `src/iobox/markdown.py`
- Implement save-to-disk for events/files (that's task-010's CLI)
- Implement summarization (task-015)

## Strategic Fit

The PoC demo needs to output events and files as markdown for display/saving. This is a pure, testable function — no auth, no API calls. Easy to parallelise with Wave 2 provider tasks.

## Architecture Notes

- YAML frontmatter format matches what `markdown_converter.py` uses for emails — consistent structure
- `convert_resource_to_markdown()` uses `resource["resource_type"]` to dispatch — no isinstance
- Frontmatter uses `yaml.dump()` from PyYAML (already a dependency)
- Text content in `convert_file_to_markdown()` is truncated at 10,000 chars with a notice
- Attendee list in event markdown: one per line, formatted as `Name <email>: response_status`
- `convert_message_to_markdown()` calls `markdown_converter.convert_email_to_markdown()` — the only link between the two modules

## Files

| Action | File | Description |
|--------|------|-------------|
| Create | `src/iobox/processing/__init__.py` | Empty package init |
| Create | `src/iobox/processing/markdown.py` | All converter functions |
| Create | `tests/unit/test_processing_markdown.py` | Unit tests |

## Output Format: Event

```markdown
---
id: evt001
title: "Team standup"
start: "2026-03-15T09:00:00-07:00"
end: "2026-03-15T09:30:00-07:00"
all_day: false
organizer: "boss@example.com"
attendees:
  - email: "tim@gmail.com"
    name: null
    response_status: "accepted"
  - email: "alice@gmail.com"
    name: "Alice Smith"
    response_status: "tentative"
location: "Zoom"
meeting_url: "https://meet.google.com/abc-defg"
status: "confirmed"
recurrence: "RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"
provider_id: "google_calendar"
resource_type: "event"
url: "https://calendar.google.com/event?eid=evt001"
saved_date: "2026-03-13"
---

# Team standup

Daily standup meeting
```

## Output Format: File

```markdown
---
id: doc_001
title: "Q4 Planning Notes"
name: "Q4 Planning Notes"
mime_type: "application/vnd.google-apps.document"
size: 0
path: null
parent_id: "folder_abc"
is_folder: false
provider_id: "google_drive"
resource_type: "file"
url: "https://docs.google.com/document/d/doc_001"
saved_date: "2026-03-13"
---

# Q4 Planning Notes

[text content here, if available]

*[Content truncated at 10,000 characters]*
```

## Implementation Guide

### Step 1 — Create processing package

```bash
mkdir src/iobox/processing
touch src/iobox/processing/__init__.py
```

### Step 2 — Implement convert_event_to_markdown

```python
# src/iobox/processing/markdown.py
from __future__ import annotations
import yaml
from datetime import date
from iobox.providers.base import Event, File, Resource, EmailData

MAX_FILE_CONTENT_CHARS = 10_000

def convert_event_to_markdown(event: Event) -> str:
    """Convert an Event TypedDict to a markdown string with YAML frontmatter."""
    frontmatter = {
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
    # Remove None values for cleaner output
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None or k in ("all_day",)}

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    title = event["title"] or "(no title)"
    description = event.get("description") or ""

    lines = [f"---\n{fm_str}---\n", f"# {title}\n"]
    if description:
        lines.append(f"\n{description}\n")

    return "\n".join(lines)
```

### Step 3 — Implement convert_file_to_markdown

```python
def convert_file_to_markdown(file: File) -> str:
    """Convert a File TypedDict to a markdown string with YAML frontmatter."""
    frontmatter = {
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
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None or k in ("size", "is_folder")}

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    title = file["title"] or file["name"] or "(unnamed)"

    lines = [f"---\n{fm_str}---\n", f"# {title}\n"]

    content = file.get("content")
    if content:
        if len(content) > MAX_FILE_CONTENT_CHARS:
            content = content[:MAX_FILE_CONTENT_CHARS]
            lines.append(f"\n{content}\n")
            lines.append(f"\n*[Content truncated at {MAX_FILE_CONTENT_CHARS:,} characters]*\n")
        else:
            lines.append(f"\n{content}\n")

    return "\n".join(lines)
```

### Step 4 — Implement convert_message_to_markdown adapter

```python
def convert_message_to_markdown(msg: EmailData) -> str:
    """Thin adapter: delegates to existing markdown_converter for backward compat."""
    from iobox.markdown_converter import convert_email_to_markdown
    return convert_email_to_markdown(msg)
```

### Step 5 — Implement dispatch function

```python
def convert_resource_to_markdown(resource: Resource) -> str:
    """Dispatch to the appropriate converter based on resource_type."""
    rtype = resource.get("resource_type")
    if rtype == "event":
        return convert_event_to_markdown(resource)  # type: ignore[arg-type]
    elif rtype == "file":
        return convert_file_to_markdown(resource)  # type: ignore[arg-type]
    elif rtype == "email":
        from iobox.providers.base import EmailData
        # EmailData doesn't have resource_type; convert_message_to_markdown handles it
        return convert_message_to_markdown(resource)  # type: ignore[arg-type]
    else:
        raise ValueError(f"Unknown resource_type: {rtype!r}")
```

### Step 6 — Unit tests

```python
# tests/unit/test_processing_markdown.py
import pytest
from iobox.processing.markdown import (
    convert_event_to_markdown,
    convert_file_to_markdown,
    convert_resource_to_markdown,
)

class TestConvertEventToMarkdown:
    def test_contains_yaml_frontmatter(self, sample_event): ...
    def test_title_as_h1(self, sample_event): ...
    def test_attendees_in_frontmatter(self, sample_event): ...
    def test_meeting_url_in_frontmatter(self, sample_event): ...
    def test_all_day_event(self, sample_event): ...
    def test_description_in_body(self, sample_event): ...
    def test_none_fields_omitted(self, sample_event): ...

class TestConvertFileToMarkdown:
    def test_contains_yaml_frontmatter(self, sample_file): ...
    def test_title_as_h1(self, sample_file): ...
    def test_content_included_when_present(self, sample_file): ...
    def test_content_truncated_at_10k(self, sample_file): ...
    def test_no_content_section_when_empty(self, sample_file): ...

class TestConvertResourceToMarkdown:
    def test_dispatches_event(self, sample_event): ...
    def test_dispatches_file(self, sample_file): ...
    def test_unknown_type_raises(self): ...
```

## Key Decisions

**Q: Should None values be omitted from YAML frontmatter?**
Yes — cleaner output. Exception: `all_day` (boolean) and `size` (int) — always include even if falsy. Use explicit allowlist for fields that must always appear.

**Q: Should `attendees` list always appear in event frontmatter?**
Yes, even if empty (`attendees: []`). Consumers may check `attendees` key existence.

**Q: What's the truncation limit for file content?**
10,000 characters, with a `*[Content truncated at 10,000 characters]*` notice. This covers most documents without bloating output.

**Q: Should `convert_message_to_markdown` be tested independently?**
Light test only — just verify it delegates correctly. The real tests are in `test_markdown_converter.py`.

## Verification

```bash
make test
python -c "from iobox.processing.markdown import convert_event_to_markdown, convert_file_to_markdown"
```

## Acceptance Criteria

- [ ] `src/iobox/processing/__init__.py` created
- [ ] `src/iobox/processing/markdown.py` with all four functions
- [ ] `convert_event_to_markdown()` produces valid YAML frontmatter + markdown body
- [ ] `convert_file_to_markdown()` produces valid YAML frontmatter; truncates content at 10k chars
- [ ] `convert_resource_to_markdown()` dispatches by `resource_type`
- [ ] `convert_message_to_markdown()` delegates to existing converter
- [ ] `src/iobox/markdown_converter.py` unchanged
- [ ] All unit tests pass
- [ ] `make type-check` passes
