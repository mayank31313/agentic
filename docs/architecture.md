# Architecture

This document describes the conceptual components of Agentic and how they interact. For
setup and usage instructions see [`README.md`](../README.md); for contribution guidelines see
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Component overview

```
[Telegram / WebSocket clients]
            │
            ▼
     [Channel Adapter]  ──▶  [Core AI Agent Engine] ──▶ [MCP Tool Servers: Gmail, Proxmox, Stable Diffusion, ...]
            │                       │
            │                       ├─▶ [Memory & State: MEMORY.md, daily logs, TinyDB]
            │                       ├─▶ [Scheduler: cron_schedules.json + sub-agents]
            │                       └─▶ [Skills: Markdown-defined behaviors, e.g. agentic-cli]
            ▼
   [FastAPI/WebSocket Gateway]
```

- **Channel Adapter** (`src/agentic/app/channels/`): receives/sends messages for a given chat
  surface (currently Telegram) and forwards them to the core agent engine.
- **Core AI Agent Engine** (`src/agentic/app/`): built on `deepagents`/LangChain, resolves the
  configured model(s), skills, and tool permissions for each agent defined in
  `resources/agentic.json`, and drives the request/response and tool-call loop.
- **MCP Tool Servers** (`src/agentic/agentic_mcp/`): standalone Model Context Protocol servers
  exposing integrations such as Gmail, Proxmox VE, and Stable Diffusion as callable tools.
- **Memory & State**: daily memory logs and a condensed `MEMORY.md` (produced by
  `memory_retriever.py`/`memory_compaction.py`) plus a SQLite-backed key/value data store
  (`src/agentic/app/db/`, schema-managed via Alembic, exposed to agents through the
  `sqlite_store` MCP tools) give the assistant durable, long-term context across sessions.
- **Scheduler** (`src/agentic/app/scheduler/`): an APScheduler-backed cron subsystem that reads
  `cron_schedules.json` and runs background sub-agent jobs (e.g. hourly memory compaction).
- **Skills** (`src/skills/`): Markdown-defined behaviors (a `SKILL.md` plus optional helper
  scripts) that the agent's skills middleware loads automatically to extend capabilities without
  changing core code.
  See [`docs/creating-agents-and-skills.md`](creating-agents-and-skills.md) for how to add a
  new agent (`workspace/agents/<name>/instructions.md` + `resources/agentic.json`) or a new skill.
- **FastAPI/WebSocket Gateway** (`src/agentic/app/gateway/`): exposes the running bot over
  HTTP/WebSocket for custom front-ends, alongside the example client in
  `src/agentic/websocket_client/`.

## Project layout

```
src/
  agentic/
    app/              # Bot core: agents, config, channels, gateway, scheduler, memory
      channels/       # Telegram (and future) channel adapters
      gateway/        # FastAPI + WebSocket adapter for external clients
      scheduler/      # Cron-based scheduling of background sub-agent tasks
      db/             # SQLAlchemy models/engine/repository for the SQLite data store
    agentic_mcp/       # MCP tool servers
      gmail/           # Gmail integration tools
      proxmox/         # Proxmox VE management tools
      stable_diffusion/# Image generation tools
      sqlite_store/    # CRUD tools over the SQLite data store
    cli/               # `agentic` command-line interface (config, agents, mcp, message)
    websocket_client/  # Example WebSocket client for the gateway
    bot_app.py         # Application entry point / bootstrap
  skills/              # Markdown-based skill definitions loaded by the agent
resources/
  agentic.json         # Agent/model/tool/MCP configuration (the "brain" wiring)
  application.yml       # Runtime/framework config (secrets provider, channels, brokers)
cron_schedules.json     # Scheduled background tasks (e.g. hourly memory compaction)
docker-compose.yaml     # `bot` (assistant) + `mcp` (tool server) services
alembic.ini              # Alembic config for the SQLite data store
alembic/                 # Migration environment + versioned schema revisions
workspace/data/agentic.db  # SQLite database file (created on first migration, gitignored)
```

## Configuration-first design

Agentic favors configuration over code changes: agents, models, skills, tool permissions, and
MCP servers are described in `resources/agentic.json`, while channel/runtime settings (secrets
provider, tokens) live in `resources/application.yml`. Adding a new integration or scheduled job
typically only requires registering it in these files rather than modifying the core runtime —
see the "Extending Agentic" section of [`README.md`](../README.md) for details.

## Secrets resolution

`resources/application.yml` enables the env secrets provider
(`secrets.provider.env.enable: true`) and resolves secrets like the Telegram
token and Tavily API key via `env://VAR_NAME` references, which are looked up
from process environment variables at runtime (see `.env.example` for the
full list). This keeps real credentials out of version control while
remaining fully config-driven — no plaintext secrets or external secret
stores are required.

