"""Tests for the pluggable vector-store backend factory."""

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from agentic.app.config import EmbeddingConfig, VectorStoreConfig
from agentic.app.vectorstore_factory import (
    VectorStoreBackendError,
    get_embeddings,
    get_vector_store,
)


class FakeEmbeddings(Embeddings):
    """Deterministic embeddings so tests don't need a real model/network call."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


def test_get_vector_store_in_memory_backend_returns_in_memory_vector_store():
    config = VectorStoreConfig(backend="in_memory")
    store = get_vector_store(config, embeddings=FakeEmbeddings())
    assert isinstance(store, InMemoryVectorStore)


def test_get_vector_store_unknown_backend_raises():
    config = VectorStoreConfig(backend="does_not_exist")
    with pytest.raises(VectorStoreBackendError):
        get_vector_store(config, embeddings=FakeEmbeddings())


def test_get_vector_store_falls_back_to_in_memory_on_missing_dependency(monkeypatch):
    """A backend whose optional dependency isn't installed should degrade to
    in_memory rather than crash, per the factory's documented behaviour."""
    import agentic.app.vectorstore_factory as factory

    def _boom(*_args, **_kwargs):
        raise VectorStoreBackendError("dependency not installed")

    monkeypatch.setitem(factory._BACKEND_BUILDERS, "chroma", _boom)

    config = VectorStoreConfig(backend="chroma")
    store = get_vector_store(config, embeddings=FakeEmbeddings())
    assert isinstance(store, InMemoryVectorStore)


def test_get_embeddings_unknown_provider_raises():
    config = EmbeddingConfig(provider="does_not_exist")
    with pytest.raises(VectorStoreBackendError):
        get_embeddings(config)

