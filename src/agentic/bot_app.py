import asyncio
import contextvars
import logging
import os
import threading
import zipfile
from collections import defaultdict
from datetime import datetime
from typing import Optional

import httpx
import uvicorn
from cndi.annotations.events import EventBus
from cndi.env import getContextEnvironment, VARS, getContextEnvironments
from huggingface_hub import hf_hub_download
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, Interrupt
from pydantic import BaseModel, Field

from agentic.app.bot import AgenticBot
from agentic.app.channels.telegram import TelegramToolNotifierMiddleware
from cndi.initializers import AppInitializer
from cndi.annotations import Component, Bean
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
    AsyncCallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool
from telegram import Update, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

from agentic.app.agents import get_main_agent, AgentRegistry, get_speech_to_text_pipeline, get_text_to_speech_pipeline
from agentic.app.common.tools import ToolsRegistry
from agentic.app.config import AgentConfig, AgenticConfig, ToolConfig, SkillsConfig
from agentic.app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID, AGENTIC_FILE_NAME_PROP
from agentic.app.gateway.adapters import InboundMessage, OutboundMessage
from agentic.app.gateway.server import Gateway, get_adapter_gateway
from agentic.app.memory_retriever import get_memory_retriever
from agentic.app.reactions import add_reaction, remove_reaction
import json
import soundfile as sf

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Context variable to store the current chat ID for the memory retriever tool
chat_id_var = contextvars.ContextVar('chat_id')


async def send_periodic_chat_action(context, chat_id: int, stop_event: asyncio.Event, interval: float = 4.0):
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

class ChannelMetadata(BaseModel):
    chat_id: str = Field(description='Chat ID for channel')
    message_id: str = Field(description='Message ID for chat')

@Bean()
def getAgenticConfig() -> AgenticConfig:
    filename = getContextEnvironment(AGENTIC_FILE_NAME_PROP)
    try:
        if os.path.exists(filename):
            with open(filename, "r") as config_json:
                return AgenticConfig.model_validate(json.load(config_json))
    except Exception as e:
        raise e

    with open(filename, "w") as config_json:
        agentic = AgenticConfig(
            workspace="./workspace",
            skills=[
                SkillsConfig(name='superpowers', path='skills/superpowers')
            ],
            agents=[
                AgentConfig(
                    system_prompt_path="AGENTS.md",
                    workspace_dir="./workspace",
                    name="main",
                    model="openai:nvidia/nemotron-3-super-120b-a12b",
                    base_url="https://integrate.api.nvidia.com/v1",
                    tools=tuple([ToolConfig(name='run_shell_command', require_approval=True, approval_text="This tool needs approval to run"),
                                 ToolConfig(name='generate_image', require_approval=False),
                                 ToolConfig(name='swamp_sub_agent', require_approval=False)]),
                    denied_tools=tuple([])
                )
            ],
            mcpServers={
                "alice_mcps": {
                    "url": "http://host.docker.internal:8811/sse",
                    "transport": "sse",
                    "headers": {
                        "Authorization": "Bearer {}"
                    }
                },
                "agentic_mcp": {
                    "url": "http://host.docker.internal:8082/mcp",
                    "transport": "http"
                }
            }
        )

        json.dump(agentic.model_dump(mode="json"), fp=config_json, indent=4)

    return agentic




async def convert_ogg_to_mp3_async(input_path: str, output_path: str) -> None:
    process = await asyncio.create_subprocess_exec(
        # "ffmpeg", "--version",
        "ffmpeg", "-i", input_path, "-vn", "-ar", "44100", "-ac", "2",
        "-b:a", "192k", "-y", output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()}")



async def convert_wav_to_ogg_async(input_path: str, output_path: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", input_path, "-c:a", "libopus", "-b:a", "64k", "-y", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()}")



def main(application: Application,
         agentic_bot: AgenticBot,
         agentic_config: AgenticConfig,
         gateway: Gateway):
    agentic_bot.initialise_agent()

    tts_processor, tts_model, tts_vocoder, female_speaker_embedding = get_text_to_speech_pipeline()
    asr = get_speech_to_text_pipeline()
    main_agent = agentic_config.get_agent('main')
    model_config = agentic_config.get_model(main_agent.model_id)
    model = init_chat_model(
        model=model_config.model,
        base_url=model_config.base_url,
        api_key=model_config.api_key if type(model_config.api_key) is str else model_config.api_key.resolve()
    )

    async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message

        if message.voice:
            tg_file_obj = message.voice
            ext = "ogg"
        elif message.audio:
            tg_file_obj = message.audio
            ext = "mp3"
        else:
            return

        # Resolve file_id -> File (contains file_path / download URL)
        file = await context.bot.get_file(tg_file_obj.file_id)
        filename = f"downloads/{message.message_id}.{ext}"

        # --- Option A: simplest, PTB streams to disk for you internally ---
        await file.download_to_drive(custom_path=filename)
        logger.info("Saved via download_to_drive: %s", filename)

        result = asr(filename)
        speech_message = result["text"]

        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        inbound_msg = InboundMessage(
            message_id=str(message_id),
            channel="telegram",
            chat_id=str(chat_id),
            user_id=str(update.effective_user.id),
            text=speech_message,
            raw=update.to_dict()
        )

        response_text = await gateway.route_to_backend(inbound_msg)
        for response in response_text:
            await send_message(content=response)

        for text in response_text:
            target_words: int = 60
            out = await model.ainvoke([{
                "role": "user",
                "content": (
                    f"Summarize the following text to maximum {target_words} words for a "
                    f"text-to-speech voice reply. Use natural spoken phrasing, no bullet points, "
                    f"no markdown, no headers — just flowing sentences a person could listen to.\n\n{text}"
                )
            }])
            inputs = tts_processor(text=out.content, return_tensors="pt")
            speech = tts_model.generate_speech(inputs["input_ids"], female_speaker_embedding, vocoder=tts_vocoder)

            wav_path = f"downloads/tts_{update.message.message_id}.wav"
            sf.write(wav_path, speech.numpy(), samplerate=16000)

            # Telegram voice notes require .ogg/Opus — convert before sending
            ogg_path = wav_path.replace(".wav", ".ogg")
            await convert_wav_to_ogg_async(wav_path, ogg_path)

            with open(ogg_path, "rb") as f:
                await context.bot.send_voice(chat_id=update.message.chat_id, voice=f)


    async def send_message(chat_id, content):
        message_type = content.get('type', 'text')

        inbound_message = OutboundMessage(
            channel="telegram",
            chat_id=str(chat_id),
            text=content.get('text', ''),
            metadata= dict(
                type=message_type,
                content = dict(data=content.get('data', None)) if message_type == 'image' else {}
            )
        )
        async with httpx.AsyncClient() as client:
            await client.post(url=f"http://localhost:5000/webhook/{chat_id}/send",
                              json=inbound_message.model_dump(mode="json"))

    async def inbound_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stream response and update emoji reactions per token."""
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        user_message = update.message.text

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Create an event to stop the periodic chat action task
        # stop_event = asyncio.Event()

        try:
            # Set the chat ID in the context variable for the memory retriever tool
            chat_id_var.set(chat_id)

            # Initialize reaction to thinking
            await add_reaction(context, chat_id, message_id, "🤔")

            logger.info(f"[Chat {chat_id}] Invoking agent with message: {user_message[:100]}...")

            # Start periodic chat action task
            # chat_action_task = asyncio.create_task(send_periodic_chat_action(context, chat_id, stop_event))

            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            inbound_msg = InboundMessage(
                message_id=str(message_id),
                channel="telegram",
                chat_id=str(chat_id),
                user_id=str(update.effective_user.id),
                text=user_message,
                raw=update.to_dict()
            )
            try:
                # response_text = await agentic_bot.invoke_agent(full_message, chat_id=chat_id,message_id=message_id, channel_metadata={})
                response_text = await gateway.route_to_backend(inbound_msg)
                for response in response_text:
                    await send_message(chat_id=chat_id, content=response)
                if response_text:
                    logger.info(f"[Chat {chat_id}] Agent responded successfully")
                # Finalize with checkmark
                await remove_reaction(context, chat_id, message_id)
                await add_reaction(context, chat_id, message_id, "✅")

            except asyncio.TimeoutError:
                logger.error(f"[Chat {chat_id}] Agent call timed out after 120 seconds")
                await remove_reaction(context, chat_id, message_id)
                await add_reaction(context, chat_id, message_id, "⏱️")
                await update.message.reply_text(
                    "⏱️ Request took too long (>2 minutes). The NVIDIA API may be slow. Try again or use /clear to reset."
                )
            finally:
                # Stop the periodic chat action task
                # stop_event.set()
                await asyncio.sleep(0.1)  # Give task time to stop
                # if not chat_action_task.done():
                #     chat_action_task.cancel()

        except Exception as e:
            logger.error(f"[Chat {chat_id}] Agent streaming failed: {type(e).__name__}: {str(e)}", exc_info=True)
            await remove_reaction(context, chat_id, message_id)
            await add_reaction(context, chat_id, message_id, "❌")
            await update.message.reply_text(f"❌ Error: {type(e).__name__}\n\nTry using /clear to reset conversation.")


    """Start the bot."""
    chat_id = getContextEnvironment(TELEGRAM_BOT_DEFAULT_CHAT_ID, castFunc=int)
    chat_filter = filters.Chat(chat_id=[chat_id])
    application.add_handler(MessageHandler(chat_filter & filters.TEXT & ~filters.COMMAND, inbound_message))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    # Run the bot until the user presses Ctrl-C
    fast_app = get_adapter_gateway(gateway)
    fast_server = threading.Thread(target= lambda: uvicorn.run(fast_app, host="0.0.0.0", port=5000))
    fast_server.start()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

def run_bot():
    app = AppInitializer()
    app.componentScan("cndi.secrets")
    app.componentScan('agentic.app')
    app.run(onComplete=main)
if __name__ == "__main__":
    run_bot()