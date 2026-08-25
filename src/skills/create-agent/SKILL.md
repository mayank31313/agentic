---
name: create-agent
description: >-
  Create a new Agentic agent — a workspace/agents/<name>/instructions.md file.
  Use this whenever the user wants to add, define, or scaffold a new agent for
  Agentic (e.g. "create a new agent for X", "add an agent that does Y", "set
  up an agent called Z", "make a weather/trip/summarizer agent"). This is
  specific to Agentic's own agent config format — not generic
  deep-agents/LangChain agent creation, and not skill authoring (see the
  deep-agents-skill-creator skill for that).
license: MIT
metadata:
  author: agentic
  project: agentic
---

# Create Agent (Agentic)

Scaffolds a new agent for the Agentic platform. An "agent" here is a single
`workspace/agents/<name>/instructions.md` file — the file actually loaded at
runtime, and discovered automatically by `agentic agents list`/`agentic
agents run` (both scan `<workspace>/agents/*/instructions.md` via
`AgenticConfig.list_agents()`/`get_agent()`; there is no separate
`resources/agentic.json` registration step to remember). Follow this
procedure rather than guessing at the file shape — the two-part format below
is exact and validated by a pydantic model.

## Before you start

Gather (ask the user if not already given):

1. **Agent name** — lowercase, `snake_case` recommended (e.g.
   `weather_reporter`), used as both the directory name and the `name`
   field. Must be unique among existing `workspace/agents/*` folders.
2. **Purpose / description** — one line describing what the agent does.
3. **Which model** — check `resources/agentic.json`'s `models` array for
   available `model_id` values (`agentic config get "models[*].model_id"`
   if the CLI is available). Don't invent a `model_id` that isn't defined
   there.
4. **Tools it needs** — which existing tools (from
   `resources/agentic.json`'s `tools`, plus MCP-exposed tools) the agent
   should have access to, and whether any need human-in-the-loop approval
   before running (e.g. shell commands, destructive actions).
5. **Skills it needs** — usually just the shared `./src/skills/` →
   `/skills/` route, unless there's a reason to scope it differently.
6. **Exact `AgentConfig` shape** — run `agentic agents schema` to fetch
   `AgentConfig.model_json_schema()` (and `agentic config schema` for the
   top-level `AgenticConfig` if editing `resources/agentic.json`) so the
   generated JSON header is precise, instead of guessing from memory.

If any of this is unclear, make a reasonable default and say so, rather
than blocking on questions the user likely doesn't have a strong opinion
on (e.g. default to no extra tools, the shared skills route, and the
smallest/cheapest configured model).

## Step 1: Write `workspace/agents/<name>/instructions.md`

This is the single file that defines the agent — nothing else needs to be
touched (`resources/agentic.json` has no `agents` field/array; it only
holds shared `models`, `tools`, and `mcpServers`).

The file has exactly two parts separated by a line containing only `---`:

1. A JSON object — this **is** an instance of the `AgentConfig` pydantic
   model (`src/agentic/app/config.py`); it's parsed with `json.loads(...)`
   and passed straight into `AgentConfig(**configs, ...)`. Before writing
   it, run `agentic agents schema` to get the authoritative, current JSON
   Schema (field names, types, required-ness) rather than trusting the
   table below alone — it can drift from the model. The table is a
   convenient summary of the current fields:

   | Field | Type | Required | Notes |
   |---|---|---|---|
   | `name` | string | yes | Must match the directory name exactly. |
   | `description` | string | yes | Short summary of the agent's purpose. |
   | `workspace_dir` | string | yes | Usually `"./workspace"`. |
   | `model_id` | string | yes | Must match a `model_id` in `resources/agentic.json`'s `models` list. |
   | `tools` | array of `{name, require_approval, approval_text}` | no (default empty) | `require_approval: true` gates the tool behind a human-in-the-loop interrupt; set `approval_text` to the prompt shown, else `null`. |
   | `denied_tools` | array of strings | no | Tool names to explicitly block even if otherwise available. Default to the standard MCP-management denylist below unless the user needs those. |
   | `skills` | array of `{path, virtual_path}` | no | Filesystem path(s) to skill directories and the virtual path they're mounted at. Usually `[{"path": "./src/skills/", "virtual_path": "/skills/"}]`. |

2. The system prompt body (Markdown) — everything after the `---` line.
   This becomes the agent's instructions verbatim, so write it as a
   direct system prompt: role, scope, tool-usage guidance, and boundaries.

   Note: the body may itself contain the literal text `---` (e.g. in
   documentation like this skill file) — the parser only splits on the
   *first* such line, so this is safe as long as the JSON header and body
   are separated by exactly one `---` line.

Template:

```text
{
  "workspace_dir": "./workspace",
  "name": "<agent_name>",
  "description": "<one-line description>",
  "model_id": "<existing_model_id>",
  "tools": [
    { "name": "<tool_name>", "require_approval": false, "approval_text": null }
  ],
  "denied_tools": [
    "mcp-activate-profile", "mcp-add", "mcp-config-set",
    "mcp-create-profile", "mcp-exec", "mcp-find", "mcp-remove", "execute_code"
  ],
  "skills": [
    { "path": "./src/skills/", "virtual_path": "/skills/" }
  ]
}
---
# <Agent Name> — System Prompt

You are ... (role, what it should and shouldn't do, how to use its tools,
when to ask for clarification or approval).
```

Write this to `workspace/agents/<agent_name>/instructions.md`, creating
the directory if it doesn't exist.

Prefer the CLI over manual file creation when it's available:

```bash
agentic agents write <agent_name> --config <json-file-or-inline-json> --instructions <md-file-or-inline-text> resources/agentic.json
```

This validates the JSON header against `AgentConfig` (see `agentic agents
schema`), refuses to run if the agent already exists, writes the file in
the exact two-part format, and re-loads it through the real runtime path
before reporting success — nothing is written if validation fails. To
modify an existing agent instead of scaffolding a new one, use:

```bash
agentic agents update <agent_name> --config '{"model_id": "..."}' resources/agentic.json
agentic agents update <agent_name> --instructions new_prompt.md resources/agentic.json
```

`update` shallow-merges any `--config` fields into the existing header
and/or replaces the instructions body, re-validating before overwriting
(the file is left untouched on failure). Either way, finish with:

```bash
agentic agents validate <agent_name> resources/agentic.json
```

## Step 2: Verify

```bash
agentic agents list
```

Confirm the new agent's name, description, model, and tool/skill counts
appear in the listing (this reads directly from
`workspace/agents/<name>/instructions.md` — no config file edit is
needed). Note that `agentic agents run <name>` is currently a
placeholder — it loads and validates the agent config and prints what it
*would* do but does not execute the agent. To actually run the new agent,
either:
- wire it up the way `AgenticBot` wires the `main` agent (load via
  `AgenticConfig.get_agent(name)`, then `get_main_agent(...)`), or
- reference it as a `subagent` target from a scheduled job in
  `cron_schedules.json` (see the existing `memory_compaction_hourly` entry
  for the shape of a subagent definition).

## Common mistakes to avoid

- **Don't** put the JSON header and the Markdown body in the same file
  without the bare `---` separator line — parsing requires exactly this
  shape (splitting on the first `---` line).
- **Don't** invent a `model_id` — always check
  `resources/agentic.json`'s `models` array first.
- **Don't** add an `agents` array/entry to `resources/agentic.json` — it
  is not part of the `AgenticConfig` schema and is ignored; the
  `workspace/agents/<name>/instructions.md` file is the only thing that
  matters.
- **Don't** use `agentic agents write` on a name that already has an
  `instructions.md` — it refuses on purpose; use `agentic agents update`
  instead so an existing agent isn't silently clobbered.
- If `agentic agents list`/`run` can't find your agent, double check the
  directory name matches the `name` field exactly and that
  `instructions.md` exists directly inside it.

## Reference

Full write-up with worked examples:
[`docs/creating-agents-and-skills.md`](../../../docs/creating-agents-and-skills.md)
(project root). Existing agents to model new ones after:
`workspace/agents/main/instructions.md` and
`workspace/agents/trip_planner/instructions.md`.

