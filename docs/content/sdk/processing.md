# Processing

`iobox.processing` turns resources into something useful: Markdown files, Claude-written summaries, and a local semantic search index.

## Markdown

### Events and files

```python
from iobox.processing.markdown import convert_event_to_markdown, convert_file_to_markdown

md = convert_event_to_markdown(event)   # YAML frontmatter + description
md = convert_file_to_markdown(file)     # YAML frontmatter + content (if fetched)
```

`convert_resource_to_markdown(resource)` dispatches on `resource["resource_type"]`.

### Email

```python
from iobox.processing.markdown_converter import convert_email_to_markdown, convert_thread_to_markdown
from iobox.processing.file_manager import save_email_to_markdown

data = dict(gmail.get_email_content(message_id, preferred_content_type="text/html"))
data["from"] = data.pop("from_")                 # converter expects "from"

md = convert_email_to_markdown(data)
path = save_email_to_markdown(data, md, "./emails")   # dedup-safe filename, returns path
```

`convert_thread_to_markdown(messages)` renders a list of messages (from `get_thread`) as one document. HTML bodies are converted to Markdown; signature clutter is cleaned up.

Formats are described in [Output format](../reference/output-format.md).

### Incremental sync

`iobox.processing.file_manager.SyncState` stores the provider sync token for an output directory, so repeated exports fetch only new messages — the mechanism behind `iobox save --sync`.

## Summaries

Requires `pip install 'iobox[ai]'` and `ANTHROPIC_API_KEY`.

```python
from iobox.processing.summarize import summarize, summarize_batch

print(summarize(event))
summaries = summarize_batch(ws.search("Henderson"), max_workers=5)
```

| Function | Returns | Notes |
|---|---|---|
| `summarize(resource, *, model, max_tokens, api_key)` | `str` | Prompt is tailored to the resource type |
| `summarize_batch(resources, *, model, max_tokens, max_workers=5, api_key)` | `list[str]` | Parallel; failures log a warning and return `""` |

The default model is a small, fast Claude model; pass `model=` to override.

## Semantic search

Requires `pip install 'iobox[semantic]'`. Builds a local SQLite index per workspace (with `sqlite-vec` acceleration when available) under `~/.iobox`.

```python
from iobox.processing.embed import embed_resources, semantic_search, get_backend

backend = get_backend("openai")      # "openai" | "voyage" | "local"
resources = ws.search("", types=["email", "event", "file"], max_results_per_type=200)

n = embed_resources(resources, workspace="personal", backend=backend)   # skips unchanged items
hits = semantic_search("plans for the kitchen renovation", workspace="personal",
                       top_k=5, backend=backend)
# [{"id": ..., "resource_type": "email", "provider_id": "gmail", "score": 0.82}, ...]
```

| Backend | Model | Dimensions | Needs |
|---|---|---|---|
| `openai` *(default)* | `text-embedding-3-small` | 1536 | `OPENAI_API_KEY` |
| `voyage` | `voyage-3-lite` | 1024 | `VOYAGE_API_KEY` |
| `local` | `all-MiniLM-L6-v2` | 384 | `sentence-transformers`, offline |

Query with the same backend you indexed with. Results are stubs (`id`, `resource_type`, `provider_id`, `score`) — fetch the full resource from its provider. The MCP tool `semantic_search_workspace` queries the same index.
