"""
Resource embedding and semantic search using a local SQLite-backed vector index.

Requires: pip install 'iobox[semantic]'

Architecture:
- ``EmbeddingBackend`` ABC: pluggable embedding model interface
- ``OpenAIEmbeddingBackend``: text-embedding-3-small (default, 1536 dims)
- ``VoyageEmbeddingBackend``: voyage-3-lite (1024 dims)
- ``LocalEmbeddingBackend``: all-MiniLM-L6-v2 via sentence-transformers (384 dims, offline)
- ``ResourceIndex``: SQLite store with optional sqlite-vec ANN acceleration
- ``embed_resources()``: idempotent batch embed + store (skips unchanged resources)
- ``semantic_search()``: embed query → search index → return ranked resource stubs

Usage::

    from iobox.processing.embed import embed_resources, semantic_search, get_backend

    backend = get_backend("openai", api_key="sk-...")
    n = embed_resources(resources, workspace="personal", backend=backend)
    results = semantic_search("budget planning documents", workspace="personal", top_k=5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import struct
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iobox.providers.base import Resource

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "openai"
DEFAULT_MODEL_OPENAI = "text-embedding-3-small"
DEFAULT_MODEL_VOYAGE = "voyage-3-lite"
DEFAULT_MODEL_LOCAL = "all-MiniLM-L6-v2"


# ── Embedding Backends ─────────────────────────────────────────────────────────


class EmbeddingBackend(ABC):
    """Abstract base for embedding model backends."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Number of dimensions in the output embedding vector."""
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Returns one embedding per text.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            List of embedding vectors in the same order as *texts*.
        """
        ...


class OpenAIEmbeddingBackend(EmbeddingBackend):
    """OpenAI ``text-embedding-3-small`` backend (default, 1536 dims).

    Requires: ``pip install openai``
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL_OPENAI,
        _client_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client_fn = _client_fn

    @property
    def dimensions(self) -> int:
        return 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client_fn is not None:
            client = self._client_fn()
        else:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "openai package required for embedding. "
                    "Install with: pip install 'iobox[semantic]'"
                ) from exc
            client = openai.OpenAI(api_key=self._api_key)
        response = client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


class VoyageEmbeddingBackend(EmbeddingBackend):
    """Voyage AI ``voyage-3-lite`` backend (1024 dims).

    Requires: ``pip install voyageai``
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL_VOYAGE,
        _client_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client_fn = _client_fn

    @property
    def dimensions(self) -> int:
        return 1024

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client_fn is not None:
            client = self._client_fn()
        else:
            try:
                import voyageai
            except ImportError as exc:
                raise ImportError(
                    "voyageai package required for Voyage embedding. Install voyageai."
                ) from exc
            client = voyageai.Client(api_key=self._api_key)
        result = client.embed(texts, model=self._model)
        return list(result.embeddings)


class LocalEmbeddingBackend(EmbeddingBackend):
    """Local ``all-MiniLM-L6-v2`` backend via sentence-transformers (384 dims, offline).

    Requires: ``pip install sentence-transformers`` (~500 MB)
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL_LOCAL,
        _model_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._model_name = model
        self._model_fn = _model_fn
        self._instance: Any = None

    @property
    def dimensions(self) -> int:
        return 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model_fn is not None:
            model = self._model_fn()
        else:
            if self._instance is None:
                try:
                    from sentence_transformers import (
                        SentenceTransformer,
                    )
                except ImportError as exc:
                    raise ImportError(
                        "sentence-transformers required for local embedding. "
                        "Install with: pip install sentence-transformers"
                    ) from exc
                self._instance = SentenceTransformer(self._model_name)
            model = self._instance
        embeddings = model.encode(texts)
        return [list(e) for e in embeddings]


def get_backend(
    name: str = DEFAULT_BACKEND,
    *,
    api_key: str | None = None,
    model: str | None = None,
    _client_fn: Callable[[], Any] | None = None,
) -> EmbeddingBackend:
    """Return an EmbeddingBackend by name.

    Args:
        name: Backend name: ``"openai"``, ``"voyage"``, or ``"local"``.
        api_key: API key for cloud backends (falls back to env var).
        model: Override the default model for the chosen backend.
        _client_fn: Dependency-injection hook for testing.

    Raises:
        ValueError: For unknown backend names.
    """
    if name == "openai":
        return OpenAIEmbeddingBackend(
            api_key=api_key, model=model or DEFAULT_MODEL_OPENAI, _client_fn=_client_fn
        )
    if name == "voyage":
        return VoyageEmbeddingBackend(
            api_key=api_key, model=model or DEFAULT_MODEL_VOYAGE, _client_fn=_client_fn
        )
    if name == "local":
        return LocalEmbeddingBackend(model=model or DEFAULT_MODEL_LOCAL, _model_fn=_client_fn)
    raise ValueError(f"Unknown backend: {name!r}. Choose from: openai, voyage, local")


# ── Vector Index ───────────────────────────────────────────────────────────────


def _get_index_path(workspace: str, credentials_dir: str | None = None) -> Path:
    base = Path(credentials_dir) if credentials_dir else Path.home() / ".iobox"
    path = base / "indexes" / workspace
    path.mkdir(parents=True, exist_ok=True)
    return path / "index.db"


class ResourceIndex:
    """SQLite-backed vector index for resource embeddings.

    Uses sqlite-vec for ANN search if available; falls back to pure-Python
    cosine similarity when sqlite-vec is not installed.

    Args:
        workspace: Workspace name (used for path and scoping queries).
        dimensions: Number of dimensions in the embedding vectors.
        credentials_dir: Base directory for ``~/.iobox/``.
        _conn: Inject a SQLite connection for testing (uses in-memory DB).
    """

    def __init__(
        self,
        workspace: str,
        dimensions: int,
        credentials_dir: str | None = None,
        _conn: sqlite3.Connection | None = None,
    ) -> None:
        self.workspace = workspace
        self.dimensions = dimensions
        self._credentials_dir = credentials_dir
        self._conn_override = _conn
        self._conn: sqlite3.Connection | None = None
        self._has_vec: bool = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._conn_override is not None:
            self._conn = self._conn_override
        else:
            db_path = _get_index_path(self.workspace, self._credentials_dir)
            self._conn = sqlite3.connect(str(db_path))
        self._setup_tables(self._conn)
        return self._conn

    def _setup_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_embeddings (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id   TEXT UNIQUE NOT NULL,
                workspace     TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                provider_id   TEXT NOT NULL,
                content_hash  TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                indexed_at    TEXT NOT NULL
            )
        """)
        conn.commit()
        self._has_vec = self._try_load_vec(conn)
        if self._has_vec:
            try:
                conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS resource_embeddings_vss "
                    f"USING vec0(embedding float[{self.dimensions}])"
                )
                conn.commit()
            except Exception:
                logger.debug("Failed to create vec0 virtual table; falling back to Python search")
                self._has_vec = False

    def _try_load_vec(self, conn: sqlite3.Connection) -> bool:
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            return True
        except Exception:
            logger.debug("sqlite-vec not available; using Python cosine similarity fallback")
            return False

    def get_content_hash(self, resource_id: str) -> str | None:
        """Return the stored content hash for a resource, or None if not indexed."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT content_hash FROM resource_embeddings WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()
        return str(row[0]) if row else None

    def upsert(
        self,
        resource_id: str,
        resource_type: str,
        provider_id: str,
        embedding: list[float],
        content_hash: str,
    ) -> None:
        """Store or update an embedding for a resource."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        embedding_json = json.dumps(embedding)

        existing = conn.execute(
            "SELECT id FROM resource_embeddings WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()

        if existing:
            row_id: int = int(existing[0])
            conn.execute(
                """UPDATE resource_embeddings
                   SET content_hash = ?, embedding_json = ?, indexed_at = ?
                   WHERE resource_id = ?""",
                (content_hash, embedding_json, now, resource_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO resource_embeddings
                   (resource_id, workspace, resource_type, provider_id,
                    content_hash, embedding_json, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    resource_id,
                    self.workspace,
                    resource_type,
                    provider_id,
                    content_hash,
                    embedding_json,
                    now,
                ),
            )
            row_id = int(cursor.lastrowid or 0)

        conn.commit()

        if self._has_vec and row_id:
            blob = struct.pack(f"{self.dimensions}f", *embedding)
            conn.execute("DELETE FROM resource_embeddings_vss WHERE rowid = ?", (row_id,))
            conn.execute(
                "INSERT INTO resource_embeddings_vss(rowid, embedding) VALUES (?, ?)",
                (row_id, blob),
            )
            conn.commit()

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_types: list[str] | None = None,
    ) -> list[tuple[str, str, str, float]]:
        """Return (resource_id, resource_type, provider_id, distance) tuples.

        Distance is cosine distance (lower = more similar). Results are sorted
        ascending by distance.
        """
        conn = self._get_conn()
        if self._has_vec:
            return self._search_vec(conn, query_embedding, top_k, filter_types)
        return self._search_python(conn, query_embedding, top_k, filter_types)

    def _search_vec(
        self,
        conn: sqlite3.Connection,
        query_embedding: list[float],
        top_k: int,
        filter_types: list[str] | None,
    ) -> list[tuple[str, str, str, float]]:
        blob = struct.pack(f"{self.dimensions}f", *query_embedding)
        fetch_k = top_k * 3 if filter_types else top_k
        rows: list[tuple[str, str, str, float]] = conn.execute(
            """SELECT r.resource_id, r.resource_type, r.provider_id, v.distance
               FROM resource_embeddings_vss v
               JOIN resource_embeddings r ON r.id = v.rowid
               WHERE v.embedding MATCH ?
                 AND k = ?
               ORDER BY v.distance""",
            (blob, fetch_k),
        ).fetchall()
        if filter_types:
            type_set = set(filter_types)
            rows = [(rid, rt, pid, d) for rid, rt, pid, d in rows if rt in type_set]
        return rows[:top_k]

    def _search_python(
        self,
        conn: sqlite3.Connection,
        query_embedding: list[float],
        top_k: int,
        filter_types: list[str] | None,
    ) -> list[tuple[str, str, str, float]]:
        where = "WHERE workspace = ?"
        params: list[Any] = [self.workspace]
        if filter_types:
            placeholders = ",".join("?" * len(filter_types))
            where += f" AND resource_type IN ({placeholders})"
            params.extend(filter_types)
        rows = conn.execute(
            f"SELECT resource_id, resource_type, provider_id, embedding_json "
            f"FROM resource_embeddings {where}",
            params,
        ).fetchall()

        scored: list[tuple[str, str, str, float]] = []
        for resource_id, resource_type, provider_id, embedding_json in rows:
            vec: list[float] = json.loads(embedding_json)
            sim = _cosine_similarity(query_embedding, vec)
            scored.append((resource_id, resource_type, provider_id, 1.0 - sim))

        scored.sort(key=lambda x: x[3])
        return scored[:top_k]

    def count(self) -> int:
        """Return the number of indexed resources."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM resource_embeddings WHERE workspace = ?",
            (self.workspace,),
        ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        """Close the database connection (no-op if using an injected connection)."""
        if self._conn is not None and self._conn_override is None:
            self._conn.close()
            self._conn = None


# ── Text extraction ────────────────────────────────────────────────────────────


def _resource_to_text(resource: Resource) -> str:
    """Convert a Resource to a plain-text string suitable for embedding."""
    raw: Any = resource
    rtype = resource.get("resource_type", "")
    title = str(resource.get("title") or "")

    if rtype == "email":
        body = str(raw.get("body") or raw.get("snippet") or "")[:3000]
        from_ = str(raw.get("from_") or "")
        return f"Email from {from_}: {title}\n{body}"
    if rtype == "event":
        description = str(raw.get("description") or "")[:2000]
        organizer = str(raw.get("organizer") or "")
        return f"Calendar event: {title}\nOrganizer: {organizer}\n{description}"
    if rtype == "file":
        content = str(raw.get("content") or "")[:3000]
        mime = str(raw.get("mime_type") or "")
        return f"File ({mime}): {title}\n{content}"
    return title


def _content_hash(resource: Resource) -> str:
    """Return a 16-char hex hash of the resource's text + modified_at."""
    text = _resource_to_text(resource)
    modified = str(resource.get("modified_at") or "")
    digest = hashlib.sha256(f"{text}{modified}".encode()).hexdigest()
    return digest[:16]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [0, 1]. Returns 0.0 for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return float(dot / (mag_a * mag_b))


# ── Public API ─────────────────────────────────────────────────────────────────


def embed_resources(
    resources: list[Resource],
    workspace: str,
    *,
    backend: EmbeddingBackend | None = None,
    credentials_dir: str | None = None,
    batch_size: int = 50,
    _index: ResourceIndex | None = None,
) -> int:
    """Embed a list of resources and store them in the local index.

    Idempotent: resources whose content hash hasn't changed are skipped.

    Args:
        resources: Resources to embed.
        workspace: Workspace name (determines index path).
        backend: Embedding backend to use (defaults to OpenAI).
        credentials_dir: Base directory for ``~/.iobox/``.
        batch_size: Maximum resources per API call.
        _index: Inject a ``ResourceIndex`` for testing.

    Returns:
        Number of resources newly embedded or updated.
    """
    if not resources:
        return 0
    if backend is None:
        backend = get_backend("openai")

    index = (
        _index
        if _index is not None
        else ResourceIndex(workspace, backend.dimensions, credentials_dir)
    )

    to_embed: list[tuple[int, Resource]] = []
    for i, resource in enumerate(resources):
        resource_id = str(resource.get("id") or "")
        if not resource_id:
            continue
        current_hash = _content_hash(resource)
        if index.get_content_hash(resource_id) != current_hash:
            to_embed.append((i, resource))

    count = 0
    for batch_start in range(0, len(to_embed), batch_size):
        batch = to_embed[batch_start : batch_start + batch_size]
        texts = [_resource_to_text(r) for _, r in batch]
        try:
            embeddings = backend.embed(texts)
        except Exception as exc:
            logger.error("Embedding batch failed: %s", exc)
            continue
        for (_, resource), embedding in zip(batch, embeddings, strict=False):
            resource_id = str(resource.get("id") or "")
            index.upsert(
                resource_id=resource_id,
                resource_type=str(resource.get("resource_type") or ""),
                provider_id=str(resource.get("provider_id") or ""),
                embedding=embedding,
                content_hash=_content_hash(resource),
            )
            count += 1

    if _index is None:
        index.close()
    return count


def semantic_search(
    query: str,
    workspace: str,
    *,
    types: list[str] | None = None,
    top_k: int = 10,
    backend: EmbeddingBackend | None = None,
    credentials_dir: str | None = None,
    _index: ResourceIndex | None = None,
) -> list[dict[str, Any]]:
    """Search the local embedding index by semantic similarity.

    Args:
        query: Natural-language query string.
        workspace: Workspace name to search.
        types: Filter by resource type, e.g. ``["email", "event"]``.
        top_k: Maximum number of results to return.
        backend: Embedding backend (must match the one used for indexing).
        credentials_dir: Base directory for ``~/.iobox/``.
        _index: Inject a ``ResourceIndex`` for testing.

    Returns:
        List of dicts with ``id``, ``resource_type``, ``provider_id``, and
        ``score`` (0–1, higher is more similar). Empty list if the index is
        empty or the query fails.
    """
    if backend is None:
        backend = get_backend("openai")

    index = (
        _index
        if _index is not None
        else ResourceIndex(workspace, backend.dimensions, credentials_dir)
    )

    try:
        query_embeddings = backend.embed([query])
    except Exception as exc:
        logger.error("Failed to embed query: %s", exc)
        if _index is None:
            index.close()
        return []

    query_vec = query_embeddings[0]
    results = index.search(query_vec, top_k=top_k, filter_types=types)

    if _index is None:
        index.close()

    return [
        {
            "id": resource_id,
            "resource_type": resource_type,
            "provider_id": provider_id,
            "score": round(max(0.0, 1.0 - distance), 4),
        }
        for resource_id, resource_type, provider_id, distance in results
    ]
