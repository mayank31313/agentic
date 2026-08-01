---
name: agentic-cli
description: Use this skill whenever the user wants to interact with your configuration or its agentic.json configuration — including starting the bot server, sending messages, reading config values, and adding, creating, updating, removing, listing, or running configured agents (e.g. "add a new agent for image processing", "create an agent that does X", "update the model for the summarizer agent", "remove an agent from the config", "what agents are configured"). Also covers inspecting the config JSON schema and listing available MCP tools. Trigger this any time the user mentions "agentic cli", "agentic.json", the bot app, agent configuration, or asks to check/change any value in the bot's config — including requests that don't literally say "config" but describe adding/editing/removing an agent entry. Always invoke the tool via shell (via scripts/run_agentic.py) rather than guessing at or hand-writing config file contents.
---

# Agentic CLI

A Click-based command-line tool (entry point: `agentic`) for managing a bot
application: starting its server, sending messages, reading/writing its
`agentic.json` configuration via JSONPath, and listing/running configured
agents. Run all of these as real shell commands — don't hand-edit
`agentic.json` or guess at output; call the CLI and read what it prints.

## Before you start

This project is `uv`-managed, so **always invoke the CLI as `uv run agentic`**,
not a bare `agentic` — a bare invocation will fail or silently use the wrong
Python environment (missing deps, stale install) if the project venv isn't
already activated.

Confirm the CLI is installed and runnable:

```bash
uv run agentic --help
```

If that fails, try, in order:

```bash
uv sync                        # ensure deps/venv are installed, then retry
uv run python -m app.cli --help   # in case the console-script entry point isn't registered
```

Check the project's `pyproject.toml` for the console-script entry point name
(under `[project.scripts]`) before assuming the command is `agentic`.

**Always run `uv run agentic ...` from the project root** — this is also
where `agentic.json` lives, since `config`/`agents` subcommands read it from
the **current working directory** by default. If you're not in the project
root, either `cd` there first or pass an explicit file path as the trailing
argument where the command supports it. `uv run` itself does not change your
cwd — it just resolves the project's venv from the nearest `pyproject.toml`.

## Preferred invocation: `scripts/run_agentic.py`

This skill bundles `scripts/run_agentic.py`, a thin wrapper around
`uv run agentic <...>` that captures stdout, stderr, and the exit code
**separately** and returns them as a single JSON object — instead of
merged, hard-to-parse shell output. Prefer this over calling `uv run
agentic` directly whenever you plan to inspect the result programmatically
(which is almost always, in an agent context).

```bash
python scripts/run_agentic.py -- config get telegram.bot_token
python scripts/run_agentic.py -- config schema
python scripts/run_agentic.py --cwd /path/to/project -- agents list
python scripts/run_agentic.py --timeout 5 -- config set telegram.bot_token --set telegram.bot_token=123:ABC
```

Output shape (always JSON on stdout, one line unless `--pretty` is passed):

```json
{
  "command": ["uv", "run", "agentic", "config", "get", "telegram.bot_token"],
  "cwd": "/path/to/project",
  "exit_code": 0,
  "success": true,
  "stdout": "\"123:ABC\"\n",
  "stderr": "",
  "stdout_json": "123:ABC",
  "timed_out": false
}
```

Notes on using it:
- `--` separates wrapper flags from the `agentic` subcommand — always
  include it if the wrapped command has its own `-`/`--` flags (e.g.
  `--set`, `-t`), to avoid argparse misparsing them as wrapper flags.
- `success` is `true` iff exit code was `0` — check this before trusting
  `stdout_json`.
- `stdout_json` is `null` whenever stdout wasn't valid JSON (e.g. plain-text
  confirmation messages) — fall back to reading `stdout` as text in that
  case.
- Default `--timeout` is 30s. **Never call `agentic run` through this
  wrapper without a short explicit `--timeout`** — it's a blocking server
  command and will otherwise hang until the wrapper's timeout kills it.
  Run `agentic run` directly in the background instead if you actually need
  the server up.
- `--cwd` lets you target a project root without a separate `cd`, useful
  when running multiple `agentic` calls against different projects in the
  same agent session.
- Exit code of the wrapper mirrors the wrapped command's exit code (127 if
  `uv` itself isn't found, 124 on timeout), so shell-level `$?` checks work
  too, in addition to parsing the JSON body.

## Command reference

### Discover what's available

```bash
uv run agentic mcp list
```
Prints every command and subcommand the CLI exposes. Run this first if
you're unsure a command still exists or want the full current surface area
— the tool may have grown commands beyond what's documented here.

### Run the bot server

```bash
uv run agentic run
```
Launches `bot_app.py` in the foreground and blocks until interrupted
(Ctrl+C). Only run this in the background (e.g. `uv run agentic run &` or a
subprocess with output capture) if you need the shell back — otherwise it
will hang the calling process.

### Send a message

```bash
uv run agentic message add "Hello, this is a test message"
```
Sends TEXT through the bot. Always quote the message text so shell
word-splitting doesn't break multi-word messages.

### Adding a new agent (no dedicated `agents add` command exists)

The CLI has `agents list` and `agents run`, but **no `agents add` /
`agents create` command** as of this version — check `uv run agentic agents
--help` to confirm that's still true before assuming otherwise. To add a
new agent, you go through `config set` against the `agents` array instead:

1. **Check the schema first** so the new entry has the right shape:
   ```bash
   python scripts/run_agentic.py -- config schema
   ```
2. **See the current agents array** to know the next index and existing structure:
   ```bash
   python scripts/run_agentic.py -- config get "agents"
   ```
3. **Append the new agent.** `jsonpath_ng`'s `.update()` replaces a matched
   node rather than appending to an array, so target the **new index
   directly** (current length of the array) rather than trying to "push":
   ```bash
   # if there are currently 2 agents (indices 0,1), target index 2
   python scripts/run_agentic.py -- config set "agents.[2]" \
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
   python scripts/run_agentic.py -- config get "agents.[2]"
   ```
   And remember: `config set` only prints the merged result — confirm
   separately whether the CLI actually persists to `file`, or whether
   you need to capture stdout and write it back yourself.

### List/read config values

```bash
uv run agentic config get <key_path> [file]
```
- `key_path` is a **JSONPath** expression (via `jsonpath_ng`), e.g.
  `telegram.bot_token`, `agents.[0].name`, `agents[*].model`.
- `file` defaults to `agentic.json` in the cwd if omitted.
- The file is validated against the `AgenticConfig` pydantic model before
  the JSONPath query runs — a malformed config will error out here rather
  than silently returning nothing.

Examples:
```bash
uv run agentic config get telegram.bot_token
uv run agentic config get "agents[*].name" custom_config.json
```

### Write config values

```bash
uv run agentic config set <key_path> --set key=value [--set key2=value2 ...] [file]
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
uv run agentic config set telegram.bot_token --set telegram.bot_token=123:ABC
uv run agentic config set "agents.[0]" --set name=Assistant --set model=gpt-4
```

⚠️ This command does **not** write the result back to `file` — it only
prints the merged config to stdout. If persistence to disk is expected,
verify that (check the source, or redirect/pipe the output to the file
yourself) rather than assuming the file changed after running `set`.

### Inspect the config schema

```bash
uv run agentic config schema
```
Prints the full JSON Schema for `AgenticConfig`. Run this before writing to
an unfamiliar config file, or when a `config set`/`get` call errors with a
validation message you don't understand — the schema tells you the exact
field names, types, and structure expected.

### List agents

```bash
uv run agentic agents list
```
Reads `agentic.json` in the cwd and prints each agent's name, model, and
tool count. Fails clearly if the file is missing or invalid JSON.

### Run an agent

```bash
uv run agentic agents run <agent_name> [--task "..."] 
uv run agentic agents run <agent_name> -t "..."
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

Every command and group supports `--help`. Use it liberally instead of
guessing at flags or relying solely on this document — the CLI's docstrings
are the source of truth and may have changed since this skill was written.

```bash
uv run agentic --help
uv run agentic config --help
uv run agentic config set --help
uv run agentic agents run --help
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

When a command run through this skill fails, don't just surface the raw
error — work through it methodically before asking the user to intervene.

1. **Read the actual error text and exit code**, not just "it failed."
   Click and this CLI raise distinct, informative errors — capture stderr
   and stdout separately if possible so you're not mixing usage errors with
   program output. `scripts/run_agentic.py` does this automatically; prefer
   it over raw shell calls when debugging a failure.

2. **Match the error to a likely cause and try one targeted fix**, then
   re-run:

   | Error looks like | Likely cause | Try |
   |---|---|---|
   | `Error: No such command` | Typo, or subcommand moved/renamed | `uv run agentic --help` / `uv run agentic <group> --help` to see current command tree |
   | `Error: No such option` / `Got unexpected extra argument` | Wrong flag name or argument order | `uv run agentic <command> --help` to check exact signature, fix and retry |
   | `Error: Missing argument` / `Missing option` | Required arg/option omitted | Check `--help`, supply the missing piece |
   | `FileNotFoundError` / config file not found | Wrong working directory, or file path/name mismatch | `pwd` and `ls` to locate `agentic.json`; retry with an explicit file path argument |
   | `json.JSONDecodeError` | Config file has invalid JSON (trailing comma, wrong quotes, etc.) | Open and inspect the file; if you're the one who last wrote it, check for shell-quoting issues before assuming the file itself is hand-edited garbage |
   | Pydantic validation error from `AgenticConfig` | Config doesn't match expected schema | Run `uv run agentic config schema` and compare field names/types against the file |
   | JSONPath match is empty (command succeeds, no output) | `key_path` doesn't match anything in the config | Run `uv run agentic config get "$"` (or the closest valid root path) to see the whole structure, then correct the path |
   | Command hangs / doesn't return | You ran `uv run agentic run` (a blocking server) inline | Re-run in the background or in a subprocess with a timeout, don't block the session on it |
   | `command not found: agentic` (running bare, without `uv run`) | Not installed globally / no active venv | Use `uv run agentic ...` instead of a bare `agentic ...` |
   | `uv run agentic` itself fails to resolve the command | Deps not synced, or wrong project root | `uv sync`, confirm you're in the directory with `pyproject.toml`, then retry |

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

- **Always `mcp list` when unsure.** It's cheap and gives ground truth on
  available commands instead of relying on this document if the CLI has
  since changed.
- **Check the schema before blind writes.** `uv run agentic config schema` avoids
  trial-and-error when a `config set` call fails validation.
- **Quote JSONPath expressions with brackets.** Paths like `agents[*].name`
  or `agents.[0].name` contain characters (`[`, `]`, `*`) that some shells
  will try to glob-expand — wrap them in quotes.
- **Capture stdout, don't parse by eye.** `config get`/`config set`/`config
  schema` all print JSON — pipe to `python -m json.tool`, `jq`, or parse the
  captured string in your own code rather than eyeballing it.
- **Non-zero exit codes signal real failures**, not just warnings — the CLI
  calls `sys.exit(1)` on missing files, JSON decode errors, and missing
  agents. Check exit status after each call, especially in scripted/agentic
  chains of commands.