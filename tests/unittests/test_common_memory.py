"""Tests for `Memory.add_memory` — the non-tool binding of semantic memory
writes, called from `AgenticBot.invoke_agent` for every conversation turn."""

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from agentic.app.common.memory import Memory
from agentic.app.config import VectorStoreConfig
from agentic.app.memory_retriever import MemoryRetriever


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


@pytest.fixture()
def memory(tmp_path):
    store = InMemoryVectorStore(embedding=FakeEmbeddings())
    retriever = MemoryRetriever(
        config=VectorStoreConfig(backend="in_memory", enabled=True), vector_store=store
    )
    return Memory(workspace=str(tmp_path), retriever=retriever)


def test_add_memory_persists_into_the_vector_store_retriever(memory):
    memory.add_memory(chat_id=1, role="user", content="remember this fact")

    docs = memory.retriever.vector_store.similarity_search("remember this fact", k=5)

    assert any(d.page_content == "remember this fact" for d in docs)


@pytest.mark.asyncio
async def test_add_memory_is_recallable_via_search_relevant_messages(memory):
    memory.add_memory(chat_id=1, role="user", content="remember this fact")

    results = await memory.retriever.search_relevant_messages(
        chat_id=1, query="remember this fact"
    )

    assert any(r["content"] == "remember this fact" for r in results)


def test_add_does_not_touch_vector_memory(memory):
    """`Memory.add` (the plain markdown log) and `Memory.add_memory` (the
    vector-store write) are independent — adding to one must not affect
    the other."""
    memory.add(dict(text="just a log line", type="user"))

    assert memory.memory == [dict(text="just a log line", type="user")]
    docs = memory.retriever.vector_store.similarity_search("just a log line", k=5)
    assert not any(d.page_content == "just a log line" for d in docs)

