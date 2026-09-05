"""Alembic migration environment for Agentic's SQLite data store.

Resolves the database URL via `agentic.app.db.engine.get_sqlite_url()`
(the same helper the running app/MCP server uses) rather than a
hardcoded/`alembic.ini`-configured URL, so there is a single source of
truth for the DB path (`workspace/data/agentic.db`, overridable via the
`AGENTIC_SQLITE_PATH` env var).
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `agentic` importable when running `alembic` from the repo root,
# mirroring `pyproject.toml`'s `pythonpath = ["."]` test config.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic.app.db.engine import get_sqlite_url  # noqa: E402
from agentic.app.db.models import Base  # noqa: E402

# this is the Alembic Config object, which provides access to values
# within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override whatever `sqlalchemy.url` is in alembic.ini with the real,
# app-resolved SQLite path.
config.set_main_option("sqlalchemy.url", get_sqlite_url())

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

