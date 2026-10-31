"""
iobox processing package.

Provides unified resource → markdown converters for all resource types:
Event, File, and Email (via adapter to existing markdown_converter).
Also provides embedding generation and semantic search via embed.py.
"""

from iobox.processing.embed import (
    EmbeddingBackend,
    IndexMismatchError,
    LocalEmbeddingBackend,
    OpenAIEmbeddingBackend,
    ResourceIndex,
    VoyageEmbeddingBackend,
    embed_resources,
    get_backend,
    semantic_search,
)

__all__ = [
    "EmbeddingBackend",
    "IndexMismatchError",
    "LocalEmbeddingBackend",
    "OpenAIEmbeddingBackend",
    "ResourceIndex",
    "VoyageEmbeddingBackend",
    "embed_resources",
    "get_backend",
    "semantic_search",
]
