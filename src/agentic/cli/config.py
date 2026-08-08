import json

import click
from jsonpath_ng import parse

from agentic import AgenticConfig


@click.group()
def config():
    """Get or Set Config properties for Bot.

    This group provides commands to inspect and modify the bot's
    configuration stored in agentic.json or other JSON configuration files.
    """
    pass


@config.command()
@click.argument("key_path", type=str, required=True)
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
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
    with open(file, "r") as config:
        value = AgenticConfig.model_validate(json.load(config)).model_dump(mode="json")

        jsonpath_expression = parse(key_path)

        for match in jsonpath_expression.find(value):
            click.echo(json.dumps(match.value, indent=2))


@config.command()
@click.argument("key_path", type=str, required=True)
@click.option(
    "--set",
    "sets",
    multiple=True,
    help="key=value pairs to set, repeatable",
    required=True,
)
@click.argument("file", type=click.Path(exists=True), default="agentic.json")
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

    with open(file, "r") as config:
        value = AgenticConfig.model_validate(json.load(config)).model_dump(mode="json")

    jsonpath_expression = parse(key_path)
    jsonpath_expression.update(value, data)

    agentic_config_json = AgenticConfig.model_validate(value).model_dump(mode="json")
    with open(file, "w") as config:
        json.dump(agentic_config_json, config, indent=2)


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


def add_config_commands(cli):
    """Add the config command group to the main CLI."""
    cli.add_command(config)
