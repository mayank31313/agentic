# Project structure

A map of the Agentic repository: what each directory and source file is for, and where to
make a change. It is written for contributors and coding agents who need to update, rewrite,
or extend Agentic. For the conceptual component view see [Architecture](architecture.md); for
adding agents and skills see [Creating agents and skills](creating-agents-and-skills.md).

!!! tip "Keeping this page accurate"
    If you add, move, rename, or delete a file under `src/`, update the matching table on this
    page in the same pull request. See [Maintaining this page](#maintaining-this-page).

## Top-level layout

```
.
├── src/agentic/          # All Python source (the installable `agentic` package)
├── skills/               # Markdown-defined skills loaded by agents
├── workspace/            # Runtime workspace: agent prompts, memory files, data, custom tools
├── resources/            # Config: agentic.json (agents/models/MCP) + application.yml (runtime)
├── alembic/              # Database migration environment + versions
├── tests/                # unittests/ (pytest) and integration/ (BDD, docker)
├── docs/                 # MkDocs site sources (this page lives here)
├── docker-compose*.yaml  # bot + MCP services, test stack, Langfuse stack
├── alembic.ini           # Alembic config
├── pyproject.toml        # Dependencies, `agentic` script entry point, pytest config
├── mkdocs.yml            # Docs site config and nav
├── cron_schedules.json   # Scheduled jobs (TinyDB file, created at runtime)
└── .env.example          # Environment variables / secrets template
```

## How a request flows

1. `agentic run` (`src/agentic/__init__.py`) calls `run_bot()` in `bot_app.py`.
2. `bot_app.py` creates the `cndi` application context, builds `AgenticConfig` from
   `resources/agentic.json`, and injects the `AgenticBot`, `Gateway` and
   `WebSocketConnectionManager` beans.
3. `AgenticBot.initialise_agent()` collects tools (`ToolsRegistry`: MCP tools, sub-agents,
   custom tools, cron tools) and builds the main deep agent through `get_main_agent()`.
4. A channel adapter (Telegram polling or the WebSocket endpoint `/ws/{chat_id}` on port 5000)
   turns incoming traffic into an `InboundMessage` and hands it to the `Gateway`.
5. `AgenticBot.invoke_agent()` runs the agent, handling tool calls and human-approval
   interrupts. The reply goes back as an `OutboundMessage` through the same adapter.
6. In parallel, the APScheduler cron subsystem runs saved jobs against agents from the
   `AgentRegistry`, and MCP servers (`agentic mcp run`) serve integration tools over HTTP.

## `src/agentic/` (root)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Click CLI entry point (`agentic` script). Defines the `run` command and `main()`, which attaches the `message`, `mcp`, `agents`, `config` and `tools` command groups. | Adding a top-level CLI command or group. |
| `bot_app.py` | Application bootstrap. Provides the `getAgenticConfig()` bean (loads or creates `agentic.json`), `main()` (init agent, start FastAPI gateway in a thread, optionally start Telegram polling) and `run_bot()`. | Changing startup order, ports, or which services start. |

## `src/agentic/app/` (bot core)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker for the `cndi` component scan. | Rarely. |
| `bot.py` | `AgenticBot` component. Owns the compiled agent, tool registry, memory and event bus. `initialise_agent()`, `reload_tools()`, `invoke_agent()` (runs the agent, handles interrupts). | Changing how messages are processed or how the agent is (re)built. |
| `agents.py` | Agent construction. `get_main_agent()` builds the deep agent (model, `CompositeBackend` routes, tools, middleware, checkpointer, approval gates); `AgentRegistry` stores named agents; also `get_image_agent()` and speech-to-text / text-to-speech pipeline getters. | Changing agent wiring, backends, or approvals. |
| `config.py` | Pydantic config models: `AgenticConfig`, `AgentConfig` (loads `instructions.md`), `ModelConfig`, `SkillsConfig`, `ToolConfig`, `EmbeddingConfig`, `VectorStoreConfig`, `RateLimitConfig`, plus `get_nested`/`set_nested` helpers. | Adding or changing any `agentic.json` / agent-header field. |
| `constants.py` | Config property keys and event names (`CRON_UPDATE_EVENT`, Telegram and LocalAI property names). | Adding a new shared property key or event name. |
| `memory_retriever.py` | `MemoryRetriever`: semantic memory over a pluggable vector store. | Changing how memories are stored or searched. |
| `memory_compaction.py` | Builds the memory-compaction agent that summarises old conversation history. | Changing the compaction prompt or model. |
| `vectorstore_factory.py` | Single extension point for vector-store backends (Chroma, Elasticsearch, in-memory…). Add a `_build_<backend>` and register it in `_BACKEND_BUILDERS`. | Supporting a new vector database. |
| `image_agent.py` | `DefectFixPromptAgent`: uses a vision model to turn a defective image into fix and negative prompts. Also runnable as a script. | Changing image-defect repair behaviour. |
| `observability.py` | `get_langfuse_handler()`: authenticates Langfuse and returns the LangChain tracing callback. | Changing tracing or observability. |
| `heartbeat.py` | `HeartBeatConfig` model (interval, enabled). | Changing heartbeat settings. |

### `app/common/` (shared by every agent)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Shared types: `InterruptEvent`, `MessageAction`, `MessageType`. | Adding a shared message or event type. |
| `tools.py` | `ToolsRegistry` (aggregates and refreshes LangChain, MCP, sub-agent and custom tools), `agent_as_tool`, `register_workspace_sub_agents`, `set_common_tools`, shell and CLI helpers (`agentic_run_agentic_cli` allowlist), `get_date_time`. | Adding a built-in tool or changing how tools are registered. |
| `custom_tools.py` | Framework for agent-authored tools stored in `workspace/custom_tools/<name>/`: source validation, arg models, sandboxed loading, approval flow. | Changing custom-tool validation or lifecycle. |
| `backends.py` | `AgenticShellBackend` (filesystem + local shell) for workspace sub-agents. Sub-agents can opt in with `enable_shell_backend`; in this path, `execute` always needs human approval. The main agent's shell backend is wired separately and is not covered by these guarantees. | Adding or hardening a deepagents backend. |
| `middleware.py` | `ToolNotifierMiddleware`: notifies the channel before and after tool calls. | Changing tool-event notifications or adding middleware. |
| `memory.py` | `Memory`: stores conversation messages and bridges to `MemoryRetriever`. | Changing conversation storage. |
| `audio.py` | Voice support: ogg→mp3 conversion via `ffmpeg`, speech-to-text and text-to-speech beans. | Changing audio handling. |
| `commands.py` | `get_agentic_commands(channel)`: slash-command handlers exposed to channels (currently `help`). | Adding a channel-agnostic chat command. |
| `providers.py` | `DateTimeProvider`: injectable date and time helpers. | Changing time sources (useful for tests). |

### `app/db/` (SQLite data store)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker. | Rarely. |
| `engine.py` | Engine and session factory. DB path defaults to `alembic/data/agentic.db` relative to the working directory, overridable via `AGENTIC_SQLITE_PATH`. | Changing DB location or connection settings. |
| `models.py` | SQLAlchemy `Base` and the generic key/value `DataRecord` model. Every schema change needs an Alembic migration. | Adding a table or column. |
| `schemas.py` | Pydantic schemas `DataRecordCreate`, `DataRecordUpdate`, `DataRecordRead`. | Changing the validated shape of records. |
| `repository.py` | CRUD functions plus `RecordNotFoundError` and `RecordAlreadyExistsError`. Keeps persistence out of tool code. | Adding queries or persistence rules. |
| `migrate.py` | Runs `alembic upgrade head` programmatically (idempotent, called at startup). | Changing migration bootstrap. |

### `app/gateway/` (FastAPI and channel adapters)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker. | Rarely. |
| `server.py` | `get_adapter_gateway()`: FastAPI app factory with the WebSocket endpoint `/ws/{chat_id}`, webhook routes and the `/admin/tools/reload` endpoint. | Adding HTTP or WebSocket endpoints. |
| `config.py` | `Gateway` component: routes `InboundMessage`s to the bot and delivers `OutboundMessage`s through adapters. | Changing routing between channels and the bot. |
| `client.py` | `BotClient`: placeholder client returning mock responses. | Replacing the stub with a real client. |
| `adapters/__init__.py` | Channel contract: `InboundMessage`, `OutboundMessage`, `OutboundMessageReply`, abstract `ChannelAdapter`, and `AdapterRegistry`. | Changing the adapter interface. |
| `adapters/consts.py` | Adapter constants (e.g. `TELEGRAM_SECRET` from the environment). | Adding adapter-level constants. |
| `adapters/websockets.py` | `WebSocketConnectionManager` and the WebSocket adapter (connect, disconnect, send, broadcast). | Changing WebSocket delivery. |
| `adapters/telegram/__init__.py` | Package marker. | Rarely. |
| `adapters/telegram/bot.py` | `TelegramAdapter` plus `/start` and `/clear` handlers, command enrolment, audio handling, message splitting (4096 chars) and sending. | Changing Telegram behaviour. |
| `adapters/telegram/config.py` | `TelegramMessageMetadata` model. | Changing Telegram message metadata. |
| `adapters/telegram/reactions.py` | `add_reaction` and `remove_reaction` helpers for message emoji. | Changing reaction UX. |

**New channel (Slack, Discord…):** add `adapters/<channel>/` implementing `ChannelAdapter`,
register it with `AdapterRegistry`, and start it from `bot_app.py`.

### `app/scheduler/` (cron)

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker. | Rarely. |
| `cron_scheduler.py` | APScheduler bean. Loads jobs from `cron_schedules.json` (`CRON_SCHEDULE_FILENAME`, TinyDB), runs `execute_task()` against agents in `AgentRegistry`, and reacts to `CRON_UPDATE_EVENT`. | Changing how jobs are scheduled or executed. |
| `tools.py` | Models `CronSettings`, `CronSchedule`, `Delivery`, `SubAgentConfig` (validates `agent_name` format and, in the tools, that the agent exists), and agent tools `create_cron_tool`, `update_cron_tool`, `delete_cron_tool`, `list_cron_tool`. | Changing the cron schema or its tools. |

## `src/agentic/agentic_mcp/` (MCP tool servers)

`agentic_mcp/__init__.py` creates the `FastMCP("Agentic MCP")` server, registers every tool
module (some only when their environment variables are set) and runs it over HTTP
(default `127.0.0.1:8811`) via `agentic mcp run`. Servers are consumed by the bot through
`mcpServers` in `resources/agentic.json`.

| File | Purpose | Tools / requirements |
|---|---|---|
| `__init__.py` | MCP server bootstrap and tool registration. | Edit to register a new tool module. |
| `gmail/tools.py` | Gmail integration. | `search_gmail_messages`, `get_message_from_message_id`, `list_gmail_attachments`, `download_gmail_attachment`. Needs `GOOGLE_CREDENTIALS_FILE`. |
| `gcalendar/tools.py` | Google Calendar integration. | `list_calendar_events`, `get_todays_schedule`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`. Needs `GOOGLE_CREDENTIALS_FILE`. |
| `openweather/tools.py` | Weather. | `get_current_weather`, `get_weather_forecast`. Needs `OPEN_WEATHER_API_KEY`. |
| `pdf_parser/tools.py` | PDF utilities. | `pdf_parser`, `extract_pdf_text`, `extract_pdf_metadata`, `extract_pdf_text_from_url`. |
| `sqlite_store/tools.py` | CRUD over the SQLite data store (via `app/db/repository.py`). | `sqlite_create_record`, `sqlite_get_record`, `sqlite_update_record`, `sqlite_delete_record`, `sqlite_list_records`. |
| `stable_diffusion/tools.py` | Image generation. | `generate_image`. |
| `proxmox/tools.py` | Proxmox VE management (`get_proxmox_tools()`). | Needs `PROXMOX_HOST`, `PROXMOX_USER`, `PROXMOX_TOKEN_NAME`, `PROXMOX_TOKEN_VALUE`. Verify it is registered in `__init__.py` before relying on it. |
| `*/__init__.py` | Package markers. | — |

**New integration:** create `agentic_mcp/<name>/tools.py` (+ `__init__.py`) with `@tool`
functions, register it in `agentic_mcp/__init__.py`, and add the server to
`resources/agentic.json` → `mcpServers`. Run `agentic tools reload` to refresh a running bot.

## `src/agentic/vector_memory/`

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker. | Rarely. |
| `tools.py` | `memory_search(chat_id, query, limit)` agent tool: semantic search over past conversation via `MemoryRetriever`. | Changing memory tools exposed to agents. |

## `src/agentic/cli/` (command-line interface)

Commands are Click groups attached in `src/agentic/__init__.py`. See the
[CLI reference](cli.md) for usage.

| File | Purpose | Change it when… |
|---|---|---|
| `__init__.py` | Package marker. | Rarely. |
| `agents.py` | `agentic agents …`: `list`, `schema`, `write`, `update` and delete for agent configs and `instructions.md`, with validation. | Changing agent management commands. |
| `config.py` | `agentic config get/set`: reads and writes `agentic.json` by JSONPath. | Changing config editing. |
| `mcp.py` | `agentic mcp run`: starts the MCP server (loads `.env`, runs `agentic_mcp.main`). | Changing MCP launch options. |
| `message.py` | `agentic message add`: send-message command (currently a placeholder). | Implementing message sending. |
| `tools.py` | `agentic tools reload`: calls the gateway `/admin/tools/reload` endpoint. | Changing tool management commands. |

## `src/agentic/websocket_client/`

| File | Purpose |
|---|---|
| `__init__.py` | Package marker. |
| `main.py` | Minimal example client connecting to `ws://localhost:5000/ws/{chat_id}`. Use it as a template for custom front-ends. |

## Non-source directories

| Path | Purpose |
|---|---|
| `skills/` | Skills the agent loads automatically. Each has a `SKILL.md` (some `SKILLS.md`) and optional scripts: `agentic-cli`, `calendar-manager`, `create-agent`, `deep-agents-skill-creator`, `trip_planner`, `user-profile-manager`. |
| `workspace/` | Runtime workspace mounted into agents. `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `USER.md`, `MEMORY.md`, `SUMMARY.md` are persona and memory files; `agents/<name>/instructions.md` defines each agent (`main`, `memory_compactor`, `trip_planner`, …); `custom_tools/`, `memory/` (daily logs) and `vector_store/` hold runtime state. |
| `resources/agentic.json` | Models, agents, skills, tool permissions and `mcpServers`. |
| `resources/application.yml` | Runtime config: secrets provider (`env://VAR_NAME`), channels, Telegram token. |
| `alembic/` | `env.py` (imports `Base` from `app/db/models.py`), `script.py.mako`, and `versions/` (e.g. `0001_create_data_records.py`). |
| `tests/unittests/` | Fast pytest tests, one module per source area (backends, db, gateway, tools, memory, vector store…). |
| `tests/integration/` | BDD tests: `features/`, `steps/`, `scenarios/`, `mcp_fixtures/`, Docker Compose scaling tests. Marked `docker` / `behaviour`. |
| `docs/` | MkDocs pages; `docs/superpowers/` holds internal plans and is excluded from the site. |
| `.github/` | `copilot-instructions.md`, agents and workflows (docs deployment). |

## Where do I change X?

| Task | Where |
|---|---|
| Add an external integration or tool | `agentic_mcp/<name>/tools.py`, register in `agentic_mcp/__init__.py` and `resources/agentic.json` (`mcpServers`) |
| Add a built-in tool for every agent | `app/common/tools.py` (`set_common_tools`) |
| Add a new agent | `workspace/agents/<name>/instructions.md` + `resources/agentic.json` |
| Add a skill | `skills/<name>/SKILL.md` |
| Add a channel (Slack, Discord…) | `app/gateway/adapters/<channel>/` implementing `ChannelAdapter`; start it in `bot_app.py` |
| Add a config field | `app/config.py` model, then `resources/agentic.json` and the docs |
| Add a DB table or column | `app/db/models.py`, `app/db/schemas.py`, `app/db/repository.py` and a new `alembic/versions/` migration |
| Add a vector-store backend | `app/vectorstore_factory.py` |
| Add middleware or tool notifications | `app/common/middleware.py`, wire it in `app/agents.py` |
| Add a CLI command | `cli/<group>.py`, attach it in `src/agentic/__init__.py`; document it in `docs/cli.md` |
| Add a scheduled job type | `app/scheduler/` |
| Add an HTTP/WebSocket endpoint | `app/gateway/server.py` |

## Conventions

- **Config first:** wire behaviour through `resources/agentic.json` / `application.yml`
  instead of hardcoding it.
- **Secrets:** use `env://VAR_NAME` references. Never commit credentials.
- **Layering:** keep persistence in `app/db/repository.py`, validation in schemas, and I/O or
  presentation in adapters and CLI, not in agent logic.
- **Quality:** add type hints, run `uv run ruff check .`, and add or update tests under `tests/`.
- **Commits:** use Conventional Commit prefixes (`feat:`, `fix:`, `docs:` …).

## Maintaining this page

Update this page in the same PR whenever you:

- add, rename, move or delete a file or package under `src/`,
- change a module's responsibility, its public classes or its tools,
- add or remove an MCP server, channel adapter, CLI command or Alembic migration,
- change the top-level layout (new top-level folder, moved config or skills directory).

Reviewers should block structural PRs that leave this page out of date.

