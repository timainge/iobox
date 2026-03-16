---
id: task-015
title: "processing/summarize.py — resource summarization"
milestone: 3
status: done
priority: p2
depends_on: [task-002]
blocks: []
parallel_with: [task-016]
estimated_effort: M
research_needed: false
research_questions: []
assigned_to: null
---

## Context

After the PoC shows cross-type retrieval, the next value layer is intelligence: summarising retrieved resources. This task adds `processing/summarize.py`, which uses the Anthropic API (Claude) to generate concise summaries of any `Resource` type.

This is an optional feature gated behind the `ai` dependency group.

## Scope

**Does:**
- `src/iobox/processing/summarize.py`
- `summarize(resource, *, model, max_tokens) -> str`
- `summarize_batch(resources, ...) -> list[str]` — parallel with rate limiting
- Prompt adapts by `resource_type`: email vs event vs file
- Add `anthropic` to optional `ai` dependency group in `pyproject.toml`
- Unit tests with mocked Anthropic client

**Does NOT:**
- Expose via MCP (task-011 update)
- Add CLI command (can be added later)
- Add summarization to save flows automatically
- Implement streaming responses

## Architecture Notes

- Uses `anthropic.Anthropic()` client — sync API for simplicity
- Model default: `"claude-haiku-4-5-20251001"` — fast and cheap for summarization
- Import guard: wrap `import anthropic` in try/except with helpful error
- Prompt is built by `_build_prompt(resource)` — dispatches by `resource_type`
- `summarize_batch` uses `ThreadPoolExecutor` with max 5 concurrent requests (rate limit friendly)
- Return plain text (no markdown) for summaries — callers decide formatting
- `EmailData` is not `Resource` — add overload that accepts `EmailData` by detecting missing `resource_type`

## Files

| Action | File | Description |
|--------|------|-------------|
| Modify | `src/iobox/processing/__init__.py` | Export summarize functions |
| Create | `src/iobox/processing/summarize.py` | Summarization functions |
| Modify | `pyproject.toml` | Add `anthropic` to `[ai]` optional group |
| Create | `tests/unit/test_processing_summarize.py` | Unit tests |

## Prompts by Resource Type

### Email prompt

```
Summarize this email in 2-3 sentences. Focus on the main request or topic, any deadlines or action items, and who needs to act.

From: {from_}
Subject: {title}
Date: {created_at}
Body:
{body[:3000]}
```

### Event prompt

```
Summarize this calendar event in 1-2 sentences. Include the purpose, key attendees, and any action items if mentioned in the description.

Title: {title}
Start: {start}
Organizer: {organizer}
Attendees: {attendee_list}
Description: {description[:2000]}
```

### File prompt

```
Summarize this document in 2-3 sentences. Focus on the main topic, key findings or decisions, and intended audience.

Title: {title}
Type: {mime_type}
Content preview:
{content[:3000]}
```

## Implementation Guide

### Step 1 — Implement summarize()

```python
# src/iobox/processing/summarize.py
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    _client_fn: Callable | None = None,  # DI hook: inject mock client in tests
) -> str:
    """
    Summarize a Resource using Claude.
    Requires: pip install 'iobox[ai]'
    """
    if _client_fn is None:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic package required for summarization. "
                "Install with: pip install 'iobox[ai]'"
            )
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = _client_fn()

    prompt = _build_prompt(resource)

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()

def summarize_batch(
    resources: list[Resource],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_workers: int = 5,
    api_key: str | None = None,
) -> list[str]:
    """
    Summarize a list of Resources in parallel.
    Returns summaries in the same order as input resources.
    """
    summaries = [""] * len(resources)

    def summarize_one(idx_resource: tuple[int, Resource]) -> tuple[int, str]:
        idx, resource = idx_resource
        try:
            return idx, summarize(resource, model=model, max_tokens=max_tokens, api_key=api_key)
        except Exception as e:
            logger.error(f"Summarization failed for resource {resource.get('id', '?')}: {e}")
            return idx, ""

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(summarize_one, (i, r)): i for i, r in enumerate(resources)}
        for future in as_completed(futures):
            idx, summary = future.result()
            summaries[idx] = summary

    return summaries
```

### Step 2 — Implement _build_prompt

```python
def _build_prompt(resource: Resource) -> str:
    rtype = resource.get("resource_type", "")
    if rtype == "email":
        return _email_prompt(resource)
    elif rtype == "event":
        return _event_prompt(resource)
    elif rtype == "file":
        return _file_prompt(resource)
    else:
        # Generic fallback
        return f"Summarize this content in 2-3 sentences:\n\nTitle: {resource.get('title', '')}\n"

def _email_prompt(resource) -> str:
    body = (resource.get("body") or resource.get("snippet") or "")[:3000]
    return (
        "Summarize this email in 2-3 sentences. Focus on the main request or topic, "
        "any deadlines or action items, and who needs to act.\n\n"
        f"From: {resource.get('from_', '')}\n"
        f"Subject: {resource.get('title', '')}\n"
        f"Date: {resource.get('created_at', '')}\n"
        f"Body:\n{body}"
    )

def _event_prompt(resource) -> str:
    attendees = resource.get("attendees", [])
    att_list = ", ".join(
        a.get("name") or a.get("email", "") for a in attendees[:10]
    )
    description = (resource.get("description") or "")[:2000]
    return (
        "Summarize this calendar event in 1-2 sentences. Include the purpose, "
        "key attendees, and any action items if mentioned.\n\n"
        f"Title: {resource.get('title', '')}\n"
        f"Start: {resource.get('start', '')}\n"
        f"Organizer: {resource.get('organizer', '')}\n"
        f"Attendees: {att_list}\n"
        f"Description: {description}"
    )

def _file_prompt(resource) -> str:
    content = (resource.get("content") or "")[:3000]
    return (
        "Summarize this document in 2-3 sentences. Focus on the main topic, "
        "key findings or decisions, and intended audience.\n\n"
        f"Title: {resource.get('title', '')}\n"
        f"Type: {resource.get('mime_type', '')}\n"
        f"Content preview:\n{content}"
    )
```

### Step 3 — Update pyproject.toml

```toml
[project.optional-dependencies]
# ... existing groups ...
ai = ["anthropic>=0.40"]
```

### Step 4 — Unit tests

Use `_client_fn=` injection — no patching required. The mock client factory returns a fake client whose `messages.create()` returns a predictable response.

```python
# tests/unit/test_processing_summarize.py
from unittest.mock import MagicMock
from iobox.processing.summarize import summarize, summarize_batch

@pytest.fixture
def mock_client_fn():
    """Returns a factory that produces a mock Anthropic client."""
    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Summary text.")]
    )
    return lambda: client

class TestSummarize:
    def test_summarize_email(self, mock_client_fn, sample_email_resource):
        result = summarize(sample_email_resource, _client_fn=mock_client_fn)
        assert result == "Summary text."

    def test_summarize_event(self, mock_client_fn, sample_event):
        result = summarize(sample_event, _client_fn=mock_client_fn)
        assert isinstance(result, str)

    def test_summarize_file(self, mock_client_fn, sample_file): ...
    def test_import_error_when_no_anthropic(self): ...

class TestSummarizeBatch:
    def test_returns_summaries_in_order(self, mock_anthropic_client): ...
    def test_partial_failure_returns_empty_string(self, mock_anthropic_client): ...
    def test_parallel_execution(self, mock_anthropic_client): ...
```

## Key Decisions

**Q: Which model should be the default?**
`claude-haiku-4-5-20251001` — fast, cheap, good enough for summarization. Power users can pass a different model.

**Q: Should `summarize` accept `EmailData` directly?**
Add a type check: if `resource_type` key is absent, assume it's `EmailData` and wrap it as an email. Don't add a separate function.

**Q: Should we truncate content before sending to the API?**
Yes — truncate body/content at 3,000 chars in the prompt. This keeps API costs low and fits within context.

## Verification

```bash
make test
python -c "from iobox.processing.summarize import summarize"
# With API key set:
# python -c "from iobox.processing.summarize import summarize; print(summarize({'resource_type': 'event', 'title': 'Test', 'start': '2026-03-15'}))"
```

## Acceptance Criteria

- [ ] `summarize(resource, model=..., max_tokens=...)` works for email, event, file
- [ ] `summarize_batch(resources, ...)` runs in parallel, preserves order, handles failures
- [ ] `_build_prompt()` dispatches by `resource_type` with appropriate prompt for each type
- [ ] Import guard raises helpful error when `anthropic` not installed
- [ ] `anthropic>=0.40` added to `ai` optional dependency group in `pyproject.toml`
- [ ] Unit tests mock `anthropic.Anthropic()` — no real API calls in tests
- [ ] All tests pass
