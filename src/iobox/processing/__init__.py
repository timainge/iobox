"""
iobox processing package.

Provides unified resource → markdown converters for all resource types:
Event, File, and Email (via adapter to existing markdown_converter).
Also provides embedding generation and semantic search via embed.py.
"""

from iobox.processing.embed import (
    EmbeddingBackend,
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
    "LocalEmbeddingBackend",
    "OpenAIEmbeddingBackend",
    "ResourceIndex",
    "VoyageEmbeddingBackend",
    "embed_resources",
    "get_backend",
    "semantic_search",
]
