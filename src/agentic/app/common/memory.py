import os
import uuid
from pathlib import Path

from agentic.app.common.providers import DateTimeProvider
from agentic.app.config import VectorStoreConfig
from agentic.app.memory_retriever import MemoryRetriever, get_memory_retriever


class Memory:
    def __init__(
        self,
        workspace: str,
        session_id: str = None,
        vector_store_config: VectorStoreConfig | None = None,
        retriever: MemoryRetriever | None = None,
    ):
        self.workspace = workspace
        self.memory = []
        self.session_id = session_id or str(uuid.uuid4())
        # Semantic (vector-store backed) memory — see `add_memory`. Injecting
        # a pre-built `retriever` (mainly for tests) skips the config-driven
        # `get_memory_retriever` lookup entirely.
        self.retriever = retriever or get_memory_retriever(vector_store_config)

    def add(self, message):
        self.memory.append(message)

    def add_memory(self, chat_id: int, role: str, content: str) -> None:
        """Persist a message into semantic (vector-store backed) memory so it
        can later be recalled via the `memory_search` tool.

        Best-effort: `MemoryRetriever.add_message` already logs and swallows
        its own failures, so a memory-store outage never breaks a
        conversation turn.
        """
        self.retriever.add_message(chat_id=chat_id, role=role, content=content)

    def load(self, file_path_in_workspace: str):
        file_path = os.path.join(self.workspace, file_path_in_workspace)
        if not os.path.exists(file_path):
            return
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("::")
                if len(parts) >= 3:
                    session_id, msg_type, text = parts[0], parts[1], "::".join(parts[2:]).strip()
                    self.memory.append({"session_id": session_id, "type": msg_type.strip(), "text": text})

    def write(self):
        date_string = DateTimeProvider.date_today_str()
        memory_file = os.path.join(self.workspace, "memory", f"{date_string}.md")
        os.makedirs(Path(self.workspace, "memory"), exist_ok=True)
        with open(memory_file, "a", encoding="utf-8") as f:
            f.writelines([f"{self.session_id}::{data['type']}\t:: {data['text']}\n" for data in self.memory])

        self.memory.clear()