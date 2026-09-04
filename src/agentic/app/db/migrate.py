"""Programmatic Alembic migration runner.

Lets the MCP server (and tests) run ``alembic upgrade head`` against the
resolved SQLite path without shelling out, using Alembic's Python API.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"


def get_alembic_config() -> Config:
    """Build an Alembic `Config` pointed at the repo-root `alembic.ini`."""
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config


def run_migrations() -> None:
    """Run all pending migrations (``alembic upgrade head``) idempotently.

    Safe to call on every startup: Alembic tracks the applied revision in
    the `alembic_version` table and is a no-op if already up to date.
    """
    logger.info("Applying SQLite migrations (alembic upgrade head)")
    command.upgrade(get_alembic_config(), "head")


