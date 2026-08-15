import contextvars
import logging
import threading
import time

import uvicorn
from cndi.annotations.threads import ContextThreads
from cndi.initializers import AppInitializer
from pydantic import BaseModel, Field
from telegram import Update
from telegram.ext import Application

from agentic.app.bot import AgenticBot
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

def main(
    application: Application,
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
