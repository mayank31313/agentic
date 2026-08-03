import click


@click.group()
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

def add_mcp_group(cli):
    """Add the 'mcp' command group to the main CLI."""
    cli.add_command(mcp)