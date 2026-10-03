# Deployment Patterns Reference

How to wire a finished skill into `create_deep_agent`, by backend.

## FilesystemBackend — local project, skills live on disk

```python
from pathlib import Path
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver

root_dir = "/Users/user/{project}"
backend = FilesystemBackend(root_dir=root_dir)

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    backend=backend,
    skills=[str(Path(root_dir) / "skills")],
    checkpointer=MemorySaver(),  # required if using human-in-the-loop
)
```

Simplest option for local dev and single-tenant apps. Skill edits on disk
are picked up on the next agent creation / process restart.

## StateBackend — ephemeral, per-thread

Skills must be seeded into the invoke call's `files` argument using
`create_file_data()` — raw strings aren't accepted, and virtual paths must
start with `/`.

```python
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data

backend = StateBackend()
skills_files = {
    "/skills/my-skill/SKILL.md": create_file_data(skill_md_content),
}

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    backend=backend,
    skills=["/skills/"],
)

result = agent.invoke(
    {"messages": [...], "files": skills_files},
    config={"configurable": {"thread_id": "..."}},
)
```

Use when skills should exist only for the current thread and don't need
to persist.

## StoreBackend — durable, shared across threads/users

```python
from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from deepagents.backends.utils import create_file_data
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
backend = StoreBackend(namespace=lambda _rt: ("filesystem",))

store.put(
    namespace=("filesystem",),
    key="/skills/my-skill/SKILL.md",
    value=create_file_data(skill_md_content),
)

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    backend=backend,
    store=store,
    skills=["/skills/"],
)
```

## Multi-tenant — namespaced skills per user/org

Route `/skills/` through a `CompositeBackend` to a `StoreBackend` whose
namespace is derived from runtime context, so each tenant only sees their
own skill set:

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    skills=["/skills/"],
    backend=CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": StoreBackend(
                namespace=lambda rt: (
                    rt.server_info.assistant_id,
                    rt.server_info.user.identity,
                ),
            ),
        },
    ),
)
```

For a shared curated library everyone should see, namespace by org ID
instead of user ID, and consider denying `write` operations under
`/skills/**` with a `FilesystemPermission` rule so only your own
application code (not the agent) can update the shared set.

## Read-only shared skills + writable personal skills, combined

Route `/skills/shared/` to an org-namespaced `StoreBackend` with writes
denied, and `/skills/personal/` to a user-namespaced `StoreBackend` left
writable, then pass both paths in `skills=[...]`. Place the more specific
deny rule (`/skills/shared/**`) before any broader rule so ordering
resolves correctly. See the Deep Agents permissions docs for rule-ordering
semantics.

## Executing bundled scripts (sandbox required)

A skill's `scripts/` files can be *read* from any backend, but *running*
them requires a sandbox backend (e.g. `LangSmithSandbox`). Skill files
outside the sandbox container aren't visible inside it — sync them in with
a `before_agent` middleware hook (upload) and sync changes back with an
`after_agent` hook (download), rather than assuming the sandbox can reach
the same backend the rest of the agent uses.

**If the skill's code doesn't actually need OS/filesystem/network
access** — it's just loops, retries, branching, or composing tool
calls — reach for an **interpreter** instead of a sandbox. It's lighter
weight (no container), runs in-process via QuickJS, and is configured with
`CodeInterpreterMiddleware` rather than a backend. See
`references/interpreters.md`.