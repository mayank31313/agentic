from typing import List

from cndi.env import getContextEnvironment
from cndi.secrets.vault import VaultSecretProvider
from langchain.agents.middleware import AgentMiddleware
import logging
from cndi.annotations import Component, Bean
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from telegram import Bot, Message, Update, ForceReply
import os

from telegram.ext import Application, CommandHandler, ContextTypes

from app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID, TELEGRAM_BOT_TOKEN_PROP

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
        message = await self.send_telegram_message(f"🔧 Calling tool: {tool_name}\nArgs: {tool_args}")
        response =   await handler(request)  # actually runs the tool
        logger.info(f"🔧 Tool Response: {response}")
        await self.delete_sent_message(message)

        return response

# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation memory when /clear is issued."""
    chat_id = update.effective_chat.id
    # clear_memory(chat_id)
    await update.message.reply_text("✅ Conversation memory cleared!")

@Bean()
def get_telegram_application() -> Application:
    telegram_bot_token = getContextEnvironment(TELEGRAM_BOT_TOKEN_PROP)
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(telegram_bot_token).build()
    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_command))

    return application

@Bean()
def get_telegram_bot(application: Application) -> Bot:
    return application.bot

class ToolsRegistry:
    def __init__(self):
        self.tools = dict()

    def register_tool(self, name, func):
        self.tools[name] = func
        logger.info(f"Tool Registered {name}")

    def get_tools(self, tool_names: List[str]) -> List[BaseTool]:
        tools = []
        for tool_name in tool_names:
            tools.append(self.tools[tool_name])

        return tools

@Bean()
def getToolsRegistry() -> ToolsRegistry:
    registry = ToolsRegistry()
    return registry