# Frontmatter Spec Reference

Full detail on each YAML frontmatter field for a Deep Agents `SKILL.md`,
per the Agent Skills specification (https://agentskills.io/specification).

## `name` (required)

- Lowercase alphanumeric characters and hyphens only, `[a-z0-9-]`.
- 1–64 characters.
- **Must exactly match the parent directory name.** A skill at
  `skills/pdf-tools/SKILL.md` must have `name: pdf-tools`. This is a common
  source of "skill missing at startup" bugs — the loader validates this
  and will fail or skip the skill on mismatch.

## `description` (required)

- Free text, max 1,024 characters.
- The *only* signal the agent has during discovery (level 1 of progressive
  disclosure) — `SkillsMiddleware` puts `name` + `description` into the
  system prompt for every configured skill at startup, and nothing else.
- Must answer two questions in the same string: **what does this skill do**,
  and **when should the agent use it**. Include concrete keywords the user
  is likely to say, not just abstract capability names.
- Avoid overlap with other skills' descriptions in the same deployment —
  overlapping descriptions cause hesitation or wrong picks. When in doubt,
  consolidate two similar skills into one with clear sub-sections rather
  than maintaining near-duplicate descriptions.

## `license` (optional)

- A license name (e.g. `MIT`, `Apache-2.0`) or a reference to a bundled
  license file in the skill directory.

## `compatibility` (optional)

- Max 500 characters.
- Environment requirements: system packages, required network access,
  required Python/Node versions, whether it needs a sandbox backend to run
  bundled scripts, etc.
- Useful signal for a human or orchestration layer deciding which agents
  should be given this skill — Deep Agents itself doesn't enforce it, so
  don't rely on it as a runtime guard.

## `metadata` (optional)

- Arbitrary key-value pairs, e.g.:
  ```yaml
  metadata:
    author: langchain
    version: "1.0"
  ```
- Not interpreted by `SkillsMiddleware` — purely informational / for your
  own tooling (versioning, ownership, changelogs).

## `allowed-tools` (optional, experimental)

- Space-separated list of tool names the skill is pre-approved to use,
  e.g. `allowed-tools: fetch_url web_search`.
- Treat as experimental / forward-looking; don't assume it's enforced by
  every Deep Agents version. Confirm against the installed `deepagents`
  version's changelog if this matters for a security boundary.

## Hard limits enforced by Deep Agents

- `SKILL.md` files **over 10 MB are silently skipped** during discovery.
  If a skill "disappears," check file size first.
- Keep the full `SKILL.md` (frontmatter + body) under roughly 5,000 tokens
  / 500 lines as a practical ceiling — not a hard limit, but every skill's
  frontmatter is loaded for *every* configured skill at startup, so bloat
  compounds across a skill library.

## Minimal valid example

```md
---
name: arxiv-search
description: >-
  Search the arXiv preprint repository for research papers. Use when the
  user asks about academic papers, recent research, or scientific literature.
---

# arxiv-search

Search arXiv for papers matching the user's query.

## Instructions

1. Run `scripts/search.py` with the user's query as an argument.
2. Parse the results and present them with title, authors, abstract summary, and link.
3. If the user asks for more detail on a specific paper, fetch the full abstract.
```
