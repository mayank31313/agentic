
def get_agentic_commands(channel: str):
    async def help():
        return "Available commands:\n"

    return {
        "help": help,
    }