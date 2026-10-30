WORKSPACE_ROOT_ENV = "AGENTIC_WORKSPACE_ROOT"

CRON_SCHEDULE_FILENAME_ENV = "CRON_SCHEDULE_FILENAME"

AGENTIC_FILE_NAME_PROP = "app.agentic.config_path"

TELEGRAM_BOT_TOKEN_PROP = "app.channels.telegram.token"
TELEGRAM_BOT_DEFAULT_CHAT_ID = "app.channels.telegram.default_chat_id"
CRON_UPDATE_EVENT = "cron_schedule_updated"

EXTERNAL_API_LOCALAI_BASE_URL_PROP = "app.externals.localai.base_url"
EXTERNAL_API_LOCALAI_DEFAULT_IMAGE_MODEL_PROP = (
    "app.externals.localai.default_image_model"
)
EXTERNAL_API_LOCALAI_REQUEST_TIMEOUT_PROP = "app.externals.localai.request_timeout"

import os

def check_for_required_env_vars() -> None:
    envs = [WORKSPACE_ROOT_ENV, CRON_SCHEDULE_FILENAME_ENV]
    if not all(var in os.environ for var in envs):
        missing_vars = [var for var in envs if var not in os.environ]
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

def get_workspace_root() -> str:
    """
    Get the absolute path to the workspace root directory.
    This function checks for the environment variable 'AGENTIC_WORKSPACE_ROOT'.
    If not set, it defaults to the current working directory.
    """
    return os.environ.get(WORKSPACE_ROOT_ENV, os.getcwd())
