"""Factory for pluggable `langchain_core` vector-store backends.

This module is the single extension point for adding new vector-database
backends to `agentic`: implement a `_build_<backend>` function that returns
a `langchain_core.vectorstores.VectorStore` and register it in
`_BACKEND_BUILDERS`. Backend selection is entirely config-driven (see
`agentic.app.config.VectorStoreConfig`) — no code changes are needed
elsewhere to switch backends.

Every backend-specific import is lazy/optional so that installing
`agentic` without e.g. `langchain-chroma` still works as long as that
backend isn't selected in config.
"""

import logging
from typing import Callable

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from agentic.app.config import EmbeddingConfig, VectorStoreConfig

logger = logging.getLogger(__name__)


class VectorStoreBackendError(RuntimeError):
    """Raised when a configured vector-store/embedding backend can't be built."""


def get_embeddings(config: EmbeddingConfig) -> Embeddings:
    """Build the `Embeddings` implementation selected by `config.provider`."""
    if config.provider == "huggingface":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as e:
            raise VectorStoreBackendError(
                "provider 'huggingface' requires the 'langchain-huggingface' and "
                "'sentence-transformers' packages. Install them or switch "
                "vector_store.embedding.provider to 'openai'."
            ) from e
        return HuggingFaceEmbeddings(model_name=config.model)

    if config.provider == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as e:
            raise VectorStoreBackendError(
                "provider 'openai' requires the 'langchain-openai' package."
            ) from e
        api_key = str(config.api_key) if config.api_key is not None else None
        return OpenAIEmbeddings(
            model=config.model, base_url=config.base_url, api_key=api_key
        )

    raise VectorStoreBackendError(f"Unknown embeddings provider: {config.provider!r}")


def _build_in_memory(config: VectorStoreConfig, embeddings: Embeddings) -> VectorStore:
    return InMemoryVectorStore(embedding=embeddings)


def _build_chroma(config: VectorStoreConfig, embeddings: Embeddings) -> VectorStore:
    try:
        from langchain_chroma import Chroma
    except ImportError as e:
        raise VectorStoreBackendError(
            "backend 'chroma' requires the 'langchain-chroma' package."
        ) from e
    return Chroma(
        collection_name=config.collection_name,
        embedding_function=embeddings,
        persist_directory=config.persist_directory,
    )


def _build_elasticsearch(config: VectorStoreConfig, embeddings: Embeddings) -> VectorStore:
    try:
        from langchain_elasticsearch import ElasticsearchStore
    except ImportError as e:
        raise VectorStoreBackendError(
            "backend 'elasticsearch' requires the 'langchain-elasticsearch' package."
        ) from e
    return ElasticsearchStore(
        es_url=f"http://{config.es_host}:{config.es_port}",
        index_name=config.collection_name,
        embedding=embeddings,
    )


# Registry of backend name -> builder. Add new backends here.
_BACKEND_BUILDERS: dict[str, Callable[[VectorStoreConfig, Embeddings], VectorStore]] = {
    "in_memory": _build_in_memory,
    "chroma": _build_chroma,
    "elasticsearch": _build_elasticsearch,
}


def get_vector_store(
    config: VectorStoreConfig, embeddings: Embeddings | None = None
) -> VectorStore:
    """Build the `VectorStore` selected by `config.backend`.

    Falls back to the in-memory backend (with a warning) if the configured
    backend's optional dependency isn't installed, so a missing extra never
    hard-crashes the app — it only degrades semantic memory to a
    process-lifetime, non-persistent store.
    """
    builder = _BACKEND_BUILDERS.get(config.backend)
    if builder is None:
        raise VectorStoreBackendError(
            f"Unknown vector_store backend: {config.backend!r}. "
            f"Available: {sorted(_BACKEND_BUILDERS)}"
        )

    embeddings = embeddings or get_embeddings(config.embedding)

    try:
        return builder(config, embeddings)
    except VectorStoreBackendError as e:
        if config.backend == "in_memory":
            raise
        logger.warning(
            "Falling back to in_memory vector store: %s", e
        )
        return _build_in_memory(config, embeddings)

