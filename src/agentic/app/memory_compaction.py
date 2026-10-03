# Create memory compaction agent
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend


def create_memory_compaction_agent():
    """Create a memory compaction agent."""
    memory_compaction_prompt = """You are a memory compaction specialist. Your task is to summarize old conversation history while preserving key information.
    
    Given a conversation history, you should:
    1. Identify main topics and key decisions discussed
    2. Summarize each major discussion point in 1-2 sentences
    3. Preserve any important context or decisions made
    4. Keep the summary concise but informative
    
    Format your summary as a bullet list of key points."""

    return create_deep_agent(
        model="openai:nvidia/nemotron-3-super-120b-a12b",
        backend=FilesystemBackend(root_dir="../../../workspace", virtual_mode=True),
        system_prompt=memory_compaction_prompt,
    )
