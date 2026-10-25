# Troubleshooting Reference

Symptom-first guide for skills that don't behave as expected in a Deep
Agents deployment. Work top to bottom within the matching symptom.

## Skill not activated (agent handles the task without reading SKILL.md)

1. **Description too vague.** The agent chooses purely from `description`
   at discovery. Rewrite to name both what the skill does and when to use
   it, with concrete keywords the user might actually say.
2. **Overlap with another skill.** If two skills have similar
   descriptions, the agent may hesitate or default to neither. Sharpen the
   differentiation, or consolidate into one skill.
3. **Not actually in the `skills` array.** Skills load only from paths
   passed at `create_deep_agent(..., skills=[...])`, or from a subagent's
   own `skills` parameter. Confirm the path is present and correct.

## Skill missing at startup (not listed in system prompt, or `read_file` on SKILL.md fails)

1. **Bad path.** Must use forward slashes, relative to the backend root.
   `FilesystemBackend` paths are relative to `root_dir`; `StateBackend`
   needs skill files supplied via `invoke(files={...})` using
   `create_file_data()` — raw strings aren't accepted.
2. **`name` doesn't match the directory name**, or frontmatter otherwise
   violates the spec. Run the `skills-ref` validation tool if available.
3. **File over 10 MB.** Silently skipped during discovery — check size.
4. **Shadowed by a later source.** When the same skill `name` exists in
   multiple entries of `skills=[...]`, the later entry wins. An empty or
   stale skill later in the list can silently override the correct one
   earlier in the list.

## Supporting files (scripts/references/assets) not found

1. **Not referenced from SKILL.md.** The agent does not auto-discover
   supporting files — state what each file contains and when to use it,
   with a relative path from the skill root.
2. **Path resolves against the wrong backend.** Confirm the referenced
   file actually exists at that path on whichever backend is active.
3. **Sandbox isolation.** If using a sandbox backend, files outside the
   sandbox container are invisible inside it. Skill files must be synced
   in explicitly (typically via a `before_agent` middleware hook that
   uploads them, and an `after_agent` hook that syncs changes back) — see
   "Execute code with skills" in the Deep Agents docs.

## Scripts fail to run (but SKILL.md reads fine)

- Reading a script works on any backend. **Running** it requires a
  sandbox backend (the agent needs an actual shell). Plain
  `StateBackend` / `StoreBackend` / `FilesystemBackend` deployments can
  only let the agent read scripts as reference material, not execute them.

## Subagent can't see a skill the main agent has

- Only the **general-purpose** subagent inherits the main agent's skills
  automatically. Any **custom** subagent definition needs its own
  `skills=[...]` entry — skill state is fully isolated between the main
  agent and subagents otherwise.

## General debugging approach

Use LangSmith traces to see exactly what happened at each stage:
discovery (system prompt contents), read (the `read_file` call on
`SKILL.md`), and execution (subsequent tool/file calls). Guessing from
symptoms alone is slower than checking the trace directly if the user has
tracing configured.
