# Agentic

**Agentic** is a personal AI assistant platform (inspired by projects like OpenClaw) that runs as a long-lived bot, talks to you over chat channels like Telegram, and can autonomously plan and execute multi-step tasks using LLMs, tools, MCP servers, scheduled jobs, and durable memory.

It's built around a config-driven agent runtime: you describe agents, models, skills, and tools in a single `agentic.json` file, and the bot wires everything together — chat channel, LLM backend(s), MCP tool servers, scheduler, and a WebSocket/REST gateway — with no custom glue code required for common integrations.

## Why Agentic exists

Most "chatbot" demos stop at request/response. Agentic is meant to behave like a persistent personal assistant that:

- **Remembers things across sessions** instead of forgetting everything after each conversation.
- **Does real work on your behalf** (send emails, manage VMs, generate images, run shell commands) instead of just talking about it.
- **Runs on a schedule**, not only when you message it (e.g. daily summaries, memory compaction, recurring reminders).
- **Is provider-agnostic**, so you can point it at NVIDIA NIM endpoints, a local OpenAI-compatible server, or any other OpenAI-compatible model — including a lightweight local model for cheap routine tasks and a larger one for heavy reasoning.
- **Is extensible via MCP (Model Context Protocol)** and a skills directory, so new capabilities can be added without touching the core bot code.

## Key features / use cases

| Use case | How Agentic handles it |
|---|---|
| **Chat with an AI assistant from Telegram** | `python-telegram-bot` channel wired straight into the agent runtime — message the bot and it responds, keeps context, and can ask for approval before running risky actions. |
| **Multi-agent configuration** | Define multiple named agents in `agentic.json`, each with its own model, system prompt, workspace, skills, and allow/deny tool lists. |
| **Tool use with human-in-the-loop approval** | Tools (e.g. `run_shell_command`) can be flagged `require_approval: true` so the assistant must ask before executing anything destructive. |
| **Email automation** | Gmail MCP tools let the assistant read/send email using Google API credentials (OAuth token stored under `credentials/`). |
| **Home-lab / infrastructure control** | Proxmox MCP tools let the assistant inspect and manage VMs/containers on a Proxmox hypervisor. |
| **Image generation** | Stable Diffusion MCP tools plus a `generate_image` tool let the assistant create images on request (local or remote SD backend). |
| **Text-to-speech / audio** | `transformers`, `torch`, `soundfile`, and `sentencepiece` support local TTS pipelines (see `downloads/` for generated audio samples). |
| **Scheduled / recurring tasks (cron)** | An APScheduler-backed cron subsystem (`cron_schedules.json`) runs background sub-agents on a schedule — e.g. hourly memory compaction that summarizes the day's activity and reports back over Telegram. |
| **Long-term memory management** | `memory_retriever.py` and `memory_compaction.py` distill daily memory logs into a condensed `MEMORY.md`, so the assistant retains high-value context without unbounded log growth. |
| **Remote/streaming clients** | A FastAPI + WebSocket gateway (`app/gateway`) exposes the bot over HTTP/WebSocket for custom front-ends, alongside a Python WebSocket client (`websocket_client/`). |
| **Search-augmented answers** | Tavily web search integration (`langchain-tavily`) for up-to-date, grounded answers. |
| **Secrets management** | Secrets (bot tokens, API keys) are resolved via a config-driven env provider (`env://VAR_NAME` references in `application.yml`), keeping real values out of plaintext config. |
| **Extensible via skills & MCP** | Drop new capabilities into `src/skills/` (Markdown "skill" definitions, e.g. the `agentic-cli` skill that teaches the assistant to manage its own config) or point at additional MCP servers. |
| **CLI for operating the bot** | The `agentic` CLI can start the bot server, inspect/edit `agentic.json` via JSONPath, list configured agents, run an agent with a one-off task, and send test messages. |

## Architecture overview

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

See [`architecture.md`](architecture.md) for the conceptual component/data-flow breakdown.

### Project layout

```
src/
  agentic/
    app/              # Bot core: agents, config, channels, gateway, scheduler, memory
      channels/       # Telegram (and future) channel adapters
      gateway/        # FastAPI + WebSocket adapter for external clients
      scheduler/      # Cron-based scheduling of background sub-agent tasks
    agentic_mcp/       # MCP tool servers
      gmail/           # Gmail integration tools
      proxmox/         # Proxmox VE management tools
      stable_diffusion/# Image generation tools
    cli/               # `agentic` command-line interface (config, agents, mcp, message)
    websocket_client/  # Example WebSocket client for the gateway
    bot_app.py         # Application entry point / bootstrap
  skills/              # Markdown-based skill definitions loaded by the agent
resources/
  agentic.json         # Agent/model/tool/MCP configuration (the "brain" wiring)
  application.yml       # Runtime/framework config (secrets provider, channels, brokers)
cron_schedules.json     # Scheduled background tasks (e.g. hourly memory compaction)
docker-compose.yaml     # `bot` (assistant) + `mcp` (tool server) services
```

## Tech stack

- **Language:** Python 3.14+
- **Agent framework:** [deepagents](https://pypi.org/project/deepagents/) on top of LangChain (`langchain-openai`, `langchain-nvidia-ai-endpoints`, `langchain-mcp-adapters`, `langchain-tavily`)
- **Tool protocol:** MCP (`mcp[cli]`, `fastmcp`)
- **Chat channel:** `python-telegram-bot`
- **Web/gateway:** FastAPI + `uvicorn`, WebSockets
- **Scheduling:** APScheduler
- **Storage:** TinyDB, SQLAlchemy, optional Elasticsearch
- **Secrets:** environment-variable-backed provider via `cndi.secrets` (`env://VAR_NAME` references in `application.yml`)
- **ML/audio:** `transformers`, `torch`, `soundfile`, `sentencepiece`
- **Infra integrations:** Google API client (Gmail), Proxmoxer (Proxmox VE)
- **Packaging/build:** `uv` (PEP 621 `pyproject.toml`, `uv_build` backend)

## Getting started

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker & Docker Compose (optional, for containerized deployment)
- A Telegram bot token, and/or an NVIDIA NIM / OpenAI-compatible API key, depending on which integrations you want

### 1. Install dependencies

```powershell
uv sync
```

### 2. Configure the assistant

Edit `resources/agentic.json` to define your model(s), agent(s), skills, tool permissions, and MCP servers. Edit `resources/application.yml` for channel tokens and secrets provider settings — secrets are referenced as `env://VAR_NAME` and resolved from environment variables at runtime by the env secrets provider (`secrets.provider.env.enable: true`).

Minimal environment variables typically needed:

```powershell
$env:NVIDIA_API_KEY = "..."
$env:TELEGRAM_BOT_TOKEN = "..."
$env:TELEGRAM_DEFAULT_CHAT_ID = "..."
$env:TAVILY_API_KEY = "..."
```

### 3. Run locally

```powershell
uv run agentic run
```

Or use the CLI to inspect/manage configuration first:

```powershell
uv run agentic config schema
uv run agentic agents list
uv run agentic message add "Hello, this is a test message"
```

### 4. Run with Docker Compose

```powershell
Copy-Item .env.example .env
# edit .env: set NVIDIA_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_DEFAULT_CHAT_ID / TAVILY_API_KEY
docker-compose up --build
```

This starts:
- `bot` — the assistant/chat runtime (health-checked on `:5000/health`)
- `mcp` — the MCP tool server exposing Gmail, Proxmox, and Stable Diffusion tools on `:8082`

## Scheduling background tasks

`cron_schedules.json` defines recurring sub-agent jobs (cron expression, target channel/chat, tools, and system prompt). For example, an hourly job distills daily memory logs into `MEMORY.md` and reports a summary back over Telegram — keeping the assistant's long-term memory small and high-value without manual upkeep.

## Extending Agentic

- **Add a tool/integration:** create a new MCP server under `src/agentic/agentic_mcp/<your_tool>/` and register it in `resources/agentic.json` under `mcpServers`.
- **Add an agent:** create `workspace/agents/<name>/instructions.md` and register it in `resources/agentic.json`'s `agents` array — see [`docs/creating-agents-and-skills.md`](docs/creating-agents-and-skills.md) for the full walkthrough.
- **Add a skill:** drop a folder with a `SKILL.md` (and any helper scripts) under `src/skills/`; the agent's skills middleware picks it up automatically — see [`docs/creating-agents-and-skills.md`](docs/creating-agents-and-skills.md) for a step-by-step guide.
- **Add a channel:** implement a new adapter under `src/agentic/app/channels/` alongside the existing Telegram adapter.
- **Add a scheduled job:** append an entry to `cron_schedules.json` with a cron expression, delivery target, and sub-agent definition.

## Contributing

Contributions are welcome — bug fixes, new MCP tools/integrations, channel adapters, skills, or documentation improvements. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup instructions, coding guidelines, and how to submit a pull request or maintain a fork.

## License

This project is licensed under the **MIT License with an Attribution Requirement** — see [`LICENSE`](LICENSE) for full terms. In short: you're free to use, modify, distribute, and fork this project, but any use or derivative work must include clear acknowledgement of the original author, **Mayank Shinde**, and the original **Agentic** project.

