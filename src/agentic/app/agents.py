import logging
import os
import zipfile
from pathlib import Path

import numpy as np
import torch
from cndi.annotations import Component
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from huggingface_hub import hf_hub_download
from langchain.agents.middleware import InterruptOnConfig
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from transformers import (
    SpeechT5ForTextToSpeech,
    SpeechT5HifiGan,
    SpeechT5Processor,
    pipeline,
)

from agentic.app.config import AgentConfig, AgentToolConfig


def read_agents_md(path: str) -> str:
    p = Path(path)
    raw = p.read_bytes()

    # 1) BOM-based quick check
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")

    # 2) Try UTF-8 (most likely)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 3) Try common fallbacks
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            return raw.decode(enc)
        except Exception:
            continue

    # 4) Last resort: decode with replacement to avoid crashing
    return raw.decode("utf-8", errors="replace")


def get_image_agent():
    # usage
    client = ChatOpenAI(
        model="gemma-4-e2b-it",
        base_url="http://localhost:8080/v1",
        api_key=os.getenv("OPENAI_API_KEY", "$NVIDIA_API_KEY"),
        temperature=0.6,
        top_p=0.95,
        max_tokens=65536,
    )

    return client


logger = logging.getLogger(__name__)


@Component
class AgentRegistry:
    def __init__(self):
        self.agents = dict()

    def register_agent(self, name, agent):
        self.agents[name] = agent
        logger.debug(f"Agent Registered {name}")

    def get_agent(self, name):
        return self.agents.get(name)


def get_speech_to_text_pipeline(device: str = "cpu"):
    return pipeline(
        "automatic-speech-recognition", model="openai/whisper-small", device=device
    )


def get_text_to_speech_pipeline():
    zip_path = hf_hub_download(
        repo_id="Matthijs/cmu-arctic-xvectors",
        filename="spkrec-xvect.zip",
        repo_type="dataset",
    )

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        print(f"Total entries: {len(names)}")
        for n in names[:15]:
            print(n)
        with zf.open("spkrec-xvect/cmu_us_slt_arctic-wav-arctic_b0516.npy") as f:
            speaker_embedding = np.load(f)

    female_speaker_embedding = torch.tensor(speaker_embedding).unsqueeze(0)

    tts_processor = SpeechT5Processor.from_pretrained("microsoft/speecht5_tts")
    tts_model = SpeechT5ForTextToSpeech.from_pretrained("microsoft/speecht5_tts")
    tts_vocoder = SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan")
    return tts_processor, tts_model, tts_vocoder, female_speaker_embedding


def get_main_agent(
    agent_config: AgentConfig,
    tools: list[BaseTool] = None,
    tools_need_approval: list[AgentToolConfig] = None,
    middlewares=[],
):
    # usage
    if tools_need_approval is None:
        tools_need_approval = []
    system_prompt = (
        agent_config.instructions
        + "\n\nYou have access to a memory retriever tool that can search past conversations. Use it when you need to recall relevant information from past chats."
    )

    checkpointer = InMemorySaver()

    interrupt_tool_on = {
        x.name: InterruptOnConfig(
            allowed_decisions=["approve", "reject"], description=x.approval_text
        )
        for x in tools_need_approval
    }

    model_config = agent_config.agent_model_config
    model = init_chat_model(
        model=model_config.model,
        base_url=model_config.base_url,
        api_key=model_config.api_key
        if type(model_config.api_key) is str
        else model_config.api_key.resolve(),
    )

    routes = {
        "/images/": FilesystemBackend(root_dir="./images", virtual_mode=True),
    }
    agent_skill_paths = []
    for skill_config in agent_config.skills:
        logger.info(
            f"Adding skill route for {skill_config.virtual_path} at path {skill_config.path}"
        )
        routes[skill_config.virtual_path] = FilesystemBackend(
            root_dir=skill_config.path, virtual_mode=True
        )
        agent_skill_paths.append(skill_config.virtual_path)

    agent = create_deep_agent(
        model=model,
        backend=CompositeBackend(
            default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
            routes={
                "/skills/": FilesystemBackend(root_dir="src/skills", virtual_mode=True),
                "/resources/": FilesystemBackend(
                    root_dir="resources", virtual_mode=True
                ),
            },
        ),
        skills=agent_skill_paths,
        system_prompt=system_prompt,
        tools=tools or [],
        middleware=middlewares,
        checkpointer=checkpointer,
        interrupt_on=interrupt_tool_on,
    )
    return agent
