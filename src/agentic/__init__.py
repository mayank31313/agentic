import click
import subprocess
import sys
from pathlib import Path

import json

from jsonpath_ng import parse

from agentic.app.config import AgenticConfig


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



@cli.group()
def message():
    """Send messages via the bot.

    This group contains commands for sending different types of messages
    through the bot application.
    """
    pass


@message.command()
@click.argument('text', type=str)
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


@cli.group()
def config():
    """Get or Set Config properties for Bot.

    This group provides commands to inspect and modify the bot's
    configuration stored in agentic.json or other JSON configuration files.
    """
    pass


@config.command()
@click.argument('key_path', type=str, required=True)
@click.argument('file', type=click.Path(exists=True), default='agentic.json')
def get(key_path, file):
    """Get value of agentic config using key path.

    Retrieves a value from the bot's configuration using a JSONPath expression.

    ARGUMENTS:
        KEY_PATH  JSONPath expression to locate the desired configuration value
                  (e.g., 'telegram.bot_token', 'agents.[0].name')

    OPTIONS:
        FILE      Path to the configuration file (default: agentic.json)

    Example:
        agentic config get telegram.bot_token
        agentic config get agents.[0].name custom_config.json
    """
    with open(file, 'r') as config:
        value = AgenticConfig.model_validate(json.load(config)).model_dump(mode='json')

        jsonpath_expression = parse(key_path)

        for match in jsonpath_expression.find(value):
            click.echo(json.dumps(match.value, indent=2))


@config.command()
@click.argument('key_path', type=str, required=True)
@click.option("--set", "sets", multiple=True, help="key=value pairs to set, repeatable", required=True)
@click.argument('file', type=click.Path(exists=True), default='agentic.json')
def set(key_path, sets, file):
    """Set value at key_path for a bot config.

    Updates one or more values in the bot's configuration using JSONPath expressions.

    ARGUMENTS:
        KEY_PATH  JSONPath expression indicating where to set the values
                  (e.g., 'telegram.bot_token', 'agents.[0].name')

    OPTIONS:
        --set     Key=value pairs to set (can be used multiple times)
                  Example: --set telegram.bot_token=123:ABC --set agents.[0].name=Assistant

    EXAMPLES:
        agentic config set telegram.bot_token --set telegram.bot_token=123:ABC
        agentic config set agents.[0].name --set agents.[0].name=Assistant --set agents.[0].model=gpt-4
    """
    data = {}
    for item in sets:
        key, value = item.split("=", 1)
        data[key] = value
    with open(file, 'r') as config:
        value = AgenticConfig.model_validate(json.load(config)).model_dump(mode='json')

    jsonpath_expression = parse(key_path)
    jsonpath_expression.update(value, data)

    click.echo(json.dumps(AgenticConfig.model_validate(value).model_dump(mode='json'), indent=2))


@config.command()
def schema():
    """Get Agentic Bot Json Schema.

    Outputs the JSON schema for the AgenticBot configuration model.
    This schema describes the structure and data types expected in the
    configuration file.

    Example:
        agentic config schema
    """
    click.echo(json.dumps(AgenticConfig.model_json_schema(), indent=2))


@cli.group()
def mcp():
    """Model Context Protocol tools.

    This group contains commands for interacting with the Model Context
    Protocol (MCP) implementation in the Agentic framework.
    """
    pass

@mcp.command()
def run():
    """Start the Model Context Protocol (MCP) server.

    This command launches the MCP server, which allows for interaction with
    the Model Context Protocol implementation in the Agentic framework.

    Example:
        agentic mcp
    """
    from agentic.agentic_mcp import main as run_mcp

    click.echo("Starting MCP server...")
    run_mcp()

@mcp.command()
def list():
    """List all available tools.

    Displays a hierarchical list of all available CLI commands and subcommands.
    This is useful for discovering what functionality is available in the Agentic CLI.

    Example:
        agentic mcp list
    """

    def list_commands(cmd, indent=0):
        if hasattr(cmd, 'commands'):
            for name, subcmd in cmd.commands.items():
                click.echo(' ' * indent + f"{name}")
                if hasattr(subcmd, 'commands'):
                    list_commands(subcmd, indent + 2)

    click.echo("Available tools:")
    list_commands(cli)


@cli.group()
def agents():
    """Manage and run AI agents.

    This group provides commands to list available agents, run specific agents,
    and manage agent configurations.
    """
    pass


@agents.command()
def list():
    """List all available agents.

    Displays a list of all configured agents from the agentic.json configuration
    file along with their basic information such as name, model, and tools.

    Example:
        agentic agents list
    """
    try:
        with open('../agentic.json', 'r') as config_file:
            config_data = json.load(config_file)

        agents = config_data.get('agents', [])
        if not agents:
            click.echo("No agents found in configuration.")
            return

        click.echo("Available Agents:")
        click.echo("=" * 50)
        for agent in agents:
            name = agent.get('name', 'Unknown')
            model = agent.get('model', 'Unknown')
            tools_count = len(agent.get('tools', []))
            click.echo(f"Name: {name}")
            click.echo(f"  Model: {model}")
            click.echo(f"  Tools: {tools_count} configured")
            click.echo("-" * 30)
    except FileNotFoundError:
        click.echo("Configuration file 'agentic.json' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading agents: {e}", err=True)
        sys.exit(1)


@agents.command()
@click.argument('agent_name')
@click.option('--task', '-t', help='Task description for the agent to perform')
def run(agent_name, task):
    """Run a specific agent with an optional task.

    Executes the specified agent with the given task description. If no task
    is provided, the agent will start in interactive mode.

    ARGUMENTS:
        AGENT_NAME  Name of the agent to run (as defined in agentic.json)

    OPTIONS:
        --task, -t  Task description for the agent to perform

    Examples:
        agentic agents run main
        agentic agents run main -t "Analyze the sales data for Q3"
        agentic agents run image_generator -t "Create a logo for a tech startup"
    """
    try:
        # Import here to avoid circular imports
        from agentic.app import get_main_agent
        from agentic.app.config import AgenticConfig

        # Load configuration
        with open('../agentic.json', 'r') as config_file:
            config_data = json.load(config_file)

        # Find the specified agent
        agent_config = None
        for agent in config_data.get('agents', []):
            if agent.get('name') == agent_name:
                agent_config = agent
                break

        if not agent_config:
            click.echo(f"Agent '{agent_name}' not found in configuration.", err=True)
            click.echo(
                "Available agents: " + ", ".join([a.get('name', 'Unknown') for a in config_data.get('agents', [])]))
            sys.exit(1)

        # Convert to AgenticConfig object
        config_obj = AgenticConfig(**config_data)

        click.echo(f"Starting agent '{agent_name}'...")
        if task:
            click.echo(f"Task: {task}")
        else:
            click.echo("Starting in interactive mode. Send messages to interactively.")

        # TODO: Implement actual agent execution logic here would call to run
        click.echo("Agent execution would start here... (placeholder)")
        click.echo("Note: Actual agent execution logic needs to be implemented.")

    except FileNotFoundError:
        click.echo("Configuration file 'agentic.json' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error running agent: {e}", err=True)
        sys.exit(1)

def main():
    """Entry point for the Agentic CLI."""
    cli()

if __name__ == '__main__':
    main()