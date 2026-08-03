import click
import json
import sys


@click.group()
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

def add_agents_commands(cli):
    """Add the agents command group to the main CLI."""
    cli.add_command(agents)