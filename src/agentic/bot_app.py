import contextvars
import json
import logging
import os
import threading
import time

import uvicorn
from cndi.annotations import Bean, getBeanObject
from cndi.annotations.threads import ContextThreads
from cndi.env import getContextEnvironment
from cndi.initializers import AppInitializer
from pydantic import BaseModel, Field
from telegram import Update
from telegram.ext import Application

from agentic import AgenticConfig
from agentic.app.bot import AgenticBot
from agentic.app.config import SkillsConfig, AgentConfig, AgentToolConfig
from agentic.app.constants import AGENTIC_FILE_NAME_PROP
from agentic.app.gateway.adapters.telegram.bot import is_telegram_channel_enabled
from agentic.app.gateway.adapters.websockets import WebSocketConnectionManager
from agentic.app.gateway.config import Gateway
from agentic.app.gateway.server import get_adapter_gateway

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

chat_id_var = contextvars.ContextVar("chat_id")

class ChannelMetadata(BaseModel):
    chat_id: str = Field(description="Chat ID for channel")
    message_id: str = Field(description="Message ID for chat")

@Bean()
def getAgenticConfig() -> AgenticConfig:
    filename = getContextEnvironment(AGENTIC_FILE_NAME_PROP)
    try:
        if os.path.exists(filename):
            with open(filename, "r") as config_json:
                return  AgenticConfig.model_validate(json.load(config_json))
    except Exception as e:
        raise e

    with open(filename, "w") as config_json:
        agentic = AgenticConfig(
            workspace="./workspace",
            skills=[SkillsConfig(name="superpowers", path="skills/superpowers")],
            agents=[
                AgentConfig(
                    system_prompt_path="AGENTS.md",
                    workspace_dir="./workspace",
                    name="main",
                    model="openai:nvidia/nemotron-3-super-120b-a12b",
                    base_url="https://integrate.api.nvidia.com/v1",
                    tools=tuple(
                        [
                            AgentToolConfig(
                                name="run_shell_command",
                                require_approval=True,
                                approval_text="This tool needs approval to run",
                            ),
                            AgentToolConfig(name="generate_image", require_approval=False),
                            AgentToolConfig(name="swamp_sub_agent", require_approval=False),
                        ]
                    ),
                    denied_tools=tuple([]),
                )
            ],
            mcpServers={
                "alice_mcps": {
                    "url": "http://host.docker.internal:8811/sse",
                    "transport": "sse",
                    "headers": {"Authorization": "Bearer {}"},
                },
                "agentic_mcp": {
                    "url": "http://host.docker.internal:8082/mcp",
                    "transport": "http",
                },
            },
        )

        json.dump(agentic.model_dump(mode="json"), fp=config_json, indent=4)

    return agentic


def main(
    agentic_bot: AgenticBot,
    gateway: Gateway,
    connection_manager: WebSocketConnectionManager,
    context_threads: ContextThreads,
):
    agentic_bot.initialise_agent()
    """Start the bot."""

    # Run the bot until the user presses Ctrl-C
    fast_app = get_adapter_gateway(gateway, connection_manager)
    fast_server = threading.Thread(
        target=lambda: uvicorn.run(fast_app, host="0.0.0.0", port=5000)
    )
    fast_server.start()

    context_threads.add_thread(fast_server)
    if is_telegram_channel_enabled():
        application = getBeanObject(Application)
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def run_bot():
    app = AppInitializer()
    app.componentScan("cndi.secrets")
    app.componentScan("agentic.app")
    app.run(onComplete=main)

    while True:
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            exit(0)


if __name__ == "__main__":
    run_bot()
