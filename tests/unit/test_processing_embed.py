"""Unit tests for iobox.processing.embed.

All tests use injected in-memory connections (_conn=) and mock backends
(_client_fn=) — no filesystem access, no live API calls, no sqlite-vec required.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from iobox.processing.embed import (
    EmbeddingBackend,
    IndexMismatchError,
    LocalEmbeddingBackend,
    OpenAIEmbeddingBackend,
    ResourceIndex,
    VoyageEmbeddingBackend,
    _content_hash,
    _cosine_similarity,
    _resource_to_text,
    embed_resources,
    get_backend,
    semantic_search,
)
from iobox.providers.base import Resource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resource(
    id: str = "r1",
    resource_type: str = "email",
    title: str = "Test Email",
    body: str = "Hello world",
) -> Resource:
    return Resource(  # type: ignore[call-arg]
        id=id,
        provider_id="gmail",
        resource_type=resource_type,  # type: ignore[arg-type]
        title=title,
        created_at="2026-01-01T00:00:00Z",
        modified_at="2026-01-01T00:00:00Z",
        url=None,
    )


def _make_conn() -> sqlite3.Connection:
    """Return a fresh in-memory SQLite connection."""
    return sqlite3.connect(":memory:")


def _make_index(dimensions: int = 4, conn: sqlite3.Connection | None = None) -> ResourceIndex:
    if conn is None:
        conn = _make_conn()
    return ResourceIndex("test-ws", dimensions=dimensions, _conn=conn)


def _fake_embedding(dims: int = 4, value: float = 0.5) -> list[float]:
    return [value] * dims


def _mock_backend(
    dims: int = 4,
    value: float = 0.5,
    name: str = "mock",
    model: str = "mock-1",
    declared_dims: int | None = None,
) -> EmbeddingBackend:
    """Return a mock EmbeddingBackend that returns a fixed vector."""

    class _MockBackend(EmbeddingBackend):
        @property
        def dimensions(self) -> int:
            return declared_dims if declared_dims is not None else dims

        @property
        def name(self) -> str:
            return name

        @property
        def model(self) -> str:
            return model

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [_fake_embedding(dims, value) for _ in texts]

    return _MockBackend()


# ---------------------------------------------------------------------------
# _resource_to_text
# ---------------------------------------------------------------------------


class TestResourceToText:
    def test_includes_title(self) -> None:
        r = _make_resource(title="Budget Report")
        text = _resource_to_text(r)
        assert "Budget Report" in text

    def test_includes_resource_type(self) -> None:
        r = _make_resource(resource_type="event")
        text = _resource_to_text(r)
        assert "event" in text

    def test_includes_body_if_present(self) -> None:
        r = _make_resource()
        r["body"] = "This is the body"  # type: ignore[typeddict-unknown-key]
        text = _resource_to_text(r)
        assert "This is the body" in text


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_returns_16_hex_chars(self) -> None:
        r = _make_resource()
        h = _content_hash(r)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_resource_same_hash(self) -> None:
        r1 = _make_resource()
        r2 = _make_resource()
        assert _content_hash(r1) == _content_hash(r2)

    def test_different_title_different_hash(self) -> None:
        r1 = _make_resource(title="Alpha")
        r2 = _make_resource(title="Beta")
        assert _content_hash(r1) != _content_hash(r2)


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 0.0, 0.0, 0.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_zero_vector_returns_zero(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# EmbeddingBackend implementations
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingBackend:
    def test_dimensions(self) -> None:
        backend = OpenAIEmbeddingBackend()
        assert backend.dimensions == 1536

    def test_embed_via_client_fn(self) -> None:
        fake_embedding = [0.1] * 1536
        mock_item = MagicMock()
        mock_item.embedding = fake_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_item]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        backend = OpenAIEmbeddingBackend(_client_fn=lambda: mock_client)
        result = backend.embed(["hello"])
        assert result == [fake_embedding]
        mock_client.embeddings.create.assert_called_once_with(
            input=["hello"], model="text-embedding-3-small"
        )

    def test_embed_multiple_texts(self) -> None:
        mock_items = [MagicMock(embedding=[float(i)] * 1536) for i in range(3)]
        mock_response = MagicMock()
        mock_response.data = mock_items
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        backend = OpenAIEmbeddingBackend(_client_fn=lambda: mock_client)
        result = backend.embed(["a", "b", "c"])
        assert len(result) == 3


class TestVoyageEmbeddingBackend:
    def test_dimensions(self) -> None:
        # PROC-03: voyage-3-lite produces 512-dimension vectors
        backend = VoyageEmbeddingBackend()
        assert backend.dimensions == 512

    def test_dimensions_other_model(self) -> None:
        assert VoyageEmbeddingBackend(model="voyage-3").dimensions == 1024

    def test_name_and_model(self) -> None:
        backend = VoyageEmbeddingBackend()
        assert backend.name == "voyage"
        assert backend.model == "voyage-3-lite"

    def test_embed_via_client_fn(self) -> None:
        fake_embeddings = [[0.2] * 1024]
        mock_result = MagicMock()
        mock_result.embeddings = fake_embeddings
        mock_client = MagicMock()
        mock_client.embed.return_value = mock_result

        backend = VoyageEmbeddingBackend(_client_fn=lambda: mock_client)
        result = backend.embed(["hello"])
        assert result == fake_embeddings


class TestLocalEmbeddingBackend:
    def test_dimensions(self) -> None:
        backend = LocalEmbeddingBackend()
        assert backend.dimensions == 384

    def test_embed_via_model_fn(self) -> None:
        # Simulate numpy-like array: list of lists works since embed() does list(e) for e in
        fake_arr = [[0.3] * 384]
        mock_model = MagicMock()
        mock_model.encode.return_value = fake_arr

        backend = LocalEmbeddingBackend(_model_fn=lambda: mock_model)
        result = backend.embed(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 384
        mock_model.encode.assert_called_once_with(["hello"])


# ---------------------------------------------------------------------------
# get_backend factory
# ---------------------------------------------------------------------------


class TestGetBackend:
    def test_openai_backend(self) -> None:
        backend = get_backend("openai")
        assert isinstance(backend, OpenAIEmbeddingBackend)

    def test_voyage_backend(self) -> None:
        backend = get_backend("voyage")
        assert isinstance(backend, VoyageEmbeddingBackend)

    def test_local_backend(self) -> None:
        backend = get_backend("local")
        assert isinstance(backend, LocalEmbeddingBackend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("nonexistent")

    def test_model_override(self) -> None:
        backend = get_backend("openai", model="text-embedding-ada-002")
        assert isinstance(backend, OpenAIEmbeddingBackend)
        assert backend._model == "text-embedding-ada-002"


# ---------------------------------------------------------------------------
# ResourceIndex
# ---------------------------------------------------------------------------


class TestResourceIndex:
    def test_init_creates_tables(self) -> None:
        idx = _make_index()
        conn = idx._get_conn()  # triggers lazy setup
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "resource_embeddings" in tables

    def test_upsert_and_retrieve(self) -> None:
        idx = _make_index(dimensions=4)
        emb = [0.1, 0.2, 0.3, 0.4]
        idx.upsert("r1", "email", "gmail", emb, "hash1")

        stored_hash = idx.get_content_hash("r1")
        assert stored_hash == "hash1"

    def test_get_content_hash_missing_returns_none(self) -> None:
        idx = _make_index()
        assert idx.get_content_hash("nonexistent") is None

    def test_upsert_idempotent(self) -> None:
        idx = _make_index(dimensions=4)
        emb = [0.1, 0.2, 0.3, 0.4]
        idx.upsert("r1", "email", "gmail", emb, "hash1")
        idx.upsert("r1", "email", "gmail", [0.9, 0.9, 0.9, 0.9], "hash2")

        stored_hash = idx.get_content_hash("r1")
        assert stored_hash == "hash2"

    def test_search_returns_ranked_results(self) -> None:
        idx = _make_index(dimensions=4)
        # r1 is very similar to query [1,0,0,0]
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
        # r2 is orthogonal
        idx.upsert("r2", "event", "gcal", [0.0, 1.0, 0.0, 0.0], "h2")

        query = [1.0, 0.0, 0.0, 0.0]
        results = idx.search(query, top_k=2)

        assert len(results) == 2
        # r1 should come first (higher cosine similarity = closer match)
        assert results[0][0] == "r1"
        assert results[0][3] > results[1][3]
        assert results[0][3] == pytest.approx(1.0)
        assert results[1][3] == pytest.approx(0.0)

    def test_search_filter_by_type(self) -> None:
        idx = _make_index(dimensions=4)
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
        idx.upsert("r2", "event", "gcal", [1.0, 0.0, 0.0, 0.0], "h2")

        results = idx.search([1.0, 0.0, 0.0, 0.0], top_k=10, filter_types=["event"])
        assert all(row[1] == "event" for row in results)

    def test_search_empty_index(self) -> None:
        idx = _make_index()
        results = idx.search([1.0, 0.0, 0.0, 0.0], top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# embed_resources
# ---------------------------------------------------------------------------


class TestEmbedResources:
    def test_embeds_new_resources(self) -> None:
        resources = [_make_resource("r1"), _make_resource("r2")]
        backend = _mock_backend(dims=4)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)

        count = embed_resources(resources, "test-ws", backend=backend, _index=idx)
        assert count == 2

    def test_skips_unchanged_resources(self) -> None:
        resource = _make_resource("r1")
        backend = _mock_backend(dims=4)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)

        # First embed
        embed_resources([resource], "test-ws", backend=backend, _index=idx)
        # Second embed — should skip (same content hash)
        count = embed_resources([resource], "test-ws", backend=backend, _index=idx)
        assert count == 0

    def test_re_embeds_changed_resources(self) -> None:
        resource = _make_resource("r1", title="Original")
        backend = _mock_backend(dims=4)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)

        embed_resources([resource], "test-ws", backend=backend, _index=idx)

        # Mutate the resource so its hash changes
        resource["title"] = "Updated"  # type: ignore[typeddict-unknown-key]
        count = embed_resources([resource], "test-ws", backend=backend, _index=idx)
        assert count == 1

    def test_returns_zero_for_empty_list(self) -> None:
        backend = _mock_backend()
        idx = _make_index()
        count = embed_resources([], "test-ws", backend=backend, _index=idx)
        assert count == 0


# ---------------------------------------------------------------------------
# semantic_search
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    def test_returns_ranked_stubs(self) -> None:
        backend = _mock_backend(dims=4, value=1.0)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)

        # Pre-populate index
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
        idx.upsert("r2", "event", "gcal", [0.0, 1.0, 0.0, 0.0], "h2")

        results = semantic_search(
            "test query",
            "test-ws",
            backend=backend,
            top_k=10,
            _index=idx,
        )

        assert len(results) == 2
        assert all("id" in r for r in results)
        assert all("resource_type" in r for r in results)
        assert all("score" in r for r in results)

    def test_filter_by_types(self) -> None:
        backend = _mock_backend(dims=4)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)

        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
        idx.upsert("r2", "event", "gcal", [1.0, 0.0, 0.0, 0.0], "h2")

        results = semantic_search(
            "test",
            "test-ws",
            types=["email"],
            backend=backend,
            _index=idx,
        )
        assert all(r["resource_type"] == "email" for r in results)

    def test_empty_index_returns_empty(self) -> None:
        backend = _mock_backend(dims=4)
        idx = _make_index(dimensions=4)
        results = semantic_search("test", "test-ws", backend=backend, _index=idx)
        assert results == []

    def test_top_k_limits_results(self) -> None:
        backend = _mock_backend(dims=4)
        conn = _make_conn()
        idx = _make_index(dimensions=4, conn=conn)
        for i in range(10):
            emb = [float(i % 2), float(1 - i % 2), 0.0, 0.0]
            idx.upsert(f"r{i}", "email", "gmail", emb, f"h{i}")

        results = semantic_search("test", "test-ws", backend=backend, top_k=3, _index=idx)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# PROC-02: plain Python floats
# ---------------------------------------------------------------------------


class _F32:
    """Stand-in for numpy.float32: convertible with float() but not JSON-serialisable."""

    def __init__(self, v: float) -> None:
        self.v = v

    def __float__(self) -> float:
        return self.v


class _FakeArray(list):
    def tolist(self) -> list[float]:
        return [float(x) for x in self]


class TestPlainFloats:
    def test_local_backend_returns_python_floats(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.return_value = [[_F32(0.1), _F32(0.2)]]
        result = LocalEmbeddingBackend(_model_fn=lambda: mock_model).embed(["x"])
        assert result == [[0.1, 0.2]]
        assert all(type(x) is float for x in result[0])

    def test_local_backend_handles_tolist_arrays(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.return_value = [_FakeArray([_F32(0.5), _F32(0.25)])]
        result = LocalEmbeddingBackend(_model_fn=lambda: mock_model).embed(["x"])
        assert result == [[0.5, 0.25]]

    def test_local_backend_numpy_float32(self) -> None:
        np = pytest.importorskip("numpy")
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
        backend = LocalEmbeddingBackend(_model_fn=lambda: mock_model)
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        assert embed_resources([_make_resource("r1")], "test-ws", backend=backend, _index=idx) == 1

    def test_local_backend_end_to_end(self) -> None:
        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda texts: [[_F32(0.5)] * 4 for _ in texts]
        backend = LocalEmbeddingBackend(_model_fn=lambda: mock_model)
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        n = embed_resources([_make_resource("r1")], "test-ws", backend=backend, _index=idx)
        assert n == 1
        hits = semantic_search("q", "test-ws", backend=backend, _index=idx)
        assert hits[0]["id"] == "r1"

    def test_upsert_accepts_non_float_numbers(self) -> None:
        idx = _make_index(dimensions=2)
        idx.upsert("r1", "email", "gmail", [_F32(1.0), _F32(0.0)], "h")  # type: ignore[list-item]
        assert idx.get_content_hash("r1") == "h"


# ---------------------------------------------------------------------------
# PROC-01: backend/model/dimension metadata
# ---------------------------------------------------------------------------


class TestIndexMetadata:
    def test_records_backend_and_dimensions_from_first_embedding(self) -> None:
        backend = _mock_backend(dims=4, declared_dims=999)
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        embed_resources([_make_resource("r1")], "test-ws", backend=backend, _index=idx)
        meta = idx.get_metadata()
        assert meta["backend"] == "mock"
        assert meta["model"] == "mock-1"
        assert meta["dimensions"] == "4"
        assert idx.dimensions == 4

    def test_different_backend_raises(self) -> None:
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        embed_resources([_make_resource("r1")], "test-ws", backend=_mock_backend(), _index=idx)
        other = _mock_backend(name="other")
        with pytest.raises(IndexMismatchError, match="rebuild=True"):
            embed_resources([_make_resource("r2")], "test-ws", backend=other, _index=idx)

    def test_different_model_raises(self) -> None:
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        embed_resources([_make_resource("r1")], "test-ws", backend=_mock_backend(), _index=idx)
        with pytest.raises(IndexMismatchError):
            semantic_search("q", "test-ws", backend=_mock_backend(model="mock-2"), _index=idx)

    def test_rebuild_switches_backend(self) -> None:
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        embed_resources(
            [_make_resource("r1"), _make_resource("r2")],
            "test-ws",
            backend=_mock_backend(dims=4),
            _index=idx,
        )
        other = _mock_backend(dims=8, name="other", model="m")
        n = embed_resources(
            [_make_resource("r1")], "test-ws", backend=other, _index=idx, rebuild=True
        )
        assert n == 1
        assert idx.count() == 1
        assert idx.get_metadata()["backend"] == "other"
        assert idx.dimensions == 8
        assert semantic_search("q", "test-ws", backend=other, _index=idx)[0]["id"] == "r1"

    def test_wrong_dimension_embedding_raises(self) -> None:
        idx = _make_index(dimensions=4)
        with pytest.raises(IndexMismatchError):
            idx.upsert("r1", "email", "gmail", [1.0, 0.0], "h")

    def test_wrong_dimension_query_raises(self) -> None:
        idx = _make_index(dimensions=4)
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h")
        with pytest.raises(IndexMismatchError):
            idx.search([1.0, 0.0])

    def test_hash_depends_on_backend(self) -> None:
        r = _make_resource("r1")
        assert _content_hash(r, "openai:a") != _content_hash(r, "local:b")
        assert _content_hash(r) == _content_hash(r, "")

    def test_metadata_persists_across_reopen(self, tmp_path) -> None:
        backend = _mock_backend(dims=4)
        embed_resources(
            [_make_resource("r1")], "ws", backend=backend, credentials_dir=str(tmp_path)
        )
        # Reopen from disk: same backend works, different one is rejected.
        hits = semantic_search("q", "ws", backend=backend, credentials_dir=str(tmp_path))
        assert [h["id"] for h in hits] == ["r1"]
        with pytest.raises(IndexMismatchError):
            semantic_search(
                "q", "ws", backend=_mock_backend(dims=8, name="x"), credentials_dir=str(tmp_path)
            )

    def test_explicit_dimensions_mismatch_on_open(self, tmp_path) -> None:
        idx = ResourceIndex("ws", None, str(tmp_path))
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h")
        idx.close()
        with pytest.raises(IndexMismatchError):
            ResourceIndex("ws", 8, str(tmp_path)).count()

    def test_legacy_index_without_metadata(self) -> None:
        conn = _make_conn()
        conn.execute(
            """CREATE TABLE resource_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, resource_id TEXT UNIQUE NOT NULL,
                workspace TEXT NOT NULL, resource_type TEXT NOT NULL,
                provider_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                embedding_json TEXT NOT NULL, indexed_at TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO resource_embeddings VALUES (1,'r1','test-ws','email','gmail','old',"
            "'[1.0, 0.0, 0.0, 0.0]','2026-01-01')"
        )
        conn.commit()
        idx = ResourceIndex("test-ws", None, _conn=conn)
        assert idx.dimensions is None
        assert idx.count() == 1
        assert idx.dimensions == 4  # inferred from stored vector
        backend = _mock_backend(dims=4, value=1.0)
        hits = semantic_search("q", "test-ws", backend=backend, _index=idx)
        assert hits[0]["id"] == "r1"
        assert idx.get_metadata()["backend"] == "mock"
        # The legacy hash didn't include the backend, so the row is re-embedded.
        assert embed_resources([_make_resource("r1")], "test-ws", backend=backend, _index=idx) == 1

    def test_empty_index_search_with_any_backend(self) -> None:
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        assert semantic_search("q", "test-ws", backend=_mock_backend(), _index=idx) == []


# ---------------------------------------------------------------------------
# PROC-04: transactional writes, backfill, partial failure
# ---------------------------------------------------------------------------


class TestIndexWrites:
    def test_vec_write_failure_rolls_back_main_row(self) -> None:
        idx = _make_index(dimensions=4)
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "old")
        # Simulate a failing vec write (table missing) — the main-row update
        # must be rolled back so the stale hash is not recorded as current.
        idx._get_conn().execute("DROP TABLE IF EXISTS resource_embeddings_vss")
        idx._has_vec = True
        with pytest.raises(sqlite3.OperationalError):
            idx.upsert("r1", "email", "gmail", [0.0, 1.0, 0.0, 0.0], "new")
        idx._has_vec = False
        assert idx.get_content_hash("r1") == "old"

    def test_batch_length_mismatch_is_skipped(self) -> None:
        class _Short(EmbeddingBackend):
            @property
            def dimensions(self) -> int:
                return 4

            def embed(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0, 0.0]]  # one vector regardless of input

        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        n = embed_resources(
            [_make_resource("r1"), _make_resource("r2")], "test-ws", backend=_Short(), _index=idx
        )
        assert n == 0
        assert idx.count() == 0

    def test_failed_batch_not_recorded(self) -> None:
        class _Boom(EmbeddingBackend):
            @property
            def dimensions(self) -> int:
                return 4

            def embed(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("api down")

        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        assert embed_resources([_make_resource("r1")], "test-ws", backend=_Boom(), _index=idx) == 0
        assert idx.get_content_hash("r1") is None

    def test_backfills_rows_written_without_sqlite_vec(self, tmp_path) -> None:
        pytest.importorskip("sqlite_vec")
        from unittest.mock import patch

        with patch.object(ResourceIndex, "_try_load_vec", return_value=False):
            idx = ResourceIndex("ws", None, str(tmp_path))
            idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
            idx.upsert("r2", "email", "gmail", [0.0, 1.0, 0.0, 0.0], "h2")
            idx.close()

        idx = ResourceIndex("ws", None, str(tmp_path))
        conn = idx._get_conn()
        assert idx._has_vec
        n_vec = conn.execute("SELECT COUNT(*) FROM resource_embeddings_vss").fetchone()[0]
        assert n_vec == 2
        assert [r[0] for r in idx.search([1.0, 0.0, 0.0, 0.0], top_k=2)] == ["r1", "r2"]
        idx.close()

    def test_migrates_legacy_l2_vec_table(self, tmp_path) -> None:
        sqlite_vec = pytest.importorskip("sqlite_vec")
        db = tmp_path / "indexes" / "ws" / "index.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.execute("CREATE VIRTUAL TABLE resource_embeddings_vss USING vec0(embedding float[4])")
        conn.commit()
        conn.close()

        idx = ResourceIndex("ws", None, str(tmp_path))
        idx.upsert("r1", "email", "gmail", [1.0, 0.0, 0.0, 0.0], "h1")
        meta = idx.get_metadata()
        assert meta["vec_metric"] == "cosine"
        sql = (
            idx._get_conn()
            .execute("SELECT sql FROM sqlite_master WHERE name = 'resource_embeddings_vss'")
            .fetchone()[0]
        )
        assert "distance_metric=cosine" in sql
        idx.close()

    def test_close_called_on_error(self, tmp_path) -> None:
        from unittest.mock import patch

        backend = _mock_backend(dims=4)
        embed_resources(
            [_make_resource("r1")], "ws", backend=backend, credentials_dir=str(tmp_path)
        )
        with (
            patch.object(ResourceIndex, "search", side_effect=RuntimeError("boom")),
            patch.object(ResourceIndex, "close", autospec=True) as close,
            pytest.raises(RuntimeError),
        ):
            semantic_search("q", "ws", backend=backend, credentials_dir=str(tmp_path))
        close.assert_called_once()


# ---------------------------------------------------------------------------
# PROC-05: consistent cosine scores
# ---------------------------------------------------------------------------


class TestCosineScores:
    def _populate(self, idx: ResourceIndex) -> None:
        idx.upsert("same", "email", "gmail", [2.0, 0.0, 0.0, 0.0], "h1")
        idx.upsert("diag", "email", "gmail", [1.0, 1.0, 0.0, 0.0], "h2")
        idx.upsert("orth", "event", "gcal", [0.0, 0.0, 3.0, 0.0], "h3")

    def test_python_path_scores_are_cosine_similarity(self) -> None:
        backend = _mock_backend(dims=4, value=0.0)
        backend.embed = lambda texts: [[1.0, 0.0, 0.0, 0.0] for _ in texts]  # type: ignore[method-assign]
        idx = _make_index(dimensions=None)  # type: ignore[arg-type]
        idx._try_load_vec = lambda conn: False  # type: ignore[method-assign]
        self._populate(idx)
        hits = semantic_search("q", "test-ws", backend=backend, _index=idx)
        scores = {h["id"]: h["score"] for h in hits}
        assert scores["same"] == pytest.approx(1.0)
        assert scores["diag"] == pytest.approx(0.7071, abs=1e-4)
        assert scores["orth"] == pytest.approx(0.0)
        assert [h["id"] for h in hits] == ["same", "diag", "orth"]

    def test_vec_and_python_paths_agree(self, tmp_path) -> None:
        pytest.importorskip("sqlite_vec")
        from unittest.mock import patch

        query = [1.0, 0.0, 0.0, 0.0]
        vec_idx = ResourceIndex("a", None, str(tmp_path))
        self._populate(vec_idx)
        assert vec_idx._has_vec
        vec_results = vec_idx.search(query, top_k=3)
        vec_idx.close()

        with patch.object(ResourceIndex, "_try_load_vec", return_value=False):
            py_idx = ResourceIndex("b", None, str(tmp_path))
            self._populate(py_idx)
            py_results = py_idx.search(query, top_k=3)
            py_idx.close()

        assert [r[0] for r in vec_results] == [r[0] for r in py_results]
        for v, p in zip(vec_results, py_results, strict=True):
            assert v[3] == pytest.approx(p[3], abs=1e-5)

    def test_vec_type_filter_returns_enough_results(self, tmp_path) -> None:
        pytest.importorskip("sqlite_vec")
        idx = ResourceIndex("ws", None, str(tmp_path))
        for i in range(10):
            idx.upsert(f"e{i}", "email", "gmail", [1.0, 0.01 * i, 0.0, 0.0], f"h{i}")
        idx.upsert("ev", "event", "gcal", [0.0, 1.0, 0.0, 0.0], "hx")
        results = idx.search([1.0, 0.0, 0.0, 0.0], top_k=1, filter_types=["event"])
        assert [r[0] for r in results] == ["ev"]
        idx.close()
