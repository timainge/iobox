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


def _mock_backend(dims: int = 4, value: float = 0.5) -> EmbeddingBackend:
    """Return a mock EmbeddingBackend that returns a fixed vector."""

    class _MockBackend(EmbeddingBackend):
        @property
        def dimensions(self) -> int:
            return dims

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
        backend = VoyageEmbeddingBackend()
        assert backend.dimensions == 1024

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
        # r1 should come first (lower distance = higher similarity)
        assert results[0][0] == "r1"
        assert results[0][3] < results[1][3]  # lower distance = closer match

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
