from pathlib import Path

CRON_SCHEDULE_FILENAME = "tests/resources/cron_schedules.json"
AGENTIC_CONFIG_FILENAME = "tests/resources/agentic.json"
MCP_FIXTURE_PATH = "tests/integration/mcp_fixtures/main.yaml"

AGENTIC_ORIGINAL_WORKSPACE_PATH = Path.cwd() / "workspace"

AGENTIC_CONFIG_JSON = "tests/resources/agentic.json"
AGENTIC_WORKSPACE_PATH = "tests/workspace"
BOOTSTRAP_CONFIG_PATH = "tests/resources/BOOTSTRAP.md"

MAIN_AGENT_MODEL = "openai:gemma-4-e2b-it-qat-mtp"
MAIN_MODEL_ID = "custom-gemma-4-e2b-it"

# JUDGE_MODEL = "openai:minimaxai/minimax-m3.1-flash"
# JUDGE_MODEL_BASE_URL = "https://integrate.api.nvidia.com/v1"
JUDGE_MODEL_BASE_URL = "http://host.docker.internal:8080/v1"
JUDGE_MODEL = MAIN_AGENT_MODEL