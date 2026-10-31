"""
Resource embedding and semantic search using a local SQLite-backed vector index.

Requires: pip install 'iobox[semantic]'

Architecture:
- ``EmbeddingBackend`` ABC: pluggable embedding model interface
- ``OpenAIEmbeddingBackend``: text-embedding-3-small (default, 1536 dims)
- ``VoyageEmbeddingBackend``: voyage-3-lite (512 dims)
- ``LocalEmbeddingBackend``: all-MiniLM-L6-v2 via sentence-transformers (384 dims, offline)
- ``ResourceIndex``: SQLite store with optional sqlite-vec ANN acceleration
- ``embed_resources()``: idempotent batch embed + store (skips unchanged resources)
- ``semantic_search()``: embed query → search index → return ranked resource stubs

Index metadata
--------------
Each index records the backend name, model, vector dimensions, and distance
metric it was built with (``index_meta`` table). The dimensions are taken from
the first embedding actually stored, not from the backend's declared value.
Opening an index with a different backend/model, or storing/querying a vector
of a different length, raises :class:`IndexMismatchError` — vectors from
different models are not comparable. Rebuild with
``embed_resources(..., rebuild=True)`` (or delete the index file). The index
is never rebuilt implicitly, because that would silently drop entries for
resources not passed to the current call.

Both search paths (sqlite-vec and the pure-Python fallback) rank by cosine
similarity, so scores are consistent whether or not sqlite-vec is installed.

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

# Declared output sizes for known models. These are informational only: the
# index always records the length of the first embedding it actually stores.
_OPENAI_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
_VOYAGE_DIMENSIONS = {
    "voyage-3-lite": 512,
    "voyage-3": 1024,
    "voyage-3-large": 1024,
    "voyage-3.5": 1024,
    "voyage-3.5-lite": 1024,
}
_LOCAL_DIMENSIONS = {"all-MiniLM-L6-v2": 384}

DISTANCE_METRIC = "cosine"
_VEC_TABLE = "resource_embeddings_vss"
_VEC_MAX_K = 4096  # sqlite-vec's upper bound on k for KNN queries


class IndexMismatchError(ValueError):
    """The index was built with a different backend, model, or vector size."""


# ── Embedding Backends ─────────────────────────────────────────────────────────


def _to_float_list(vector: Any) -> list[float]:
    """Convert a vector (list, tuple, numpy array) to a list of Python floats."""
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(x) for x in vector]


class EmbeddingBackend(ABC):
    """Abstract base for embedding model backends."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Declared number of dimensions in the output embedding vector."""
        ...

    @property
    def name(self) -> str:
        """Short backend identifier recorded in the index metadata."""
        return type(self).__name__

    @property
    def model(self) -> str:
        """Model identifier recorded in the index metadata."""
        return ""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Returns one embedding per text.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            List of embedding vectors (plain Python floats) in the same order
            as *texts*.
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
        return _OPENAI_DIMENSIONS.get(self._model, 1536)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

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
        return [_to_float_list(item.embedding) for item in response.data]


class VoyageEmbeddingBackend(EmbeddingBackend):
    """Voyage AI ``voyage-3-lite`` backend (512 dims).

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
        return _VOYAGE_DIMENSIONS.get(self._model, 1024)

    @property
    def name(self) -> str:
        return "voyage"

    @property
    def model(self) -> str:
        return self._model

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
        return [_to_float_list(e) for e in result.embeddings]


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
        return _LOCAL_DIMENSIONS.get(self._model_name, 384)

    @property
    def name(self) -> str:
        return "local"

    @property
    def model(self) -> str:
        return self._model_name

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
        # sentence-transformers returns numpy float32 arrays, which json.dumps
        # cannot serialise — convert to plain Python floats.
        return [_to_float_list(e) for e in embeddings]


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
    from iobox.space_config import validate_space_name

    validate_space_name(workspace)  # the name becomes a directory under indexes/
    base = Path(credentials_dir) if credentials_dir else Path.home() / ".iobox"
    path = base / "indexes" / workspace
    path.mkdir(parents=True, exist_ok=True)
    return path / "index.db"


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class ResourceIndex:
    """SQLite-backed vector index for resource embeddings.

    Uses sqlite-vec for ANN search if available; falls back to pure-Python
    cosine similarity when sqlite-vec is not installed. Both paths return
    cosine similarity.

    Args:
        workspace: Workspace name (used for path and scoping queries).
        dimensions: Expected vector size. ``None`` (recommended) takes the
            size from the index metadata, or from the first embedding stored
            in a new index. If given and the index already records a
            different size, :class:`IndexMismatchError` is raised.
        credentials_dir: Base directory for ``~/.iobox/``.
        _conn: Inject a SQLite connection for testing (uses in-memory DB).
    """

    def __init__(
        self,
        workspace: str,
        dimensions: int | None = None,
        credentials_dir: str | None = None,
        _conn: sqlite3.Connection | None = None,
    ) -> None:
        self.workspace = workspace
        self.dimensions: int | None = dimensions
        self._credentials_dir = credentials_dir
        self._conn_override = _conn
        self._conn: sqlite3.Connection | None = None
        self._has_vec: bool = False
        self._vec_available: bool = False

    # ── connection / schema ────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._conn_override is not None:
            conn = self._conn_override
        else:
            db_path = _get_index_path(self.workspace, self._credentials_dir)
            conn = sqlite3.connect(str(db_path))
        try:
            self._setup_tables(conn)
        except BaseException:
            if self._conn_override is None:
                conn.close()
            raise
        self._conn = conn
        return conn

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS index_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

        meta = self._read_meta(conn)
        stored_dims = int(meta["dimensions"]) if meta.get("dimensions") else None
        if stored_dims is None:
            # Legacy index (pre-metadata): infer the size from a stored vector.
            row = conn.execute("SELECT embedding_json FROM resource_embeddings LIMIT 1").fetchone()
            if row:
                stored_dims = len(json.loads(row[0]))
                self._write_meta(conn, dimensions=str(stored_dims))

        if stored_dims is not None:
            if self.dimensions is not None and self.dimensions != stored_dims:
                raise IndexMismatchError(
                    f"Index for workspace {self.workspace!r} stores {stored_dims}-dimension "
                    f"vectors but {self.dimensions} were requested. "
                    "Rebuild it with embed_resources(..., rebuild=True)."
                )
            self.dimensions = stored_dims
        elif self.dimensions is not None:
            self._write_meta(conn, dimensions=str(self.dimensions))

        self._vec_available = self._try_load_vec(conn)
        if self._vec_available and self.dimensions is not None:
            self._setup_vec(conn)

    def _read_meta(self, conn: sqlite3.Connection) -> dict[str, str]:
        return {str(k): str(v) for k, v in conn.execute("SELECT key, value FROM index_meta")}

    def _write_meta(self, conn: sqlite3.Connection, **values: str) -> None:
        conn.executemany(
            "INSERT INTO index_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            list(values.items()),
        )
        conn.commit()

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

    def _setup_vec(self, conn: sqlite3.Connection) -> None:
        """Create (or migrate) the vec0 table and backfill missing rows."""
        meta = self._read_meta(conn)
        try:
            if meta.get("vec_metric") != DISTANCE_METRIC or meta.get("vec_dimensions") != str(
                self.dimensions
            ):
                # Legacy tables used the default L2 metric (or another size):
                # drop and rebuild from the main table.
                conn.execute(f"DROP TABLE IF EXISTS {_VEC_TABLE}")
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {_VEC_TABLE} "
                f"USING vec0(embedding float[{self.dimensions}] "
                f"distance_metric={DISTANCE_METRIC})"
            )
            conn.commit()
            self._write_meta(conn, vec_metric=DISTANCE_METRIC, vec_dimensions=str(self.dimensions))
            self._has_vec = True
        except Exception:
            conn.rollback()
            logger.debug("Failed to create vec0 virtual table; falling back to Python search")
            self._has_vec = False
            return
        self._backfill_vec(conn)

    def _backfill_vec(self, conn: sqlite3.Connection) -> None:
        """Insert vec rows for main rows that have none (e.g. written without sqlite-vec)."""
        rows = conn.execute(
            f"SELECT id, embedding_json FROM resource_embeddings "
            f"WHERE id NOT IN (SELECT rowid FROM {_VEC_TABLE})"
        ).fetchall()
        if not rows:
            return
        added = 0
        try:
            for row_id, embedding_json in rows:
                vec = json.loads(embedding_json)
                if len(vec) != self.dimensions:
                    logger.warning(
                        "Skipping index row %s: %d dimensions, expected %s",
                        row_id,
                        len(vec),
                        self.dimensions,
                    )
                    continue
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
                    (int(row_id), _pack(vec)),
                )
                added += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        logger.info("Backfilled %d vector index row(s)", added)

    def _ensure_dimensions(self, size: int) -> None:
        """Record *size* for a new index, or check it against the stored size."""
        conn = self._get_conn()
        if self.dimensions is None:
            self.dimensions = size
            self._write_meta(conn, dimensions=str(size))
            if self._vec_available:
                self._setup_vec(conn)
        elif size != self.dimensions:
            raise IndexMismatchError(
                f"Embedding has {size} dimensions but the index for workspace "
                f"{self.workspace!r} stores {self.dimensions}-dimension vectors. "
                "It was probably built with a different embedding backend or model — "
                "rebuild it with embed_resources(..., rebuild=True)."
            )

    # ── backend identity ───────────────────────────────────────────────────

    def get_metadata(self) -> dict[str, str]:
        """Return the stored index metadata (backend, model, dimensions, …)."""
        return self._read_meta(self._get_conn())

    def ensure_backend(self, backend_name: str, model: str) -> None:
        """Bind the index to a backend/model, or verify it matches the stored one.

        Raises:
            IndexMismatchError: If the index was built with a different
                backend or model.
        """
        conn = self._get_conn()
        meta = self._read_meta(conn)
        stored_backend = meta.get("backend")
        stored_model = meta.get("model", "")
        if stored_backend is None:
            has_rows = conn.execute("SELECT 1 FROM resource_embeddings LIMIT 1").fetchone()
            if has_rows:
                logger.warning(
                    "Index for workspace %r has no backend metadata (built by an older "
                    "iobox); assuming %s/%s.",
                    self.workspace,
                    backend_name,
                    model,
                )
            self._write_meta(conn, backend=backend_name, model=model)
            return
        if stored_backend != backend_name or stored_model != model:
            raise IndexMismatchError(
                f"Index for workspace {self.workspace!r} was built with backend "
                f"{stored_backend!r} (model {stored_model!r}) but {backend_name!r} "
                f"(model {model!r}) was requested. Embeddings from different models "
                "are not comparable: query with the original backend, or rebuild the "
                "index with embed_resources(..., rebuild=True)."
            )

    def reset(self) -> None:
        """Delete all embeddings and metadata so the index can be rebuilt."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM resource_embeddings")
            conn.execute("DELETE FROM index_meta")
            conn.execute(f"DROP TABLE IF EXISTS {_VEC_TABLE}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        self.dimensions = None
        self._has_vec = False

    # ── read / write ───────────────────────────────────────────────────────

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
        """Store or update an embedding for a resource.

        The main row and the sqlite-vec row are written in one transaction, so
        a failure never leaves a fresh content hash pointing at a stale vector.
        """
        vec = _to_float_list(embedding)
        self._ensure_dimensions(len(vec))
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        embedding_json = json.dumps(vec)

        try:
            existing = conn.execute(
                "SELECT id FROM resource_embeddings WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()

            if existing:
                row_id: int = int(existing[0])
                conn.execute(
                    """UPDATE resource_embeddings
                       SET resource_type = ?, provider_id = ?, content_hash = ?,
                           embedding_json = ?, indexed_at = ?
                       WHERE resource_id = ?""",
                    (resource_type, provider_id, content_hash, embedding_json, now, resource_id),
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

            if self._has_vec and row_id:
                conn.execute(f"DELETE FROM {_VEC_TABLE} WHERE rowid = ?", (row_id,))
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
                    (row_id, _pack(vec)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_types: list[str] | None = None,
    ) -> list[tuple[str, str, str, float]]:
        """Return (resource_id, resource_type, provider_id, similarity) tuples.

        Similarity is cosine similarity (higher = more similar, 1.0 = same
        direction). Results are sorted descending by similarity. Both the
        sqlite-vec and pure-Python paths produce the same scores.

        Raises:
            IndexMismatchError: If the query vector's size differs from the
                index's.
        """
        conn = self._get_conn()
        if self.dimensions is None:
            return []  # nothing has been indexed yet
        query = _to_float_list(query_embedding)
        if len(query) != self.dimensions:
            raise IndexMismatchError(
                f"Query embedding has {len(query)} dimensions but the index for workspace "
                f"{self.workspace!r} stores {self.dimensions}-dimension vectors. Query with "
                "the backend the index was built with, or rebuild it."
            )
        if self._has_vec:
            return self._search_vec(conn, query, top_k, filter_types)
        return self._search_python(conn, query, top_k, filter_types)

    def _search_vec(
        self,
        conn: sqlite3.Connection,
        query_embedding: list[float],
        top_k: int,
        filter_types: list[str] | None,
    ) -> list[tuple[str, str, str, float]]:
        blob = _pack(query_embedding)
        total = self.count()
        if total == 0 or top_k <= 0:
            return []
        type_set = set(filter_types) if filter_types else None
        fetch_k = min(top_k * 3 if type_set else top_k, total, _VEC_MAX_K)
        while True:
            rows = conn.execute(
                f"""SELECT r.resource_id, r.resource_type, r.provider_id, v.distance
                    FROM {_VEC_TABLE} v
                    JOIN resource_embeddings r ON r.id = v.rowid
                    WHERE v.embedding MATCH ?
                      AND k = ?
                    ORDER BY v.distance""",
                (blob, fetch_k),
            ).fetchall()
            results = [
                (str(rid), str(rt), str(pid), 1.0 - float(dist))
                for rid, rt, pid, dist in rows
                if type_set is None or rt in type_set
            ]
            # With a type filter, widen the KNN window until we have enough
            # matches or have scanned everything sqlite-vec allows.
            if len(results) >= top_k or fetch_k >= min(total, _VEC_MAX_K):
                return results[:top_k]
            fetch_k = min(fetch_k * 2, total, _VEC_MAX_K)

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
            scored.append((resource_id, resource_type, provider_id, sim))

        scored.sort(key=lambda x: x[3], reverse=True)
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


def _backend_key(backend: EmbeddingBackend | None) -> str:
    if backend is None:
        return ""
    return f"{backend.name}:{backend.model}"


def _content_hash(resource: Resource, backend_key: str = "") -> str:
    """Return a 16-char hex hash of the backend identity + resource text + modified_at.

    Including the backend identity means switching backend/model invalidates
    every stored hash, so nothing is skipped as "unchanged" after a rebuild.
    """
    text = _resource_to_text(resource)
    modified = str(resource.get("modified_at") or "")
    prefix = f"{backend_key}\x00" if backend_key else ""
    digest = hashlib.sha256(f"{prefix}{text}{modified}".encode()).hexdigest()
    return digest[:16]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [-1, 1]. Returns 0.0 for zero vectors."""
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
    rebuild: bool = False,
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
        rebuild: Discard the existing index (all entries and metadata) before
            embedding. Required when switching backend or model.
        _index: Inject a ``ResourceIndex`` for testing.

    Returns:
        Number of resources newly embedded or updated.

    Raises:
        IndexMismatchError: If the index was built with a different backend,
            model, or vector size and *rebuild* is False.
    """
    if not resources and not rebuild:
        return 0
    if backend is None:
        backend = get_backend("openai")

    index = _index if _index is not None else ResourceIndex(workspace, None, credentials_dir)
    try:
        if rebuild:
            index.reset()
        index.ensure_backend(backend.name, backend.model)
        backend_key = _backend_key(backend)

        to_embed: list[tuple[Resource, str]] = []
        for resource in resources:
            resource_id = str(resource.get("id") or "")
            if not resource_id:
                continue
            current_hash = _content_hash(resource, backend_key)
            if index.get_content_hash(resource_id) != current_hash:
                to_embed.append((resource, current_hash))

        count = 0
        for batch_start in range(0, len(to_embed), batch_size):
            batch = to_embed[batch_start : batch_start + batch_size]
            texts = [_resource_to_text(r) for r, _ in batch]
            try:
                embeddings = backend.embed(texts)
            except Exception as exc:
                logger.error("Embedding batch failed: %s", exc)
                continue
            if len(embeddings) != len(batch):
                logger.error(
                    "Embedding batch returned %d vectors for %d texts; skipping batch",
                    len(embeddings),
                    len(batch),
                )
                continue
            for (resource, content_hash), embedding in zip(batch, embeddings, strict=True):
                index.upsert(
                    resource_id=str(resource.get("id") or ""),
                    resource_type=str(resource.get("resource_type") or ""),
                    provider_id=str(resource.get("provider_id") or ""),
                    embedding=embedding,
                    content_hash=content_hash,
                )
                count += 1
        return count
    finally:
        if _index is None:
            index.close()


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
        ``score`` (cosine similarity clamped to 0–1, higher is more similar).
        Empty list if the index is empty or the query embedding fails.

    Raises:
        IndexMismatchError: If the index was built with a different backend,
            model, or vector size.
    """
    if backend is None:
        backend = get_backend("openai")

    index = _index if _index is not None else ResourceIndex(workspace, None, credentials_dir)
    try:
        if index.count() == 0:
            return []
        index.ensure_backend(backend.name, backend.model)

        try:
            query_embeddings = backend.embed([query])
        except Exception as exc:
            logger.error("Failed to embed query: %s", exc)
            return []

        results = index.search(query_embeddings[0], top_k=top_k, filter_types=types)
    finally:
        if _index is None:
            index.close()

    return [
        {
            "id": resource_id,
            "resource_type": resource_type,
            "provider_id": provider_id,
            "score": round(min(1.0, max(0.0, similarity)), 4),
        }
        for resource_id, resource_type, provider_id, similarity in results
    ]
