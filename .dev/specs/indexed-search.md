# Spec: Indexed workspace search

- **Status:** proposed — not started
- **Written:** 2026-10-31
- **Replaces:** the half-built semantic search in `processing/embed.py` + MCP `semantic_search_workspace` (see [Current state](#current-state))

## Problem

Provider search (Gmail syntax, Graph KQL, Drive `fullText`) is good at finding things you can name: a sender, a subject keyword, a date range. It fails at recall when you can't remember the words — "the email where someone recommended a plumber", "the doc about the kitchen quote", "when did we last talk about the lease renewal?" — especially across years of mail, several accounts, and three resource types.

An AI assistant using iobox over MCP can rephrase keyword queries, which covers recent and well-named items. The gap is **long-tail recall over the whole archive**. That is the only job an index should be built for; a recent-window index duplicates what provider search already does.

## Goals

1. **Whole-archive coverage.** Every email, event and file in every slot of a workspace — not a recent window.
2. **Hybrid retrieval.** Semantic (vector) *and* lexical (BM25) ranking, fused — exact names, invoice numbers and addresses must still match.
3. **Actionable hits.** Every hit carries `slot`, `resource_type`, `id`, `title`, `date`, and a snippet, so the caller can fetch or act on it without guessing the account.
4. **Incremental and resumable.** First build may take an hour; every later run only touches what changed. An interrupted build resumes where it stopped.
5. **Local and private by default.** The index lives under `~/.iobox/indexes/`. Sending content to a third-party embedding API is an explicit choice.
6. **Same surface everywhere.** CLI to build and query; MCP and SDK to query.

## Non-goals (for v1)

- Attachment content (PDF/DOCX text extraction) — metadata and filenames only. Revisit after v1.
- Cross-workspace search.
- Re-ranking with an LLM.
- Real-time indexing (webhooks / push notifications). Incremental runs are on demand or scheduled by the user.
- An MCP tool that *builds* the index. Builds are long-running and may spend API credit; they belong in the CLI.

## User experience

### CLI

```bash
iobox index build [-w WORKSPACE] [--types email,event,file] [--since 2015-01-01]
                  [--backend local|openai|voyage] [--rebuild]
iobox index status [-w WORKSPACE]
iobox index search "plumber recommendation" [-w WORKSPACE] [--types email] [-n 10]
iobox index clear [-w WORKSPACE]
```

- `build` with no index → full build of every slot; with an index → incremental update. Progress per slot (`personal-gmail: 12,400 / 48,210 emails`), safe to Ctrl-C and re-run.
- `--since` bounds the first build for people who genuinely want less; default is everything.
- `--rebuild` discards the index (required when changing backend/model).
- `status` shows backend, model, dimensions, item counts per slot and type, last build time, and per-slot cursor health (e.g. "Gmail history expired — next build does a full rescan of this slot").
- `search` is primarily for debugging ranking; it prints slot, type, date, title and score.

### MCP

`search_index(query, types=None, top_k=10, workspace=None)` (readonly) replaces `semantic_search_workspace`. Returns hits shaped like normal search results (`slot`, `resource_type`, `id`, `title`, `date`, `snippet`, `score`) so the model can pass `slot` as `provider` to `get_email` / `get_event` / `get_file`. Missing index → explicit error telling the user to run `iobox index build`. Stale index (> N days since last build) → results plus a warning entry.

### SDK

```python
from iobox.index import WorkspaceIndex

idx = WorkspaceIndex.open("personal")            # existing index, or empty
idx.build(ws, types=["email"], progress=print)   # full or incremental
hits = idx.search("kitchen renovation quote", top_k=10)
```

## Design

### What gets indexed

| Type | Text embedded | Stored metadata |
|---|---|---|
| Email | subject, from, to/cc, date, body as Markdown (quoted replies and signatures stripped), attachment filenames | slot, id, thread_id, title, date, from, snippet |
| Event | title, organizer, attendees, location, description, date | slot, id, title, start, end |
| File | name, path, extracted text for Docs/Sheets/Slides/text files (size cap) | slot, id, title, modified, mime_type, url |

**Chunking.** Long bodies/documents are split into ~500-token chunks with overlap; each chunk is a row pointing at its parent resource. Search aggregates chunk scores per resource (max), so a long thread or document is one hit.

**Threads.** Index per message (for recall), but return the thread's newest message as the canonical hit with `thread_id`, so assistants can `save_thread`.

### Storage (`~/.iobox/indexes/<workspace>/index.db`)

SQLite, one file per workspace:

- `resources(slot, id, resource_type, title, date, snippet, meta_json, content_hash, indexed_at)` — primary key `(slot, id)`.
- `chunks(rowid, slot, id, chunk_no, text)` plus an **FTS5** virtual table over `text` for BM25.
- `vectors` — `sqlite-vec` `vec0` table (`float[N] distance_metric=cosine`), binary float32 storage (not JSON); pure-Python cosine fallback when `sqlite-vec` is unavailable.
- `cursors(slot, kind, value, updated_at)` — per-slot incremental sync cursors.
- `index_meta` — backend, model, dimensions, schema version (the PROC-01 mismatch guard carries over).

Keying everything by `(slot, id)` is what makes hits routable; today's index keys by `id` alone.

### Build pipeline

For each slot, in parallel across slots, serial within a slot (rate limits are per account):

1. **Enumerate** ids — full enumeration on first build (Gmail `messages.list` paging; Graph `/me/messages` paging; Drive `files.list`; calendar windows).
2. **Diff** against `resources` (new / changed / deleted). Changed = provider modified time or content hash differs.
3. **Fetch** full content for new/changed items in batches (Gmail batch API, Graph `$batch`, Drive export), honouring rate limits and `Retry-After` (reuse the retry logic from the providers).
4. **Convert** to text (existing Markdown converters), chunk, hash.
5. **Embed** in batches; write resources + chunks + vectors in one transaction per batch.
6. **Checkpoint** the enumeration position after each batch so a crash resumes mid-slot.

**Incremental runs** use the provider sync APIs the codebase already has, recorded in `cursors`:

| Provider | Cursor | On expiry |
|---|---|---|
| Gmail | `historyId` (`history.list`) | full re-enumeration of that slot (diff keeps it cheap) |
| Outlook mail | Graph delta link per folder | same |
| Google Calendar | `nextSyncToken` (`CalendarSyncTokenExpiredError` on 410) | same |
| Outlook Calendar | not implemented — re-scan a rolling window | — |
| Google Drive | `changes.list` start page token | same |
| OneDrive | Graph delta | same |

Deletions from the cursor streams remove rows; a periodic full diff catches anything the cursors miss.

### Retrieval

1. Embed the query; take top-K₁ chunk vectors (vec0 or fallback).
2. Take top-K₂ chunks by FTS5 BM25.
3. Fuse with **reciprocal rank fusion**; aggregate per `(slot, id)`; apply `types` filter.
4. Return hits with metadata from `resources` — no provider calls at query time.

### Backends and privacy

- **Default: `local`** (`sentence-transformers`, e.g. `all-MiniLM-L6-v2` or a stronger small model) — free, offline, nothing leaves the machine. Adds an optional heavyweight dependency (`iobox[index]`).
- **`openai` / `voyage`** — better quality, but email bodies are sent to the provider. `build` must say so and require `--backend openai` explicitly (never silently default to a remote API because a key happens to be set).
- Dimensions are taken from the first embedding (PROC-03 lesson), recorded in `index_meta`.

## Estimates

For a mailbox of ~50,000 emails averaging ~500 tokens of useful text:

- **Embedding:** ~25M tokens. Local: free, roughly tens of minutes on a laptop CPU. `text-embedding-3-small`: on the order of US$0.50 (verify current pricing).
- **Fetching:** the dominant cost. Gmail per-user quota allows on the order of tens of full-message fetches per second in batches; expect **~30 minutes to a few hours** for the first build, seconds to minutes for incremental runs. Must be measured on a real mailbox.
- **Storage:** 384-dim float32 ≈ 1.5 KB/chunk; ~100k chunks ≈ 150 MB plus FTS and text. 1536-dim (OpenAI) ≈ 4× the vector storage.

## Current state

`src/iobox/processing/embed.py` has backends, a `ResourceIndex` (sqlite-vec + fallback, metadata/mismatch guard, cosine scoring — fixed in the 2026-10-31 review), `embed_resources()` and `semantic_search()`. Gaps against this spec:

- Nothing builds the index (FU-09); `embed_resources` is SDK-only and embeds whatever dicts it's given (search results carry snippets, not bodies).
- Rows are keyed by `id` with no `slot`, title, date or snippet → hits aren't routable or readable.
- No chunking, no FTS/BM25, no cursors, no resumability.
- Vectors stored as JSON text.
- Default backend is OpenAI (remote).

Recommendation: build this as a new `iobox.index` package (reusing the backend classes) rather than extending `ResourceIndex` in place; deprecate `semantic_search_workspace` / `embed_resources` in the release that ships it.

## Implementation plan

1. **Schema + storage** (`iobox/index/store.py`): tables above, binary vectors, FTS5, migrations, mismatch guard. Unit tests with an in-memory DB.
2. **Text extraction + chunking** (`iobox/index/text.py`): per-type text builders using existing converters; chunker; hashing.
3. **Enumeration + incremental cursors** per provider — small additions to the provider classes (list-all-ids with paging; Drive `changes.list`; OneDrive delta) behind a common `iter_changes(cursor)` interface.
4. **Builder** (`iobox/index/build.py`): per-slot workers, batching, rate-limit handling, checkpoints, progress callback.
5. **Retrieval** (`iobox/index/search.py`): vector + BM25 + RRF, per-resource aggregation.
6. **CLI** `iobox index …`; **MCP** `search_index`; deprecate the old tool.
7. **Docs**: a "Search your archive" guide (setup, privacy, cost, scheduling with cron/launchd).
8. **Live validation** on a real large Gmail mailbox: build time, quota behaviour, result quality on a hand-made set of 20 recall queries (precision@5 vs provider keyword search).

## Open questions

- Which local model gives the best quality/speed trade-off on CPU for email text? Benchmark 2–3 candidates on the recall set.
- Should Drive/OneDrive file text extraction include PDFs in v1 (pure-Python `pypdf`) given how much household admin lives in PDFs?
- Index Sent mail? (Useful for "what did I tell X" — probably yes, flagged per slot.)
- Do we expose `iobox index build` as a scheduled job (launchd/cron helper), or just document it?
- How should the MCP server surface "index is N days stale" without nagging on every call?
