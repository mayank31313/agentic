
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, LocalShellBackend
from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.middleware import InterruptOnConfig
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.config import AgentConfig, ToolConfig


def read_agents_md(path: str) -> str:
    p = Path(path)
    raw = p.read_bytes()

    # 1) BOM-based quick check
    if raw.startswith(b'\xEF\xBB\xBF'):
        return raw.decode('utf-8-sig')
    if raw.startswith(b'\xFF\xFE') or raw.startswith(b'\xFE\xFF'):
        return raw.decode('utf-16')

    # 2) Try UTF-8 (most likely)
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # 3) Try common fallbacks
    for enc in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252'):
        try:
            return raw.decode(enc)
        except Exception:
            continue

    # 4) Last resort: decode with replacement to avoid crashing
    return raw.decode('utf-8', errors='replace')

os.environ['OPENAI_API_BASE'] = 'https://integrate.api.nvidia.com/v1'
os.environ['OPENAI_API_KEY'] = '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'

def get_image_agent():
    # usage
    client = ChatOpenAI(
                    model="gemma-4-e2b-it",
                    base_url='http://localhost:8080/v1',
                    api_key=os.getenv("OPENAI_API_KEY", "$NVIDIA_API_KEY"),
                    temperature=0.6,
                    top_p=0.95,
                    max_tokens=65536,
                )

    return client

def get_main_agent(agent_config: AgentConfig,
                   tools: list[BaseTool] = None,
                   tools_need_approval: list[ToolConfig]=None,
                   middlewares=[]):
    # usage
    if tools_need_approval is None:
        tools_need_approval = []
    base_prompt = read_agents_md(os.path.join(agent_config.workspace_dir, agent_config.system_prompt_path))
    system_prompt = base_prompt + "\n\nYou have access to a memory retriever tool that can search past conversations. Use it when you need to recall relevant information from past chats."

    checkpointer = InMemorySaver()

    interrupt_tool_on = {x.name: InterruptOnConfig(allowed_decisions=["approve", "reject"], description=x.approval_text) for x in tools_need_approval}

    model = init_chat_model(
        model=agent_config.model,
        base_url=agent_config.base_url
    )

    agent = create_deep_agent(
        model=model,
        backend=CompositeBackend(
            default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
            routes={
                "/images/": FilesystemBackend(root_dir="./images", virtual_mode=True),
                "/skills/": LocalShellBackend(root_dir="./skills", virtual_mode=True, env={"PATH": "/usr/bin:/bin"}),
            },
        ),

        skills=['/skills/'],
        system_prompt=system_prompt,
        tools=tools or [],
        middleware=middlewares,
        checkpointer=checkpointer,
        interrupt_on=interrupt_tool_on,
    )

    return agent