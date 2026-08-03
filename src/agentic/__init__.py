import click

from agentic.app.config import AgenticConfig
from agentic.cli.agents import add_agents_commands
from agentic.cli.config import add_config_commands
from agentic.cli.mcp import add_mcp_group
from agentic.cli.message import add_message_group


@click.group()
def cli():
    """Agentic CLI tool for managing the bot application.

    This command-line interface provides tools to:
    - Run the bot application server
    - Send messages via the bot
    - Manage configuration settings
    - Access Model Context Protocol tools
    """
    pass

@cli.command()
def run():
    """Start the bot app server.

    This command launches the bot application by executing bot_app.py.
    The server will continue running until interrupted (Ctrl+C).

    Example:
        agentic run
    """
    from agentic.app.config import AgenticConfig
    from agentic.bot_app import run_bot
    click.echo(f"Starting bot app server from...")
    run_bot()








def main():
    """Entry point for the Agentic CLI."""
    add_message_group(cli)
    add_mcp_group(cli)
    add_agents_commands(cli)
    add_config_commands(cli)
    cli()

if __name__ == '__main__':
    main()