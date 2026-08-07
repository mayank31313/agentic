import logging
from typing import Optional

import httpx
from cndi.annotations import Component, Bean
from cndi.env import getContextEnvironment
from cndi.secrets.vault import VaultSecretProvider
from telegram import Bot, ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from agentic.app.constants import TELEGRAM_BOT_TOKEN_PROP
from agentic.app.gateway.adapters import OutboundMessage, InboundMessage, ChannelAdapter, AdapterRegistry
from agentic.app.gateway.adapters.consts import EXPECTED_TELEGRAM_SECRET
import logging

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
def get_telegram_application(vault_provider: VaultSecretProvider) -> Application:
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

logger = logging.getLogger(__name__)
@Component
class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, application: Application):
        self.application = application
        self.bot: Bot = application.bot
        AdapterRegistry.register(self)

    async def verify_webhook(self, request) -> bool:
        # Telegram supports a secret token header, set via setWebhook(secret_token=...)
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        return secret == EXPECTED_TELEGRAM_SECRET

    def parse_inbound(self, payload: dict) -> Optional[InboundMessage]:
        msg = payload.get("message", {})
        if "text" not in msg:
            return None
        return InboundMessage(
            message_id=str(msg["message_id"]),
            channel=self.name,
            chat_id=str(msg["chat"]["id"]),
            user_id=str(msg["from"]["id"]),
            text=msg["text"],
            raw=payload,
        )

    async def send(self, message: OutboundMessage) -> None:
        if message.metadata.get('type') == 'text':
            await self.bot.send_message(chat_id=message.chat_id, text=message.text)
        elif message.metadata.get('type') == 'image':
            content = message.metadata.get('content')
            with open(content.get('data'), 'rb') as file:
                await self.bot.send_photo(chat_id=message.chat_id,photo=file, caption=message.text)
        else:
            logger.info(f"Unsupported message type: {message.metadata.get('type')} and Message: {message}")