# Embedding Stack Research — task-016

## Decisions

### Vector Store: `sqlite-vec`

**Chosen.** Reasons:
- Zero additional services — pure SQLite extension, consistent with project philosophy
- Acceptable ANN search performance for 50k vectors (sub-100ms)
- Smallest install footprint among options
- `chromadb` and `lancedb` bring heavier deps and are overkill for single-user local indexing

### Embedding Backend: pluggable, default OpenAI

**Architecture:** `EmbeddingBackend` ABC with multiple implementations.

**Default:** `OpenAIEmbeddingBackend` (`text-embedding-3-small`, 1536 dims, $0.02/1M tokens)
- Most users already have an OpenAI key
- Excellent quality for email/calendar/file content
- Configurable dimensions (can use 512 dims to save storage)

**Secondary:** `VoyageEmbeddingBackend` (`voyage-3-lite`, 1024 dims)
- Slightly cheaper, good quality
- Less common — keep as option

**Local/offline:** `LocalEmbeddingBackend` (`all-MiniLM-L6-v2` via `sentence-transformers`, 384 dims)
- No API key, fully offline
- ~500MB install — too heavy for default, but valuable as fallback
- Useful for air-gapped environments

### Index Storage: per-workspace

**Decision:** Embeddings stored per-workspace at `~/.iobox/indexes/{workspace}/index.db`

Reasons:
- Workspaces have different provider sets; mixing embeddings across workspaces would be confusing
- Users may want to delete/rebuild a single workspace's index without affecting others
- Clean separation mirrors the workspace config model

### Staleness Handling: content hash

**Decision:** Hash resource content + modified_at — re-embed when hash changes.

Simpler than TTL (no arbitrary expiry window) and more correct (re-embed when content actually changes, not on a schedule). TTL-based can be added as a CLI flag later if needed.

### Use Case: hybrid search (keyword + semantic)

Semantic search augments, does not replace, keyword search. The `semantic_search()` function returns top-k resources by cosine similarity. MCP tool exposes it alongside existing `search_workspace`.

No RAG/chunking for MVP — resources are summarized before embedding (use first N chars of body/content as the embedding text).

## Optional Dependency Group

```toml
semantic = [
    "sqlite-vec>=0.1",
    "openai>=1.0",        # default backend
]
# voyageai>=0.3 and sentence-transformers are alternatives, not in default group
```
