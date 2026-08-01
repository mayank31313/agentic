import asyncio
import contextvars
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Optional, List

from cndi.annotations.events import EventBus
from cndi.env import getContextEnvironment
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, Interrupt
from pydantic import BaseModel, Field

from app.channels.telegram import TelegramToolNotifierMiddleware, ToolsRegistry
from cndi.initializers import AppInitializer
from cndi.annotations import Component
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
    AsyncCallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool, tool
from telegram import Update, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode

from src.app.agents import get_main_agent
from app.config import AgentConfig, AgenticConfig
from app.constants import TELEGRAM_BOT_DEFAULT_CHAT_ID
from app.memory_compaction import create_memory_compaction_agent
from app.memory_retriever import get_memory_retriever
from app.reactions import add_reaction, remove_reaction
from app.stable_diffusion.tools import LocalAiApi, ImageGenerationRequest
import json

logging.getLogger('cndi').setLevel('DEBUG')
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Context variable to store the current chat ID for the memory retriever tool
chat_id_var = contextvars.ContextVar('chat_id')

os.environ['OPENAI_API_BASE'] = 'https://integrate.api.nvidia.com/v1'
os.environ['OPENAI_API_KEY'] = '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'

class MemoryRetrieverTool(BaseTool):
    name: str = "memory_retriever"
    description: str = "Search past conversations for relevant information given a query."

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        raise NotImplementedError("This tool must be used asynchronously.")

    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        chat_id = chat_id_var.get()
        result = await memory_retriever.search_relevant_messages(chat_id, query, limit=3)
        return result

memory_retriever_tool = MemoryRetrieverTool()
conversation_memory = defaultdict(list)



def add_to_memory(chat_id: int, role: str, content: str) -> None:
    """Add a message to conversation memory."""
    message_index = len(conversation_memory[chat_id])
    conversation_memory[chat_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    # Also index in Elasticsearch
    try:
        memory_retriever.add_message(chat_id, role, content, message_index)
    except Exception as e:
        logger.debug(f"Failed to index message in memory retriever: {e}")

def get_memory(chat_id: int, max_messages: int = 20) -> list:
    """Get the last N messages from conversation memory."""
    messages = conversation_memory[chat_id]
    # Keep only the last max_messages to avoid token limits
    return messages[-max_messages:] if len(messages) > max_messages else messages

def clear_memory(chat_id: int) -> None:
    """Clear conversation memory for a specific chat."""
    if chat_id in conversation_memory:
        del conversation_memory[chat_id]

def format_memory_for_agent(memory: list) -> str:
    """Format conversation memory into a string for the agent."""
    if not memory:
        return ""

    formatted = "Previous conversation:\n"
    for msg in memory:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted += f"{role}: {msg['content']}\n"
    return formatted


def estimate_tokens(text: str) -> int:
    """Rough estimate of token count (approximately 1 token per 4 characters)."""
    return len(text) // 4


def count_memory_tokens(memory: list) -> int:
    """Count approximate tokens in memory."""
    total = 0
    for msg in memory:
        total += estimate_tokens(msg['content'])
    return total


async def retrieve_relevant_context(chat_id: int, query: str, limit: int = 3) -> str:
    """
    Retrieve relevant context from past conversations using semantic search.

    Args:
        chat_id: Chat ID to search
        query: Query to search for
        limit: Maximum number of results

    Returns:
        Formatted relevant context string
    """
    try:
        # Search for relevant messages
        results = await memory_retriever.search_relevant_messages(chat_id, query, limit)

        if not results:
            return ""

        context = "Relevant past context:\n"
        for result in results:
            role = "User" if result.get("role") == "user" else "Assistant"
            content = result.get("content", "")[:200]  # Limit to 200 chars per message
            context += f"- {role}: {content}\n"

        return context

    except Exception as e:
        logger.debug(f"Failed to retrieve relevant context: {e}")
        return ""

memory_compaction_agent = create_memory_compaction_agent()
memory_retriever = get_memory_retriever(es_host="localhost", es_port=9200, enabled=True)




async def compact_memory_with_agent(chat_id: int, max_tokens: int = 2000) -> bool:
    """
    Compact old messages using the memory compaction agent.
    Returns True if compaction was performed, False otherwise.
    """
    memory = conversation_memory[chat_id]
    token_count = count_memory_tokens(memory)

    # If under limit, no need to compact
    if token_count < max_tokens or len(memory) <= 5:
        return False

    logger.info(f"[Chat {chat_id}] Memory compaction triggered: {token_count} tokens ({len(memory)} messages)")

    try:
        # Keep last 5 messages (recent conversation)
        recent_messages = memory[-5:]
        old_messages = memory[:-5]

        # Format old conversation for the compaction agent
        old_conversation = format_memory_for_agent(old_messages)

        # Use memory compaction agent to summarize
        compaction_prompt = f"""Summarize this conversation history into key bullet points:

{old_conversation}

Provide only the bullet points summary, no extra text."""

        logger.debug(f"[Chat {chat_id}] Calling memory compaction agent...")

        try:
            summary_output = await asyncio.wait_for(
                memory_compaction_agent.ainvoke(dict(messages=compaction_prompt)),
                timeout=30.0
            )

            # Extract summary from agent output
            summary = ""
            for message in summary_output.get('messages', []):
                for content in message.content if hasattr(message, 'content') else []:
                    if type(content) == dict and content.get('type') == 'text':
                        summary += content['text']

            if not summary:
                summary = old_conversation

        except asyncio.TimeoutError:
            logger.warning(f"[Chat {chat_id}] Memory compaction agent timed out, using automatic summary")
            # Fallback to automatic summary
            topics = []
            for msg in old_messages:
                content = msg['content'].split('.')[0]
                if len(content) > 10:
                    topics.append(content[:100])
            summary = "[SUMMARY] Key topics: " + "; ".join(topics[:5])

        # Replace old messages with summary
        conversation_memory[chat_id] = [
            {
                "role": "system",
                "content": summary,
                "timestamp": datetime.now().isoformat(),
                "is_summary": True
            }
        ] + recent_messages

        new_token_count = count_memory_tokens(conversation_memory[chat_id])
        logger.info(
            f"[Chat {chat_id}] Memory compacted: {token_count} → {new_token_count} tokens. "
            f"Kept {len(recent_messages)} recent messages, summarized {len(old_messages)} old messages."
        )
        return True

    except Exception as e:
        logger.error(f"[Chat {chat_id}] Memory compaction failed: {e}", exc_info=True)
        return False


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


os.environ['TAVILY_API_KEY'] = "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"

class ChannelMetadata(BaseModel):
    chat_id: str = Field(description='Chat ID for channel')
    message_id: str = Field(description='Message ID for chat')


@Component
class AgenticBot:
    def __init__(self, agenticConfig: AgenticConfig,
                 telegram_tool_middleware: TelegramToolNotifierMiddleware,
                 event_bus: EventBus,
                 tool_registry: ToolsRegistry
                 ):
        self.middelwares = [telegram_tool_middleware]
        self.max_approvals = 5
        self.agentConfig: AgentConfig = next(filter(lambda x: x.name == 'main',agenticConfig.agents))
        self.tool_registry = tool_registry
        self.event_bus = event_bus
        self.agent = None
        self.content_ids = set()

    def initialise_agent(self):
        runnable_tools, approvable_tools = [], []
        for tool_config in self.agentConfig.tools:
            if tool_config.require_approval:
                approvable_tools.append(tool_config)

        tools = list(filter(lambda x: x.name not in self.agentConfig.denied_tools, self.tool_registry.tools.values()))

        if len(tools) > 0:
            logger.info("Available tools in context")
            for i, t in enumerate(tools):
                logger.info(f"{i}: {t}")


        self.agent = get_main_agent(agent_config=self.agentConfig,
                                    tools=tools,
                                    tools_need_approval=approvable_tools,
                                    middlewares=self.middelwares)

    async def send_message(self, content, update_object):
        response_text = ""
        if content.get('type') == 'text':
            response_text += content['text']
            try:
                await update_object.message.reply_text(
                    content['text'],
                    parse_mode=ParseMode.MARKDOWN,
                )
            except BadRequest as bad_request_error:
                logger.error(f"Failed to send message: {bad_request_error}")
                await update_object.message.reply_text(
                    content['text']
                )
        if content.get('type') == 'image':
            with open(content.get('data'), 'rb') as file:
                await update_object.message.reply_photo(photo=file)
        return response_text

    async def invoke_agent(self, message, update: Update,
                           channel_metadata: dict):
        chat_id = update.effective_chat.id
        message_id = update.message.message_id

        config = {"configurable": {"thread_id": chat_id}}
        if message.startswith('$decision'):
            _, decision = message.split(' ')
            await update.message.reply_text(
                text=f"Decision captured {decision}",
                reply_markup=ReplyKeyboardRemove(),
            )
            output = await self.agent.ainvoke(Command(resume={"decisions": [dict(type=decision)]}), config=config)
        else:
            output = await self.agent.ainvoke(dict(messages=message), config=config)

        if  "__interrupt__" in output:
            interrupt_data: list[Interrupt] = output["__interrupt__"]
            review_configs = interrupt_data[0].value['review_configs']
            action_requests = interrupt_data[0].value['action_requests']

            keyboard_buttons = [[f"$decision {decision}"] for decision in review_configs[0]['allowed_decisions']]
            logger.info(interrupt_data)
            await update.message.reply_text(f"""Tool Called Request Interrupt
Tool Name: {action_requests[0]['name']}
Args: {action_requests[0]['args']}    
""")
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, one_time_keyboard=True, resize_keyboard=True)

            await update.message.reply_text(f"{action_requests[0]['description']}",
                                            reply_markup=keyboard, reply_to_message_id=message_id)

        # Extract and send response
        response_text = ""
        for message in output['messages']:
            logger.info(f"[Chat {chat_id}] Agent response: {message}")
            if message.id in self.content_ids:
                logger.debug(f"[Chat {chat_id}] Skipping duplicate message ID: {message.id}")
                continue
            self.content_ids.add(message.id)
            if type(message) == ToolMessage and message.content.startswith('json:'):
                contents = json.loads(message.content[5:])
                for content in contents:
                    await self.send_message(content, update)
            if type(message) == AIMessage and message.content != '':
                content = dict(text=message.content, type='text')
                await self.send_message(content, update)
            if type(message) in [list ,tuple]:
                for content in message.content:
                    if type(content) == dict:
                        await self.send_message(content, update)

        return response_text

def main(application: Application,
         agentic_bot: AgenticBot,
         localai: LocalAiApi):
    agentic_bot.initialise_agent()




    # data = asyncio.run(localai.generate_image_to_image_as_task(ImageGenerationRequest(
    #     prompt="Fix the finger in the image to make it look natural and realistic.",
    #     negative_prompt="blurry, low quality, distorted, unnatural, unrealistic, deformed, mutated, extra fingers, missing fingers",
    #     init_image_path="images/3f6c7685-6052-4604-8246-c66ee27a7266-0.png"
    # )))
    # logger.info(f"Image generation response: {data}")
    async def inbound_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stream response and update emoji reactions per token."""
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        user_message = update.message.text

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Create an event to stop the periodic chat action task
        stop_event = asyncio.Event()

        try:
            # Set the chat ID in the context variable for the memory retriever tool
            chat_id_var.set(chat_id)

            # Initialize reaction to thinking
            await add_reaction(context, chat_id, message_id, "🤔")

            # Add user message to memory
            add_to_memory(chat_id, "user", user_message)

            # Compact memory if needed (using memory compaction agent)
            await compact_memory_with_agent(chat_id, max_tokens=2000)

            # Get conversation history (only recent memory, no explicit retrieval)
            memory = get_memory(chat_id)
            memory_context = format_memory_for_agent(memory)

            # Prepare messages with context (only the recent memory)
            # full_message = f"{memory_context}\nCurrent message: {user_message}"

            full_message = f"{user_message}"
            logger.info(f"[Chat {chat_id}] Invoking agent with message: {user_message[:100]}...")

            # Start periodic chat action task
            chat_action_task = asyncio.create_task(send_periodic_chat_action(context, chat_id, stop_event))

            try:
                response_text = await agentic_bot.invoke_agent(full_message, update=update, channel_metadata={})
                if response_text:
                    add_to_memory(chat_id, "assistant", response_text)
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
                stop_event.set()
                await asyncio.sleep(0.1)  # Give task time to stop
                if not chat_action_task.done():
                    chat_action_task.cancel()

        except Exception as e:
            logger.error(f"[Chat {chat_id}] Agent streaming failed: {type(e).__name__}: {str(e)}", exc_info=True)
            await remove_reaction(context, chat_id, message_id)
            await add_reaction(context, chat_id, message_id, "❌")
            await update.message.reply_text(f"❌ Error: {type(e).__name__}\n\nTry using /clear to reset conversation.")


    """Start the bot."""
    chat_id = getContextEnvironment(TELEGRAM_BOT_DEFAULT_CHAT_ID, castFunc=int)
    chat_filter = filters.Chat(chat_id=[chat_id])
    application.add_handler(MessageHandler(chat_filter & filters.TEXT & ~filters.COMMAND, inbound_message))
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    app = AppInitializer()
    app.componentScan("cndi.secrets")
    app.componentScan('app')
    app.run(onComplete=main)