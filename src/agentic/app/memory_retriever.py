"""Memory Retriever using Elasticsearch for semantic search over conversation history."""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk

    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    Elasticsearch = None  # type: ignore
    ELASTICSEARCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Elasticsearch-based memory retriever for searching conversation history.
    Supports full-text search and semantic retrieval of relevant past messages.
    """

    def __init__(
        self,
        es_host: str = "localhost",
        es_port: int = 9200,
        index_name: str = "conversation_memory",
        enabled: bool = True,
    ):
        """
        Initialize the memory retriever.

        Args:
            es_host: Elasticsearch host
            es_port: Elasticsearch port
            index_name: Index name for storing messages
            enabled: Whether to enable Elasticsearch (if False, will use in-memory fallback)
        """
        self.es_host = es_host
        self.es_port = es_port
        self.index_name = index_name
        self.enabled = enabled and ELASTICSEARCH_AVAILABLE
        self.es_client = None
        self.in_memory_messages = {}  # Fallback: chat_id -> list of messages

        if not ELASTICSEARCH_AVAILABLE and enabled:
            logger.warning(
                "Elasticsearch not available. Using in-memory fallback. Install: pip install elasticsearch"
            )
            self.enabled = False

        if self.enabled:
            self._init_elasticsearch()

    def _init_elasticsearch(self):
        """Initialize Elasticsearch connection and create index."""
        try:
            self.es_client = Elasticsearch(
                hosts=[{"host": self.es_host, "port": self.es_port}], timeout=10
            )

            # Check connection
            if not self.es_client.ping():
                logger.warning(
                    f"Cannot connect to Elasticsearch at {self.es_host}:{self.es_port}"
                )
                self.enabled = False
                return

            # Create index if it doesn't exist
            if not self.es_client.indices.exists(index=self.index_name):
                self.es_client.indices.create(
                    index=self.index_name,
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "analysis": {
                                "analyzer": {
                                    "default": {
                                        "type": "standard",
                                        "stopwords": "_english_",
                                    }
                                }
                            },
                        },
                        "mappings": {
                            "properties": {
                                "chat_id": {"type": "keyword"},
                                "role": {"type": "keyword"},
                                "content": {"type": "text", "analyzer": "standard"},
                                "timestamp": {"type": "date"},
                                "message_index": {"type": "integer"},
                            }
                        },
                    },
                )
                logger.info(f"Created Elasticsearch index: {self.index_name}")

            logger.info("Elasticsearch initialized successfully")

        except Exception as e:
            logger.warning(
                f"Failed to initialize Elasticsearch: {e}. Using in-memory fallback."
            )
            self.enabled = False

    def add_message(
        self, chat_id: int, role: str, content: str, message_index: int = 0
    ):
        """
        Add a message to the memory index.

        Args:
            chat_id: Chat ID
            role: Message role (user/assistant)
            content: Message content
            message_index: Index of this message in the conversation
        """
        try:
            if self.enabled:
                doc = {
                    "chat_id": str(chat_id),
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                    "message_index": message_index,
                }

                doc_id = f"{chat_id}_{message_index}_{datetime.now().timestamp()}"
                self.es_client.index(index=self.index_name, id=doc_id, body=doc)
            else:
                # Fallback: in-memory storage
                if chat_id not in self.in_memory_messages:
                    self.in_memory_messages[chat_id] = []

                self.in_memory_messages[chat_id].append(
                    {
                        "chat_id": chat_id,
                        "role": role,
                        "content": content,
                        "timestamp": datetime.now().isoformat(),
                        "message_index": message_index,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to add message to index: {e}")

    async def search_relevant_messages(
        self, chat_id: int, query: str, limit: int = 5, timeout: float = 5.0
    ) -> List[Dict]:
        """
        Search for relevant messages in the conversation history.

        Args:
            chat_id: Chat ID to search within
            query: Search query
            limit: Maximum number of results
            timeout: Search timeout in seconds

        Returns:
            List of relevant messages
        """
        try:
            if self.enabled:
                # Use asyncio.to_thread to run the blocking ES call
                results = await asyncio.wait_for(
                    asyncio.to_thread(self._es_search, chat_id, query, limit),
                    timeout=timeout,
                )
                return results
            else:
                # Fallback: simple in-memory search
                return self._in_memory_search(chat_id, query, limit)

        except asyncio.TimeoutError:
            logger.warning(f"Search timeout for chat {chat_id}")
            return []
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _es_search(self, chat_id: int, query: str, limit: int) -> List[Dict]:
        """Elasticsearch search (blocking)."""
        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"content": query}},
                            {"term": {"chat_id": str(chat_id)}},
                        ]
                    }
                },
                "size": limit,
                "sort": [{"timestamp": {"order": "desc"}}],
            }

            response = self.es_client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit["_source"]
                results.append(
                    {
                        "role": source.get("role"),
                        "content": source.get("content"),
                        "timestamp": source.get("timestamp"),
                        "score": hit.get("_score", 0),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Elasticsearch search error: {e}")
            return []

    def _in_memory_search(self, chat_id: int, query: str, limit: int) -> List[Dict]:
        """Simple in-memory search using keyword matching."""
        if chat_id not in self.in_memory_messages:
            return []

        query_lower = query.lower()
        results = []

        # Score messages by keyword matches
        for msg in self.in_memory_messages[chat_id]:
            content_lower = msg["content"].lower()
            score = content_lower.count(query_lower)

            if score > 0:
                results.append({**msg, "score": score})

        # Sort by score and return top results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def search_by_topic(
        self, chat_id: int, keywords: List[str], limit: int = 5
    ) -> List[Dict]:
        """
        Search for messages containing any of the given keywords.

        Args:
            chat_id: Chat ID to search within
            keywords: List of keywords to search for
            limit: Maximum number of results

        Returns:
            List of relevant messages
        """
        try:
            if self.enabled:
                results = await asyncio.wait_for(
                    asyncio.to_thread(self._es_topic_search, chat_id, keywords, limit),
                    timeout=5.0,
                )
                return results
            else:
                return self._in_memory_topic_search(chat_id, keywords, limit)

        except Exception as e:
            logger.error(f"Topic search failed: {e}")
            return []

    def _es_topic_search(
        self, chat_id: int, keywords: List[str], limit: int
    ) -> List[Dict]:
        """Elasticsearch topic search (blocking)."""
        try:
            should_clauses = [{"match": {"content": kw}} for kw in keywords]

            search_body = {
                "query": {
                    "bool": {
                        "must": {"term": {"chat_id": str(chat_id)}},
                        "should": should_clauses,
                        "minimum_should_match": 1,
                    }
                },
                "size": limit,
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"timestamp": {"order": "desc"}},
                ],
            }

            response = self.es_client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit["_source"]
                results.append(
                    {
                        "role": source.get("role"),
                        "content": source.get("content"),
                        "timestamp": source.get("timestamp"),
                        "score": hit.get("_score", 0),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Topic search error: {e}")
            return []

    def _in_memory_topic_search(
        self, chat_id: int, keywords: List[str], limit: int
    ) -> List[Dict]:
        """Simple in-memory topic search."""
        if chat_id not in self.in_memory_messages:
            return []

        keywords_lower = [kw.lower() for kw in keywords]
        results = []

        for msg in self.in_memory_messages[chat_id]:
            content_lower = msg["content"].lower()
            score = sum(1 for kw in keywords_lower if kw in content_lower)

            if score > 0:
                results.append({**msg, "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def get_chat_history(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """
        Get recent messages for a chat.

        Args:
            chat_id: Chat ID
            limit: Number of recent messages

        Returns:
            List of messages
        """
        try:
            if self.enabled:
                results = await asyncio.wait_for(
                    asyncio.to_thread(self._es_get_history, chat_id, limit), timeout=5.0
                )
                return results
            else:
                if chat_id not in self.in_memory_messages:
                    return []
                return self.in_memory_messages[chat_id][-limit:]

        except Exception as e:
            logger.error(f"Get history failed: {e}")
            return []

    def _es_get_history(self, chat_id: int, limit: int) -> List[Dict]:
        """Get chat history from Elasticsearch (blocking)."""
        try:
            search_body = {
                "query": {"term": {"chat_id": str(chat_id)}},
                "size": limit,
                "sort": [{"timestamp": {"order": "desc"}}],
            }

            response = self.es_client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response.get("hits", {}).get("hits", []):
                source = hit["_source"]
                results.append(
                    {
                        "role": source.get("role"),
                        "content": source.get("content"),
                        "timestamp": source.get("timestamp"),
                    }
                )

            results.reverse()  # Return in chronological order
            return results

        except Exception as e:
            logger.error(f"Get history error: {e}")
            return []

    def clear_chat_history(self, chat_id: int):
        """Clear all messages for a chat."""
        try:
            if self.enabled:
                self.es_client.delete_by_query(
                    index=self.index_name,
                    body={"query": {"term": {"chat_id": str(chat_id)}}},
                )
            else:
                if chat_id in self.in_memory_messages:
                    del self.in_memory_messages[chat_id]

            logger.info(f"Cleared history for chat {chat_id}")
        except Exception as e:
            logger.error(f"Clear history failed: {e}")


# Global instance
_memory_retriever: Optional[MemoryRetriever] = None


def get_memory_retriever(
    es_host: str = "localhost", es_port: int = 9200, enabled: bool = True
) -> MemoryRetriever:
    """Get or create the global memory retriever instance."""
    global _memory_retriever

    if _memory_retriever is None:
        _memory_retriever = MemoryRetriever(
            es_host=es_host, es_port=es_port, enabled=enabled
        )

    return _memory_retriever
