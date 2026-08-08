import logging

from cndi.annotations import Component
from cndi.env import getContextEnvironment
from langchain.agents.middleware import AgentMiddleware
from telegram import Bot, Message

from agentic.app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID

logger = logging.getLogger(__name__)


@Component
class TelegramToolNotifierMiddleware(AgentMiddleware):
    """Sends a Telegram message before and after every tool call."""

    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot
        self.chat_id = getContextEnvironment(TELEGRAM_BOT_DEFAULT_CHAT_ID)

    async def send_telegram_message(self, text: str) -> Message:
        try:
            return await self.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as e:
            logger.error(f"[telegram notify] failed to send: {e}")

    async def delete_sent_message(self, message: Message):
        try:
            await self.bot.delete_message(chat_id=self.chat_id, message_id=message.id)
        except Exception as e:
            logger.error(f"[telegram delete] failed to send: {e}")

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call["args"]
        logger.info(f"🔧 Calling tool: {tool_name} Args: {tool_args}")
        message = await self.send_telegram_message(
            f"🔧 Calling tool: {tool_name}\nArgs: {tool_args}"
        )
        response = await handler(request)  # actually runs the tool
        logger.info(f"🔧 Tool Response: {response}")
        await self.delete_sent_message(message)

        return response
