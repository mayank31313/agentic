import json
import os
import sys
import urllib.error
import urllib.request

import click


@click.group()
def tools():
    """Manage runtime tools for a running Agentic bot.

    Includes triggering a live reload of MCP/sub-agent/agent-authored
    custom tools on a running bot process, and managing agent-authored
    custom tools (list/inspect/approve/remove) directly on disk under
    `<workspace>/custom_tools/`.
    """


def _load_agentic_config(file):
    from agentic.app.config import AgenticConfig

    with open(file, "r") as config_file:
        config_data = json.load(config_file)
    return AgenticConfig.model_validate(config_data)


@tools.command(name="reload")
@click.option(
    "--url",
    default=lambda: os.environ.get("AGENTIC_GATEWAY_URL", "http://localhost:5000"),
    help="Base URL of the running bot's gateway (default: $AGENTIC_GATEWAY_URL or http://localhost:5000).",
)
@click.option(
    "--token",
    default=lambda: os.environ.get("AGENTIC_ADMIN_TOKEN"),
    help="Admin token to send as X-Admin-Token (default: $AGENTIC_ADMIN_TOKEN).",
)
def reload_tools(url, token):
    """Trigger a running bot to refresh MCP/sub-agent/custom tools and
    rebuild its compiled agent graph, without a full process restart.

    NOTE: this drops any in-flight conversation state for the running
    agent (a fresh in-memory checkpointer is created) — prefer running
    this between conversations rather than mid-task.

    Example:
        agentic tools reload
        agentic tools reload --url http://localhost:5000 --token secret
    """
    endpoint = f"{url.rstrip('/')}/admin/tools/reload"
    req = urllib.request.Request(endpoint, method="POST", data=b"")
    if token:
        req.add_header("X-Admin-Token", token)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        click.echo(f"Reload failed ({e.code}): {detail}", err=True)
        sys.exit(1)
    except urllib.error.URLError as e:
        click.echo(f"Failed to reach bot at {endpoint}: {e.reason}", err=True)
        sys.exit(1)

    click.echo("Tools reloaded:")
    for kind, names in body.get("reloaded", {}).items():
        names = names or []
        click.echo(f"  {kind}: {len(names)} -> {', '.join(names) if names else '(none)'}")


@tools.group(name="custom")
def custom():
    """Manage agent-authored custom tools under `<workspace>/custom_tools/`.

    Includes list/inspect/edit/approve/remove.
    """


@custom.command(name="list")
@click.argument("file", type=click.Path(exists=True), default=os.environ.get("AGENTIC_CONFIG", "resources/agentic.json"))
def list_custom(file):
    """List agent-authored custom tools and their approval status.

    Example:
        agentic tools custom list
    """
    from agentic.app.common.custom_tools import CustomToolLoader

    agentic_config = _load_agentic_config(file)
    loader = CustomToolLoader(agentic_config.workspace)
    specs = loader.list_specs()
    if not specs:
        click.echo(f"No custom tools found under '{agentic_config.workspace}/custom_tools/'.")
        return

    for spec in specs:
        status = "approved" if spec.approved else "PENDING APPROVAL"
        click.echo(f"{spec.name} [{spec.kind}] - {status}")
        click.echo(f"  Description: {spec.description}")
        click.echo(f"  Created: {spec.created_at} by {spec.created_by or 'unknown'}")
        click.echo("-" * 30)


@custom.command(name="inspect")
@click.argument("name")
@click.argument("file", type=click.Path(exists=True), default=os.environ.get("AGENTIC_CONFIG", "resources/agentic.json"))
def inspect_custom(name, file):
    """Print a custom tool's spec and generated source/Dockerfile for review.

    Example:
        agentic tools custom inspect my_tool
    """
    from pathlib import Path

    from agentic.app.common.custom_tools import CustomToolLoader

    agentic_config = _load_agentic_config(file)
    loader = CustomToolLoader(agentic_config.workspace)
    try:
        specs = {s.name: s for s in loader.list_specs()}
        spec = specs[name]
    except KeyError:
        click.echo(f"No custom tool named '{name}' found.", err=True)
        sys.exit(1)

    tool_dir = Path(agentic_config.workspace) / "custom_tools" / name
    click.echo(spec.model_dump_json(indent=2))
    click.echo("-" * 30)
    if spec.kind == "python":
        click.echo((tool_dir / "tool.py").read_text(encoding="utf-8"))
    else:
        click.echo("# Dockerfile")
        click.echo((tool_dir / "Dockerfile").read_text(encoding="utf-8"))
        click.echo("# entrypoint")
        click.echo((tool_dir / "entrypoint").read_text(encoding="utf-8"))


@custom.command(name="approve")
@click.argument("name")
@click.argument("file", type=click.Path(exists=True), default=os.environ.get("AGENTIC_CONFIG", "resources/agentic.json"))
def approve_custom(name, file):
    """Promote a custom tool out of the mandatory per-call approval gate.

    After a human has reviewed the tool's source/Dockerfile (see
    `agentic tools custom inspect`), this stops it from requiring
    interactive approval on every call. Run `agentic tools reload`
    afterwards for a running bot to pick up the change.

    Example:
        agentic tools custom approve my_tool
    """
    from agentic.app.common.custom_tools import CustomToolLoader

    agentic_config = _load_agentic_config(file)
    loader = CustomToolLoader(agentic_config.workspace)
    try:
        loader.approve(name)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    click.echo(f"Custom tool '{name}' approved. Run 'agentic tools reload' to apply.")


@custom.command(name="edit")
@click.argument("name")
@click.option("--description", default=None, help="New description; omit to leave unchanged.")
@click.option(
    "--tool-args",
    "tool_args_json",
    default=None,
    help='New argument schema as a JSON object, e.g. \'{"x": "integer"}\'; omit to leave unchanged.',
)
@click.option(
    "--python-source",
    "python_source_path",
    default=None,
    help="Workspace-relative path to the FULL new python source (kind='python' tools only); omit to leave unchanged.",
)
@click.option(
    "--dockerfile",
    "dockerfile_path",
    default=None,
    help="Workspace-relative path to the FULL new Dockerfile (kind='docker' tools only); omit to leave unchanged.",
)
@click.option(
    "--entrypoint",
    "entrypoint_path",
    default=None,
    help="Workspace-relative path to the FULL new entrypoint script (kind='docker' tools only); omit to leave unchanged.",
)
@click.option(
    "--network-access/--no-network-access",
    "network_access",
    default=None,
    help="Docker kind only: allow/disallow container network access; omit to leave unchanged.",
)
@click.option("--timeout-seconds", type=int, default=None, help="Omit to leave unchanged.")
@click.argument("file", type=click.Path(exists=True), default=os.environ.get("AGENTIC_CONFIG", "resources/agentic.json"))
def edit_custom(
    name,
    description,
    tool_args_json,
    python_source_path,
    dockerfile_path,
    entrypoint_path,
    network_access,
    timeout_seconds,
    file,
):
    """Edit/update an existing custom tool's metadata and/or source.

    Only the options you pass are changed; everything else is left as-is.
    Source is always read from a file already on disk under the
    workspace (write it first, e.g. with a text editor or your agent's
    filesystem tool) — this command never accepts inline source content,
    matching `create_custom_tool`. You cannot change a tool's 'kind' or
    'name' this way; remove and re-create it instead.

    Any edit — even metadata-only — resets the tool's approval gate, so
    it will require interactive approval on every call again until you
    re-review it (`agentic tools custom inspect`) and re-run
    `agentic tools custom approve`. Run `agentic tools reload` afterwards
    for a running bot to pick up the change.

    Examples:
        agentic tools custom edit my_tool --description "New description"
        agentic tools custom edit my_tool --python-source custom_tools/my_tool/tool_v2.py
        agentic tools custom edit my_tool --tool-args '{"x": "integer", "y": "integer"}'
    """
    from agentic.app.common.custom_tools import update_custom_tool

    tool_args = None
    if tool_args_json is not None:
        try:
            tool_args = json.loads(tool_args_json)
        except json.JSONDecodeError as e:
            click.echo(f"--tool-args is not valid JSON: {e}", err=True)
            sys.exit(1)

    agentic_config = _load_agentic_config(file)
    try:
        update_custom_tool(
            workspace=agentic_config.workspace,
            name=name,
            description=description,
            tool_args=tool_args,
            python_source_path=python_source_path,
            dockerfile_path=dockerfile_path,
            entrypoint_path=entrypoint_path,
            network_access=network_access,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as e:
        click.echo(f"Update failed: {e}", err=True)
        sys.exit(1)

    click.echo(
        f"Custom tool '{name}' updated. It now requires approval on every call again "
        f"until you run 'agentic tools custom approve {name}'. Run 'agentic tools reload' "
        "to apply to a running bot."
    )


@custom.command(name="remove")
@click.argument("name")
@click.argument("file", type=click.Path(exists=True), default=os.environ.get("AGENTIC_CONFIG", "resources/agentic.json"))
def remove_custom(name, file):
    """Delete a custom tool's files from `<workspace>/custom_tools/<name>/`.

    Example:
        agentic tools custom remove my_tool
    """
    from agentic.app.common.custom_tools import CustomToolLoader

    agentic_config = _load_agentic_config(file)
    loader = CustomToolLoader(agentic_config.workspace)
    try:
        loader.remove(name)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    click.echo(f"Custom tool '{name}' removed. Run 'agentic tools reload' to apply.")


def add_tools_commands(cli):
    """Add the tools command group to the main CLI."""
    cli.add_command(tools)

