"""Semantic memory retriever backed by a pluggable `langchain_core` VectorStore.

Backend selection (Chroma, Elasticsearch, in-memory, ...) is entirely
config-driven — see `agentic.app.config.VectorStoreConfig` and
`agentic.app.vectorstore_factory.get_vector_store`. This module only deals
with the conversation-memory domain (per-chat documents/metadata); it does
not know or care which backend is actually storing the vectors.
"""

import asyncio
import logging
from datetime import datetime

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

from agentic.app.config import VectorStoreConfig
from agentic.app.vectorstore_factory import VectorStoreBackendError, get_vector_store

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """Semantic (embedding-based) retriever for searching conversation history.

    Each message is stored as a `Document` in the configured `VectorStore`,
    tagged with `chat_id`/`role`/`timestamp`/`message_index` metadata so
    searches can be scoped to a single conversation.
    """

    def __init__(
        self,
        config: VectorStoreConfig | None = None,
        vector_store: VectorStore | None = None,
    ):
        """
        Args:
            config: Vector-store backend configuration. Defaults to the
                in-memory backend if not provided.
            vector_store: Pre-built `VectorStore` to use instead of building
                one from `config` (mainly for tests/dependency injection).
        """
        self.config = config or VectorStoreConfig()
        self.enabled = self.config.enabled
        self.vector_store: VectorStore | None = vector_store

        if self.enabled and self.vector_store is None:
            try:
                self.vector_store = get_vector_store(self.config)
            except VectorStoreBackendError as e:
                logger.warning(
                    "Failed to initialize vector store backend %r: %s. "
                    "Semantic memory retrieval is disabled.",
                    self.config.backend,
                    e,
                )
                self.enabled = False

    def add_message(
        self, chat_id: int, role: str, content: str, message_index: int = 0
    ):
        """Add a message to the vector store."""
        if not self.enabled or not content.strip():
            return
        try:
            doc = Document(
                page_content=content,
                metadata={
                    "chat_id": str(chat_id),
                    "role": role,
                    "timestamp": datetime.now().isoformat(),
                    "message_index": message_index,
                },
            )
            self.vector_store.add_documents([doc])
        except Exception as e:
            logger.error(f"Failed to add message to vector store: {e}")

    async def search_relevant_messages(
        self, chat_id: int, query: str, limit: int = 5, timeout: float = 5.0
    ) -> list[dict]:
        """Semantically search for messages relevant to `query` within `chat_id`."""
        if not self.enabled:
            return []
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(self._search, chat_id, query, limit), timeout=timeout
            )
            return results
        except TimeoutError:
            logger.warning(f"Search timeout for chat {chat_id}")
            return []
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _search(self, chat_id: int, query: str, limit: int) -> list[dict]:
        try:
            docs_with_scores = self.vector_store.similarity_search_with_score(
                query,
                k=limit,
                filter={"chat_id": str(chat_id)},
            )
        except TypeError:
            # Some backends (e.g. InMemoryVectorStore) accept `filter` as a
            # callable predicate rather than a dict of exact-match metadata.
            docs_with_scores = self.vector_store.similarity_search_with_score(
                query,
                k=limit,
                filter=lambda doc: doc.metadata.get("chat_id") == str(chat_id),
            )

        return [
            {
                "role": doc.metadata.get("role"),
                "content": doc.page_content,
                "timestamp": doc.metadata.get("timestamp"),
                "score": score,
            }
            for doc, score in docs_with_scores
        ]

    def clear_chat_history(self, chat_id: int):
        """Best-effort deletion of all vectors for a chat (backend-dependent)."""
        if not self.enabled:
            return
        try:
            delete = getattr(self.vector_store, "delete", None)
            if delete is None:
                logger.warning(
                    "Backend %r does not support delete(); skipping clear_chat_history",
                    self.config.backend,
                )
                return
            # Most VectorStore.delete() implementations take ids, not filters;
            # backends that support metadata-filtered delete should override
            # this via a config-specific subclass if needed.
            delete(filter={"chat_id": str(chat_id)})
            logger.info(f"Cleared history for chat {chat_id}")
        except Exception as e:
            logger.error(f"Clear history failed: {e}")


# Global instance
_memory_retriever: MemoryRetriever | None = None


def get_memory_retriever(config: VectorStoreConfig | None = None) -> MemoryRetriever:
    """Get or create the global memory retriever instance."""
    global _memory_retriever

    if _memory_retriever is None:
        _memory_retriever = MemoryRetriever(config=config)

    return _memory_retriever
