import logging

logger = logging.getLogger(__name__)
async def add_reaction(context, chat_id: int, message_id: int, emoji: str):
    """Add an emoji reaction to a message."""
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[emoji],
            is_big=False
        )
    except Exception as e:
        logger.debug(f"Failed to add reaction: {e}")

async def remove_reaction(context, chat_id: int, message_id: int):
    """Remove all reactions from a message."""
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[]
        )
    except Exception as e:
        logger.debug(f"Failed to remove reaction: {e}")

class StreamingReactionHandler():
    """Callback handler to update Telegram reactions as agent streams."""

    def __init__(self, context, chat_id: int, message_id: int):
        self.context = context
        self.chat_id = chat_id
        self.message_id = message_id
        self.step_count = 0

    async def on_agent_start(self, **kwargs):
        """Called when agent starts."""
        await add_reaction(self.context, self.chat_id, self.message_id, "🤔")
        logger.info("Agent started")

    async def on_agent_step(self, **kwargs):
        """Called on each agent step/iteration."""
        self.step_count += 1
        # Cycle through processing emojis
        emojis = ["🤔", "⚙️", "🔄", "💭"]
        emoji = emojis[self.step_count % len(emojis)]
        await add_reaction(self.context, self.chat_id, self.message_id, emoji)
        logger.info(f"Agent step {self.step_count}")

    async def on_agent_finish(self, **kwargs):
        """Called when agent finishes."""
        await remove_reaction(self.context, self.chat_id, self.message_id)
        await add_reaction(self.context, self.chat_id, self.message_id, "✅")
        logger.info("Agent finished")

    async def on_chain_error(self, **kwargs):
        """Called on error."""
        await remove_reaction(self.context, self.chat_id, self.message_id)
        await add_reaction(self.context, self.chat_id, self.message_id, "⚠️")
        logger.error("Agent error")