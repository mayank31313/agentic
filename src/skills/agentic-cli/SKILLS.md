---
name: agentic-cli
description: Use this skill whenever the user wants to interact with your configuration or its agentic.json configuration — including starting the bot server, sending messages, reading config values, and adding, creating, updating, removing, listing, or running configured agents (e.g. "add a new agent for image processing", "create an agent that does X", "update the model for the summarizer agent", "remove an agent from the config", "what agents are configured"). Also covers inspecting the config JSON schema and listing available MCP tools. Trigger this any time the user mentions "agentic cli", "agentic.json", the bot app, agent configuration, or asks to check/change any value in the bot's config — including requests that don't literally say "config" but describe adding/editing/removing an agent entry. Always invoke the CLI via your terminal/execute tool (direct `agentic` command) rather than guessing at or hand-writing config file contents.
---

# Agentic CLI

A Click-based command-line tool (entry point: `agentic`) for managing a bot
application: starting its server, sending messages, reading/writing its
`agentic.json` configuration via JSONPath, and listing/running configured
agents. Run all of these through your **execute/terminal tool** as real
shell commands — don't hand-edit `agentic.json` or guess at output; invoke
the CLI with your execute tool and read what it actually prints back.

## How to invoke commands

You have access to a terminal/execute tool (e.g. a "run command"/"execute"
tool) that runs a shell command and returns its stdout, stderr, and exit
code. **Always use that tool to run `agentic ...` commands** — never
fabricate or assume CLI output, and never simulate what a command "would"
print. Concretely:

- Pass the full command line (e.g. `agentic config get telegram.bot_token`)
  to the execute tool as a single invocation; don't split it across
  multiple tool calls unless you're chaining independent commands.
- For blocking commands (`agentic run`), invoke the tool in **background
  mode** if your tool supports it, or with an explicit timeout — never run
  it in a blocking foreground call, since that hangs the whole session.
- After every invocation, read the **actual returned stdout/stderr and exit
  code** from the tool result before deciding the command succeeded — a
  non-zero exit code is a real failure even if some output was printed.
- If the execute tool exposes a working-directory / `cwd` parameter, set it
  to the project root (or pass `agentic --cwd <path>`) instead of chaining
  a separate `cd` command, when possible.

## Before you start

Confirm the CLI is installed and runnable by running this through your
execute tool:

```bash
agentic --help
```

If that fails, try:

```bash
python -m app.cli --help   # in case the console-script entry point isn't registered
```

Check the project's `pyproject.toml` for the console-script entry point name
(under `[project.scripts]`) before assuming the command is `agentic`.

**Always run `agentic ...` from the project root** — this is also
where `agentic.json` lives, since `config`/`agents` subcommands read it from
the **current working directory** by default. If you're not in the project
root, either set the execute tool's working directory / `cd` there first,
or pass an explicit file path as the trailing argument where the command
supports it.

## Preferred invocation: Direct agentic command via the execute tool

Run the agentic CLI directly through your execute/terminal tool and capture
the returned output programmatically when needed (which is almost always,
in an agent context) — don't guess at what it would print.

```bash
agentic config get telegram.bot_token
agentic config schema
agentic --cwd /path/to/project agents list
agentic --timeout 5 config set telegram.bot_token --set telegram.bot_token=123:ABC
```

Output shape varies by command:
- JSON commands (config get, config schema, agents list) print JSON to stdout
- Text commands (config set, message add) print plain text to stdout
- The run command runs a blocking server and should be invoked in background
  when needed programmatically

Notes on using it:
- `success` can be determined by checking exit code (0 = success)
- JSON output can be parsed directly from stdout
- Default behavior for blocking commands like `agentic run` will block until
  interrupted — use background processes or subprocesses with timeouts when
  needed programmatically
- `--cwd` lets you target a project root without a separate `cd`, useful
  when running multiple agentic calls against different projects in the
  same agent session.
- Exit code follows standard conventions (0 = success, non-zero = failure)

## Command reference

### Discover what's available

```bash
agentic mcp list
```
Run this through your execute tool first if you're unsure a command still
exists or want the full current surface area — the tool may have grown
commands beyond what's documented here. Read the returned stdout to see
every command and subcommand the CLI exposes.

### Run the bot server

```bash
agentic run
```
Launches `bot_app.py` in the foreground and blocks until interrupted
(Ctrl+C). This is a long-running/blocking command — invoke it through your
execute tool's **background mode** (or with an explicit timeout) if you
need the session back; never call it as a plain blocking foreground
invocation, or it will hang the whole tool call.

### Send a message

```bash
agentic message add "Hello, this is a test message"
```
Sends TEXT through the bot. Always quote the message text so shell
word-splitting doesn't break multi-word messages when passed through the
execute tool.

### Adding a new agent (no dedicated `agents add` command exists)

The CLI has `agents list` and `agents run`, but **no `agents add` /
`agents create` command** as of this version — check `agentic agents
--help` to confirm that's still true before assuming otherwise. To add a
new agent, you go through `config set` against the `agents` array instead:

1. **Check the schema first** so the new entry has the right shape:
   ```bash
   agentic config schema
   ```

2. **See the current agents array** to know the next index and existing structure:
   ```bash
   agentic config get "agents"
   ```

3. **Append the new agent.** `jsonpath_ng`'s `.update()` replaces a matched
   node rather than appending to an array, so target the **new index
   directly** (current length of the array) rather than trying to "push":
   ```bash
   # if there are currently 2 agents (indices 0,1), target index 2
   agentic config set "agents.[2]" \
     --set name=image_processor \
     --set model=gpt-4-vision \
     --set tools='["image_analyze","image_resize"]'
   ```
   Note `--set` values are passed as raw strings by this CLI's current
   implementation — a list like `tools` will need to be validated against
   whatever `AgenticConfig`'s pydantic schema actually expects for that
   field (string vs. list). If the schema expects a real JSON array/object
   and this CLI's `--set` only supports flat string values, flag that gap
   to the user rather than silently writing a malformed entry — check the
   printed output against the schema before treating the write as
   successful.

4. **Verify the write:**
   ```bash
   agentic config get "agents.[2]"
   ```
   Run this through your execute tool right after the write and inspect
   the returned stdout. And remember: `config set` only prints the merged
   result — confirm separately whether the CLI actually persists to
   `file`, or whether you need to capture stdout and write it back
   yourself.

### List/read config values

```bash
agentic config get <key_path> [file]
```
- `key_path` is a **JSONPath** expression (via `jsonpath_ng`), e.g.
  `telegram.bot_token`, `agents.[0].name`, `agents[*].model`.
- `file` defaults to `agentic.json` in the cwd if omitted.
- The file is validated against the `AgenticConfig` pydantic model before
  the JSONPath query runs — a malformed config will error out here rather
  than silently returning nothing.

Examples:
```bash
agentic config get telegram.bot_token
agentic config get "agents[*].name" custom_config.json
```

### Write config values

```bash
agentic config set <key_path> --set key=value [--set key2=value2 ...] [file]
```
- `key_path` is the JSONPath target to update.
- `--set` takes repeatable `key=value` pairs; all provided pairs are merged
  into a dict and used as the replacement value at `key_path` (note: this
  replaces/updates the matched node — this is not a deep per-field patch of
  arbitrary depth, so pick a `key_path` that points at the right level).
- Output is the **full resulting config**, printed as pretty JSON — not
  just the changed field. Capture and inspect it to confirm the write did
  what you expected.

Example:
```bash
agentic config set telegram.bot_token --set telegram.bot_token=123:ABC
agentic config set "agents.[0]" --set name=Assistant --set model=gpt-4
```

⚠️ This command does **not** write the result back to `file` — it only
prints the merged config to stdout. If persistence to disk is expected,
verify that (check the source, or redirect/pipe the output to the file
yourself) rather than assuming the file changed after running `set`.

### Inspect the config schema

```bash
agentic config schema
```
Prints the full JSON Schema for `AgenticConfig`. Run this before writing to
an unfamiliar config file, or when a `config set`/`get` call errors with a
validation message you don't understand — the schema tells you the exact
field names, types, and structure expected.

### List agents

```bash
agentic agents list
```
Reads `agentic.json` in the cwd and prints each agent's name, model, and
tool count. Fails clearly if the file is missing or invalid JSON.

### Run an agent

```bash
agentic agents run <agent_name> [--task "..."] 
agentic agents run <agent_name> -t "..."
```
- Looks up `agent_name` in `agentic.json`'s `agents` list.
- With `--task`/`-t`, runs that task; without it, starts interactive mode.
- **Note:** as of the current code, actual execution is a placeholder — the
  command validates config and echoes what it *would* do, but does not yet
  perform real agent execution. Don't assume a task actually ran just
  because this command exits 0; check the printed output for the
  placeholder notice.

## If this skill itself fails to load

If deepagents logs something like:

```
WARNING - Cannot load skills from './skills': Path './skills': path_not_found
```

that's a `SkillsMiddleware` config issue, not an `agentic` CLI issue. Fix it
in the agent's Python setup, not here:

- `./skills` is resolved relative to the process's **cwd at runtime**, not
  the script file's location. Anchor it instead:
  ```python
  from pathlib import Path

  SKILLS_DIR = Path(__file__).parent / "skills"
  agent = create_deep_agent(model="...", skills=[str(SKILLS_DIR)])
  ```
- Confirm the directory actually contains a skill **subfolder** with a
  `SKILL.md` inside (`skills/agentic-cli/SKILL.md`), not a bare `SKILL.md`
  directly under `skills/`.
- If using `StateBackend` or another non-filesystem backend, a plain
  relative path won't resolve — seed the skill content into backend state
  with virtual paths (`/skills/...`) instead.

## Using `--help`

Every command and group supports `--help`. Run it through your execute
tool liberally instead of guessing at flags or relying solely on this
document — the CLI's docstrings are the source of truth and may have
changed since this skill was written.

```bash
agentic --help
agentic config --help
agentic config set --help
agentic agents run --help
```

Reach for `--help` in these situations:
- **Before running an unfamiliar command** for the first time in a session.
- **After any error** whose message references usage, arguments, or options
  (see the error-recovery workflow below) — check `--help` on that exact
  command before retrying.
- **When this document's example doesn't match** what you're seeing (e.g.
  a flag mentioned here errors as "no such option") — the installed
  version may differ from what's documented, and `--help` reflects reality.

## Automatic error recovery

When a command run through the execute tool fails, don't just surface the
raw error — work through it methodically before asking the user to
intervene.

1. **Read the actual error text and exit code returned by the execute
   tool**, not just "it failed." Click and this CLI raise distinct,
   informative errors — read stderr and stdout separately from the tool
   result if possible so you're not mixing usage errors with program
   output.

2. **Match the error to a likely cause and try one targeted fix**, then
   re-run:

   | Error looks like | Likely cause | Try |
   |---|---|---|
   | `Error: No such command` | Typo, or subcommand moved/renamed | `agentic --help` / `agentic <group> --help` to see current command tree |
   | `Error: No such option` / `Got unexpected extra argument` | Wrong flag name or argument order | `agentic <command> --help` to check exact signature, fix and retry |
   | `Error: Missing argument` / `Missing option` | Required arg/option omitted | Check `--help`, supply the missing piece |
   | `FileNotFoundError` / config file not found | Wrong working directory, or file path/name mismatch | Run `pwd`/`ls` (or check the execute tool's cwd parameter) to locate `agentic.json`; retry with an explicit file path argument |
   | `json.JSONDecodeError` | Config file has invalid JSON (trailing comma, wrong quotes, etc.) | Open and inspect the file; if you're the one who last wrote it, check for shell-quoting issues before assuming the file itself is hand-edited garbage |
   | Pydantic validation error from `AgenticConfig` | Config doesn't match expected schema | Run `agentic config schema` and compare field names/types against the file |
   | JSONPath match is empty (command succeeds, no output) | `key_path` doesn't match anything in the config | Run `agentic config get "$"` (or the closest valid root path) to see the whole structure, then correct the path |
   | Command hangs / doesn't return | You ran `agentic run` (a blocking server) inline | Re-run via your execute tool in background mode or with an explicit timeout, don't block the session on it |
   | `command not found: agentic` | Not installed globally / no active venv | Use `agentic` directly if in PATH, or use full path to executable |
   | `agentic` itself fails to resolve the command | Deps not installed, or wrong project root | Ensure dependencies are installed, confirm you're in the directory with `pyproject.toml`, then retry |

3. **Retry once with the fix applied.** If the second attempt still fails
   with the *same* error after checking `--help` and the schema, stop
   auto-retrying — surface the full error, what you tried, and ask the user
   rather than looping indefinitely or guessing further. Two failed
   attempts on the same root cause is the signal to stop, not three or
   four.

4. **Never silently swallow a failure.** If a fix works, briefly say what
   was wrong and what you changed, so the user isn't surprised by a config
   value that got corrected on their behalf. If a `config set` was involved
   in the recovery, always show the resulting JSON so they can verify it.

## Practical workflow tips

- **Always invoke through the execute tool, never simulate output.**
  Run every `agentic ...` command via your execute/terminal tool and read
  its actual returned stdout/stderr/exit code — don't guess or hand-write
  what the CLI "would" print.
- **Always `agentic mcp list` when unsure.** It's cheap and gives ground truth on
  available commands instead of relying on this document if the CLI has
  since changed.
- **Check the schema before blind writes.** `agentic config schema` avoids
  trial-and-error when a `config set` call fails validation.
- **Quote JSONPath expressions with brackets.** Paths like `agents[*].name`
  or `agents.[0].name` contain characters (`[`, `]`, `*`) that some shells
  will try to glob-expand — wrap them in quotes when passing the command to
  the execute tool.
- **Capture stdout, don't parse by eye.** `config get`/`config set`/`config
  schema` all print JSON — pipe to `python -m json.tool`, `jq`, or parse the
  captured string returned by the execute tool in your own code rather than
  eyeballing it.
- **Non-zero exit codes signal real failures**, not just warnings — the CLI
  calls `sys.exit(1)` on missing files, JSON decode errors, and missing
  agents. Check the exit status returned by the execute tool after each
  call, especially in scripted/agentic chains of commands.
