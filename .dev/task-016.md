---
id: task-016
title: "processing/embed.py + semantic search"
milestone: 3
status: done
priority: p2
depends_on: [task-002]
blocks: []
parallel_with: [task-015]
estimated_effort: XL
research_needed: false
research_questions: []
assigned_to: null
---

## Context

After the PoC demonstrates cross-type retrieval and summarization, the next capability is semantic (meaning-based) search — finding resources by conceptual similarity rather than keyword matching. This task is currently blocked on research decisions about the embedding and vector store stack.

**Do not implement this task until the research questions are resolved.**

## Scope (draft — subject to change after research)

**Will:**
- `src/iobox/processing/embed.py` — embedding generation and local vector index
- `embed(resources: list[Resource]) -> list[list[float]]` — batch embedding
- Local index stored in `~/.iobox/indexes/{workspace}/index.db`
- `semantic_search(query, workspace, types, top_k) -> list[Resource]`
- MCP tool: `semantic_search_workspace(query, types, top_k)`

**Will NOT:**
- Replace keyword search — this augments, not replaces
- Handle chunking for long documents in initial version
- Implement RAG pipeline (future)

## Resolved Decisions (from architecture planning)

Based on architectural analysis, preliminary preferred choices:
- **Vector store**: `sqlite-vec` — minimal deps, consistent with SQLite usage elsewhere in iobox
- **Embedding**: `voyage-3-lite` (Voyage AI) or `text-embedding-3-small` (OpenAI) as optional dependency, OR local `all-MiniLM-L6-v2` via `sentence-transformers` for offline use

Final decision should be made after testing embedding quality and install-size tradeoffs.

## Research Needed Before Implementation

Before writing any code, answer these questions:

### 1. Vector Store

```
sqlite-vec pros:
  - Pure SQLite extension — zero additional services
  - Small install footprint
  - Already consistent with SQLite if used elsewhere

chromadb pros:
  - Full-featured (HNSW index, metadata filtering)
  - Good Python API

sqlite-vec cons:
  - Newer library, less community resources
  - Vector similarity only (no hybrid search)

Decision criteria:
  - Can we do basic ANN search within 100ms on 50k vectors?
  - What's the wheel size for pip install?
```

### 2. Embedding Model

```
Options to evaluate:
  A. voyage-3-lite (Voyage AI)
     - 1024 dims, context 32k tokens
     - API: ~$0.02/1M tokens (cheap)
     - Requires: pip install voyageai

  B. text-embedding-3-small (OpenAI)
     - 1536 dims
     - API: ~$0.02/1M tokens
     - Requires: pip install openai
     - Many users already have OpenAI key

  C. all-MiniLM-L6-v2 (local, sentence-transformers)
     - 384 dims, offline
     - Install: pip install sentence-transformers (~500MB)
     - No API key needed

Recommendation: Support multiple backends via a pluggable interface.
Default: OpenAI (most users have keys), with local fallback option.
```

### 3. Index Schema

```sql
-- Proposed sqlite-vec schema
CREATE TABLE resource_embeddings (
    id TEXT PRIMARY KEY,           -- resource ID
    workspace TEXT NOT NULL,
    resource_type TEXT NOT NULL,   -- email/event/file
    provider_id TEXT NOT NULL,
    embedding BLOB NOT NULL,       -- vector as JSON or binary
    indexed_at TEXT NOT NULL,      -- ISO 8601
    content_hash TEXT             -- for staleness detection
);

CREATE VIRTUAL TABLE resource_embeddings_vss USING vec0(
    embedding float[1536]  -- dimension depends on model
);
```

### 4. Staleness Handling

Options:
- Hash content + metadata — re-embed when hash changes
- TTL-based expiry — re-embed resources older than N days
- Event-driven — hook into sync to trigger re-embedding

MVP: TTL-based (simplest).

## Implementation Guide (draft)

### After research is complete, implement in this order:

1. `EmbeddingBackend` ABC with `embed(texts: list[str]) -> list[list[float]]`
2. `VoyageEmbeddingBackend`, `OpenAIEmbeddingBackend`, `LocalEmbeddingBackend`
3. `ResourceIndex` — wraps sqlite-vec, stores/queries embeddings
4. `embed_resources(resources, backend, workspace)` — batch embed and store
5. `semantic_search(query, workspace, types, top_k)` — embed query, search index, load full resources
6. MCP tool registration

### Key design constraints:
- Index is workspace-scoped (`~/.iobox/indexes/{workspace}/`)
- `embed_resources` is idempotent — re-run safe (check content hash)
- `semantic_search` falls back gracefully if index doesn't exist

## Dependencies (to add after research confirms)

```toml
[project.optional-dependencies]
semantic = [
    "sqlite-vec>=0.1",
    "voyageai>=0.3",  # or openai>=1.0
]
```

## Test Strategy

- Unit tests: mock embedding backend, test index store/retrieve
- Integration tests: build small index from fixtures, verify search returns correct resources
- No live API calls in CI

## Acceptance Criteria (draft)

- [ ] Research questions answered (documented in `.dev/research/embedding-stack.md`)
- [ ] `EmbeddingBackend` ABC with at least 2 implementations
- [ ] `ResourceIndex` stores and retrieves embeddings via sqlite-vec
- [ ] `semantic_search()` returns ranked resources by similarity
- [ ] Staleness detection prevents unnecessary re-embedding
- [ ] MCP `semantic_search_workspace` tool added
- [ ] All tests pass without live API calls
