import logging

logger = logging.getLogger(__name__)


async def add_reaction(context, chat_id: int, message_id: int, emoji: str):
    """Add an emoji reaction to a message."""
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id, reaction=[emoji], is_big=False
        )
    except Exception as e:
        logger.debug(f"Failed to add reaction: {e}")


async def remove_reaction(context, chat_id: int, message_id: int):
    """Remove all reactions from a message."""
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id, reaction=[]
        )
    except Exception as e:
        logger.debug(f"Failed to remove reaction: {e}")
