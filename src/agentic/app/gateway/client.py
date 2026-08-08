from agentic.app.gateway.adapters import InboundMessage


class BotClient:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id

    async def send_message(self, message: InboundMessage) -> dict:
        # Logic to send a message to the bot and receive a response
        response = {
            "bot_id": self.bot_id,
            "message": message,
            "response": "This is a mock response from the bot."
        }
        return response

    async def get_bot_status(self) -> dict:
        # Logic to get the status of the bot
        status = {
            "bot_id": self.bot_id,
            "status": "active"
        }
        return status