import click


@click.group()
def message():
    """Send messages via the bot.

    This group contains commands for sending different types of messages
    through the bot application.
    """


@message.command()
@click.argument("text", type=str)
def add(text):
    """Send a text message.

    Sends the provided text message through the bot to the configured
    destination (e.g., Telegram channel, group, or private chat).

    ARGUMENTS:
        TEXT  The message text to send

    Example:
        agentic message add "Hello, this is a test message"
    """
    click.echo(f"Preparing to send message: {text}")
    # TODO: Implement actual message sending logic here
    # This would typically involve calling the bot's message sending function
    click.echo("Message sent! (placeholder)")


def add_message_group(cli):
    """Add the 'message' command group to the main CLI."""
    cli.add_command(message)
