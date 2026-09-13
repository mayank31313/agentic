# CLI Reference

The `agentic` command-line tool (installed via `uv sync`, entry point defined in
[`pyproject.toml`](https://github.com/mayank31313/agentic/blob/main/pyproject.toml)
as `agentic = "agentic:main"`) is how you run the bot server, inspect/edit
`resources/agentic.json`, and manage agents, MCP tools, and custom tools. Every
command accepts `--help` for its exact, current signature — this page is a
human-readable tour of the same commands, grouped by
[`src/agentic/cli/`](https://github.com/mayank31313/agentic/blob/main/src/agentic/cli/).

All commands are invoked as `uv run agentic <command> [args]` (or just
`agentic ...` if you've activated the project's virtualenv). Most commands that
touch agent/model/tool config accept an optional trailing `FILE` argument for
the agentic config path, defaulting to `$AGENTIC_CONFIG` or
`resources/agentic.json`.

## Top-level commands

### `agentic run`

Starts the bot application server (`agentic.bot_app.run_bot`) — the Telegram
channel, scheduler, and gateway all come up together. Runs until interrupted
(`Ctrl+C`).

```powershell
uv run agentic run
```

## `agentic message` — send messages via the bot

| Command | Description |
|---|---|
| `agentic message add TEXT` | Send a text message through the bot to its configured destination (e.g. the default Telegram chat). |

```powershell
uv run agentic message add "Hello, this is a test message"
```

## `agentic mcp` — Model Context Protocol server

| Command | Description |
|---|---|
| `agentic mcp run` | Start the standalone MCP tool server (`agentic.agentic_mcp`), exposing Gmail, Proxmox, Stable Diffusion, PDF parser, and SQLite store tools. |

```powershell
uv run agentic mcp run
```

## `agentic config` — inspect/edit `resources/agentic.json`

Operates on the top-level `AgenticConfig` model (models, tools, mcpServers).

| Command | Description |
|---|---|
| `agentic config get KEY_PATH [FILE]` | Print the value at a [JSONPath](https://github.com/h2non/jsonpath-ng) expression. |
| `agentic config set KEY_PATH --set key=value [--set ...] [FILE]` | Apply one or more `key=value` patches at a JSONPath location. |
| `agentic config schema` | Print `AgenticConfig.model_json_schema()` — the authoritative schema for `resources/agentic.json`. |

```powershell
uv run agentic config schema
uv run agentic config get "models[*].model_id"
uv run agentic config set telegram.bot_token --set telegram.bot_token=123:ABC
```

!!! warning "`config set` does not persist to disk"
    It only prints the merged config to stdout — capture and write the output
    back to the file yourself. See
    [Creating agents and skills → Known limitations](creating-agents-and-skills.md#known-limitations).

## `agentic agents` — manage and run agents

Operates on `workspace/agents/<name>/instructions.md` files — the *only*
place agent configuration lives (see
[Creating agents and skills](creating-agents-and-skills.md)).

| Command | Description |
|---|---|
| `agentic agents list [FILE]` | List all agents discovered under `<workspace>/agents/*/instructions.md`, with description, model, and tool/skill counts. |
| `agentic agents schema` | Print `AgentConfig.model_json_schema()` — the schema the JSON header of every `instructions.md` must validate against. |
| `agentic agents write AGENT_NAME --config ... --instructions ... [FILE]` | Create a **new** agent's `instructions.md`, validating the header against `AgentConfig` and re-loading it through the real runtime path before reporting success. Fails if the agent already exists. |
| `agentic agents update AGENT_NAME [--config ...] [--instructions ...] [FILE]` | Shallow-merge `--config` into the existing header and/or replace the instructions body, re-validating before overwriting. |
| `agentic agents show AGENT_NAME [FILE]` | Read-only: print the exact current JSON header and instructions body, without validating or writing anything. |
| `agentic agents validate AGENT_NAME [FILE]` | Validate an existing agent and print a clear error list on failure (directory name matches `name`, `model_id` exists, instructions body isn't blank). |
| `agentic agents run AGENT_NAME [--task/-t TEXT] [FILE]` | **Placeholder** — validates and prints what it *would* do but does not actually execute the agent yet. |

```powershell
uv run agentic agents list
uv run agentic agents schema
uv run agentic agents write weather_reporter --config agent.json --instructions prompt.md
uv run agentic agents update weather_reporter --config '{"model_id": "custom-gemma-4-e2b-it"}'
uv run agentic agents show weather_reporter
uv run agentic agents validate weather_reporter
```

!!! tip "Prefer the CLI over manual file edits"
    `write`/`update` validate the JSON header against `AgentConfig` and refuse
    to leave a broken file on disk; `show` lets you copy the exact current
    content before a targeted edit, since both `--config` and `--instructions`
    always *replace* (never patch) their respective content.

## `agentic tools` — runtime tools on a running bot

| Command | Description |
|---|---|
| `agentic tools reload [--url URL] [--token TOKEN]` | Hit a running bot's `POST /admin/tools/reload` gateway endpoint to re-scan MCP servers, workspace sub-agents, and custom tools, then rebuild the compiled agent graph. **Drops in-flight conversation state.** |

`--url` defaults to `$AGENTIC_GATEWAY_URL` or `http://localhost:5000`; `--token`
defaults to `$AGENTIC_ADMIN_TOKEN` and is sent as the `X-Admin-Token` header.

```powershell
uv run agentic tools reload
uv run agentic tools reload --url http://localhost:5000 --token secret
```

### `agentic tools custom` — agent-authored custom tools

Manages tools an agent created at runtime via `create_custom_tool`, stored
under `<workspace>/custom_tools/<name>/` (never under `src/`).

| Command | Description |
|---|---|
| `agentic tools custom list [FILE]` | List custom tools with kind and approval status. |
| `agentic tools custom inspect NAME [FILE]` | Print a tool's spec plus its generated source (`tool.py`) or `Dockerfile`/`entrypoint`, for human review. |
| `agentic tools custom approve NAME [FILE]` | Lift the per-call approval gate after reviewing the tool. |
| `agentic tools custom edit NAME [options] [FILE]` | Update description/args/timeout/network-access and/or replace the full source (never a diff). **Any** edit resets the approval flag. |
| `agentic tools custom remove NAME [FILE]` | Delete a custom tool's files. |

`edit` options: `--description`, `--tool-args '{"x": "integer"}'`,
`--python-source PATH` (python-kind only), `--dockerfile PATH` /
`--entrypoint PATH` (docker-kind only), `--network-access` /
`--no-network-access`, `--timeout-seconds N`. Only the options you pass are
changed.

```powershell
uv run agentic tools custom list
uv run agentic tools custom inspect my_tool
uv run agentic tools custom edit my_tool --description "New description"
uv run agentic tools custom approve my_tool
uv run agentic tools custom remove my_tool
uv run agentic tools reload   # apply changes to a running bot
```

See [Creating agents and skills → Agent-authored custom tools](creating-agents-and-skills.md#agent-authored-custom-tools)
for the full approval-gating model.

## Getting help

Every group and command supports `--help`:

```powershell
uv run agentic --help
uv run agentic agents --help
uv run agentic agents write --help
```

