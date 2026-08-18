import asyncio
import logging

from cndi.annotations import Bean, Component, ConditionalRendering
from cndi.env import getContextEnvironment
from cndi.secrets.fromenv import FromEnvProvider
from telegram import Bot, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agentic.app.common import INTERRUPT_EVENT, InterruptEvent
from agentic.app.common.audio import AudioProcessor
from agentic.app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID, TELEGRAM_BOT_TOKEN_PROP
from agentic.app.gateway.adapters import (
    AdapterRegistry,
    ChannelAdapter,
    InboundMessage,
    OutboundMessage, OutboundMessageReply,
)
from agentic.app.gateway.adapters.consts import TELEGRAM_SECRET
from agentic.app.gateway.adapters.telegram.reactions import add_reaction, remove_reaction
from agentic.app.gateway.config import Gateway

logger = logging.getLogger(__name__)


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

TELEGRAM_CHANNEL_ENABLED = "app.channels.telegram.enable"

def is_telegram_channel_enabled(x=None):
    return getContextEnvironment(TELEGRAM_CHANNEL_ENABLED, defaultValue=False, castFunc=bool)

@Bean()
@ConditionalRendering(callback=is_telegram_channel_enabled)
def get_telegram_application(env_provider: FromEnvProvider) -> Application:
    telegram_bot_token = getContextEnvironment(TELEGRAM_BOT_TOKEN_PROP)
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(telegram_bot_token).build()
    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_command))

    return application

@ConditionalRendering(callback=is_telegram_channel_enabled)
@Component
class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(
        self,
        application: Application,
        audio_processor: AudioProcessor,
        gateway: Gateway
    ):
        self.application = application
        self.bot: Bot = application.bot
        self.audio_processor = audio_processor
        self.gateway = gateway

        chat_id = getContextEnvironment(TELEGRAM_BOT_DEFAULT_CHAT_ID, castFunc=int)
        chat_filter = filters.Chat(chat_id=[chat_id])

        application.add_handler(
            MessageHandler(
                chat_filter & filters.TEXT & ~filters.COMMAND, self.inbound_message
            )
        )
        application.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, self.handle_audio)
        )

        AdapterRegistry.register(self)

    async def send_periodic_chat_action(
        self, context, chat_id: int, stop_event: asyncio.Event, interval: float = 4.0
    ):
        """Send chat action every N seconds to keep Telegram connection alive."""
        while not stop_event.is_set():
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Failed to send chat action: {e}")
                await asyncio.sleep(interval)

    async def handle_audio(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.message

        if message.voice:
            tg_file_obj = message.voice
            ext = "ogg"
        elif message.audio:
            tg_file_obj = message.audio
            ext = "mp3"
        else:
            return
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        # Resolve file_id -> File (contains file_path / download URL)
        file = await context.bot.get_file(tg_file_obj.file_id)
        filename = f"downloads/{message.message_id}.{ext}"

        # --- Option A: simplest, PTB streams to disk for you internally ---
        await file.download_to_drive(custom_path=filename)
        logger.info("Saved via download_to_drive: %s", filename)

        result = await self.audio_processor.speech_to_text(filename)
        speech_message = result["text"]

        inbound_msg = InboundMessage(
            message_id=str(message_id),
            channel="telegram",
            chat_id=str(chat_id),
            user_id=str(update.effective_user.id),
            text=speech_message,
            raw=update.to_dict(),
        )

        response_text = await self._process(inbound_msg)
        for text in response_text:
            out = await self.audio_processor.summarize_audio_text(text)
            ogg_path = await self.audio_processor.text_to_speech(out.content)
            with open(ogg_path, "rb") as f:
                await context.bot.send_voice(chat_id=update.message.chat_id, voice=f)

    async def _process(self, inbound_message: InboundMessage) -> list:
        response_text = await self.gateway.route_to_backend(inbound_message)
        for content in response_text:
            message_type = content.get("type", "text")
            outbound_message = OutboundMessage(
                channel="telegram",
                chat_id=inbound_message.chat_id,
                text=content.get("text", ""),
                metadata=dict(
                    type=message_type,
                    content=dict(data=content.get("data", None))
                    if message_type == "image"
                    else content,
                ),
            )
            await self.gateway.deliver_to_channel(outbound_message)
        return response_text

    async def invoke_webhook(self, message: OutboundMessage) -> OutboundMessageReply:
        """Process the incoming webhook request and return an InboundMessage."""
        if message.metadata.get("type") == "action" and message.metadata.get("document_action") == "delete":
            success = await self.bot.delete_message(chat_id=message.chat_id, message_id=message.metadata.get("message_id"))
            return message.to_reply(message_id=message.metadata.get("message_id"), metadata={"deleted": success})
        return await self.send(message)

    async def inbound_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Stream response and update emoji reactions per token."""
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        user_message = update.message.text

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        if user_message.startswith("$decision"):
            _, decision = user_message.split(" ")
            await update.message.reply_text(
                text=f"Decision captured {decision}",
                reply_markup=ReplyKeyboardRemove(),
            )
        stop_event = asyncio.Event()

        try:
            # Initialize reaction to thinking
            await add_reaction(context, chat_id, message_id, "🤔")

            logger.info(
                f"[Chat {chat_id}] Invoking agent with message: {user_message[:100]}..."
            )

            # Start periodic chat action task
            chat_action_task = asyncio.create_task(
                self.send_periodic_chat_action(context, chat_id, stop_event)
            )

            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            inbound_msg = InboundMessage(
                message_id=str(message_id),
                channel="telegram",
                chat_id=str(chat_id),
                user_id=str(update.effective_user.id),
                text=user_message,
                raw=update.to_dict(),
            )
            try:
                # response_text = await agentic_bot.invoke_agent(full_message, chat_id=chat_id,message_id=message_id, channel_metadata={})
                response_text = await self._process(inbound_msg)
                if response_text:
                    logger.info(f"[Chat {chat_id}] Agent responded successfully")
                # Finalize with checkmark
                await remove_reaction(context, chat_id, message_id)
                await add_reaction(context, chat_id, message_id, "✅")

            except TimeoutError:
                logger.error(f"[Chat {chat_id}] Agent call timed out after 120 seconds")
                await remove_reaction(context, chat_id, message_id)
                await add_reaction(context, chat_id, message_id, "⏱️")
                await update.message.reply_text(
                    "⏱️ Request took too long (>2 minutes). The NVIDIA API may be slow. Try again or use /clear to reset."
                )
            finally:
                # Stop the periodic chat action task
                stop_event.set()
                await asyncio.sleep(0.1)  # Give task time to stop
                if not chat_action_task.done():
                    chat_action_task.cancel()

        except Exception as e:
            logger.error(
                f"[Chat {chat_id}] Agent streaming failed: {type(e).__name__}: {e!s}",
                exc_info=True,
            )
            await remove_reaction(context, chat_id, message_id)
            await add_reaction(context, chat_id, message_id, "❌")
            await update.message.reply_text(
                f"❌ Error: {type(e).__name__}\n\nTry using /clear to reset conversation."
            )

    async def verify_webhook(self, request) -> bool:
        # Telegram supports a secret token header, set via setWebhook(secret_token=...)
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        return secret == TELEGRAM_SECRET

    async def send(self, message: OutboundMessage) -> OutboundMessageReply:
        logger.info(f"Sending message to Telegram: {message}")
        if message.metadata.get("type") == "text":
            message_response: Message = await self.bot.send_message(chat_id=message.chat_id, text=message.text)
            return message.to_reply(str(message_response.message_id))
        elif message.metadata.get("type") == "image":
            content = message.metadata.get("content")
            with open(content.get("data"), "rb") as file:
                await self.bot.send_photo(
                    chat_id=message.chat_id, photo=file, caption=message.text
                )
        elif message.metadata.get("type") == INTERRUPT_EVENT:
            interrupt_event = InterruptEvent(**message.metadata.get("content"))
            action_requests = interrupt_event.metadata.get("action_requests")[0]
            keyboard_buttons = interrupt_event.metadata.get("keyboard_buttons")

            keyboard = ReplyKeyboardMarkup(
                keyboard_buttons, one_time_keyboard=True, resize_keyboard=True
            )
            await self.bot.send_message(
                chat_id=message.chat_id,
                text=f"{action_requests['description']}",
                reply_markup=keyboard,
                reply_to_message_id=int(interrupt_event.message_id),
            )

        else:
            logger.info(
                f"Unsupported message event_type: {message.metadata.get('event_type')} and Message: {message}"
            )
        return None