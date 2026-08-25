import json
import os
import sys

import click


@click.group()
def agents():
    """Manage and run AI agents.

    This group provides commands to list available agents, run specific agents,
    and manage agent configurations.
    """


def _load_agentic_config(file):
    """Load and validate an AgenticConfig from a JSON config file path."""
    # Import here to avoid circular imports
    from agentic.app.config import AgenticConfig

    with open(file, "r") as config_file:
        config_data = json.load(config_file)
    return AgenticConfig.model_validate(config_data)


@agents.command()
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
def list(file):
    """List all available agents.

    Discovers agents by scanning `<workspace>/agents/*/instructions.md`
    (the actual runtime source of truth — see
    docs/creating-agents-and-skills.md) rather than any bookkeeping list in
    the JSON config file, and prints their name, description, model, and
    tool/skill counts.

    ARGUMENTS:
        FILE  Path to the agentic config file (default: agentic.json)

    Example:
        agentic agents list
    """
    try:
        agentic_config = _load_agentic_config(file)
    except FileNotFoundError:
        click.echo(f"Configuration file '{file}' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    results = agentic_config.list_agents()
    if not results:
        click.echo(f"No agents found under '{agentic_config.workspace}/agents/'.")
        return

    click.echo("Available Agents:")
    click.echo("=" * 50)
    for name, agent_config, error in results:
        if error is not None:
            click.echo(f"Name: {name}")
            click.echo(f"  Error: Failed to load agent ({error})", err=True)
            click.echo("-" * 30)
            continue

        click.echo(f"Name: {agent_config.name}")
        click.echo(f"  Description: {agent_config.description}")
        click.echo(f"  Model: {agent_config.model_id}")
        click.echo(f"  Tools: {len(agent_config.tools or ())} configured")
        click.echo(f"  Skills: {len(agent_config.skills or [])} configured")
        click.echo("-" * 30)


@agents.command()
def schema():
    """Get the AgentConfig JSON Schema.

    Outputs the JSON schema for the `AgentConfig` pydantic model
    (src/agentic/app/config.py). This is the model that the JSON header of
    every `workspace/agents/<name>/instructions.md` file must validate
    against, so use this command to generate or verify that header
    precisely instead of guessing field names/types. See also
    `agentic config schema` for the top-level `AgenticConfig` schema
    (models/tools/mcpServers).

    Example:
        agentic agents schema
    """
    from agentic.app.config import AgentConfig

    click.echo(json.dumps(AgentConfig.model_json_schema(), indent=2))


def _resolve_text(source):
    """Resolve a CLI option value that may be a file path or an inline string.

    Reads with `utf-8-sig` so a UTF-8 BOM (common when files are saved by
    Windows editors) doesn't break `json.loads` on the config header.
    """
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8-sig") as f:
            return f.read()
    return source


def _build_and_validate_agent_config(agentic_config, agent_name, config_data, instructions_text):
    """Validate an agent's JSON header + instructions body, returning (agent_config, errors)."""
    from pydantic import ValidationError

    from agentic.app.config import AgentConfig

    # Avoid the tools/skills default_factory edge case in AgentConfig by
    # always supplying explicit values, matching every existing agent.
    config_data.setdefault("tools", [])
    config_data.setdefault("skills", [])
    config_data.setdefault("denied_tools", [])

    errors = []
    if config_data.get("name") != agent_name:
        errors.append(
            f"'name' field ({config_data.get('name')!r}) must match "
            f"AGENT_NAME ({agent_name!r})."
        )
    if not instructions_text or not instructions_text.strip():
        errors.append("Instructions body is empty; the system prompt must not be blank.")

    model_id = config_data.get("model_id")
    if model_id is not None and agentic_config.get_model(model_id) is None:
        errors.append(f"model_id '{model_id}' is not defined in the agentic config's 'models' list.")

    agent_config = None
    try:
        agent_config = AgentConfig(
            **config_data,
            instructions=instructions_text,
            agent_model_config=agentic_config.get_model(model_id),
        )
    except ValidationError as e:
        errors.append(str(e))

    return agent_config, errors


@agents.command(name="write")
@click.argument("agent_name")
@click.option(
    "--config",
    "config_source",
    required=True,
    help="Path to a JSON file with the AgentConfig header fields, or a literal JSON string.",
)
@click.option(
    "--instructions",
    "instructions_source",
    required=True,
    help="Path to a Markdown file with the system prompt body, or a literal string.",
)
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
def write(agent_name, config_source, instructions_source, file):
    """Write and validate a new agent's instructions.md file.

    Builds `workspace/agents/<agent_name>/instructions.md` from a JSON
    header (validated against `AgentConfig` — see `agentic agents
    schema`) and a Markdown system prompt body, writes it in the exact
    two-part format the runtime expects, then re-loads it through
    `AgenticConfig.get_agent(...)` to confirm it actually parses before
    reporting success. Nothing is written if validation fails. Fails if
    the agent already exists — use `agentic agents update` for that.

    ARGUMENTS:
        AGENT_NAME  Name for the agent; must match the "name" field in
                    --config and becomes the directory name under
                    <workspace>/agents/.
        FILE        Path to the agentic config file (default: agentic.json)

    OPTIONS:
        --config        Path to a JSON file, or an inline JSON string,
                         matching the AgentConfig header fields.
        --instructions  Path to a Markdown file, or an inline string,
                         used as the system prompt body.

    Examples:
        agentic agents write weather_reporter --config agent.json --instructions prompt.md
        agentic agents write weather_reporter --config '{"workspace_dir": "./workspace", "name": "weather_reporter", "description": "...", "model_id": "custom-nemotron-3-super-120b-a12b"}' --instructions "# Weather Reporter\n\nYou are ..."
    """
    try:
        agentic_config = _load_agentic_config(file)
    except FileNotFoundError:
        click.echo(f"Configuration file '{file}' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    agent_dir = os.path.join(agentic_config.workspace, "agents", agent_name)
    agent_path = os.path.join(agent_dir, "instructions.md")
    if os.path.isfile(agent_path):
        click.echo(
            f"Agent '{agent_name}' already exists at '{agent_path}'. "
            "Use 'agentic agents update' to modify it.",
            err=True,
        )
        sys.exit(1)

    config_text = _resolve_text(config_source)
    try:
        config_data = json.loads(config_text)
    except json.JSONDecodeError as e:
        click.echo(f"--config is not valid JSON (and not an existing file path): {e}", err=True)
        sys.exit(1)

    instructions_text = _resolve_text(instructions_source)

    agent_config, errors = _build_and_validate_agent_config(
        agentic_config, agent_name, config_data, instructions_text
    )
    if errors:
        click.echo("Validation FAILED — nothing was written:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        sys.exit(1)

    os.makedirs(agent_dir, exist_ok=True)
    agent_config.dump(agent_path)

    # Re-load through the real runtime path to confirm it parses correctly.
    try:
        agentic_config.get_agent(agent_name)
    except Exception as e:
        click.echo(f"Wrote '{agent_path}' but it failed to re-load: {e}", err=True)
        sys.exit(1)

    click.echo(f"Wrote and validated '{agent_path}'.")
    click.echo(f"  Name: {agent_config.name}")
    click.echo(f"  Description: {agent_config.description}")
    click.echo(f"  Model: {agent_config.model_id}")
    click.echo(f"  Tools: {len(agent_config.tools or ())} configured")
    click.echo(f"  Skills: {len(agent_config.skills or [])} configured")
    click.echo("Run 'agentic agents list' to confirm it appears in the listing.")


@agents.command(name="update")
@click.argument("agent_name")
@click.option(
    "--config",
    "config_source",
    default=None,
    help=(
        "Path to a JSON file, or a literal JSON string, of AgentConfig "
        "fields to merge (shallow) into the existing header."
    ),
)
@click.option(
    "--instructions",
    "instructions_source",
    default=None,
    help="Path to a Markdown file, or a literal string, to replace the system prompt body.",
)
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
def update(agent_name, config_source, instructions_source, file):
    """Edit and re-validate an existing agent's instructions.md file.

    Loads the current `workspace/agents/<agent_name>/instructions.md`,
    shallow-merges any `--config` fields into the existing JSON header
    (e.g. change `model_id`, add a tool, tweak `denied_tools`) and/or
    replaces the instructions body with `--instructions`, re-validates
    the result against `AgentConfig`, and only overwrites the file if
    validation (and a re-load) succeeds. At least one of --config /
    --instructions must be given.

    ARGUMENTS:
        AGENT_NAME  Name of the existing agent to update.
        FILE        Path to the agentic config file (default: agentic.json)

    OPTIONS:
        --config        Path to a JSON file, or inline JSON string, with
                         fields to merge into the existing header
                         (top-level keys only; e.g. {"model_id": "..."}).
        --instructions  Path to a Markdown file, or inline string, to
                         fully replace the system prompt body.

    Examples:
        agentic agents update weather_reporter --config '{"model_id": "custom-gemma-4-e2b-it"}'
        agentic agents update weather_reporter --instructions new_prompt.md
    """
    if config_source is None and instructions_source is None:
        click.echo("Provide at least one of --config or --instructions.", err=True)
        sys.exit(1)

    try:
        agentic_config = _load_agentic_config(file)
    except FileNotFoundError:
        click.echo(f"Configuration file '{file}' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    agent_path = os.path.join(agentic_config.workspace, "agents", agent_name, "instructions.md")
    if not os.path.isfile(agent_path):
        click.echo(
            f"Agent '{agent_name}' not found at '{agent_path}'. Use 'agentic agents write' to create it.",
            err=True,
        )
        sys.exit(1)

    try:
        current_agent_config = agentic_config.get_agent(agent_name)
    except Exception as e:
        click.echo(f"Existing '{agent_path}' fails to load, refusing to update: {e}", err=True)
        sys.exit(1)

    config_data = current_agent_config.model_dump(
        mode="json", exclude={"system_prompt_path", "instructions", "agent_model_config"}
    )
    instructions_text = current_agent_config.instructions

    if config_source is not None:
        config_text = _resolve_text(config_source)
        try:
            patch = json.loads(config_text)
        except json.JSONDecodeError as e:
            click.echo(f"--config is not valid JSON (and not an existing file path): {e}", err=True)
            sys.exit(1)
        config_data.update(patch)  # shallow merge

    if instructions_source is not None:
        instructions_text = _resolve_text(instructions_source)

    agent_config, errors = _build_and_validate_agent_config(
        agentic_config, agent_name, config_data, instructions_text
    )
    if errors:
        click.echo("Validation FAILED — existing file left untouched:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        sys.exit(1)

    agent_config.dump(agent_path)

    # Re-load through the real runtime path to confirm it parses correctly.
    try:
        agentic_config.get_agent(agent_name)
    except Exception as e:
        click.echo(f"Updated '{agent_path}' but it failed to re-load: {e}", err=True)
        sys.exit(1)

    click.echo(f"Updated and validated '{agent_path}'.")
    click.echo(f"  Name: {agent_config.name}")
    click.echo(f"  Description: {agent_config.description}")
    click.echo(f"  Model: {agent_config.model_id}")
    click.echo(f"  Tools: {len(agent_config.tools or ())} configured")
    click.echo(f"  Skills: {len(agent_config.skills or [])} configured")


@agents.command(name="validate")
@click.argument("agent_name")
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
def validate(agent_name, file):
    """Validate an existing agent's instructions.md file.

    Loads `workspace/agents/<agent_name>/instructions.md`, parses its
    JSON header against the `AgentConfig` schema, and checks a few extra
    invariants (directory name matches "name", model_id exists in the
    agentic config, system prompt body isn't blank). Exits non-zero with
    a clear error list on failure instead of a raw stack trace.

    ARGUMENTS:
        AGENT_NAME  Name of the agent to validate.
        FILE        Path to the agentic config file (default: agentic.json)

    Example:
        agentic agents validate weather_reporter
    """
    try:
        agentic_config = _load_agentic_config(file)
    except FileNotFoundError:
        click.echo(f"Configuration file '{file}' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    agent_path = os.path.join(agentic_config.workspace, "agents", agent_name, "instructions.md")
    if not os.path.isfile(agent_path):
        click.echo(f"Agent instructions file not found: {agent_path}", err=True)
        sys.exit(1)

    try:
        agent_config = agentic_config.get_agent(agent_name)
    except Exception as e:
        click.echo(f"Validation FAILED for '{agent_path}':", err=True)
        click.echo(f"  - {e}", err=True)
        sys.exit(1)

    errors = []
    if agent_config.name != agent_name:
        errors.append(
            f"'name' field ({agent_config.name!r}) does not match directory name ({agent_name!r})."
        )
    if agentic_config.get_model(agent_config.model_id) is None:
        errors.append(f"model_id '{agent_config.model_id}' is not defined in {file}'s 'models' list.")
    if not agent_config.instructions or not agent_config.instructions.strip():
        errors.append("System prompt body (after the '---' separator) is empty.")

    if errors:
        click.echo(f"Validation FAILED for '{agent_path}':", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        sys.exit(1)

    click.echo(f"'{agent_path}' is valid.")
    click.echo(f"  Name: {agent_config.name}")
    click.echo(f"  Description: {agent_config.description}")
    click.echo(f"  Model: {agent_config.model_id}")
    click.echo(f"  Tools: {len(agent_config.tools or ())} configured")
    click.echo(f"  Skills: {len(agent_config.skills or [])} configured")


@agents.command()
@click.argument("agent_name")
@click.option("--task", "-t", help="Task description for the agent to perform")
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
def run(agent_name, task, file):
    """Run a specific agent with an optional task.

    Executes the specified agent with the given task description. If no task
    is provided, the agent will start in interactive mode.

    ARGUMENTS:
        AGENT_NAME  Name of the agent to run (must exist as
                    `<workspace>/agents/<agent_name>/instructions.md`)
        FILE        Path to the agentic config file (default: agentic.json)

    OPTIONS:
        --task, -t  Task description for the agent to perform

    Examples:
        agentic agents run main
        agentic agents run main -t "Analyze the sales data for Q3"
        agentic agents run image_generator -t "Create a logo for a tech startup"
    """
    try:
        agentic_config = _load_agentic_config(file)
    except FileNotFoundError:
        click.echo(f"Configuration file '{file}' not found.", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    try:
        agent_config = agentic_config.get_agent(agent_name)
    except FileNotFoundError:
        click.echo(f"Agent '{agent_name}' not found.", err=True)
        available = agentic_config.list_agent_names()
        if available:
            click.echo("Available agents: " + ", ".join(available))
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading agent '{agent_name}': {e}", err=True)
        sys.exit(1)

    click.echo(f"Starting agent '{agent_config.name}'...")
    click.echo(f"Description: {agent_config.description}")
    click.echo(f"Model: {agent_config.model_id}")
    if task:
        click.echo(f"Task: {task}")
    else:
        click.echo("Starting in interactive mode. Send messages to interactively.")

    # TODO: Implement actual agent execution logic here would call to run
    click.echo("Agent execution would start here... (placeholder)")
    click.echo("Note: Actual agent execution logic needs to be implemented.")



def add_agents_commands(cli):
    """Add the agents command group to the main CLI."""
    cli.add_command(agents)
