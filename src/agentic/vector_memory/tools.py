"""LangChain tool exposing semantic conversation-memory *search* over the
config-driven vector-store backend (see `agentic.app.vectorstore_factory`).

Writing to memory is intentionally NOT exposed as an agent-callable tool —
every turn is recorded automatically via
`agentic.app.common.memory.Memory.add_memory`, called from
`AgenticBot.invoke_agent`. This module only exposes read access
(`memory_search`) so an agent can explicitly recall relevant past context.
"""

import logging

from langchain_core.tools import BaseTool, tool

from agentic.app.config import VectorStoreConfig
from agentic.app.memory_retriever import MemoryRetriever, get_memory_retriever

logger = logging.getLogger(__name__)


def get_vector_memory_tools(config: VectorStoreConfig | None = None) -> list[BaseTool]:
    """Build the `memory_search` LangChain tool bound to a `MemoryRetriever`
    built from `config` (or the default `VectorStoreConfig` if omitted).
    """
    retriever: MemoryRetriever = get_memory_retriever(config)

    @tool
    async def memory_search(chat_id: int, query: str, limit: int = 5) -> list[dict]:
        """Semantically search past conversation messages for a given chat.

        Returns the `limit` most relevant messages (role/content/timestamp/score)
        to `query`, scoped to `chat_id`. Empty list if memory is disabled or
        nothing relevant is found.
        """
        try:
            return await retriever.search_relevant_messages(
                chat_id=chat_id, query=query, limit=limit
            )
        except Exception as e:
            logger.error(f"Error searching memory for chat {chat_id!r}: {e}")
            return [{"error": str(e)}]

    return [memory_search]

