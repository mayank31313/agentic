"""Tests for the VectorStore-backed MemoryRetriever."""

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from agentic.app.config import VectorStoreConfig
from agentic.app.memory_retriever import MemoryRetriever


class FakeEmbeddings(Embeddings):
    """Simple bag-of-words-ish embeddings: closer text -> closer vectors,
    good enough to exercise similarity search deterministically in tests."""

    _VOCAB = ["pizza", "python", "vector", "weather", "unrelated"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(word)) for word in self._VOCAB]


@pytest.fixture()
def retriever():
    store = InMemoryVectorStore(embedding=FakeEmbeddings())
    config = VectorStoreConfig(backend="in_memory", enabled=True)
    return MemoryRetriever(config=config, vector_store=store)


@pytest.mark.asyncio
async def test_search_relevant_messages_scopes_to_chat_id(retriever):
    retriever.add_message(chat_id=1, role="user", content="I love pizza toppings")
    retriever.add_message(chat_id=1, role="assistant", content="Python vector search is great")
    retriever.add_message(chat_id=2, role="user", content="pizza in another chat")

    results = await retriever.search_relevant_messages(chat_id=1, query="pizza", limit=5)

    assert len(results) >= 1
    assert all(r["content"] != "pizza in another chat" for r in results)


@pytest.mark.asyncio
async def test_disabled_retriever_returns_empty_results():
    config = VectorStoreConfig(enabled=False)
    retriever = MemoryRetriever(config=config)

    retriever.add_message(chat_id=1, role="user", content="hello")
    results = await retriever.search_relevant_messages(chat_id=1, query="hello")

    assert results == []


def test_add_message_skips_blank_content(retriever):
    # Should not raise and should not add an empty document.
    retriever.add_message(chat_id=1, role="user", content="   ")


