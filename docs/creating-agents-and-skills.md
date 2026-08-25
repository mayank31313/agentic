# Creating agents and skills for Agentic

This guide walks through the current, code-verified steps for adding a new
**agent** and a new **skill** to Agentic. It complements
[`architecture.md`](../architecture.md) and the "Extending Agentic" section
of [`README.md`](../README.md); read those first for the high-level
component overview.

> Everything here reflects the current implementation
> (`src/agentic/app/config.py`, `src/agentic/app/agents.py`,
> `src/agentic/cli/agents.py`). Where the implementation has rough edges or
> inconsistencies, they're called out explicitly rather than glossed over —
> see [Known limitations](#known-limitations).

## Table of contents

- [Creating a new agent](#creating-a-new-agent)
  - [1. Understand where agent config actually lives](#1-understand-where-agent-config-actually-lives)
  - [2. Create the instructions file](#2-create-the-instructions-file)
  - [3. Verify](#3-verify)
  - [Worked example: a new `weather_reporter` agent](#worked-example-a-new-weather_reporter-agent)
- [Creating a new skill](#creating-a-new-skill)
  - [1. Layout and frontmatter](#1-layout-and-frontmatter)
  - [2. Worked example: reusing `agentic-cli`'s shape](#2-worked-example-reusing-agentic-clis-shape)
  - [3. Wiring and verification](#3-wiring-and-verification)
- [Known limitations](#known-limitations)

---

## Creating a new agent

### 1. Understand where agent config actually lives

`workspace/agents/<name>/instructions.md` is the **only** place agent
configuration lives — there's no separate registration step. It's loaded
at runtime by `AgenticConfig.get_agent(name)` (see
[`config.py`](../src/agentic/app/config.py)), and both `agentic agents
list` and `agentic agents run` (see
[`src/agentic/cli/agents.py`](../src/agentic/cli/agents.py)) discover
agents the same way, via `AgenticConfig.list_agents()`, which scans
`<workspace>/agents/*/instructions.md` on disk. `resources/agentic.json`
holds shared `models`, `tools`, and `mcpServers` config, but has no
`agents` field of its own.

So: **creating a working agent means creating the
`workspace/agents/<name>/instructions.md` file — and that's the whole
job.**

### 2. Create the instructions file

Each `instructions.md` file has two parts separated by a line containing
only `---`:

1. A JSON object matching the `AgentConfig` fields (see
   [`config.py`](../src/agentic/app/config.py)) — the header **is**
   parsed straight into an `AgentConfig` instance
   (`AgentConfig(**json.loads(header), ...)`), so it must validate against
   that pydantic model exactly. Run `agentic agents schema` to print the
   authoritative, current JSON Schema (`AgentConfig.model_json_schema()`)
   before generating or editing a header, rather than relying only on the
   table below, which can drift from the model as it evolves. (See also
   `agentic config schema` for the top-level `AgenticConfig` schema used
   by `resources/agentic.json`.)

   | Field | Type | Notes |
   |---|---|---|
   | `name` | string | Must match the parent directory name (`workspace/agents/<name>/`). |
   | `description` | string | Short human-readable summary. |
   | `workspace_dir` | string | Usually `"./workspace"`. |
   | `model_id` | string | Must match a `model_id` defined in `resources/agentic.json`'s `models` list. |
   | `tools` | array of `{name, require_approval, approval_text}` | Per-tool approval gating (`require_approval: true` triggers a human-in-the-loop interrupt). |
   | `denied_tools` | array of strings | Tool names to exclude even if otherwise available. |
   | `skills` | array of `{path, virtual_path}` | Filesystem path(s) to skill directories and the virtual path the agent sees them under (usually `./src/skills/` → `/skills/`). |

2. The system prompt / instructions body (plain Markdown), which becomes
   `agent_config.instructions` and is passed to `create_deep_agent` as the
   system prompt.

Minimal template (note: this is `instructions.md`'s actual two-part format —
JSON header, a bare `---` line, then Markdown — not a single JSON document,
so it's fenced as `text` rather than `json` below):

```text
{
  "workspace_dir": "./workspace",
  "name": "my_new_agent",
  "description": "One-line description of what this agent does",
  "model_id": "custom-gemma-4-e2b-it",
  "tools": [],
  "denied_tools": [
    "mcp-activate-profile", "mcp-add", "mcp-config-set",
    "mcp-create-profile", "mcp-exec", "mcp-find", "mcp-remove", "execute_code"
  ],
  "skills": [
    { "path": "./src/skills/", "virtual_path": "/skills/" }
  ]
}
---
# My New Agent — System Prompt

You are ... (describe the agent's role, boundaries, and how it should use
its tools).
```

Save it as `workspace/agents/my_new_agent/instructions.md`.

Prefer writing it via the CLI over manual file creation, since it
validates for you:

```bash
agentic agents write my_new_agent --config <json-file-or-inline-json> --instructions <md-file-or-inline-text> resources/agentic.json
```

`agentic agents write` parses `--config` against the `AgentConfig`
schema (see `agentic agents schema`), refuses if the agent already
exists, writes the two-part file, and re-loads it through
`AgenticConfig.get_agent(...)` before reporting success — nothing is
written if validation fails. To edit an existing agent, use
`agentic agents update <name> [--config ...] [--instructions ...]`
instead, which shallow-merges `--config` into the current header and/or
replaces the instructions body, re-validating before overwriting.

### 3. Verify

```bash
agentic agents list
agentic agents validate my_new_agent
```

Confirm your new agent name, description, model, and tool/skill counts
appear — this command reads `workspace/agents/*/instructions.md` directly,
so no separate config-file registration step is needed. `agentic agents
validate <name>` additionally checks that the directory name matches
`name`, the `model_id` exists in `resources/agentic.json`, and the
instructions body isn't blank, failing fast with a clear error list
instead of a raw stack trace. Full end-to-end
execution via `agentic agents run <name>` is currently a placeholder (see
[Known limitations](#known-limitations)) — to actually exercise the new
agent, wire it up the way `AgenticBot` wires the `main` agent (via
`AgenticConfig.get_agent(name)` + `get_main_agent(...)`), or use it as a
`subagent` target from a scheduled job in `cron_schedules.json` (see the
existing `memory_compaction_hourly` entry for the shape).

### Worked example: a new `weather_reporter` agent

Mirrors the existing `workspace/agents/trip_planner/` agent:

`workspace/agents/weather_reporter/instructions.md`:

```text
{
  "workspace_dir": "./workspace",
  "name": "weather_reporter",
  "description": "Agent that fetches and summarizes weather forecasts",
  "model_id": "custom-nemotron-3-super-120b-a12b",
  "tools": [
    { "name": "tavily_search", "require_approval": false, "approval_text": null }
  ],
  "denied_tools": [
    "mcp-activate-profile", "mcp-add", "mcp-config-set",
    "mcp-create-profile", "mcp-exec", "mcp-find", "mcp-remove", "execute_code"
  ],
  "skills": []
}
---
# Weather Reporter — System Prompt

You are a weather-reporting agent. Given a location and a time range, use
`tavily_search` to find the current forecast and summarize it concisely,
including temperature range, precipitation chance, and any notable
warnings (storms, heat, etc.). Ask for clarification if the location is
ambiguous.
```

---

## Creating a new skill

Skills are Markdown-defined behaviors under `src/skills/<name>/SKILL.md`,
loaded automatically by the deep agent's `SkillsMiddleware` via the
`skills` route configured in each agent's `instructions.md` (see above).

This project already has a dedicated meta-skill for authoring skills in
depth — **[`src/skills/deep-agents-skill-creator/SKILL.md`](../src/skills/deep-agents-skill-creator/SKILL.md)** —
covering the full Agent Skills spec, frontmatter fields, interpreter vs.
sandbox vs. plain-tool-call patterns, and validation/testing steps. Use it
as the canonical deep-dive; this section is a condensed quick-start.

### 1. Layout and frontmatter

```
src/skills/
└── my-skill/
    ├── SKILL.md          # required
    ├── scripts/           # optional: executable code (needs a sandbox backend to run)
    ├── references/        # optional: docs loaded only when SKILL.md points to them
    └── assets/             # optional: templates, schemas, etc.
```

`SKILL.md` frontmatter (YAML) requires:

```yaml
---
name: my-skill               # must exactly match the directory name
description: >-
  What this skill does AND when to use it (this is the only text an
  agent sees at discovery time — be specific, include trigger phrases).
---
```

The body is the full instruction set the agent follows once the skill
activates — step-by-step procedure, decision criteria, example
inputs/outputs, edge cases, and explicit pointers to any `scripts/`,
`references/`, or `assets/` files.

### 2. Worked example: reusing `agentic-cli`'s shape

Look at [`src/skills/agentic-cli/SKILLS.md`](../src/skills/agentic-cli/SKILLS.md)
for a real, working example: frontmatter with a detailed trigger
description, a command reference section, an error-recovery table, and
explicit "if this skill fails to load" troubleshooting. New skills should
follow the same structure: frontmatter → workflow/procedure → edge cases →
troubleshooting.

> Note: `agentic-cli`'s file is named `SKILLS.md` (plural) rather than
> `SKILL.md` — this is inconsistent with the spec used by
> `deep-agents-skill-creator` and other skills in this repo. **New skills
> should use `SKILL.md` (singular)** to match the Agent Skills
> specification and `SkillsMiddleware`'s expected filename.

### 3. Wiring and verification

1. Confirm the skill directory sits under a path already referenced by an
   agent's `skills` config (`./src/skills/` is wired to `/skills/` for the
   `main` agent by default — see
   [`workspace/agents/main/instructions.md`](../workspace/agents/main/instructions.md)).
   No extra registration step is needed if you add the skill under
   `src/skills/`; it's picked up automatically the next time the agent
   initializes.
2. Validate the frontmatter (`name` matches the directory, `description`
   ≤1,024 chars, states both what and when).
3. Test with a real prompt that should trigger the skill, and a near-miss
   prompt that shouldn't — confirm it fires only when intended and doesn't
   collide with another skill's description.
4. If it doesn't load, check `SkillsMiddleware` logs for
   `path_not_found`-style warnings — usually a cwd/relative-path issue, not
   a problem with the skill content itself (see the "If this skill itself
   fails to load" section of `agentic-cli/SKILLS.md` for the general fix
   pattern).

---

## Known limitations

These are current, observed gaps in the tooling — call them out rather
than working around them silently:

- **`agentic agents run <name>` is a placeholder.** It validates config and
  prints what it *would* do but does not actually execute the agent (see
  the `TODO` in [`cli/agents.py`](../src/agentic/cli/agents.py)).
- **`config set` does not persist to disk** — it only prints the merged
  config to stdout. You must capture and write the output back to the
  file yourself.
- **`agentic-cli`'s skill file is named `SKILLS.md`**, not `SKILL.md` —
  inconsistent with the spec other skills in this repo follow. Don't copy
  that filename convention for new skills.

If you fix any of these, update this document and
[`README.md`](../README.md)/[`architecture.md`](../architecture.md)
alongside the code change, per the project's config-first / docs-in-sync
philosophy.

