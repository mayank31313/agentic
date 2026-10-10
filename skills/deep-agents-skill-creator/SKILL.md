---
name: deep-agents-skill-creator
description: >-
  Create, validate, and improve SKILL.md skills for Agentic and yourself. Use this whenever the
  user wants to author a new skill, package a workflow as a reusable skill,
  fix a skill that isn't triggering or loading in a deep agent, review a
  SKILL.md against the Agent Skills specification, or set up a skills/
  directory for create_deep_agent. Trigger this for phrases like "make a
  skill for deep agents", "write a SKILL.md", "why isn't my skill loading",
  "package this workflow as a skill", or "set up skills for my agent" — even
  if the user doesn't say "deep agents" explicitly but is clearly working
  with create_deep_agent, SkillsMiddleware, or a deepagents backend.
license: MIT
metadata:
  author: user
  framework: langchain-deepagents
---

# Deep Agents Skill Creator

A meta-skill for writing skills that LangChain Deep Agents (`deepagents`)
can discover and load via `SkillsMiddleware`. Deep Agents skills follow the
[Agent Skills specification](https://agentskills.io/specification) — the
same spec used by Claude Code and Claude.ai — but Deep Agents adds its own
loading rules (virtual filesystem paths, backends, subagent isolation,
"last source wins") that make certain choices matter more than they would
in other harnesses. This skill captures both.

## Workflow

1. **Capture intent** — figure out what the skill should do and where it fits.
2. **Interview** — nail down triggering, inputs/outputs, and deployment target.
3. **Write the SKILL.md** — frontmatter + instructions, following the spec.
4. **Add supporting resources** — scripts/, references/, assets/ as needed.
5. **Place it correctly** — under a `skills/` directory the agent's `skills=[...]` argument can reach.
6. **Validate & test** — check the frontmatter, then actually invoke the agent.

Jump to whichever step matches where the user already is — if they have a
draft SKILL.md, skip to step 6.

---

## Step 1–2: Capture Intent & Interview

Ask (inline, not necessarily as a numbered interrogation):

1. **What should the skill do?** A workflow, a piece of domain knowledge, a
   bundled script, or a style/guardrail?
2. **When should it trigger?** What phrases or task types should cause the
   agent to activate it? This becomes the `description` — the single most
   important field (see Step 3).
3. **Does it need code execution — and which kind?** Deep Agents has three
   tiers; pick the cheapest one that fits the workflow:
   - **Normal tool calls** — one or two external calls, nothing to loop or
     branch on. No extra setup needed.
   - **Interpreter (in-memory JS via QuickJS)** — loops, branches, retries,
     or data transforms with no OS access, or orchestrating many tool
     calls/subagents from code so intermediate results don't all hit the
     model's context. Requires `CodeInterpreterMiddleware` from
     `langchain-quickjs` configured on the *agent*, plus (optionally) a
     PTC allowlist. See `references/interpreters.md`.
   - **Sandbox** — shell commands, package installs, tests, or real
     filesystem/network access. Requires a sandbox backend; a skill's
     `scripts/*.py` (or similar) can only be *read* on a plain backend and
     needs a sandbox attached to actually *run*.
   These aren't exclusive — a skill can describe an interpreter pattern in
   its instructions and still ship `scripts/` meant for a sandboxed run.
4. **Where will this skill live?** This determines the directory layout:
   - Local project → `FilesystemBackend`, skill lives on disk under a
     `/skills/[skill-name]` folder.
   - Per-thread/ephemeral → `StateBackend`, seeded via `invoke(files={...})`.
   - Shared across users/durable → `StoreBackend`, seeded via `store.put()`.
   - Multi-tenant → `StoreBackend` with a namespace factory (one skill set
     per org/user).
5. **Does a subagent need it?** Only the **general-purpose** subagent
   automatically inherits the main agent's skills. Custom subagents need
   their own `skills=[...]` list in their subagent definition — skill state
   is otherwise fully isolated between main agent and subagents.

Don't write test prompts until this is settled.

---

## Step 3: Write the SKILL.md

### Frontmatter (required: `name`, `description`)

| Field | Required | Constraint |
|---|---|---|
| `name` | Yes | Lowercase alphanumeric + hyphens, 1–64 chars. **Must exactly match the parent directory name.** |
| `description` | Yes | What it does *and* when to use it. Max 1,024 chars. This is the *only* thing the agent sees at discovery — see below. |
| `license` | No | License name or reference to a bundled license file. |
| `compatibility` | No | Environment requirements (packages, network access). Max 500 chars. |
| `metadata` | No | Arbitrary key-value pairs. |
| `allowed-tools` | No | Space-separated pre-approved tools. Experimental. |

Full field-by-field detail and edge cases: `references/frontmatter-spec.md`.

### Writing the description (this is where skills succeed or fail)

At discovery, `SkillsMiddleware` injects only `name` + `description` into
the system prompt for every configured skill. The agent picks a skill
*based on this text alone*. Make it specific, and pack in both the "what"
and the "when":

```yaml
# Good — specific about what and when, with matchable keywords
description: >-
  Extract text and tables from PDF files, fill PDF forms, and merge
  multiple PDFs. Use when working with PDF documents or when the user
  mentions PDFs, forms, or document extraction.

# Poor — too vague, will under-trigger or never trigger
description: Helps with PDFs.
```

If you're drafting several related skills, check their descriptions
against each other — overlapping descriptions cause the agent to hesitate
or pick the wrong one. Either sharpen the differentiation or consolidate
into one skill with sections.

### Body

Write the body as instructions the agent follows once it has activated the
skill (this loads in full, so it's more forgiving of length than the
description — but still keep the whole `SKILL.md` under ~5,000 tokens /
500 lines). Include:

- **Step-by-step procedure(s)** for the workflow
- **Decision criteria** when there's more than one path
- **Example inputs/outputs** so the agent knows what success looks like
- **Edge cases** to handle or flag to the user
- **Explicit pointers** to any `scripts/`, `references/`, or `assets/`
  files, stating what each contains and when to read/run it — the agent
  does not auto-discover supporting files, and Deep Agents does not load
  them at discovery or activation regardless

If the body is creeping past ~500 lines, split detail into
`references/*.md` and link to it — keep reference chains one level deep
from `SKILL.md` (don't make the agent hop through multiple files).

### Skills that use the interpreter instead of `scripts/`

If the workflow is "loop over N items," "compose several tool calls
without every intermediate result returning to the model," or
"deterministically transform structured data" — and it doesn't need OS,
filesystem, or network access — write it as an **interpreter** pattern
rather than a bundled script:

- The SKILL.md body should show the *shape* of the JavaScript the agent
  should write into the `eval` tool (a short inline example is enough,
  not a full script file), plus which tools it expects available under
  `tools.*` via programmatic tool calling (PTC).
- State the PTC allowlist the skill assumes (e.g. `web_search`,
  `read_file`). PTC is enabled per tool when the *agent* is created
  (`CodeInterpreterMiddleware(ptc=[...])`) — the skill can't turn it on
  itself, so call out the dependency in `compatibility` so it's visible
  before the skill is even activated.
- Note that the interpreter has **no filesystem, network, or clock
  access** by default — only what's explicitly bridged through PTC. Don't
  assume it can read skill files or the backend directly.
- If part of the workflow also needs real OS-level effects (writing an
  actual file, running a shell command), that part still belongs in
  `scripts/` + a sandbox — it's fine for one skill to use both.

Full quickstart, PTC, dynamic subagents (`task()`), and persistence modes
are in `references/interpreters.md`.

---

## Step 4: Supporting Resources

```
skills/
└── my-skill/
    ├── SKILL.md          # required
    ├── scripts/           # executable code (needs a sandbox backend to run)
    ├── references/        # docs loaded only when SKILL.md points to them
    └── assets/             # templates, schemas, images — copied/used, not read as instructions
```

Reference every supporting file from `SKILL.md` with a relative path and a
one-line note on when to use it, e.g.:

```md
For API details, see the [reference guide](references/api-patterns.md).

To extract tables from a PDF, run:
scripts/extract.py
```

---

## Step 5: Placement & Wiring

Deep Agents skills are discovered from whatever paths you pass in the
`skills=[...]` argument to `create_deep_agent` — nothing is auto-scanned.
Key rules:

- **Paths use forward slashes always**, relative to the backend root
  (even on Windows). E.g. `/skills/my-skill/SKILL.md`.
- **`name` in frontmatter must match the directory name** — mismatches
  cause the skill to fail discovery or validation.
- **Last source wins.** If the same skill `name` appears in more than one
  path passed to `skills=[...]`, the source listed *later* in the array
  overrides earlier ones. This is intentional for base-skill +
  project-override layering, but a common bug source if unintended.
- **10 MB per-file limit.** `SKILL.md` files over 10 MB are silently
  skipped during discovery.
- Full backend-specific setup snippets (StateBackend / StoreBackend /
  FilesystemBackend, sandbox syncing, multi-tenant namespacing) are in
  `references/deployment-patterns.md` — pull that in once you know which
  backend the user is targeting.

---

## Step 6: Validate & Test

**Validate the frontmatter** before testing behavior:
- `name` matches the directory name, lowercase-hyphenated, ≤64 chars
- `description` ≤1,024 chars and states both what + when
- Use the [`skills-ref` validation tool](https://github.com/agentskills/agentskills/tree/main/skills-ref)
  if available, to check spec conformance mechanically.

**Test with a real agent**, not just a read-through:

```python
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

backend = FilesystemBackend(root_dir="./my-project")
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    backend=backend,
    skills=["./my-project/skills/"],
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "<a prompt that should trigger the skill>"}]},
    config={"configurable": {"thread_id": "test-1"}},
)
```

Check (ideally via a LangSmith trace, if the user has it set up):
1. Did the skill's `name`/`description` appear in the system prompt at
   startup?
2. Did the agent call `read_file` on the skill's `SKILL.md` when given a
   matching prompt?
3. Did it follow the instructions correctly, including reading/running any
   referenced supporting files?
4. Try a near-miss prompt too — confirm the skill *doesn't* fire when it
   shouldn't, and that it doesn't collide with another skill's description.

If activation fails or is flaky, walk through `references/troubleshooting.md`
rather than guessing — it maps each symptom to a specific, likely cause.

---

## Quick Reference

- Spec: https://agentskills.io/specification
- Deep Agents skills docs: https://docs.langchain.com/oss/python/deepagents/skills
- Interpreters docs: https://docs.langchain.com/oss/python/deepagents/interpreters
- Sandboxes docs: https://docs.langchain.com/oss/python/deepagents/sandboxes
- Example skills: https://github.com/langchain-ai/deepagents/tree/main/libs/cli/examples/skills
- Curated skill library: https://github.com/langchain-ai/langchain-skills
- Starter template: `assets/SKILL.md.template`