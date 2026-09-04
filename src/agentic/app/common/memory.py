import os
import uuid
from pathlib import Path

from agentic.app.common.providers import DateTimeProvider


class Memory:
    def __init__(self, workspace: str, session_id: str = None):
        self.workspace = workspace
        self.memory = []
        self.session_id = session_id or str(uuid.uuid4())

    def add(self, message):
        self.memory.append(message)

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